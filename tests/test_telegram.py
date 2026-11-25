"""Bot Telegram: quyền truy cập, giao việc, duyệt bằng nút và trả hồ sơ. Không gọi Telegram thật."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import telegram_bot
from main import SAMPLE
from monitoring.runner import manager
from telegram_bot import api, messages, store
from telegram_bot.bot import STALE, Bot

OWNER, OTHER = 1001, 2002
REQUEST = SAMPLE.replace("2,5 tỷ", "8 tỷ")
TOKEN = "123456789:" + "A" * 35


class FakeClient:
    def __init__(self):
        self.sent, self.docs, self.photos, self.edits, self.fail = [], [], [], [], None

    def call(self, method, data=None, files=None, timeout=20):
        return {}

    def send(self, chat, text, keyboard=None):
        if self.fail:
            raise self.fail
        self.sent.append((chat, text, keyboard or []))
        return len(self.sent)

    def edit(self, chat, message_id, text, keyboard=None):
        self.edits.append((chat, text))

    def send_document(self, chat, path, caption=""):
        self.docs.append(path.name)

    def send_photos(self, chat, items):
        self.photos += [caption for _, caption in items]

    def data(self, label):
        return next(b["callback_data"] for _, _, rows in reversed(self.sent) for row in rows for b in row if label in b["text"])


@pytest.fixture
def bot():
    store._query("SELECT 1")
    for table in ("telegram_runs", "telegram_chats", "telegram_state"):
        store._query(f"DELETE FROM {table}")
    bot = Bot(FakeClient(), lambda: {OWNER, OTHER})
    yield bot
    for run in manager.runs.values():
        if run.thread:
            run.thread.join(timeout=60)


def text(bot, value, user=OWNER, chat_type="private", chat=None):
    bot.handle({"update_id": 1, "message": {"text": value, "from": {"id": user, "first_name": "A"},
                                            "chat": {"id": chat or user, "type": chat_type}}})


def press(bot, data, user=OWNER):
    bot.handle({"update_id": 1, "callback_query": {"id": "q", "data": data, "from": {"id": user},
                                                   "message": {"message_id": 5, "text": "trước", "chat": {"id": user, "type": "private"}}}})


def settle(bot, timeout=60):
    """Chờ lượt đứng lại rồi chạy một vòng thông báo."""
    run = manager.get(store.current_run(OWNER))
    end = time.time() + timeout
    while run.status == "running" and time.time() < end:
        time.sleep(0.05)
    if run.thread:
        run.thread.join(timeout=10)
    for row in store.watched():
        bot.notify(row)
    return run


def assign(bot, mode, request=REQUEST):
    text(bot, request)
    press(bot, bot.client.data({"auto": "Chạy tự động", "key": "Duyệt bước chính", "all": "Duyệt mọi bước"}[mode]))
    return settle(bot)


def test_only_allowed_private_accounts(bot):
    before = set(manager.runs)
    bot.allowed = lambda: {OWNER}
    text(bot, REQUEST, user=666)
    text(bot, "/trangthai", user=666)
    press(bot, "d|x|auto", user=666)
    text(bot, REQUEST, chat_type="group", chat=-5)
    assert len(bot.client.sent) == 1 and "666" in bot.client.sent[0][1]   # chỉ báo mã một lần
    assert list(bot.pending) == [666] and set(manager.runs) == before


def test_message_needs_confirmation_and_runs_once(bot):
    before = set(manager.runs)
    text(bot, "chào bạn")
    assert "Giao việc mới" in bot.client.sent[-1][1] and set(manager.runs) == before
    start = bot.client.data("Chạy tự động")
    press(bot, bot.client.data("Hủy"))
    press(bot, start)
    assert set(manager.runs) == before and "hết hiệu lực" in bot.client.edits[-1][1]


def test_auto_run_delivers_package(bot):
    run = assign(bot, "auto")
    assert run.status == "done"
    assert bot.client.docs == ["ban_ve.pdf", "ban_ve_dxf.zip", "mo_hinh_3d.glb", "mo_hinh_3d.dxf", "thuyet_minh.docx", "du_toan.xlsx"]
    assert any("Phối cảnh" in caption for caption in bot.client.photos)
    assert any("Đã hoàn thành" in item[1] for item in bot.client.sent)
    count = len(bot.client.sent), len(bot.client.docs)
    for row in store.watched():
        bot.notify(row)
    assert count == (len(bot.client.sent), len(bot.client.docs))          # không báo lặp
    # khởi động lại bot: không gửi lại hồ sơ cũ
    again = Bot(FakeClient(), lambda: {OWNER})
    for row in store.watched():
        again.notify(row)
    assert not again.client.sent and not again.client.docs
    # giao một agent làm lại trên lượt đã xong
    text(bot, "/agent")
    press(bot, bot.client.data("Dự toán chi phí"))
    press(bot, bot.client.data("Giao làm lại"))
    assert settle(bot).status == "done" and len(bot.client.docs) == 12


def test_approval_flow_choose_feedback_and_stale_buttons(bot):
    run = assign(bot, "key")
    assert run.status == "awaiting_approval" and "Phương án" in bot.client.sent[-1][1]
    approve, choose = bot.client.data("Đồng ý"), bot.client.data("Chọn B")
    first = run.interrupt_id
    press(bot, bot.client.data("Góp ý"))
    text(bot, "phòng khách 25 m2")
    assert "Đã gửi góp ý" in bot.client.sent[-1][1]
    settle(bot)
    assert run.status == "awaiting_approval" and run.interrupt_id != first
    for old in (approve, choose):                                       # nút của điểm duyệt cũ không có tác dụng
        current = run.interrupt_id
        press(bot, old)
        assert STALE in bot.client.edits[-1][1] and run.interrupt_id == current
    assert not run.answer("approve", expected=first)
    press(bot, bot.client.data("Đồng ý"))
    settle(bot)
    assert run.interrupt_payload["agent"] == "drafter" and bot.client.photos
    press(bot, bot.client.data("⏹ Dừng"))
    assert run.status == "awaiting_approval"                            # cần xác nhận
    press(bot, bot.client.data("Xác nhận dừng"))
    settle(bot)
    assert run.status == "stopped" and "Lượt đã dừng" in bot.client.sent[-1][1]


def test_missing_input_is_appended_then_conflict_is_rewritten(bot):
    run = assign(bot, "auto", "Cần nhà hiện đại, 3 phòng ngủ, ngân sách 8 tỷ, ở Hà Nội")
    assert run.status == "needs_input" and "nhắn phần còn thiếu" in bot.client.sent[-1][1]
    text(bot, "Đất 5x20 m, hướng Đông Nam")
    assert settle(bot).status == "done"
    assert "hiện đại" in run.state()["user_request"] and "5x20" in run.state()["user_request"]
    content, rewrite = messages.clarification({"clarification": {"conflicts": ["2 hoặc 3 tầng"], "questions": []}, "user_request": "x"})
    assert rewrite and "gửi lại toàn bộ" in content


def test_other_user_cannot_control_and_one_active_run(bot):
    run = assign(bot, "all")
    approve = bot.client.data("Đồng ý")
    for data in (approve, f"s|{run.run_id}", f"r|{run.run_id}|drafter", f"u|{run.run_id}", f"g|{run.run_id}|architect"):
        sent = len(bot.client.sent)
        press(bot, data, user=OTHER)
        assert len(bot.client.sent) == sent
    assert run.status == "awaiting_approval" and store.current_run(OTHER) is None
    text(bot, "Đất 5x20, 3 phòng ngủ")                                  # đang chờ duyệt: không mở lượt mới
    assert "đang chờ bạn duyệt" in bot.client.sent[-1][1]
    text(bot, "/giao Đất 5x20, 3 phòng ngủ")
    assert "chưa xong" in bot.client.sent[-1][1]
    press(bot, approve[:-7] + "bogus")
    press(bot, "a|" + run.run_id)
    press(bot, "zz")
    assert run.status == "awaiting_approval"
    run.stop()


def test_failed_notification_is_retried_without_spam(bot):
    text(bot, REQUEST)
    press(bot, bot.client.data("Duyệt mọi bước"))
    run = manager.get(store.current_run(OWNER))
    bot.client.fail = api.TelegramError(0, "mất mạng")
    settle(bot)
    row = store.watched()[0]
    assert not row["notified"].startswith("awaiting")
    bot.client.fail = None
    sent = len(bot.client.sent)
    bot.notify(row)
    assert len(bot.client.sent) == sent                                 # đang chờ trước khi thử lại
    bot.retry.clear()
    bot.notify(row)
    assert "Duyệt cấu hình" in bot.client.sent[-1][1]
    run.stop()


def test_status_and_unsafe_text(bot):
    run = assign(bot, "all")
    text(bot, "/trangthai")
    assert "🟡 Chủ nhiệm dự án: Chờ bạn" in bot.client.sent[-1][1] and "▫️ Triển khai bản vẽ: Chờ đến lượt" in bot.client.sent[-1][1]
    text(bot, "/__init__ x")
    assert "Chưa có lệnh" in bot.client.sent[-1][1]
    run.stop()
    text(bot, "x" * 3001)
    assert "quá 3000" in bot.client.sent[-1][1]
    # tệp ngoài thư mục của lượt không được gửi
    assert messages.documents({"output_dir": "/tmp/none", "final_files": {"ban_ve_pdf": "/etc/hosts"}}) == []


@pytest.fixture
def server(monkeypatch):
    calls, queue = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"] or 0))
            token, method = self.path.split("/")[1:3]
            calls.append((method, body))
            if token != "bot" + TOKEN:
                reply = {"ok": False, "error_code": 401, "description": "Unauthorized"}
            elif method == "getUpdates":
                reply = {"ok": True, "result": queue.pop(0) if queue else []}
                time.sleep(0.02)
            else:
                reply = {"ok": True, "result": {"username": "kts_bot", "message_id": 7}}
            data = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    monkeypatch.setattr(api, "BASE", f"http://127.0.0.1:{http.server_port}")
    yield calls, queue
    http.shutdown()


def test_polling_settings_and_single_instance(server, monkeypatch, tmp_path):
    import api_keys

    calls, queue = server
    env = tmp_path / ".env"
    env.write_text("LLM_PROVIDER=none\n", encoding="utf-8")
    monkeypatch.setattr(api_keys, "ENV_FILE", env)
    store._query("DELETE FROM telegram_state")
    queue.append([{"update_id": 41, "message": {"text": "/start", "from": {"id": OWNER, "first_name": "Chủ"},
                                                "chat": {"id": OWNER, "type": "private"}}}])
    for bad in ("abc", "123456789:short", TOKEN + "\nX=1", TOKEN[:-1] + "B"):
        with pytest.raises(ValueError):
            telegram_bot.save_token(bad)
    assert "TELEGRAM" not in env.read_text(encoding="utf-8")
    try:
        assert telegram_bot.save_token(TOKEN) == "kts_bot"
        first = telegram_bot._holder.bot
        telegram_bot.ensure_started()
        assert telegram_bot._holder.bot is first                        # nhiều lần vẽ trang vẫn một bot
        end = time.time() + 10
        while not telegram_bot.status()["pending"] and time.time() < end:
            time.sleep(0.02)
        assert telegram_bot.status()["state"] == "online" and telegram_bot.status()["pending"] == {OWNER: "Chủ"}
        assert store.offset() == 42
        telegram_bot.allow(OWNER)
        assert telegram_bot.allowed_users() == {OWNER} and not telegram_bot.status()["pending"]
        assert f"TELEGRAM_ALLOWED_USERS={OWNER}" in env.read_text(encoding="utf-8")
        telegram_bot._holder.generation = object()                      # mã nguồn được nạp lại
        telegram_bot.ensure_started()
        assert telegram_bot._holder.bot is not first and first.stopping.is_set()
    finally:
        telegram_bot.revoke(OWNER)
        telegram_bot.remove_token()
    assert env.read_text(encoding="utf-8").strip() == "LLM_PROVIDER=none" and telegram_bot.status()["state"] == "off"


def test_client_hides_token_and_splits_text(server, monkeypatch, tmp_path):
    calls, _ = server
    client = api.Client(TOKEN)
    client.send(1, "dòng\n" * 1500)
    assert len([c for c in calls if c[0] == "sendMessage"]) == 2
    path = tmp_path / "ban_ve.pdf"
    path.write_bytes(b"%PDF-noi-dung")
    client.send_document(1, path, "Bộ bản vẽ")
    client.send_photos(1, [(path, "a"), (path, "b")])
    assert [c[0] for c in calls[-2:]] == ["sendDocument", "sendMediaGroup"] and b"%PDF-noi-dung" in calls[-2][1]
    monkeypatch.setattr(api, "BASE", "http://127.0.0.1:9")
    with pytest.raises(api.TelegramError) as error:
        client.call("getMe")
    assert TOKEN not in str(error.value) and error.value.__cause__ is None
