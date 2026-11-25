"""Nhập / thay / gỡ khóa API của nhà cung cấp LLM từ giao diện.

Khóa được ghi vào tệp `.env` ở thư mục dự án (đã nằm trong .gitignore, quyền 600) và nạp ngay vào
biến môi trường của tiến trình, nên dùng được luôn mà không cần khởi động lại. Giao diện không bao giờ
hiển thị lại khóa, chỉ hiện 4 ký tự cuối.
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

from config import ROOT

ENV_FILE = ROOT / ".env"
_KEY_VALUE = re.compile(r"^[A-Za-z0-9._\-]{16,256}$")
_lock = threading.Lock()


def key_env(provider: str) -> str | None:
    from llm import PROVIDERS

    return PROVIDERS.get(provider, (None, None, None, None))[2]


def _env_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _in_file(name: str, path: Path) -> bool:
    return any(re.match(rf"^\s*{re.escape(name)}\s*=", line) for line in _env_lines(path))


def status(provider: str) -> dict:
    """{env, set, hint, source} – không trả giá trị khóa."""
    name = key_env(provider)
    if not name:
        return {"env": None, "set": True, "hint": "", "source": "Không cần khóa"}
    value = os.getenv(name, "").strip()
    if not value:
        return {"env": name, "set": False, "hint": "", "source": "Chưa có"}
    source = ".env" if _in_file(name, ENV_FILE) else "Biến môi trường hệ thống"
    return {"env": name, "set": True, "hint": f"…{value[-4:]}" if len(value) >= 12 else "", "source": source}


def _write(name: str, value: str | None) -> None:
    """Thay dòng `name=` trong .env (hoặc thêm vào cuối); value None = gỡ dòng. Giữ nguyên các dòng khác."""
    lines = _env_lines(ENV_FILE)
    pattern = re.compile(rf"^\s*{re.escape(name)}\s*=")
    out, done = [], False
    for line in lines:
        if pattern.match(line):
            if value is not None and not done:
                out.append(f"{name}={value}")
                done = True
            continue
        out.append(line)
    if value is not None and not done:
        out.append(f"{name}={value}")
    tmp = ENV_FILE.with_name(".env.tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV_FILE)


def _refresh(provider: str) -> None:
    import llm

    llm._build.cache_clear()   # client cũ giữ khóa cũ
    llm._exhausted.difference_update({item for item in llm._exhausted if item[0] == provider})


def set_key(provider: str, value: str) -> None:
    name = key_env(provider)
    if not name:
        raise ValueError("Nhà cung cấp này không dùng khóa API")
    value = (value or "").strip().strip('"').strip("'")
    if not _KEY_VALUE.fullmatch(value):
        raise ValueError("Khóa API không hợp lệ: 16–256 ký tự, không có dấu cách (chữ, số, . _ -).")
    with _lock:
        _write(name, value)
        os.environ[name] = value
        _refresh(provider)


def list_models(provider: str, timeout_s: float = 20.0) -> list[str]:
    """Danh sách model chat mà khóa hiện tại dùng được (Gemini, OpenAI). Lỗi → ValueError có lời giải thích."""
    import concurrent.futures

    from monitoring.redaction import redact

    name = key_env(provider)
    if provider not in ("gemini", "openai"):
        raise ValueError("Chỉ tải được danh sách model của Gemini và OpenAI.")
    if not os.getenv(name or "", "").strip():
        raise ValueError(f"Chưa có {name}. Lưu khóa trước khi tải danh sách model.")

    def fetch() -> list[str]:
        if provider == "gemini":
            from google import genai

            client = genai.Client(api_key=os.environ[name])
            return sorted(m.name.removeprefix("models/") for m in client.models.list()
                          if "generateContent" in (m.supported_actions or []) and "gemini" in (m.name or ""))
        from openai import OpenAI

        client = OpenAI(api_key=os.environ[name], max_retries=0)
        skip = ("embedding", "whisper", "tts", "dall-e", "image", "audio", "realtime", "moderation", "transcribe", "search")
        return sorted(m.id for m in client.models.list() if not any(word in m.id for word in skip))

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(fetch).result(timeout=timeout_s)
    except concurrent.futures.TimeoutError:
        raise ValueError(f"Quá {timeout_s:.0f} giây chưa có phản hồi.") from None
    except ImportError:
        raise ValueError("Chưa cài thư viện kết nối của nhà cung cấp này.") from None
    except Exception as error:  # noqa: BLE001
        text = f"{type(error).__name__} {error}".lower()
        if any(k in text for k in ("401", "403", "api key", "api_key", "permission", "unauthenticated", "invalid")):
            raise ValueError("Khóa API không hợp lệ hoặc không có quyền.") from None
        detail = redact(str(error)).strip().splitlines()[0][:160] if str(error).strip() else type(error).__name__
        raise ValueError(f"Không tải được danh sách model: {detail}") from None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def remove_key(provider: str) -> bool:
    """Gỡ khóa khỏi .env và tiến trình. Khóa đặt ở biến môi trường hệ thống thì chỉ gỡ khỏi tiến trình hiện tại."""
    name = key_env(provider)
    if not name:
        return False
    with _lock:
        had = _in_file(name, ENV_FILE)
        if had:
            _write(name, None)
        removed = os.environ.pop(name, None) is not None
        _refresh(provider)
    return had or removed
