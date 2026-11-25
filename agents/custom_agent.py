"""Agent LLM tùy biến tạo trên giao diện Quản lý agent.

Mỗi agent được gắn sau một bước của luồng. Nó đọc các khóa state đã chọn, gọi LLM với prompt của
người dùng và ghi nhận xét vào `custom_outputs[<mã agent>]`. Agent tùy biến chỉ tư vấn: không đổi
`route`, không sửa số liệu của các agent lõi, nên luồng vẫn đi tiếp đúng như agent lõi đã chọn.
"""
from __future__ import annotations

import json
from datetime import datetime

import agent_settings
from agents.base import agent_node
from monitoring import tasks
from monitoring.redaction import redact
from monitoring.tracker import current_agent

CONTEXT_LIMIT = 12_000   # ký tự dữ liệu hồ sơ gửi kèm prompt

# Vị trí từng nhánh trong luồng, để chỉ chạy agent tùy biến khi luồng đi tiếp (không chạy khi quay lại sửa).
_ORDER = {stage: index for index, stage in enumerate(agent_settings.CUSTOM_STAGES)}
_ORDER.update(plan_options=_ORDER["concept_architect"], publish=len(_ORDER))


def hook_name(stage: str) -> str:
    return f"custom_after_{stage}"


def settings_of(state: dict) -> dict:
    """Bản chụp của lượt; lượt tạo trước khi có tính năng này đọc cấu hình hiện hành."""
    return state.get("agent_settings") or agent_settings.load()


def pending(state: dict, stage: str) -> bool:
    route = state.get("route") or "end"
    if route not in _ORDER or _ORDER[route] <= _ORDER[stage] or state.get("outcome") == "stopped":
        return False
    return bool(agent_settings.custom_agents_after(stage, settings_of(state)))


def build_prompt(spec: dict, state: dict) -> tuple[str, str]:
    data = {key: state[key] for key in spec["inputs"] if state.get(key) is not None}
    context = json.dumps(redact(data), ensure_ascii=False, default=str)
    if len(context) > CONTEXT_LIMIT:
        context = context[:CONTEXT_LIMIT] + " …(đã cắt bớt)"
    system = (f"Bạn là “{spec['name']}”, một thành viên trong văn phòng thiết kế nhà ở AI Architect Studio."
              + (f" Vai trò: {spec['role']}." if spec.get("role") else "")
              + " Chỉ nhận xét và kiến nghị dựa trên dữ liệu được cung cấp; không bịa số liệu.\n\n"
              + f"Nhiệm vụ:\n{spec['prompt']}")
    prompt = (f"Dữ liệu hồ sơ hiện tại (JSON):\n{context}" if data else "Chưa có dữ liệu hồ sơ được chọn.") \
        + "\n\nHãy thực hiện nhiệm vụ của bạn."
    return system, prompt


def run_one(spec: dict, state: dict) -> dict:
    """Gọi LLM cho một agent tùy biến; trả về bản ghi nhận xét (không ghi vào state)."""
    from llm import agent_config, invoke_text, llm_enabled

    token = current_agent.set(spec["id"])
    try:
        config = agent_config(spec["id"])
        model = f"{config['provider']} · {config['model']}"
        text = invoke_text(*build_prompt(spec, state)) if llm_enabled(spec["id"]) else None
    finally:
        current_agent.reset(token)
    return {"id": spec["id"], "name": spec["name"], "after": spec["after"],
            "status": "done" if text else "no_llm",
            "text": text or "Chưa có model khả dụng hoặc model không phản hồi – bỏ qua nhận xét.",
            "model": model if text else "—", "revision_id": state.get("revision_id"),
            "time": datetime.now().isoformat(timespec="seconds")}


def make_hook(stage: str):
    """Node chạy lần lượt các agent tùy biến gắn sau `stage`, rồi để luồng đi tiếp theo `route` sẵn có."""

    def hook(state: dict) -> dict:
        outputs = dict(state.get("custom_outputs") or {})
        merged = {"events": [], "log": [], "history": []}
        versions = dict(state.get("versions") or {})
        for spec in agent_settings.custom_agents_after(stage, settings_of(state)):
            def work(current: dict, spec=spec) -> dict:
                note = run_one(spec, current)
                return {"note": note, "_summary": note["text"][:160], "_output": note,
                        "_to": current.get("route", "")}

            node = agent_node(spec["id"], stage=hook_name(stage), inputs=tuple(spec["inputs"]), name=spec["name"])
            # Mỗi agent tùy biến là một task riêng trong Công việc & Hiệu suất (mã task = mã agent).
            tracked = tasks.track_stage(spec["id"], node(work))
            result = tracked({**state, "versions": versions, "custom_outputs": outputs})
            versions = result["versions"]
            outputs[spec["id"]] = result["note"]
            for key in merged:
                merged[key] += result.get(key, [])
        return {"custom_outputs": outputs, "versions": versions, **merged}

    hook.__name__ = hook_name(stage)
    return hook
