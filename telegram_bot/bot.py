"""Bot Telegram giao việc cho đội agent: nhận yêu cầu, báo tiến độ, duyệt bằng nút và trả hồ sơ.

Bot chạy cùng tiến trình với ứng dụng web và dùng chung `manager`, nên một lượt chỉ có một bộ điều khiển.
Chỉ nhận tin nhắn riêng từ tài khoản trong danh sách cho phép; mỗi người chỉ điều khiển lượt do chính họ giao.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from uuid import uuid4

from config import AGENT_LABELS, AGENT_ORDER, MAX_ITERATIONS
from graph import AGENT_NODES
from monitoring import events
from monitoring.redaction import redact
from telegram_bot import messages as msg
from telegram_bot import store
from telegram_bot.api import FILE_LIMIT, TelegramError

log = logging.getLogger(__name__)

REQUEST_LIMIT = 3000
BUSY = ("running", "awaiting_approval", "needs_input")
MODES = {"auto": ("Chạy tự động", []), "key": ("Duyệt bước chính", ["architect", "drafter"]),
         "all": ("Duyệt mọi bước", list(AGENT_NODES))}
COMMANDS = [("trangthai", "Agent nào đang làm, đang rảnh"), ("agent", "Giao lại việc cho một agent"),
            ("duyet", "Mở lại điểm duyệt đang chờ"), ("hoso", "Nhận bộ hồ sơ"), ("duan", "Các lượt đã giao"),
            ("tamdung", "Tạm dừng lượt"), ("tieptuc", "Chạy tiếp"), ("dung", "Dừng lượt"), ("help", "Hướng dẫn")]
STALE = "Nút này không còn hiệu lực: bước đó đã được xử lý hoặc đã đổi. Gửi /duyet để xem điểm duyệt hiện tại."


def button(text: str, *parts) -> dict:
    return {"text": text, "callback_data": "|".join(map(str, parts))}


def get_manager():
    from monitoring.runner import manager     # lấy lúc dùng để luôn là bộ điều khiển mà web đang dùng

    return manager


class Bot:
    def __init__(self, client, allowed):
        """`allowed()` trả về tập mã tài khoản được phép, đọc lại ở mỗi tin nhắn."""
        self.client, self.allowed = client, allowed
        self.state, self.detail, self.username = "starting", "", ""
        self.pending: OrderedDict[int, str] = OrderedDict()   # người lạ đã nhắn, chờ chủ máy cho phép
        self.drafts: dict[int, dict] = {}
        self.modes: dict[int, tuple] = {}
        self.edited: dict[str, tuple[float, str]] = {}
        self.retry: dict[str, float] = {}     # lượt gửi thông báo lỗi thì chờ trước khi thử lại
        self.stopping = threading.Event()
        self.threads: list[threading.Thread] = []

    # ------------------------------------------------------------------ vòng đời
    def start(self) -> None:
        for target in (self._poll, self._watch):
            thread = threading.Thread(target=target, name=f"telegram{target.__name__}", daemon=True)
            self.threads.append(thread)
            thread.start()

    def stop(self) -> None:
        self.stopping.set()
        self.state = "off"

    def _set(self, state: str, detail: str = "") -> None:
        if not self.stopping.is_set():
            self.state, self.detail = state, redact(detail)

    def _poll(self) -> None:
        ready, failures = False, 0
        while not self.stopping.is_set():
            try:
                if not ready:
                    self.username = self.client.call("getMe").get("username", "")
                    self.client.call("deleteWebhook")
                    self.client.call("setMyCommands", {"commands": [
                        {"command": name, "description": text} for name, text in COMMANDS]})
                    ready = True
                updates = self.client.call("getUpdates", {"timeout": 25, "offset": store.offset(),
                                                          "allowed_updates": ["message", "callback_query"]}, timeout=40)
                failures = 0
                self._set("online")
            except TelegramError as error:
                failures += 1
                if error.code in (401, 404):
                    self._set("error", "Token không hợp lệ hoặc đã bị thu hồi.")
                    return
                if error.code == 409 and failures < 5:
                    pass        # bot cũ của lần nạp trước đang nhường chỗ
                elif error.code == 409:
                    self._set("error", "Một tiến trình khác đang dùng bot này. Chỉ chạy một ứng dụng với mỗi bot.")
                else:
                    self._set("error", error.description)
                self.stopping.wait(min(30, 3 * failures))
                continue
            except Exception as error:  # noqa: BLE001
                failures += 1
                log.warning("Telegram: lỗi nhận tin (%s)", type(error).__name__)
                self._set("error", "Lỗi nội bộ khi nhận tin.")
                self.stopping.wait(min(30, 3 * failures))
                continue
            for update in updates:
                if self.stopping.is_set():
                    return
                # Ghi mốc trước khi xử lý: sự cố giữa chừng không làm một yêu cầu bị chạy hai lần.
                store.save_offset(update["update_id"] + 1)
                self.handle(update)

    def _watch(self) -> None:
        while not self.stopping.wait(2.0):
            try:
                rows = store.watched()
            except Exception as error:  # noqa: BLE001
                log.warning("Telegram: không đọc được danh sách lượt (%s)", type(error).__name__)
                continue
            for row in rows:
                if self.stopping.is_set():
                    return
                self.notify(row)

    # ------------------------------------------------------------------ nhận tin
    def handle(self, update: dict) -> None:
        query = update.get("callback_query")
        message = (query or update).get("message") or {}
        sender = (query or message).get("from") or {}
        chat, user = message.get("chat") or {}, sender.get("id")
        if chat.get("type") != "private" or not isinstance(user, int) or chat.get("id") != user or sender.get("is_bot"):
            return
        try:
            if user not in self.allowed():
                self._stranger(user, sender, query)
            elif query:
                self._callback(user, query)
            elif isinstance(message.get("text"), str) and message["text"].strip():
                self._text(user, message["text"].strip())
            else:
                self.client.send(user, "Hiện tôi chỉ đọc được tin nhắn chữ.")
        except TelegramError as error:
            log.warning("Telegram: không trả lời được (%s)", error.code)
        except Exception as error:  # noqa: BLE001
            log.warning("Telegram: lỗi xử lý tin (%s)", type(error).__name__)
            try:
                self.client.send(user, "Có lỗi khi xử lý tin nhắn này. Hãy thử lại hoặc mở ứng dụng web.")
            except TelegramError:
                pass

    def _stranger(self, user: int, sender: dict, query) -> None:
        if query or user in self.pending:
            return
        name = " ".join(filter(None, (sender.get("first_name"), sender.get("last_name")))) or "Không tên"
        self.pending[user] = msg.clip(name.replace("\n", " "), 60)
        while len(self.pending) > 20:
            self.pending.popitem(last=False)
        self.client.send(user, f"Tài khoản này chưa được phép dùng bot.\nMã của bạn: {user}\n"
                               "Chủ ứng dụng có thể cho phép ở trang Cấu hình → Telegram.")

    def _text(self, user: int, text: str) -> None:
        if text.startswith("/"):
            self.modes.pop(user, None)
            name, _, rest = text[1:].partition(" ")
            handler = getattr(self, "cmd_" + name.split("@")[0].lower(), None)
            if handler is None:
                self.client.send(user, "Chưa có lệnh này. Gửi /help để xem hướng dẫn.")
            else:
                handler(user, rest.strip())
            return
        if len(text) > REQUEST_LIMIT:
            self.client.send(user, f"Nội dung dài quá {REQUEST_LIMIT} ký tự. Hãy rút gọn rồi gửi lại.")
            return
        run = self._run(user)
        if run and run.status in ("awaiting_approval", "needs_input"):
            self._reply_to_run(user, run, text)
        else:
            self.modes.pop(user, None)
            self._draft(user, text)

    def _reply_to_run(self, user: int, run, text: str) -> None:
        payload, mode = run.interrupt_payload or {}, self.modes.pop(user, None)
        if run.status == "needs_input":
            _, rewrite = msg.clarification(payload)
            request = text if rewrite else f"{(payload.get('user_request') or '').rstrip('. ')}. {text}"
            self._answer(user, run, run.interrupt_id, "edit_request", "Đã gửi yêu cầu bổ sung cho Phân tích yêu cầu.",
                         request=request)
        elif mode == ("feedback", run.run_id, run.interrupt_id):
            self._answer(user, run, run.interrupt_id, "revise", "Đã gửi góp ý cho Thiết kế công năng.", feedback=text)
        elif payload.get("rows"):
            self.drafts[user] = {"feedback": text, "id": uuid4().hex[:8]}
            self.client.send(user, "Lượt đang chờ bạn duyệt. Gửi nội dung này làm góp ý cho Thiết kế công năng?",
                             [[button("✏️ Gửi góp ý", "f", run.run_id, run.interrupt_id[:8], self.drafts[user]["id"])],
                              [button("Bỏ qua", "x", self.drafts[user]["id"])]])
        else:
            self.client.send(user, "Lượt đang chờ bạn duyệt. Hãy dùng các nút duyệt (/duyet), hoặc /dung để dừng lượt này "
                                   "trước khi giao việc mới.")

    # ------------------------------------------------------------------ giao việc
    def _draft(self, user: int, text: str) -> None:
        busy = self._busy_run(user)
        if busy:
            self.client.send(user, f"Lượt {busy.run_id} của bạn chưa xong ({msg.STATUS.get(busy.status, busy.status)}). "
                                   "Xem /trangthai, hoặc /dung để dừng trước khi giao việc mới.")
            return
        ident = uuid4().hex[:8]
        self.drafts[user] = {"id": ident, "text": text}
        self.client.send(user, redact(f"Giao việc mới cho đội agent?\n\n{text}"),
                         [[button(f"▶️ {MODES[key][0]}", "d", ident, key)] for key in MODES]
                         + [[button("Hủy", "x", ident)]])

    def _launch(self, user: int, text: str, points: list, submission: str, **options) -> None:
        run = get_manager().start(text, approval_points=list(points), submission_id=submission, **options)
        store.add_run(run.run_id, user)
        self.client.send(user, f"Đã giao việc. Mã lượt: {run.run_id}\nTôi sẽ báo khi cần bạn duyệt và khi xong. "
                               "Lượt này cũng hiện trên ứng dụng web.")

    def _busy_run(self, user: int):
        for run_id in store.runs(user):
            if events.run_status(run_id) in BUSY:
                run = get_manager().get(run_id)
                if run.status in BUSY:
                    return run
        return None

    def _run(self, user: int):
        run_id = store.current_run(user)
        return get_manager().get(run_id) if run_id and store.owns(user, run_id) else None

    # ------------------------------------------------------------------ lệnh
    def cmd_start(self, user: int, _rest: str) -> None:
        self.client.send(user, msg.HELP)

    cmd_help = cmd_start

    def cmd_id(self, user: int, _rest: str) -> None:
        self.client.send(user, f"Mã tài khoản của bạn: {user}")

    def cmd_giao(self, user: int, rest: str) -> None:
        if not rest or len(rest) > REQUEST_LIMIT:
            self.client.send(user, f"Gửi kèm yêu cầu, tối đa {REQUEST_LIMIT} ký tự. Ví dụ: /giao Đất 5x20 m, 3 phòng ngủ, 3 tỷ")
            return
        self._draft(user, rest)

    def _need_run(self, user: int):
        run = self._run(user)
        if run is None:
            self.client.send(user, "Bạn chưa giao lượt nào. Hãy gửi yêu cầu thiết kế.")
        return run

    def cmd_trangthai(self, user: int, _rest: str) -> None:
        if run := self._need_run(user):
            self.client.send(user, msg.progress(run, run.state(), events.get_events(run.run_id)))

    def cmd_duyet(self, user: int, _rest: str) -> None:
        run = self._need_run(user)
        if run is None:
            return
        if run.status in ("awaiting_approval", "needs_input"):
            self._ask(user, run)
        else:
            self.client.send(user, f"Không có điểm duyệt nào đang chờ ({msg.STATUS.get(run.status, run.status)}).")

    def cmd_hoso(self, user: int, _rest: str) -> None:
        if run := self._need_run(user):
            self._send_files(user, run.state())

    def cmd_duan(self, user: int, _rest: str) -> None:
        listed = {row["run_id"]: row for row in events.list_runs(None)}
        rows = [listed[run_id] for run_id in store.runs(user) if run_id in listed]
        if not rows:
            self.client.send(user, "Bạn chưa giao lượt nào.")
            return
        current = store.current_run(user)
        keyboard = [[button(("● " if row["run_id"] == current else "") + msg.clip(
            f"{msg.STATUS.get(row['status'], row['status'])} · {row['summary'].get('ten_du_an') or row['request']}", 55),
            "u", row["run_id"])] for row in rows]
        self.client.send(user, "Các lượt bạn đã giao. Chọn lượt để xem và điều khiển:", keyboard)

    def cmd_tamdung(self, user: int, _rest: str) -> None:
        run = self._need_run(user)
        if run is None:
            return
        if run.status == "running":
            run.pause()
            self.client.send(user, "Lượt sẽ tạm dừng sau bước hiện tại.")
        else:
            self.client.send(user, f"Lượt không đang chạy ({msg.STATUS.get(run.status, run.status)}).")

    def cmd_tieptuc(self, user: int, _rest: str) -> None:
        run = self._need_run(user)
        if run is None:
            return
        if run.status == "paused":
            run.resume()
            self.client.send(user, "Lượt đã chạy tiếp.")
        else:
            self.client.send(user, f"Lượt không ở trạng thái tạm dừng ({msg.STATUS.get(run.status, run.status)}).")

    def cmd_dung(self, user: int, _rest: str) -> None:
        run = self._need_run(user)
        if run is None:
            return
        if run.status in (*BUSY, "paused"):
            self.client.send(user, f"Dừng hẳn lượt {run.run_id}?", [[button("⏹ Xác nhận dừng", "s", run.run_id)],
                                                                   [button("Giữ lại", "x", "-")]])
        else:
            self.client.send(user, f"Lượt đã kết thúc ({msg.STATUS.get(run.status, run.status)}).")

    def cmd_agent(self, user: int, _rest: str) -> None:
        run = self._need_run(user)
        if run is None:
            return
        buttons = [button(AGENT_LABELS[agent], "g", run.run_id, agent) for agent in AGENT_ORDER]
        self.client.send(user, redact("\n".join(["Chọn agent để giao việc:", "",
                                                 *msg.agent_lines(run, run.state(), events.get_events(run.run_id))])),
                         [buttons[i:i + 2] for i in range(0, len(buttons), 2)])

    # ------------------------------------------------------------------ nút bấm
    def _callback(self, user: int, query: dict) -> None:
        parts = str(query.get("data") or "").split("|")
        message_id = query["message"]["message_id"]
        try:
            self.client.call("answerCallbackQuery", {"callback_query_id": query["id"]})
        except TelegramError:
            pass                # phản hồi quá hạn không ảnh hưởng thao tác
        kind, args = parts[0], parts[1:]
        handler = {"d": self._cb_draft, "x": self._cb_cancel, "f": self._cb_feedback, "a": self._cb_approval, "u": self._cb_use,
                   "s": self._cb_stop, "g": self._cb_agent, "r": self._cb_rerun, "p": self._cb_proposal}.get(kind)
        if handler is None or not args:
            return
        if kind not in ("d", "x") and not store.owns(user, args[0]):
            return              # chỉ điều khiển lượt do chính người này giao
        text = handler(user, *args)
        if text:
            self._close(user, message_id, query, text)

    def _close(self, user: int, message_id: int, query: dict, text: str) -> None:
        """Bỏ nút trên tin đã xử lý để không bấm lại."""
        before = query["message"].get("text") or ""
        try:
            self.client.edit(user, message_id, f"{before}\n\n{text}".strip()[-3900:])
        except TelegramError:
            self.client.send(user, text)

    def _cb_draft(self, user: int, ident: str, mode: str = "") -> str:
        draft = self.drafts.get(user)
        if not draft or draft["id"] != ident or "text" not in draft or mode not in MODES:
            return "Yêu cầu này đã hết hiệu lực. Hãy gửi lại."
        if self._busy_run(user):
            return "Bạn đang có một lượt chưa xong. Xem /trangthai."
        del self.drafts[user]
        self._launch(user, draft["text"], MODES[mode][1], f"telegram:{ident}", max_iterations=MAX_ITERATIONS)
        return f"▶️ {MODES[mode][0]}"

    def _cb_cancel(self, user: int, ident: str = "", *_) -> str:
        if self.drafts.get(user, {}).get("id") == ident:
            del self.drafts[user]
        self.modes.pop(user, None)
        return "Đã bỏ qua."

    def _cb_feedback(self, user: int, run_id: str, short: str = "", ident: str = "") -> str:
        run, draft = get_manager().get(run_id), self.drafts.get(user)
        if not draft or draft["id"] != ident or "feedback" not in draft or not short or not run.interrupt_id.startswith(short):
            return STALE
        del self.drafts[user]
        return "✏️ Đã gửi góp ý." if run.answer("revise", draft["feedback"], expected=run.interrupt_id) else STALE

    def _cb_approval(self, user: int, run_id: str, short: str = "", action: str = "", arg: str = "") -> str | None:
        run = get_manager().get(run_id)
        ident, payload = run.interrupt_id, run.interrupt_payload or {}
        if not short or not ident.startswith(short) or run.status not in ("awaiting_approval", "needs_input"):
            return STALE
        if action == "feedback":
            if not payload.get("rows"):
                return STALE
            store.select_run(user, run_id)
            self.modes[user] = ("feedback", run_id, ident)
            self.client.send(user, "Hãy nhắn góp ý của bạn, ví dụ: phòng khách rộng hơn, thêm phòng ngủ ở tầng 2.")
            return None
        if action == "stop":
            self.client.send(user, f"Dừng hẳn lượt {run_id}?", [[button("⏹ Xác nhận dừng", "s", run_id)],
                                                               [button("Giữ lại", "x", "-")]])
            return None
        clarify = run.status == "needs_input"
        done = {"approve": "✅ Đã đồng ý.", "forward": "⏭ Đi tiếp và giữ lại cảnh báo.", "rerun": "🔁 Đã giao làm lại.",
                "choose": f"✅ Đã chọn phương án {arg}."}.get(action)
        if (done is None or clarify or (action == "forward" and not payload.get("forward"))
                or (action == "choose" and arg not in [o["id"] for o in payload.get("options") or [] if o.get("eligible")])):
            return STALE
        data = {"option": arg} if action == "choose" else {}
        return done if run.answer(action, expected=ident, **data) else STALE

    def _cb_use(self, user: int, run_id: str, *_) -> None:
        store.select_run(user, run_id)
        self.modes.pop(user, None)
        run = get_manager().get(run_id)
        self.client.send(user, msg.progress(run, run.state(), events.get_events(run_id)))

    def _cb_stop(self, _user: int, run_id: str, *_) -> str:
        run = get_manager().get(run_id)
        if run.status not in (*BUSY, "paused"):
            return f"Lượt đã kết thúc ({msg.STATUS.get(run.status, run.status)})."
        run.stop()
        return "⏹ Đã yêu cầu dừng. Nếu agent đang chạy, lượt dừng sau bước hiện tại."

    def _cb_agent(self, user: int, run_id: str, agent: str = "") -> None:
        if agent not in AGENT_ORDER:
            return
        run = get_manager().get(run_id)
        payload, keyboard = run.interrupt_payload or {}, []
        if run.can_rerun(agent, run.state()):
            keyboard.append([button("🔁 Giao làm lại", "r", run_id, agent)])
        if agent == "architect" and run.status == "awaiting_approval" and payload.get("rows"):
            keyboard.append([button("✏️ Gửi góp ý", "a", run_id, run.interrupt_id[:8], "feedback")])
        if keyboard:
            note = "Giao làm lại sẽ tạo lại kết quả của bước này và mọi bước phía sau, có thể gọi model."
        elif run.status == "running":
            note = "Lượt đang chạy nên chưa giao thêm được. Chờ xong, hoặc /tamdung trước."
        else:
            note = "Agent này chưa có kết quả trong lượt, hoặc thiếu dữ liệu của bước trước để làm riêng."
        self.client.send(user, f"{AGENT_LABELS[agent]}\n{note}", keyboard or None)

    def _cb_rerun(self, user: int, run_id: str, agent: str = "") -> str:
        run = get_manager().get(run_id)
        if agent not in AGENT_ORDER or not run.rerun_agent(agent):
            return "Chưa giao lại được: lượt đang chạy hoặc thiếu dữ liệu."
        store.select_run(user, run_id)
        return f"🔁 Đã giao {AGENT_LABELS[agent]} làm lại."

    def _cb_proposal(self, user: int, run_id: str, index: str = "") -> str:
        run = get_manager().get(run_id)
        state = run.state()
        proposals = (state.get("adjustment") or {}).get("de_xuat") or []
        if run.status != "not_passed" or not index.isdigit() or int(index) >= len(proposals):
            return STALE
        if self._busy_run(user):
            return "Bạn đang có một lượt chưa xong. Xem /trangthai."
        self._launch(user, proposals[int(index)]["request"], state.get("approval_points") or [], f"{run_id}:telegram:{index}",
                     request_fields={}, max_iterations=state.get("max_iterations", MAX_ITERATIONS),
                     fengshui_enabled=state.get("fengshui_enabled", True))
        return f"▶️ Thiết kế lại theo đề xuất {int(index) + 1}."

    def _answer(self, user: int, run, ident: str, action: str, done: str, **data) -> None:
        feedback = data.pop("feedback", "")
        self.client.send(user, done if run.answer(action, feedback, expected=ident, **data) else STALE)

    # ------------------------------------------------------------------ báo tiến độ
    def notify(self, row: dict) -> None:
        user, run_id = row["chat_id"], row["run_id"]
        if user not in self.allowed() or time.monotonic() < self.retry.get(run_id, 0):
            return
        try:
            run = get_manager().get(run_id)
            status = run.status
            # Mã điểm duyệt hoặc sự kiện cuối phân biệt hai lần cùng trạng thái (vd. làm lại rồi xong lần nữa).
            key = status if status == "running" else f"{status}:{run.interrupt_id or store.last_event(run_id)}"
            if status == "running":
                self._progress(user, run, row)
            if key == row["notified"]:
                return
            if status in ("awaiting_approval", "needs_input"):
                if status == "awaiting_approval" and (run.interrupt_payload or {}).get("sheets"):
                    self._send_previews(user, run.state())
                self._ask(user, run)
            elif status in ("done", "not_passed", "stopped", "error", "paused"):
                state = run.state()
                proposals = (state.get("adjustment") or {}).get("de_xuat") or [] if status == "not_passed" else []
                self.client.send(user, msg.result(run, state),
                                 [[button(f"▶️ Thiết kế lại theo đề xuất {i + 1}", "p", run_id, i)] for i in range(len(proposals))] or None)
                if status in ("done", "not_passed") and state.get("final_files"):
                    self._send_previews(user, state)
                    self._send_files(user, state)
            # Lượt mới bắt đầu chạy lại thì mở tin tiến độ mới.
            store.update(run_id, notified=key, **({} if status == "running" else {"progress_message": None}))
        except TelegramError as error:
            if error.code == 403:       # người dùng đã chặn bot
                store.update(run_id, notified=key)
            self.retry[run_id] = time.monotonic() + 30
            log.warning("Telegram: chưa gửi được thông báo (%s)", error.code)
        except Exception as error:  # noqa: BLE001
            self.retry[run_id] = time.monotonic() + 30
            log.warning("Telegram: lỗi báo tiến độ (%s)", type(error).__name__)

    def _progress(self, user: int, run, row: dict) -> None:
        last, before = self.edited.get(run.run_id, (0.0, ""))
        if time.monotonic() - last < 3:
            return
        text = msg.progress(run, run.state(), events.get_events(run.run_id))
        if text == before and row["progress_message"]:
            return
        if row["progress_message"]:
            self.client.edit(user, row["progress_message"], text)
        else:
            store.update(run.run_id, progress_message=self.client.send(user, text))
        self.edited[run.run_id] = (time.monotonic(), text)

    def _ask(self, user: int, run) -> None:
        payload, ident = run.interrupt_payload or {}, run.interrupt_id
        if run.status == "needs_input":
            store.select_run(user, run.run_id)
            self.client.send(user, msg.clarification(payload)[0])
            return
        short = ident[:8]

        def act(text, *parts):
            return button(text, "a", run.run_id, short, *parts)

        keyboard = [[act("✅ Đồng ý & tiếp tục", "approve")]]
        if payload.get("forward"):
            keyboard.append([act("⏭ Đi tiếp với cảnh báo ngân sách", "forward")])
        if payload.get("agent") == "architect":
            chosen = [act(f"Chọn {o['id']}", "choose", o["id"]) for o in payload.get("options") or [] if o.get("eligible")]
            if chosen:
                keyboard.append(chosen)
        keyboard.append([*([act("✏️ Góp ý", "feedback")] if payload.get("rows") else []), act("🔁 Chạy lại", "rerun"),
                         act("⏹ Dừng", "stop")])
        self.client.send(user, f"{msg.approval(payload)}\n\nLượt {run.run_id}", keyboard)

    def _send_previews(self, user: int, state: dict) -> None:
        try:
            self.client.send_photos(user, msg.previews(state))
        except (TelegramError, OSError):
            self.client.send(user, "Chưa gửi được ảnh xem trước. Có thể xem trên ứng dụng web.")

    def _send_files(self, user: int, state: dict) -> None:
        files = msg.documents(state)
        if not files:
            self.client.send(user, "Lượt này chưa xuất hồ sơ.")
            return
        failed = []
        for path, title in files:
            try:
                if path.stat().st_size > FILE_LIMIT:
                    failed.append(title)
                else:
                    self.client.send_document(user, path, title)
            except (TelegramError, OSError):
                failed.append(title)
        if failed:
            self.client.send(user, "Chưa gửi được: " + ", ".join(failed) + ". Gửi /hoso để thử lại hoặc tải trên web.")
