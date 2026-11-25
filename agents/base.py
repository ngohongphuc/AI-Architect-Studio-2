"""Bộ khung chung cho mọi agent: đo thời gian, đếm token, phát AgentEvent, ghi log và lịch sử phiên bản."""
from __future__ import annotations

import copy
import time
from datetime import datetime
from functools import wraps

import agent_settings
from config import AGENT_LABELS
from monitoring import events
from monitoring.redaction import error_text, redact
from monitoring.tracker import current_agent, current_run, tracker


AGENT_INPUTS = {
    "project_manager": ("user_request", "brief", "area_table", "feedback", "repair_target", "iteration"),
    "requirements_analyst": ("user_request", "request_fields"),
    "concept_architect": ("brief", "option_brief", "feedback"),
    "architect": ("brief", "option_brief", "concept_plan", "feedback"),
    "drafter": ("brief", "program", "revision_id"),
    "reviewer": ("brief", "area_table", "revision_id"),
    "fengshui_advisor": ("brief", "fengshui_enabled", "revision_id"),
    "cost_estimator": ("brief", "program", "area_table", "revision_id"),
    "final_reviewer": ("brief", "area_table", "draft_files", "revision_id"),
}


def describe_input(agent: str, state: dict, keys: tuple | None = None) -> dict:
    keys = AGENT_INPUTS.get(agent, ()) if keys is None else keys
    return {key: state[key] for key in keys if state.get(key) is not None}


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def agent_node(agent: str, *, stage: str | None = None, inputs: tuple | None = None, name: str | None = None):
    """Decorator biến hàm `fn(state) -> dict` thành node LangGraph có theo dõi.

    Hàm agent có thể trả thêm các khóa đặc biệt:
        _summary: tóm tắt ngắn cho timeline
        _to:      agent nhận việc tiếp theo
        _output:  dữ liệu lưu vào lịch sử phiên bản
        _feedback: True nếu đây là phản hồi lỗi (tô đỏ)
    """

    def deco(fn):
        @wraps(fn)
        def wrapper(state: dict) -> dict:
            run_id = state.get("run_id", "local")
            versions = dict(state.get("versions") or {})
            version = versions.get(agent, 0) + 1
            events.emit(run_id, {"time": now(), "agent": agent, "status": "revising" if version > 1 else "running",
                                 "to_agent": "", "summary": "Đang xử lý", "tokens": 0, "duration_s": 0.0,
                                 "version": version})
            t_run, t_agent = current_run.set(run_id), current_agent.set(agent)
            t_settings = agent_settings.run_settings.set(state.get("agent_settings"))
            tok0 = tracker.tokens(run_id, agent)
            snapshot = copy.deepcopy(describe_input(agent, state, inputs))
            t0 = time.perf_counter()
            try:
                result = fn(state) or {}
            except Exception as e:
                events.emit(run_id, {"time": now(), "agent": agent, "status": "error", "to_agent": "",
                                     "summary": error_text(e), "tokens": tracker.tokens(run_id, agent) - tok0,
                                     "duration_s": round(time.perf_counter() - t0, 2), "version": version,
                                     "feedback": True})
                raise
            finally:
                agent_settings.run_settings.reset(t_settings)
                current_run.reset(t_run)
                current_agent.reset(t_agent)
            duration = round(time.perf_counter() - t0, 2)
            tokens = tracker.tokens(run_id, agent) - tok0
            summary = redact(result.pop("_summary", "Hoàn thành"))
            to_agent = result.pop("_to", "")
            output = result.pop("_output", None)
            feedback = bool(result.pop("_feedback", False))
            ev = {"time": now(), "agent": agent, "status": "done", "to_agent": to_agent, "summary": summary,
                  "tokens": tokens, "duration_s": duration, "version": version, "feedback": feedback}
            events.emit(run_id, ev)
            versions[agent] = version
            label_to = AGENT_LABELS.get(to_agent, to_agent or "Kết thúc")
            result["versions"] = versions
            result["events"] = [ev]
            result["log"] = [f"{ev['time']}  {AGENT_LABELS.get(agent, name or agent)} → {label_to}: {summary}"]
            result["history"] = [{"agent": agent, "stage": stage or agent, "version": version,
                                  "attempt_id": events.current_attempt.get(),
                                  "iteration": result.get("iteration", state.get("iteration", 0)),
                                  "to_agent": to_agent, "feedback": feedback,
                                  "time": ev["time"], "summary": summary,
                                  "input": redact(snapshot), "output": redact(output)}]
            return result

        wrapper.agent_name = agent
        return wrapper

    return deco
