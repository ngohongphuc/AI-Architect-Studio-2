"""Tìm cách điều chỉnh yêu cầu khi lượt thiết kế chưa đạt.

Chủ nhiệm thử các biến thể của brief (số tầng, số phòng, gara, phòng phụ, ngân sách),
chạy lại đúng bộ lập phương án, bố trí hình học, kiểm tra kỹ thuật và dự toán mà các agent
đang dùng, rồi giữ các biến thể bố trí được và nằm trong ngân sách, ưu tiên ít thay đổi nhất.
Mỗi đề xuất kèm mô tả yêu cầu mới đã được phân tích lại để chắc chắn tạo đúng brief.
"""
from __future__ import annotations

import copy
import itertools
import math

from config import BUDGET_TOLERANCE
from tools.brief_parser import EXTRA_KEYWORDS, inspect_request
from tools.docx_writer import vn_num, vnd

MAX_FLOORS = 5
MAX_PROPOSALS = 3


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else vn_num(value)


def _assumed(brief: dict, prefix: str) -> bool:
    return any(note.startswith(prefix) for note in brief.get("gia_dinh_bo_sung", []))


def _best_option(brief: dict) -> dict | None:
    """Lập 3 phương án như Kiến trúc sư, đánh giá như Dự toán, trả phương án khả thi tốt nhất."""
    from agents import architect
    from agents.cost_estimator import _option_rank, evaluate_option

    try:
        base = architect.initial_program(brief)
        versions: dict = {}
        options = [{**opt, "program": architect.version_option(opt["program"], brief, "de-xuat", versions)}
                   for opt in architect.make_options(brief, base)]
        evaluated = [evaluate_option(brief, option) for option in options]
    except Exception:  # noqa: BLE001 - biến thể không lập được chương trình thì bỏ qua
        return None
    eligible = sorted((opt for opt in evaluated if opt["eligible"]), key=lambda opt: _option_rank(opt, brief))
    return eligible[0] if eligible else None


def _within_budget(brief: dict, option: dict) -> bool:
    return _assumed(brief, "Ngân sách:") or option["chi_so"]["vuot_pct"] <= BUDGET_TOLERANCE


def _changes(brief: dict) -> list[tuple[str, int, str, object]]:
    """Các thay đổi đơn lẻ: (nhóm, điểm thay đổi, mô tả, giá trị mới)."""
    req = brief["yeu_cau_phong"]
    out = []
    floors = req.get("so_tang")
    for value in range(1, MAX_FLOORS + 1):
        if value != floors:
            label = f"Đổi số tầng {floors} → {value}" if floors else f"Chốt {value} tầng"
            out.append(("so_tang", abs(value - floors) if floors else 1, label, value))
    for fewer in (1, 2, 3):
        if req["phong_ngu"] - fewer >= 1:
            out.append(("phong_ngu", 2 * fewer,
                        f"Giảm phòng ngủ {req['phong_ngu']} → {req['phong_ngu'] - fewer}", req["phong_ngu"] - fewer))
    if req.get("phong_lam_viec"):
        out.append(("phong_lam_viec", 2, "Bỏ phòng làm việc riêng (gộp vào sinh hoạt chung)", 0))
    if req.get("gara") == "ô tô":
        out.append(("gara", 2, "Đổi gara ô tô thành chỗ để xe máy", "xe máy"))
    if req.get("gara"):
        out.append(("gara", 3, "Bỏ gara, để xe ngoài nhà", None))
    if req.get("phong_tho"):
        out.append(("phong_tho", 4, "Bỏ phòng thờ riêng (đặt bàn thờ tại phòng sinh hoạt tầng trên)", 0))
    return out


def _apply(brief: dict, changes: tuple) -> dict:
    variant = copy.deepcopy(brief)
    for group, _, _, value in changes:
        variant["yeu_cau_phong"][group] = value
    return variant


def request_text(brief: dict) -> str:
    """Viết lại brief thành mô tả tiếng Việt mà bộ phân tích yêu cầu đọc lại đúng."""
    lot, family, req = brief["lo_dat"], brief["gia_dinh"], brief["yeu_cau_phong"]
    parts = []
    lot_text = f"Lô đất {_num(lot['rong'])}x{_num(lot['dai'])}m"
    if not _assumed(brief, "Hướng mặt tiền:"):
        lot_text += f", mặt tiền hướng {lot['huong']}"
    if not _assumed(brief, "Địa điểm:"):
        lot_text += f", tại {lot['tinh']}"
    parts.append(lot_text + ".")
    if lot.get("ma_lo_dat"):
        parts.append(f"Mã lô đất {lot['ma_lo_dat']}.")
    people = [] if _assumed(brief, "Số người:") else [f"Gia đình {family['so_nguoi']} người"]
    if family.get("nam_sinh_chu_nha"):
        people.append(f"chủ nhà là {'chồng' if family['gioi_tinh_chu_nha'] == 'nam' else 'nữ'}"
                      f"{', sinh năm' if family['gioi_tinh_chu_nha'] == 'nam' else ' sinh năm'} {family['nam_sinh_chu_nha']}")
    if people:
        parts.append("; ".join(people) + ".")
    rooms = []
    if req.get("so_tang"):
        rooms.append(f"{req['so_tang']} tầng")
    rooms.append(f"{req['phong_ngu']} phòng ngủ")
    if req.get("phong_tho"):
        rooms.append("1 phòng thờ")
    if req.get("phong_lam_viec"):
        rooms.append("1 phòng làm việc")
    if req.get("gara"):
        rooms.append(f"có chỗ để {req['gara']}" if req["gara"] == "xe máy" else "có gara ô tô")
    parts.append("Cần " + ", ".join(rooms) + ".")
    if not _assumed(brief, "Ngân sách:"):
        parts.append(f"Ngân sách {vn_num(brief['ngan_sach'] / 1e9, 2)} tỷ.")
    style = [] if _assumed(brief, "Phong cách:") else [f"Phong cách {brief['phong_cach']}"]
    reverse = {}
    for key, value in EXTRA_KEYWORDS.items():
        reverse.setdefault(value, key)
    style += [reverse[item] for item in brief.get("yeu_cau_khac", []) if item in reverse]
    if style:
        parts.append(", ".join(style) + ".")
    return " ".join(parts)


def _round_budget(amount: float) -> int:
    return int(math.ceil(amount / 1e8) * 1e8)


def _proposal(brief: dict, variant: dict, option: dict, changes: list[str], score: int) -> dict | None:
    text = request_text(variant)
    parsed, questions, conflicts = inspect_request(text, {})
    keys = ("yeu_cau_phong", "ngan_sach", "lo_dat")
    if parsed is None or questions or conflicts or any(parsed[k] != variant[k] for k in keys):
        return None
    metrics = option["chi_so"]
    return {
        "tieu_de": "; ".join(changes),
        "thay_doi": changes,
        "diem_thay_doi": score,
        "phuong_an": option["id"],
        "ten_phuong_an": option["ten"],
        "so_tang": metrics["so_tang"],
        "tong_dien_tich_san": metrics["tong_dien_tich_san"],
        "chi_phi": metrics["chi_phi"],
        "ngan_sach": variant["ngan_sach"],
        "vuot_pct": metrics["vuot_pct"],
        "can_xac_nhan": variant["lo_dat"] != brief["lo_dat"],
        "ly_do": (f"{option['ten']} bố trí được trên lô {_num(variant['lo_dat']['rong'])}×{_num(variant['lo_dat']['dai'])} m: "
                  f"{metrics['so_tang']} tầng, {vn_num(metrics['tong_dien_tich_san'])} m² sàn, dự toán {vnd(metrics['chi_phi'])} "
                  f"({'+' if metrics['vuot_pct'] >= 0 else ''}{vn_num(metrics['vuot_pct'] * 100)}% so với ngân sách)."),
        "request": text,
    }


def find_adjustments(brief: dict, limit: int = MAX_PROPOSALS) -> list[dict]:
    """Trả tối đa `limit` đề xuất khả thi, ít thay đổi nhất trước."""
    singles = _changes(brief)
    combos = [(c,) for c in singles]
    combos += [pair for pair in itertools.combinations(singles, 2) if pair[0][0] != pair[1][0]]
    combos.sort(key=lambda combo: sum(change[1] for change in combo))
    found, over_budget, seen = [], [], set()
    budget_fixed = not _assumed(brief, "Ngân sách:")
    for combo in [(), *combos]:
        score = sum(change[1] for change in combo)
        if len(found) >= limit and score > found[-1]["diem_thay_doi"]:
            break
        variant = _apply(brief, combo)
        signature = repr(sorted(variant["yeu_cau_phong"].items()))
        if signature in seen:
            continue
        seen.add(signature)
        option = _best_option(variant)
        if option is None:
            continue
        labels = [change[2] for change in combo]
        if _within_budget(variant, option):
            if combo:
                proposal = _proposal(brief, variant, option, labels, score)
                if proposal:
                    found.append(proposal)
        elif budget_fixed:
            over_budget.append((score, variant, option, labels))
    # Bố trí được nhưng vượt ngân sách: đề xuất mức ngân sách tương ứng (thay đổi ít nhất).
    budget_proposal = None
    for score, variant, option, labels in sorted(over_budget, key=lambda item: (item[0], item[2]["chi_so"]["chi_phi"]))[:1]:
        budget = _round_budget(option["chi_so"]["chi_phi"])
        raised = {**variant, "ngan_sach": budget}
        priced = _best_option(raised)
        if priced and _within_budget(raised, priced):
            label = f"Tăng ngân sách {vn_num(brief['ngan_sach'] / 1e9, 2)} → {vn_num(budget / 1e9, 2)} tỷ"
            weight = 3 + math.ceil((budget / brief["ngan_sach"] - 1) / 0.1)  # mỗi 10% ngân sách tăng thêm = 1 điểm
            budget_proposal = _proposal(brief, raised, priced, [*labels, label], score + weight)
    if not found and budget_proposal is None:
        lot_proposal = _lot_proposal(brief)
        return [lot_proposal] if lot_proposal else []
    found.sort(key=lambda item: (item["diem_thay_doi"], item["chi_phi"]))
    unique, titles = [], set()
    for item in found:
        if item["request"] not in titles:
            titles.add(item["request"])
            unique.append(item)
    unique = unique[:limit]
    if budget_proposal:  # luôn giữ một lựa chọn giữ nguyên công năng, chỉ tăng ngân sách
        unique = [*unique[:limit - 1], budget_proposal]
        unique.sort(key=lambda item: (item["diem_thay_doi"], item["chi_phi"]))
    return unique


def _lot_proposal(brief: dict) -> dict | None:
    """Không biến thể nào bố trí được: tìm kích thước lô tối thiểu cho đúng yêu cầu hiện tại."""
    lot = brief["lo_dat"]
    for key, label, start in (("dai", "chiều sâu", lot["dai"]), ("rong", "chiều rộng", lot["rong"])):
        for value in range(math.floor(start) + 1, math.floor(start) + 21):
            variant = copy.deepcopy(brief)
            variant["lo_dat"][key] = float(value)
            option = _best_option(variant)
            if option and _within_budget(variant, option):
                change = (f"Kiểm tra lại kích thước lô: mẫu nhà ống của hệ thống cần {label} tối thiểu {value} m "
                          f"(hiện {_num(start)} m)")
                return _proposal(brief, variant, option, [change], 50)
    return None
