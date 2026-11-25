"""Chuẩn hóa yêu cầu và yêu cầu xác nhận dữ liệu quan trọng."""
import json

from pydantic import ValidationError

from agents.base import agent_node
from llm import invoke_structured, llm_enabled
from state import Brief, BriefAssessment
from tools.brief_parser import FIELD_LABELS, inspect_request

SYSTEM_BRIEF = ("Bạn là chuyên viên phân tích yêu cầu kiến trúc. Trích xuất yêu cầu thiết kế nhà ở từ lời khách hàng thành JSON "
                "đúng schema. Không bịa thông tin: trường nào khách không nói thì để mặc định và ghi vào "
                "gia_dinh_bo_sung là giả định. Ngân sách đổi ra VNĐ (2,5 tỷ = 2500000000).")


def needs_confirmation(brief: dict) -> list[str]:
    assumptions = brief.get("gia_dinh_bo_sung", [])
    prompts = {
        "Ngân sách:": "Xác nhận ngân sách xây dựng dự kiến.",
        "Số phòng ngủ:": "Xác nhận số phòng ngủ cần bố trí.",
        "Hướng mặt tiền:": "Xác nhận hướng mặt tiền để rà soát lấy sáng và thông gió.",
    }
    missing = [question for prefix, question in prompts.items() if any(a.startswith(prefix) for a in assumptions)]
    if not brief["lo_dat"].get("ma_lo_dat"):
        missing.append("Bổ sung mã lô đất để đối chiếu phạm vi áp dụng của nguồn.")
    if not brief["lo_dat"].get("tinh") or any(a.startswith("Địa điểm:") for a in assumptions):
        missing.append("Xác nhận tỉnh/thành phố của lô đất.")
    return missing


def analyze_brief(request: str, request_fields: dict | None = None, *, rule: dict | None = None) -> dict | None:
    if rule is None:
        rule, _, _ = inspect_request(request, request_fields)
    if rule is None:
        return None
    if not llm_enabled():
        return rule
    inputs = request
    if request_fields:
        labels = {FIELD_LABELS[key]: value for key, value in request_fields.items() if value is not None}
        inputs += "\nDữ liệu người dùng xác nhận trong biểu mẫu:\n" + json.dumps(labels, ensure_ascii=False)
    out = invoke_structured(SYSTEM_BRIEF, inputs, Brief)
    if out is None:
        rule["gia_dinh_bo_sung"].append("LLM không trả kết quả hợp lệ – dùng bộ phân tích quy tắc")
        return rule
    try:
        brief = Brief.model_validate(out).model_dump()
    except ValidationError:
        rule["gia_dinh_bo_sung"].append("LLM trả dữ liệu sai schema — dùng bộ phân tích quy tắc.")
        return rule
    # Giữ số liệu định lượng nhận diện được bằng quy tắc.
    brief["lo_dat"] = rule["lo_dat"]
    brief["gia_dinh"]["so_nguoi"] = rule["gia_dinh"]["so_nguoi"]
    for field in ("phong_ngu", "so_tang"):
        brief["yeu_cau_phong"][field] = rule["yeu_cau_phong"][field]
    brief["ngan_sach"] = rule["ngan_sach"]
    brief["gia_dinh_bo_sung"] = rule["gia_dinh_bo_sung"]
    return brief



@agent_node("requirements_analyst")
def run(state: dict) -> dict:
    request = state["user_request"]
    request_fields = state.get("request_fields")
    rule, questions, conflicts = inspect_request(request, request_fields)
    brief = analyze_brief(request, request_fields, rule=rule) if rule is not None else None
    assessment = BriefAssessment(questions=questions, conflicts=conflicts,
                                 needs_confirmation=needs_confirmation(brief) if brief else [])
    blocked = bool(questions or conflicts)
    return {"brief": brief, "brief_assessment": assessment.model_dump(),
            "route": "end" if blocked else "plan_options",
            "outcome": "needs_input" if blocked else None, "_feedback": blocked,
            "_to": "user" if blocked else "project_manager",
            "_summary": "Cần xác nhận yêu cầu" if blocked else "Đã chuẩn hóa yêu cầu thiết kế",
            "_output": {"brief": brief, **assessment.model_dump()}}
