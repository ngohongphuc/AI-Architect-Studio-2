"""Cấu hình agent chỉnh trên giao diện: model theo agent và agent LLM tùy biến.

Lưu ở `AGENT_SETTINGS_FILE` (JSON, không chứa khóa API). Thứ tự ưu tiên khi chọn model:
giao diện → biến riêng của agent trong .env → biến chung trong .env.

Mỗi lượt thiết kế chụp lại cấu hình lúc bắt đầu (`state["agent_settings"]`); trong lúc node chạy,
`run_settings` giữ bản chụp đó để lượt cũ không đổi model khi người dùng sửa cấu hình giữa chừng.
"""
from __future__ import annotations

import contextvars
import copy
import json
import os
import re
import threading
import unicodedata
from datetime import datetime

from config import AGENT_LABELS, AGENT_ORDER, AGENT_SETTINGS_FILE

# 9 agent lõi: định nghĩa trong code, giao diện không thêm/sửa/xóa/tắt được. Chỉ đổi được model LLM.
CORE_AGENTS = tuple(AGENT_ORDER)
# Agent lõi có gọi LLM (các agent còn lại chạy thuật toán Python, đổi model không có tác dụng).
LLM_AGENTS = ("project_manager", "requirements_analyst", "concept_architect", "architect", "reviewer", "cost_estimator")
_RESERVED_NAMES = {AGENT_LABELS[a].casefold() for a in CORE_AGENTS} | {a.casefold() for a in CORE_AGENTS}

# Bước có thể gắn agent tùy biến phía sau (trùng thứ tự điểm duyệt trong graph.APPROVALS).
CUSTOM_STAGES = ("project_manager", "requirements_analyst", "concept_architect", "architect", "drafter",
                 "fengshui_advisor", "reviewer", "cost_estimator", "pm_report", "final_reviewer")
STAGE_LABELS = {
    "project_manager": "Khởi tạo dự án", "requirements_analyst": "Phân tích yêu cầu",
    "concept_architect": "Ý tưởng kiến trúc", "architect": "Chốt phương án công năng",
    "drafter": "Triển khai bản vẽ", "fengshui_advisor": "Tư vấn phong thủy", "reviewer": "Kiểm định quy chuẩn",
    "cost_estimator": "Dự toán chi phí", "pm_report": "Tổng hợp hồ sơ", "final_reviewer": "Kiểm tra hồ sơ cuối",
}

# Dữ liệu agent tùy biến được đọc: khóa state → (mô tả, bước tạo ra dữ liệu).
INPUT_KEYS = {
    "user_request": ("Yêu cầu gốc của chủ nhà", "project_manager"),
    "brief": ("Yêu cầu thiết kế đã chuẩn hóa", "requirements_analyst"),
    "concept": ("Mô tả ý tưởng kiến trúc", "concept_architect"),
    "concept_plan": ("Định hướng ý tưởng (số tầng, phong cách, vật liệu)", "concept_architect"),
    "program": ("Chương trình công năng đã chốt", "architect"),
    "area_table": ("Bảng diện tích", "drafter"),
    "layout": ("Hình học mặt bằng (dữ liệu lớn)", "drafter"),
    "fengshui": ("Kết quả tư vấn phong thủy", "fengshui_advisor"),
    "review": ("Kết quả kiểm định quy chuẩn", "reviewer"),
    "cost": ("Dự toán chi phí", "cost_estimator"),
    "final_review": ("Kết quả đối chiếu hồ sơ cuối", "final_reviewer"),
    "custom_outputs": ("Nhận xét của các agent tùy biến khác", "project_manager"),
}

_ID = re.compile(r"^custom_[a-z0-9_]{1,40}$")
_lock = threading.Lock()
_cache: tuple[float, dict] | None = None

run_settings: contextvars.ContextVar[dict | None] = contextvars.ContextVar("run_settings", default=None)


def _empty() -> dict:
    return {"version": 1, "models": {}, "custom_agents": [], "updated": None}


def load() -> dict:
    """Cấu hình hiện hành trên đĩa (đọc lại khi tệp thay đổi). Tệp hỏng → coi như chưa cấu hình."""
    global _cache
    try:
        stamp = AGENT_SETTINGS_FILE.stat().st_mtime_ns
    except OSError:
        return _empty()
    with _lock:
        if _cache and _cache[0] == stamp:
            return copy.deepcopy(_cache[1])
    try:
        raw = json.loads(AGENT_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty()
    data = _empty()
    if isinstance(raw, dict):
        models = raw.get("models") if isinstance(raw.get("models"), dict) else {}
        for agent, item in models.items():
            if agent not in LLM_AGENTS:   # chỉ agent lõi có LLM mới nhận ghi đè model (kể cả khi sửa tay tệp)
                continue
            try:
                data["models"][agent] = validate_model(item)
            except ValueError:
                continue
        for item in raw.get("custom_agents") or []:
            try:
                data["custom_agents"].append(validate_custom(item))
            except ValueError:
                continue
        data["updated"] = raw.get("updated")
    with _lock:
        _cache = (stamp, data)
    return copy.deepcopy(data)


def save(data: dict) -> None:
    global _cache
    data = {**data, "version": 1, "updated": datetime.now().isoformat(timespec="seconds")}
    with _lock:
        _cache = None
    AGENT_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = AGENT_SETTINGS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, AGENT_SETTINGS_FILE)
    with _lock:
        _cache = None


def current() -> dict:
    """Bản chụp của lượt đang chạy nếu có, nếu không thì cấu hình trên đĩa."""
    return run_settings.get() or load()


def snapshot() -> dict:
    """Cấu hình chụp vào state khi bắt đầu lượt mới (chỉ agent tùy biến đang bật)."""
    data = load()
    return {"models": data["models"], "custom_agents": [a for a in data["custom_agents"] if a["enabled"]]}


# ---------------------------------------------------------------- kiểm tra dữ liệu
def _text(value, limit: int, field: str, *, required: bool = False, multiline: bool = False) -> str:
    text = (value or "").strip() if isinstance(value, str) or value is None else None
    if text is None:
        raise ValueError(f"{field} phải là chuỗi")
    if required and not text:
        raise ValueError(f"Thiếu {field}")
    if len(text) > limit:
        raise ValueError(f"{field} dài quá {limit} ký tự")
    if not multiline and ("\n" in text or "\r" in text):
        raise ValueError(f"{field} không được xuống dòng")
    return text


def validate_model(item) -> dict:
    """{provider, model}; provider rỗng = theo .env. Temperature không chỉnh trên giao diện (dùng mặc định / .env)."""
    from llm import PROVIDERS

    if not isinstance(item, dict):
        raise ValueError("Cấu hình model sai định dạng")
    provider = _text(item.get("provider"), 20, "Nhà cung cấp").lower()
    if provider and provider not in (*PROVIDERS, "none"):
        raise ValueError(f"Nhà cung cấp chưa hỗ trợ: {provider}")
    model = _text(item.get("model"), 100, "Tên model")
    if model and not re.fullmatch(r"[\w.:/@+-]+", model):
        raise ValueError("Tên model chỉ gồm chữ, số và . : / @ + - _")
    return {"provider": provider, "model": model}   # khóa "temperature" cũ trong tệp bị bỏ qua


def validate_custom(item) -> dict:
    if not isinstance(item, dict):
        raise ValueError("Agent tùy biến sai định dạng")
    ident = item.get("id")
    if not isinstance(ident, str) or not _ID.fullmatch(ident):
        raise ValueError("Mã agent phải dạng custom_<chữ thường, số, _>")
    after = item.get("after")
    if after not in CUSTOM_STAGES:
        raise ValueError("Chọn bước để chèn agent phía sau")
    name = _text(item.get("name"), 60, "Tên agent", required=True)
    if name.casefold() in _RESERVED_NAMES:
        raise ValueError(f"“{name}” là tên agent lõi. Đặt tên khác cho agent tùy biến.")
    inputs = item.get("inputs") or []
    if not isinstance(inputs, list) or any(key not in INPUT_KEYS for key in inputs):
        raise ValueError("Dữ liệu đầu vào không hợp lệ")
    late = [INPUT_KEYS[key][0] for key in inputs
            if CUSTOM_STAGES.index(INPUT_KEYS[key][1]) > CUSTOM_STAGES.index(after)]
    if late:
        raise ValueError("Chưa có dữ liệu ở bước này: " + ", ".join(late))
    return {"id": ident, "name": name,
            "role": _text(item.get("role"), 200, "Vai trò"),
            "prompt": _text(item.get("prompt"), 4000, "Nhiệm vụ (prompt)", required=True, multiline=True),
            "after": after, "inputs": list(dict.fromkeys(inputs)), "enabled": bool(item.get("enabled", True)),
            **validate_model(item)}


def available_inputs(after: str) -> list[str]:
    position = CUSTOM_STAGES.index(after)
    return [key for key, (_, stage) in INPUT_KEYS.items() if CUSTOM_STAGES.index(stage) <= position]


# ---------------------------------------------------------------- đọc
def model_override(agent: str | None) -> dict:
    """Ghi đè model của agent lõi, hoặc cấu hình model của agent tùy biến."""
    if not agent:
        return {}
    data = current()
    custom = next((a for a in data["custom_agents"] if a["id"] == agent), None)
    if custom is not None:
        return {key: custom[key] for key in ("provider", "model")}
    return data["models"].get(agent, {})


def custom_agent(agent: str | None, settings: dict | None = None) -> dict | None:
    if not agent or not agent.startswith("custom_"):
        return None
    data = settings or current()
    return next((a for a in data["custom_agents"] if a["id"] == agent), None)


def custom_label(agent: str) -> str | None:
    found = custom_agent(agent, load()) or custom_agent(agent)
    return found["name"] if found else None


def custom_agents_after(stage: str, settings: dict | None) -> list[dict]:
    data = settings if settings is not None else load()
    return [a for a in data.get("custom_agents") or [] if a.get("enabled", True) and a["after"] == stage]


# ---------------------------------------------------------------- ghi
def set_model(agent: str, provider: str = "", model: str = "") -> dict:
    """Đổi model của agent lõi có dùng LLM. Agent tùy biến đổi model qua `upsert_custom`."""
    if agent not in LLM_AGENTS:
        raise ValueError("Chỉ đổi được model của agent lõi có dùng LLM")
    item = validate_model({"provider": provider, "model": model})
    data = load()
    if any(item.values()):
        data["models"][agent] = item
    else:
        data["models"].pop(agent, None)
    save(data)
    return item


def clear_model(agent: str) -> None:
    data = load()
    if data["models"].pop(agent, None) is not None:
        save(data)


def new_custom_id(name: str, taken: set[str] | None = None) -> str:
    ascii_name = unicodedata.normalize("NFKD", name.replace("đ", "d").replace("Đ", "D"))
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name.encode("ascii", "ignore").decode().lower()).strip("_")[:30] or "agent"
    taken = taken if taken is not None else {a["id"] for a in load()["custom_agents"]}
    ident, n = f"custom_{slug}", 2
    while ident in taken:
        ident, n = f"custom_{slug}_{n}", n + 1
    return ident


def upsert_custom(item: dict) -> dict:
    data = load()
    if not item.get("id"):
        item = {**item, "id": new_custom_id(item.get("name") or "", {a["id"] for a in data["custom_agents"]})}
    agent = validate_custom(item)
    agents = data["custom_agents"]
    index = next((i for i, a in enumerate(agents) if a["id"] == agent["id"]), None)
    if index is None:
        agents.append(agent)
    else:
        agents[index] = agent
    save(data)
    return agent


def delete_custom(agent_id: str) -> bool:
    data = load()
    kept = [a for a in data["custom_agents"] if a["id"] != agent_id]
    if len(kept) == len(data["custom_agents"]):
        return False
    data["custom_agents"] = kept
    save(data)
    return True
