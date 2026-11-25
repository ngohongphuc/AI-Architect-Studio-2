"""Lượt thiết kế giao qua Telegram: ai giao, đã báo tới đâu. Lưu cùng cơ sở dữ liệu theo dõi."""
from __future__ import annotations

from monitoring import events

SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_state (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS telegram_runs (
    run_id TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, progress_message INTEGER, notified TEXT NOT NULL DEFAULT '',
    created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS telegram_chats (chat_id INTEGER PRIMARY KEY, run_id TEXT);
"""


def _query(sql: str, args: tuple = ()) -> list[tuple]:
    with events._lock, events._conn() as con:
        con.executescript(SCHEMA)
        return con.execute(sql, args).fetchall()


def offset() -> int | None:
    rows = _query("SELECT value FROM telegram_state WHERE key='offset'")
    return int(rows[0][0]) if rows else None


def save_offset(value: int) -> None:
    _query("INSERT INTO telegram_state VALUES ('offset', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(value),))


def add_run(run_id: str, chat_id: int) -> None:
    _query("INSERT OR IGNORE INTO telegram_runs (run_id, chat_id) VALUES (?, ?)", (run_id, chat_id))
    select_run(chat_id, run_id)


def select_run(chat_id: int, run_id: str) -> None:
    _query("INSERT INTO telegram_chats VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET run_id=excluded.run_id", (chat_id, run_id))


def current_run(chat_id: int) -> str | None:
    rows = _query("SELECT run_id FROM telegram_chats WHERE chat_id=?", (chat_id,))
    return rows[0][0] if rows else None


def owns(chat_id: int, run_id: str) -> bool:
    return bool(_query("SELECT 1 FROM telegram_runs WHERE run_id=? AND chat_id=?", (run_id, chat_id)))


def runs(chat_id: int, limit: int = 8) -> list[str]:
    return [row[0] for row in _query("SELECT run_id FROM telegram_runs WHERE chat_id=? ORDER BY rowid DESC LIMIT ?",
                                     (chat_id, limit))]


def watched() -> list[dict]:
    """Lượt đang chọn của từng cuộc trò chuyện và các lượt chưa kết thúc."""
    rows = _query("SELECT r.run_id, r.chat_id, r.progress_message, r.notified FROM telegram_runs r "
                  "LEFT JOIN telegram_chats c ON c.run_id=r.run_id "
                  "WHERE c.run_id IS NOT NULL OR r.notified='' OR r.notified LIKE 'running%' "
                  "OR r.notified LIKE 'awaiting%' OR r.notified LIKE 'needs_input%' OR r.notified LIKE 'paused%'")
    return [dict(zip(("run_id", "chat_id", "progress_message", "notified"), row)) for row in rows]


def last_event(run_id: str) -> int:
    return _query("SELECT COALESCE(MAX(id), 0) FROM events WHERE run_id=?", (run_id,))[0][0]


def update(run_id: str, **fields) -> None:
    names = [name for name in ("progress_message", "notified") if name in fields]
    _query(f"UPDATE telegram_runs SET {', '.join(n + '=?' for n in names)} WHERE run_id=?",
           (*(fields[n] for n in names), run_id))
