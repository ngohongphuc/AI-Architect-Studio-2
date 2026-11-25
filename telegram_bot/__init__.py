"""Bật/tắt bot Telegram cùng ứng dụng web và quản lý cấu hình (token, tài khoản được phép) trong `.env`."""
from __future__ import annotations

import os
import re
import sys
import threading
import types

TOKEN, ALLOWED = "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS"
_TOKEN_VALUE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,60}$")
_GENERATION = object()       # đổi khi Streamlit nạp lại mã nguồn

# Giữ bot ngoài module này để việc nạp lại mã không tạo hai bot cùng nhận tin.
_holder = sys.modules.setdefault("_ai_architect_telegram", types.ModuleType("_ai_architect_telegram"))
if not hasattr(_holder, "lock"):
    _holder.lock, _holder.bot, _holder.generation = threading.RLock(), None, None


def token() -> str:
    return os.getenv(TOKEN, "").strip()


def allowed_users() -> set[int]:
    return {int(item) for item in re.split(r"[,\s]+", os.getenv(ALLOWED, "")) if item.isdigit()}


def ensure_started() -> None:
    """Gọi ở mỗi lần vẽ trang: chỉ khởi động khi có token và chưa có bot của bản mã hiện tại."""
    with _holder.lock:
        if _holder.bot is not None and _holder.generation is not _GENERATION:
            _holder.bot.stop()
            _holder.bot = None
        if _holder.bot is None and token():
            from telegram_bot.api import Client
            from telegram_bot.bot import Bot

            _holder.bot, _holder.generation = Bot(Client(token()), allowed_users), _GENERATION
            _holder.bot.start()


def shutdown() -> None:
    with _holder.lock:
        if _holder.bot is not None:
            _holder.bot.stop()
            _holder.bot = None


def status() -> dict:
    bot = _holder.bot
    if bot is None:
        return {"state": "off", "detail": "", "username": "", "pending": {}}
    return {"state": bot.state, "detail": bot.detail, "username": bot.username, "pending": dict(bot.pending)}


def _store(name: str, value: str | None) -> None:
    import api_keys

    with api_keys._lock:
        api_keys._write(name, value)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def save_token(value: str) -> str:
    """Kiểm tra token với Telegram rồi mới lưu; trả tên bot."""
    from telegram_bot.api import Client, TelegramError

    value = (value or "").strip()
    if not _TOKEN_VALUE.fullmatch(value):
        raise ValueError("Token không đúng dạng. Token của BotFather có dạng 123456789:ABC…")
    try:
        username = Client(value).call("getMe").get("username", "")
    except TelegramError as error:
        raise ValueError("Telegram từ chối token này." if error.code in (401, 404)
                         else "Không kết nối được Telegram, chưa lưu token.") from None
    _store(TOKEN, value)
    shutdown()
    ensure_started()
    return username


def remove_token() -> None:
    shutdown()
    _store(TOKEN, None)


def set_allowed(users: set[int]) -> None:
    _store(ALLOWED, ",".join(map(str, sorted(users))) or None)


def allow(user: int) -> None:
    set_allowed(allowed_users() | {user})
    if _holder.bot is not None:
        _holder.bot.pending.pop(user, None)
        try:
            _holder.bot.client.send(user, "Bạn đã được phép dùng bot. Gửi /help để xem hướng dẫn.")
        except Exception:  # noqa: BLE001  – lời chào không gửi được thì quyền vẫn có hiệu lực
            pass


def revoke(user: int) -> None:
    set_allowed(allowed_users() - {user})
