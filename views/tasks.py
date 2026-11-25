"""Bảng theo dõi công việc thật và các lần thực hiện đã lưu."""
from datetime import datetime, timezone

import streamlit as st

import task_timeline
import ui_theme as ui
from config import AGENT_ORDER
from graph import NODE_AGENT
from monitoring import events, tasks
from monitoring.timeline import MARK_LABELS, build_timeline, timestamp
from ui_common import label
from views.performance import open_profile, show_performance
from views.task_reviews import show_task_reviews


STATUSES = {
    "queued": "Chờ", "running": "Đang làm", "awaiting_approval": "Chờ duyệt",
    "completed": "Hoàn thành", "error": "Lỗi", "canceled": "Hủy",
}
ACCEPTANCE = {
    "pending": "Chờ quyết định", "accepted": "Được nghiệm thu", "changes_requested": "Yêu cầu sửa",
    "forwarded": "Chuyển tiếp kèm vấn đề tồn tại", "canceled": "Đã hủy", None: "Chưa có quyết định",
}
CAUSES = {
    "agent_error": "Lỗi agent", "missing_input": "Thiếu đầu vào", "user_change": "Người dùng đổi yêu cầu",
    "infrastructure": "API hoặc hạ tầng", "unknown": "Chưa xác định",
}
UNKNOWN = "Chưa xác định"
LIVE_STATES = {"running", "awaiting_approval", "needs_input"}


def seconds(value: float | None) -> str:
    return f"{value:.3f} giây" if value is not None else UNKNOWN


def date(value: str | None) -> str:
    return datetime.fromisoformat(value).astimezone().strftime("%d/%m/%Y %H:%M:%S") if value else UNKNOWN


def cost(attempt: dict) -> str:
    value = attempt["cost_usd"]
    if value is None:
        return UNKNOWN
    return f"{value:.6g} USD" + (" · Ước tính" if attempt["cost_basis"] == "estimated" else "")


def known(value) -> str:
    return str(value) if value is not None else UNKNOWN


def show_attempt(attempt: dict, *, latest: bool, live: bool = False) -> None:
    with st.expander(f"Lần {attempt['attempt_no']} · {STATUSES[attempt['status']]}", expanded=latest):
        details = [
            ("Mã lần thực hiện", attempt["attempt_id"]),
            ("Hoàn thành xử lý", "Đã xử lý" if attempt["processed"] else "Chưa xử lý xong"),
            ("Nghiệm thu", ACCEPTANCE[attempt["acceptance"]]),
            ("Giao việc", date(attempt["assigned_at"])),
            ("Bắt đầu", date(attempt["started_at"])),
            ("Kết thúc lần thực hiện", date(attempt["finished_at"])),
            ("Chờ trước khi xử lý", seconds(attempt["wait_s"])),
            ("Thời gian xử lý", seconds(attempt["processing_s"])),
            ("Mời duyệt", date(attempt["approval_requested_at"])),
            ("Thời điểm quyết định", date(attempt["decision_at"])),
            ("Phiên bản phương án", known(attempt["output_version"] or attempt["input_version"])),
            ("Model", known(attempt["model"])),
            ("Lượt gọi model", known(attempt["call_count"])),
            ("Token", known(attempt["tokens"])),
            ("Chi phí model", cost(attempt)),
        ]
        if attempt["rubric"]:
            details.append(("Bộ tiêu chí nghiệm thu", attempt["rubric"]["version"]))
        if attempt["input_version"] and attempt["output_version"] and attempt["input_version"] != attempt["output_version"]:
            details.append(("Phiên bản đầu vào", attempt["input_version"]))
        if attempt["approval_version"] and attempt["approval_version"] != (attempt["output_version"] or attempt["input_version"]):
            details.append(("Phiên bản đưa ra duyệt", attempt["approval_version"]))
        if attempt["approval_requested_at"] and attempt["decision_at"]:
            delay = datetime.fromisoformat(attempt["decision_at"]) - datetime.fromisoformat(attempt["approval_requested_at"])
            details.append(("Thời gian chờ duyệt", seconds(max(0.0, delay.total_seconds()))))
        if live:
            running = attempt["status"] == "running"
            start = timestamp(attempt["started_at"] if running else attempt["approval_requested_at"])
            if start is not None:
                elapsed = max(0.0, datetime.now(timezone.utc).timestamp() - start / 1000)
                details.append(("Đang xử lý" if running else "Đang chờ duyệt", seconds(elapsed)))
        if attempt["api_errors"]:
            details.append(("Lượt gọi model gặp lỗi", str(attempt["api_errors"])))
        if attempt["retry_reason"]:
            details += [("Lý do chạy lại", attempt["retry_reason"]),
                        ("Nhóm nguyên nhân sửa", CAUSES[attempt["retry_category"]])]
        if attempt["failure_category"]:
            details.append(("Vướng mắc ghi nhận", CAUSES[attempt["failure_category"]]))
        ui.html_block(ui.kv([(name, ui.esc(value)) for name, value in details]))
        if attempt["summary"]:
            st.caption(attempt["summary"])
        if attempt["error"]:
            st.text(attempt["error"])
        inputs, outputs = st.tabs(["Đầu vào", "Đầu ra"])
        with inputs:
            st.json(attempt["input"], expanded=False)
        with outputs:
            if attempt["output"] is not None:
                st.json(attempt["output"], expanded=False)
            else:
                st.caption("Chưa ghi nhận đầu ra.")


def run_label(row: dict) -> str:
    name = row["summary"].get("ten_du_an") or " ".join(row["request"].split())[:68] or "Lượt thiết kế"
    return f"{name} · {row['run_id']}"


def table_version(row: dict) -> str:
    version = row["output_version"] or row["input_version"]
    if version is None:
        return UNKNOWN
    parts = version.split(" · ")
    return " · ".join(parts[:2]) if len(parts) > 1 else version[:12]


def dismiss_task_dialog() -> None:
    st.session_state.pop("task_dialog", None)


DETAIL_VIEW = ":material/list_alt: Chi tiết"
REVIEW_VIEW = ":material/rate_review: Đánh giá task"


def agent_name(row: dict) -> str:
    """Tên agent của task; agent tùy biến đã xóa vẫn hiện tên lưu trong task."""
    if row["agent_id"].startswith("custom_"):
        return f"{label(row['agent_id']) if label(row['agent_id']) != row['agent_id'] else row['name']} (tùy biến)"
    return label(row["agent_id"])


def task_title(row: dict) -> str:
    return f"{row['name']} · {agent_name(row)}"


def open_task(run_id: str, task_id: str, view: str, *, sync_picker: bool = True) -> None:
    st.session_state["task_dialog"] = (task_id, view)
    st.session_state[f"task_dialog_view_{task_id}"] = view
    if sync_picker:  # chỉ gọi từ callback, trước khi ô chọn trên trang được tạo lại
        st.session_state[f"task_detail_{run_id}"] = task_id


@st.dialog("Chi tiết công việc", width="large", on_dismiss=dismiss_task_dialog)
def task_dialog(run_id: str, row: dict, view: str, index: dict | None = None) -> None:
    task_id = row["task_id"]
    if index and len(index) > 1:
        switch_key = f"task_dialog_switch_{run_id}"
        st.session_state[switch_key] = task_id

        def switch() -> None:
            current = st.session_state.get(f"task_dialog_view_{task_id}", view)
            open_task(run_id, st.session_state[switch_key], current)

        st.selectbox("Chuyển công việc", list(index), format_func=lambda ident: task_title(index[ident]),
                     key=switch_key, on_change=switch,
                     help="Chọn task của agent khác để xem chi tiết hoặc chấm điểm mà không cần đóng hộp thoại.")
        if (st.session_state.get("task_dialog") or (task_id,))[0] != task_id:
            st.rerun()  # hộp thoại chạy như fragment với tham số cũ: chạy lại cả trang để mở task mới
    ui.section(row["name"], row["description"], glyph="clipboard")
    ui.html_block('<div class="aa-task-badge-group">' + ui.pill(agent_name(row), "info")
                  + ui.pill(STATUSES[row["status"]], "warning" if row["status"] == "awaiting_approval" else "brand")
                  + "</div>")
    detail, review = st.tabs([DETAIL_VIEW, REVIEW_VIEW],
                             default=view, key=f"task_dialog_view_{task_id}", on_change="rerun")
    if detail.open:
        with detail:
            st.caption(f"Mã công việc · {task_id}")
            ui.html_block(ui.kv([("Tiêu chí nghiệm thu", ui.esc(row["acceptance_criteria"]))]))
            for attempt in tasks.attempts(task_id):
                show_attempt(attempt, latest=attempt["attempt_no"] == row["attempt_no"])
    elif review.open:
        with review:
            show_task_reviews(run_id, task_id)


def show_table(run_id: str, agent: str | None, status: str) -> None:
    rows = tasks.list_tasks(run_id, agent=agent, status=status or None)
    if not rows:
        st.info("Không có công việc khớp bộ lọc." if agent or status else
                "Chưa ghi nhận công việc cho lượt này. Các lượt cũ vẫn có nhật ký bàn giao trong Studio AI.")
        return
    with st.container(border=True, key="task_list"):
        ui.section("Danh sách công việc", f"{len(rows)} task trong bộ lọc.")
        table = st.dataframe([{
            "Công việc": row["name"], "Agent": agent_name(row), "Trạng thái": STATUSES[row["status"]],
            "Nghiệm thu": ACCEPTANCE[row["acceptance"]], "Số lần": row["attempt_no"],
            "Phiên bản": table_version(row), "Thời gian xử lý": seconds(row["processing_s"]),
        } for row in rows], hide_index=True, width="stretch", column_config={
            "Công việc": st.column_config.TextColumn(width=205),
            "Agent": st.column_config.TextColumn(width=170),
            "Trạng thái": st.column_config.TextColumn(width=112),
            "Nghiệm thu": st.column_config.TextColumn(width=192),
            "Số lần": st.column_config.NumberColumn(width=75),
            "Phiên bản": st.column_config.TextColumn(width=115),
            "Thời gian xử lý": st.column_config.TextColumn(width=130),
        }, on_select="rerun", selection_mode="single-row", key=f"task_table_{run_id}")
        index = {row["task_id"]: row for row in rows}
        ids = list(index)
        detail_key = f"task_detail_{run_id}"
        picked = table.selection.rows if table is not None else []
        picked_id = ids[picked[0]] if picked and picked[0] < len(ids) else None
        if picked_id and st.session_state.get(f"task_table_applied_{run_id}") != picked_id:
            st.session_state[f"task_table_applied_{run_id}"] = picked_id  # bấm dòng trong bảng để chọn task
            st.session_state[detail_key] = picked_id
        if st.session_state.get(detail_key) not in index:
            st.session_state[detail_key] = ids[0]
        st.caption("Bấm một dòng trong bảng hoặc chọn bên dưới để xem chi tiết và chấm điểm task của từng agent.")
        form, details, rating = st.columns([2.25, 1, 1], vertical_alignment="bottom")
        task_id = form.selectbox("Chọn công việc", ids, format_func=lambda ident: task_title(index[ident]), key=detail_key)
        inspect = details.button("Mở chi tiết", icon=":material/open_in_new:", width="stretch")
        assess = rating.button("Đánh giá task", icon=":material/rate_review:", width="stretch")
        if inspect or assess:
            open_task(run_id, task_id, REVIEW_VIEW if assess else DETAIL_VIEW, sync_picker=False)
    selected = st.session_state.get("task_dialog")
    if selected and selected[0] in index:
        task_dialog(run_id, index[selected[0]], selected[1], index)


def show_timeline(run_id: str, agent: str | None, run_status: str) -> None:
    attempts = tasks.timeline_attempts(run_id)
    visible_attempts = {row["attempt_id"] for row in attempts if agent is None or row["agent_id"] == agent}
    data = build_timeline(attempts, events.get_events(run_id), run_status=run_status, targets=NODE_AGENT, agent=agent)
    if not data["attempts"] and not data["markers"]:
        if attempts and not visible_attempts:
            st.info("Chưa ghi nhận lần thực hiện hoặc sự kiện của agent này trong lượt đang xem.")
        else:
            st.info("Thiếu mốc thời gian để vẽ Timeline cho lượt và agent đang xem. "
                    "Lượt cũ có thể chỉ có nhật ký bàn giao trong Studio AI.")
        return
    gaps = [f"{data[key]} {name}" for key, name in (("missing_attempts", "lần thực hiện"),
                                                   ("missing_events", "sự kiện bàn giao")) if data[key]]
    if gaps:
        st.caption("Thiếu mốc thời gian ở " + " và ".join(gaps) + ".")
    elif not visible_attempts:
        st.caption("Lượt này chưa có mốc xử lý task trong bộ lọc đang xem.")
    data["scope"] = agent or "all"
    selection = task_timeline.show(data, run_id=run_id, tones=ui.TONES, statuses=STATUSES, marks=MARK_LABELS)
    selected = selection.get("id") if isinstance(selection, dict) and selection.get("scope") == data["scope"] else None
    if not isinstance(selected, str):
        st.caption("Chọn một thanh hoặc mốc trên Timeline để xem chi tiết.")
        return
    marker = next((item for item in data["markers"] if item["id"] == selected), None)
    attempt_id = selected
    if marker:
        ui.section(marker["label"], marker["detail"])
        st.caption(date(datetime.fromtimestamp(marker["at"] / 1000, timezone.utc).isoformat()))
        attempt_id = marker["attempt_id"]
    if attempt_id in visible_attempts:
        attempt = tasks.find_attempt(run_id, attempt_id)
        if attempt:
            ui.section(attempt["name"], agent_name(attempt))
            live = run_status in LIVE_STATES and attempt["status"] in ("running", "awaiting_approval")
            show_attempt(attempt, latest=True, live=live)


def work_dashboard(view: str) -> None:
    runs = {row["run_id"]: row for row in events.list_runs(None, recent_activity=True)}
    if not runs:
        st.info("Chưa có lượt thiết kế.")
        return
    saved = st.session_state.setdefault("task_work_filters", {})
    active = saved.get("run") or st.session_state.get("run_id")
    if st.session_state.get("task_run_filter") not in runs:
        st.session_state["task_run_filter"] = active if active in runs else next(iter(runs))
    st.session_state.setdefault("task_agent_filter", saved.get("agent", ""))
    run_filter, agent_filter, status_filter = st.columns([2, 1.2, 1])
    run_id = run_filter.selectbox("Lượt thiết kế", list(runs), format_func=lambda ident: run_label(runs[ident]),
                                  key="task_run_filter")
    # 9 agent lõi + agent tùy biến đã có task trong lượt đang xem (tên lấy theo task, kể cả khi agent đã bị xóa).
    custom = {row["agent_id"]: row["name"] for row in tasks.list_tasks(run_id) if row["agent_id"].startswith("custom_")}
    agents = ["", *AGENT_ORDER, *custom]
    if st.session_state.get("task_agent_filter") not in agents:
        st.session_state["task_agent_filter"] = ""
    agent = agent_filter.selectbox("Agent", agents, key="task_agent_filter",
                                    format_func=lambda value: (f"{custom[value]} (tùy biến)" if value in custom
                                                               else label(value)) if value else "Tất cả agent")
    saved.update(run=run_id, agent=agent)
    status = ""
    if view == "Công việc":
        st.session_state.setdefault("task_status_filter", saved.get("status", ""))
        status = status_filter.selectbox("Trạng thái", ["", *STATUSES], key="task_status_filter",
                                         format_func=lambda value: STATUSES[value] if value else "Tất cả trạng thái")
        saved["status"] = status
    initial_status = runs[run_id]["status"]
    polling = initial_status in LIVE_STATES

    @st.fragment(run_every=2.0 if polling else None)
    def display() -> None:
        run_status = events.run_status(run_id) if polling else initial_status
        if polling and run_status not in LIVE_STATES:
            st.rerun()
        if view == "Công việc":
            show_table(run_id, agent or None, status)
        else:
            with st.container(border=True, key="work_timeline"):
                ui.section("Diễn biến xử lý", "Chọn thanh hoặc mốc sự kiện để xem lần thực hiện.")
                show_timeline(run_id, agent or None, run_status)

    display()


PAGES = (("Công việc", ":material/assignment_turned_in: Công việc"),
         ("Timeline", ":material/calendar_month: Timeline"), ("Hiệu suất", ":material/bar_chart: Hiệu suất"))
PERFORMANCE_TAB = PAGES[-1][1]
if profile := st.session_state.pop("performance_request", None):
    open_profile(profile)
    st.session_state["tasks_tab"] = PERFORMANCE_TAB

with st.container(key="page_heading"):
    ui.page_header("Công việc & Hiệu suất", "Theo dõi tiến độ và chất lượng của đội ngũ AI.",
                   live_badge=st.session_state.get("tasks_tab") != PERFORMANCE_TAB)

tabs = st.tabs([title for _, title in PAGES], key="tasks_tab", on_change="rerun")
for (view, _), tab in zip(PAGES, tabs, strict=True):
    if tab.open:
        with tab:
            if view == "Hiệu suất":
                show_performance()
            else:
                work_dashboard(view)
