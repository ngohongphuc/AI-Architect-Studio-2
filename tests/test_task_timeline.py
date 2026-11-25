from datetime import datetime, timedelta, timezone
from threading import Barrier

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from monitoring import events, tasks
from monitoring.timeline import build_timeline, timestamp
from state import DesignState


def test_parallel_task_intervals_and_repair_history_share_stored_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "LOG_DB", tmp_path / "tasks.db")
    events.record_run("test", "Chạy kiểm thử", "")
    parallel = Barrier(2, timeout=5)

    def drawing(state):
        if not state.get("task_retry"):
            parallel.wait()
        events.emit("test", {"time": "00:04:08", "status": "done", "agent": "drafter",
                             "to_agent": "reviewer", "summary": "Bàn giao bản vẽ"})
        return {}

    def review(state):
        parallel.wait()
        return {}

    def repair(state):
        events.emit("test", {"time": "00:04:09", "status": "done", "agent": "project_manager",
                             "to_agent": "drafter", "summary": "Giao sửa", "feedback": True})
        return {"iteration": 1, "task_retry": {"category": "agent_error", "reason": "Sửa mặt bằng vòng 1"}}

    graph = StateGraph(DesignState)
    for name, func in (("drafter", drawing), ("reviewer", review), ("coordinate_repair", repair)):
        graph.add_node(name, tasks.track_stage(name, func))
    graph.add_edge(START, "drafter")
    graph.add_edge(START, "reviewer")
    graph.add_conditional_edges("drafter", lambda state: END if state.get("task_retry") else "coordinate_repair",
                                [END, "coordinate_repair"])
    graph.add_edge("reviewer", END)
    graph.add_edge("coordinate_repair", "drafter")
    workflow = graph.compile(checkpointer=MemorySaver())
    list(tasks.stream_tracked(workflow, {"run_id": "test"}, {"configurable": {"thread_id": "test"}}))

    tasks.approval_pending({"run_id": "test"}, "drafter")
    tasks.approval_decided({"run_id": "test"}, "drafter", "changes_requested")
    history = tasks.timeline_attempts("test")
    timeline = build_timeline(history, events.get_events("test"), run_status="done", targets={})
    first, second = [item for item in timeline["attempts"] if item["agent"] == "drafter"]
    inspecting = next(item for item in timeline["attempts"] if item["agent"] == "reviewer")
    assert max(first["processing"][0], inspecting["processing"][0]) <= min(first["processing"][1], inspecting["processing"][1])
    assert (first["number"], second["number"]) == (1, 2)
    assert first["processing"][1] <= second["processing"][0] <= second["processing"][1] <= second["approval"][0]
    assert second["approval"][0] <= second["approval"][1]
    assert {item["kind"] for item in timeline["markers"]} >= {"handoff", "repair", "approval", "retry"}
    assert all(item["attempt_id"] for item in timeline["markers"])
    detail = tasks.find_attempt("test", second["id"])
    assert detail["name"] == "Triển khai bản vẽ" and detail["retry_category"] == "agent_error"
    assert tasks.find_attempt("different-run", second["id"]) is None
    assert timeline["missing_attempts"] == timeline["missing_events"] == 0

    filtered = build_timeline(history, events.get_events("test"), run_status="done", targets={}, agent="drafter")
    assert len(filtered["rows"]) == 1 and [item["id"] for item in filtered["attempts"]] == [first["id"], second["id"]]
    assert filtered["extent"] == timeline["extent"]


def test_live_endpoint_and_incomplete_history_do_not_invent_durations():
    origin = datetime(2025, 11, 18, 23, 59, 59, tzinfo=timezone.utc)
    later = (origin + timedelta(seconds=7)).isoformat()
    start = origin.isoformat()
    base = {"agent_id": "reviewer", "name": "Đối chiếu", "attempt_no": 1, "assigned_at": start,
            "approval_requested_at": None, "decision_at": None}
    live = dict(base, attempt_id="active", status="running", started_at=start, finished_at=None)
    waiting = dict(base, attempt_id="queue", status="queued", started_at=None, finished_at=None)
    pending = dict(base, attempt_id="pending", status="awaiting_approval", started_at=start,
                   finished_at=later, approval_requested_at=later)
    incomplete = dict(base, attempt_id="before", status="completed", started_at=None, finished_at=later)
    old_event = {"id": 1, "agent": "reviewer", "to_agent": "architect", "status": "done", "time": "23:59:59"}
    newer = dict(old_event, id=2, occurred_at=later, attempt_id="pending")
    result = build_timeline([live, waiting, pending, incomplete], [old_event, newer], run_status="running", targets={})
    assert result["missing_attempts"] == result["missing_events"] == 1
    active, review = result["attempts"]
    assert active["processing"] == [timestamp(start), None]
    assert review["processing"] == [timestamp(start), timestamp(later)]
    assert review["approval"] == [timestamp(later), None]
    assert [item["kind"] for item in result["markers"]] == ["queued", "approval", "handoff"]
    assert result["markers"][-1]["at"] == timestamp(later)

    ended = build_timeline([live, waiting, incomplete], [old_event], run_status="stopped", targets={})
    assert not ended["attempts"] and ended["missing_attempts"] == 2
    assert ended["markers"][0]["kind"] == "queued"
