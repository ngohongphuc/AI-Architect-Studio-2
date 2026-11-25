"""Tạo file data/don_gia.xlsx – bảng đơn giá tham khảo (nhóm cập nhật theo giá thị trường).

Chạy:  python -m tools.make_don_gia
"""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from config import PRICE_FILE

THOI_DIEM = "Quý III/2026"
NGUON = "Tham khảo báo giá xây nhà phố tại Hà Nội của một số nhà thầu (nhóm tự tổng hợp, cần cập nhật)"

# ma, hang_muc, don_vi, don_gia, ghi_chu
ROWS = [
    ("THO", "Phần thô + nhân công hoàn thiện", "m² quy đổi", 3_700_000, "Kết cấu BTCT, xây tô, chống thấm"),
    ("HT_TIET_KIEM", "Vật tư hoàn thiện – gói tiết kiệm", "m² sàn", 1_800_000, "Gạch 60x60 phổ thông, sơn nội địa"),
    ("HT_TRUNG_BINH", "Vật tư hoàn thiện – gói trung bình", "m² sàn", 2_300_000, "Gạch Viglacera/Prime, sơn Dulux nội thất"),
    ("HT_KHA", "Vật tư hoàn thiện – gói khá", "m² sàn", 3_000_000, "Gạch granite, thiết bị vệ sinh TOTO/Inax"),
    ("HT_CAO_CAP", "Vật tư hoàn thiện – gói cao cấp", "m² sàn", 4_200_000, "Đá tự nhiên, thiết bị nhập khẩu"),
    ("DIEN_NUOC", "Hệ thống điện, cấp thoát nước", "m² sàn", 400_000, "Dây, ống, thiết bị cơ bản"),
    ("CUA_NHOM", "Cửa nhôm hệ + kính cường lực", "m²", 2_000_000, "Nhôm Xingfa, kính 8–10 mm"),
    ("CUA_GO_CN", "Cửa gỗ công nghiệp", "m²", 3_500_000, "MDF/HDF chống ẩm, phủ melamine"),
    ("CUA_GO_TN", "Cửa gỗ tự nhiên", "m²", 6_000_000, "Gỗ lim/gõ"),
    ("CUA_CUON", "Cửa cuốn", "m²", 1_600_000, "Cửa cuốn khe thoáng, motor"),
    ("THIET_KE", "Chi phí thiết kế", "m² sàn", 150_000, "Thiết kế kiến trúc + kết cấu + điện nước"),
    ("DU_PHONG", "Dự phòng phí", "%", 0.07, "5–10% chi phí xây dựng"),
]

COEFFICIENTS = [
    ("HS_MONG_DON", "Hệ số móng đơn (nhà ≤ 2 tầng)", 0.30),
    ("HS_MONG_BANG", "Hệ số móng băng (nhà 3 tầng)", 0.50),
    ("HS_MONG_COC", "Hệ số móng cọc (nhà ≥ 4 tầng)", 0.40),
    ("HS_SAN", "Hệ số sàn các tầng", 1.00),
    ("HS_BAN_CONG", "Hệ số ban công, lô gia", 0.70),
    ("HS_SAN_PHOI", "Hệ số sân phơi, sân thượng", 0.50),
    ("HS_SAN_NGOAI", "Hệ số sân trước/sau", 0.50),
    ("HS_MAI_BTCT", "Hệ số mái BTCT", 0.50),
    ("HS_MAI_TON", "Hệ số mái tôn", 0.30),
]


def build(path=PRICE_FILE) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Don_gia"
    ws.append(["Mã", "Hạng mục", "Đơn vị", "Đơn giá (VNĐ)", "Ghi chú", "Nguồn", "Thời điểm"])
    for r in ROWS:
        ws.append([*r[:4], r[4], NGUON, THOI_DIEM])
    ws2 = wb.create_sheet("He_so")
    ws2.append(["Mã", "Diễn giải", "Hệ số"])
    for code, desc, val in COEFFICIENTS:
        ws2.append([code, desc, val])
    for sheet in (ws, ws2):
        for c in sheet[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E78")
            c.alignment = Alignment(horizontal="center")
        for col, w in zip("ABCDEFG", (16, 40, 12, 16, 40, 50, 12)):
            sheet.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2, min_col=4, max_col=4):
        for c in row:
            c.number_format = "0%" if isinstance(c.value, float) and c.value < 1 else "#,##0"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


if __name__ == "__main__":
    build()
    print(f"Đã tạo {PRICE_FILE}")
