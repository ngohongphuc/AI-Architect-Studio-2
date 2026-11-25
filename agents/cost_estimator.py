"""Agent 5 – Kỹ sư dự toán: diện tích quy đổi, chi phí theo hạng mục, so sánh ngân sách, file du_toan.xlsx."""
from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from agents import reviewer
from agents.base import agent_node
from config import BUDGET_TOLERANCE
from llm import invoke_text
from tools.design_option import option_label, option_stamp, requires_repair, selected_assumptions
from tools.docx_writer import vn_num, vnd
from tools.layout_algorithm import LayoutError, build_area_table, compute_layout
from tools.xlsx_writer import write_cost_xlsx
from tools.cost_calc import compute_cost


def budget_assumed(brief: dict) -> bool:
    return any(note.startswith("Ngân sách:") for note in brief.get("gia_dinh_bo_sung", []))


def evaluate_option(brief: dict, option: dict) -> dict:
    program = option["program"]
    rear = program.get("san_sau", 0)
    metrics = {"so_tang": program["so_tang"], "san_sau": rear, "cap_hoan_thien": program["cap_hoan_thien"]}
    assumptions = list(brief.get("gia_dinh_bo_sung", []))
    assumptions.append(f"Mặt bằng theo lô chữ nhật đã khai, chừa sân trước {vn_num(program.get('san_truoc', 0))} m "
                       f"và sân sau {vn_num(rear)} m theo bản phác thảo. Các khoảng trống là lựa chọn thiết kế.")
    if brief["yeu_cau_phong"].get("so_tang") is None:
        assumptions.append(f"Tạm chọn {program['so_tang']} tầng theo nhu cầu công năng.")
    assumptions.append(f"Tạm dùng gói hoàn thiện {program['cap_hoan_thien']} để tính chi phí.")
    identity = {key: option[key] for key in ("id", "ten", "mo_ta", "program")}
    result = {**identity, "phien_ban": program["option_version"], "chi_so": metrics,
              "vat_lieu": program["vat_lieu"], "gia_dinh": assumptions, "can_xac_minh": [],
              "cong_nang": {}, "uu_diem": [], "han_che": [], "loi": [], "eligible": False}
    try:
        layout = compute_layout(brief, program)
    except LayoutError as exc:
        result["loi"].append({"ma": "KHONG_DU_CHO", "muc": "Bố trí mặt bằng", "noi_dung": str(exc),
                              "phan_loai": "ky_thuat"})
        result["han_che"].append("Chưa có hình học để lập bảng diện tích và dự toán.")
        return result
    area = build_area_table(layout, brief)
    cost = compute_cost(area, layout, program, brief["ngan_sach"])
    checks, issues, _ = reviewer.code_checks(
        {"brief": brief, "program": program, "layout": layout, "area_table": area}, lookup_citations=False)
    blockers = [issue for issue in issues if requires_repair(issue)]
    unknown = reviewer.verification_items(checks)
    matches = not any(check["dat"] is False and check["nguon"] == "Brief và bảng diện tích" for check in checks)
    technical = not any(check["dat"] is False and check["loai"] == "Kỹ thuật" for check in checks)
    metrics.update(tong_dien_tich_san=area["tong_dien_tich_san"], dien_tich_xay_dung=area["dien_tich_xay_dung"],
                   so_phong=area["so_phong"], chenh_lech=cost["chenh_lech"],
                   mat_do=area["mat_do_xay_dung"], kha_thi=technical, chi_phi=cost["tong_chi_phi"],
                   vuot_pct=cost["vuot_pct"], khop_yeu_cau=matches)
    pros = ["Khớp số phòng và số tầng được yêu cầu."] if matches and technical else []
    if rear:
        pros.append(f"Có sân sau {vn_num(rear)} m để bố trí khoảng thoáng.")
    cons = ["Chừa sân sau làm giảm phần chiều sâu dành cho các phòng." if rear else
            "Cần rà soát lấy sáng phía sau vì phương án chưa chừa sân sau."]
    if cost["vuot_pct"] > 0:
        cons.append(f"Cao hơn mốc ngân sách {'giả định' if budget_assumed(brief) else 'đã nhập'} "
                    f"{vn_num(cost['vuot_pct'] * 100)}%.")
    if unknown:
        cons.append(f"Còn {len(unknown)} tiêu chí cần xác minh trước khi chốt thiết kế.")
    result.update(eligible=not blockers, loi=blockers, can_xac_minh=unknown, kiem_tra=checks, uu_diem=pros, han_che=cons,
                  cong_nang={f"Tầng {floor['tang']}": [room["ten"] for room in floor["phong"]
                                                     if room["loai"] not in ("hanh_lang", "san")]
                             for floor in area["tang"]})
    return result


def _option_rank(option: dict, brief: dict) -> tuple:
    metrics = option["chi_so"]
    target = brief["yeu_cau_khac"]
    over = 0 if budget_assumed(brief) else max(0, metrics["vuot_pct"])
    preference = (metrics["chi_phi"] if "Ưu tiên tiết kiệm chi phí" in target else
                  metrics["cap_hoan_thien"] != "cao cấp" if "Hoàn thiện cao cấp" in target else 0)
    return (over > BUDGET_TOLERANCE, over if over > BUDGET_TOLERANCE else 0, preference,
            len(option["can_xac_minh"]), metrics["dien_tich_xay_dung"] if option["can_xac_minh"] else 0,
            over, metrics["chi_phi"], option["id"])


@agent_node("cost_estimator", stage="compare_options")
def compare_options(state: dict) -> dict:
    brief = state["brief"]
    options = [evaluate_option(brief, option) for option in state["options"]]
    eligible = sorted((opt for opt in options if opt["eligible"]), key=lambda opt: _option_rank(opt, brief))
    current_id = state["program"]["phuong_an"]
    current = next(opt for opt in options if opt["id"] == current_id)
    estimated = [opt for opt in options if "chi_phi" in opt["chi_so"]]
    if len(estimated) > 1:
        lowest = min(opt["chi_so"]["chi_phi"] for opt in estimated)
        highest = max(opt["chi_so"]["chi_phi"] for opt in estimated)
        if lowest < highest:
            for opt in estimated:
                if opt["chi_so"]["chi_phi"] == lowest:
                    opt["uu_diem"].append("Dự toán thấp nhất trong các phương án đã tính được chi phí.")
    result = {"options": options, "recommended_option": None,
              "_output": {"phuong_an": [{k: v for k, v in o.items() if k != "program"} for o in options]}}
    if not eligible:
        issues = current["loi"]
        result["_output"]["loi"] = issues
        return {**result, "route": "coordinate_repair", "feedback": issues, "review_issues": issues,
                "repair_target": reviewer.repair_target(issues), "repair_fallback": "end",
                "feedback_source": "compare_options", "_feedback": True, "_to": "project_manager",
                "_summary": "Các phương án cần xử lý lỗi hình học, sai lệch brief hoặc vi phạm đã xác minh"}
    recommended = eligible[0]
    metrics = recommended["chi_so"]
    budget = "mốc ngân sách giả định" if budget_assumed(brief) else "ngân sách đã nhập"
    reasons = [f"Đáp ứng công năng và các kiểm tra hình học của ứng dụng. Dự toán {vnd(metrics['chi_phi'])}, "
               f"chênh {vn_num(metrics['vuot_pct'] * 100)}% so với {budget}."]
    if metrics["vuot_pct"] > BUDGET_TOLERANCE and not budget_assumed(brief):
        reasons.append("Các lựa chọn khả thi đều vượt mức chênh 10%. Ưu tiên phương án gần ngân sách nhất để điều chỉnh.")
    if recommended["can_xac_minh"]:
        reasons.append(f"Còn {len(recommended['can_xac_minh'])} tiêu chí cần xác minh. Diện tích chiếm đất "
                       f"{vn_num(metrics['dien_tich_xay_dung'])} m² được cân nhắc để giảm phần diện tích có thể phải bố trí lại.")
    recommended["ly_do_uu_tien"] = " ".join(reasons)
    keep_selection = (state.get("selected_by_user") or state.get("iteration", 0) > 0) and current["eligible"]
    selected = current if keep_selection else recommended
    program = selected["program"]
    concept = {**(state.get("concept_plan") or {}), "so_tang": program["so_tang"], "vat_lieu": program["vat_lieu"]}
    result["_output"].update(uu_tien=recommended["id"], da_chon=selected["id"], ly_do=recommended["ly_do_uu_tien"])
    return {**result, "recommended_option": recommended["id"], "program": program, "concept_plan": concept,
            "revision_id": program["revision_id"], "selected_by_user": bool(keep_selection and state.get("selected_by_user")),
            "review_issues": [],
            "route": "drafter", "_to": "drafter",
            "_summary": f"So sánh {len(options)} phương án. Đề xuất {recommended['id']}, tiếp tục với {selected['id']}"}


def cost_notes(cost: dict) -> str:
    base = (f"Tổng chi phí dự kiến {vnd(cost['tong_chi_phi'])} cho {vn_num(cost['dt_san_hoan_thien'])} m² sàn hoàn thiện "
            f"(bình quân {vnd(cost['chi_phi_m2_san'])}/m²), gói hoàn thiện '{cost['cap_hoan_thien']}'. ")
    if cost["vuot_pct"] > BUDGET_TOLERANCE:
        base += (f"Vượt ngân sách {vn_num(cost['vuot_pct'] * 100)}%; phương án tiết kiệm hiệu quả nhất: "
                 f"{max(cost['tiet_kiem'], key=lambda s: s['tiet_kiem'])['phuong_an']}.")
    elif cost["vuot_pct"] > 0:
        base += f"Vượt nhẹ {vn_num(cost['vuot_pct'] * 100)}% (trong ngưỡng 10%), có thể bù bằng dự phòng hoặc thương lượng."
    else:
        base += f"Trong ngân sách, còn dư {vnd(-cost['chenh_lech'])}."
    txt = invoke_text("Bạn là kỹ sư dự toán xây dựng nhà phố tại Việt Nam.",
                      "Viết 2–3 câu ghi chú cho chủ nhà dựa trên thông tin sau, giữ nguyên mọi con số, "
                      f"không thêm số mới:\n{base}")
    numbers = r"\d+(?:[.,]\d+)*"
    return txt if txt and re.findall(numbers, txt) == re.findall(numbers, base) else base


@agent_node("cost_estimator")
def run(state: dict) -> dict:
    budget = state["brief"]["ngan_sach"]
    cost = compute_cost(state["area_table"], state["layout"], state["program"], budget)
    notes = cost_notes(cost)
    assumed = budget_assumed(state["brief"])
    if assumed:
        notes = "Ngân sách chưa được xác nhận. Các mức chênh lệch so với mốc giả định chỉ dùng để tham khảo. " + notes
    cost["ghi_chu"] = notes
    cost["ngan_sach_gia_dinh"] = assumed
    program = state["program"]
    option = None
    if option_stamp(program):
        assessment = state.get("brief_assessment") or {}
        review = state.get("review") or {}
        option = {"stamp": option_stamp(program), "label": option_label(program), "notes": [
            *(("Giả định thiết kế", "", note) for note in selected_assumptions(state)),
            *(("Cần bổ sung", "", note) for note in assessment.get("needs_confirmation", [])),
            *(("Cần xác minh", item["muc"], item["noi_dung"]) for item in review.get("chua_du_can_cu", [])),
        ]}
    path = write_cost_xlsx(cost, state["area_table"], state["brief"],
                           Path(state["output_dir"]) / "drafts" / uuid4().hex / "du_toan.xlsx", notes, option=option)
    total_ty = cost["tong_chi_phi"] / 1e9
    if cost["vuot_pct"] > BUDGET_TOLERANCE and not assumed:
        fb = [{"loai": "Ngân sách", "phan_loai": "ngan_sach", "ma": "VUOT_NGAN_SACH", "muc": "Vượt ngân sách",
               "hien_tai": f"{vn_num(total_ty, 2)} tỷ", "cho_phep": f"≤ {vn_num(budget / 1e9 * (1 + BUDGET_TOLERANCE), 2)} tỷ",
               "noi_dung": f"Chi phí vượt {vn_num(cost['vuot_pct'] * 100)}% ngân sách",
               "de_xuat": "; ".join(s["phuong_an"] for s in cost["tiet_kiem"][:2]),
               "du_lieu": {"vuot_pct": cost["vuot_pct"]}}]
        return {"cost": cost, "cost_file": str(path), "route": "coordinate_repair", "feedback": fb,
                "budget_issues": fb, "repair_target": "concept_architect", "repair_fallback": "pm_report",
                "feedback_source": "cost_estimator", "_feedback": True, "_to": "project_manager",
                "_summary": f"❌ {vn_num(total_ty, 2)} tỷ, vượt ngân sách {vn_num(cost['vuot_pct'] * 100)}% > {BUDGET_TOLERANCE:.0%}",
                "_output": {k: cost[k] for k in ("tong_chi_phi", "vuot_pct", "cap_hoan_thien", "chi_phi_m2_san")}}
    return {"budget_issues": [], "cost": cost, "cost_file": str(path), "route": "pm_report", "_to": "project_manager",
            "_summary": f"{vn_num(total_ty, 2)} tỷ ({'+' if cost['vuot_pct'] >= 0 else ''}{vn_num(cost['vuot_pct'] * 100)}% so với ngân sách)",
            "_output": {k: cost[k] for k in ("tong_chi_phi", "vuot_pct", "cap_hoan_thien", "chi_phi_m2_san")}}
