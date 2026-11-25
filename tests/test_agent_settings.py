"""Cấu hình model theo agent và agent LLM tùy biến (chạy chế độ quy tắc, không gọi API)."""
import pytest

import agent_settings
import llm
from agents import custom_agent
from config import AGENT_SETTINGS_FILE
from graph import APPROVALS, build_graph, run_design
from main import SAMPLE


@pytest.fixture(autouse=True)
def clean_settings():
    AGENT_SETTINGS_FILE.unlink(missing_ok=True)
    yield
    AGENT_SETTINGS_FILE.unlink(missing_ok=True)


def test_custom_stages_follow_approval_order():
    assert list(agent_settings.CUSTOM_STAGES) == list(APPROVALS)


def test_ui_override_takes_priority_over_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_ARCHITECT", "openai")
    monkeypatch.setenv("LLM_MODEL_ARCHITECT", "gpt-6-luna")
    assert llm.agent_config("architect")["model"] == "gpt-6-luna"

    agent_settings.set_model("architect", "anthropic")
    cfg = llm.agent_config("architect")
    # Đổi nhà cung cấp mà không ghi model -> model mặc định của nhà cung cấp mới, không mượn model OpenAI.
    assert (cfg["provider"], cfg["model"], cfg["temperature"], cfg["source"]) == (
        "anthropic", "claude-sonnet-5-5", 0.3, "ui")

    agent_settings.set_model("architect", "", "gpt-6.1-sol")
    cfg = llm.agent_config("architect")
    # Cùng nhà cung cấp với .env: OpenAI mặc định không gửi temperature.
    assert (cfg["provider"], cfg["model"], cfg["temperature"]) == ("openai", "gpt-6.1-sol", None)

    agent_settings.clear_model("architect")
    assert llm.agent_config("architect")["source"] == "env"


def test_run_snapshot_wins_over_live_file():
    agent_settings.set_model("reviewer", "gemini", "gemini-2.5-pro")
    token = agent_settings.run_settings.set({"models": {}, "custom_agents": []})
    try:
        assert llm.agent_config("reviewer")["provider"] == "none"
    finally:
        agent_settings.run_settings.reset(token)
    assert llm.agent_config("reviewer")["provider"] == "gemini"


@pytest.mark.parametrize("item", [
    {"provider": "mistral"},
    {"model": "gpt 6\nrm"},
])
def test_invalid_model_rejected(item):
    with pytest.raises(ValueError):
        agent_settings.validate_model(item)


def test_saved_temperature_is_ignored():
    """Tệp cấu hình cũ còn temperature: bỏ qua, agent dùng mức mặc định."""
    agent_settings.save({"models": {"reviewer": {"provider": "gemini", "model": "", "temperature": 1.4}},
                         "custom_agents": []})
    assert agent_settings.load()["models"]["reviewer"] == {"provider": "gemini", "model": ""}
    assert llm.agent_config("reviewer")["temperature"] == 0.3


def test_custom_agent_validation():
    with pytest.raises(ValueError, match="Chưa có dữ liệu"):
        agent_settings.upsert_custom({"name": "Kết cấu", "prompt": "Rà soát", "after": "architect",
                                      "inputs": ["area_table"]})
    with pytest.raises(ValueError, match="Thiếu Tên"):
        agent_settings.upsert_custom({"name": " ", "prompt": "Rà soát", "after": "drafter"})
    first = agent_settings.upsert_custom({"name": "Kỹ sư kết cấu", "prompt": "Rà soát", "after": "drafter"})
    second = agent_settings.upsert_custom({"name": "Kỹ sư kết cấu", "prompt": "Rà soát", "after": "drafter"})
    assert (first["id"], second["id"]) == ("custom_ky_su_ket_cau", "custom_ky_su_ket_cau_2")
    assert agent_settings.delete_custom(second["id"]) and not agent_settings.delete_custom(second["id"])


def test_core_agents_are_locked():
    from config import AGENT_ORDER

    assert agent_settings.CORE_AGENTS == tuple(AGENT_ORDER) and len(AGENT_ORDER) == 9
    # Chỉ đổi model của agent lõi có LLM; agent thuật toán và mã lạ bị từ chối.
    for agent in ("drafter", "fengshui_advisor", "final_reviewer", "custom_x", "unknown"):
        with pytest.raises(ValueError, match="agent lõi có dùng LLM"):
            agent_settings.set_model(agent, "openai")
    # Agent tùy biến không mang mã hoặc tên của agent lõi, nên không thay thế/ghi đè được agent lõi.
    for item in ({"id": "architect"}, {"id": "custom_architect", "name": "Thiết kế công năng"},
                 {"name": "drafter"}, {"name": "KIỂM ĐỊNH QUY CHUẨN"}):
        with pytest.raises(ValueError):
            agent_settings.upsert_custom({"name": "X", "prompt": "x", "after": "drafter", **item})
    assert not agent_settings.delete_custom("architect")
    # Sửa tay tệp cấu hình cũng không gắn được model cho agent lõi không dùng LLM.
    agent_settings.save({"models": {"drafter": {"provider": "openai"}, "architect": {"provider": "gemini"}},
                         "custom_agents": [{"id": "custom_a", "name": "Triển khai bản vẽ", "prompt": "x",
                                            "after": "drafter"}]})
    data = agent_settings.load()
    assert list(data["models"]) == ["architect"] and data["custom_agents"] == []


def test_corrupt_settings_file_is_ignored():
    AGENT_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    AGENT_SETTINGS_FILE.write_text("{not json", encoding="utf-8")
    assert agent_settings.load()["custom_agents"] == []
    assert llm.agent_config("architect")["source"] == "env"


def test_custom_agent_runs_in_workflow_and_keeps_route():
    spec = agent_settings.upsert_custom({"name": "Kỹ sư kết cấu", "role": "Kết cấu nhà phố", "prompt": "Nêu rủi ro",
                                         "after": "drafter", "inputs": ["brief", "area_table"]})
    agent_settings.upsert_custom({"name": "Đang tắt", "prompt": "x", "after": "drafter", "enabled": False})
    state = run_design(SAMPLE.replace("2,5 tỷ", "8 tỷ"), persist=False)

    assert state["outcome"] == "done" and state.get("final_files")
    assert list(state["custom_outputs"]) == [spec["id"]]
    note = state["custom_outputs"][spec["id"]]
    assert note["status"] == "no_llm" and note["after"] == "drafter"   # test chạy chế độ quy tắc
    entries = [h for h in state["history"] if h["agent"] == spec["id"]]
    assert entries and set(entries[0]["input"]) == {"brief", "area_table"}
    # Agent lõi phía sau vẫn chạy đủ: agent tùy biến không đổi nhánh của luồng.
    assert state.get("review") and state.get("cost") and state.get("final_review")


def test_custom_agent_has_task_in_work_list():
    from config import AGENT_ORDER
    from monitoring import events, rubrics, tasks
    from monitoring.timeline import build_timeline
    from graph import NODE_AGENT

    spec = agent_settings.upsert_custom({"name": "Kỹ sư kết cấu", "prompt": "x", "after": "drafter",
                                         "inputs": ["brief"]})
    state = run_design(SAMPLE.replace("2,5 tỷ", "8 tỷ"))
    rows = tasks.list_tasks(state["run_id"])
    agents = [row["agent_id"] for row in rows]
    assert set(AGENT_ORDER) <= set(agents) and spec["id"] in agents   # đủ 9 agent lõi + agent tùy biến
    task = next(row for row in rows if row["agent_id"] == spec["id"])
    assert (task["name"], task["status"]) == ("Kỹ sư kết cấu", "completed")
    assert agents.index(spec["id"]) == agents.index("drafter") + 1   # chạy ngay sau bước được gắn
    attempt = tasks.attempts(task["task_id"])[0]
    assert set(attempt["input"]) == {"brief"} and attempt["output"]["chi_tiet_agent"]["status"] == "no_llm"
    assert rubrics.evaluate(attempt)["criteria"][0]["status"] == "missing"   # chưa có model: chưa chấm được
    timeline = build_timeline(tasks.timeline_attempts(state["run_id"]), events.get_events(state["run_id"]),
                              run_status="done", targets=NODE_AGENT)
    assert {"id": spec["id"], "name": "Kỹ sư kết cấu"} in timeline["rows"]
    assert any(item["agent"] == spec["id"] for item in timeline["attempts"])   # có thanh xử lý trên Timeline


def test_custom_agent_not_run_when_flow_goes_back():
    agent_settings.upsert_custom({"name": "Sau kiểm định", "prompt": "x", "after": "reviewer"})
    settings = agent_settings.snapshot()
    assert custom_agent.pending({"route": "cost_estimator", "agent_settings": settings}, "reviewer")
    assert not custom_agent.pending({"route": "coordinate_repair", "agent_settings": settings}, "reviewer")
    assert not custom_agent.pending({"route": "end", "agent_settings": settings}, "reviewer")
    assert not custom_agent.pending({"route": "cost_estimator", "agent_settings": settings}, "drafter")


def test_custom_prompt_contains_selected_data_only():
    spec = agent_settings.validate_custom({"id": "custom_x", "name": "X", "prompt": "Làm việc", "after": "drafter",
                                           "inputs": ["brief"]})
    system, prompt = custom_agent.build_prompt(spec, {"brief": {"so_tang": 3}, "cost": {"tong_chi_phi": 1}})
    assert "Làm việc" in system and '"so_tang": 3' in prompt and "tong_chi_phi" not in prompt


def test_graph_has_hook_after_every_approval():
    nodes = build_graph().get_graph().nodes
    assert all(custom_agent.hook_name(stage) in nodes for stage in APPROVALS)


def test_connection_check_without_api():
    assert llm.test_connection("none", "")["ok"] is False
    result = llm.test_connection("mistral", "x")
    assert result["ok"] is False and "chưa hỗ trợ" in result["message"]
