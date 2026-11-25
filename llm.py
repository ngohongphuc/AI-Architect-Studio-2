"""Kết nối mô hình ngôn ngữ qua LangChain (tùy chọn).

Đặt biến môi trường (hoặc file .env):
    LLM_PROVIDER = gemini | openai | anthropic | ollama | none
    LLM_MODEL    = tên model (không bắt buộc)
và API key tương ứng (GOOGLE_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY).

Khi không cấu hình hoặc gọi lỗi, các hàm trả về None và agent dùng phương án quy tắc
(rule-based) — mọi con số luôn được tính bằng Python nên kết quả vẫn đầy đủ.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import math
import os
from functools import lru_cache

import agent_settings
from config import AGENT_ORDER
from monitoring.redaction import error_category, redact
from monitoring.tracker import current_agent, tracker

log = logging.getLogger(__name__)

PROVIDERS = {
    "gemini": ("langchain_google_genai", "ChatGoogleGenerativeAI", "GOOGLE_API_KEY", "gemini-2.5-flash"),
    "openai": ("langchain_openai", "ChatOpenAI", "OPENAI_API_KEY", "gpt-6-luna"),
    "anthropic": ("langchain_anthropic", "ChatAnthropic", "ANTHROPIC_API_KEY", "claude-sonnet-5-5"),
    "ollama": ("langchain_ollama", "ChatOllama", None, "qwen2.5:7b"),
}


AGENTS = AGENT_ORDER


def _env(name: str, agent: str | None) -> str | None:
    """Đọc biến riêng của agent (vd. LLM_MODEL_ARCHITECT) trước, rồi mới tới biến chung (LLM_MODEL)."""
    if agent:
        v = os.getenv(f"{name}_{agent.upper()}")
        if v:
            return v.strip()
    v = os.getenv(name)
    return v.strip() if v else None


def env_config(agent: str | None = None) -> dict:
    """Cấu hình chỉ từ biến môi trường / .env (biến riêng của agent trước, rồi biến chung)."""
    if agent not in AGENTS:
        agent = None
    provider = (_env("LLM_PROVIDER", agent) or "none").lower()
    default_model = PROVIDERS.get(provider, (None, None, None, ""))[3]
    return {"agent": agent, "provider": provider, "model": _env("LLM_MODEL", agent) or default_model,
            # Model suy luận của OpenAI (GPT-5/6) không nhận temperature tùy ý -> chỉ gửi khi khai báo rõ
            "temperature": float(t) if (t := _env("LLM_TEMPERATURE", agent)) else (None if provider == "openai" else 0.3)}


def agent_config(agent: str | None = None) -> dict:
    """Cấu hình LLM của một agent: giao diện Quản lý agent → .env riêng của agent → .env chung."""
    agent = agent or current_agent.get()
    known = agent in AGENTS or agent_settings.custom_agent(agent) is not None
    if not known:
        agent = None
    override = agent_settings.model_override(agent) if known else {}
    base = env_config(agent)
    if not any(override.values()):
        return {**base, "agent": agent, "source": "env"}
    provider = override.get("provider") or base["provider"]
    if override.get("model"):
        model = override["model"]
    elif provider == base["provider"]:
        model = base["model"]
    else:   # đổi nhà cung cấp mà không ghi model -> model mặc định của nhà cung cấp mới
        model = PROVIDERS.get(provider, (None, None, None, ""))[3]
    # Temperature không chỉnh trên giao diện: giữ giá trị của .env khi cùng nhà cung cấp, nếu không thì mặc định.
    temperature = base["temperature"] if provider == base["provider"] else (None if provider == "openai" else 0.3)
    return {"agent": agent, "provider": provider, "model": model, "temperature": temperature, "source": "ui"}


def provider_name(agent: str | None = None) -> str:
    return agent_config(agent)["provider"]


@lru_cache(maxsize=16)
def _build(provider: str, model: str, temperature: float | None):
    if provider not in PROVIDERS:
        return None
    module, cls, key_env, _ = PROVIDERS[provider]
    if key_env and not os.getenv(key_env):
        log.warning("Thiếu %s – chạy chế độ quy tắc", key_env)
        return None
    try:
        klass = getattr(importlib.import_module(module), cls)
    except ImportError:
        log.warning("Chưa cài %s – chạy chế độ quy tắc", module)
        return None
    kw = {"model": model}
    if temperature is not None:
        kw["temperature"] = temperature
    try:
        return klass(**kw, max_retries=1)
    except TypeError:
        try:
            return klass(**kw)
        except Exception as error:
            log.warning("Không khởi tạo được LLM (%s)", type(error).__name__)
            return None
    except Exception as error:
        log.warning("Không khởi tạo được LLM (%s)", type(error).__name__)
        return None


_exhausted: set[tuple[str, str]] = set()   # (provider, model) đã hết quota trong phiên này


def _quota_error(e: Exception) -> bool:
    t = f"{type(e).__name__} {e}".lower()
    return any(k in t for k in ("429", "resource_exhausted", "ratelimit", "rate limit", "quota", "insufficient_quota"))


def _mark_if_quota(e: Exception) -> bool:
    """Hết quota -> ngừng gọi model này cho tới khi khởi động lại, agent dùng phương án quy tắc."""
    if _quota_error(e):
        c = agent_config()
        if (c["provider"], c["model"]) not in _exhausted:
            log.warning("%s · %s hết quota/rate limit – chuyển sang chế độ quy tắc cho tới khi khởi động lại",
                        c["provider"], redact(c["model"]))
        _exhausted.add((c["provider"], c["model"]))
        return True
    return False


def get_llm(agent: str | None = None):
    """LLM cho agent hiện tại (lấy từ ngữ cảnh khi agent đang chạy) hoặc agent được chỉ định."""
    c = agent_config(agent)
    if (c["provider"], c["model"]) in _exhausted:
        return None
    return _build(c["provider"], c["model"], c["temperature"])


def llm_enabled(agent: str | None = None) -> bool:
    return get_llm(agent) is not None


def agent_model_label(agent: str) -> str:
    c = agent_config(agent)
    return f"{c['provider']} · {c['model']}" if llm_enabled(agent) else "quy tắc (không LLM)"


def configuration_status(agent: str) -> dict[str, str]:
    """Đọc trạng thái cấu hình mà không khởi tạo client hoặc trả giá trị khóa."""
    try:
        config = agent_config(agent)
    except (ValueError, TypeError):
        return {"provider": "—", "model": "—", "status": "Cấu hình model thiếu hoặc sai định dạng"}
    provider, model = config["provider"], config["model"]
    if provider == "none":
        return {"provider": "Quy tắc cục bộ", "model": "—", "status": "Không dùng API"}
    if provider not in PROVIDERS:
        return {"provider": "Chưa hỗ trợ", "model": "—", "status": "Kiểm tra biến LLM_PROVIDER"}
    module, _, key_env, _ = PROVIDERS[provider]
    keys = [os.getenv(item[2], "").strip() for item in PROVIDERS.values() if item[2]]
    visible_model = "—" if not model or any(key and key in model for key in keys) else model
    try:
        available = importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        available = False
    if key_env and not os.getenv(key_env, "").strip():
        status = f"Thiếu {key_env}"
    elif not available:
        status = "Thiếu gói kết nối"
    elif key_env:
        status = "Đã cấu hình · chưa thử kết nối"
    else:
        status = "Model cục bộ · chưa thử kết nối"
    return {"provider": provider, "model": visible_model, "status": status}


def test_connection(provider: str, model: str, temperature: float | None = None, timeout_s: float = 30.0) -> dict:
    """Gửi một câu ngắn tới model, trả {ok, message, latency_s}. Không ghi token vào lượt thiết kế nào."""
    import concurrent.futures
    import time

    provider = (provider or "none").lower()
    if provider == "none":
        return {"ok": False, "message": "Chế độ quy tắc không gọi API.", "latency_s": None}
    if provider not in PROVIDERS:
        return {"ok": False, "message": f"Nhà cung cấp chưa hỗ trợ: {provider}", "latency_s": None}
    module, _, key_env, default_model = PROVIDERS[provider]
    model = model or default_model
    if key_env and not os.getenv(key_env, "").strip():
        return {"ok": False, "message": f"Thiếu {key_env} trong .env hoặc biến môi trường.", "latency_s": None}
    if importlib.util.find_spec(module) is None:
        return {"ok": False, "message": f"Chưa cài gói {module} (pip install {module.replace('_', '-')}).",
                "latency_s": None}
    llm = _build(provider, model, temperature)
    if llm is None:
        return {"ok": False, "message": "Không khởi tạo được client với cấu hình này.", "latency_s": None}
    started = time.perf_counter()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        msg = pool.submit(llm.invoke, [("human", "Trả lời đúng một từ: OK")]).result(timeout=timeout_s)
    except concurrent.futures.TimeoutError:
        return {"ok": False, "message": f"Quá {timeout_s:.0f} giây chưa có phản hồi.", "latency_s": None}
    except Exception as e:  # noqa: BLE001
        text = f"{type(e).__name__} {e}".lower()
        if _quota_error(e):
            reason = "Hết quota hoặc bị giới hạn tốc độ (429)."
        elif any(k in text for k in ("401", "403", "api key", "api_key", "authentication", "permission", "unauthorized")):
            reason = "Khóa API không hợp lệ hoặc không có quyền dùng model này."
        elif any(k in text for k in ("404", "not found", "not_found", "does not exist", "unknown model")):
            reason = f"Không tìm thấy model “{model}”."
        elif any(k in text for k in ("connect", "timeout", "timed out", "network", "resolve")):
            reason = "Không kết nối được tới máy chủ model."
        else:
            reason = f"Lỗi {type(e).__name__}."
        detail = redact(str(e)).strip().splitlines()[0][:200] if str(e).strip() else ""
        return {"ok": False, "message": reason + (f" Chi tiết: {detail}" if detail else ""), "latency_s": None}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    latency = round(time.perf_counter() - started, 2)
    _exhausted.discard((provider, model))   # kết nối lại được thì bỏ đánh dấu hết quota trong phiên
    content = msg.content if isinstance(getattr(msg, "content", None), str) else str(getattr(msg, "content", ""))
    return {"ok": True, "message": f"Phản hồi: {redact(content).strip()[:60] or '(trống)'}", "latency_s": latency}


def mode_label() -> str:
    labels = {a: agent_model_label(a) for a in AGENTS}
    if len(set(labels.values())) == 1:
        v = labels[AGENTS[0]]
        return "Chế độ quy tắc (không dùng LLM)" if v.startswith("quy tắc") else f"LLM: {v}"
    return "LLM theo agent – " + "; ".join(f"{a}: {v}" for a, v in labels.items())


def _usage_tokens(msg) -> int | None:
    meta = getattr(msg, "response_metadata", {}) or {}
    for usage in (getattr(msg, "usage_metadata", None), meta.get("token_usage"), meta.get("usage")):
        if not isinstance(usage, dict):
            continue
        total = usage.get("total_tokens")
        if type(total) is int and total >= 0:
            return total
        incoming = usage.get("input_tokens", usage.get("prompt_tokens"))
        outgoing = usage.get("output_tokens", usage.get("completion_tokens"))
        if type(incoming) is int and type(outgoing) is int and min(incoming, outgoing) >= 0:
            return incoming + outgoing
    return None


def _record_response(msg, model: str | None, prompt: str, response: str) -> None:
    meta = getattr(msg, "response_metadata", {}) or {}
    actual_model = meta.get("model_name") or meta.get("model") or model
    cost = meta.get("cost_usd")
    tracker.record(_usage_tokens(msg), prompt=prompt, response=response,
                   model=actual_model if isinstance(actual_model, str) else model,
                   cost_usd=cost if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0 else None)


def invoke_text(system: str, prompt: str, retries: int = 2) -> str | None:
    llm = get_llm()
    if llm is None:
        return None
    model = agent_config()["model"] or None
    for attempt in range(retries + 1):
        try:
            msg = llm.invoke([("system", system + PLAIN_RULE), ("human", prompt)])
        except Exception as e:  # noqa: BLE001
            tracker.record(None, model=model, api_error=error_category(e) == "infrastructure")
            if _mark_if_quota(e):
                return None
            log.warning("LLM lỗi (lần %d): %s", attempt + 1, type(e).__name__)
            continue
        try:
            text = msg.content if isinstance(msg.content, str) else "".join(
                p.get("text") or "" if isinstance(p, dict) else str(p) for p in (msg.content or []))
        except (AttributeError, TypeError):
            _record_response(msg, model, f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}", "")
            log.warning("LLM trả nội dung sai định dạng (lần %d)", attempt + 1)
            continue
        _record_response(msg, model, f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}", text)
        return clean_text(redact(text))
    return None


PLAIN_RULE = ("\n\nChỉ trả về đúng nội dung được yêu cầu bằng tiếng Việt: không lời chào, không câu dẫn "
              "(như 'Dưới đây là...'), không tiêu đề, không markdown (không dùng *, #, gạch đầu dòng).")


def clean_text(text: str) -> str:
    """Bỏ câu dẫn đầu ('Chào bạn, đây là ...:') và ký hiệu markdown còn sót."""
    import re

    lines = [ln.strip() for ln in text.strip().splitlines()]
    while lines and (not lines[0] or (lines[0].endswith(":") and len(lines) > 1)
                     or re.match(r"^(chào|dưới đây|đây là|sau đây)", lines[0], re.I)):
        lines.pop(0)
    out = []
    for ln in lines:
        ln = re.sub(r"^\s*([*\-•]|\d+\.)\s+", "", ln)
        ln = re.sub(r"[*#]{1,3}", "", ln).strip()
        if ln:
            out.append(ln)
    if out and out[0].startswith("{"):
        return "\n".join(out)  # JSON giữ nguyên dòng
    return " ".join(out)


def invoke_structured(system: str, prompt: str, schema, retries: int = 2):
    """Gọi LLM với Pydantic structured output; tự thử lại khi JSON sai định dạng."""
    llm = get_llm()
    if llm is None:
        return None
    try:
        runnable = llm.with_structured_output(schema, include_raw=True)
    except Exception as e:  # noqa: BLE001
        log.warning("Model không hỗ trợ structured output: %s", type(e).__name__)
        return None
    model = agent_config()["model"] or None
    for attempt in range(retries + 1):
        try:
            out = runnable.invoke([("system", system), ("human", prompt)])
        except Exception as e:  # noqa: BLE001
            tracker.record(None, model=model, api_error=error_category(e) == "infrastructure")
            if _mark_if_quota(e):
                return None
            log.warning("Structured output lỗi (lần %d): %s", attempt + 1, type(e).__name__)
            continue
        if not isinstance(out, dict):
            tracker.record(None, model=model)
            log.warning("Structured output trả sai định dạng (lần %d)", attempt + 1)
            continue
        parsed = out.get("parsed")
        _record_response(out.get("raw"), model, f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}", str(parsed))
        if parsed is not None:
            return parsed
    return None
