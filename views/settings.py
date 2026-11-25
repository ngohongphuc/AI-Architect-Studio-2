"""Tùy chọn chạy và trạng thái cấu hình cục bộ."""
import os
from datetime import datetime
from math import isfinite

import streamlit as st

import telegram_bot
import ui_theme as ui
from config import AGENT_ORDER, DATA_DIR, PRICE_FILE, RULES_FILE
from graph import APPROVAL_LABELS
from llm import agent_config, configuration_status
from tools.rag import reference_files
from tools.rules import MANIFEST
from tools.docx_writer import vn_num
from ui_common import label, run_preferences

MODES = {
    "auto": ("Tự động", "play_circle", "Chạy luồng theo các kiểm tra của hệ thống."),
    "all": ("Duyệt tất cả các bước", "assignment_turned_in", "Dừng tại các bước cần người dùng duyệt."),
    "custom": ("Chọn bước cần duyệt", "tune", "Chỉ dừng ở những bước bạn chọn."),
}


def approval_mode(points: list[str]) -> str:
    if not points:
        return "auto"
    return "all" if set(points) == set(APPROVAL_LABELS) else "custom"


def show_run_preferences() -> None:
    preferences = run_preferences()
    all_points = list(APPROVAL_LABELS)
    saved_mode = approval_mode(preferences["approval_points"])
    main, summary = st.columns([1.65, 1], gap="medium")
    with main.container(border=True, key="workflow_settings"):
        ui.section("Mặc định cho lượt mới", "Áp dụng cho bản nháp mới trong phiên hiện tại.")
        st.session_state.setdefault("pref_approval_mode", saved_mode)
        st.session_state.setdefault("pref_approval_points", preferences["approval_points"] if saved_mode == "custom"
                                    else ["architect", "reviewer"])
        st.session_state.setdefault("pref_max_iterations", preferences["max_iterations"])
        st.session_state.setdefault("pref_fengshui", preferences["fengshui_enabled"])
        with st.container(key="settings_mode"):
            mode = st.radio("Chế độ duyệt", list(MODES), horizontal=True, key="pref_approval_mode",
                            format_func=lambda value: f":material/{MODES[value][1]}: **{MODES[value][0]}**  \n"
                                                      + MODES[value][2])
        with st.expander("Các bước duyệt tùy chọn", expanded=True):
            st.caption("Chỉ áp dụng trong chế độ Chọn bước cần duyệt." if mode == "custom"
                       else f"Tuỳ chọn đang tắt khi dùng chế độ {MODES[mode][0]}.")
            points = st.multiselect("Bước cần duyệt", all_points, key="pref_approval_points",
                                    format_func=APPROVAL_LABELS.get, disabled=mode != "custom")
        limit_col, fengshui_col = st.columns(2, vertical_alignment="bottom")
        limit = limit_col.number_input("Số vòng sửa tự động tối đa", min_value=0, max_value=3, key="pref_max_iterations")
        fengshui = fengshui_col.toggle("Tư vấn phong thủy", key="pref_fengshui")
        if st.button("Lưu tùy chọn", type="primary", icon=":material/save:"):
            if mode == "custom" and not points:
                st.error("Chọn ít nhất một bước cần duyệt để lưu chế độ này.")
            else:
                st.session_state["run_preferences"] = {
                    "max_iterations": int(limit), "fengshui_enabled": fengshui,
                    "approval_points": [] if mode == "auto" else all_points if mode == "all" else list(points),
                }
                st.success("Đã lưu tùy chọn cho lượt thiết kế mới.")

    effective = run_preferences()
    with summary:
        with st.container(border=True, key="settings_summary"):
            ui.section("Tóm tắt cấu hình")
            ui.html_block("<div>" + "".join((
                ui.fact("Chế độ duyệt", MODES[approval_mode(effective["approval_points"])][0], "clipboard", status=True),
                ui.fact("Vòng sửa tối đa", str(effective["max_iterations"]), "repeat", "warning", status=True),
                ui.fact("Phong thủy", "Đã bật" if effective["fengshui_enabled"] else "Đã tắt", "leaf",
                        "success" if effective["fengshui_enabled"] else "neutral", status=True),
                ui.fact("Phạm vi", "Lượt thiết kế mới", "layers", status=True),
            )) + "</div>")
        with st.container(border=True, key="settings_tip"):
            ui.section("Gợi ý", "Chọn các bước cần duyệt khi bạn muốn xem và phản hồi trước khi giao tiếp.", glyph="idea")


def show_models() -> None:
    with st.container(border=True, key="model_settings"):
        ui.section("Kết nối theo agent",
                   "Model hiện hành của từng agent (trang Quản lý agent, rồi tới .env). Trạng thái dưới đây chỉ kiểm tra cấu hình cục bộ.")
        statuses = []
        for agent in AGENT_ORDER:
            cfg = configuration_status(agent)
            try:
                temperature = agent_config(agent)["temperature"] if cfg["model"] != "—" else None
            except (TypeError, ValueError):
                temperature = None
            statuses.append({"Agent": label(agent), "Nhà cung cấp": cfg["provider"], "Model": cfg["model"],
                             "Temperature": vn_num(temperature, 2) if temperature is not None and isfinite(temperature) else "—",
                             "Trạng thái": cfg["status"]})
        st.dataframe(statuses, hide_index=True, width="stretch")
        st.caption("Khóa API đặt trong .env hoặc biến môi trường ở máy chủ.")
        st.page_link("views/agent_manager.py", label="Đổi model, kiểm tra kết nối, thêm agent", icon=":material/smart_toy:")


def show_references() -> None:
    with st.container(border=True, key="reference_settings"):
        ui.section("Nguồn dữ liệu tại máy", "Danh mục tệp tra cứu và tài liệu tham khảo cấu hình tại máy chủ.")
        search = st.text_input("Tìm tài liệu", icon=":material/search:", placeholder="Tên tệp hoặc nhóm tài liệu")
        sources = {path: ("Quy chuẩn" if path.parent.name == "quy_chuan" else "Phong thủy", "Tài liệu tra cứu")
                   for path in reference_files()}
        manifest = DATA_DIR / "quy_chuan" / MANIFEST
        sources.update({RULES_FILE: ("Quy chuẩn", "Ngưỡng tham khảo"), PRICE_FILE: ("Dự toán", "Đơn giá tham khảo"),
                        manifest: ("Quy chuẩn", "Khai báo căn cứ áp dụng")})
        items = {}
        for path, (group, role) in sources.items():
            if not path.resolve().is_relative_to(DATA_DIR.resolve()) or not path.is_file():
                continue
            if search.strip().casefold() not in f"{path.name} {group} {role}".casefold():
                continue
            try:
                info = path.stat()
            except OSError:
                continue
            items[path] = {"Tệp": path.relative_to(DATA_DIR).as_posix(), "Nhóm": group, "Vai trò": role,
                           "Cập nhật": datetime.fromtimestamp(info.st_mtime).strftime("%d/%m/%Y %H:%M"),
                           "Dung lượng": f"{vn_num(info.st_size / 1024, 1)} KB", "Trạng thái": "Có tệp cục bộ"}
        if items:
            st.dataframe(list(items.values()), hide_index=True, width="stretch")
            choice = st.selectbox("Tài liệu để xem", list(items), index=None, format_func=lambda path: items[path]["Tệp"],
                                  placeholder="Chọn tài liệu")
            if choice:
                try:
                    data = choice.read_bytes()
                except OSError:
                    st.error("Không đọc được tệp tại thời điểm hiện tại.")
                else:
                    if choice.suffix.casefold() in (".md", ".txt", ".json"):
                        limit = 80_000
                        st.code(data[:limit].decode("utf-8-sig", errors="replace"),
                                language="json" if choice.suffix.casefold() == ".json" else "text")
                        if len(data) > limit:
                            st.caption("Đang xem phần đầu tài liệu. Tải tệp để đọc đầy đủ.")
                    st.download_button("Tải tài liệu", data, file_name=choice.name, icon=":material/download:", on_click="ignore")
        else:
            st.info("Không có tài liệu khớp tìm kiếm." if search.strip() else "Chưa tìm thấy tài liệu tham chiếu.")
        if manifest.is_file():
            st.caption(f"Đã tìm thấy `{MANIFEST}`. Phạm vi áp dụng và nguồn được đối chiếu trong tab Kiểm định của từng hồ sơ.")
        else:
            st.caption(f"Chưa tìm thấy `{MANIFEST}` trong thư mục `data/quy_chuan/`.")
        st.caption("Cấu hình tra cứu · " + ("Yêu cầu dùng Chroma" if os.getenv("USE_CHROMA") == "1" else "BM25 cục bộ"))
        st.caption("Tải lên và gỡ tài liệu hiện do quản trị viên thực hiện trong thư mục dữ liệu.")


TELEGRAM_STATES = {"off": ("Chưa bật", "neutral"), "starting": ("Đang kết nối", "info"), "online": ("Đang hoạt động", "success"),
                   "error": ("Gặp lỗi", "danger")}


def _telegram_save() -> None:
    try:
        name = telegram_bot.save_token(st.session_state.get("telegram_token", ""))
    except ValueError as error:
        st.session_state["telegram_flash"] = ("error", str(error))
        return
    st.session_state["telegram_token"] = ""
    st.session_state["telegram_flash"] = ("success", f"Đã kết nối bot @{name}.")


def _telegram_change(action, *args) -> None:
    action(*args)
    st.session_state["telegram_flash"] = ("success", "Đã cập nhật.")


@st.fragment(run_every=3.0)
def telegram_access() -> None:
    info = telegram_bot.status()
    text, tone = TELEGRAM_STATES[info["state"]]
    ui.html_block(ui.pill(text + (f" · @{info['username']}" if info["username"] else ""), tone))
    if info["detail"] and info["state"] == "error":
        st.caption(info["detail"])
    allowed = telegram_bot.allowed_users()
    st.markdown("**Tài khoản được phép**")
    if not allowed:
        st.caption("Chưa có. Mở Telegram, nhắn một tin cho bot từ tài khoản của bạn, rồi bấm Cho phép bên dưới.")
    for user in sorted(allowed):
        name, remove = st.columns([3, 1], vertical_alignment="center")
        name.write(f"Mã {user}")
        remove.button("Gỡ", key=f"telegram_revoke_{user}", width="stretch", on_click=_telegram_change,
                      args=(telegram_bot.revoke, user))
    waiting = {user: name for user, name in info["pending"].items() if user not in allowed}
    if waiting:
        st.markdown("**Đang xin quyền**")
        st.caption("Tên do người nhắn tự đặt. Chỉ cho phép khi bạn chắc đó là tài khoản của mình hoặc người mình tin.")
        for user, name in waiting.items():
            who, allow = st.columns([3, 1], vertical_alignment="center")
            who.text(f"{name} · mã {user}")
            allow.button("Cho phép", key=f"telegram_allow_{user}", type="primary", width="stretch",
                         on_click=_telegram_change, args=(telegram_bot.allow, user))


def show_telegram() -> None:
    if flash := st.session_state.pop("telegram_flash", None):
        getattr(st, flash[0])(flash[1])
    setup, access = st.columns(2, gap="medium")
    with setup.container(border=True, key="telegram_setup"):
        ui.section("Kết nối bot", "Giao việc, duyệt và nhận hồ sơ qua Telegram.")
        st.markdown("1. Trong Telegram, nhắn **@BotFather**, gửi `/newbot` và làm theo hướng dẫn.\n"
                    "2. Dán token BotFather đưa vào ô dưới đây.\n"
                    "3. Nhắn một tin cho bot vừa tạo, rồi bấm **Cho phép** ở khung bên cạnh.")
        st.text_input("Token của bot", type="password", key="telegram_token", autocomplete="off",
                      placeholder="Đã có token" if telegram_bot.token() else "123456789:ABC…")
        save, remove = st.columns(2)
        save.button("Thay token" if telegram_bot.token() else "Kết nối", type="primary", icon=":material/link:", width="stretch",
                    on_click=_telegram_save)
        remove.button("Ngắt kết nối", icon=":material/link_off:", width="stretch", disabled=not telegram_bot.token(),
                      on_click=_telegram_change, args=(telegram_bot.remove_token,))
        st.caption("Token lưu trong .env, không hiện lại. Yêu cầu và hồ sơ gửi qua bot sẽ đi qua máy chủ Telegram. "
                   "Bot chỉ hoạt động khi ứng dụng này đang chạy.")
    with access.container(border=True, key="telegram_access"):
        ui.section("Trạng thái và quyền")
        telegram_access()


with st.container(key="page_heading"):
    ui.page_header("Cấu hình", "Thiết lập quy trình và tùy chọn cho đội ngũ AI.")
run_tab, model_tab, reference_tab, telegram_tab = st.tabs(
    [":material/play_circle: Chế độ chạy", ":material/memory: Model & API", ":material/menu_book: Tài liệu tham chiếu",
     ":material/send: Telegram"], key="settings_tab", on_change="rerun")
with run_tab:
    show_run_preferences()
with model_tab:
    show_models()
with reference_tab:
    show_references()
with telegram_tab:
    show_telegram()
