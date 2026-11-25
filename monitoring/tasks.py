"""Theo dõi công việc thật theo checkpoint, tách lần xử lý khỏi quyết định duyệt."""
from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable
from contextlib import closing
from datetime import datetime, timezone
from typing import NamedTuple
from uuid import uuid4

from langgraph.config import get_config

import agent_settings
from monitoring import events, rubrics
from monitoring.redaction import error_category, error_text, redact
from monitoring.tracker import AttemptUsage, current_agent, current_run, current_usage


class Stage(NamedTuple):
    agent: str
    name: str
    description: str
    inputs: str
    criteria: str


STAGES = {
    "project_manager": Stage("project_manager", "Khởi tạo lượt",
                             "Chuẩn bị hồ sơ và giao phân tích yêu cầu.", "run_id user_request request_fields max_iterations fengshui_enabled",
                             "Xác định được lượt thiết kế, tùy chọn và bước nhận việc."),
    "requirements_analyst": Stage("requirements_analyst", "Phân tích yêu cầu",
                                  "Chuẩn hóa yêu cầu và phát hiện mâu thuẫn.", "user_request request_fields",
                                  "Có brief có cấu trúc hoặc danh sách thông tin phải bổ sung."),
    "plan_options": Stage("project_manager", "Giao lập phương án",
                          "Xác định hướng so sánh và thông tin cần kiểm chứng.", "brief brief_assessment",
                          "Nêu hướng so sánh, giả định và vướng mắc về nguồn."),
    "concept_architect": Stage("concept_architect", "Lập ý tưởng",
                               "Đề xuất quy mô và định hướng kiến trúc.", "brief option_brief feedback",
                               "Có số tầng, phong cách, vật liệu, chiếu sáng và thông gió."),
    "architect": Stage("architect", "Thiết kế công năng",
                       "Lập chương trình phòng và phương án để so sánh.", "brief concept_plan option_brief program feedback",
                       "Tầng và phòng có định danh, kích thước và yêu cầu bố trí đối chiếu được."),
    "compare_options": Stage("cost_estimator", "So sánh phương án",
                             "Tính chi phí và kiểm tra các phương án để đề xuất lựa chọn.", "brief program options selected_by_user",
                             "Có kết quả kiểm tra và chi phí từng phương án tính được, kèm lý do đề xuất."),
    "check_edited_option": Stage("cost_estimator", "Kiểm tra phương án đã chỉnh",
                                 "Tính lại chi phí và đánh giá thay đổi người dùng vừa chốt.", "brief program options selected_by_user",
                                 "Kết quả gắn với phiên bản vừa chỉnh và nêu rõ các vấn đề còn lại."),
    "drafter": Stage("drafter", "Triển khai bản vẽ",
                     "Bố trí hình học và xuất bản vẽ.", "brief program",
                     "Có bảng diện tích từ hình học, bản vẽ và thông tin các lỗi bố trí nếu có."),
    "fengshui_advisor": Stage("fengshui_advisor", "Tư vấn phong thủy",
                              "Đưa gợi ý tùy chọn theo dữ liệu thiết kế.", "brief layout fengshui_enabled",
                              "Nêu dữ liệu áp dụng và giữ tư vấn riêng với kết luận quy chuẩn."),
    "reviewer": Stage("reviewer", "Kiểm định quy chuẩn",
                      "Kiểm tra hình học và đối chiếu căn cứ quy chuẩn.", "brief program layout area_table",
                      "Mỗi kết luận có nguồn và phạm vi, mục thiếu dữ liệu nêu lý do chưa xác minh."),
    "cost_estimator": Stage("cost_estimator", "Lập dự toán",
                            "Tính khối lượng, chi phí và xuất bảng tính.", "brief program layout area_table review",
                            "Dự toán khớp phiên bản và nêu chênh lệch ngân sách cùng gợi ý nếu có."),
    "coordinate_repair": Stage("project_manager", "Điều phối vòng sửa",
                                "Xét lỗi và chuyển cho bước xử lý phù hợp.", "repair_target repair_fallback feedback feedback_source iteration max_iterations",
                                "Chuyển đúng bước hoặc liệt kê lỗi còn lại khi hết vòng sửa."),
    "pm_report": Stage("project_manager", "Tổng hợp thuyết minh",
                       "Tổng hợp bản vẽ, thuyết minh và dự toán.", "brief program layout area_table drawings review fengshui cost cost_file",
                       "Hồ sơ nháp có cùng phiên bản, giả định và nội dung cần xác minh."),
    "final_reviewer": Stage("final_reviewer", "Đối chiếu hồ sơ cuối",
                            "Đối chiếu dữ liệu và tệp trước khi xuất.", "brief program area_table layout cost draft_files",
                            "Có kết quả đối chiếu số tầng, số phòng, diện tích, chi phí và lệch phiên bản."),
    "propose_adjustment": Stage("project_manager", "Đề xuất điều chỉnh",
                                "Thử các biến thể yêu cầu khi lượt chưa đạt và đề xuất cách điều chỉnh khả thi.",
                                "brief remaining_issues",
                                "Mỗi đề xuất bố trí được, nằm trong ngân sách và kèm mô tả yêu cầu mới."),
    "publish": Stage("project_manager", "Xuất hồ sơ",
                      "Đóng gói và lưu phiên bản đã đối chiếu.", "draft_files final_review",
                      "Có danh sách tệp đã xuất và dữ liệu gốc của phiên bản lưu."),
}


def stage_spec(stage: str, state: dict | None = None) -> Stage:
    """Mô tả task của bước. Agent tùy biến (mã custom_…) lấy từ bản chụp cấu hình của lượt."""
    if stage in STAGES:
        return STAGES[stage]
    settings = (state or {}).get("agent_settings") or agent_settings.current()
    custom = agent_settings.custom_agent(stage, settings) or agent_settings.custom_agent(stage, agent_settings.load())
    if custom is None:
        raise KeyError(stage)
    after = agent_settings.STAGE_LABELS.get(custom["after"], custom["after"])
    return Stage(stage, custom["name"],
                 (custom.get("role") or "Agent tùy biến") + f" · nhận xét sau bước {after}.",
                 " ".join(custom["inputs"]),
                 "Có nhận xét do model lập, bám dữ liệu được chọn và không mâu thuẫn số liệu của agent lõi.")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, agent_id TEXT NOT NULL, stage TEXT NOT NULL,
    name TEXT NOT NULL, description TEXT NOT NULL, acceptance_criteria TEXT NOT NULL, UNIQUE(run_id, stage)
);
CREATE TABLE IF NOT EXISTS task_attempts (
    attempt_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id), execution_id TEXT NOT NULL,
    attempt_no INTEGER NOT NULL, status TEXT NOT NULL, processed INTEGER NOT NULL DEFAULT 0, acceptance TEXT,
    assigned_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, approval_requested_at TEXT, decision_at TEXT,
    approval_version TEXT,
    wait_s REAL, processing_s REAL, input_json TEXT NOT NULL, output_json TEXT,
    input_version TEXT, output_version TEXT, summary TEXT, error TEXT, failure_category TEXT,
    retry_reason TEXT, retry_category TEXT, model TEXT, tokens INTEGER, call_count INTEGER,
    api_errors INTEGER, cost_usd REAL, cost_basis TEXT, rubric_json TEXT, UNIQUE(task_id, attempt_no)
);
CREATE INDEX IF NOT EXISTS task_attempt_execution ON task_attempts(task_id, execution_id, attempt_no);
"""


def _init_schema() -> None:
    with events._conn() as con:
        con.executescript(SCHEMA)
        if not any(row[1] == "rubric_json" for row in con.execute("PRAGMA table_info(task_attempts)")):
            con.execute("BEGIN IMMEDIATE")
            if not any(row[1] == "rubric_json" for row in con.execute("PRAGMA table_info(task_attempts)")):
                con.execute("ALTER TABLE task_attempts ADD COLUMN rubric_json TEXT")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _json(value) -> str:
    return json.dumps(redact(value), ensure_ascii=False, separators=(",", ":"))


def _version(state: dict) -> str | None:
    program = state.get("program") or {}
    revision = state.get("revision_id") or program.get("revision_id")
    if program.get("phuong_an") and program.get("option_version") is not None:
        return redact(f"{program['phuong_an']} · v{program['option_version']}" + (f" · {revision}" if revision else ""))
    return redact(revision) if revision else None


def _attempt(con, stage: str, execution_id: str, state: dict, *, start: bool) -> str | None:
    task_id = f"{state['run_id']}:{stage}"
    spec = stage_spec(stage, state)
    previous = con.execute(
        "SELECT attempt_no, failure_category FROM task_attempts WHERE task_id=? ORDER BY attempt_no DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    same = con.execute(
        "SELECT attempt_id, status, assigned_at FROM task_attempts WHERE task_id=? AND execution_id=? "
        "ORDER BY attempt_no DESC LIMIT 1", (task_id, execution_id),
    ).fetchone()
    now = _now()
    if same:
        if not start:
            return None
        if same["status"] == "queued":
            wait = (datetime.fromisoformat(now) - datetime.fromisoformat(same["assigned_at"])).total_seconds()
            con.execute("UPDATE task_attempts SET status='running', started_at=?, wait_s=? WHERE attempt_id=?",
                        (now, max(0.0, wait), same["attempt_id"]))
            return same["attempt_id"]
        if same["status"] == "running":
            raise RuntimeError("Checkpoint đã có lần thực hiện đang chạy.")
    con.execute("INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(task_id) DO NOTHING",
                (task_id, state["run_id"], spec.agent, stage, spec.name, spec.description, spec.criteria))
    cause = state.get("task_retry") or {}
    reason = category = None
    if previous:
        reason = cause.get("reason") or ("Thực hiện lại từ checkpoint" if same else "Tạo lại đầu ra của bước")
        prior_category = previous["failure_category"]
        category = cause.get("category")
        if category in (None, "unknown"):
            category = prior_category or "unknown"
    attempt_id = uuid4().hex
    inputs = {key: state[key] for key in spec.inputs.split() if state.get(key) is not None}
    con.execute(
        """INSERT INTO task_attempts (attempt_id, task_id, execution_id, attempt_no, status, assigned_at,
           started_at, wait_s, input_json, input_version, retry_reason, retry_category, rubric_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (attempt_id, task_id, execution_id, previous["attempt_no"] + 1 if previous else 1,
         "running" if start else "queued", now, now if start else None, None,
         _json(inputs), _version(state), redact(reason), category, _json(rubrics.snapshot(stage, spec.criteria))),
    )
    return attempt_id


def queue_ready(state: dict, ready: Iterable[tuple[str, str]]) -> None:
    candidates = [(ident, name) for ident, name in ready if name in STAGES]
    if not state.get("run_id") or not candidates:
        return
    _init_schema()
    with events._conn() as con:
        con.row_factory = sqlite3.Row
        con.execute("BEGIN IMMEDIATE")
        for ident, name in candidates:
            _attempt(con, name, ident, state, start=False)


def stream_tracked(graph, inputs, config):
    """Đọc bước sẵn sàng từ checkpoint chính thức của LangGraph trước khi chạy."""
    with closing(graph.stream(inputs, config, stream_mode=["checkpoints", "updates"], durability="sync")) as stream:
        for kind, data in stream:
            if kind == "checkpoints":
                queue_ready(data["values"], ((item["id"], item["name"]) for item in data["tasks"]))
            yield kind, data


def track_stage(stage: str, fn):
    def run(state: dict) -> dict:
        if not (run_id := state.get("run_id")):
            return fn(state)
        namespace = get_config()["metadata"]["langgraph_checkpoint_ns"]
        execution_id = namespace.rsplit(":", 1)[1]
        _init_schema()
        with events._conn() as con:
            con.row_factory = sqlite3.Row
            con.execute("BEGIN IMMEDIATE")
            attempt_id = _attempt(con, stage, execution_id, state, start=True)
        usage = AttemptUsage()
        usage_token = current_usage.set(usage)
        run_token = current_run.set(run_id)
        agent_token = current_agent.set(stage_spec(stage, state).agent)
        event_token = events.current_attempt.set(attempt_id)
        settings_token = agent_settings.run_settings.set(state.get("agent_settings"))
        started = time.perf_counter()
        try:
            result = fn(state) or {}
        except Exception as error:
            _finish(attempt_id, started, usage, error=error)
            if redact(str(error)) != str(error):
                raise RuntimeError(error_text(error)) from None
            raise
        else:
            _finish(attempt_id, started, usage, result=result)
            return result
        finally:
            agent_settings.run_settings.reset(settings_token)
            events.current_attempt.reset(event_token)
            current_agent.reset(agent_token)
            current_run.reset(run_token)
            current_usage.reset(usage_token)

    return run


def _finish(attempt_id: str, started: float, usage: AttemptUsage, *, result: dict | None = None,
            error: Exception | None = None) -> None:
    fields = usage.snapshot()
    fields.update(finished_at=_now(), processing_s=time.perf_counter() - started)
    if error is not None:
        fields.update(status="error", error=error_text(error), failure_category=error_category(error))
    else:
        result = result or {}
        history = result.get("history") or [{}]
        output = {k: v for k, v in result.items() if k not in ("history", "log", "events", "versions", "task_retry")}
        if history[-1].get("output") is not None:
            output["chi_tiet_agent"] = history[-1]["output"]
        failure = ("missing_input" if result.get("outcome") == "needs_input" else
                   "infrastructure" if usage.calls and usage.calls == usage.api_errors else None)
        fields.update(status="completed", processed=1, summary=redact(history[-1].get("summary")),
                      output_json=_json(output), output_version=_version(result), failure_category=failure)
    with events._conn() as con:
        con.execute(f"UPDATE task_attempts SET {', '.join(f'{key}=?' for key in fields)} "
                    "WHERE attempt_id=? AND status='running'", (*fields.values(), attempt_id))


def approval_pending(state: dict, stage: str) -> None:
    _init_schema()
    task_id = f"{state['run_id']}:{stage}"
    with events._conn() as con:
        con.execute(
            """UPDATE task_attempts SET status='awaiting_approval', acceptance='pending', approval_requested_at=?,
                      approval_version=?
               WHERE task_id=? AND status='completed' AND acceptance IS NULL
                 AND attempt_no=(SELECT MAX(attempt_no) FROM task_attempts WHERE task_id=?)""",
            (_now(), _version(state), task_id, task_id),
        )


def approval_decided(state: dict, stage: str, decision: str) -> None:
    with events._conn() as con:
        con.execute("UPDATE task_attempts SET status=?, acceptance=?, decision_at=?, "
                    "approval_version=COALESCE(?, approval_version) WHERE task_id=? AND status='awaiting_approval'",
                    ("canceled" if decision == "canceled" else "completed", decision, _now(), _version(state),
                     f"{state['run_id']}:{stage}"))


def cancel_open(run_id: str, reason: str) -> None:
    _init_schema()
    now = _now()
    with events._conn() as con:
        con.execute(
            """UPDATE task_attempts SET status='canceled', finished_at=COALESCE(finished_at, ?),
               decision_at=CASE WHEN acceptance='pending' THEN ? ELSE decision_at END,
               wait_s=COALESCE(wait_s, MAX(0, (julianday(?) - julianday(assigned_at)) * 86400)),
               acceptance=CASE WHEN acceptance='pending' THEN 'canceled' ELSE acceptance END,
               error=COALESCE(error, ?) WHERE task_id IN (SELECT task_id FROM tasks WHERE run_id=?)
               AND status IN ('queued', 'awaiting_approval')""",
            (now, now, now, reason, run_id),
        )


def list_tasks(run_id: str, *, agent: str | None = None, status: str | None = None) -> list[dict]:
    _init_schema()
    with events._conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT t.*, a.status, a.processed, a.acceptance, a.assigned_at, a.input_version, a.output_version,
                      a.attempt_no, a.call_count, a.tokens, a.cost_usd, a.cost_basis, a.processing_s, a.wait_s
               FROM tasks t JOIN task_attempts a ON a.task_id=t.task_id
                 AND a.attempt_no=(SELECT MAX(h.attempt_no) FROM task_attempts h WHERE h.task_id=t.task_id)
               WHERE t.run_id=? AND (? IS NULL OR t.agent_id=?) AND (? IS NULL OR a.status=?)
               ORDER BY a.assigned_at, t.stage""", (run_id, agent, agent, status, status),
        )
        return [dict(row) for row in rows]


def attempts(task_id: str) -> list[dict]:
    _init_schema()
    with events._conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM task_attempts WHERE task_id=? ORDER BY attempt_no DESC", (task_id,))
        return [_decode_attempt(row) for row in rows]


def _decode_attempt(row: sqlite3.Row) -> dict:
    attempt = dict(row)
    attempt["input"] = json.loads(attempt.pop("input_json"))
    output = attempt.pop("output_json")
    attempt["output"] = json.loads(output) if output is not None else None
    rubric = attempt.pop("rubric_json", None)
    attempt["rubric"] = json.loads(rubric) if rubric else None
    return attempt


def timeline_attempts(run_id: str) -> list[dict]:
    """Đọc toàn bộ lần thực hiện của lượt, bỏ qua JSON hồ sơ lớn trên biểu đồ."""
    _init_schema()
    with events._conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT t.name, t.agent_id, t.stage, a.attempt_id, a.attempt_no, a.status, a.assigned_at,
                      a.started_at, a.finished_at, a.approval_requested_at, a.decision_at, a.acceptance, a.retry_reason,
                      CASE WHEN t.stage='coordinate_repair' THEN json_extract(a.output_json, '$.iteration')
                           END AS repair_iteration
               FROM tasks t JOIN task_attempts a ON a.task_id=t.task_id
               WHERE t.run_id=?
               ORDER BY a.assigned_at, a.attempt_no""", (run_id,),
        )
        return [dict(row) for row in rows]


def find_attempt(run_id: str, attempt_id: str) -> dict | None:
    _init_schema()
    with events._conn() as con:
        con.row_factory = sqlite3.Row
        return _find_attempt(con, run_id, attempt_id)


def _find_attempt(con: sqlite3.Connection, run_id: str, attempt_id: str) -> dict | None:
    row = con.execute(
        """SELECT t.name, t.agent_id, t.stage, a.* FROM task_attempts a JOIN tasks t ON t.task_id=a.task_id
           WHERE t.run_id=? AND a.attempt_id=?""", (run_id, attempt_id),
    ).fetchone()
    return _decode_attempt(row) if row is not None else None
