"""Tiêu chí chất lượng theo bước và phép đối chiếu bằng dữ liệu của từng lần thực hiện."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from math import isclose, isfinite
from typing import NamedTuple


VERSION = "task-quality-v1"
GROUPS = {"requirement": ("Đáp ứng yêu cầu", 40), "accuracy": ("Chính xác, nhất quán", 30),
          "professional": ("Chất lượng chuyên môn", 20), "handoff": ("Bàn giao đầy đủ", 10)}


def fields(label: str, *paths: str) -> dict:
    return {"label": label, "rule": "fields-v1", "fields": list(paths)}


def equal(label: str, *pairs: tuple[str, str]) -> dict:
    return {"label": label, "rule": "equal-v1", "pairs": [list(pair) for pair in pairs]}


def check(label: str, rule: str) -> dict:
    return {"label": label, "rule": rule}


PACKAGE = ("ban_ve_pdf:pdf", "ban_ve_dxf_zip:zip", "thuyet_minh_docx:docx", "du_toan_xlsx:xlsx")
PACKAGE_3D = (*PACKAGE, "mo_hinh_3d_glb:glb", "mo_hinh_3d_dxf:dxf")
COMPARE = (
    fields("Bảng kết quả đối chiếu có danh sách phương án và đầu mối xử lý", "options:items", "route:text"),
    check("Mã phương án được đối chiếu đầy đủ và mã đề xuất thuộc nhóm khả thi", "options-v1"),
    "Đánh giá cách giải thích đánh đổi giữa ngân sách, tính khả thi và giả định.",
    fields("Đã ghi danh sách so sánh trong đầu ra bàn giao", "chi_tiet_agent.phuong_an:items"),
)

# Thứ tự các tiêu chí trong mỗi bước tương ứng với GROUPS. Mã phép tính được giữ theo phiên bản.
STAGE_RUBRICS = {
    "project_manager": (
        fields("Có mã lượt, giới hạn vòng sửa và lựa chọn phong thủy",
               "chi_tiet_agent.run_id:text", "chi_tiet_agent.max_iterations:count",
               "chi_tiet_agent.fengshui_enabled:flag"),
        equal("Thông tin khởi tạo khớp các lựa chọn đã giao",
              ("run_id", "chi_tiet_agent.run_id"), ("max_iterations", "chi_tiet_agent.max_iterations"),
              ("fengshui_enabled", "chi_tiet_agent.fengshui_enabled")),
        "Đánh giá việc nêu rõ mục tiêu, phạm vi và những quyết định cần xác nhận trước khi thiết kế.",
        check("Chuyển việc đến bước Phân tích yêu cầu", "start-route-v1"),
    ),
    "requirements_analyst": (
        check("Có brief với kích thước hợp lệ hoặc câu hỏi rõ ràng khi bị chặn", "brief-contract-v1"),
        check("Brief khớp các trường có cấu trúc do người dùng cung cấp", "explicit-brief-v1"),
        "Đánh giá cách nhận diện mâu thuẫn, chất lượng giả định và câu hỏi xác nhận theo yêu cầu gốc.",
        fields("Bàn giao câu hỏi, mâu thuẫn và mục cần xác nhận",
               "brief_assessment.questions:list", "brief_assessment.conflicts:list",
               "brief_assessment.needs_confirmation:list"),
    ),
    "plan_options": (
        fields("Có hướng so sánh và danh sách vướng mắc về nguồn",
               "option_brief.huong_so_sanh:items", "option_brief.vuong_mac_nguon:list"),
        equal("Thông tin cần bổ sung khớp với kết quả phân tích",
              ("brief_assessment.needs_confirmation", "option_brief.thong_tin_can_bo_sung")),
        "Đánh giá độ khác biệt hữu ích giữa các hướng thiết kế và thứ tự xác minh các giả định.",
        fields("Bàn giao hướng so sánh và các nội dung đã có căn cứ", "route:text", "option_brief.da_co_can_cu:list"),
    ),
    "concept_architect": (
        fields("Có số tầng, phong cách, vật liệu, giải pháp gió và sáng",
               "concept_plan.so_tang:positive", "concept_plan.phong_cach:text", "concept_plan.vat_lieu:map",
               "concept_plan.thong_gio:items", "concept_plan.chieu_sang:items"),
        check("Số tầng khớp brief nếu người dùng đã chốt", "concept-floors-v1"),
        "Đánh giá sự phù hợp khí hậu, hướng nhà, quy mô, vật liệu và chất lượng giải thích phương án.",
        fields("Có diễn giải để kiến trúc sư công năng tiếp tục", "concept:text", "route:text"),
    ),
    "architect": (
        check("Số phòng ngủ, phòng thờ và phòng làm việc đã xác định khớp brief", "room-counts-v1"),
        check("Số tầng, mã phòng và mã phiên bản công năng nhất quán", "program-v1"),
        "Đánh giá luồng giao thông, quan hệ kề, ưu tiên bố trí và chất lượng xử lý phản hồi.",
        fields("Bàn giao danh sách phương án công năng cho bước đối chiếu", "options:items", "route:text"),
    ),
    "compare_options": COMPARE,
    "check_edited_option": COMPARE,
    "drafter": (
        fields("Có hình học theo tầng và bảng diện tích", "layout.floors:map", "area_table.tang:items"),
        check("Bảng diện tích khớp với phép tính lại từ hình học đã bàn giao", "drawing-area-v1"),
        "Đánh giá độ rõ bản vẽ, tính khả thi mặt bằng và cách thể hiện kích thước, ký hiệu.",
        fields("Manifest có tham chiếu PDF, DXF ZIP và danh sách tờ", "drawings.pdf:pdf",
               "drawings.dxf_zip:zip", "drawings.sheets:items"),
    ),
    "reviewer": (
        fields("Có bảng kiểm tra và danh sách nội dung chưa đủ căn cứ", "review.kiem_tra:items",
               "review.chua_du_can_cu:list"),
        check("Mục quy chuẩn ghi phạm vi, nguồn trích dẫn hoặc lý do chưa kết luận", "evidence-v1"),
        "Đánh giá cách đọc phạm vi áp dụng, chất lượng phân tích vấn đề và ưu tiên xác minh.",
        fields("Bàn giao danh sách phát hiện, cảnh báo và nhận xét", "review.loi:list",
               "review.canh_bao:list", "review.nhan_xet:text"),
    ),
    "fengshui_advisor": (
        fields("Có trạng thái dữ liệu gia chủ và danh sách kiểm tra bố trí",
               "fengshui.thong_tin.co_du_lieu:flag", "fengshui.bo_tri:list"),
        check("Kết quả kiểm tra bố trí khớp phép tính từ hình học và brief", "fengshui-v1"),
        "Đánh giá tính tùy chọn, khả năng áp dụng gợi ý và cách diễn đạt khi thiếu dữ liệu gia chủ.",
        fields("Bàn giao danh sách gợi ý trong mục phong thủy riêng", "fengshui.goi_y:list", "route:text"),
    ),
    "cost_estimator": (
        fields("Có hạng mục, chi phí xây dựng, dự phòng và mốc ngân sách",
               "cost.hang_muc:items", "cost.chi_phi_xay_dung:number", "cost.du_phong:number", "cost.ngan_sach:number"),
        check("Thành tiền, tổng dự toán và chênh lệch khớp các phép tính từ bảng dòng", "cost-math-v1"),
        "Đánh giá cơ sở khối lượng, giả định đơn giá, dự phòng và mức khả thi của đề xuất tiết kiệm.",
        fields("Có tham chiếu XLSX, ghi chú và phương án tiết kiệm", "cost_file:xlsx", "cost.ghi_chu:text",
               "cost.tiet_kiem:list"),
    ),
    "coordinate_repair": (
        fields("Có bước nhận xử lý hoặc đường chuyển tiếp khi dừng sửa", "route:text"),
        check("Nhánh sửa và bộ đếm khớp giới hạn vòng sửa đã giao", "repair-route-v1"),
        "Đánh giá việc ưu tiên vấn đề và xác định bước chịu trách nhiệm dựa trên bằng chứng.",
        check("Ghi vấn đề cần sửa, vấn đề còn lại hoặc phản hồi đã xử lý", "repair-handoff-v1"),
    ),
    "pm_report": (
        fields("Manifest hồ sơ nháp có tham chiếu đủ tài liệu và mô hình 3D", *("draft_files." + f for f in PACKAGE_3D)),
        equal("Tệp bản vẽ và dự toán trong gói khớp đầu vào",
              ("drawings.pdf", "draft_files.ban_ve_pdf"), ("drawings.dxf_zip", "draft_files.ban_ve_dxf_zip"),
              ("cost_file", "draft_files.du_toan_xlsx")),
        "Đánh giá sự rõ ràng của thuyết minh, giả định và các điểm còn phải xác minh.",
        fields("Bàn giao đường dẫn thuyết minh và các vấn đề còn lại", "description_file:docx",
               "remaining_issues:list", "route:text"),
    ),
    "final_reviewer": (
        fields("Có kết quả đối chiếu và danh sách sai lệch", "final_review.dat:flag", "final_review.loi:list"),
        check("Báo đúng chênh lệch số tầng giữa công năng và bảng diện tích", "final-floors-v1"),
        "Đánh giá phạm vi kiểm tra, bằng chứng sai lệch và việc chỉ đúng bước cần xử lý.",
        check("Chuyển xuất hồ sơ hoặc điều phối sửa theo danh sách sai lệch", "final-route-v1"),
    ),
    "propose_adjustment": (
        fields("Có lý do chưa đạt và danh sách đề xuất điều chỉnh", "adjustment.ly_do:list", "adjustment.de_xuat:list"),
        check("Mỗi đề xuất có yêu cầu mới, dự toán và nằm trong ngân sách cho phép", "adjustment-v1"),
        "Đánh giá mức hợp lý của đánh đổi giữa công năng, quy mô và ngân sách trong các đề xuất.",
        fields("Đã bàn giao đề xuất cho chủ nhà", "adjustment.de_xuat:list"),
    ),
    "publish": (
        fields("Manifest hồ sơ xuất có tham chiếu đủ PDF, DXF ZIP, DOCX, XLSX và mô hình 3D",
               *("final_files." + f for f in PACKAGE_3D)),
        check("Tên các tệp trong gói xuất khớp gói đã đối chiếu", "publish-files-v2"),
        "Đánh giá cách đóng gói, nhận diện phiên bản và khả năng truy xuất bộ hồ sơ.",
        fields("Gói xuất có tham chiếu nhật ký CSV", "final_files.timeline_csv:csv"),
    ),
}


# Agent tùy biến (mã custom_…): một bộ tiêu chí chung vì nhiệm vụ do người dùng tự mô tả.
CUSTOM_RUBRIC = (
    check("Có nhận xét do model lập theo nhiệm vụ được giao", "custom-note-v1"),
    fields("Nhận xét ghi bước gắn kèm và model đã dùng", "chi_tiet_agent.after:text", "chi_tiet_agent.model:text"),
    "Đánh giá mức bám dữ liệu đã chọn, tính cụ thể và khả thi của kiến nghị.",
    fields("Bàn giao nhận xét cho màn hình duyệt và trang Kết quả", "chi_tiet_agent.text:text"),
)


def rubric_for(stage: str) -> tuple:
    return CUSTOM_RUBRIC if stage.startswith("custom_") else STAGE_RUBRICS[stage]


def snapshot(stage: str, acceptance: str) -> dict:
    criteria = []
    for (group, (_, points)), entry in zip(GROUPS.items(), rubric_for(stage), strict=True):
        definition = {"label": entry, "rule": "manual"} if isinstance(entry, str) else deepcopy(entry)
        criteria.append({"group": group, "points": points, **definition})
    return {"version": VERSION, "stage": stage, "acceptance": acceptance, "criteria": criteria}


MISSING = object()


class Evidence(NamedTuple):
    status: str
    detail: str


def read(data: dict, path: str):
    value = data
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return MISSING
        value = value[key]
    return value


def missing(detail: str) -> Evidence:
    return Evidence("missing", detail)


def measured(passes: bool, detail: str) -> Evidence:
    return Evidence("passed" if passes else "failed", detail)


def number(value) -> bool:
    return type(value) in (int, float) and isfinite(value)


def text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


FIELD_TYPES = {
    "text": text, "number": number, "flag": lambda v: type(v) is bool,
    "positive": lambda v: type(v) is int and v > 0, "count": lambda v: type(v) is int and v >= 0,
    "list": lambda v: isinstance(v, list), "items": lambda v: isinstance(v, list) and bool(v),
    "map": lambda v: isinstance(v, dict) and bool(v),
}


def field_check(output: dict, requirements: list[str]) -> Evidence:
    absent, invalid, verified = [], [], []
    for field in requirements:
        path, kind = field.split(":")
        value = read(output, path)
        if value is MISSING or value is None:
            absent.append(path)
            continue
        valid = FIELD_TYPES[kind](value) if kind in FIELD_TYPES else text(value) and value.lower().endswith("." + kind)
        (verified if valid else invalid).append(path)
    if absent:
        return missing("Thiếu dữ liệu lưu tại " + ", ".join(absent))
    if invalid:
        return measured(False, "Trường đã ghi sai định dạng hoặc rỗng tại " + ", ".join(invalid))
    return measured(True, "Đã đối chiếu các trường " + ", ".join(verified))


def paired(inputs: dict, output: dict, pairs: list[list[str]]) -> Evidence:
    inconsistent, compared = [], []
    for source, target in pairs:
        before, after = read(inputs, source), read(output, target)
        if before is MISSING or after is MISSING:
            return missing(f"Thiếu mốc đối chiếu {source} → {target}")
        compared.append(f"{source} → {target}")
        if type(before) is not type(after) or before != after:
            inconsistent.append(compared[-1])
    return measured(not inconsistent, ("Khác giá trị đã giao ở " if inconsistent else "Khớp các cặp trường ")
                    + ", ".join(inconsistent or compared))


def brief_contract(inputs: dict, output: dict) -> Evidence:
    if output.get("outcome") == "needs_input":
        report = output.get("brief_assessment") or {}
        entries = [note for key in ("questions", "conflicts") if isinstance(report.get(key), list)
                   for note in report[key] if text(note)]
        if not entries:
            return missing("Chưa lưu câu hỏi hoặc mâu thuẫn để đối chiếu khi thiếu đầu vào.")
        return measured(True, f"Đã ghi {len(entries)} câu hỏi hoặc mâu thuẫn thay cho brief chưa chốt.")
    dims = [read(output, "brief.lo_dat." + key) for key in ("rong", "dai")]
    if MISSING in dims or None in dims:
        return missing("Thiếu brief có kích thước lô đất đã lưu.")
    valid = all(number(value) and value > 0 for value in dims)
    return measured(valid, f"Kích thước trong brief {dims[0]} × {dims[1]} m, cần hai số dương.")


BRIEF_FIELDS = {
    "rong": "brief.lo_dat.rong", "dai": "brief.lo_dat.dai", "tinh": "brief.lo_dat.tinh",
    "so_nguoi": "brief.gia_dinh.so_nguoi", "so_tang": "brief.yeu_cau_phong.so_tang",
    "phong_ngu": "brief.yeu_cau_phong.phong_ngu", "ngan_sach": "brief.ngan_sach",
}


def explicit_brief(inputs: dict, output: dict) -> Evidence:
    if not isinstance(inputs.get("request_fields"), dict):
        return missing("Chưa lưu trường nhập có cấu trúc.")
    pairs = [[f"request_fields.{key}", path] for key, path in BRIEF_FIELDS.items()
             if inputs["request_fields"].get(key) is not None]
    if not pairs:
        return Evidence("na", "Người dùng chưa nhập trường có cấu trúc. Tiêu chí này chỉ đối chiếu các trường đó.")
    for source, target in pairs:
        before, after = read(inputs, source), read(output, target)
        if after is MISSING or after is None:
            return missing(f"Chưa có giá trị brief để đối chiếu {source}.")
        if before != after:
            return measured(False, f"{source} ghi {before}, brief ghi {after}.")
    return measured(True, f"Khớp {len(pairs)} trường người dùng điền trực tiếp.")


def concept_floors(inputs: dict, output: dict) -> Evidence:
    requested = read(inputs, "brief.yeu_cau_phong.so_tang")
    supplied = read(output, "concept_plan.so_tang")
    if requested is None:
        return Evidence("na", "Brief lưu rõ số tầng chưa chốt và giao kiến trúc sư đề xuất.")
    if type(requested) is not int or type(supplied) is not int:
        return missing("Cần số tầng đã chốt trong brief và số tầng trong ý tưởng.")
    return measured(requested == supplied, f"Brief đã chốt {requested} tầng · Ý tưởng {supplied} tầng.")


def room_counts(inputs: dict, output: dict) -> Evidence:
    from agents.architect import program_to_rows

    if "brief" in output and output["brief"] != inputs.get("brief"):
        return missing("Brief đã thay đổi trong lần thực hiện. Cần người chấm xác nhận mốc yêu cầu áp dụng.")
    required = read(inputs, "brief.yeu_cau_phong")
    program = output.get("program")
    if not isinstance(required, dict) or not isinstance(program, dict):
        return missing("Thiếu brief hoặc chương trình công năng.")
    counts = Counter(row["loai"] for row in program_to_rows(program))
    keys = {"phong_ngu": "ngu", "phong_tho": "tho", "phong_lam_viec": "lam_viec"}
    assumptions = (inputs["brief"].get("gia_dinh_bo_sung") or [])
    assumed_bedrooms = any(note.startswith("Số phòng ngủ:") for note in assumptions)
    if assumed_bedrooms:
        keys.pop("phong_ngu")
    if not all(type(required.get(key)) is int for key in keys):
        return missing("Thiếu số phòng ngủ, phòng thờ hoặc phòng làm việc trong brief.")
    diff = [f"{key} {counts[room]}/{required[key]}" for key, room in keys.items()]
    return measured(all(counts[room] == required[key] for key, room in keys.items()),
                    "Số phòng công năng/brief · " + ", ".join(diff)
                    + (" · Số phòng ngủ đang là giả định." if assumed_bedrooms else ""))


def program_consistency(inputs: dict, output: dict) -> Evidence:
    plan = output.get("program")
    if not isinstance(plan, dict) or type(plan.get("so_tang")) is not int or not text(output.get("revision_id")):
        return missing("Thiếu số tầng, chương trình công năng hoặc mã phiên bản của lần thực hiện.")
    floors = [rooms for name, rooms in plan.items() if name.startswith("tang_")]
    if not all(isinstance(rooms, list) for rooms in floors):
        return missing("Danh sách phòng theo tầng chưa đủ để đối chiếu.")
    room_ids = [room.get("id") for rooms in floors for room in rooms]
    valid_ids = [ident for ident in room_ids if text(ident)]
    ok = (len(floors) == plan["so_tang"] and len(set(valid_ids)) == len(room_ids)
          and plan.get("revision_id") == output["revision_id"])
    return measured(ok, f"{len(floors)}/{plan['so_tang']} tầng · {len(set(valid_ids))}/{len(room_ids)} mã phòng "
                    f"riêng · Mã phiên bản {'khớp' if plan.get('revision_id') == output['revision_id'] else 'lệch'}.")


def option_consistency(inputs: dict, output: dict) -> Evidence:
    before, after = inputs.get("options"), output.get("options")
    if not isinstance(before, list) or not isinstance(after, list) or "recommended_option" not in output:
        return missing("Thiếu danh sách phương án hoặc kết quả đề xuất.")
    assigned = [item["id"] for item in before]
    calculated = [item["id"] for item in after]
    if not all(type(item.get("eligible")) is bool for item in after):
        return missing("Thiếu trạng thái khả thi của từng phương án.")
    eligible = [item["id"] for item in after if item["eligible"]]
    recommendation = output["recommended_option"]
    if any(item["eligible"] and not number((item.get("chi_so") or {}).get("chi_phi")) for item in after):
        return missing("Chưa có kết quả chi phí cho tất cả phương án khả thi.")
    ok = sorted(assigned) == sorted(calculated) and (recommendation in eligible if eligible else recommendation is None)
    return measured(ok, f"{len(calculated)}/{len(assigned)} mã phương án · {len(eligible)} khả thi · "
                    f"Mã đề xuất {recommendation or 'chưa có'}.")


def drawing_area(inputs: dict, output: dict) -> Evidence:
    from tools.layout_algorithm import build_area_table

    if not all(isinstance(item, dict) for item in (inputs.get("brief"), output.get("layout"), output.get("area_table"))):
        return missing("Thiếu brief, hình học hoặc bảng diện tích. Chưa xác định trách nhiệm.")
    recalculated = build_area_table(output["layout"], inputs["brief"])
    recorded = output["area_table"]
    keys = ("so_tang", "so_phong", "tong_dien_tich_san", "tang")
    if not all(key in recorded for key in keys):
        return missing("Thiếu số tầng, số phòng hoặc dữ liệu diện tích đã lưu.")
    unequal = [key for key in keys if recalculated[key] != recorded[key]]
    return measured(not unequal, "Tính lại từ hình học đã lưu · " + (
                    "Lệch " + ", ".join(unequal) if unequal else
                    f"{recalculated['so_tang']} tầng và {recalculated['tong_dien_tich_san']} m² sàn, khớp theo từng tầng."))


def regulation_evidence(inputs: dict, output: dict) -> Evidence:
    rows = read(output, "review.kiem_tra")
    if not isinstance(rows, list) or not rows:
        return missing("Chưa có bảng kiểm định.")
    regulatory = [row for row in rows if row.get("loai") == "Quy chuẩn"]
    if not regulatory:
        return missing("Bảng chưa có mục quy chuẩn để kiểm tra cách ghi căn cứ.")
    incomplete = []
    for row in regulatory:
        citation = row.get("trich_dan")
        valid = text(row.get("pham_vi")) and (
            text(row.get("ly_do")) if "dat" in row and row["dat"] is None else
            type(row.get("dat")) is bool and row.get("da_xac_minh") is True
            and text(row.get("nguon")) and isinstance(citation, dict)
            and all(text(citation.get(key)) for key in ("nguon", "muc", "trich")))
        if not valid:
            incomplete.append(row.get("muc", "Mục chưa đặt tên"))
    return measured(not incomplete, ("Mục thiếu căn cứ hoặc cách ghi rõ lý do · " + ", ".join(incomplete)) if incomplete
                    else f"{len(regulatory)} mục có phạm vi và trích dẫn hoặc lý do chưa kết luận.")


def fengshui(inputs: dict, output: dict) -> Evidence:
    from agents.fengshui_advisor import fengshui_checks

    saved = read(output, "fengshui.bo_tri")
    if not isinstance(saved, list) or not inputs.get("layout") or not inputs.get("brief"):
        return missing("Thiếu bảng gợi ý bố trí, hình học hoặc brief.")
    _, checks, _, _ = fengshui_checks(inputs)
    return measured(saved == checks, f"Phép kiểm từ hình học đã lưu cho {len(checks)} mục · Kết quả ghi {len(saved)} mục.")


def cost_math(inputs: dict, output: dict) -> Evidence:
    cost = output.get("cost") or {}
    lines = cost.get("hang_muc")
    observed = ("chi_phi_xay_dung", "du_phong_pct", "du_phong", "tong_chi_phi", "ngan_sach", "chenh_lech")
    if not isinstance(lines, list) or not lines or not all(number(cost.get(key)) for key in observed):
        return missing("Thiếu đơn giá, số tiền, tỷ lệ dự phòng hoặc số tổng để đối chiếu.")
    if not all(number(line.get(key)) for line in lines for key in ("kl", "don_gia", "thanh_tien")):
        return missing("Có hạng mục chưa đủ khối lượng, đơn giá và thành tiền.")
    subtotals = [line["kl"] * line["don_gia"] for line in lines]
    base = sum(subtotals)
    reserve = base * cost["du_phong_pct"]
    total = base + reserve
    expected = {"chi_phi_xay_dung": round(base), "du_phong": round(reserve),
                "tong_chi_phi": round(total), "chenh_lech": round(total - cost["ngan_sach"])}
    mismatches = [key for key, value in expected.items() if value != cost[key]]
    bad_lines = sum(not isclose(line["thanh_tien"], subtotal, rel_tol=1e-12, abs_tol=1e-6)
                    for line, subtotal in zip(lines, subtotals, strict=True))
    return measured(not mismatches and bad_lines == 0,
                    f"Tính lại {expected['tong_chi_phi']:,} đ · Đã ghi {cost['tong_chi_phi']:,} đ · "
                    f"{bad_lines} dòng lệch · Tổng lệch ở {', '.join(mismatches) or 'không có mục nào'}.")


def repair_route(inputs: dict, output: dict) -> Evidence:
    needed = ("feedback", "iteration", "max_iterations", "repair_target", "repair_fallback")
    if not all(key in inputs for key in needed) or not text(output.get("route")):
        return missing("Thiếu nhánh, vòng sửa hoặc phản hồi tại thời điểm giao.")
    issues = [item for item in inputs["feedback"] if item.get("ma") != "THIEU_CAN_CU"
              and item.get("phan_loai") != "tham_chieu"]
    can_repair = bool(issues) and inputs["iteration"] < inputs["max_iterations"]
    expected = inputs["repair_target"] if can_repair else inputs["repair_fallback"]
    iteration = inputs["iteration"] + int(can_repair)
    actual = output.get("iteration", inputs["iteration"])
    return measured(output["route"] == expected and actual == iteration,
                    f"Nhánh theo dữ liệu giao việc {expected}, đã ghi {output['route']} · Vòng {actual}/{iteration}.")


def repair_handoff(inputs: dict, output: dict) -> Evidence:
    return field_check(output, ["chi_tiet_agent.loi:list"] if "chi_tiet_agent" in output else ["feedback:list"])


def final_floors(inputs: dict, output: dict) -> Evidence:
    found = read(output, "final_review.loi")
    planned, drawn = read(inputs, "program.so_tang"), read(inputs, "area_table.so_tang")
    if not isinstance(found, list) or type(planned) is not int or type(drawn) is not int:
        return missing("Chưa có báo cáo đối chiếu hoặc cặp số tầng làm bằng chứng.")
    flagged = any(row.get("ma") == "MAT_BANG_SAI_TANG" for row in found)
    return measured(flagged == (planned != drawn),
                    f"Công năng {planned} tầng · Bảng diện tích {drawn} tầng · "
                    f"{'Có' if flagged else 'Chưa ghi'} mã MAT_BANG_SAI_TANG.")


def final_route(inputs: dict, output: dict) -> Evidence:
    issues = read(output, "final_review.loi")
    if not isinstance(issues, list) or not text(output.get("route")):
        return missing("Chưa ghi danh sách sai lệch hoặc bước nhận việc.")
    expected = "coordinate_repair" if issues else "publish"
    return measured(output["route"] == expected, f"{len(issues)} sai lệch ghi nhận · Nhánh {output['route']} · Dự kiến {expected}.")


def publish_files(inputs: dict, output: dict, package: tuple = PACKAGE) -> Evidence:
    mismatches = []
    for field in package:
        key, _ = field.split(":")
        first, last = read(inputs, f"draft_files.{key}"), read(output, f"final_files.{key}")
        if not text(first) or not text(last):
            return missing(f"Thiếu đường dẫn trong gói nháp hoặc gói xuất của {key}.")
        if first.replace("\\", "/").split("/")[-1] != last.replace("\\", "/").split("/")[-1]:
            mismatches.append(key)
    return measured(not mismatches, "Tên tệp lệch ở " + ", ".join(mismatches) if mismatches
                    else f"{'Bốn' if package is PACKAGE else 'Sáu'} tên tệp trong manifest khớp gói nháp đã giao. "
                         "Chỉ đối chiếu tham chiếu đã lưu.")


def publish_files_3d(inputs: dict, output: dict) -> Evidence:
    return publish_files(inputs, output, PACKAGE_3D)


def adjustment_proposals(inputs: dict, output: dict) -> Evidence:
    from config import BUDGET_TOLERANCE

    proposals = read(output, "adjustment.de_xuat")
    if not isinstance(proposals, list):
        return missing("Chưa ghi danh sách đề xuất điều chỉnh.")
    if not proposals:
        return missing("Không có đề xuất khả thi để đối chiếu.")
    bad = [p.get("tieu_de", "?") for p in proposals
           if not text(p.get("request")) or not isinstance(p.get("chi_phi"), (int, float))
           or p.get("vuot_pct", 1) > BUDGET_TOLERANCE]
    return measured(not bad, f"{len(proposals)} đề xuất · " + ("Đều có yêu cầu mới và dự toán trong ngưỡng ngân sách."
                                                            if not bad else "Thiếu dữ liệu ở: " + "; ".join(bad)))


def start_route(inputs: dict, output: dict) -> Evidence:
    return (measured(output["route"] == "requirements_analyst", f"Nhánh ghi nhận {output['route']}.")
            if text(output.get("route")) else missing("Chưa ghi bước nhận việc."))


def custom_note(inputs: dict, output: dict) -> Evidence:
    """Agent tùy biến: có nhận xét thật từ model (không phải bản ghi bỏ qua khi thiếu model)."""
    note = output["chi_tiet_agent"]
    if note.get("status") != "done":
        return missing("Chưa có model khả dụng nên agent tùy biến chưa lập nhận xét.")
    return measured(text(note.get("text")), "Có nhận xét do model lập." if text(note.get("text"))
                    else "Model trả nhận xét rỗng.")


CHECKS = {
    "start-route-v1": start_route, "brief-contract-v1": brief_contract, "explicit-brief-v1": explicit_brief,
    "concept-floors-v1": concept_floors, "room-counts-v1": room_counts, "program-v1": program_consistency,
    "options-v1": option_consistency, "drawing-area-v1": drawing_area, "evidence-v1": regulation_evidence,
    "fengshui-v1": fengshui, "cost-math-v1": cost_math, "repair-route-v1": repair_route, "repair-handoff-v1": repair_handoff,
    "final-floors-v1": final_floors, "final-route-v1": final_route, "publish-files-v1": publish_files, "publish-files-v2": publish_files_3d,
    "adjustment-v1": adjustment_proposals,
    "custom-note-v1": custom_note,
}


def assessable(attempt: dict) -> bool:
    return bool(attempt.get("processed") and isinstance(attempt.get("output"), dict) and attempt["output"])


def _auto(criterion: dict, attempt: dict) -> Evidence:
    if not assessable(attempt):
        return missing("Chưa có đầu ra đã xử lý để đối chiếu. Chưa xác định trách nhiệm.")
    inputs, output = attempt.get("input") or {}, attempt["output"]
    rule = criterion["rule"]
    try:
        if rule == "fields-v1":
            return field_check(output, criterion["fields"])
        if rule == "equal-v1":
            return paired(inputs, output, criterion["pairs"])
        if rule in CHECKS:
            return CHECKS[rule](inputs, output)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, ArithmeticError):
        return missing("Dữ liệu lưu chưa đủ hoặc sai định dạng để chạy phép đối chiếu.")
    return missing("Chưa hỗ trợ phép đối chiếu của phiên bản tiêu chí này.")


def evaluate(attempt: dict, *, manual_score: int | None = None, manual_evidence: str = "") -> dict:
    rubric = attempt.get("rubric")
    if not rubric:
        raise ValueError("Lần thực hiện chưa được gắn bộ tiêu chí khi giao việc.")
    manual = next(item for item in rubric["criteria"] if item["rule"] == "manual")
    if manual_score is not None:
        if type(manual_score) is not int or not 0 <= manual_score <= manual["points"]:
            raise ValueError(f"Điểm chuyên môn cần là số nguyên từ 0 đến {manual['points']}.")
        if not assessable(attempt) or not text(manual_evidence):
            raise ValueError("Cần đầu ra đã xử lý và bằng chứng hoặc nhận xét cụ thể để chấm chuyên môn.")
    rows = []
    for criterion in rubric["criteria"]:
        is_manual = criterion["rule"] == "manual"
        if is_manual:
            rating = Evidence("rated", manual_evidence) if manual_score is not None else missing("Chưa có điểm chuyên môn.")
            score = manual_score
        else:
            rating = _auto(criterion, attempt)
            if rating.status == "failed" and attempt.get("failure_category") in ("missing_input", "infrastructure"):
                rating = missing("Chưa xác định trách nhiệm vì lần thực hiện có thiếu đầu vào hoặc lỗi hạ tầng. "
                                 + rating.detail)
            score = criterion["points"] if rating.status == "passed" else 0 if rating.status == "failed" else None
        rows.append({**criterion, "method": "manual" if is_manual else "automatic", "status": rating.status,
                     "score": score, "evidence": rating.detail})

    def subtotal(items):
        return {"earned": sum(item["score"] for item in items if item["score"] is not None),
                "assessed": sum(item["points"] for item in items if item["score"] is not None),
                "applicable": sum(item["points"] for item in items if item["status"] != "na"),
                "maximum": sum(item["points"] for item in items)}

    auto = subtotal([item for item in rows if item["method"] == "automatic"])
    human = subtotal([item for item in rows if item["method"] == "manual"])
    total = subtotal(rows)
    return {"rubric_version": rubric["version"], "criteria": rows, "automatic": auto, "manual": human, "total": total,
            "status": "partial" if total["assessed"] < total["applicable"] else "complete"}
