"""Quản lý agent: đổi model theo agent, kiểm tra kết nối, thêm agent LLM tùy biến."""

import streamlit as st

import agent_settings as settings
import api_keys
import ui_theme as ui
from agents.custom_agent import run_one
from llm import PROVIDERS, agent_config, configuration_status, env_config, test_connection
from monitoring import events
from tools.docx_writer import vn_num
from ui_common import label

MODEL_HINTS = {
    "openai": ["gpt-6-luna", "gpt-6.1-terra", "gpt-6.1-sol"],
    "anthropic": ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro"],
    "ollama": ["qwen2.5:7b", "llama3.1:8b"],
}
PROVIDER_NAMES = {"openai": "OpenAI", "anthropic": "Anthropic", "gemini": "Google Gemini", "ollama": "Ollama (máy cục bộ)",
                  "none": "Không dùng LLM (quy tắc)"}
PROMPT_EXAMPLE = ("Ví dụ: Rà soát mặt bằng theo góc nhìn kết cấu nhà phố: nhịp phòng lớn, vị trí cầu thang, "
                  "giếng trời và tải tầng mái. Nêu tối đa 5 rủi ro, mỗi rủi ro kèm một kiến nghị cụ thể.")


def flash(kind: str, text: str) -> None:
    st.session_state["agents_flash"] = (kind, text)


def show_flash() -> None:
    if item := st.session_state.pop("agents_flash", None):
        getattr(st, item[0])(item[1])


def remember_test(provider: str, model: str, result: dict) -> None:
    st.session_state.setdefault("agents_tests", {})[(provider, model)] = result


def test_text(provider: str, model: str) -> str | None:
    result = st.session_state.get("agents_tests", {}).get((provider, model))
    if result is None:
        return None
    return f"Kết nối OK · {vn_num(result['latency_s'], 2)} s" if result["ok"] else f"Lỗi · {result['message']}"


def show_test(result: dict) -> None:
    if result["ok"]:
        st.success(f"Kết nối thành công sau {vn_num(result['latency_s'], 2)} giây. {result['message']}",
                   icon=":material/check_circle:")
    else:
        st.error(result["message"], icon=":material/error:")


def model_fields(prefix: str, saved: dict, inherit: dict, inherit_name: str) -> dict:
    """Ô chọn nhà cung cấp và model. Giá trị rỗng = theo `inherit` (cấu hình .env)."""
    st.session_state.setdefault(f"{prefix}_provider", saved.get("provider") or "")
    providers = ["", *PROVIDERS, "none"]
    left, right = st.columns(2)
    provider = left.selectbox(
        "Nhà cung cấp", providers, key=f"{prefix}_provider",
        format_func=lambda v: f"Theo {inherit_name} ({PROVIDER_NAMES.get(inherit['provider'], inherit['provider'])})"
        if not v else PROVIDER_NAMES.get(v, v))
    effective = provider or inherit["provider"]
    same = effective == inherit["provider"]
    default_model = inherit["model"] if same else PROVIDERS.get(effective, (None, None, None, ""))[3]
    hints = [m for m in MODEL_HINTS.get(effective, []) if m != default_model]
    model_key = f"{prefix}_model_{effective}"
    st.session_state.setdefault(model_key, saved.get("model") if saved.get("model") and (
        saved.get("provider") or "") == provider else "")
    model = right.selectbox(
        "Model", ["", *hints, *([st.session_state[model_key]] if st.session_state[model_key] not in ("", *hints) else [])],
        key=model_key, accept_new_options=True, disabled=effective == "none",
        format_func=lambda v: f"Mặc định ({default_model or '—'})" if not v else v,
        help="Chọn trong danh sách hoặc gõ tên model khác rồi nhấn Enter.")
    value = {"provider": provider, "model": (model or "").strip() if effective != "none" else ""}
    final_model = value["model"] or default_model
    value["effective"] = {"provider": effective, "model": final_model,
                          "temperature": inherit["temperature"] if same else None if effective == "openai" else 0.3}
    st.caption(f"Sẽ dùng: **{PROVIDER_NAMES.get(effective, effective)}**"
               + ("" if effective == "none" else f" · `{final_model}`"))
    return value


# ---------------------------------------------------------------- tab kết nối nhanh
QUICK_PROVIDERS = ("gemini", "openai", "anthropic", "ollama")
KEY_LINKS = {"gemini": "https://aistudio.google.com/apikey", "openai": "https://platform.openai.com/api-keys",
             "anthropic": "https://console.anthropic.com/settings/keys"}
KEY_PLACEHOLDER = {"gemini": "AIza…", "openai": "sk-…", "anthropic": "sk-ant-…"}


def save_key(provider: str) -> None:
    field = f"agents_key_{provider}"
    try:
        api_keys.set_key(provider, st.session_state.get(field, ""))
    except ValueError as error:
        flash("error", str(error))
        return
    st.session_state[field] = ""   # xóa ô nhập, khóa không còn nằm trên giao diện
    flash("success", f"Đã lưu {api_keys.key_env(provider)} vào .env và dùng được ngay.")


def drop_key(provider: str) -> None:
    source = api_keys.status(provider)["source"]
    api_keys.remove_key(provider)
    flash("success" if source == ".env" else "warning",
          f"Đã gỡ {api_keys.key_env(provider)}." if source == ".env" else
          f"Đã gỡ {api_keys.key_env(provider)} khỏi phiên hiện tại. Khóa đặt ở biến môi trường hệ thống sẽ quay lại "
          "khi khởi động lại – hãy xóa nó ở nơi đã khai báo.")


def show_quick() -> None:
    provider = st.radio("Nhà cung cấp", QUICK_PROVIDERS, horizontal=True, key="agents_q_provider",
                        format_func=lambda v: PROVIDER_NAMES[v])
    key_box, model_box = st.columns(2, gap="medium")
    with key_box.container(border=True, key="agents_quick_key"):
        ui.section("1. Khóa API", glyph="shield")
        info = api_keys.status(provider)
        if not info["env"]:
            st.caption("Ollama chạy trên máy của bạn nên không cần khóa. Cần cài và mở Ollama trước.")
        else:
            ui.html_block(ui.pill(f"Đã có khóa {info['hint']} · {info['source']}", "success") if info["set"]
                          else ui.pill(f"Chưa có {info['env']}", "warning"))
            st.text_input(f"Dán {info['env']}", type="password", key=f"agents_key_{provider}",
                          placeholder=KEY_PLACEHOLDER.get(provider, ""), autocomplete="off")
            save, remove, _ = st.columns([1.1, 1, 1.4])
            save.button("Thay khóa" if info["set"] else "Lưu khóa", type="primary", icon=":material/key:",
                        width="stretch", on_click=save_key, args=(provider,), key=f"agents_key_save_{provider}")
            remove.button("Gỡ khóa", icon=":material/key_off:", width="stretch", disabled=not info["set"],
                          on_click=drop_key, args=(provider,), key=f"agents_key_drop_{provider}")
            if provider in KEY_LINKS:
                st.caption(f"Lấy khóa tại [{KEY_LINKS[provider].split('//')[1]}]({KEY_LINKS[provider]}). "
                           "Khóa lưu vào tệp .env của dự án (không đưa lên git), giao diện chỉ hiện 4 ký tự cuối.")

    with model_box.container(border=True, key="agents_quick_model"):
        ui.section("2. Model cho tất cả agent", glyph="layers")
        in_use = {(agent_config(a)["provider"], agent_config(a)["model"]) for a in settings.LLM_AGENTS}
        st.caption("Đang dùng: " + "; ".join(f"{PROVIDER_NAMES.get(p, p)} · {m}" if p != "none" else PROVIDER_NAMES["none"]
                                            for p, m in sorted(in_use)))
        listed = st.session_state.get(f"agents_q_list_{provider}")
        default = PROVIDERS[provider][3]
        current = next((m for p, m in in_use if p == provider), default)
        typed = st.session_state.get(f"agents_q_model_{provider}")   # model gõ tay vẫn giữ khi danh sách đổi
        options = [m for m in dict.fromkeys([typed, current, default, *(listed or MODEL_HINTS.get(provider, []))]) if m]
        model = st.selectbox("Model", options, key=f"agents_q_model_{provider}", accept_new_options=True,
                             help="Chọn trong danh sách hoặc gõ tên model khác rồi nhấn Enter.")
        if provider in ("gemini", "openai") and st.button("Tải danh sách model từ tài khoản",
                                                          icon=":material/cloud_download:", key=f"agents_q_fetch_{provider}"):
            try:
                with st.spinner("Đang tải danh sách model…"):
                    st.session_state[f"agents_q_list_{provider}"] = api_keys.list_models(provider)
            except ValueError as error:
                st.error(str(error))
            else:
                st.rerun()
        if listed:
            st.caption(f"Đã tải {len(listed)} model khả dụng với khóa hiện tại.")
        test, apply, _ = st.columns([1, 1.6, .4])
        if test.button("Kiểm tra", icon=":material/network_check:", width="stretch", key="agents_q_test"):
            with st.spinner("Đang kiểm tra…"):
                result = test_connection(provider, model)
            remember_test(provider, model, result)
            show_test(result)
        if apply.button("Áp dụng cho 6 agent LLM", type="primary", icon=":material/done_all:", width="stretch",
                        key="agents_q_apply"):
            try:
                for agent in settings.LLM_AGENTS:
                    settings.set_model(agent, provider, model or "")
            except ValueError as error:
                st.error(str(error))
            else:
                for key in [k for k in st.session_state if k.startswith("agents_m_")]:
                    del st.session_state[key]
                flash("success", f"6 agent LLM đã chuyển sang {PROVIDER_NAMES[provider]} · {model or default}. "
                                 "Áp dụng cho lượt thiết kế mới. Muốn chỉnh riêng từng agent, dùng tab Agent lõi.")
                st.rerun()


# ---------------------------------------------------------------- tab agent lõi
CORE_ROLES = {
    "project_manager": "Điều phối luồng, vòng sửa, tổng hợp hồ sơ",
    "requirements_analyst": "Chuẩn hóa yêu cầu của chủ nhà",
    "concept_architect": "Đề xuất ý tưởng, quy mô, phong cách",
    "architect": "Lập phương án công năng các phòng",
    "drafter": "Xếp mặt bằng, xuất bản vẽ",
    "fengshui_advisor": "Gợi ý phong thủy (tùy chọn)",
    "reviewer": "Kiểm tra quy chuẩn xây dựng",
    "cost_estimator": "Lập dự toán, so sánh ngân sách",
    "final_reviewer": "Đối chiếu hồ sơ trước khi xuất",
}
PROVIDER_SHORT = {"openai": "OpenAI", "anthropic": "Anthropic", "gemini": "Gemini", "ollama": "Ollama"}


def short_status(agent: str, cfg: dict) -> str:
    """Trạng thái ngắn cho bảng; chi tiết lỗi hiện ở khung kiểm tra kết nối."""
    tested = st.session_state.get("agents_tests", {}).get((cfg["provider"], cfg["model"]))
    if tested:
        return f"✅ Kết nối OK · {vn_num(tested['latency_s'], 1)} s" if tested["ok"] else "❌ Lỗi kết nối"
    text = configuration_status(agent)["status"]
    if text == "Không dùng API":
        return "Chế độ quy tắc"
    if text.startswith("Thiếu"):
        return f"⚠️ {text}"
    return "Sẵn sàng · chưa kiểm tra" if "chưa thử" in text else text


def show_models() -> None:
    data = settings.load()
    with st.container(border=True, key="agents_model_table"):
        head, action = st.columns([3, 1], vertical_alignment="bottom")
        with head:
            ui.section("9 agent lõi",
                       "Ưu tiên: cấu hình trên trang này → biến riêng của agent trong .env → biến chung trong .env. "
                       "Lượt thiết kế mới dùng cấu hình mới; lượt đang có giữ cấu hình lúc bắt đầu.")
        if action.button("Kiểm tra tất cả", icon=":material/network_check:", width="stretch"):
            targets = {}
            for agent in settings.LLM_AGENTS:
                cfg = agent_config(agent)
                if cfg["provider"] != "none":
                    targets[(cfg["provider"], cfg["model"])] = cfg["temperature"]
            if not targets:
                st.info("Mọi agent đang chạy chế độ quy tắc, không có model nào để kiểm tra.")
            with st.spinner("Đang gửi câu kiểm tra tới từng model…"):
                for (provider, model), temperature in targets.items():
                    remember_test(provider, model, test_connection(provider, model, temperature))
        rows = []
        for agent in settings.CORE_AGENTS:
            row = {"Agent": f"🔒 {label(agent)}", "Vai trò": CORE_ROLES.get(agent, "")}
            if agent not in settings.LLM_AGENTS:
                rows.append({**row, "Model": "Thuật toán Python", "Trạng thái": "Không dùng LLM"})
                continue
            cfg = agent_config(agent)
            model = (PROVIDER_NAMES["none"] if cfg["provider"] == "none"
                     else f"{PROVIDER_SHORT.get(cfg['provider'], cfg['provider'])} · {configuration_status(agent)['model']}")
            rows.append({**row, "Model": model, "Trạng thái": short_status(agent, cfg)})
        st.dataframe(rows, hide_index=True, width="stretch",
                     column_config={"Agent": st.column_config.TextColumn(width="medium"),
                                    "Vai trò": st.column_config.TextColumn(width="large")})
        st.caption("9 agent lõi được định nghĩa trong code: không thêm, xóa, tắt hay sửa tên, vai trò, prompt và vị trí "
                   "trong luồng trên giao diện. Chỉ đổi được model của 6 agent có gọi LLM. "
                   "Nhập khóa API ở tab Kết nối nhanh.")

    with st.container(border=True, key="agents_model_editor"):
        ui.section("Đổi model cho agent lõi", "Chỉ áp dụng cho agent có gọi LLM.")
        agent = st.selectbox("Agent", settings.LLM_AGENTS, format_func=label, key="agents_model_agent")
        saved = data["models"].get(agent, {})
        value = model_fields(f"agents_m_{agent}", saved, env_config(agent), ".env")
        save, test, reset, _ = st.columns([1, 1.2, 1.3, 2])
        if save.button("Lưu", type="primary", icon=":material/save:", width="stretch", key="agents_model_save"):
            try:
                settings.set_model(agent, value["provider"], value["model"])
            except ValueError as error:
                st.error(str(error))
            else:
                flash("success", f"Đã lưu model cho {label(agent)}.")
                st.rerun()
        if test.button("Kiểm tra kết nối", icon=":material/network_check:", width="stretch", key="agents_model_test"):
            eff = value["effective"]
            with st.spinner("Đang kiểm tra…"):
                result = test_connection(eff["provider"], eff["model"], eff["temperature"])
            remember_test(eff["provider"], eff["model"], result)
            show_test(result)
        if reset.button("Dùng cấu hình .env", icon=":material/restart_alt:", width="stretch", key="agents_model_reset",
                        disabled=agent not in data["models"]):
            settings.clear_model(agent)
            for key in [k for k in st.session_state if k.startswith(f"agents_m_{agent}_")]:
                del st.session_state[key]
            flash("success", f"{label(agent)} quay về cấu hình trong .env.")
            st.rerun()


# ---------------------------------------------------------------- tab agent tùy biến
def clear_form() -> None:
    for key in [k for k in st.session_state if k.startswith("agents_c_")]:
        del st.session_state[key]
    st.session_state.pop("agents_editing", None)


def custom_form(existing: dict | None) -> None:
    editing = existing is not None
    spec = existing or {}
    ui.section("Sửa agent" if editing else "Thêm agent tùy biến",
               "Agent tùy biến đọc dữ liệu hồ sơ đã chọn, gọi LLM theo nhiệm vụ bạn mô tả và ghi nhận xét. "
               "Nó không thay đổi số liệu hay nhánh đi của các agent lõi.")
    for key, default in (("name", spec.get("name", "")), ("role", spec.get("role", "")),
                         ("prompt", spec.get("prompt", "")), ("after", spec.get("after", "drafter")),
                         ("inputs", spec.get("inputs", ["brief", "area_table"])), ("enabled", spec.get("enabled", True))):
        st.session_state.setdefault(f"agents_c_{key}", default)
    name_col, after_col = st.columns(2)
    name = name_col.text_input("Tên agent", key="agents_c_name", max_chars=60, placeholder="Kỹ sư kết cấu")
    after = after_col.selectbox("Chạy sau bước", settings.CUSTOM_STAGES, key="agents_c_after",
                                format_func=settings.STAGE_LABELS.get,
                                help="Agent chạy khi luồng đi tiếp từ bước này (sau điểm duyệt nếu có).")
    role = st.text_input("Vai trò (một câu)", key="agents_c_role", max_chars=200,
                         placeholder="Kỹ sư kết cấu nhà phố, 10 năm kinh nghiệm")
    options = settings.available_inputs(after)
    st.session_state["agents_c_inputs"] = [k for k in st.session_state["agents_c_inputs"] if k in options]
    inputs = st.multiselect("Dữ liệu được đọc", options, key="agents_c_inputs",
                            format_func=lambda k: settings.INPUT_KEYS[k][0],
                            help="Chỉ hiện dữ liệu đã có tại bước được chọn. Dữ liệu dài được cắt bớt trước khi gửi.")
    prompt = st.text_area("Nhiệm vụ (prompt)", key="agents_c_prompt", height=150, max_chars=4000,
                          placeholder=PROMPT_EXAMPLE)
    with st.expander("Model của agent", expanded=bool(spec.get("provider") or spec.get("model"))):
        model = model_fields("agents_c_model", spec, env_config(None), ".env chung")
    enabled = st.toggle("Bật agent", key="agents_c_enabled")
    save, cancel, _ = st.columns([1.2, 1, 3])
    if save.button("Lưu thay đổi" if editing else "Tạo agent", type="primary", icon=":material/save:", width="stretch"):
        item = {"id": spec.get("id"), "name": name, "role": role, "prompt": prompt, "after": after, "inputs": inputs,
                "enabled": enabled, "provider": model["provider"], "model": model["model"]}
        try:
            saved = settings.upsert_custom(item)
        except ValueError as error:
            st.error(str(error))
        else:
            clear_form()
            flash("success", f"Đã {'cập nhật' if editing else 'tạo'} agent “{saved['name']}”. Áp dụng cho lượt thiết kế mới.")
            st.rerun()
    if editing and cancel.button("Hủy", width="stretch"):
        clear_form()
        st.rerun()


def preview(spec: dict) -> None:
    runs = {r["run_id"]: r for r in events.list_runs(30) if r.get("output_dir")}
    if not runs:
        st.info("Chưa có lượt thiết kế nào để chạy thử.")
        return
    run_id = st.selectbox("Lượt thiết kế để chạy thử", list(runs), key=f"agents_pv_run_{spec['id']}",
                          format_func=lambda r: f"{(runs[r]['created'] or '')[:16]} · {(runs[r]['request'] or '')[:60]}")
    choice = runs[run_id]
    st.caption("Chạy thử gọi model thật và tốn token, kết quả chỉ hiển thị ở đây, không ghi vào lượt thiết kế.")
    if st.button("Chạy thử", icon=":material/play_arrow:", key=f"agents_pv_go_{spec['id']}"):
        from monitoring.runner import load_snapshot

        state = load_snapshot(choice["run_id"], output_dir=choice["output_dir"], include_log=False)
        if not state:
            st.warning("Lượt này chưa lưu dữ liệu hồ sơ (state.json). Chọn lượt đã hoàn tất.")
            return
        missing = [settings.INPUT_KEYS[k][0] for k in spec["inputs"] if state.get(k) is None]
        if missing:
            st.caption("Lượt này thiếu: " + ", ".join(missing))
        with st.spinner(f"{spec['name']} đang xử lý…"):
            note = run_one(spec, state)
        (st.write if note["status"] == "done" else st.info)(note["text"])
        st.caption(f"Model: {note['model']}")


def custom_card(spec: dict) -> None:
    cfg = agent_config(spec["id"])
    with st.container(border=True, key=f"agents_card_{spec['id']}"):
        title, state = st.columns([4, 1], vertical_alignment="center")
        title.markdown(f"**{spec['name']}**" + (f"  \n{spec['role']}" if spec.get("role") else ""))
        with state:
            ui.html_block(ui.pill("Đang bật", "success") if spec["enabled"] else ui.pill("Đã tắt", "neutral"))
        model = "Không dùng LLM" if cfg["provider"] == "none" else f"{PROVIDER_NAMES.get(cfg['provider'], cfg['provider'])} · {cfg['model']}"
        st.caption(f"Sau bước **{settings.STAGE_LABELS[spec['after']]}** · Model: {model}"
                   + (" (theo .env chung)" if cfg.get("source") == "env" else "")
                   + " · Đọc: " + (", ".join(settings.INPUT_KEYS[k][0] for k in spec["inputs"]) or "không có"))
        toggle, edit, test, remove = st.columns(4)
        if toggle.button("Tắt" if spec["enabled"] else "Bật", key=f"agents_tg_{spec['id']}", width="stretch",
                         icon=":material/toggle_off:" if spec["enabled"] else ":material/toggle_on:"):
            settings.upsert_custom({**spec, "enabled": not spec["enabled"]})
            st.rerun()
        if edit.button("Sửa", key=f"agents_ed_{spec['id']}", width="stretch", icon=":material/edit:"):
            clear_form()
            st.session_state["agents_editing"] = spec["id"]
            st.rerun()
        if test.button("Kiểm tra kết nối", key=f"agents_ts_{spec['id']}", width="stretch",
                       icon=":material/network_check:"):
            with st.spinner("Đang kiểm tra…"):
                show_test(test_connection(cfg["provider"], cfg["model"], cfg["temperature"]))
        with remove.popover("Xóa", icon=":material/delete:", width="stretch"):
            st.write(f"Xóa agent “{spec['name']}”? Lượt đã chạy vẫn giữ nhận xét cũ.")
            if st.button("Xác nhận xóa", type="primary", key=f"agents_rm_{spec['id']}"):
                settings.delete_custom(spec["id"])
                if st.session_state.get("agents_editing") == spec["id"]:
                    clear_form()
                flash("success", f"Đã xóa agent “{spec['name']}”.")
                st.rerun()
        with st.expander("Chạy thử với một lượt đã có"):
            preview(spec)


def show_custom_agents() -> None:
    agents = settings.load()["custom_agents"]
    editing = next((a for a in agents if a["id"] == st.session_state.get("agents_editing")), None)
    if st.session_state.get("agents_editing") and editing is None:
        clear_form()
    listing, form = st.columns([1.15, 1], gap="medium")
    with listing:
        ui.section(f"Agent tùy biến ({len(agents)})")
        if not agents:
            st.info("Chưa có agent tùy biến. Tạo agent ở khung bên cạnh.", icon=":material/smart_toy:")
        for spec in agents:
            custom_card(spec)
    with form.container(border=True, key="agents_custom_form"):
        custom_form(editing)


with st.container(key="page_heading"):
    ui.page_header("Quản lý agent", "9 agent lõi cố định (chỉ đổi model), cùng các agent tùy biến bạn tự thêm.",
                   live_badge=False)
with st.container(key="agents_flash_box"):   # khung cố định: thông báo không làm đổi vị trí của tabs
    show_flash()
# `key` + on_change="rerun": Streamlit nhớ tab đang mở, nên sau khi Lưu (st.rerun) vẫn ở đúng tab đó.
quick_tab, model_tab, custom_tab = st.tabs([":material/bolt: Kết nối nhanh", ":material/lock: Agent lõi",
                                            ":material/smart_toy: Agent tùy biến"],
                                           key="agents_tab", on_change="rerun")
with quick_tab:
    show_quick()
with model_tab:
    show_models()
with custom_tab:
    show_custom_agents()
