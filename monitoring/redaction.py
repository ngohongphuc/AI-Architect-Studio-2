"""Loại bỏ bí mật khỏi dữ liệu quan sát trước khi ghi hoặc hiển thị."""
from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping

_KEY = (r"(?:api[-_ ]?key|secret[-_ ]?access[-_ ]?key|(?:api|access|auth|refresh|session)[-_ ]?token|"
        r"token|authorization|password|secret|private[-_ ]?key|credentials)")
_FIELD = re.compile(rf"(?:^|[-_]){_KEY}$", re.I)
_INLINE = re.compile(rf"(\b(?:[\w-]+_)?{_KEY}\b[\"']?\s*[:=]\s*)(\[đã ẩn\]|\"[^\"]*\"|'[^']*'|[^\s,;}}\]]+)", re.I)
_TOKEN = re.compile(r"\b(?:Bearer\s+[^\s,;\"']+|sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{30,}|"
                    r"(?:ghp_|github_pat_)[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)", re.I)
_HIDDEN = "[đã ẩn]"


def redact(value):
    secrets = sorted({v.strip() for k, v in os.environ.items() if _FIELD.search(k) and len(v.strip()) >= 6},
                     key=len, reverse=True)

    def clean(item):
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, _HIDDEN)
            return _INLINE.sub(lambda match: match[1] + _HIDDEN, _TOKEN.sub(_HIDDEN, item))
        if isinstance(item, Mapping):
            return {clean(str(key)): _HIDDEN if _FIELD.search(str(key)) else clean(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(val) for val in item]
        if isinstance(item, float) and not math.isfinite(item):
            return None
        if item is None or isinstance(item, (int, float, bool)):
            return item
        return clean(str(item))

    return clean(value)


def error_category(error: Exception) -> str:
    name = type(error).__name__.lower()
    if isinstance(error, OSError) or any(part in name for part in (
            "apierror", "apistatus", "apiconnection", "timeout", "ratelimit", "authentication",
            "permissiondenied", "serviceunavailable", "resourceexhausted", "http", "connection")):
        return "infrastructure"
    return "agent_error"


def error_text(error: Exception) -> str:
    return redact(f"{type(error).__name__}: {error}")[:1500]
