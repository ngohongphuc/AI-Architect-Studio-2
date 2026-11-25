"""Khung bản vẽ và khung tên (vẽ trên hệ tọa độ giấy, mm)."""
from __future__ import annotations

from tools.sheet import FRAME, PAPER, Sheet


def draw_frame(sheet: Sheet) -> None:
    x0, y0, x1, y1 = FRAME
    sheet.rect(5, 5, PAPER[0] - 10, PAPER[1] - 10, "KHUNG", paper=True, lw=0.18)
    sheet.rect(x0, y0, x1 - x0, y1 - y0, "KHUNG", paper=True, lw=0.5)
    draw_title_block(sheet)


def draw_title_block(sheet: Sheet) -> None:
    info = sheet.info
    w, h = 175.0, 44.0
    x1, y0 = FRAME[2], FRAME[1]
    x0, y1 = x1 - w, y0 + h
    L = "KHUNG_TEN"
    sheet.rect(x0, y0, w, h, L, paper=True, lw=0.5)
    # cột: nhãn | nội dung ; hàng
    rows = [
        ("ĐƠN VỊ THIẾT KẾ", "AI ARCHITECT STUDIO – Văn phòng kiến trúc ảo"),
        ("DỰ ÁN", info.get("du_an", "Nhà ở riêng lẻ")),
        ("CHỦ ĐẦU TƯ", info.get("chu_dau_tu", "Hộ gia đình")),
        ("ĐỊA ĐIỂM", info.get("dia_diem", "")),
        ("TÊN BẢN VẼ", sheet.title.upper()),
    ]
    rh = 6.4
    lab_w = 32.0
    y = y1
    for label, value in rows:
        y -= rh
        sheet.line((x0, y), (x0 + w, y), L, paper=True)
        sheet.text((x0 + 2, y + rh / 2), label, L, h=1.8, ha="left", paper=True)
        sheet.text((x0 + lab_w + 2, y + rh / 2), value, L, h=2.2 if label != "TÊN BẢN VẼ" else 2.6,
                   ha="left", bold=label in ("TÊN BẢN VẼ", "ĐƠN VỊ THIẾT KẾ"), paper=True)
    sheet.line((x0 + lab_w, y), (x0 + lab_w, y1), L, paper=True)
    # hàng cuối: số hiệu | tỉ lệ | ngày | giai đoạn | phiên bản
    cells = [("SỐ HIỆU", sheet.code), ("TỈ LỆ", f"1:{sheet.scale}" if sheet.info.get("co_ti_le", True) else "—"),
             ("NGÀY", info.get("ngay", "")), ("GIAI ĐOẠN", "Thiết kế sơ bộ"), ("PHIÊN BẢN", info.get("phien_ban", "v1"))]
    cw = w / len(cells)
    for i, (label, value) in enumerate(cells):
        cx = x0 + i * cw
        if i:
            sheet.line((cx, y0), (cx, y), L, paper=True)
        sheet.text((cx + cw / 2, y - 3.2), label, L, h=1.6, paper=True)
        sheet.text((cx + cw / 2, y0 + 4.2), value, L, h=2.6 if i == 0 else 2.2, bold=i == 0, paper=True)
    # tên bản vẽ lớn ở góc trái dưới khung
    sheet.text((FRAME[0] + 6, FRAME[1] + 30), sheet.title.upper(), "CHU", h=5.0, ha="left", bold=True, paper=True)
    if info.get("co_ti_le", True):
        sheet.text((FRAME[0] + 6, FRAME[1] + 22), f"TỈ LỆ 1:{sheet.scale}", "CHU", h=3.0, ha="left", paper=True)
    note = info.get("ghi_chu_ban_ve")
    if note:
        sheet.text((FRAME[0] + 6, FRAME[1] + 14), note, "CHU", h=2.0, ha="left", paper=True)
