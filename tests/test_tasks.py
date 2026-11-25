from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import graph
import llm
from agents.base import agent_node
from monitoring import events, runner, tasks


@pytest.fixture
def store(tmp_path, monkeypatch):
    db = tmp_path / "log.db"
    monkeypatch.setattr(events, "LOG_DB", db)
    monkeypatch.setattr(graph, "OUTPUT_DIR", tmp_path / "output")
    return db


def use_graph(monkeypatch):
    workflow = graph.build_graph()
    monkeypatch.setattr(runner, "get_graph", lambda: workflow)
    return workflow, runner.RunManager()


def wait(run, status):
    run.thread.join(10)
    assert not run.thread.is_alive()
    assert run.status == status, run.error


def test_retry_and_acceptance_are_separate_and_reads_are_idempotent(store, monkeypatch):
    key = "sample-test-api-key-for-redaction"
    monkeypatch.setenv("OPENAI_API_KEY", key)
    reply = SimpleNamespace(content="Nội dung hợp lệ", usage_metadata={"input_tokens": 12, "output_tokens": 3},
                            response_metadata={"model_name": "mock-model", "cost_usd": 0.001})
    client = Mock()
    client.invoke.return_value = reply
    monkeypatch.setattr(llm, "get_llm", lambda: client)

    @agent_node("project_manager")
    def start(state):
        text = llm.invoke_text("Viết nội dung", f"OPENAI_API_KEY={key}")
        return {"route": "end", "outcome": "done", "revision_id": "rev-1",
                "_output": {"description": text, "api_key": key}}

    monkeypatch.setattr(graph.project_manager, "start", start)
    _, manager = use_graph(monkeypatch)
    run = manager.start("Đất 5×20m", approval_points=["project_manager"], submission_id="draft")
    wait(run, "awaiting_approval")
    row, = tasks.list_tasks(run.run_id, status="awaiting_approval")
    task_id = row["task_id"]
    first, = tasks.attempts(task_id)
    assert first["processed"] and first["acceptance"] == "pending"
    assert first["output_version"] == first["approval_version"] == "rev-1"
    assert first["assigned_at"] <= first["started_at"] <= first["finished_at"]
    assert first["wait_s"] >= 0 and first["processing_s"] >= 0
    assert (first["model"], first["tokens"], first["call_count"], first["cost_usd"]) == ("mock-model", 15, 1, 0.001)
    assert first["cost_basis"] == "reported"
    assert key not in str(first) and first["output"]["chi_tiet_agent"]["api_key"] == "[đã ẩn]"

    before = events.get_events(run.run_id)
    for _ in range(3):
        assert manager.get(run.run_id) is run
        assert tasks.list_tasks(run.run_id, agent="project_manager") == [row]
        assert tasks.attempts(task_id) == [first]
    assert events.get_events(run.run_id) == before
    assert manager.start("Trùng lượt", submission_id="draft") is run
    assert client.invoke.call_count == 1

    run.answer("rerun")
    wait(run, "awaiting_approval")
    second, previous = tasks.attempts(task_id)
    assert previous["attempt_id"] == first["attempt_id"] and previous["acceptance"] == "changes_requested"
    assert second["attempt_id"] != first["attempt_id"] and second["attempt_no"] == 2
    assert second["retry_category"] == "unknown" and second["retry_reason"]
    assert second["acceptance"] == "pending"

    run.answer("approve")
    wait(run, "done")
    accepted, previous = tasks.attempts(task_id)
    assert accepted["status"] == "completed" and accepted["acceptance"] == "accepted"
    assert accepted["decision_at"] >= accepted["approval_requested_at"]
    assert previous["acceptance"] == "changes_requested"
    assert client.invoke.call_count == 2
    assert run.rerun_agent("project_manager", expected_revision="rev-1")
    wait(run, "awaiting_approval")
    third, accepted, _ = tasks.attempts(task_id)
    assert third["attempt_no"] == 3 and third["acceptance"] == "pending"
    assert accepted["acceptance"] == "accepted" and client.invoke.call_count == 3


def test_queue_is_shared_by_pause_resume_and_stop(store, monkeypatch):
    entered, proceed = Event(), Event()

    def plan(state):
        entered.set()
        assert proceed.wait(5)
        return {"route": "concept_architect"}

    concept = Mock(return_value={"route": "end", "outcome": "done"})
    monkeypatch.setattr(graph.project_manager, "start", Mock(return_value={"route": "requirements_analyst"}))
    monkeypatch.setattr(graph.requirements_analyst, "run", Mock(return_value={"route": "plan_options"}))
    monkeypatch.setattr(graph.project_manager, "plan_options", plan)
    monkeypatch.setattr(graph.concept_architect, "run", concept)
    workflow, manager = use_graph(monkeypatch)
    run = manager.start("Đất 5×20m")
    assert entered.wait(5)
    working, = tasks.list_tasks(run.run_id, status="running")
    assert working["stage"] == "plan_options"
    run.pause()
    proceed.set()
    wait(run, "paused")
    queued, = tasks.list_tasks(run.run_id, status="queued")
    assert queued["stage"] == "concept_architect"
    snapshot = workflow.get_state(run.config)
    ready = [(node.id, node.name) for node in snapshot.tasks]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: tasks.queue_ready(snapshot.values, ready), range(6)))
    initial, = tasks.attempts(queued["task_id"])
    assert initial["started_at"] is None and not concept.called

    run.resume()
    wait(run, "done")
    final, = tasks.attempts(queued["task_id"])
    assert final["attempt_id"] == initial["attempt_id"]
    assert final["wait_s"] >= 0 and final["status"] == "completed"
    assert final["call_count"] is final["model"] is final["tokens"] is final["cost_usd"] is None
    concept.assert_called_once()

    stopping = manager.start("Đất 5×20m", approval_points=["project_manager"])
    wait(stopping, "awaiting_approval")
    stopping.stop()
    canceled, = tasks.list_tasks(stopping.run_id, status="canceled")
    assert canceled["processed"] and canceled["acceptance"] == "canceled"
    assert runner.RunManager().get(stopping.run_id).status == "stopped"


def test_error_retry_preserves_unknown_usage_and_masks_secrets(store, monkeypatch):
    secret = "test-secret-used-by-fake-provider-only"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    client = Mock()
    client.invoke.side_effect = ConnectionError(f"API_KEY={secret}")
    monkeypatch.setattr(llm, "get_llm", lambda: client)
    fail = True

    @agent_node("project_manager")
    def start(state):
        if fail:
            assert llm.invoke_text("Test", "Test", retries=1) is None
            raise TimeoutError(f"Authorization: Bearer {secret}")
        return {"route": "end", "outcome": "done"}

    monkeypatch.setattr(graph.project_manager, "start", start)
    workflow, manager = use_graph(monkeypatch)
    run = manager.start("Đất 5×20m")
    wait(run, "error")
    row, = tasks.list_tasks(run.run_id, status="error")
    failed, = tasks.attempts(row["task_id"])
    assert failed["failure_category"] == "infrastructure" and not failed["processed"]
    assert failed["tokens"] is failed["cost_usd"] is None
    assert failed["call_count"] == failed["api_errors"] == 2
    assert "TimeoutError" in failed["error"] and secret not in run.error
    with events._conn() as con:
        assert secret not in "\n".join(con.iterdump())

    fail = False
    workflow.invoke(None, run.config)
    retry, prior = tasks.attempts(row["task_id"])
    assert prior["status"] == "error" and retry["status"] == "completed"
    assert retry["retry_category"] == "infrastructure" and retry["retry_reason"]


def test_task_schema_keeps_legacy_event_history(store):
    with events._conn() as con:
        con.executescript("""
            CREATE TABLE runs (run_id TEXT PRIMARY KEY, created TEXT, request TEXT, status TEXT, output_dir TEXT, summary TEXT);
            CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, time TEXT, agent TEXT, status TEXT,
                                 to_agent TEXT, summary TEXT, tokens INTEGER, duration_s REAL, version INTEGER, feedback INTEGER);
            INSERT INTO runs VALUES ('old', '2024-01-01', 'Old request', 'done', '', '{}');
            INSERT INTO events (run_id, time, agent, status, summary) VALUES ('old', '08:00:00', 'architect', 'done', 'Old event');
        """)
    assert tasks.list_tasks("old") == []
    assert events.list_runs()[0]["run_id"] == "old"
    historic, = events.get_events("old")
    assert historic["summary"] == "Old event" and historic["occurred_at"] is None and historic["attempt_id"] is None


def test_clarification_retry_is_classified_as_missing_input(store, monkeypatch):
    monkeypatch.setattr(graph.project_manager, "start", Mock(return_value={"route": "requirements_analyst"}))

    def analyze(state):
        if state["user_request"] == "Thiết kế nhà":
            return {"route": "end", "outcome": "needs_input",
                    "brief_assessment": {"questions": ["Kích thước lô đất?"]}}
        return {"route": "end", "outcome": "done"}

    analyst = Mock(side_effect=analyze)
    monkeypatch.setattr(graph.requirements_analyst, "run", analyst)
    _, manager = use_graph(monkeypatch)
    run = manager.start("Thiết kế nhà", approval_points=[], request_fields={"ma_lo_dat": "QA/01"})
    wait(run, "needs_input")
    row, = tasks.list_tasks(run.run_id, agent="requirements_analyst")
    pending, = tasks.attempts(row["task_id"])
    assert pending["failure_category"] == "missing_input"
    assert pending["processed"] and pending["acceptance"] == "pending"
    run.answer("edit_request", request="Thiết kế nhà trên đất 5×20 m")
    wait(run, "done")
    new, old = tasks.attempts(row["task_id"])
    assert new["retry_category"] == "missing_input"
    assert new["input"]["user_request"] == "Thiết kế nhà trên đất 5×20 m"
    assert new["input"]["request_fields"] == {"ma_lo_dat": "QA/01"}
    assert new["acceptance"] is None and old["acceptance"] == "changes_requested"
    assert analyst.call_count == 2
