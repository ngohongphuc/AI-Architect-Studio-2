"""Phân tích yêu cầu tiếng Việt thành brief bằng quy tắc (dùng khi không có LLM,
và để kiểm tra chéo kết quả LLM)."""
from __future__ import annotations

import re
import unicodedata

from pydantic import ValidationError

from state import Brief, RequestFields

LOT_PATTERN = r"(?<![\d.,-])(-?\d+(?:[.,]\d+)?)\s*m?\s*[x×*]\s*(-?\d+(?:[.,]\d+)?)"
PARCEL_PATTERN = re.compile(r"\bmã lô đất(?:[ \t]*[:=][ \t]*|[ \t]+)([^\s,;!]+)", re.IGNORECASE)
BUDGET_PATTERN = (r"(?<![\d.,])(-?\d+(?:[.,]\d+)?)\s*"
                  r"(?:(tỷ|tỉ)(?:\s*(\d{1,3})(?:\s*triệu\b|(?=\s*[,.;!\n]|\s*$)))?|(triệu))")

DIRS = ["đông nam", "đông bắc", "tây nam", "tây bắc", "đông", "tây", "nam", "bắc"]
PROVINCES = {
    "hà nội": "Hà Nội", "hn": "Hà Nội", "hồ chí minh": "TP. Hồ Chí Minh", "tp.hcm": "TP. Hồ Chí Minh",
    "tphcm": "TP. Hồ Chí Minh", "tp hcm": "TP. Hồ Chí Minh", "tp. hcm": "TP. Hồ Chí Minh",
    "hcm": "TP. Hồ Chí Minh", "sài gòn": "TP. Hồ Chí Minh", "đà nẵng": "Đà Nẵng",
    "hải phòng": "Hải Phòng", "cần thơ": "Cần Thơ", "nha trang": "Khánh Hòa", "khánh hòa": "Khánh Hòa",
    "huế": "Huế", "bắc ninh": "Bắc Ninh", "hải dương": "Hải Dương", "nam định": "Nam Định",
    "thanh hóa": "Thanh Hóa", "nghệ an": "Nghệ An", "vinh": "Nghệ An", "quảng ninh": "Quảng Ninh",
    "bình dương": "Bình Dương", "đồng nai": "Đồng Nai", "vũng tàu": "Bà Rịa – Vũng Tàu", "đà lạt": "Lâm Đồng",
    "lâm đồng": "Lâm Đồng", "thái nguyên": "Thái Nguyên", "vĩnh phúc": "Vĩnh Phúc", "hưng yên": "Hưng Yên",
    "long an": "Long An", "tây ninh": "Tây Ninh", "gia lai": "Gia Lai", "quảng ngãi": "Quảng Ngãi",
    "quảng nam": "Quảng Nam", "bình định": "Bình Định", "đắk lắk": "Đắk Lắk", "đồng tháp": "Đồng Tháp",
    "an giang": "An Giang", "cà mau": "Cà Mau", "vĩnh long": "Vĩnh Long", "tiền giang": "Tiền Giang",
    "ninh bình": "Ninh Bình", "phú thọ": "Phú Thọ", "sơn la": "Sơn La", "lào cai": "Lào Cai",
}
STYLES = {
    "tân cổ điển": "tân cổ điển", "cổ điển": "cổ điển", "tối giản": "tối giản", "minimalism": "tối giản",
    "indochine": "Indochine", "đông dương": "Indochine", "japandi": "Japandi", "bắc âu": "Bắc Âu",
    "scandinavian": "Bắc Âu", "nhiệt đới": "nhiệt đới", "hiện đại": "hiện đại",
}
WORD_NUM = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5, "sáu": 6}
EXTRA_KEYWORDS = {
    "ánh sáng": "Nhiều ánh sáng tự nhiên", "thông thoáng": "Thông thoáng", "sân vườn": "Có sân vườn",
    "thang máy": "Thang máy (ghi nhận – ngoài phạm vi bản vẽ sơ bộ)", "người già": "Có người cao tuổi",
    "ông bà": "Có người cao tuổi", "tiết kiệm": "Ưu tiên tiết kiệm chi phí", "cao cấp": "Hoàn thiện cao cấp",
    "sang trọng": "Hoàn thiện cao cấp", "cây xanh": "Nhiều cây xanh", "kinh doanh": "Tầng 1 kết hợp kinh doanh",
}


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


FIELD_LABELS = {
    "rong": "Chiều rộng mặt tiền", "dai": "Chiều sâu lô đất", "tinh": "Địa điểm",
    "ma_lo_dat": "Mã lô đất",
    "so_tang": "Số tầng", "so_nguoi": "Số người", "phong_ngu": "Số phòng ngủ", "ngan_sach": "Ngân sách",
}


def _counts(text: str, noun: str) -> list[int]:
    number = rf"(-?\d+|{'|'.join(WORD_NUM)})"
    values = re.findall(rf"(?<![\w.,]){number}\s*{noun}\b", text)
    values.extend(re.findall(rf"\bsố\s*{noun}\s*[:=]\s*{number}\b", text))
    return [WORD_NUM[v] if v in WORD_NUM else int(v) for v in values]


def _location(value: str) -> str:
    value = " ".join(value.strip().rstrip(".").split())
    return PROVINCES.get(_norm(value), value)


def explicit_request_fields(request: str) -> dict[str, list]:
    """Trích các giá trị có mặt trong mô tả; giữ các giá trị khác nhau để báo mâu thuẫn."""
    request = unicodedata.normalize("NFC", request)
    parcels = [match[1].rstrip(".") for match in PARCEL_PATTERN.finditer(request)]
    request = PARCEL_PATTERN.sub("", request)
    t = _norm(request)
    dimensions = []
    for match in re.finditer(LOT_PATTERN, t):
        clause = re.split(r"[,;!\n]|\.\s", t[:match.start()])[-1]
        if re.search(r"\b(?:phòng|bếp|gara|wc)\b", clause) and not re.search(r"\b(?:đất|lô)\b", clause):
            continue
        dimensions.append(match.groups())
    decimal = r"\s*[:=]?\s*(-?\d+(?:[.,]\d+)?)"
    land = r"(?:^|[,;\n]\s*|\b(?:lô đất|đất)\s+)"
    widths = [_num(w) for w, _ in dimensions] + [
        _num(v) for v in re.findall(land + r"(?:rộng|mặt tiền|chiều rộng)" + decimal, t)]
    depth_pattern = land + r"(?:dài|sâu|chiều sâu)" + decimal
    if not dimensions:
        depth_pattern = r"(?:dài|sâu|chiều sâu)" + decimal
    depths = [_num(d) for _, d in dimensions] + [_num(v) for v in re.findall(depth_pattern, t)]
    named_locations = re.findall(r"(?:địa điểm|tỉnh/thành(?: phố)?)\s*:\s*([^,;\n]+)",
                                 unicodedata.normalize("NFC", request), re.IGNORECASE)
    if named_locations:
        locations = [_location(value.strip().rstrip(".")) for value in named_locations]
        # Một tên đã ghi bằng nhãn có thể xuất hiện lại trong mô tả tự do.
        t_location = re.sub(r"(?:địa điểm|tỉnh/thành(?: phố)?)\s*:\s*[^,;\n]+", "", t)
    else:
        locations = []
        t_location = t
    for country_name in re.finditer(r"(?<!\w)(?:" + "|".join(re.escape(k) for k in sorted(PROVINCES, key=len, reverse=True))
                                    + r")(?!\w)", t_location):
        locations.append(PROVINCES[country_name.group()])
    budgets = [int(round(_num(value) * (1e9 if billion else 1e6) + int(rest or 0) * 1e6))
               for value, billion, rest, _ in re.findall(BUDGET_PATTERN, t)]
    budgets.extend(int(amount.replace(".", "")) for amount in
                   re.findall(r"(?<![\w.,])(-?(?:\d{1,3}(?:\.\d{3})+|\d+))\s*(?:vnđ|vnd|đồng)\b", t)
                   if len(amount.replace(".", "").lstrip("-")) >= 5)
    values = {"rong": widths, "dai": depths, "tinh": locations,
              "ma_lo_dat": list({code.casefold(): code for code in parcels if code}.values()), "so_tang": _counts(t, "tầng"),
              "so_nguoi": _counts(t, "người"), "phong_ngu": _counts(t, r"(?:phòng ngủ|pn)"),
              "ngan_sach": budgets}
    return {key: list(dict.fromkeys(items)) for key, items in values.items()}


def parse_request(request: str, *, values: dict | None = None) -> dict:
    """Trả về brief từ mô tả và các giá trị đã hợp nhất, rồi tính các giả định còn thiếu."""
    t = _norm(PARCEL_PATTERN.sub("", unicodedata.normalize("NFC", request)))
    if values is None:
        values = {key: items[0] for key, items in explicit_request_fields(request).items() if items}
    assumptions: list[str] = []

    rong, dai = values.get("rong", 5.0), values.get("dai", 20.0)
    if "rong" not in values or "dai" not in values:
        assumptions.append("Kích thước lô đất: không rõ, giả định 5×20 m")

    huong = None
    m = re.search(r"hướng\s+(" + "|".join(DIRS) + r")", t)
    if m:
        huong = m.group(1).title()
    else:
        huong = "Nam"
        assumptions.append("Hướng mặt tiền: không rõ, giả định hướng Nam")

    tinh = values.get("tinh")
    if not tinh:
        tinh = "Hà Nội"
        assumptions.append("Địa điểm: tạm ghi Hà Nội để lập brief. Cần xác nhận tỉnh/thành của lô đất.")

    # --- Gia đình ---
    so_nguoi = values.get("so_nguoi")
    if so_nguoi is None:
        so_nguoi = 4
        assumptions.append("Số người: không rõ, giả định 4 người")
    years = [int(y) for y in re.findall(r"(?<!\d)(19[3-9]\d|20[0-2]\d)(?!\d)", t)]
    gioi_tinh = "nam"
    nam_sinh = None
    mh = re.search(r"chồng\D{0,20}?(19\d\d|20[0-2]\d)", t)
    mw = re.search(r"vợ\D{0,20}?(19\d\d|20[0-2]\d)", t)
    if mh and not re.search(r"vợ chồng", t[max(0, mh.start() - 4):mh.end()]):
        nam_sinh = int(mh.group(1))
    elif years:
        nam_sinh = years[0]
        if re.search(r"(chủ nhà|gia chủ)\s*(là\s*)?nữ|\bchị\b.*sinh", t) or (mw and not mh and "vợ chồng" not in t):
            gioi_tinh = "nữ"
    if not nam_sinh:
        assumptions.append("Năm sinh chủ nhà: không có, bỏ qua phân tích cung mệnh")

    # --- Phòng ---
    phong_ngu = values.get("phong_ngu")
    if phong_ngu is None:
        phong_ngu = max(2, min(5, so_nguoi - 1))
        assumptions.append(f"Số phòng ngủ: không rõ, đề xuất {phong_ngu} phòng theo số người")
    phong_tho = 0 if re.search(r"không\s*(cần|có)?\s*phòng thờ", t) else (1 if "phòng thờ" in t or "thờ cúng" in t else 0)
    gara = None
    gara_terms = r"(?:gara|garage|chỗ đỗ xe|đỗ xe|để xe)"
    if re.search(gara_terms, t) and not re.search(r"không\s*(?:cần|có)?\s*" + gara_terms, t):
        gara = "ô tô" if re.search(r"ô tô|oto|ôtô|xe hơi|xe con", t) else "xe máy"
    work_terms = r"(?:phòng làm việc|phòng đọc|thư viện)"
    phong_lam_viec = int(bool(re.search(work_terms, t))
                        and not re.search(r"không\s*(?:cần|có)?\s*" + work_terms, t))
    so_tang = values.get("so_tang")
    if so_tang is None:
        assumptions.append("Số tầng: để Kiến trúc sư đề xuất")

    # --- Ngân sách ---
    ngan_sach = values.get("ngan_sach")
    if ngan_sach is None:
        ngan_sach = rong * dai * 0.9 * 4 * 6_500_000
        assumptions.append(f"Ngân sách: không rõ, ước theo suất đầu tư ≈ {ngan_sach / 1e9:.2f} tỷ")

    phong_cach = None
    for key in sorted(STYLES, key=len, reverse=True):
        if key in t:
            phong_cach = STYLES[key]
            break
    if not phong_cach:
        phong_cach = "hiện đại"
        assumptions.append("Phong cách: không rõ, giả định hiện đại")

    extras = sorted({v for k, v in EXTRA_KEYWORDS.items() if k in t})

    brief = Brief(
        lo_dat={"rong": rong, "dai": dai, "huong": huong, "tinh": tinh, "ma_lo_dat": values.get("ma_lo_dat")},
        gia_dinh={"so_nguoi": so_nguoi, "nam_sinh_chu_nha": nam_sinh, "gioi_tinh_chu_nha": gioi_tinh,
                  "nam_sinh_thanh_vien": years},
        yeu_cau_phong={"phong_ngu": phong_ngu, "phong_tho": phong_tho, "gara": gara,
                       "phong_lam_viec": phong_lam_viec, "so_tang": so_tang},
        ngan_sach=int(round(ngan_sach)),
        phong_cach=phong_cach,
        yeu_cau_khac=extras,
        gia_dinh_bo_sung=assumptions,
    )
    return brief.model_dump()


def inspect_request(request: str, fields: dict | None = None) -> tuple[dict | None, list[str], list[str]]:
    """Hợp nhất biểu mẫu và mô tả bằng quy tắc cục bộ."""
    explicit = explicit_request_fields(request)
    conflicts = []
    try:
        supplied = RequestFields.model_validate(fields or {}).model_dump(exclude_none=True)
    except ValidationError as error:
        invalid = [FIELD_LABELS.get(item["loc"][-1], "Thông tin biểu mẫu") for item in error.errors()]
        return None, [], [f"{label} nằm ngoài phạm vi đầu vào." for label in invalid]
    if "tinh" in supplied:
        supplied["tinh"] = _location(supplied["tinh"])
        if not supplied["tinh"]:
            supplied.pop("tinh")
    if not supplied.get("ma_lo_dat"):
        supplied.pop("ma_lo_dat", None)

    values = supplied.copy()
    for key, mentions in explicit.items():
        label = FIELD_LABELS[key]
        if len(mentions) > 1:
            conflicts.append(f"{label} có nhiều giá trị trong mô tả. Chọn một giá trị trước khi tiếp tục.")
        elif mentions:
            value = mentions[0]
            equal = key in supplied and (value == supplied[key] or
                    key in ("tinh", "ma_lo_dat") and _norm(value) == _norm(supplied[key]))
            if key in supplied and not equal:
                conflicts.append(f"{label} khác nhau. Mô tả ghi “{value}”, biểu mẫu ghi “{supplied[key]}”.")
            else:
                values[key] = value

    questions = [f"Bổ sung {FIELD_LABELS[key].lower()} (m)." for key in ("rong", "dai") if key not in values]
    if conflicts or questions:
        return None, questions, conflicts
    try:
        RequestFields.model_validate(values)
        return parse_request(request, values=values), [], []
    except ValidationError as error:
        labels = [FIELD_LABELS.get(item["loc"][-1], "Yêu cầu") for item in error.errors()]
        return None, [], [f"{label} nằm ngoài phạm vi đầu vào." for label in labels]


def project_title(request: str, brief: dict | None) -> str:
    brief = brief or {}
    lot = brief.get("lo_dat") or {}
    assumptions = brief.get("gia_dinh_bo_sung", [])
    if lot and not any(note.startswith("Kích thước lô đất:") for note in assumptions):
        known_location = lot.get("tinh") and not any(note.startswith("Địa điểm:") for note in assumptions)
        suffix = f" · {lot['tinh']}" if known_location else ""
        return f"Nhà ở {lot['rong']:g} × {lot['dai']:g} m{suffix}"
    description = " ".join(request.split())
    return (description[:68] + "…" if len(description) > 68 else description) or "Dự án nhà ở"
