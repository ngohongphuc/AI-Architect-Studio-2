"""Xuất file ước tính chi phí du_toan.xlsx – các ô thành tiền là CÔNG THỨC Excel (không ghi số cứng)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from tools.cost_calc import load_prices

HEAD_FILL = PatternFill("solid", fgColor="1F4E78")
SUB_FILL = PatternFill("solid", fgColor="DDEBF7")
TOTAL_FILL = PatternFill("solid", fgColor="FFF2CC")
INPUT_FONT = Font(color="0000FF")          # ô người dùng có thể sửa
THIN = Side(style="thin", color="999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
VND = '#,##0" ₫"'
M2 = '#,##0.00'


def _header(ws, row, values, widths=None):
    for i, v in enumerate(values, start=1):
        c = ws.cell(row=row, column=i, value=v)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HEAD_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BORDER
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w


def _row(ws, row, values, fmts=None, bold=False, fill=None):
    for i, v in enumerate(values, start=1):
        c = ws.cell(row=row, column=i, value=v)
        c.border = BORDER
        if fmts and i - 1 < len(fmts) and fmts[i - 1]:
            c.number_format = fmts[i - 1]
        if bold:
            c.font = Font(bold=True)
        if fill:
            c.fill = fill


def write_cost_xlsx(cost: dict, area: dict, brief: dict, path: Path, notes: str = "", *,
                    option: dict | None = None) -> Path:
    P = load_prices()
    wb = Workbook()
    ws_th = wb.active
    ws_th.title = "Tong_hop"
    ws_dt = wb.create_sheet("Dien_tich")
    ws_ct = wb.create_sheet("Chi_tiet")
    ws_dg = wb.create_sheet("Don_gia")
    ws_tk = wb.create_sheet("Tiet_kiem")
    if option:
        wb.properties.identifier = option["stamp"]
        sheet = wb.create_sheet("Gia_dinh")
        sheet["A1"] = "THIẾT KẾ SƠ BỘ"
        sheet["A2"] = option["label"]
        _header(sheet, 4, ["Nhóm", "Mục cần rà soát", "Nội dung"], [24, 44, 85])
        for row in option["notes"]:
            sheet.append(row)
            sheet[f"C{sheet.max_row}"].alignment = Alignment(wrap_text=True, vertical="top")
            sheet.row_dimensions[sheet.max_row].height = 42
        sheet.freeze_panes = "A5"

    # ---------------- Don_gia ----------------
    ws_dg["A1"] = "BẢNG ĐƠN GIÁ THAM KHẢO ĐÃ DÙNG (ô màu xanh có thể sửa – các sheet khác tự tính lại)"
    ws_dg["A1"].font = Font(bold=True, size=12)
    _header(ws_dg, 3, ["Mã", "Hạng mục", "Đơn vị", "Đơn giá", "Ghi chú", "Nguồn", "Thời điểm"],
            [16, 40, 12, 16, 38, 50, 12])
    dg_ref = {}
    r = 4
    for code, p in P["don_gia"].items():
        fmt = "0%" if p["don_vi"] == "%" else VND
        _row(ws_dg, r, [code, p["hang_muc"], p["don_vi"], p["don_gia"], p["ghi_chu"], p["nguon"], p["thoi_diem"]],
             [None, None, None, fmt])
        ws_dg.cell(row=r, column=4).font = INPUT_FONT
        dg_ref[code] = f"Don_gia!$D${r}"
        r += 1
    r += 1
    ws_dg.cell(row=r, column=1, value="HỆ SỐ QUY ĐỔI DIỆN TÍCH").font = Font(bold=True)
    r += 1
    _header_row = r
    for i, v in enumerate(["Mã", "Diễn giải", "", "Hệ số"], start=1):
        c = ws_dg.cell(row=_header_row, column=i, value=v)
        c.font = Font(bold=True, color="FFFFFF"); c.fill = HEAD_FILL; c.border = BORDER
    r += 1
    hs_ref = {}
    for code, h in P["he_so"].items():
        _row(ws_dg, r, [code, h["dien_giai"], "", h["he_so"]], [None, None, None, "0.00"])
        ws_dg.cell(row=r, column=4).font = INPUT_FONT
        hs_ref[code] = f"Don_gia!$D${r}"
        r += 1

    # ---------------- Dien_tich ----------------
    ws_dt["A1"] = "BẢNG DIỆN TÍCH QUY ĐỔI"
    ws_dt["A1"].font = Font(bold=True, size=12)
    _header(ws_dt, 3, ["STT", "Hạng mục", "Diện tích (m²)", "Hệ số", "DT quy đổi (m²)"], [6, 36, 16, 10, 18])
    r = 4
    first = r
    for i, row in enumerate(cost["dien_tich"], start=1):
        _row(ws_dt, r, [i, row["hang_muc"], row["dien_tich"], f"={hs_ref[row['ma_he_so']]}", f"=C{r}*D{r}"],
             [None, None, M2, "0.00", M2])
        r += 1
    last = r - 1
    _row(ws_dt, r, ["", "TỔNG DIỆN TÍCH QUY ĐỔI", "", "", f"=SUM(E{first}:E{last})"], [None, None, None, None, M2],
         bold=True, fill=TOTAL_FILL)
    dt_qd_ref = f"Dien_tich!$E${r}"
    r += 2
    floor_rows = [i for i, row in enumerate(cost["dien_tich"]) if row["ma_he_so"] == "HS_SAN"]
    bc_row = next(i for i, row in enumerate(cost["dien_tich"]) if row["ma_he_so"] == "HS_BAN_CONG")
    f_cells = ",".join(f"C{first + i}" for i in floor_rows)
    _row(ws_dt, r, ["", "Tổng diện tích sàn các tầng", f"=SUM({f_cells})", "", ""], [None, None, M2], bold=True)
    dt_san_ref = f"Dien_tich!$C${r}"
    r += 1
    _row(ws_dt, r, ["", "Diện tích sàn hoàn thiện (sàn + ban công)", f"={dt_san_ref.split('!')[1]}+C{first + bc_row}",
                    "", ""], [None, None, M2], bold=True)
    dt_ht_ref = f"Dien_tich!$C${r}"
    r += 2
    ws_dt.cell(row=r, column=2, value="Thống kê diện tích từng phòng").font = Font(bold=True)
    r += 1
    _header(ws_dt, r, ["Tầng", "Phòng", "Diện tích (m²)", "", "Kích thước (m)"])
    r += 1
    for t in area["tang"]:
        for ph in t["phong"]:
            _row(ws_dt, r, [t["tang"], ph["ten"], ph["dien_tich"], "", ph["kich_thuoc"]], [None, None, M2])
            r += 1

    # ---------------- Chi_tiet ----------------
    ws_ct["A1"] = "CHI PHÍ THEO HẠNG MỤC"
    ws_ct["A1"].font = Font(bold=True, size=12)
    _header(ws_ct, 3, ["STT", "Hạng mục", "Đơn vị", "Khối lượng", "Đơn giá", "Thành tiền", "Diễn giải khối lượng"],
            [6, 40, 12, 14, 16, 20, 30])
    r = 4
    first_ct = r
    qty_formula = {"DT quy đổi": f"={dt_qd_ref}", "DT sàn + ban công": f"={dt_ht_ref}"}
    for it in cost["hang_muc"]:
        qty = qty_formula.get(it["dien_giai"], round(it["kl"], 2))
        _row(ws_ct, r, [it["stt"], it["hang_muc"], it["don_vi"], qty, f"={dg_ref[it['ma']]}", f"=D{r}*E{r}",
                        it["dien_giai"]], [None, None, None, M2, VND, VND])
        if not isinstance(qty, str):
            ws_ct.cell(row=r, column=4).font = INPUT_FONT
        r += 1
    last_ct = r - 1
    _row(ws_ct, r, ["", "CỘNG CHI PHÍ XÂY DỰNG", "", "", "", f"=SUM(F{first_ct}:F{last_ct})", ""],
         [None] * 5 + [VND], bold=True, fill=SUB_FILL)
    sub_row = r
    r += 1
    _row(ws_ct, r, [len(cost["hang_muc"]) + 1, "Dự phòng phí", "%", f"=F{sub_row}", f"={dg_ref['DU_PHONG']}",
                    f"=D{r}*E{r}", "Trên chi phí xây dựng"], [None, None, None, VND, "0%", VND])
    dp_row = r
    r += 1
    _row(ws_ct, r, ["", "TỔNG CHI PHÍ", "", "", "", f"=F{sub_row}+F{dp_row}", ""], [None] * 5 + [VND], bold=True,
         fill=TOTAL_FILL)
    total_ref = f"Chi_tiet!$F${r}"

    # ---------------- Tong_hop ----------------
    ld = brief["lo_dat"]
    ws_th["A1"] = "TỔNG HỢP ƯỚC TÍNH CHI PHÍ XÂY DỰNG"
    ws_th["A1"].font = Font(bold=True, size=14)
    ws_th["A2"] = (f"Công trình: nhà ở riêng lẻ {area['so_tang']} tầng – lô {ld['rong']:g}×{ld['dai']:g} m – "
                   f"{ld['tinh']}. Lập ngày {date.today():%d/%m/%Y}")
    ws_th.column_dimensions["A"].width = 44
    ws_th.column_dimensions["B"].width = 24
    ws_th.column_dimensions["C"].width = 50
    rows = [
        ("Tổng chi phí dự kiến", f"={total_ref}", VND, "Chi_tiet"),
        ("Ngân sách giả định" if cost.get("ngan_sach_gia_dinh") else "Ngân sách chủ đầu tư",
         cost["ngan_sach"], VND, "Cần xác nhận (có thể sửa)" if cost.get("ngan_sach_gia_dinh") else "Nhập từ yêu cầu (có thể sửa)"),
        ("Chênh lệch (dự kiến – ngân sách)", "=B4-B5", VND, "Dương = vượt ngân sách"),
        ("Tỉ lệ vượt ngân sách", "=IF(B5=0,0,B6/B5)", "0.0%", "Mốc phản hồi chi phí 10%"),
        ("Tổng diện tích sàn hoàn thiện (m²)", f"={dt_ht_ref}", M2, "Dien_tich"),
        ("Tổng diện tích quy đổi (m²)", f"={dt_qd_ref}", M2, "Dien_tich"),
        ("Chi phí / m² sàn", "=IF(B8=0,0,B4/B8)", VND, ""),
        ("Gói hoàn thiện", cost["cap_hoan_thien"], None, ""),
        ("Đánh giá", '=IF(B7>0.1,"VƯỢT NGÂN SÁCH > 10% – xem sheet Tiet_kiem",IF(B7>0,"Vượt nhẹ (≤ 10%)",'
                     '"Trong ngân sách"))', None, ""),
    ]
    _header(ws_th, 3, ["Chỉ tiêu", "Giá trị", "Ghi chú"])
    for i, (k, v, fmt, note) in enumerate(rows, start=4):
        _row(ws_th, i, [k, v, note], [None, fmt])
    ws_th["B5"].font = INPUT_FONT
    ws_th.cell(row=12, column=2).font = Font(bold=True, color="C00000")
    if notes:
        ws_th["A15"] = "Ghi chú của Kỹ sư dự toán"
        ws_th["A15"].font = Font(bold=True)
        ws_th["A16"] = notes
        ws_th["A16"].alignment = Alignment(wrap_text=True, vertical="top")
        ws_th.merge_cells("A16:C22")
    ws_th["A24"] = ("Lưu ý: ước tính sơ bộ theo diện tích quy đổi và đơn giá tham khảo; không thay thế dự toán chi tiết "
                    "theo định mức nhà nước.")
    ws_th["A24"].font = Font(italic=True, color="666666")

    # ---------------- Tiet_kiem ----------------
    ws_tk["A1"] = "PHƯƠNG ÁN GIẢM CHI PHÍ"
    ws_tk["A1"].font = Font(bold=True, size=12)
    _header(ws_tk, 3, ["STT", "Phương án", "Tiết kiệm ước tính", "Tổng sau tiết kiệm", "So với ngân sách"],
            [6, 50, 20, 20, 18])
    r = 4
    for i, s in enumerate(cost["tiet_kiem"], start=1):
        kind = s["cong_thuc"][0]
        dp = f"(1+{dg_ref['DU_PHONG']})"
        if kind == "grade":
            f = f"=({dg_ref[s['cong_thuc'][1]]}-{dg_ref[s['cong_thuc'][2]]})*{dt_ht_ref}*{dp}"
        elif kind == "door":
            f = f"=({dg_ref['CUA_GO_TN']}-{dg_ref['CUA_GO_CN']})*{cost['cua']['CUA_GO']}*{dp}"
        else:
            f = round(s["tiet_kiem"])
        _row(ws_tk, r, [i, s["phuong_an"], f, f"={total_ref}-C{r}", f"=D{r}-Tong_hop!$B$5"],
             [None, None, VND, VND, VND])
        r += 1
    ws_tk.cell(row=r + 1, column=2, value="Các phương án có thể kết hợp; Kiến trúc sư áp dụng lần lượt khi vượt ngân sách > 10%.")
    for ws in (ws_th, ws_dt, ws_ct, ws_tk):
        ws.freeze_panes = "A4"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
