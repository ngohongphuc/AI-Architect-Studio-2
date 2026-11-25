"""Đếm token, số lần gọi LLM và lưu prompt theo (run_id, agent)."""
from __future__ import annotations

import contextvars
import math
import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field

from monitoring.redaction import redact

current_run: contextvars.ContextVar[str] = contextvars.ContextVar("current_run", default="local")
current_agent: contextvars.ContextVar[str] = contextvars.ContextVar("current_agent", default="unknown")


@dataclass
class AttemptUsage:
    calls: int = 0
    api_errors: int = 0
    tokens: int | None = 0
    cost_usd: float | None = 0.0
    models: set[str] = field(default_factory=set)
    estimated: bool = False

    def add(self, tokens: int | None, model: str | None, cost: float | None, estimated: bool, error: bool) -> None:
        self.calls += 1
        self.api_errors += int(error)
        if model:
            self.models.add(model)
        self.tokens = self.tokens + tokens if self.tokens is not None and tokens is not None else None
        self.cost_usd = self.cost_usd + cost if self.cost_usd is not None and cost is not None else None
        self.estimated |= estimated

    def snapshot(self) -> dict:
        has_cost = self.calls > 0 and self.cost_usd is not None
        return {"model": " · ".join(sorted(self.models)) or None, "tokens": self.tokens if self.calls else None,
                "call_count": self.calls or None, "api_errors": self.api_errors if self.calls else None,
                "cost_usd": self.cost_usd if has_cost else None,
                "cost_basis": ("estimated" if self.estimated else "reported") if has_cost else None}


current_usage: contextvars.ContextVar[AttemptUsage | None] = contextvars.ContextVar("current_usage", default=None)

# Giá tham khảo USD / 1 triệu token (blended input+output), có thể ghi đè bằng LLM_PRICE_PER_MTOK
DEFAULT_PRICE = {"gemini": 0.6, "openai": 1.0, "anthropic": 6.0, "ollama": 0.0, "none": 0.0}


class Tracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict = defaultdict(lambda: defaultdict(lambda: {"tokens": 0, "calls": 0, "usd": 0.0, "prompts": []}))

    def record(self, tokens: int | None, prompt: str | None = None, response: str | None = None,
               run_id: str | None = None, agent: str | None = None, *,
               model: str | None = None, cost_usd: float | None = None, api_error: bool = False) -> None:
        run_id = run_id or current_run.get()
        agent = agent or current_agent.get()
        if usage := current_usage.get():
            rate = configured_rate(agent) if cost_usd is None and tokens is not None else None
            estimated = rate is not None
            if estimated:
                cost_usd = tokens / 1e6 * rate
            usage.add(tokens, redact(model), cost_usd, estimated, api_error)
        with self._lock:
            d = self._data[run_id][agent]
            d["tokens"] += int(tokens or 0)
            d["usd"] += int(tokens or 0) / 1e6 * price_per_mtok(agent)
            d["calls"] += 1
            if prompt is not None:
                d["prompts"].append({"prompt": redact(prompt)[:6000], "response": redact(response or "")[:3000]})
                d["prompts"] = d["prompts"][-10:]

    def tokens(self, run_id: str, agent: str | None = None) -> int:
        with self._lock:
            if agent:
                return self._data[run_id][agent]["tokens"]
            return sum(v["tokens"] for v in self._data[run_id].values())

    def prompts(self, run_id: str, agent: str) -> list[dict]:
        with self._lock:
            return list(self._data[run_id][agent]["prompts"])

    def usd(self, run_id: str) -> float:
        with self._lock:
            return round(sum(v["usd"] for v in self._data[run_id].values()), 4)

    def summary(self, run_id: str) -> dict:
        with self._lock:
            return {a: {"tokens": v["tokens"], "calls": v["calls"]} for a, v in self._data[run_id].items()}


tracker = Tracker()


def _env(name: str, agent: str | None) -> str | None:
    if agent and os.getenv(f"{name}_{agent.upper()}"):
        return os.environ[f"{name}_{agent.upper()}"]
    return os.getenv(name)


def price_per_mtok(agent: str | None = None) -> float:
    """Giá USD / 1 triệu token của agent (LLM_PRICE_PER_MTOK_<AGENT> > LLM_PRICE_PER_MTOK > bảng mặc định)."""
    rate = configured_rate(agent)
    if rate is not None:
        return rate
    try:
        from llm import agent_config   # import muộn: llm phụ thuộc tracker

        provider = agent_config(agent)["provider"]   # gồm cả model đổi trên giao diện Quản lý agent
    except Exception:  # noqa: BLE001
        provider = (_env("LLM_PROVIDER", agent) or "none").lower()
    return DEFAULT_PRICE.get(provider, 1.0)


def configured_rate(agent: str | None) -> float | None:
    try:
        rate = float(_env("LLM_PRICE_PER_MTOK", agent) or "")
    except ValueError:
        return None
    return rate if math.isfinite(rate) and rate >= 0 else None

def estimate_cost_usd(tokens: int) -> float:
    return round(tokens / 1e6 * price_per_mtok(), 4)
