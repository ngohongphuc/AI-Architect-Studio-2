from config import AGENT_ORDER
from monitoring import events
from studio3d.data import office_data, project_geometry


def test_idle_office_contains_each_real_agent_once():
    data = office_data({}, [], {}, run_id=None, status="idle", current=None)
    assert len(data["rooms"]) == 7
    assert [a["id"] for a in data["agents"]] == AGENT_ORDER
    assert all(a["status"] == "waiting" and not a["input"] and not a["output"] for a in data["agents"])
    assert not data["transfers"]
    assert data["geometry"] is None
    assert "performance" not in data
    assert all(a["duration"] is None and a["tokens"] is None for a in data["agents"])


def test_geometry_uses_actual_rooms_and_elevations():
    state = {
        "area_table": {"so_tang": 5},
        "layout": {
            "building": {"x": 1, "y": 2, "w": 4, "l": 10},
            "heights": [3.5, 3.2],
            "so_tang": 2,
            "floors": {
                "1": {"rooms": [
                    {"x": 1, "y": 2, "w": 4, "h": 10, "loai": "khach"},
                    {"x": 1, "y": 0, "w": 4, "h": 2, "loai": "san"},
                ]},
                "2": {"rooms": [{"x": 2, "y": 3, "w": 2, "h": 5, "loai": "ngu"}]},
            },
        },
    }
    assert project_geometry(state) == {
        "width": 4, "depth": 10,
        "floors": [
            {"height": 3.5, "rooms": [{"x": 0, "z": 0, "w": 4, "d": 10, "kind": "khach"}]},
            {"height": 3.2, "rooms": [{"x": 1, "z": 1, "w": 2, "d": 5, "kind": "ngu"}]},
        ],
    }
    state["layout"]["floors"]["2"]["rooms"][0]["h"] = 15
    assert project_geometry(state) is None
    assert project_geometry({"area_table": {"so_tang": 5}}) is None


def test_office_reuses_event_ids_and_marks_feedback_without_extra_events(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "LOG_DB", tmp_path / "events.db")
    events.emit("real-run", {"agent": "reviewer", "status": "done", "time": "09:01:42",
                             "to_agent": "project_manager", "summary": "Chuyển phản hồi kiểm định",
                             "feedback": True, "version": 1})
    events.emit("real-run", {"agent": "project_manager", "status": "done", "time": "09:01:42",
                             "to_agent": "architect", "summary": "Giao sửa công năng", "feedback": True, "version": 2})
    rows = events.get_events("real-run")
    state = {"fengshui_enabled": False, "iteration": 1}
    data = office_data(state, rows, {}, run_id="real-run", status="awaiting_approval", current="project_manager")
    assert [item["id"] for item in data["transfers"]] == [row["id"] for row in rows]
    assert data["transfers"][0]["feedback"]
    assert data["transfers"][1]["pending"]
    assert data["transfers"][1]["to"] == "architect"
    assert next(a for a in data["agents"] if a["id"] == "fengshui_advisor")["status"] == "skipped"
    assert next(a for a in data["agents"] if a["id"] == "reviewer")["issues"] == ["Chuyển phản hồi kiểm định"]
    assert events.get_events("real-run") == rows


def test_manual_forward_uses_the_users_approved_destination():
    rows = [
        {"id": 11, "agent": "reviewer", "status": "done", "time": "09:01:42", "to_agent": "project_manager",
         "summary": "Đề nghị trả về Chủ nhiệm", "feedback": True, "version": 1},
        {"id": 12, "agent": "user", "status": "done", "time": "09:02:02", "to_agent": "cost_estimator",
         "summary": "Đi tiếp và giữ lại lỗi đã phát hiện", "feedback": True, "version": 0},
    ]
    state = {"approval_points": ["reviewer"]}
    waiting = office_data(state, rows[:1], {}, run_id="r", status="running", current="reviewer")
    assert waiting["transfers"][-1]["pending"]
    approved = office_data(state, rows, {}, run_id="r", status="running", current="cost_estimator")
    assert approved["transfers"] == [
        {"id": 12, "from": "reviewer", "to": "cost_estimator", "time": "09:02:02",
         "summary": "Đi tiếp và giữ lại lỗi đã phát hiện", "approved": True, "feedback": False},
    ]


def test_approval_keeps_the_real_document_summary_and_sender():
    rows = [
        {"id": 1, "agent": "drafter", "status": "done", "time": "09:00:05",
         "to_agent": "reviewer", "summary": "Bộ bản vẽ mặt bằng v2", "feedback": False, "version": 2},
        {"id": 2, "agent": "user", "status": "done", "time": "09:01:02",
         "to_agent": "reviewer", "summary": "Đồng ý: Duyệt mặt bằng và bản vẽ", "feedback": False, "version": 0},
    ]
    payload = office_data({"approval_points": ["drafter"]}, rows, {}, run_id="r", status="running", current="reviewer")
    transfer, = payload["transfers"]
    assert transfer["id"] == 2 and transfer["approved"] and not transfer.get("pending")
    assert (transfer["from"], transfer["to"], transfer["summary"]) == ("drafter", "reviewer", "Bộ bản vẽ mặt bằng v2")


def test_studio_counts_actual_unverified_checks_once_and_keeps_source():
    state = {
        "final_files": {"ban_ve_pdf": "ban_ve.pdf"},
        "fengshui_enabled": False,
        "remaining_issues": [{"ma": "THIEU_CAN_CU", "muc": "Căn cứ quy chuẩn", "noi_dung": "Thiếu xác minh."}],
        "review": {"kiem_tra": [
            {"muc": "Mật độ", "loai": "Quy chuẩn", "dat": None, "ly_do": "Thiếu hồ sơ lô đất.",
             "nguon": "Nguồn tham khảo"},
            {"muc": "Phòng nằm trong biên", "loai": "Kỹ thuật", "dat": True},
        ]},
    }
    data = office_data(state, [], {}, run_id="real-run", status="done", current=None)
    assert data["run"]["status"] == "done"
    assert data["run"]["fengshui_enabled"] is False
    quality = data["quality"]
    assert quality["preliminary"] and quality["unverified"] == 1
    assert quality["technical"] == "Đạt" and quality["regulatory"] == "Chưa đủ căn cứ đánh giá"
    finding, = quality["findings"]
    assert finding["reason"] == "Thiếu hồ sơ lô đất." and "Nguồn tham khảo" in finding["source"]


def test_studio_separates_verified_violation_from_running_agent():
    state = {"review": {"kiem_tra": [{"muc": "Số tầng", "loai": "Quy chuẩn", "dat": False,
                                     "da_xac_minh": True, "nguon": "Nguồn kiểm thử", "pham_vi": "Lô kiểm thử"}]}}
    event = {"id": 1, "agent": "reviewer", "status": "running", "time": "10:00:00", "summary": "Đang xử lý"}
    data = office_data(state, [event], {}, run_id="run", status="running", current="reviewer")
    assert data["run"]["current"] == "reviewer"
    assert next(a for a in data["agents"] if a["id"] == "reviewer")["status"] == "running"
    assert data["quality"]["regulatory"] == "Không đạt do vi phạm"
    assert data["quality"]["unverified"] == 0
    assert data["quality"]["findings"][0]["source"] == "Nguồn kiểm thử"


def test_agent_activity_fields():
    running = {"id": 1, "agent": "drafter", "status": "running", "time": "10:00:00", "summary": "Đang xử lý",
               "occurred_at": "2026-11-25T10:00:00+00:00"}
    custom = {"id": 2, "agent": "custom_x", "status": "running", "time": "10:00:00", "summary": "Đang xử lý",
              "occurred_at": "2026-11-25T10:00:01+00:00"}
    state = {"agent_settings": {"custom_agents": [{"id": "custom_x", "name": "Kết cấu", "role": "Kỹ sư"}]}}
    data = office_data(state, [running, custom], {}, run_id="r", status="running", current="drafter",
                       step_name="Triển khai bản vẽ")
    drafter = next(a for a in data["agents"] if a["id"] == "drafter")
    assert (drafter["step"], drafter["since"]) == ("Triển khai bản vẽ", running["occurred_at"])
    assert [(h["name"], h["status"], h["since"]) for h in data["helpers"]] == [("Kết cấu", "running", custom["occurred_at"])]
    paused = office_data(state, [running, custom], {}, run_id="r", status="paused", current="reviewer")
    assert next(a for a in paused["agents"] if a["id"] == "reviewer")["status"] == "paused"
    assert paused["helpers"][0]["status"] == "paused" and paused["helpers"][0]["since"] is None
    waiting = office_data({}, [], {}, run_id="r", status="awaiting_approval", current="drafter", upcoming="reviewer")
    assert waiting["run"]["upcoming"] == "reviewer" and waiting["helpers"] == []


def test_new_task_of_same_agent_is_not_reported_as_rework():
    from graph import run_design
    from main import SAMPLE
    from monitoring import events

    state = run_design(SAMPLE.replace("2,5 tỷ", "8 tỷ"), persist=False)
    rows = [(e["agent"], e["status"]) for e in events.get_events(state["run_id"])]
    assert state["iteration"] == 0 and rows.count(("project_manager", "running")) >= 3
    assert not any(status == "revising" for _, status in rows)
