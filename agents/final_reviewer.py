"""Đọc lại bộ hồ sơ nháp, kiểm tra số liệu và chỉ ra bước cần sửa."""
from collections import Counter
from io import StringIO
from math import isclose
from zipfile import ZipFile

import ezdxf
from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader
from tools.pycel_compat import ExcelCompiler

from agents.architect import program_to_rows
from agents.base import agent_node
from agents.project_manager import outstanding
from state import DesignIssue, FinalReview
from tools.cost_calc import compute_cost
from tools.design_option import option_stamp
from tools.docx_writer import vn_num, vnd
from tools.drawing_plan import fmt_area
from tools.layout_algorithm import build_area_table


def _drawing_matches(files: dict, state: dict) -> bool:
    floors = state["layout"]["floors"]
    sheets = state["drawings"]["sheets"]
    pdf = PdfReader(files["ban_ve_pdf"])
    stamp = option_stamp(state["program"])
    if (len(pdf.pages) != len(sheets) or len(sheets) != len(floors) + 4
            or (stamp and (pdf.metadata or {}).get("/Subject") != stamp)):
        return False
    with ZipFile(files["ban_ve_dxf_zip"]) as archive:
        if set(archive.namelist()) != {f"{s['so_hieu']}.dxf" for s in sheets}:
            return False
        floor_docs = {}
        for index, sheet in enumerate(sheets):
            name = f"{sheet['so_hieu']}.dxf"
            doc = ezdxf.read(StringIO(archive.read(name).decode("utf-8-sig"), newline=None))
            if stamp and doc.ezdxf_metadata().get("AI_ARCHITECT_OPTION") != stamp:
                return False
            if str(index) in floors:
                floor_docs[index] = doc
        for floor, data in floors.items():
            index = int(floor)
            sheet = sheets[index]
            title = f"Mặt bằng tầng {floor}"
            pdf_text = " ".join(pdf.pages[index].extract_text().split()).upper()
            if sheet["ten"] != title or title.upper() not in pdf_text:
                return False
            doc = floor_docs[index]
            labels = [e.dxf.text for e in doc.modelspace().query("TEXT") if e.dxf.layer == "CHU_PHONG"]
            expected = []
            for room in data["rooms"]:
                if room["loai"] == "hanh_lang":
                    if room["h"] > 2.5:
                        expected.append(room["ten"])
                    continue
                if room["loai"] == "thang":
                    continue
                label, area = room["ten"].upper(), fmt_area(room["dien_tich"])
                if room["h"] < 1.5 and room["loai"] != "gieng_troi":
                    expected.append(label + " " + area)
                else:
                    expected.extend((label, area))
                if " ".join((label + " " + area).split()).upper() not in pdf_text:
                    return False
            if labels != expected:
                return False
    return True


def _doc_matches(path: str, area: dict, cost: dict) -> bool:
    doc = Document(path)
    if cost.get("option_stamp") and doc.core_properties.identifier != cost["option_stamp"]:
        return False
    tables = [[tuple(cell.text for cell in row.cells) for row in table.rows] for table in doc.tables]
    all_rows = [row for table in tables for row in table]
    expected = []
    for floor in area["tang"]:
        expected.extend((floor["ten"], room["ten"], room["kich_thuoc"], vn_num(room["dien_tich"], 2))
                        for room in floor["phong"])
        expected.append((floor["ten"], "Cộng diện tích sàn tầng", "", vn_num(floor["dien_tich_san"], 2)))
    expected.append(("Toàn nhà", "TỔNG DIỆN TÍCH SÀN", "", vn_num(area["tong_dien_tich_san"], 2)))
    area_rows = [table[1:] for table in tables if table and table[0][:2] == ("Tầng", "Phòng / khu vực")]
    costs = [(it["hang_muc"], f"{vn_num(it['kl'], 2)} {it['don_vi']}", vnd(it["don_gia"]),
              vnd(it["thanh_tien"])) for it in cost["hang_muc"]]
    return (area_rows == [expected] and all(row in all_rows for row in costs)
            and ("Số tầng", f"{area['so_tang']} tầng") in all_rows
            and ("TỔNG CHI PHÍ DỰ KIẾN", "", "", vnd(cost["tong_chi_phi"])) in all_rows)


def _cost_matches(path: str, area: dict, cost: dict) -> bool:
    book = load_workbook(path, read_only=True)
    try:
        if cost.get("option_stamp") and book.properties.identifier != cost["option_stamp"]:
            return False
        values = list(book["Dien_tich"].iter_rows(min_row=4, max_col=5, values_only=True))
        floor_rows = [row[1:3] for row in values if isinstance(row[1], str) and row[1].startswith("Sàn tầng ")]
        expected = [(f"Sàn tầng {floor['tang']}", floor["dien_tich_san"]) for floor in area["tang"]]
        marker = next(i for i, row in enumerate(values) if row[1] == "Thống kê diện tích từng phòng")
        rooms = [(row[0], row[1], row[2], row[4]) for row in values[marker + 2:] if any(row)]
        expected_rooms = [(floor["tang"], room["ten"], room["dien_tich"], room["kich_thuoc"])
                          for floor in area["tang"] for room in floor["phong"]]
        if (floor_rows != expected or rooms != expected_rooms or book["Tong_hop"]["B5"].value != cost["ngan_sach"]
                or book["Tong_hop"]["B4"].data_type != "f"):
            return False
        items = cost["hang_muc"]
        details = list(book["Chi_tiet"].iter_rows(min_row=4, max_row=3 + len(items), min_col=2, max_col=6))
        if any(row[0].value != item["hang_muc"] or row[4].data_type != "f" for row, item in zip(details, items)):
            return False
    finally:
        book.close()
    excel = ExcelCompiler(filename=path)
    totals = [("Tong_hop!B4", cost["tong_chi_phi"], 1), ("Tong_hop!B7", cost["vuot_pct"], 1e-3),
              ("Tong_hop!B9", cost["dt_quy_doi"], 0.01)]
    amounts = [(f"Chi_tiet!F{row}", item["thanh_tien"], 1) for row, item in enumerate(items, start=4)]
    return all(isclose(float(excel.evaluate(cell)), expected, rel_tol=0, abs_tol=tolerance)
               for cell, expected, tolerance in totals + amounts)


def audit(state: dict) -> FinalReview:
    issues = []

    def check(ok, code, title, message, target):
        if not ok:
            issues.append(DesignIssue(ma=code, muc=title, noi_dung=message, target=target))

    brief, area, files = state["brief"], state["area_table"], state["draft_files"]
    requested = brief["yeu_cau_phong"]
    program = state["program"]
    stamp = option_stamp(program)
    if stamp:
        check(state.get("revision_id") == program["revision_id"]
              and any(option_stamp(opt["program"]) == stamp for opt in state.get("options") or []),
              "SAI_PHIEN_BAN", "Mã phương án", "Phiên bản công năng khác phương án đang chọn.", "architect")
    counts = area["so_phong"]
    planned = Counter(r["loai"] for r in program_to_rows(program))
    if program.get("san_truoc") and "đỗ xe" in program.get("ten_san_truoc", ""):
        planned["gara"] += 1
    for room, amount in {"ngu": requested["phong_ngu"], "tho": requested["phong_tho"],
                         "gara": int(bool(requested["gara"])), "lam_viec": requested["phong_lam_viec"]}.items():
        code = "THIEU_PHONG" if planned[room] < amount else "THUA_PHONG"
        check(planned[room] == amount, code, "Số phòng so với brief",
              f"{room}: công năng có {planned[room]}, brief yêu cầu {amount}.", "architect")
        check(counts.get(room, 0) == planned[room], "SAI_SO_PHONG", "Số phòng trên bản vẽ",
              f"{room}: bản vẽ có {counts.get(room, 0)}, công năng có {planned[room]}.", "drafter")
    check(requested["so_tang"] is None or requested["so_tang"] == program["so_tang"],
          "SAI_SO_TANG", "Số tầng so với brief", "Phương án khác số tầng đã yêu cầu.", "concept_architect")
    check(area["so_tang"] == program["so_tang"], "MAT_BANG_SAI_TANG", "Số tầng trên bản vẽ",
          "Bản vẽ và chương trình công năng có số tầng khác nhau.", "drafter")
    check(build_area_table(state["layout"], brief) == area, "SAI_BANG_DIEN_TICH", "Bảng diện tích",
          "Bảng diện tích khác hình học phòng.", "drafter")
    recomputed = compute_cost(area, state["layout"], state["program"], brief["ngan_sach"])
    recomputed["option_stamp"] = stamp
    checks = (
        ("drafter", "Bản vẽ", "Số tờ, tầng, nhãn phòng hoặc diện tích trên bản vẽ sai.",
         lambda: _drawing_matches(files, state)),
        ("cost_estimator", "Dự toán", "Khối lượng, ngân sách hoặc công thức chi phí XLSX sai.",
         lambda: recomputed["tong_chi_phi"] == state["cost"]["tong_chi_phi"]
         and _cost_matches(files["du_toan_xlsx"], area, recomputed)),
        ("pm_report", "Thuyết minh", "Số tầng, danh mục phòng, diện tích hoặc chi phí DOCX sai.",
         lambda: _doc_matches(files["thuyet_minh_docx"], area, recomputed)),
    )
    for target, title, message, validate in checks:
        try:
            ok = validate()
        except Exception as error:
            # Thư viện đọc tài liệu có các kiểu lỗi riêng cho tệp hỏng.
            ok = False
            message += f" Không đọc được dữ liệu ({type(error).__name__})."
        check(ok, "HO_SO_KHONG_KHOP", title, message, target)
    return FinalReview(dat=not issues, loi=issues)


@agent_node("final_reviewer")
def run(state: dict) -> dict:
    issues = outstanding(state)
    blocking = [i for i in issues if i.get("phan_loai") in ("vi_pham", "ky_thuat")]
    if blocking:
        return {"route": "propose_adjustment", "outcome": "not_passed", "remaining_issues": issues, "final_files": None,
                "_to": "project_manager",
                "_summary": "Tạm giữ hồ sơ để xử lý lỗi kỹ thuật hoặc vi phạm đã xác minh",
                "_output": {"loi": blocking}, "_feedback": True}
    review = audit(state)
    result = review.model_dump()
    if review.dat:
        return {"final_review": result, "route": "publish", "remaining_issues": issues,
                "outcome": "not_passed" if state.get("repair_limit_reached") and issues else "done", "_output": result,
                "_summary": "Đối chiếu hồ sơ nhất quán", "_to": "publish"}
    # Sửa sớm nhất trong chuỗi phụ thuộc để tất cả sản phẩm liên quan được tạo lại.
    priority = ("concept_architect", "architect", "drafter", "cost_estimator", "pm_report")
    target = next(step for step in priority if any(i.target == step for i in review.loi))
    return {"final_review": result, "route": "coordinate_repair", "repair_target": target,
            "repair_fallback": "end", "feedback_source": "final_reviewer", "feedback": result["loi"],
            "_summary": f"Phát hiện {len(review.loi)} sai lệch trong hồ sơ", "_output": result,
            "_to": "project_manager", "_feedback": True}
