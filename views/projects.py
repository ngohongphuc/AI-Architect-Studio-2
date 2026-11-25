"""Danh mục dự án và biểu mẫu tạo thiết kế."""
from datetime import datetime
from unicodedata import normalize
from uuid import uuid4

import streamlit as st

import ui_theme as ui
from graph import APPROVAL_LABELS
from main import SAMPLE
from monitoring import events
from monitoring.redaction import error_text
from monitoring.runner import get_graph, load_snapshot, manager
from tools.brief_parser import FIELD_LABELS, explicit_request_fields, inspect_request, project_title
from tools.design_option import option_label
from tools.docx_writer import vn_num, vnd
from ui_common import RUN_STATUS, begin_draft, project_name, run_preferences

EXAMPLES = {
    "Nhà phố 5 × 20 m · Hà Nội": SAMPLE,
    "Nhà nhỏ 4 × 15 m · Đà Nẵng": "Đất 4x15m hướng Tây ở Đà Nẵng, vợ chồng trẻ sinh 1995, cần 2 phòng ngủ, "
                                  "ngân sách 1,8 tỷ, phong cách tối giản.",
    "Nhà 6 × 25 m có gara · TP.HCM": "Lô đất 6x25m hướng Bắc tại TP.HCM, gia đình 6 người có ông bà, chủ nhà sinh năm 1980. "
                                     "Cần 4 phòng ngủ, phòng thờ, phòng làm việc, gara ô tô. Ngân sách 6 tỷ, phong cách hiện đại.",
}
PAGE_SIZE = 5
DRAFT_WIDGET = "intake_"


def catalog_name(row: dict) -> str:
    summary = row["summary"]
    if summary.get("ten_du_an"):
        return summary["ten_du_an"]
    brief, _, _ = inspect_request(row["request"], summary.get("request_fields"))
    return project_title(row["request"], brief)


def search_text(text: str) -> str:
    return "".join(char for char in normalize("NFD", text.casefold().replace("đ", "d"))
                   if not "\u0300" <= char <= "\u036f")


def catalog_state(row: dict) -> dict:
    rid = row["run_id"]
    if row["status"] in ("running", "paused", "awaiting_approval", "needs_input", "stopped", "error"):
        state = get_graph().get_state({"configurable": {"thread_id": rid}}).values
        if state:
            return state
    return load_snapshot(rid, output_dir=row["output_dir"], include_log=False) or (
        get_graph().get_state({"configurable": {"thread_id": rid}}).values or {})


def selected_option(state: dict) -> str:
    program = state.get("program") or {}
    oid = program.get("phuong_an")
    option = next((opt for opt in state.get("options") or [] if opt.get("id") == oid), {})
    if not oid or option.get("eligible") is False or (program.get("option_version") and not option.get("eligible")):
        return "Chưa chốt"
    return option_label(program) or f"Phương án {oid}"


def activity_date(row: dict) -> str:
    try:
        timestamp = datetime.fromisoformat(row["updated"] or row["created"])
    except (TypeError, ValueError):
        return "—"
    suffix = "" if row["updated"] else " · ngày tạo"
    return timestamp.strftime("%d/%m/%Y %H:%M") + suffix


def open_studio(run_id: str) -> None:
    st.session_state["run_id"] = run_id
    st.session_state["studio_mode"] = "live"
    st.session_state["project_form_open"] = False
    st.switch_page("views/studio.py")


def reset_page() -> None:
    st.session_state["projects_page"] = 1


def show_catalog() -> None:
    with st.container(key="page_heading"):
        main, action = st.columns([4, 1.45], vertical_alignment="center")
        with main:
            ui.page_header("Dự án", "Quản lý và tiếp tục các dự án thiết kế.")
        with action:
            st.button("Tạo thiết kế mới", icon=":material/add:", type="primary",
                      width="stretch", on_click=begin_draft)

    rows = events.list_runs(None, recent_activity=True)
    active = sum(row["status"] in ("running", "paused", "awaiting_approval", "needs_input") for row in rows)
    done = sum(row["status"] == "done" for row in rows)
    ui.kpi_grid([ui.kpi("Tổng dự án", len(rows), "layers"),
                 ui.kpi("Đang thực hiện", active, "target", "warning"),
                 ui.kpi("Đã hoàn thành", done, "check", "success")])
    if not rows:
        with st.container(border=True, key="project_empty"):
            ui.section("Chưa có dự án", "Tạo thiết kế mới để lưu yêu cầu và theo dõi tiến độ trong Studio AI.", glyph="house")
        return

    latest = rows[0]
    name = catalog_name(latest)
    state = catalog_state(latest)
    with st.container(border=True, key="project_resume"):
        art, detail, action = st.columns([1.35, 2.2, 1], vertical_alignment="center")
        with art:
            ui.html_block(f'<figure class="aa-project-art">{ui.house_art()}'
                          '<figcaption>Minh họa kiến trúc</figcaption></figure>')
        with detail:
            ui.section("Tiếp tục dự án gần nhất")
            ui.html_block(f'<strong class="aa-resume-name">{ui.esc(name)}</strong>')
            ui.html_block(f'<div class="aa-project-meta">{ui.run_pill(latest["status"])}'
                          f'<span>{ui.icon("layers")} {ui.esc(selected_option(state))}</span>'
                          f'<span>{ui.icon("calendar")} {ui.esc(activity_date(latest))}</span></div>')
        with action:
            if st.button("Tiếp tục dự án", icon=":material/play_arrow:", width="stretch",
                         key=f"continue_{latest['run_id']}"):
                open_studio(latest["run_id"])

    heading, search, filter_column = st.columns([1.55, 1.3, 1], vertical_alignment="center")
    with heading:
        ui.section("Danh sách dự án")
    query = search.text_input("Tìm kiếm dự án", placeholder="Tìm kiếm dự án…", label_visibility="collapsed",
                              key="project_search", on_change=reset_page, icon=":material/search:")
    states = list(dict.fromkeys(row["status"] for row in rows))
    if st.session_state.get("project_status", "") not in ["", *states]:
        st.session_state["project_status"] = ""
        reset_page()
    status = filter_column.selectbox("Lọc trạng thái", ["", *states], label_visibility="collapsed", key="project_status",
                                     on_change=reset_page, format_func=lambda item: RUN_STATUS.get(item, item)
                                     if item else "Tất cả trạng thái")
    words = search_text(query.strip()).split()
    matches = []
    for row in rows:
        title = name if row is latest else catalog_name(row)
        haystack = search_text(f"{title} {row['request']} {row['run_id']}")
        if (not status or row["status"] == status) and all(word in haystack for word in words):
            matches.append((row, title))
    if not matches:
        st.info("Không tìm thấy dự án phù hợp.")
        return
    total = len(matches)
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if not 1 <= st.session_state.get("projects_page", 1) <= pages:
        reset_page()
    page = st.session_state.get("projects_page", 1)
    first = (page - 1) * PAGE_SIZE
    ratios = [2.4, 1.17, 1.18, 1.22, .72]
    with st.container(border=True, key="project_list"):
        with st.container(key="project_table_header"):
            for column, heading in zip(st.columns(ratios), ("Tên dự án", "Cập nhật", "Trạng thái", "Phương án", "Thao tác"), strict=True):
                column.html(ui.esc(heading))
        for row, title in matches[first:first + PAGE_SIZE]:
            with st.container(key=f"project_row_{row['run_id']}"):
                cells = st.columns(ratios, vertical_alignment="center")
                values = (f'{ui.emblem("house")} <span class="aa-project-row-title">{ui.esc(title)}</span>',
                          f'{ui.icon("calendar")} <span>{ui.esc(activity_date(row))}</span>',
                          ui.run_pill(row["status"]),
                          f'{ui.icon("layers")} <span>{ui.esc(selected_option(state if row is latest else catalog_state(row)))}</span>')
                for column, value in zip(cells[:4], values, strict=True):
                    column.html(f'<div class="aa-project-cell">{value}</div>')
                if cells[4].button("Mở", key=f"open_{row['run_id']}", icon=":material/chevron_right:",
                                   help=f"Mở {title}", width="stretch"):
                    open_studio(row["run_id"])
        count, pagination = st.columns([2.25, 1], vertical_alignment="center")
        count.caption(f"Hiển thị {first + 1}–{min(first + PAGE_SIZE, total)} trong {total} dự án phù hợp")
        if pages > 1:
            with pagination.container(key="project_pagination"):
                previous, indicator, following = st.columns([1, 1.4, 1], vertical_alignment="center")
                if previous.button("Trước", icon=":material/chevron_left:", disabled=page == 1, width="stretch"):
                    st.session_state["projects_page"] = page - 1
                    st.rerun()
                indicator.html(f'<div class="aa-project-page" aria-live="polite">Trang {page} / {pages}</div>')
                if following.button("Sau", icon=":material/chevron_right:", disabled=page == pages, width="stretch"):
                    st.session_state["projects_page"] = page + 1
                    st.rerun()


def save_widget(name: str, key: str) -> None:
    st.session_state["project_draft_values"][name] = st.session_state[key]


def draft_widget(widget, name: str, label: str, default=None, **kwargs):
    key = DRAFT_WIDGET + name
    if key not in st.session_state:
        st.session_state[key] = st.session_state["project_draft_values"].get(name, default)
    return widget(label, key=key, on_change=save_widget, args=(name, key), **kwargs)


def load_example() -> None:
    example = EXAMPLES.get(st.session_state["project_example"])
    if example:
        st.session_state["project_draft_values"]["request"] = example
        st.session_state[DRAFT_WIDGET + "request"] = example


def request_fields(request: str) -> dict:
    found = explicit_request_fields(request)
    fields = {}
    with st.expander("Thông tin có cấu trúc"):
        st.caption("Các ô trống lấy dữ liệu nhận diện từ mô tả. Nếu hai nguồn khác nhau, hãy chỉnh lại trước khi gửi.")
        groups = [
            ("Khu đất", [("rong", "Chiều rộng mặt tiền (m)", 0.01, None, 0.1),
                         ("dai", "Chiều sâu lô đất (m)", 0.01, None, 0.1)]),
            ("Nhu cầu sử dụng và ngân sách", [("so_tang", "Số tầng", 1, 5, 1), ("so_nguoi", "Số người", 1, None, 1),
                                              ("phong_ngu", "Số phòng ngủ", 1, 12, 1),
                                              ("ngan_sach", "Ngân sách (triệu đồng)", 0.01, None, 10.0)]),
        ]
        for heading, widgets in groups:
            st.markdown(f"**{heading}**")
            if heading == "Khu đất":
                locations = found["tinh"]
                location = draft_widget(st.text_input, "tinh", "Địa điểm", default="",
                                        placeholder=f"Từ mô tả · {locations[0]}" if len(locations) == 1 else "Tỉnh hoặc thành phố")
                if location.strip():
                    fields["tinh"] = location.strip()
                parcels = found["ma_lo_dat"]
                parcel = draft_widget(st.text_input, "ma_lo_dat", "Mã lô đất", default="",
                                      placeholder=f"Từ mô tả · {parcels[0]}" if len(parcels) == 1 else "Theo hồ sơ lô đất")
                if parcel.strip():
                    fields["ma_lo_dat"] = parcel.strip()
            columns = st.columns(2)
            for index, (name, label, minimum, maximum, step) in enumerate(widgets):
                detected = found[name]
                initial = detected[0] if len(detected) == 1 else None
                if name == "ngan_sach" and initial is not None:
                    initial /= 1_000_000
                placeholder = f"Từ mô tả · {initial:g}" if initial is not None else "Để trống"
                value = draft_widget(columns[index % 2].number_input, name, label, value=None, min_value=minimum,
                                     max_value=maximum, step=step, placeholder=placeholder)
                if value is not None:
                    fields[name] = round(value * 1_000_000) if name == "ngan_sach" else value
    return fields


def design_preferences() -> dict:
    preferences = run_preferences()
    all_points = list(APPROVAL_LABELS)
    saved = preferences["approval_points"]
    with st.expander("Tùy chọn nâng cao"):
        fengshui = draft_widget(st.toggle, "fengshui_enabled", "Tư vấn phong thủy", preferences["fengshui_enabled"])
        mode = draft_widget(st.radio, "approval_mode", "Duyệt thủ công",
                            "Tự động" if not saved else "Tất cả các bước" if saved == all_points else "Chọn bước",
                            options=["Tự động", "Tất cả các bước", "Chọn bước"], horizontal=True)
        points = all_points if mode == "Tất cả các bước" else []
        if mode == "Chọn bước":
            points = draft_widget(st.multiselect, "approval_points", "Các bước cần duyệt",
                                  saved if saved and saved != all_points else ["architect", "reviewer"],
                                  options=all_points, format_func=APPROVAL_LABELS.get)
        limit = draft_widget(st.number_input, "max_iterations", "Số vòng sửa tối đa", preferences["max_iterations"],
                             min_value=0, max_value=3, step=1)
    return {"max_iterations": limit, "approval_points": points, "fengshui_enabled": fengshui}


def show_brief(brief: dict) -> None:
    lot, families, rooms = brief["lo_dat"], brief["gia_dinh"], brief["yeu_cau_phong"]
    summary = [
        ("Lô đất", f"{vn_num(lot['rong'], 2)} × {vn_num(lot['dai'], 2)} m"),
        (FIELD_LABELS["tinh"], lot["tinh"]),
        (FIELD_LABELS["so_tang"], str(rooms["so_tang"] or "Đề xuất sau")),
        (FIELD_LABELS["so_nguoi"], str(families["so_nguoi"])),
        (FIELD_LABELS["phong_ngu"], str(rooms["phong_ngu"])),
        (FIELD_LABELS["ngan_sach"], vnd(brief["ngan_sach"])),
    ]
    if lot.get("ma_lo_dat"):
        summary.insert(2, (FIELD_LABELS["ma_lo_dat"], lot["ma_lo_dat"]))
    other = [label for key, label in (("phong_tho", "Phòng thờ"), ("phong_lam_viec", "Phòng làm việc"),
                                     ("gara", "Gara")) if rooms[key]]
    if other:
        summary.append(("Công năng bổ sung", ", ".join(other)))
    ui.html_block(ui.kv([(label, ui.esc(value)) for label, value in summary]))
    assumptions = brief["gia_dinh_bo_sung"]
    if assumptions:
        st.markdown("**Giả định ban đầu**")
        notes = "".join(f"<li>{ui.esc(note)}</li>" for note in assumptions)
        ui.html_block(f'<ul class="aa-brief-assumptions">{notes}</ul>')


def show_intake() -> None:
    run_id = st.session_state.get("project_submitted")
    run = manager.get(run_id) if run_id else None
    with st.container(key="page_heading"):
        main, action = st.columns([3, 1], vertical_alignment="center")
        with main:
            ui.page_header("Tạo thiết kế mới", "Kiểm tra yêu cầu và các giả định trước khi giao việc.",
                           project=project_name(run) if run else "")
        with action:
            if st.button("Về danh sách dự án", icon=":material/arrow_back:", type="tertiary"):
                st.session_state["project_form_open"] = False
                st.rerun()
    if run_id:
        st.success("Đã tạo lượt thiết kế.")
        if st.button("Mở Studio AI", icon=":material/arrow_forward:", type="primary"):
            open_studio(run_id)
        return

    form, preview = st.columns([1.55, 1], gap="large")
    with form.container(border=True, key="project_brief"):
        ui.section("Yêu cầu thiết kế", "Ghi nhu cầu phòng, phong cách, hướng nhà hoặc lưu ý riêng.", glyph="clipboard")
        request = draft_widget(st.text_area, "request", "Mô tả yêu cầu bằng tiếng Việt", default="", height=155,
                               placeholder="Ví dụ: Đất 5 × 20 m tại Hà Nội, cần 3 phòng ngủ, ngân sách 2,5 tỷ.")
        with st.expander("Dùng yêu cầu mẫu"):
            st.selectbox("Yêu cầu mẫu", EXAMPLES, index=None, placeholder="Chọn mẫu để điền mô tả",
                         disabled=bool(request.strip()), key="project_example", on_change=load_example)
        fields = request_fields(request)
        preferences = design_preferences()
    brief, questions, conflicts = inspect_request(request, fields)
    with preview.container(border=True, key="project_defaults"):
        ui.section("Tóm tắt yêu cầu", glyph="check")
        for conflict in conflicts:
            st.error(conflict)
        if questions:
            st.warning("\n".join(f"- {question}" for question in questions))
        if brief is not None:
            show_brief(brief)
        if st.button("Bắt đầu thiết kế", icon=":material/arrow_forward:", type="primary",
                     width="stretch", disabled=brief is None):
            submission_id = st.session_state["project_submission_id"]
            try:
                with st.spinner("Đang giao yêu cầu cho Studio AI…"):
                    run = manager.start(request.strip(), request_fields=fields, submission_id=submission_id, **preferences)
            except Exception as exc:
                st.error("Chưa tạo được lượt thiết kế. Bản nháp vẫn có thể chỉnh và gửi lại.")
                st.caption(error_text(exc))
                return
            st.session_state["project_submitted"] = run.run_id
            st.session_state["run_id"] = run.run_id
            st.rerun()


st.session_state.setdefault("project_draft_values", {"request": st.session_state.get("project_draft", "")})
st.session_state.setdefault("project_submission_id", uuid4().hex)
if st.session_state.get("project_form_open"):
    show_intake()
else:
    show_catalog()
