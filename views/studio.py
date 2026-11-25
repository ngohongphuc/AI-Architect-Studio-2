"""Studio AI, điều phối tác vụ và theo dõi lượt thiết kế."""
import csv
import io
import json
from pathlib import Path

import streamlit as st

import ui_theme as ui
from config import AGENT_ORDER
from llm import agent_model_label
from monitoring import events
from monitoring.tracker import tracker
from studio3d import component
from studio3d.data import office_data
from tools.review_display import quality_status
from ui_common import (adjustment_panel, agent_stats, approval_box, begin_draft, current_run, label, project_name,
                       run_picker, step_label)


def run_controls(run) -> None:
    if run.status not in ("running", "paused", "awaiting_approval", "needs_input"):
        return
    first, second = st.columns([1.25, 1])
    with first:
        if run.status == "running" and st.button("Tạm dừng lượt", icon=":material/pause:", width="stretch",
                                                disabled=run.pause_requested or run.stop_requested):
            run.pause()
            st.toast("Lượt sẽ tạm dừng sau bước hiện tại")
        if run.status == "paused" and st.button("Tiếp tục lượt", icon=":material/play_arrow:", width="stretch"):
            run.resume()
            st.rerun()
    with second:
        if st.button("Dừng lượt", icon=":material/stop_circle:", width="stretch", disabled=run.stop_requested):
            run.stop()
            st.rerun()


def download_timeline(run, event_rows: list[dict]) -> None:
    rows = [row for row in event_rows if row["status"] in ("done", "error")]
    if rows:
        out = io.StringIO()
        fields = ("time", "agent", "to_agent", "summary", "status", "version", "tokens", "duration_s", "feedback")
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        st.download_button("Tải timeline (CSV)", out.getvalue().encode("utf-8-sig"),
                           f"timeline_{run.run_id}.csv", "text/csv", icon=":material/download:", on_click="ignore")


def show_agent_versions(run, state: dict) -> None:
    agent = st.selectbox("Agent để xem phiên bản", AGENT_ORDER, format_func=label)
    st.caption(f"Model cấu hình · {agent_model_label(agent)}")
    if st.button("Chạy lại agent đã chọn", icon=":material/replay:",
                 disabled=not run.can_rerun(agent, state)):
        if run.rerun_agent(agent):
            st.rerun()
        else:
            st.warning("Không thể chạy lại từ checkpoint hiện hành.")
    history = [entry for entry in state.get("history") or [] if entry["agent"] == agent]
    if agent == "drafter":
        previews = {f"v{entry['version']}": (entry.get("output") or {}).get("mat_bang", []) for entry in history}
        available = [version for version, files in previews.items() if files]
        if available:
            chosen = st.multiselect("So sánh mặt bằng", available, max_selections=3)
            if chosen:
                floor = st.number_input("Tầng để so sánh", 1, max(len(previews[v]) for v in chosen), 1)
                for column, version in zip(st.columns(len(chosen)), chosen):
                    images = previews[version]
                    if floor <= len(images) and Path(images[floor - 1]).is_file():
                        column.image(images[floor - 1], caption=version)
    for entry in reversed(history):
        with st.expander(f"v{entry['version']} · vòng {entry['iteration']} · {entry['time']}"):
            st.write(entry["summary"])
            st.json(entry.get("output") or {}, expanded=False)
    if not history:
        st.caption("Chưa có phiên bản trong checkpoint.")
    prompts = tracker.prompts(run.run_id, agent)
    if prompts:
        for index, prompt in enumerate(prompts, 1):
            with st.expander(f"Lần gọi LLM {index}"):
                st.code(prompt["prompt"])
                st.code(prompt["response"])
    else:
        st.caption("Phiên này chưa ghi nhận prompt của agent.")


def show_technical(run, state: dict, event_rows: list[dict]) -> None:
    with st.expander("Dữ liệu kỹ thuật"):
        versions, log = st.tabs(["Phiên bản & prompt", "Nhật ký"])
        with versions:
            show_agent_versions(run, state)
        with log:
            if run.error:
                st.code(run.error)
            st.code("\n".join(state.get("log") or []))
            st.download_button("Tải state.json", json.dumps(
                {key: value for key, value in state.items() if key != "history"},
                ensure_ascii=False, indent=1, default=str), f"state_{run.run_id}.json", icon=":material/download:",
                               on_click="ignore")
            download_timeline(run, event_rows)


def show_rounds(state: dict, event_rows: list[dict]) -> None:
    history = state.get("history") or []
    errors = [row for row in event_rows if row.get("status") == "error"]
    with st.expander("Lịch sử kiểm định và vòng sửa"):
        if not history:
            st.caption("Chưa có bản ghi theo vòng cho lượt này.")
        groups = {}
        for item in history:
            groups.setdefault(item.get("iteration"), []).append(item)
        for number, entries in groups.items():
            st.markdown("**Kiểm tra ban đầu**" if number == 0 else
                        f"**Vòng sửa {number}**" if number is not None else "**Chưa rõ vòng sửa**")
            for item in entries:
                output = item.get("output")
                output = output if isinstance(output, dict) else {}
                stage = item.get("stage") or item.get("agent")
                target = item.get("to_agent") or output.get("dich")
                destination = f" → {label(target)}" if target and target not in ("end", "publish") else ""
                st.write(f"{item.get('time', '—')} · **{label(item.get('agent', ''))}** "
                         f"· Lần {item.get('version', '—')}{destination} · {item.get('summary', '')}")
                if stage == "reviewer" and output.get("kiem_tra"):
                    quality = quality_status({"review": output})
                    st.caption(f"Kỹ thuật · {quality['technical']} | Quy chuẩn · {quality['regulatory']}")
                for change in output.get("thay_doi") or []:
                    st.caption(f"Thay đổi · {change}")
                for issue in output.get("loi") or []:
                    st.caption(f"Phản hồi · {issue.get('muc', 'Kiểm tra')} · {issue.get('noi_dung', '')}")
        if errors:
            st.markdown("**Lỗi thực thi ghi trong nhật ký**")
            for item in errors:
                st.text(f"{item['time']} · {label(item['agent'])} · Lần {item.get('version', '—')} · {item['summary']}")


def run_steps(run, state: dict) -> tuple[str, str]:
    """(bước hiện tại, bước tiếp theo) theo trạng thái thực thi của lượt."""
    payload = run.interrupt_payload or {}
    status = run.status
    if status == "awaiting_approval" and payload:
        return f"Chờ bạn duyệt · {payload.get('title', '')}", step_label(payload.get("next"))
    if status == "needs_input":
        return "Chờ bổ sung yêu cầu", "Phân tích yêu cầu"
    if status == "running":
        return (step_label(run.current_node) if run.current_node else "Đang khởi động",
                "Xác định khi bước hiện tại xong")
    if status == "paused":
        return "Tạm dừng", step_label(run.current_node)
    if status == "done":
        return "Đã kết thúc", "Xem bộ hồ sơ ở trang Kết quả"
    if status == "not_passed":
        return "Đã kết thúc · Chưa đạt", ("Xem đề xuất điều chỉnh bên dưới" if state.get("adjustment")
                                         else "Xem vấn đề còn lại bên dưới")
    if status == "stopped":
        return "Đã dừng", "Tạo thiết kế mới hoặc mở lượt khác"
    if status == "error":
        return "Gặp lỗi", "Chạy lại bước lỗi trong Dữ liệu kỹ thuật"
    return "Chưa xác định", "Chưa xác định"


def status_header(run, state: dict) -> None:
    current, upcoming = run_steps(run, state)
    iteration, limit = state.get("iteration"), state.get("max_iterations")
    rounds = f"{iteration}/{limit}" if iteration is not None and limit is not None else "Chưa xác định"
    active = run.status in ("running", "paused", "awaiting_approval", "needs_input")
    status, actions = st.columns([3, 1.3], vertical_alignment="center")
    with status:
        ui.html_block(f'<div class="aa-studio-run" role="status"><span>{ui.icon("clipboard")} Thực thi {ui.run_pill(run.status)}</span>'
                      f'<span>{ui.icon("target")} Bước hiện tại <b>{ui.esc(current)}</b></span>'
                      f'<span>{ui.icon("arrow")} Tiếp theo <b>{ui.esc(upcoming)}</b></span>'
                      f'<span>{ui.icon("repeat")} Vòng sửa <b>{rounds}</b></span></div>')
    if active:
        with actions:
            run_controls(run)
    elif state.get("final_files"):
        actions.page_link("views/results.py", label="Xem kết quả", icon=":material/image:", width="stretch")


def waiting_notice(run) -> None:
    """Thông báo nổi một lần cho mỗi điểm duyệt mới, kể cả khi đang cuộn xem phần dưới của trang."""
    payload = run.interrupt_payload or {}
    ident = f"{run.run_id}:{run.current_node}:{payload.get('title')}"
    if st.session_state.get("studio_waiting_notified") != ident:
        st.session_state["studio_waiting_notified"] = ident
        text = ("Cần bổ sung yêu cầu thiết kế" if run.status == "needs_input"
                else f"Chờ bạn duyệt · {payload.get('title', 'bước hiện tại')}")
        st.toast(text, icon=":material/notifications_active:", duration="long")


def save_mode() -> None:
    st.session_state["studio_mode"] = st.session_state["studio_mode_picker"]


run = current_run()
saved_mode = st.session_state.get("studio_mode", "live")
runs = events.list_runs(50) if saved_mode == "live" else []
has_picker = saved_mode == "live" and bool(runs or run)
name = project_name(run) if run else ""
with st.container(key="page_heading"):
    heading, create = st.columns([3.4, 1.3], vertical_alignment="center")
    with heading:
        ui.page_header("Studio AI", "Điều phối thiết kế, theo dõi agent và duyệt phương án.", live_badge=False)
    if create.button("Tạo thiết kế mới", icon=":material/add:", type="primary", width="stretch"):
        begin_draft()
        st.switch_page("views/projects.py")
    if has_picker:
        project, controls = st.columns([1.65, 1], vertical_alignment="bottom")
        with project:
            run_picker(runs, run, "studio_run", current_name=name, show_current_status=False, label_visibility="visible")
    else:
        controls, _ = st.columns([1, 2])
    with controls:
        choices = {"live": "Dữ liệu thật", "demo": "Mô phỏng"}
        mode = st.radio("Chế độ hiển thị", choices, index=list(choices).index(saved_mode), format_func=choices.get,
                        horizontal=True, key="studio_mode_picker", on_change=save_mode)
polling = mode == "live" and run is not None and run.status == "running"


@st.fragment(run_every=1.0 if polling else None)
def monitor() -> None:
    if polling and run.status != "running":
        st.rerun()

    live_run = run if mode == "live" else None
    state = live_run.state() if live_run else {}
    event_rows = events.get_events(live_run.run_id) if live_run else []
    stats = agent_stats(live_run.run_id, event_rows) if live_run else {}
    if live_run:
        status_header(live_run, state)
        if live_run.status in ("awaiting_approval", "needs_input") and live_run.interrupt_payload:
            waiting_notice(live_run)
            heading = ("Cần bổ sung yêu cầu" if live_run.status == "needs_input" else "Lượt đang chờ phản hồi · Mở tác vụ duyệt")
            with st.expander(heading, expanded=True):
                approval_box(live_run, "studio")
            # Nhắc lại ngay trên văn phòng 3D: khi cuộn xuống xem cảnh, khung duyệt ở trên dễ bị khuất.
            st.warning(f"Lượt đang **dừng chờ bạn duyệt**: {live_run.interrupt_payload.get('title', 'bước hiện tại')}. "
                       "Bấm **Đồng ý & tiếp tục** trong khung duyệt phía trên để agent làm tiếp.",
                       icon=":material/pause_circle:")
        if live_run.status == "error":
            st.error("Lượt thiết kế gặp lỗi xử lý. Xem dữ liệu kỹ thuật để chọn bước chạy lại nếu khả dụng.")
        if live_run.status == "not_passed":
            st.warning("Chưa đạt · đã hết số vòng sửa tự động." if state.get("repair_limit_reached")
                       else "Chưa đạt · còn vấn đề cần xử lý.")
            for issue in state.get("remaining_issues") or []:
                st.write(f"• {issue['noi_dung']}")
            adjustment_panel(live_run, state, "studio")
    action = component.show(office_data(state, event_rows, stats, run_id=live_run.run_id if live_run else None,
                                        status=live_run.status if live_run else "idle",
                                        current=live_run.step()[1] if live_run else None), mode=mode)
    if isinstance(action, dict) and action.get("action") == "performance" and action.get("agent") in AGENT_ORDER:
        nonce = action.get("nonce")
        if isinstance(nonce, str) and nonce != st.session_state.get("studio_performance_nonce"):
            st.session_state["studio_performance_nonce"] = nonce
            st.session_state["performance_request"] = {
                "agent": action["agent"], "run": live_run.run_id if live_run else None,
                "source": "live" if mode == "live" else "simulation",
            }
            st.switch_page("views/tasks.py")
    if live_run:
        show_rounds(state, event_rows)
        show_technical(live_run, state, event_rows)
    elif mode == "live":
        st.info("Chưa có lượt thiết kế. Có thể tạo yêu cầu mới để giao việc cho đội ngũ AI.")


monitor()
