"""Xây dựng định hướng kiến trúc từ brief và điều chỉnh quy mô khi có phản hồi."""
from agents import architect
from agents.base import agent_node
from llm import invoke_text
from state import ConceptPlan


@agent_node("concept_architect")
def run(state: dict) -> dict:
    brief = state["brief"]
    style = brief["phong_cach"]
    previous = state.get("program")
    feedback = state.get("feedback") or []
    has_feedback = bool(feedback)
    owned_codes = {"MAT_DO", "SO_TANG", "CHIEU_CAO_TANG", "THIEU_PHONG", "VUOT_NGAN_SACH", "SAI_SO_TANG"}
    scale_feedback = [issue for issue in feedback if issue["ma"] in owned_codes]
    pending = [issue for issue in feedback if issue["ma"] not in owned_codes]
    changes = []
    floors = architect.proposed_floors(brief)
    if previous and has_feedback:
        identity = {key: previous[key] for key in ("phuong_an", "option_version", "revision_id") if key in previous}
        if any(issue["ma"] == "SAI_SO_TANG" for issue in scale_feedback):
            previous = architect.initial_program(brief, keep=previous)
            changes.append("Lập lại quy mô theo số tầng đã chốt trong brief")
        revised, scale_changes = architect.apply_feedback(previous, scale_feedback, brief)
        previous = {**revised, **identity}
        changes.extend(scale_changes)
        floors = previous["so_tang"]
    direction = brief["lo_dat"]["huong"]
    daylight = ["Lấy sáng từ mặt tiền và giếng trời", "Bổ sung sân sau nếu chiều sâu lô đất cho phép"]
    if direction.casefold().startswith("tây"):
        daylight.append("Dùng lam mặt tiền để giảm nắng chiều")
    plan = ConceptPlan(so_tang=floors, phong_cach=style, vat_lieu=previous["vat_lieu"] if previous and has_feedback else architect._materials(style),
                       thong_gio=["Dẫn gió từ mặt tiền và sân sau", "Thoát khí qua giếng trời cạnh lõi giao thông"],
                       chieu_sang=daylight)
    context = "; ".join([*plan.thong_gio, *plan.chieu_sang])
    directions = (state.get("option_brief") or {}).get("huong_so_sanh", [])
    narrative = invoke_text("Bạn là kiến trúc sư ý tưởng cho nhà ống Việt Nam.",
                            f"Nêu giải pháp cho mặt tiền hướng {direction}, phong cách {style}. "
                            "Mọi quyết định khi thiếu hồ sơ chỉ là giả định thiết kế. "
                            f"Không đưa con số hoặc kết luận pháp lý. Định hướng: {context}. "
                            f"Các hướng cần cân nhắc: {', '.join(directions)}.") or context
    return {"concept_plan": plan.model_dump(), "concept": narrative,
            "program": previous if has_feedback else None, "feedback": pending,
            "route": "architect", "_to": "architect",
            "_summary": f"Định hướng {floors} tầng, phong cách {style}, lấy sáng và thông gió tự nhiên" + (". " + ". ".join(changes) if changes else ""),
            "_output": plan.model_dump() | {"dien_giai": narrative, "thay_doi": changes}}
