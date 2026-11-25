"""Lưu các bản đánh giá chất lượng theo từng lần thực hiện, chỉ thêm bản ghi mới."""
import json
import sqlite3
from datetime import datetime, timezone

from monitoring import events, rubrics, tasks
from monitoring.redaction import redact


SCHEMA = """
CREATE TABLE IF NOT EXISTS task_reviews (
    submission_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES task_attempts(attempt_id),
    revision INTEGER NOT NULL,
    rubric_version TEXT NOT NULL,
    design_version TEXT,
    created_at TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reviewer_kind TEXT NOT NULL CHECK (reviewer_kind = 'self_declared'),
    manual_score INTEGER,
    manual_evidence TEXT NOT NULL,
    comment TEXT NOT NULL,
    agent_fault_confirmed INTEGER NOT NULL DEFAULT 0,
    agent_fault_evidence TEXT NOT NULL DEFAULT '',
    score_json TEXT NOT NULL,
    UNIQUE(attempt_id, revision)
);
"""


class ReviewConflict(ValueError):
    """Bản đang sửa không còn là bản mới nhất."""


def _init_schema() -> None:
    with events._conn() as con:
        con.executescript(SCHEMA)
        columns = {row[1] for row in con.execute("PRAGMA table_info(task_reviews)")}
        if {"agent_fault_confirmed", "agent_fault_evidence"} - columns:
            con.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in con.execute("PRAGMA table_info(task_reviews)")}
            if "agent_fault_confirmed" not in columns:
                con.execute("ALTER TABLE task_reviews ADD COLUMN agent_fault_confirmed INTEGER NOT NULL DEFAULT 0")
            if "agent_fault_evidence" not in columns:
                con.execute("ALTER TABLE task_reviews ADD COLUMN agent_fault_evidence TEXT NOT NULL DEFAULT ''")


def can_confirm_fault(attempt: dict) -> bool:
    return (attempt["attempt_no"] > 1 and attempt["status"] not in ("queued", "running")
            and attempt["retry_category"] in ("agent_error", "unknown"))


def _record(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["score"] = json.loads(data.pop("score_json"))
    return data


def history(run_id: str, attempt_id: str) -> list[dict]:
    tasks._init_schema()
    _init_schema()
    with events._conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT r.* FROM task_reviews r JOIN task_attempts a ON a.attempt_id=r.attempt_id
               JOIN tasks t ON t.task_id=a.task_id WHERE t.run_id=? AND r.attempt_id=?
               ORDER BY r.revision DESC""", (run_id, attempt_id),
        )
        return [_record(row) for row in rows]


def save(run_id: str, attempt_id: str, *, expected_revision: int, submission_id: str,
         reviewer: str, manual_score: int | None, manual_evidence: str = "", comment: str = "",
         agent_fault_confirmed: bool = False, agent_fault_evidence: str = "") -> dict:
    reviewer, manual_evidence, comment, fault_evidence = (redact(value.strip()) for value in (
        reviewer, manual_evidence, comment, agent_fault_evidence))
    if not reviewer or len(reviewer) > 80:
        raise ValueError("Nhập tên tự khai của người chấm, tối đa 80 ký tự.")
    if max(len(manual_evidence), len(comment), len(fault_evidence)) > 4000:
        raise ValueError("Mỗi mục bằng chứng và nhận xét giới hạn 4.000 ký tự.")
    if manual_score is not None and type(manual_score) is not int:
        raise ValueError("Điểm chuyên môn cần là số nguyên.")
    if not submission_id or len(submission_id) > 64:
        raise ValueError("Mã gửi đánh giá không hợp lệ.")

    tasks._init_schema()
    _init_schema()
    with events._conn() as con:
        con.row_factory = sqlite3.Row
        con.execute("BEGIN IMMEDIATE")
        attempt = tasks._find_attempt(con, run_id, attempt_id)
        if attempt is None or not attempt["rubric"]:
            raise ValueError("Không tìm thấy lần thực hiện có bộ tiêu chí đã giao.")
        same = con.execute("SELECT * FROM task_reviews WHERE submission_id=?", (submission_id,)).fetchone()
        if same is not None:
            if same["attempt_id"] != attempt_id:
                raise ValueError("Mã gửi thuộc lần thực hiện khác.")
            return _record(same)
        if attempt["status"] in ("queued", "running"):
            raise ValueError("Chờ lần thực hiện kết thúc xử lý trước khi lưu đánh giá.")
        if agent_fault_confirmed and (not can_confirm_fault(attempt) or not fault_evidence):
            raise ValueError("Chỉ xác nhận lỗi agent cho lần chạy lại phù hợp và có bằng chứng.")

        latest = con.execute("SELECT * FROM task_reviews WHERE attempt_id=? ORDER BY revision DESC LIMIT 1",
                             (attempt_id,)).fetchone()
        revision = latest["revision"] if latest is not None else 0
        if revision != expected_revision:
            raise ReviewConflict("Đã có bản đánh giá mới. Nạp bản mới nhất trước khi chỉnh sửa.")
        keys = ("reviewer", "manual_score", "manual_evidence", "comment", "agent_fault_confirmed", "agent_fault_evidence")
        form = (reviewer, manual_score, manual_evidence, comment, int(bool(agent_fault_confirmed)),
                fault_evidence if agent_fault_confirmed else "")
        if latest is not None and form == tuple(latest[key] for key in keys):
            return _record(latest)

        score = rubrics.evaluate(attempt, manual_score=manual_score, manual_evidence=manual_evidence)
        con.execute(
            """INSERT INTO task_reviews (submission_id, attempt_id, revision, rubric_version, design_version,
               created_at, reviewer, reviewer_kind, manual_score, manual_evidence, comment,
               agent_fault_confirmed, agent_fault_evidence, score_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'self_declared', ?, ?, ?, ?, ?, ?)""",
            (submission_id, attempt_id, revision + 1, score["rubric_version"],
             attempt["output_version"] or attempt["input_version"],
             datetime.now(timezone.utc).isoformat(timespec="milliseconds"), *form,
             json.dumps(redact(score), ensure_ascii=False, separators=(",", ":"))),
        )
        saved = con.execute("SELECT * FROM task_reviews WHERE submission_id=?", (submission_id,)).fetchone()
        return _record(saved)
