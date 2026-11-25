"""Phát hiện hai ứng dụng cùng chạy trên một dữ liệu, hoặc ứng dụng còn giữ mã cũ sau khi mã nguồn thay đổi."""
from __future__ import annotations

import os
import sys
import threading
import types
from pathlib import Path

from config import LOG_DB, ROOT

try:
    import fcntl
except ImportError:          # Windows: không có khóa tệp kiểu này, chỉ dùng phần phát hiện mã cũ
    fcntl = None

# Giữ ngoài module này để khóa còn nguyên khi Streamlit nạp lại mã.
_holder = sys.modules.setdefault("_ai_architect_guard", types.ModuleType("_ai_architect_guard"))
if not hasattr(_holder, "lock"):
    _holder.lock, _holder.file, _holder.seen = threading.Lock(), None, {}


def other_instance() -> str:
    """Mã tiến trình của ứng dụng khác đang giữ dữ liệu này; rỗng nếu đây là ứng dụng chính."""
    if fcntl is None:
        return ""
    with _holder.lock:
        if _holder.file is not None:
            return ""
        path = LOG_DB.with_name("app.lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.seek(0)
            owner = handle.read().strip()
            handle.close()
            return owner if owner.isdigit() else "không rõ"
        handle.truncate(0)
        handle.write(str(os.getpid()))
        handle.flush()
        _holder.file = handle          # hệ điều hành tự nhả khóa khi tiến trình kết thúc
        return ""


def stale_modules() -> list[str]:
    """Tệp mã đã đổi trên đĩa nhưng tiến trình vẫn dùng bản nạp trước đó."""
    changed = []
    for module in list(sys.modules.values()):
        source = getattr(module, "__file__", None)
        if not isinstance(source, str) or not source.endswith(".py"):
            continue
        path = Path(source)
        if not path.is_relative_to(ROOT) or any(part.startswith(".venv") for part in path.parts):
            continue
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            continue
        module_seen = _holder.seen.setdefault(str(path), (id(module), stamp))
        if module_seen[0] != id(module):
            _holder.seen[str(path)] = (id(module), stamp)
        elif module_seen[1] != stamp:
            changed.append(path.name)
    return sorted(changed)
