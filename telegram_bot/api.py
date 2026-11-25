"""Gọi Telegram Bot API. Token nằm trong URL nên lỗi chỉ giữ mã và mô tả của Telegram, không giữ URL."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import requests

BASE = "https://api.telegram.org"
TEXT_LIMIT = 4000                  # Telegram cho 4096 ký tự mỗi tin
FILE_LIMIT = 49 * 1024 * 1024      # bot gửi tệp tối đa 50 MB


class TelegramError(Exception):
    def __init__(self, code: int, description: str):
        super().__init__(f"{code} {description}")
        self.code, self.description = code, description


def split_text(text: str, limit: int = TEXT_LIMIT) -> list[str]:
    """Cắt tin dài theo dòng."""
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", limit // 2, limit)
        cut = cut if cut > 0 else limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return [*parts, text]


class Client:
    def __init__(self, token: str):
        self._token = token
        self._local = threading.local()      # mỗi luồng một phiên kết nối

    def call(self, method: str, data: dict | None = None, files: dict | None = None, timeout: float = 20.0):
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._local.session = requests.Session()
        payload = {k: json.dumps(v) if isinstance(v, (dict, list)) else v
                   for k, v in (data or {}).items() if v is not None}
        for attempt in (1, 2):
            try:
                body = session.post(f"{BASE}/bot{self._token}/{method}", data=payload, files=files,
                                    timeout=(10, timeout)).json()
            except (requests.RequestException, ValueError) as error:
                raise TelegramError(0, f"Không kết nối được Telegram ({type(error).__name__})") from None
            if body.get("ok"):
                return body["result"]
            wait = (body.get("parameters") or {}).get("retry_after")
            if wait and attempt == 1 and wait <= 30 and not files:
                time.sleep(wait)
                continue
            raise TelegramError(int(body.get("error_code") or 0), str(body.get("description") or ""))

    def send(self, chat_id: int, text: str, keyboard: list | None = None) -> int:
        """Gửi văn bản thuần (không diễn giải định dạng); trả mã tin cuối."""
        parts, message = split_text(text), None
        for index, part in enumerate(parts):
            markup = {"inline_keyboard": keyboard} if keyboard and index == len(parts) - 1 else None
            message = self.call("sendMessage", {"chat_id": chat_id, "text": part, "reply_markup": markup,
                                                "link_preview_options": {"is_disabled": True}})
        return message["message_id"]

    def edit(self, chat_id: int, message_id: int, text: str, keyboard: list | None = None) -> None:
        try:
            self.call("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text[:TEXT_LIMIT],
                                          "reply_markup": {"inline_keyboard": keyboard or []}})
        except TelegramError as error:
            if "not modified" not in error.description:
                raise

    def send_document(self, chat_id: int, path: Path, caption: str = "") -> None:
        with path.open("rb") as stream:
            self.call("sendDocument", {"chat_id": chat_id, "caption": caption[:1000]},
                      {"document": (path.name, stream)}, timeout=120)

    def send_photos(self, chat_id: int, items: list[tuple[Path, str]]) -> None:
        items = items[:10]
        if len(items) == 1:
            with items[0][0].open("rb") as stream:
                self.call("sendPhoto", {"chat_id": chat_id, "caption": items[0][1][:1000]},
                          {"photo": (items[0][0].name, stream)}, timeout=120)
            return
        if items:
            media = [{"type": "photo", "media": f"attach://p{i}", "caption": caption[:1000]}
                     for i, (_, caption) in enumerate(items)]
            files = {f"p{i}": (path.name, path.read_bytes()) for i, (path, _) in enumerate(items)}
            self.call("sendMediaGroup", {"chat_id": chat_id, "media": media}, files, timeout=180)
