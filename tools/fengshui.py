"""Phong thủy Bát trạch: cung mệnh theo năm sinh, hướng tốt/xấu."""
from __future__ import annotations

CAN = ["Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý"]
CHI = ["Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi"]

# Số Lạc thư -> cung (số 5: nam là Khôn, nữ là Cấn)
_CUNG = {1: "Khảm", 2: "Khôn", 3: "Chấn", 4: "Tốn", 6: "Càn", 7: "Đoài", 8: "Cấn", 9: "Ly"}
DONG_TU = {"Khảm", "Ly", "Chấn", "Tốn"}

# Thứ tự: Sinh khí, Thiên y, Diên niên, Phục vị, Họa hại, Ngũ quỷ, Lục sát, Tuyệt mệnh
_HUONG = {
    "Khảm": ["Đông Nam", "Đông", "Nam", "Bắc", "Tây", "Đông Bắc", "Tây Bắc", "Tây Nam"],
    "Ly":   ["Đông", "Đông Nam", "Bắc", "Nam", "Đông Bắc", "Tây", "Tây Nam", "Tây Bắc"],
    "Chấn": ["Nam", "Bắc", "Đông Nam", "Đông", "Tây Nam", "Tây Bắc", "Đông Bắc", "Tây"],
    "Tốn":  ["Bắc", "Nam", "Đông", "Đông Nam", "Tây Bắc", "Tây Nam", "Tây", "Đông Bắc"],
    "Càn":  ["Tây", "Đông Bắc", "Tây Nam", "Tây Bắc", "Đông Nam", "Đông", "Bắc", "Nam"],
    "Khôn": ["Đông Bắc", "Tây", "Tây Bắc", "Tây Nam", "Đông", "Đông Nam", "Nam", "Bắc"],
    "Cấn":  ["Tây Nam", "Tây Bắc", "Tây", "Đông Bắc", "Nam", "Bắc", "Đông", "Đông Nam"],
    "Đoài": ["Tây Bắc", "Tây Nam", "Đông Bắc", "Tây", "Bắc", "Nam", "Đông Nam", "Đông"],
}
_TEN_HUONG = ["Sinh khí", "Thiên y", "Diên niên", "Phục vị", "Họa hại", "Ngũ quỷ", "Lục sát", "Tuyệt mệnh"]
TOT = set(_TEN_HUONG[:4])

DIRECTIONS = ["Bắc", "Đông Bắc", "Đông", "Đông Nam", "Nam", "Tây Nam", "Tây", "Tây Bắc"]
BEARING = {d: i * 45 for i, d in enumerate(DIRECTIONS)}


def can_chi(year: int) -> str:
    return f"{CAN[(year - 4) % 10]} {CHI[(year - 4) % 12]}"


def cung_menh(year: int, gioi_tinh: str = "nam") -> str:
    """Cung phi theo năm sinh (dương lịch, coi như năm âm lịch) và giới tính."""
    yy = year % 100
    male = gioi_tinh.lower().startswith("nam")
    if year < 2000:
        r = (100 - yy) % 9 if male else (yy - 4) % 9
    else:
        r = (99 - yy) % 9 if male else (yy + 6) % 9
    r = r or 9
    if r == 5:
        return "Khôn" if male else "Cấn"
    return _CUNG[r]


def huong_menh(cung: str) -> dict[str, str]:
    """Bảng {hướng: tên sao} cho cung mệnh."""
    return {h: _TEN_HUONG[i] for i, h in enumerate(_HUONG[cung])}


def opposite(direction: str) -> str:
    return DIRECTIONS[(DIRECTIONS.index(direction) + 4) % 8]


def analyze(year: int | None, gioi_tinh: str, huong_nha: str) -> dict:
    """Phân tích hướng nhà so với cung mệnh chủ nhà."""
    if not year:
        return {"co_du_lieu": False, "ghi_chu": "Không có năm sinh chủ nhà – bỏ qua phân tích cung mệnh."}
    cung = cung_menh(year, gioi_tinh)
    table = huong_menh(cung)
    sao = table.get(huong_nha, "?")
    good = [h for h, s in table.items() if s in TOT]
    return {
        "co_du_lieu": True,
        "nam_sinh": year,
        "can_chi": can_chi(year),
        "gioi_tinh": gioi_tinh,
        "cung_menh": cung,
        "nhom": "Đông tứ mệnh" if cung in DONG_TU else "Tây tứ mệnh",
        "huong_nha": huong_nha,
        "sao_huong_nha": sao,
        "hop_huong": sao in TOT,
        "huong_tot": {h: table[h] for h in good},
        "huong_xau": {h: s for h, s in table.items() if s not in TOT},
        "goi_y_bep": f"Miệng bếp nên quay về hướng {good[1]} ({table[good[1]]}) hoặc {good[0]} ({table[good[0]]}).",
        "goi_y_ban_tho": f"Bàn thờ nên quay về hướng {good[0]} (Sinh khí) hoặc {good[3]} (Phục vị).",
    }
