"""Xuất file mô tả chi tiết dự án (thuyết minh thiết kế) thuyet_minh.docx.

Mọi con số lấy trực tiếp từ trạng thái chung; phần văn bản tự do do agent (LLM hoặc mẫu) cung cấp.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


def vn_num(v: float, nd: int = 1) -> str:
    s = f"{v:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def vnd(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".") + " đ"


def _setup(doc: Document) -> None:
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(13)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    for name in ("Heading 1", "Heading 2", "Title"):
        s = doc.styles[name]
        s.font.name = "Times New Roman"
        s.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
        s.font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.left_margin, sec.right_margin = Cm(3.0), Cm(2.0)
    sec.top_margin = sec.bottom_margin = Cm(2.0)


def _table(doc: Document, header: list[str], rows: list[list], widths: list[float] | None = None, bold_last=False):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        cell = t.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(str(h))
        run.bold = True
        run.font.size = Pt(11)
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(v))
            run.font.size = Pt(11)
            if bold_last and ri == len(rows) - 1:
                run.bold = True
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return t


def write_description_docx(state: dict, texts: dict, path: Path) -> Path:
    from tools.design_option import option_label, option_stamp, selected_assumptions
    from tools.review_display import MISSING, regulatory_label, review_rows

    brief, program, area = state["brief"], state["program"], state["area_table"]
    review, cost = state.get("review", {}), state.get("cost", {})
    ld, gd, yc = brief["lo_dat"], brief["gia_dinh"], brief["yeu_cau_phong"]
    doc = Document()
    if option_stamp(program):
        doc.core_properties.identifier = option_stamp(program)
    _setup(doc)

    # ---- Trang bìa ----
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("AI ARCHITECT STUDIO\nVĂN PHÒNG KIẾN TRÚC ẢO")
    r.bold = True
    r.font.size = Pt(14)
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("THUYẾT MINH THIẾT KẾ SƠ BỘ")
    r.bold = True
    r.font.size = Pt(22)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"NHÀ Ở RIÊNG LẺ {area['so_tang']} TẦNG\nLô đất {ld['rong']:g} × {ld['dai']:g} m – {ld['tinh']}")
    r.font.size = Pt(15)
    for _ in range(8):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    label = option_label(program)
    identity = f"{label}\n" if label else ""
    p.add_run(f"{identity}Mã hồ sơ: {state.get('run_id', '')}\nNgày lập: {date.today():%d/%m/%Y}").italic = True
    doc.add_page_break()

    # ---- 1. Thông tin chung ----
    doc.add_heading("1. Thông tin chung", level=1)
    chu = f"Hộ gia đình {gd['so_nguoi']} người" + (f", chủ hộ sinh năm {gd['nam_sinh_chu_nha']}"
                                                  if gd.get("nam_sinh_chu_nha") else "")
    _table(doc, ["Hạng mục", "Nội dung"], [
        ["Tên công trình", f"Nhà ở riêng lẻ {area['so_tang']} tầng"],
        ["Chủ đầu tư", chu],
        ["Địa điểm", f"{ld['tinh']} – mặt tiền hướng {ld['huong']}"],
        ["Diện tích lô đất", f"{vn_num(area['dien_tich_dat'])} m² ({ld['rong']:g} × {ld['dai']:g} m)"],
        ["Diện tích xây dựng", f"{vn_num(area['dien_tich_xay_dung'])} m²"],
        ["Mật độ xây dựng", f"{vn_num(area['mat_do_xay_dung'] * 100)}%"],
        ["Số tầng", f"{area['so_tang']} tầng"],
        ["Tổng diện tích sàn", f"{vn_num(area['tong_dien_tich_san'])} m² (chưa gồm ban công, sân thượng)"],
        ["Chiều cao công trình", f"{vn_num(area['chieu_cao_cong_trinh'], 2)} m (tính đến đỉnh tường chắn mái)"],
        ["Giai đoạn", "Thiết kế sơ bộ"],
    ], [5.5, 10.5])

    # ---- 2. Yêu cầu chủ đầu tư ----
    doc.add_heading("2. Yêu cầu của chủ đầu tư", level=1)
    doc.add_paragraph(f"Yêu cầu gốc: “{state['user_request']}”").italic = True
    items = [f"Số phòng ngủ: {yc['phong_ngu']}", f"Phòng thờ: {'có' if yc.get('phong_tho') else 'không'}",
             f"Gara: {yc.get('gara') or 'không'}", f"Ngân sách: {vnd(brief['ngan_sach'])}",
             f"Phong cách: {brief.get('phong_cach')}"]
    if yc.get("phong_lam_viec"):
        items.append("Phòng làm việc: có")
    items += brief.get("yeu_cau_khac", [])
    for it in items:
        doc.add_paragraph(it, style="List Bullet")

    # ---- 3. Ý tưởng ----
    doc.add_heading("3. Ý tưởng thiết kế", level=1)
    doc.add_paragraph(state.get("concept", ""))
    vl = program.get("vat_lieu", {})
    _table(doc, ["Bộ phận", "Vật liệu chủ đạo"], [
        ["Sàn", vl.get("san", "")], ["Mặt tiền", vl.get("mat_tien", "")], ["Cửa đi, cửa sổ", vl.get("cua", "")],
        ["Cửa phòng", vl.get("cua_phong", "")], ["Lan can", vl.get("lan_can", "")], ["Mái", vl.get("mai", "")],
        ["Gói hoàn thiện", program.get("cap_hoan_thien", "")],
    ], [5.5, 10.5])

    # ---- 4. Giải pháp công năng ----
    doc.add_heading("4. Giải pháp công năng từng tầng", level=1)
    for t in area["tang"]:
        names = [ph["ten"] for ph in t["phong"] if ph["loai"] not in ("hanh_lang",)]
        seen = []
        for n in names:
            if n not in seen:
                seen.append(n)
        doc.add_paragraph().add_run(f"{t['ten']} (cao {vn_num(area['chieu_cao_tang'][t['tang'] - 1], 2)} m): ").bold = True
        doc.paragraphs[-1].add_run(texts.get(f"tang_{t['tang']}", ", ".join(seen) + "."))
    img = state.get("drawings", {}).get("sheets", [])
    plan_imgs = [s for s in img if s["ten"].startswith("Mặt bằng tầng")]
    for s in plan_imgs:
        if Path(s["png"]).exists():
            doc.add_picture(s["png"], width=Cm(16))
            cap = doc.add_paragraph(f"Hình: {s['ten']} ({s['so_hieu']})")
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap.runs[0].italic = True

    # ---- 5. Thông gió, chiếu sáng ----
    doc.add_heading("5. Giải pháp thông gió, chiếu sáng tự nhiên", level=1)
    doc.add_paragraph(texts.get("thong_gio", ""))

    # ---- 6. Thống kê diện tích ----
    doc.add_heading("6. Bảng thống kê diện tích", level=1)
    rows = []
    for t in area["tang"]:
        for ph in t["phong"]:
            rows.append([t["ten"], ph["ten"], ph["kich_thuoc"], vn_num(ph["dien_tich"], 2)])
        rows.append([t["ten"], "Cộng diện tích sàn tầng", "", vn_num(t["dien_tich_san"], 2)])
    rows.append(["Toàn nhà", "TỔNG DIỆN TÍCH SÀN", "", vn_num(area["tong_dien_tich_san"], 2)])
    _table(doc, ["Tầng", "Phòng / khu vực", "Kích thước (m)", "Diện tích (m²)"], rows, [2.5, 6.5, 3.5, 3.5],
           bold_last=True)
    _table(doc, ["Tổng hợp", "Diện tích (m²)"], [
        ["Tổng diện tích sàn", vn_num(area["tong_dien_tich_san"], 2)],
        ["Ban công, lô gia", vn_num(area["tong_ban_cong"], 2)],
        ["Sân phơi, sân thượng", vn_num(area["tong_san_phoi"], 2)],
        ["Giếng trời (không tính sàn)", vn_num(area["tong_gieng_troi"], 2)],
        ["Sân trước + sân sau", vn_num(area["san_truoc"] + area["san_sau"], 2)],
    ], [8, 8])

    # ---- 7. Quy chuẩn ----
    doc.add_heading("7. Kiểm tra kỹ thuật và xác minh quy chuẩn", level=1)
    checks = review_rows(review, brief)
    doc.add_paragraph(f"Xác minh quy chuẩn — {regulatory_label(checks)}. Vòng sửa tự động {state.get('iteration', 0)}.")
    rows = [[row["criterion"], row["actual"],
             "Cần xác minh" if row["status"] == MISSING else row["threshold"], row["status"]]
            for row in checks]
    _table(doc, ["Tiêu chí", "Phương án", "Ngưỡng phép kiểm", "Kết quả"], rows, [5, 3.5, 3.5, 4])
    for row in checks:
        if row["regulatory"]:
            detail = row["reason"] if row["status"] == MISSING else f"{row['source']}. Phạm vi: {row['scope']}"
            if row["status"] == MISSING and row["action"]:
                detail += f" Cách bổ sung: {row['action']}"
            doc.add_paragraph(f"{row['criterion']} — {detail}", style="List Bullet")
    if review.get("canh_bao"):
        doc.add_paragraph("Khuyến nghị:")
        for w in review["canh_bao"]:
            doc.add_paragraph(f"{w.get('muc', '')}: {w.get('noi_dung', '')}", style="List Bullet")

    # ---- 8. Phong thủy ----
    doc.add_heading("8. Tư vấn phong thủy", level=1)
    advice = state.get("fengshui") or {}
    fs = advice.get("thong_tin", {})
    if fs.get("co_du_lieu"):
        _table(doc, ["Nội dung", "Kết quả"], [
            ["Năm sinh chủ nhà", f"{fs['nam_sinh']} ({fs['can_chi']}) – {fs['gioi_tinh']}"],
            ["Cung mệnh", f"{fs['cung_menh']} ({fs['nhom']})"],
            ["Hướng nhà", f"{fs['huong_nha']} – sao {fs['sao_huong_nha']} "
                          f"({'hợp' if fs['hop_huong'] else 'không hợp'} mệnh)"],
            ["Hướng tốt", ", ".join(f"{h} ({s})" for h, s in fs["huong_tot"].items())],
            ["Hướng xấu", ", ".join(f"{h} ({s})" for h, s in fs["huong_xau"].items())],
        ], [5, 11])
        doc.add_paragraph(fs.get("goi_y_bep", ""), style="List Bullet")
        doc.add_paragraph(fs.get("goi_y_ban_tho", ""), style="List Bullet")
    else:
        doc.add_paragraph(fs.get("ghi_chu", "Không có dữ liệu năm sinh." if state.get("fengshui_enabled", True) else "Đã tắt tư vấn phong thủy."))
    for c in advice.get("bo_tri", []):
        doc.add_paragraph(f"{'✔' if c['dat'] else '✘'} {c['noi_dung']}", style="List Bullet")
    for note in advice.get("goi_y", []):
        doc.add_paragraph(note["noi_dung"] + ". " + note["de_xuat"], style="List Bullet")
    doc.add_paragraph(texts.get("phong_thuy", ""))

    # ---- 9. Chi phí ----
    doc.add_heading("9. Tóm tắt chi phí", level=1)
    if cost:
        rows = [[it["hang_muc"], f"{vn_num(it['kl'], 2)} {it['don_vi']}", vnd(it["don_gia"]), vnd(it["thanh_tien"])]
                for it in cost["hang_muc"]]
        rows.append([f"Dự phòng ({cost['du_phong_pct'] * 100:.0f}%)", "", "", vnd(cost["du_phong"])])
        rows.append(["TỔNG CHI PHÍ DỰ KIẾN", "", "", vnd(cost["tong_chi_phi"])])
        _table(doc, ["Hạng mục", "Khối lượng", "Đơn giá", "Thành tiền"], rows, [6, 3.5, 3, 3.5], bold_last=True)
        doc.add_paragraph(
            f"Ngân sách{' giả định' if cost.get('ngan_sach_gia_dinh') else ''} {vnd(cost['ngan_sach'])}, "
            f"chênh lệch {vnd(cost['chenh_lech'])} "
            f"({vn_num(cost['vuot_pct'] * 100)}%). Chi phí bình quân {vnd(cost['chi_phi_m2_san'])}/m² sàn. "
            f"Chi tiết xem file du_toan.xlsx.")
        if texts.get("chi_phi"):
            doc.add_paragraph(texts["chi_phi"])

    # ---- 10. Giả định ----
    doc.add_heading("10. Các giả định và lưu ý", level=1)
    notes = selected_assumptions(state) + list(program.get("ghi_chu", []))
    for n in notes:
        doc.add_paragraph(n, style="List Bullet")
    for question in (state.get("brief_assessment") or {}).get("needs_confirmation", []):
        doc.add_paragraph("Thông tin cần bổ sung — " + question, style="List Bullet")
    if program.get("lich_su_sua"):
        doc.add_paragraph("Các điều chỉnh qua vòng phản hồi giữa các agent:")
        for n in program["lich_su_sua"]:
            doc.add_paragraph(n, style="List Bullet")
    for issue in state.get("remaining_issues", []):
        doc.add_paragraph(f"Lỗi còn tồn tại: {issue.get('muc', '')} – {issue.get('noi_dung', '')} "
                          f"(đề xuất: {issue.get('de_xuat', '')})", style="List Bullet")
    doc.add_paragraph("Hồ sơ là thiết kế sơ bộ do hệ thống AI lập; cần kiến trúc sư có chứng chỉ hành nghề rà soát, "
                      "khảo sát hiện trạng và thiết kế kỹ thuật trước khi xin phép xây dựng.").italic = True
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path
