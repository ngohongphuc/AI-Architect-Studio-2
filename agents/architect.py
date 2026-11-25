"""Thiết kế công năng, lựa chọn và điều chỉnh chương trình phòng."""
from __future__ import annotations

import copy
import math
import re
from collections import Counter
from uuid import NAMESPACE_URL, uuid4, uuid5

from agents.base import agent_node
from tools.rules import load_rules, min_room

GRADES = ["tiết kiệm", "trung bình", "khá", "cao cấp"]

MATERIALS = {
    "hiện đại": {"san": "gạch granite 60×60", "mat_tien": "sơn ngoại thất trắng + kính cường lực",
                 "cua": "nhôm hệ Xingfa + kính cường lực", "cua_phong": "gỗ công nghiệp",
                 "lan_can": "kính cường lực 10 mm", "mai": "BTCT, chống nóng bằng gạch lỗ"},
    "tối giản": {"san": "gạch giả bê tông 60×60", "mat_tien": "sơn ngoại thất xám nhạt + lam nhôm",
                 "cua": "nhôm hệ + kính", "cua_phong": "gỗ công nghiệp", "lan_can": "thép sơn tĩnh điện",
                 "mai": "BTCT"},
    "tân cổ điển": {"san": "gạch granite vân đá 80×80", "mat_tien": "phào chỉ GRC + sơn kem",
                    "cua": "nhôm hệ + kính", "cua_phong": "gỗ tự nhiên", "lan_can": "con tiện GRC",
                    "mai": "BTCT + mái Thái ngói"},
    "Indochine": {"san": "gạch bông + gỗ", "mat_tien": "sơn vàng nhạt + lam gỗ", "cua": "gỗ + kính",
                  "cua_phong": "gỗ tự nhiên", "lan_can": "sắt nghệ thuật", "mai": "BTCT"},
}


def _n(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def _materials(style: str) -> dict:
    return dict(MATERIALS.get(style, MATERIALS["hiện đại"]))


def _room(ten, loai, dien_tich, vi_tri="trước", **kw) -> dict:
    return {"ten": ten, "loai": loai, "dien_tich": round(dien_tich, 1), "vi_tri": vi_tri, **kw}


def _core() -> list[dict]:
    return [{"ten": "Cầu thang", "loai": "thang", "co_dinh": True, "vi_tri": "lõi", "dien_tich": 0},
            {"ten": "Giếng trời", "loai": "gieng_troi", "co_dinh": True, "vi_tri": "lõi", "dien_tich": 0}]


def _wc(W: float, name="WC") -> dict:
    return _room(name, "wc", max(4.2, 1.6 * (W - 1.1)), "trước", nho=True)


def _balcony(W: float) -> dict:
    return _room("Ban công", "ban_cong", 1.2 * W, "mặt tiền", co_dinh=True, chieu_sau=1.2)


def proposed_floors(brief: dict) -> int:
    req = brief["yeu_cau_phong"]
    upper = math.ceil((req["phong_ngu"] + bool(req.get("phong_lam_viec"))) / 2)
    return req.get("so_tang") or min(1 + upper + bool(req.get("phong_tho")),
                                     load_rules()["so_tang_toi_da"]["gia_tri"])


def initial_program(brief: dict, keep: dict | None = None, concept: dict | None = None) -> dict:
    """Lập chương trình công năng từ brief. `keep` giữ lại các quyết định đã sửa (sân sau, vật liệu)."""
    W = brief["lo_dat"]["rong"]
    req = brief["yeu_cau_phong"]
    n_bed = max(1, int(req.get("phong_ngu") or 1))
    tho = bool(req.get("phong_tho"))
    gara = req.get("gara")
    lam_viec = bool(req.get("phong_lam_viec"))
    max_floors = load_rules()["so_tang_toi_da"]["gia_tri"]
    notes = []

    needed_upper = math.ceil((n_bed + (1 if lam_viec else 0)) / 2) + (1 if tho else 0)
    upper = (concept["so_tang"] if concept else proposed_floors(brief)) - 1
    if 0 < upper < needed_upper:
        notes.append("Số tầng giới hạn vị trí dành cho các phòng yêu cầu.")

    # --- Phân bổ phòng cho các tầng trên: mỗi tầng 2 vị trí (trước, sau) ---
    bedrooms = [("Phòng ngủ master" if i == 0 else f"Phòng ngủ {i + 1}") for i in range(n_bed)]
    slots: list[list] = [[None, None] for _ in range(upper)]
    top = upper - 1
    bed_floors = upper - 1 if tho and upper >= 2 else upper
    if tho and upper >= 2 and bed_floors * 2 >= n_bed + (1 if lam_viec else 0):
        slots[top] = ["tho", "san_phoi"]
    elif tho and upper:
        slots[top][0] = "tho"
        bed_floors = upper
    queue = list(bedrooms)
    for f in range(bed_floors):
        for s in (0, 1):
            if slots[f][s] is None and queue:
                slots[f][s] = queue.pop(0)
    ground_bed = queue.pop(0) if queue else None
    if queue and upper:
        notes.append(f"Không đủ tầng cho {len(queue)} phòng ngủ còn lại (giới hạn {max_floors} tầng)")
    extras = (["lam_viec"] if lam_viec else []) + ["sinh_hoat"]
    for f in range(upper):
        for s in (0, 1):
            if slots[f][s] is None:
                slots[f][s] = extras.pop(0) if extras else "san_phoi"
    if lam_viec and "lam_viec" in extras:
        notes.append("Không còn vị trí cho phòng làm việc – đề xuất kết hợp trong phòng ngủ master")

    program: dict = {
        "so_tang": upper + 1,
        "chieu_cao_tang": {"tang_1": 3.6 if gara else 3.4, "tang_khac": 3.3},
        "phong_cach": brief.get("phong_cach", "hiện đại"),
        "vat_lieu": _materials(brief.get("phong_cach", "hiện đại")),
        "cap_hoan_thien": "cao cấp" if "Hoàn thiện cao cấp" in brief.get("yeu_cau_khac", []) else (
            "trung bình" if "Ưu tiên tiết kiệm chi phí" in brief.get("yeu_cau_khac", []) else "khá"),
        "loai_mai": "BTCT",
        "san_truoc": 0.0,
        "san_sau": 0.0,
        "ghi_chu": notes,
        "lich_su_sua": [],
    }

    # --- Tầng 1 ---
    t1 = []
    if gara:
        area = max(5.5 * W, 16) if gara == "ô tô" else max(3.0 * W, 12)
        t1.append(_room("Gara " + gara, "gara", area, "mặt tiền"))
    t1.append(_room("Phòng khách", "khach", 22 if W >= 4.5 else 18, "trước"))
    t1.append(_wc(W))
    t1 += _core()
    if ground_bed:
        t1.append(_room("Bếp + ăn", "bep", 16, "sau", vung="sau"))
        t1.append(_room(ground_bed, "ngu", 12, "sau"))
    else:
        t1.append(_room("Bếp + ăn", "bep", 20, "sau"))
    if not upper:
        t1.extend(_room(bedroom, "ngu", 12, "sau") for bedroom in queue)
        if tho:
            t1.append(_room("Phòng thờ", "tho", 12, "sau"))
        if lam_viec:
            t1.append(_room("Phòng làm việc", "lam_viec", 12, "trước"))
    program["tang_1"] = t1
    if concept:
        program.update(phong_cach=concept["phong_cach"], vat_lieu=dict(concept["vat_lieu"]))

    # --- Tầng trên ---
    names = {"tho": ("Phòng thờ", "tho", 12), "san_phoi": ("Sân phơi", "san_phoi", 10),
             "lam_viec": ("Phòng làm việc", "lam_viec", 12), "sinh_hoat": ("Phòng sinh hoạt chung", "sinh_hoat", 14)}
    for f, (front, back) in enumerate(slots, start=2):
        rooms = []
        has_bed = any(s and s.startswith("Phòng ngủ") for s in (front, back))
        if front != "tho":
            rooms.append(_balcony(W))
        else:
            rooms.append(_room("Sân thượng trước", "san_phoi", 8, "mặt tiền",
                               ghi_chu="Trồng cây xanh, che nắng cho phòng thờ"))
        for pos, s in (("trước", front), ("sau", back)):
            if s.startswith("Phòng ngủ"):
                rooms.append(_room(s, "ngu", 16 if "master" in s else 13, pos))
            else:
                ten, loai, a = names[s]
                rooms.append(_room(ten, loai, a, pos))
        if has_bed or (front in ("lam_viec", "sinh_hoat")):
            rooms.append(_wc(W))
        elif front == "tho" and back == "san_phoi":
            rooms.append(_room("Phòng giặt + kho", "kho", max(4.0, 1.4 * (W - 1.1)), "sau", nho=True))
        rooms += _core()
        program[f"tang_{f}"] = rooms

    # Lô quá sâu so với nhu cầu -> chủ động để sân sau (thông gió, giảm mật độ)
    Llot = brief["lo_dat"]["dai"]
    need = 0.0
    for k in _floors(program):
        d = 0.0
        for r in program[k]:
            if r["loai"] in ("thang", "gieng_troi"):
                continue
            room_width = max(W - 1.1, W / 2) if r.get("nho") else W
            d += r["chieu_sau"] if r.get("co_dinh") else r["dien_tich"] / room_width
        need = max(need, d)
    extra = Llot - (need * 1.3 + 4.8)
    if extra > 1.5:
        program["san_sau"] = min(math.floor(extra * 2) / 2, 6.0)
        notes.append(f"Lô đất sâu: bố trí sân sau {_n(program['san_sau'])} m để thông gió, lấy sáng")

    if keep:
        for k in ("san_truoc", "ten_san_truoc", "san_sau", "cap_hoan_thien", "vat_lieu", "lich_su_sua", "loai_mai"):
            if k in keep:
                program[k] = copy.deepcopy(keep[k])
    return program


# ---------------------------------------------------------------------------
# Xử lý phản hồi
# ---------------------------------------------------------------------------
def _floors(program):
    return sorted((k for k in program if k.startswith("tang_")), key=lambda k: int(k.split("_")[1]))


def _drop_top_floor(program: dict) -> bool:
    """Gộp phòng thờ của tầng trên cùng xuống vị trí phía sau tầng dưới (thay phòng sinh hoạt / sân phơi)."""
    keys = _floors(program)
    if len(keys) < 3:
        return False
    top, below = program[keys[-1]], program[keys[-2]]
    tho = next((r for r in top if r["loai"] == "tho"), None)
    target = next((r for r in below if r["vi_tri"] == "sau" and r["loai"] in ("sinh_hoat", "san_phoi", "lam_viec")),
                  None)
    if tho is None or target is None:
        return False
    target.update({"ten": "Phòng thờ", "loai": "tho", "dien_tich": 12})
    # phòng thờ ở tầng trên cùng mới -> không còn gì phía trên
    del program[keys[-1]]
    program["so_tang"] = len(keys) - 1
    return True


def apply_feedback(program: dict, feedback: list[dict], brief: dict) -> tuple[dict, list[str]]:
    program = copy.deepcopy(program)
    W = brief["lo_dat"]["rong"]
    Llot = brief["lo_dat"]["dai"]
    changes: list[str] = []
    codes = {f.get("ma") for f in feedback}

    if "THUA_PHONG" in codes:
        program = initial_program(brief, keep=program)
        changes.append("Lập lại chương trình công năng theo số phòng trong brief")
    if "THIEU_PHONG" in codes:
        # thêm 1 tầng (nếu còn trong giới hạn) rồi lập lại chương trình để đủ phòng
        b2 = copy.deepcopy(brief)
        max_floors = load_rules()["so_tang_toi_da"]["gia_tri"]
        b2["yeu_cau_phong"]["so_tang"] = brief["yeu_cau_phong"].get("so_tang") or min(program["so_tang"] + 1, max_floors)
        program = initial_program(b2, keep=program)
        changes.append(f"Lập lại chương trình công năng ({program['so_tang']} tầng) để đủ số phòng theo brief")

    done_codes = set()
    for f in feedback:
        ma, data = f.get("ma"), f.get("du_lieu", {})
        if ma in ("KHONG_DU_CHO", "MAT_DO", "VUOT_NGAN_SACH") and ma in done_codes:
            continue
        done_codes.add(ma)
        if ma == "MAT_DO":
            allowed = data["cho_phep_m2"]
            need_depth = Llot - program.get("san_truoc", 0) - program.get("san_sau", 0) - allowed / W
            gara = next((r for r in program.get("tang_1", []) if r["loai"] == "gara" and "ô tô" in r["ten"]), None)
            if gara and program.get("san_truoc", 0) == 0 and need_depth >= 2.5:
                # chuyển chỗ đỗ ô tô ra sân trước (không tính vào diện tích xây dựng)
                program["tang_1"].remove(gara)
                program["san_truoc"] = 5.5
                program["ten_san_truoc"] = "Sân đỗ xe ô tô"
                changes.append("Chuyển gara ô tô ra sân trước 5,5 m (sân đỗ xe) để giảm mật độ xây dựng")
            else:
                sb_new = Llot - program.get("san_truoc", 0) - allowed / W
                sb_new = max(program.get("san_sau", 0) + 0.5, math.ceil(sb_new * 2 - 1e-9) / 2)
                program["san_sau"] = round(sb_new, 2)
                changes.append(f"Thêm sân sau {_n(program['san_sau'])} m để giảm mật độ xây dựng")
        elif ma == "SO_TANG":
            if not brief["yeu_cau_phong"].get("so_tang") and _drop_top_floor(program):
                changes.append(f"Giảm còn {program['so_tang']} tầng (gộp phòng thờ xuống tầng dưới)")
        elif ma == "CHIEU_CAO_TANG":
            limits = load_rules()["chieu_cao_tang"]
            clear = limits["thong_thuy_min"] + limits["chieu_day_san"] + 0.1
            h = program["chieu_cao_tang"]
            new_heights = {key: min(max(value, limits[f"{key}_min"], clear), limits[f"{key}_max"])
                           for key, value in h.items()}
            if h != new_heights:
                program["chieu_cao_tang"] = new_heights
                changes.append("Điều chỉnh chiều cao tầng theo phép kiểm đang áp dụng")
        elif ma == "CAU_THANG" and not program.get("doi_chieu_cau_thang"):
            program["doi_chieu_cau_thang"] = True
            changes.append("Tính lại bề rộng vế, số bậc và kích thước bậc theo phép kiểm cầu thang")
        elif ma == "PHONG_NHO":
            k = f"tang_{data['tang']}"
            for r in program.get(k, []):
                if r["ten"] == data["phong"]:
                    r["dien_tich"] = round(max(r["dien_tich"], data["can"]) * 1.15, 1)
                    changes.append(f"Tăng diện tích {r['ten']} tầng {data['tang']} lên {r['dien_tich']} m²")
        elif ma == "THIEU_SANG":
            k = f"tang_{data['tang']}"
            for r in program.get(k, []):
                if r["ten"] == data["phong"] and r["vi_tri"] != "giữa":
                    r["vung"] = "sau" if r["vi_tri"] == "sau" else "trước"
                    r["vi_tri"] = "giữa"
                    changes.append(f"Dời {r['ten']} tầng {data['tang']} sát giếng trời để lấy sáng")
        elif ma == "WC_TREN_THO":
            k = f"tang_{data['tang_wc']}"
            for r in program.get(k, []):
                if r["loai"] == "wc" and r.get("vi_tri") != "sau":
                    r["vi_tri"] = "sau"
                    changes.append(f"Dời WC tầng {data['tang_wc']} ra phía sau lõi thang (không nằm trên phòng thờ)")
        elif ma == "BEP_KE_WC":
            k = f"tang_{data['tang']}"
            for r in program.get(k, []):
                if r["loai"] == "wc":
                    r["vi_tri"] = "trước" if r.get("vi_tri") == "sau" else "sau"
                    changes.append(f"Đổi vị trí WC tầng {data['tang']} để không kề bếp")
        elif ma == "KHONG_DU_CHO":
            for k in _floors(program):
                for r in program[k]:
                    if not r.get("co_dinh") and not r.get("nho"):
                        r["dien_tich"] = round(r["dien_tich"] * 0.85, 1)
            if program.get("san_sau", 0) >= 1.5:
                program["san_sau"] = round(program["san_sau"] - 0.5, 2)
            changes.append("Giảm 15% diện tích mong muốn các phòng để đủ chỗ bố trí")
        elif ma == "VUOT_NGAN_SACH":
            changes += _save_cost(program, data, brief)
        elif ma == "USER":
            program, brief, ch, reply = _user_feedback(program, f.get("noi_dung", ""), brief, f.get("lich_su"))
            program["_brief"] = brief
            program["_reply"] = {"nguoi_dung": f.get("noi_dung", ""), "kien_truc_su": reply}
            changes += ch
    if changes:
        program.setdefault("lich_su_sua", []).extend(changes)
    return program, changes


def _save_cost(program: dict, data: dict, brief: dict) -> list[str]:
    over = data.get("vuot_pct", 0.0)
    changes = []
    steps = 2 if over > 0.25 else 1
    for _ in range(steps):
        g = program.get("cap_hoan_thien", "khá")
        if GRADES.index(g) > 0:
            program["cap_hoan_thien"] = GRADES[GRADES.index(g) - 1]
            changes.append(f"Hạ gói hoàn thiện từ '{g}' xuống '{program['cap_hoan_thien']}'")
            continue
        if program["vat_lieu"].get("cua_phong") == "gỗ tự nhiên":
            program["vat_lieu"]["cua_phong"] = "gỗ công nghiệp"
            changes.append("Đổi cửa phòng gỗ tự nhiên sang gỗ công nghiệp")
            continue
        if program.get("loai_mai") != "tôn" and program["vat_lieu"].get("mai", "").startswith("BTCT + mái"):
            program["vat_lieu"]["mai"] = "BTCT"
            changes.append("Bỏ mái ngói trang trí")
            continue
        if not brief["yeu_cau_phong"].get("so_tang") and _drop_top_floor(program):
            changes.append(f"Giảm còn {program['so_tang']} tầng để giảm diện tích sàn")
            continue
        program["san_sau"] = round(program.get("san_sau", 0) + 1.0, 2)
        changes.append(f"Tăng sân sau lên {_n(program['san_sau'])} m để giảm diện tích xây dựng")
    return changes


# ---------------------------------------------------------------------------
# Chỉnh sửa trực tiếp chương trình công năng (dùng khi người dùng duyệt phương án)
# ---------------------------------------------------------------------------
ROOM_TYPES = {"gara": "Gara", "khach": "Phòng khách", "bep": "Bếp", "wc": "WC", "ngu": "Phòng ngủ",
              "tho": "Phòng thờ", "lam_viec": "Phòng làm việc", "sinh_hoat": "Sinh hoạt chung", "kho": "Kho / giặt",
              "ban_cong": "Ban công", "san_phoi": "Sân phơi / sân thượng"}
POSITIONS = ["mặt tiền", "trước", "giữa", "sau"]
SMALL_TYPES = {"wc", "kho"}


def program_to_rows(program: dict) -> list[dict]:
    """Chương trình công năng -> bảng phẳng (bỏ lõi thang + giếng trời vì cố định)."""
    rows = []
    for k in _floors(program):
        for r in program[k]:
            if r["loai"] in ("thang", "gieng_troi"):
                continue
            rows.append({"id": r.get("id"), "tang": int(k.split("_")[1]), "ten": r["ten"], "loai": r["loai"],
                         "dien_tich": float(r["dien_tich"]), "vi_tri": r.get("vi_tri", "trước")})
    return rows


def rows_to_program(program: dict, rows: list[dict], W: float) -> tuple[dict, list[str]]:
    """Bảng đã chỉnh -> chương trình công năng mới. Trả về (program, lỗi)."""
    errors = []
    new = {k: copy.deepcopy(v) for k, v in program.items() if not k.startswith("tang_")}
    floors: dict[int, list] = {}
    for i, r in enumerate(rows, start=1):
        ten = str(r.get("ten") or "").strip()
        loai = r.get("loai")
        if not ten and not loai:
            continue  # dòng trống
        try:
            tang = int(r.get("tang"))
            dt = float(r.get("dien_tich"))
        except (TypeError, ValueError):
            errors.append(f"Dòng {i}: tầng / diện tích không hợp lệ")
            continue
        if loai not in ROOM_TYPES:
            errors.append(f"Dòng {i} ({ten}): loại phòng không hợp lệ")
            continue
        if not math.isfinite(dt) or dt <= 0 or tang < 1:
            errors.append(f"Dòng {i} ({ten}): diện tích và tầng phải > 0")
            continue
        vi_tri = r.get("vi_tri") if r.get("vi_tri") in POSITIONS else "trước"
        room = _room(ten or ROOM_TYPES[loai], loai, dt, vi_tri)
        if r.get("id"):
            room["id"] = r["id"]
        if loai in SMALL_TYPES:
            room["nho"] = True
        if loai == "ban_cong":
            room.update(co_dinh=True, chieu_sau=round(dt / W, 2))
        if vi_tri == "giữa":
            room["vung"] = "trước"
        floors.setdefault(tang, []).append(room)
    if 1 not in floors:
        errors.append("Phải có ít nhất 1 phòng ở tầng 1")
    max_floors = load_rules()["so_tang_toi_da"]["gia_tri"]
    keys = sorted(floors)
    if len(keys) > max_floors:
        errors.append(f"Tối đa {max_floors} tầng")
    for n, k in enumerate(keys, start=1):          # đánh số lại tầng liên tục 1..n
        new[f"tang_{n}"] = floors[k] + _core()
    new["so_tang"] = len(keys)
    return new, errors


def apply_user_edit(program: dict, rows: list[dict], settings: dict, brief: dict) -> tuple[dict, dict, list[str]]:
    """Áp dụng chỉnh sửa trực tiếp của người dùng. Trả về (program, brief cập nhật, mô tả thay đổi)."""
    W = brief["lo_dat"]["rong"]
    new, errors = rows_to_program(program, rows, W)
    if errors:
        raise ValueError("; ".join(errors))
    for key in ("san_truoc", "san_sau"):
        if key in settings:
            new[key] = max(0.0, round(float(settings[key]), 2))
    if settings.get("cap_hoan_thien") in GRADES:
        new["cap_hoan_thien"] = settings["cap_hoan_thien"]
    h = new.setdefault("chieu_cao_tang", {})
    for key in ("tang_1", "tang_khac"):
        if settings.get(key):
            h[key] = round(float(settings[key]), 2)
    changes = _diff(program, new)
    new.setdefault("lich_su_sua", []).extend(changes)
    brief = sync_brief(brief, new)
    return new, brief, changes


def sync_brief(brief: dict, program: dict) -> dict:
    """Người dùng là chủ đầu tư: số phòng sau chỉnh sửa trở thành yêu cầu mới (để Kiểm định viên không ép thêm lại)."""
    b = copy.deepcopy(brief)
    rows = program_to_rows(program)
    yc = b["yeu_cau_phong"]
    yc["phong_ngu"] = sum(r["loai"] == "ngu" for r in rows)
    yc["phong_tho"] = int(any(r["loai"] == "tho" for r in rows))
    yc["phong_lam_viec"] = int(any(r["loai"] == "lam_viec" for r in rows))
    if not any(r["loai"] == "gara" for r in rows) and program.get("ten_san_truoc", "").find("đỗ xe") < 0:
        yc["gara"] = None
    yc["so_tang"] = program["so_tang"]
    return b


def _diff(old: dict, new: dict) -> list[str]:
    out = []
    a = {(r["tang"], r["ten"]): r for r in program_to_rows(old)}
    b = {(r["tang"], r["ten"]): r for r in program_to_rows(new)}
    for key in b.keys() - a.keys():
        out.append(f"Thêm {key[1]} ({b[key]['dien_tich']:g} m²) ở tầng {key[0]}")
    for key in a.keys() - b.keys():
        out.append(f"Bỏ {key[1]} ở tầng {key[0]}")
    for key in a.keys() & b.keys():
        x, y = a[key], b[key]
        if abs(x["dien_tich"] - y["dien_tich"]) > 1e-6:
            out.append(f"{key[1]} tầng {key[0]}: {x['dien_tich']:g} → {y['dien_tich']:g} m²")
        if x["vi_tri"] != y["vi_tri"] or x["loai"] != y["loai"]:
            out.append(f"{key[1]} tầng {key[0]}: đổi vị trí/loại ({x['vi_tri']} → {y['vi_tri']})")
    for k, label in (("san_truoc", "Sân trước"), ("san_sau", "Sân sau")):
        if abs(old.get(k, 0) - new.get(k, 0)) > 1e-6:
            out.append(f"{label}: {_n(old.get(k, 0))} → {_n(new.get(k, 0))} m")
    if old.get("cap_hoan_thien") != new.get("cap_hoan_thien"):
        out.append(f"Gói hoàn thiện: {old.get('cap_hoan_thien')} → {new.get('cap_hoan_thien')}")
    if old.get("chieu_cao_tang") != new.get("chieu_cao_tang"):
        out.append(f"Chiều cao tầng: {new.get('chieu_cao_tang')}")
    if old.get("so_tang") != new.get("so_tang"):
        out.append(f"Số tầng: {old.get('so_tang')} → {new.get('so_tang')}")
    return out or ["Người dùng giữ nguyên phương án"]


# ---------------------------------------------------------------------------
# Góp ý bằng lời -> thao tác sửa
# ---------------------------------------------------------------------------
_NUM = r"(\d+(?:[.,]\d+)?)"
_WORD_NUM = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5}


def _f(v: str) -> float:
    return float(v.replace(",", "."))


def _find_room(program: dict, name: str, tang: int | None = None):
    name = name.lower().strip()
    for k in _floors(program):
        if tang and k != f"tang_{tang}":
            continue
        for r in program[k]:
            if r["loai"] in ("thang", "gieng_troi"):
                continue
            if r["ten"].lower() == name or r["ten"].lower().startswith(name) or name in r["ten"].lower():
                return k, r
    return None, None


def _rule_ops(text: str) -> list[dict]:
    """Phân tích góp ý tiếng Việt thường gặp thành danh sách thao tác."""
    t = text.lower()
    ops = []
    if "tiết kiệm" in t or "rẻ hơn" in t or "giảm chi phí" in t:
        ops.append({"op": "tiet_kiem"})
    for g in GRADES[::-1]:
        if re.search(rf"(gói|hoàn thiện|mức)\s*{g}", t) or (g == "cao cấp" and "cao cấp" in t):
            ops.append({"op": "cap_hoan_thien", "gia_tri": g})
            break
    for key, word in (("san_sau", "sân sau"), ("san_truoc", "sân trước")):
        m = re.search(rf"{word}\D{{0,12}}?{_NUM}", t)
        if m:
            ops.append({"op": key, "gia_tri": _f(m.group(1))})
        elif re.search(rf"(bỏ|không cần|không có)\s*{word}", t):
            ops.append({"op": key, "gia_tri": 0})
    m = re.search(rf"(\d+)\s*tầng", t)
    if m and not re.search(r"tầng\s*\d", t[max(0, m.start() - 6):m.start() + 1]):
        ops.append({"op": "so_tang", "gia_tri": int(m.group(1))})
    elif "bớt tầng" in t or "giảm tầng" in t or "bớt 1 tầng" in t:
        ops.append({"op": "bot_tang"})
    elif "thêm tầng" in t or "thêm 1 tầng" in t:
        ops.append({"op": "them_tang"})
    m = re.search(r"(thêm|bổ sung)\s*(\d+|một|hai|ba)?\s*phòng ngủ", t)
    if m:
        n = m.group(2) or "1"
        ops.append({"op": "so_phong_ngu_delta", "gia_tri": int(n) if n.isdigit() else _WORD_NUM.get(n, 1)})
    m = re.search(r"(bớt|giảm|bỏ)\s*(\d+|một|hai)?\s*phòng ngủ", t)
    if m:
        n = m.group(2) or "1"
        ops.append({"op": "so_phong_ngu_delta", "gia_tri": -(int(n) if n.isdigit() else _WORD_NUM.get(n, 1))})
    m = re.search(r"(\d+)\s*phòng ngủ", t)
    if m and not any(o["op"] == "so_phong_ngu_delta" for o in ops):
        ops.append({"op": "so_phong_ngu", "gia_tri": int(m.group(1))})
    for word, key in (("phòng thờ", "phong_tho"), ("phòng làm việc", "phong_lam_viec")):
        if re.search(rf"(bỏ|không cần|không có)\s*{word}", t):
            ops.append({"op": key, "gia_tri": 0})
        elif re.search(rf"(thêm|cần|có)\s*{word}", t):
            ops.append({"op": key, "gia_tri": 1})
    if re.search(r"(bỏ|không cần)\s*(gara|chỗ để xe)", t):
        ops.append({"op": "gara", "gia_tri": None})
    elif re.search(r"gara\s*ô tô|để ô tô|đỗ ô tô", t):
        ops.append({"op": "gara", "gia_tri": "ô tô"})
    # "<tên phòng> [tầng N] <số> m2"  -> đặt diện tích; "<tên phòng> rộng/to hơn" -> +20%
    for m in re.finditer(rf"((?:phòng|bếp|gara|wc|ban công|sân phơi|sân thượng)[\w\s+]*?)(?:\s*tầng\s*(\d))?"
                         rf"\s*(?:là|=|:|lên|thành|khoảng)?\s*{_NUM}\s*(?:m2|m²|m\b)", t):
        ops.append({"op": "dien_tich", "phong": m.group(1).strip(), "tang": int(m.group(2)) if m.group(2) else None,
                    "gia_tri": _f(m.group(3))})
    for m in re.finditer(r"((?:phòng|bếp)[\w\s+]*?)\s*(rộng hơn|to hơn|lớn hơn|nhỏ hơn|hẹp hơn)", t):
        ops.append({"op": "ti_le_dien_tich", "phong": m.group(1).strip(),
                    "gia_tri": 1.2 if m.group(2) in ("rộng hơn", "to hơn", "lớn hơn") else 0.85})
    # dời phòng: "chuyển phòng thờ xuống tầng 3", "đưa bếp ra phía trước"
    for m in re.finditer(r"(?:chuyển|dời|đưa|đặt|để)\s+((?:phòng|bếp|wc|gara)[\w\s+]*?)\s*(?:lên|xuống|sang|về|ra|ở)?"
                         r"\s*(?:tầng\s*(\d)|(?:phía\s*)?(mặt tiền|trước|sau|giữa))", t):
        ops.append({"op": "chuyen_phong", "phong": m.group(1).strip(),
                    "tang_moi": int(m.group(2)) if m.group(2) else None, "vi_tri": m.group(3)})
    m = re.search(r"đổi tên\s+((?:phòng|bếp)[\w\s+]*?)\s*(?:thành|sang)\s*([\w\s+]+)", t)
    if m:
        ops.append({"op": "doi_ten", "phong": m.group(1).strip(), "gia_tri": m.group(2).strip().capitalize()})
    for style in ("tân cổ điển", "tối giản", "indochine", "hiện đại"):
        if re.search(rf"phong cách\s*{style}", t):
            ops.append({"op": "phong_cach", "gia_tri": "Indochine" if style == "indochine" else style})
            break
    m = re.search(rf"tầng\s*1\s*(?:cao)\s*{_NUM}", t)
    if m:
        ops.append({"op": "chieu_cao_tang", "tang": 1, "gia_tri": _f(m.group(1))})
    m = re.search(rf"(?:các tầng (?:trên|khác))\s*(?:cao)\s*{_NUM}", t)
    if m:
        ops.append({"op": "chieu_cao_tang", "tang": 0, "gia_tri": _f(m.group(1))})
    # cách nói tự nhiên thường gặp
    if re.search(r"(nhà|phòng|bên trong)[\w\s]{0,12}?(tối(?! giản| đa)|thiếu sáng|bí bách|ngột ngạt)", t) \
            and not any(o["op"] == "san_sau" for o in ops):
        ops.append({"op": "san_sau", "gia_tri": "+1"})
    if re.search(r"(bố mẹ|ông bà|người già)\b.*(tầng 1|dưới|lên xuống)", t):
        ops.append({"op": "chuyen_phong", "phong": "phòng ngủ", "tang_moi": 1, "vi_tri": "sau"})
    return ops


OP_HELP = """Các thao tác (op) hợp lệ:
- dien_tich: đặt diện tích phòng (phong, tang?, gia_tri = m²)
- ti_le_dien_tich: nhân diện tích phòng với hệ số (phong, tang?, gia_tri vd 1.2 / 0.85)
- them_phong: thêm phòng (tang, loai, phong = tên, gia_tri = m², vi_tri)
- xoa_phong: bỏ phòng (phong, tang?)
- chuyen_phong: dời phòng (phong, tang? = tầng hiện tại, tang_moi?, vi_tri?)
- doi_ten: đổi tên phòng (phong, gia_tri = tên mới)
- san_sau / san_truoc: chiều sâu sân (m)
- cap_hoan_thien: tiết kiệm | trung bình | khá | cao cấp
- phong_cach: hiện đại | tối giản | tân cổ điển | Indochine
- chieu_cao_tang: tang (1 = tầng 1, 0 = các tầng khác), gia_tri (m)
- so_tang, them_tang, bot_tang, so_phong_ngu, so_phong_ngu_delta, phong_tho (0/1), phong_lam_viec (0/1),
  gara ("xe máy" | "ô tô" | null), tiet_kiem
Loại phòng (loai): """ + ", ".join(f"{k} = {v}" for k, v in ROOM_TYPES.items())


def _context(program: dict, brief: dict, history: list[dict] | None) -> str:
    ld, yc = brief["lo_dat"], brief["yeu_cau_phong"]
    rooms = "\n".join(f"- Tầng {r['tang']}: {r['ten']} ({r['loai']}, {r['dien_tich']} m², {r['vi_tri']})"
                      for r in program_to_rows(program))
    hist = "\n".join(f"Chủ nhà: {h['nguoi_dung']}\nKiến trúc sư: {h['kien_truc_su']}" for h in (history or [])[-6:])
    return (f"Lô đất {ld['rong']}×{ld['dai']} m, hướng {ld['huong']}, {ld['tinh']}. Gia đình {brief['gia_dinh']['so_nguoi']} "
            f"người. Yêu cầu: {yc['phong_ngu']} phòng ngủ, phòng thờ {'có' if yc.get('phong_tho') else 'không'}, "
            f"gara {yc.get('gara') or 'không'}. Ngân sách {brief['ngan_sach'] / 1e9:.2f} tỷ, phong cách "
            f"{program.get('phong_cach', brief.get('phong_cach'))}.\n"
            f"Phương án hiện tại ({program['so_tang']} tầng, sân trước {program.get('san_truoc', 0)} m, sân sau "
            f"{program.get('san_sau', 0)} m, gói {program.get('cap_hoan_thien')}, chiều cao tầng "
            f"{program.get('chieu_cao_tang')}):\n{rooms}\n"
            f"Các điều chỉnh đã làm: {'; '.join(program.get('lich_su_sua', [])[-8:]) or 'chưa có'}\n"
            + (f"Trao đổi trước đó:\n{hist}\n" if hist else ""))


def _llm_ops(text: str, program: dict, brief: dict | None = None,
             history: list[dict] | None = None) -> tuple[list[dict], str]:
    """LLM hiểu góp ý theo ngữ cảnh (brief, phương án hiện tại, lịch sử trao đổi) -> (thao tác, lời trả lời)."""
    from pydantic import BaseModel, Field

    from llm import invoke_structured, llm_enabled

    if not llm_enabled():
        return [], ""

    class Op(BaseModel):
        op: str
        phong: str | None = Field(None, description="Tên phòng đúng như trong phương án hiện tại")
        tang: int | None = None
        tang_moi: int | None = None
        loai: str | None = None
        vi_tri: str | None = Field(None, description="mặt tiền | trước | giữa | sau")
        gia_tri: float | str | None = None

    class Plan(BaseModel):
        ops: list[Op] = Field(description="Danh sách thao tác để thực hiện mong muốn của chủ nhà")
        tra_loi: str = Field(description="Trả lời chủ nhà 1–3 câu: đã/ sẽ thay đổi gì, vì sao; nếu yêu cầu không hợp lý "
                                         "(vd vượt quy chuẩn) thì giải thích và đề xuất cách khác")

    brief = brief or {"lo_dat": {"rong": "?", "dai": "?", "huong": "?", "tinh": "?"}, "gia_dinh": {"so_nguoi": "?"},
                      "yeu_cau_phong": {"phong_ngu": "?"}, "ngan_sach": 0}
    out = invoke_structured(
        "Bạn là kiến trúc sư nhà phố Việt Nam đang trao đổi với chủ nhà. Hiểu cả cách nói tự nhiên, ẩn ý "
        "(vd 'nhà hơi tối' → tăng sân sau / giếng trời; 'bố mẹ già lên xuống khó' → đưa phòng ngủ xuống tầng 1; "
        "'con sắp lớn cần chỗ học' → thêm phòng làm việc). Chuyển mong muốn thành thao tác sửa chương trình "
        "công năng. Chỉ dùng op hợp lệ, tên phòng phải khớp phương án hiện tại.\n" + OP_HELP,
        _context(program, brief, history) + f"\nChủ nhà vừa nói: “{text}”", Plan)
    if out is None:
        return [], ""
    return [o.model_dump() for o in out.ops], out.tra_loi


def apply_ops(program: dict, ops: list[dict], brief: dict) -> tuple[dict, dict, list[str]]:
    """Thực hiện các thao tác sửa. Trả về (program, brief, mô tả)."""
    program = copy.deepcopy(program)
    brief = copy.deepcopy(brief)
    yc = brief["yeu_cau_phong"]
    changes: list[str] = []
    rebuild = False
    max_floors = load_rules()["so_tang_toi_da"]["gia_tri"]
    structural = {"so_tang", "them_tang", "so_phong_ngu", "so_phong_ngu_delta", "phong_tho", "phong_lam_viec", "gara"}
    # 1) thao tác thay đổi cấu trúc -> lập lại chương trình; 2) sau đó mới chỉnh diện tích, sân, vật liệu
    ordered = [o for o in ops if o.get("op") in structural] + [{"op": "_rebuild"}] + \
              [o for o in ops if o.get("op") not in structural]
    for o in ordered:
        if o["op"] == "_rebuild":
            if rebuild:
                program = initial_program(brief, keep=program)
            continue
        op, v = o.get("op"), o.get("gia_tri")
        if op == "tiet_kiem":
            changes += _save_cost(program, {"vuot_pct": 0.1}, brief)
        elif op == "cap_hoan_thien" and v in GRADES:
            program["cap_hoan_thien"] = v
            changes.append(f"Đổi gói hoàn thiện sang '{v}'")
        elif op in ("san_sau", "san_truoc") and v is not None:
            program[op] = max(0.0, program.get(op, 0) + float(v[1:]) if isinstance(v, str) and v.startswith("+")
                              else float(v))
            changes.append(f"Đặt {'sân sau' if op == 'san_sau' else 'sân trước'} {_n(program[op])} m")
        elif op == "so_tang" and v:
            yc["so_tang"] = max(1, min(int(v), max_floors)); rebuild = True
            changes.append(f"Đổi số tầng thành {yc['so_tang']}")
        elif op == "bot_tang":
            if _drop_top_floor(program):
                changes.append(f"Giảm còn {program['so_tang']} tầng")
        elif op == "them_tang":
            yc["so_tang"] = min(program["so_tang"] + 1, max_floors); rebuild = True
            changes.append(f"Tăng lên {yc['so_tang']} tầng")
        elif op == "so_phong_ngu" and v:
            yc["phong_ngu"] = max(1, int(v)); yc["so_tang"] = None; rebuild = True
            changes.append(f"Đổi số phòng ngủ thành {yc['phong_ngu']}")
        elif op == "so_phong_ngu_delta" and v:
            yc["phong_ngu"] = max(1, yc["phong_ngu"] + int(v)); yc["so_tang"] = None; rebuild = True
            changes.append(f"Số phòng ngủ: {yc['phong_ngu']}")
        elif op in ("phong_tho", "phong_lam_viec"):
            yc[op] = int(bool(v)); yc["so_tang"] = None; rebuild = True
            changes.append(f"{'Thêm' if v else 'Bỏ'} {'phòng thờ' if op == 'phong_tho' else 'phòng làm việc'}")
        elif op == "gara":
            yc["gara"] = v or None; rebuild = True
            changes.append(f"Gara: {v or 'không'}")
        elif op in ("dien_tich", "ti_le_dien_tich") and o.get("phong"):
            k, r = _find_room(program, o["phong"], o.get("tang"))
            if r is None:
                changes.append(f"Không tìm thấy phòng “{o['phong']}”")
                continue
            r["dien_tich"] = round(float(v) if op == "dien_tich" else r["dien_tich"] * float(v), 1)
            if r.get("co_dinh") and r["loai"] == "ban_cong":
                r["chieu_sau"] = round(r["dien_tich"] / brief["lo_dat"]["rong"], 2)
            changes.append(f"{r['ten']} {k.replace('tang_', 'tầng ')}: {r['dien_tich']:g} m²")
        elif op == "chuyen_phong" and o.get("phong"):
            k, r = _find_room(program, o["phong"], o.get("tang"))
            if r is None:
                changes.append(f"Không tìm thấy phòng “{o['phong']}”")
                continue
            dest = f"tang_{o['tang_moi']}" if o.get("tang_moi") else k
            if dest not in program:
                changes.append(f"Không có {dest.replace('tang_', 'tầng ')}")
                continue
            if o.get("vi_tri") in POSITIONS:
                r["vi_tri"] = o["vi_tri"]
                r.pop("vung", None)
                if r["vi_tri"] == "giữa":
                    r["vung"] = "trước"
            if dest != k:
                program[k].remove(r)
                program[dest].insert(0, r)
            changes.append(f"Dời {r['ten']} {('tới ' + dest.replace('tang_', 'tầng ')) if dest != k else ''}"
                           f"{(' – vị trí ' + r['vi_tri']) if o.get('vi_tri') else ''}".strip())
        elif op == "doi_ten" and o.get("phong") and v:
            k, r = _find_room(program, o["phong"], o.get("tang"))
            if r is not None:
                changes.append(f"Đổi tên {r['ten']} → {v}")
                r["ten"] = str(v)
        elif op == "phong_cach" and v:
            program["phong_cach"] = str(v)
            program["vat_lieu"] = _materials(str(v))
            changes.append(f"Đổi phong cách sang {v}")
        elif op == "chieu_cao_tang" and v:
            key = "tang_1" if (o.get("tang") or 0) == 1 else "tang_khac"
            program.setdefault("chieu_cao_tang", {})[key] = round(float(v), 2)
            changes.append(f"Chiều cao {'tầng 1' if key == 'tang_1' else 'các tầng trên'}: {_n(float(v))} m")
        elif op == "xoa_phong" and o.get("phong"):
            k, r = _find_room(program, o["phong"], o.get("tang"))
            if r is not None:
                program[k].remove(r)
                changes.append(f"Bỏ {r['ten']} {k.replace('tang_', 'tầng ')}")
        elif op == "them_phong" and o.get("loai") in ROOM_TYPES:
            k = f"tang_{o.get('tang') or 1}"
            if k in program:
                room = _room(o.get("phong") or ROOM_TYPES[o["loai"]], o["loai"], float(v or 10),
                             o.get("vi_tri") if o.get("vi_tri") in POSITIONS else "trước")
                if o["loai"] in SMALL_TYPES:
                    room["nho"] = True
                program[k].insert(0, room)
                changes.append(f"Thêm {room['ten']} ở {k.replace('tang_', 'tầng ')}")
    return program, brief, changes


def _user_feedback(program: dict, text: str, brief: dict,
                   history: list[dict] | None = None) -> tuple[dict, dict, list[str], str]:
    """Hiểu góp ý tự nhiên: LLM (có ngữ cảnh) trước, bộ quy tắc dự phòng. Trả về (program, brief, thay đổi, trả lời)."""
    ops, reply = _llm_ops(text, program, brief, history)
    if not ops:
        ops, reply = _rule_ops(text), ""
    if not ops:
        msg = (f"Tôi chưa rõ ý “{text}”. Anh/chị có thể nói cụ thể hơn, ví dụ: “phòng khách 30 m2”, “thêm phòng ngủ”, "
               f"“chuyển phòng thờ lên tầng 4”, “nhà hơi tối”, “sân sau 3”, hoặc sửa trực tiếp trong bảng.")
        return program, brief, [], msg
    program, brief, changes = apply_ops(program, ops, brief)
    if not reply:
        reply = ("Đã điều chỉnh: " + "; ".join(changes) + ".") if changes else "Phương án không cần thay đổi."
    return program, brief, changes, reply


# ---------------------------------------------------------------------------
# Các phương án để chủ nhà lựa chọn
# ---------------------------------------------------------------------------
def make_options(brief: dict, base: dict) -> list[dict]:
    """3 phương án: A cân bằng, B tiết kiệm, C thoáng & cao cấp."""
    a = copy.deepcopy(base)
    b = copy.deepcopy(base)
    gi = GRADES.index(b["cap_hoan_thien"])
    b["cap_hoan_thien"] = GRADES[max(0, gi - 1)]
    b["vat_lieu"].update(san="gạch ceramic", cua_phong="gỗ công nghiệp")
    for k in _floors(b):
        for r in b[k]:
            if not r.get("co_dinh") and not r.get("nho") and r["loai"] not in ("san_phoi",):
                r["dien_tich"] = round(r["dien_tich"] * 0.88, 1)
    c = copy.deepcopy(base)
    c["cap_hoan_thien"] = GRADES[min(len(GRADES) - 1, gi + 1)]
    c["san_sau"] = round(c.get("san_sau", 0) + (2.0 if brief["lo_dat"]["dai"] >= 15 else 1.0), 2)
    for k in _floors(c):
        for r in c[k]:
            if r["loai"] in ("ngu", "khach") and "master" in r["ten"].lower() or r["loai"] == "khach":
                r["dien_tich"] = round(r["dien_tich"] * 1.15, 1)
    specs = [
        ("A", "Phương án A – Cân bằng", "Bám sát yêu cầu, công năng đầy đủ, gói hoàn thiện "
                                         f"'{a['cap_hoan_thien']}'.", a),
        ("B", "Phương án B – Tiết kiệm", f"Thu gọn diện tích phòng ~12%, gói hoàn thiện '{b['cap_hoan_thien']}' để giảm "
                                          "chi phí.", b),
        ("C", "Phương án C – Thoáng & cao cấp", f"Thêm sân sau {_n(c['san_sau'])} m lấy sáng, phòng khách/master rộng hơn, "
                                                 f"gói '{c['cap_hoan_thien']}'.", c),
    ]
    out = []
    for oid, name, desc, prog in specs:
        prog["phuong_an"] = oid
        out.append({"id": oid, "ten": name, "mo_ta": desc, "program": prog})
    return out


def identify_program(program: dict, brief: dict, run_id: str, version: int | None = None) -> dict:
    """Giữ ID phòng đã có và định danh các phòng theo vai trò khi lập lại phương án."""
    program = copy.deepcopy(program)
    program.setdefault("phuong_an", "A")
    program["option_version"] = version if version is not None else program.get("option_version", 0) + 1
    program["revision_id"] = uuid4().hex
    program["floor_ids"] = {key: key for key in _floors(program)}
    used = set()
    occurrences = Counter()
    preferred_neighbors = {
        "gara": {"khach"}, "khach": {"gara", "bep"}, "bep": {"khach", "san_phoi"},
        "ngu": {"wc"}, "lam_viec": {"sinh_hoat", "ban_cong"}, "tho": {"san_phoi", "ban_cong"},
    }
    for key in _floors(program):
        for room in program[key]:
            role = (room["loai"], room["ten"].strip().casefold())
            occurrences[role] += 1
            old_id = room.get("id")
            stable = uuid5(NAMESPACE_URL, f"{run_id}/{role}/{occurrences[role]}").hex
            room["id"] = old_id if old_id and old_id not in used else stable
            if room["id"] in used:
                room["id"] = uuid5(NAMESPACE_URL, f"{stable}/{key}").hex
            used.add(room["id"])
            room["toi_thieu"] = dict(min_room(room["loai"], brief["yeu_cau_phong"].get("gara")) or {})
            room["ke_khong_gian"] = ["giếng trời hoặc mặt thoáng"] if room["loai"] in (
                "ngu", "khach", "bep", "lam_viec", "sinh_hoat", "tho") else []
        for room in program[key]:
            types = preferred_neighbors.get(room["loai"], ())
            room["ke_phong_uu_tien"] = [other["id"] for other in program[key] if other["loai"] in types]
    return program


def version_option(program: dict, brief: dict, run_id: str, versions: dict) -> dict:
    oid = program.get("phuong_an", "A")
    versions[oid] = max(versions.get(oid, 0), program.get("option_version", 0)) + 1
    return identify_program(program, brief, run_id, versions[oid])


def candidate_with_program(options: list[dict], program: dict) -> dict:
    oid = program["phuong_an"]
    existing = next((opt for opt in options if opt["id"] == oid), {})
    return {"id": oid, "ten": existing.get("ten", f"Phương án {oid}"),
            "mo_ta": existing.get("mo_ta", "Phương án đã điều chỉnh theo phản hồi."),
            "program": program}


@agent_node("architect")
def run(state: dict) -> dict:
    brief = state["brief"]
    feedback = state.get("feedback") or []
    program = state.get("program")
    options = [option for option in state.get("options") or [] if "option_version" in option["program"]]
    versions = dict(state.get("option_versions") or {})
    new_selection = not program
    reply = None
    if new_selection:
        options = make_options(brief, initial_program(brief, concept=state.get("concept_plan")))
        options = [{**opt, "program": version_option(opt["program"], brief, state["run_id"], versions)}
                   for opt in options]
        program = options[0]["program"]
        new_brief = None
        changes = []
    else:
        oid = program.get("phuong_an", "A")
        program, changes = apply_feedback(program, feedback, brief)
        program["phuong_an"] = oid
        new_brief = program.pop("_brief", None)
        reply = program.pop("_reply", None)
        brief_changed = new_brief is not None and new_brief != brief
        if brief_changed:
            brief = new_brief
        program = version_option(program, brief, state["run_id"], versions)
        candidate = candidate_with_program(options, program)
        if brief_changed:
            options = [candidate]
        else:
            options = [candidate if opt["id"] == oid else opt for opt in options]
            if not any(opt["id"] == oid for opt in options):
                options.append(candidate)
    concept = dict(state.get("concept_plan") or {})
    concept.update(so_tang=program["so_tang"], phong_cach=program["phong_cach"], vat_lieu=program["vat_lieu"])
    n_rooms = sum(1 for k in _floors(program) for r in program[k] if not r.get("co_dinh") or r["loai"] == "ban_cong")
    if changes:
        summary = f"Sửa phương án (v{(state.get('versions') or {}).get('architect', 0) + 1}): " + "; ".join(changes)
    elif reply:
        summary = f"Trả lời chủ nhà: {reply['kien_truc_su']}"
    elif new_selection:
        summary = f"Lập {len(options)} phương án công năng để đối chiếu hình học và dự toán"
    else:
        summary = f"Cập nhật công năng {program['so_tang']} tầng, {n_rooms} phòng theo định hướng mới"
    extra = {}
    if new_brief is not None:
        from agents.requirements_analyst import needs_confirmation

        extra.update(brief=brief, brief_assessment={"questions": [], "conflicts": [],
                                                   "needs_confirmation": needs_confirmation(brief)})
    if reply:
        extra["trao_doi"] = [reply]
    return {**extra, "program": program, "revision_id": program["revision_id"], "concept_plan": concept, "feedback": [],
            "options": options, "option_versions": versions,
            "selected_by_user": (not new_selection and (bool(state.get("selected_by_user")) or bool(reply))),
            "_summary": summary, "_to": "cost_estimator",
            "route": "compare_options",
            "_output": {"so_tang": program["so_tang"], "san_sau": program["san_sau"],
                        "cap_hoan_thien": program["cap_hoan_thien"], "thay_doi": changes,
                        "phuong_an": [{k: v for k, v in o.items() if k != "program"} for o in options],
                        "phong": {k: [f"{r['ten']} ({r['dien_tich']} m²)" for r in program[k] if r['loai'] not in
                                      ('thang', 'gieng_troi')] for k in _floors(program)}}}
