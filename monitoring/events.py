"""Gửi / nhận AgentEvent: lưu vào SQLite (monitoring/logs.db) và phát cho listener trong bộ nhớ."""
from __future__ import annotations

import csv
import json
import sqlite3
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from config import AGENT_LABELS, LOG_DB
from monitoring.redaction import redact

_lock = threading.Lock()
_listeners: dict[str, list] = {}
current_attempt: ContextVar[str | None] = ContextVar("event_attempt", default=None)
SOURCES = ("live", "mock", "simulation")


@contextmanager
def _conn():
    LOG_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(LOG_DB, timeout=10)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        with con:
            yield con
    finally:
        con.close()


def init_db() -> None:
    with _lock, _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, created TEXT, request TEXT, status TEXT,
            output_dir TEXT, summary TEXT, updated TEXT, data_source TEXT NOT NULL DEFAULT 'live');
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, time TEXT, agent TEXT,
            status TEXT, to_agent TEXT, summary TEXT, tokens INTEGER, duration_s REAL,
            version INTEGER, feedback INTEGER, occurred_at TEXT, attempt_id TEXT);
        """)
        con.execute("BEGIN IMMEDIATE")
        run_columns = {column[1] for column in con.execute("PRAGMA table_info(runs)")}
        if "updated" not in run_columns:
            con.execute("ALTER TABLE runs ADD COLUMN updated TEXT")
        if "data_source" not in run_columns:
            con.execute("ALTER TABLE runs ADD COLUMN data_source TEXT NOT NULL DEFAULT 'live'")
        columns = {column[1] for column in con.execute("PRAGMA table_info(events)")}
        for column in ("occurred_at", "attempt_id"):
            if column not in columns:
                con.execute(f"ALTER TABLE events ADD COLUMN {column} TEXT")


def record_run(run_id: str, request: str, output_dir: str, summary: dict | None = None, *,
               data_source: str = "live") -> None:
    if data_source not in SOURCES:
        raise ValueError("Nguồn dữ liệu lượt thiết kế không hợp lệ.")
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _lock, _conn() as con:
        cursor = con.execute(
            "INSERT INTO runs (run_id, created, request, status, output_dir, summary, updated, data_source) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET request=excluded.request, "
            "status=excluded.status, output_dir=excluded.output_dir, summary=excluded.summary, updated=excluded.updated "
            "WHERE runs.data_source=excluded.data_source",
            (run_id, now, redact(request), "running", output_dir, json.dumps(redact(summary or {}), ensure_ascii=False),
             now, data_source),
        )
        if cursor.rowcount != 1:
            raise ValueError("Mã lượt đã được ghi trong nguồn dữ liệu khác.")


def update_run(run_id: str, status: str, summary: dict | None = None) -> None:
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with _lock, _conn() as con:
        if summary is not None:
            con.execute("UPDATE runs SET status=?, summary=?, updated=? WHERE run_id=?",
                        (status, json.dumps(redact(summary), ensure_ascii=False), now, run_id))
        else:
            con.execute("UPDATE runs SET status=?, updated=? WHERE run_id=?", (status, now, run_id))


def list_runs(limit: int | None = 50, *, recent_activity: bool = False, data_source: str = "live") -> list[dict]:
    init_db()
    order = "COALESCE(updated, created) DESC, created DESC, rowid DESC" if recent_activity else "created DESC, rowid DESC"
    with _lock, _conn() as con:
        rows = con.execute("SELECT run_id, created, request, status, output_dir, summary, updated FROM runs "
                           f"WHERE data_source=? ORDER BY {order} LIMIT ?", (data_source, limit if limit is not None else -1)).fetchall()
    return [{"run_id": r[0], "created": r[1], "request": r[2], "status": r[3], "output_dir": r[4],
             "summary": json.loads(r[5] or "{}"), "updated": r[6]} for r in rows]


def run_status(run_id: str) -> str | None:
    init_db()
    with _lock, _conn() as con:
        row = con.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
    return row[0] if row else None


def emit(run_id: str, event: dict) -> None:
    occurred = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    init_db()
    event = redact(event)
    with _lock, _conn() as con:
        con.execute("INSERT INTO events (run_id,time,agent,status,to_agent,summary,tokens,duration_s,version,feedback,"
                    "occurred_at,attempt_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, event.get("time"), event.get("agent"), event.get("status"), event.get("to_agent", ""),
                     event.get("summary", ""), event.get("tokens", 0), event.get("duration_s", 0.0),
                     event.get("version", 0), int(bool(event.get("feedback"))), occurred, current_attempt.get()))
        con.execute("UPDATE runs SET updated=? WHERE run_id=?", (datetime.now().isoformat(timespec="seconds"), run_id))
    for cb in list(_listeners.get(run_id, [])):
        try:
            cb(event)
        except Exception:  # noqa: BLE001
            pass


def get_events(run_id: str) -> list[dict]:
    init_db()
    with _lock, _conn() as con:
        rows = con.execute("SELECT id,time,agent,status,to_agent,summary,tokens,duration_s,version,feedback,occurred_at,attempt_id "
                           "FROM events WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
    keys = ["id", "time", "agent", "status", "to_agent", "summary", "tokens", "duration_s", "version", "feedback",
            "occurred_at", "attempt_id"]
    return [dict(zip(keys, r)) for r in rows]


def subscribe(run_id: str, callback) -> None:
    _listeners.setdefault(run_id, []).append(callback)


def export_timeline(run_id: str, path: Path) -> Path:
    """Xuất dòng thời gian (chỉ các sự kiện hoàn thành / lỗi) ra CSV để đưa vào báo cáo."""
    events = [e for e in get_events(run_id) if e["status"] in ("done", "error")]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Thời điểm", "Agent gửi", "Agent nhận", "Nội dung", "Trạng thái", "Lần chạy",
                    "Token", "Thời gian (s)", "Phản hồi lỗi"])
        for e in events:
            w.writerow([e["time"], AGENT_LABELS.get(e["agent"], e["agent"]),
                        AGENT_LABELS.get(e["to_agent"], e["to_agent"] or ""), e["summary"], e["status"],
                        e["version"], e["tokens"], e["duration_s"], "có" if e["feedback"] else ""])
    return path
