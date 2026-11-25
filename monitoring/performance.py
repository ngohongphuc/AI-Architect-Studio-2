"""Tổng hợp theo task và các lần thực hiện đã lưu, độc lập với workflow."""
from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from math import fsum, isfinite
from statistics import mean, median

from config import AGENT_ORDER
from monitoring import events, task_reviews, tasks
from monitoring.redaction import redact

UNRECORDED_MODEL = "__unrecorded__"
METRICS = {
    "assigned": ("Task đã giao", "Đếm task khác nhau có lần giao đầu tiên trong phạm vi lọc."),
    "completed": ("Đã xử lý", "Đếm task có ít nhất một lần hoàn thành xử lý."),
    "accepted": ("Được nghiệm thu", "Đếm task có ít nhất một lần được nghiệm thu."),
    "scored": ("Đã chấm đủ", "Đếm task có ít nhất một lần có bản đánh giá mới nhất chấm đủ tiêu chí áp dụng."),
    "quality": ("Điểm chất lượng TB", "Trung bình điểm gốc của lần cuối được nghiệm thu mỗi task. Bước chạy tự động "
                "(không có điểm duyệt) dùng lần cuối đã xử lý mà workflow đã chuyển tiếp. Chỉ lấy lần đó nếu bản đánh giá "
                "mới nhất đã chấm đủ. Hiển thị điểm tối đa trung bình của cùng mẫu."),
    "first_pass": ("Đạt lần đầu", "Task nghiệm thu ở lần số 1 chia cho toàn bộ task đã giao. Task chưa nghiệm thu không được tính đạt."),
    "completion": ("Tỷ lệ hoàn thành", "Task đã xử lý chia cho toàn bộ task đã giao."),
    "repairs": ("Sửa do lỗi agent", "Đếm lần chạy lại được xác nhận do lỗi chính agent này, "
                "có bằng chứng trong bản đánh giá mới nhất của lần chạy lại."),
    "processing": ("Trung vị xử lý", "Trung vị thời gian xử lý của các lần có số liệu. Mẫu số là số lần có số liệu xử lý."),
    "waiting": ("Trung vị chờ", "Trung vị thời gian chờ trước xử lý hoặc trước khi bị hủy. Chỉ dùng lần có thời gian chờ lưu."),
    "tokens": ("Token", "Tổng token đã ghi của toàn bộ lần thực hiện thuộc task được lọc. Công bố phần có dữ liệu."),
    "cost": ("Chi phí model", "Tổng USD đã ghi của toàn bộ lần thực hiện thuộc task được lọc. "
             "Công bố phần có dữ liệu và đánh dấu khoản ước tính."),
    "unit_cost": ("Chi phí/task nghiệm thu", "Tổng chi phí mọi lần thử và sửa của các task đã nghiệm thu, "
                  "chia cho số task đó. Cần biết chi phí của mọi lần đã bắt đầu trong nhóm."),
}


@dataclass(frozen=True)
class Task:
    id: str
    run: str
    agent: str
    stage: str
    name: str
    attempts: tuple[dict, ...]

    @property
    def first(self) -> dict:
        return self.attempts[0]

    @property
    def accepted(self) -> dict | None:
        return next((row for row in reversed(self.attempts) if row["acceptance"] == "accepted"), None)

    @property
    def final(self) -> dict | None:
        """Lần dùng để tính điểm chất lượng: lần cuối được nghiệm thu, hoặc với bước chạy tự động
        (không mời duyệt, chưa có quyết định) là lần cuối đã xử lý mà workflow đã chuyển tiếp."""
        if (accepted := self.accepted) is not None:
            return accepted
        last = self.attempts[-1]
        if last["processed"] and last["acceptance"] is None and not last.get("approval_requested_at"):
            return last
        return None

    @property
    def models(self) -> set[str]:
        return {model for row in self.attempts if row.get("model") for model in row["model"].split(" · ")}


@dataclass(frozen=True)
class Metric:
    value: int | float | None
    task_ids: tuple[str, ...]
    assessed: int
    population: int
    scale: float | None = None
    estimated: bool = False


def load(data_source: str) -> list[Task]:
    if data_source not in events.SOURCES:
        raise ValueError("Nguồn dữ liệu hiệu suất không hợp lệ.")
    events.init_db()
    tasks._init_schema()
    task_reviews._init_schema()
    grouped: dict[str, list[dict]] = {}
    with events._conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT t.task_id, t.run_id, t.agent_id, t.stage, t.name,
                   a.attempt_id, a.attempt_no, a.assigned_at, a.started_at, a.decision_at, a.status, a.processed,
                   a.approval_requested_at, a.finished_at,
                   a.acceptance, a.processing_s, a.wait_s, a.tokens, a.cost_usd, a.cost_basis, a.call_count,
                   a.model, a.input_version, a.output_version, a.retry_category,
                   r.agent_fault_confirmed, r.agent_fault_evidence, r.reviewer, r.created_at AS reviewed_at,
                   json_extract(r.score_json, '$.status') AS score_status,
                   json_extract(r.score_json, '$.total.earned') AS earned,
                   json_extract(r.score_json, '$.total.applicable') AS applicable
            FROM tasks t JOIN runs run ON run.run_id=t.run_id
            JOIN task_attempts a ON a.task_id=t.task_id
            LEFT JOIN task_reviews r ON r.attempt_id=a.attempt_id AND r.revision=(
                SELECT MAX(h.revision) FROM task_reviews h WHERE h.attempt_id=a.attempt_id
            )
            WHERE run.data_source=? ORDER BY t.task_id, a.attempt_no
        """, (data_source,))
        for row in rows:
            grouped.setdefault(row["task_id"], []).append(dict(row))
    return [Task(ident, items[0]["run_id"], items[0]["agent_id"], items[0]["stage"], items[0]["name"], tuple(items))
            for ident, items in grouped.items()]


def local_day(stamp: str | None) -> date | None:
    if stamp:
        try:
            return datetime.fromisoformat(stamp).astimezone().date()
        except ValueError:
            pass
    return None


def filter_tasks(data: list[Task], *, start: date | None = None, end: date | None = None,
                 run: str = "", agent: str = "", stage: str = "", model: str = "") -> list[Task]:
    selected = []
    for item in data:
        if (run and item.run != run) or (agent and item.agent != agent) or (stage and item.stage != stage):
            continue
        if model == UNRECORDED_MODEL and item.models:
            continue
        if model and model != UNRECORDED_MODEL and model not in item.models:
            continue
        if start is not None or end is not None:
            day = local_day(item.first["assigned_at"])
            if day is None or (start is not None and day < start) or (end is not None and day > end):
                continue
        selected.append(item)
    return selected


def valid_number(value) -> bool:
    return type(value) in (int, float) and isfinite(value) and value >= 0


def complete_grade(row: dict | None) -> bool:
    return (row is not None and row.get("score_status") == "complete"
            and valid_number(row.get("earned")) and valid_number(row.get("applicable"))
            and 0 < row["applicable"] and row["earned"] <= row["applicable"])


def fault_confirmed(row: dict) -> bool:
    return (task_reviews.can_confirm_fault(row) and bool(row.get("agent_fault_confirmed"))
            and bool((row.get("agent_fault_evidence") or "").strip()))


def used_resources(row: dict) -> bool:
    return bool(row["started_at"] or row["processed"] or row.get("call_count")
                or valid_number(row.get("tokens")) or valid_number(row.get("cost_usd")))


def summarize(data: list[Task]) -> dict[str, Metric]:
    ids = tuple(item.id for item in data)
    total = len(data)
    completed = tuple(item.id for item in data if any(row["processed"] for row in item.attempts))
    accepted = {item.id: row for item in data if (row := item.accepted) is not None}
    scored = tuple(item.id for item in data if any(complete_grade(row) for row in item.attempts))
    first = sum(item.first["attempt_no"] == 1 and item.first["acceptance"] == "accepted" for item in data)
    finals = {item.id: row for item in data if (row := item.final) is not None}
    scored_accepted = {ident: row for ident, row in finals.items() if complete_grade(row)}
    repairs = [(item.id, row) for item in data for row in item.attempts if fault_confirmed(row)]
    all_attempts = [(item.id, row) for item in data for row in item.attempts]
    used = [(ident, row) for ident, row in all_attempts if used_resources(row)]

    def count(matches: tuple[str, ...]) -> Metric:
        return Metric(len(matches) if total else None, matches, len(matches), total)

    def measured(column: str, sample: list[tuple[str, dict]], combine) -> Metric:
        values = [(ident, row) for ident, row in sample if valid_number(row.get(column))]
        return Metric(combine(row[column] for _, row in values) if values else None,
                      tuple(dict.fromkeys(ident for ident, _ in sample)), len(values), len(sample),
                      estimated=column == "cost_usd" and any(row.get("cost_basis") == "estimated" for _, row in values))

    quality_count = len(scored_accepted)
    total_by_accepted = measured("cost_usd", [(ident, row) for ident, row in used if ident in accepted], fsum)
    unit = (total_by_accepted.value / len(accepted) if accepted and total_by_accepted.value is not None
            and total_by_accepted.assessed == total_by_accepted.population else None)
    if unit is not None and not set(accepted).issubset(total_by_accepted.task_ids):
        unit = None
    return {
        "assigned": Metric(total if total else None, ids, total, total),
        "completed": count(completed),
        "accepted": count(tuple(accepted)),
        "scored": count(scored),
        "quality": Metric(mean(row["earned"] for row in scored_accepted.values()) if quality_count else None,
                          tuple(scored_accepted), quality_count, len(finals),
                          mean(row["applicable"] for row in scored_accepted.values()) if quality_count else None),
        "first_pass": Metric(first / total if total else None, ids, first, total),
        "completion": Metric(len(completed) / total if total else None, ids, len(completed), total),
        "repairs": Metric(len(repairs) if total else None, tuple(dict.fromkeys(ident for ident, _ in repairs)),
                          len(repairs), sum(row["attempt_no"] > 1 for _, row in all_attempts)),
        "processing": measured("processing_s", used, median),
        "waiting": measured("wait_s", all_attempts, median),
        "tokens": measured("tokens", used, sum),
        "cost": measured("cost_usd", used, fsum),
        "unit_cost": Metric(unit, tuple(accepted), total_by_accepted.assessed, total_by_accepted.population,
                            estimated=total_by_accepted.estimated),
    }


def by_agent(data: list[Task]) -> dict[str, dict[str, Metric]]:
    return {agent: summarize([item for item in data if item.agent == agent]) for agent in AGENT_ORDER}


def quality_series(data: list[Task]) -> list[dict]:
    groups: dict[tuple[str, date], list[dict]] = {}
    for item in data:
        attempt = item.final
        if complete_grade(attempt) and (day := local_day(attempt["decision_at"] or attempt.get("finished_at"))) is not None:
            groups.setdefault((item.agent, day), []).append(attempt)
    return [{"agent": agent, "day": day.isoformat(), "earned": mean(row["earned"] for row in rows),
             "applicable": mean(row["applicable"] for row in rows), "tasks": len(rows)}
            for (agent, day), rows in sorted(groups.items())]


CSV_COLUMNS = ("data_source", "run_id", "agent_id", "stage", "task_id", "attempt_id", "attempt_no", "assigned_at",
               "started_at", "decision_at", "status", "processed", "acceptance", "input_version", "output_version",
               "score_status", "earned", "applicable", "retry_category", "agent_fault_confirmed", "processing_s",
               "wait_s", "model", "tokens", "cost_usd", "cost_basis")


def csv_export(data: list[Task], data_source: str) -> bytes:
    destination = io.StringIO()
    writer = csv.writer(destination)
    writer.writerow(CSV_COLUMNS)

    def safe(value):
        if not isinstance(value, str):
            return value
        value = redact(value)
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value

    for item in data:
        for attempt in item.attempts:
            row = {**attempt, "data_source": data_source, "run_id": item.run, "agent_id": item.agent,
                   "stage": item.stage, "task_id": item.id, "agent_fault_confirmed": int(fault_confirmed(attempt))}
            writer.writerow([safe(row.get(key)) for key in CSV_COLUMNS])
    return destination.getvalue().encode("utf-8-sig")
