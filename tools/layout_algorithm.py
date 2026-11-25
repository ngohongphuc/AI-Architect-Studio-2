"""Thuật toán bố trí mặt bằng nhà ống (phiên bản cơ bản theo kế hoạch).

Hệ tọa độ (m): gốc ở góc trước-trái lô đất, trục x theo chiều ngang mặt tiền,
trục y theo chiều sâu (y = 0 là chỉ giới mặt tiền).

Ý tưởng:
1. Vùng xây dựng = lô đất trừ sân trước / sân sau.
2. Lõi giao thông (giếng trời | cầu thang | sảnh thang) cố định, thẳng hàng mọi tầng.
3. Chia phần còn lại thành vùng trước lõi và vùng sau lõi (cùng một vị trí lõi cho mọi tầng).
4. Mỗi phòng chiếm một dải theo chiều sâu; phòng nhỏ (WC, kho) chia chung dải với hành lang.
5. Chiều sâu các dải được co giãn tỉ lệ nhưng không nhỏ hơn kích thước tối thiểu.
"""
from __future__ import annotations

import math

from tools.rules import load_rules, min_room

OPEN_TYPES = {"ban_cong", "san_phoi", "san", "gieng_troi"}       # không phải sàn kín
CIRCULATION = {"hanh_lang", "thang"}
FRONT_ORDER = {"mặt tiền": 0, "trước": 1, "nho": 2, "giữa": 3}
BACK_ORDER = {"nho": 0, "giữa": 1, "sau": 2}
EPS = 1e-6


class LayoutError(Exception):
    pass


def r2(v: float) -> float:
    return round(v + 0.0, 3)


# ---------------------------------------------------------------------------
# Cầu thang
# ---------------------------------------------------------------------------
def design_stair(heights: list[float], stair_w: float, *, tune: bool = False) -> dict:
    rules = load_rules()["cau_thang"]
    gap = 0.1
    flight_w = round((stair_w - gap) / 2, 3)
    per_floor = []
    max_run = 0.0
    for h in heights:
        tread = 0.26
        n = math.ceil(h / 0.175 - 1e-9)
        if tune:
            # Dùng cùng ngưỡng với phép kiểm. Tìm bậc gần cấu hình gốc nhất có thể bố trí.
            candidates = []
            for count in range(max(2, math.ceil(h / rules["bac_cao_max"] - EPS)), 2 * rules["so_bac_ve_max"] + 1):
                rise = h / count
                low = max(rules["bac_rong_min"], rules["blondel_min"] - 2 * rise)
                high = rules["blondel_max"] - 2 * rise
                lower_mm, upper_mm = math.ceil(low * 1000 - EPS), math.floor(high * 1000 + EPS)
                if lower_mm <= upper_mm:
                    depth = min(max(round(tread * 1000), lower_mm), upper_mm) / 1000
                    candidates.append((abs(count - n), abs(depth - tread), count, depth))
            if not candidates:
                raise LayoutError("Không bố trí được số bậc và mặt bậc thỏa các ngưỡng cầu thang đang đối chiếu")
            _, _, n, tread = min(candidates)
        riser = h / n
        ra = math.ceil(n / 2)
        rb = n - ra
        run = (ra - 1) * tread
        max_run = max(max_run, run)
        per_floor.append({"chieu_cao_tang": h, "so_bac": n, "bac_cao": round(riser, 4), "bac_rong": tread,
                          "bac_ve_1": ra, "bac_ve_2": rb, "blondel": round(2 * riser + tread, 3)})
    landing = max(flight_w, rules["be_rong_ve_min"])
    length = math.ceil((max_run + 2 * landing) * 10 - 1e-9) / 10
    return {"rong": stair_w, "ve_rong": flight_w, "khe": gap, "chieu_nghi": landing,
            "chieu_dai": round(length, 2), "cac_tang": per_floor}


# ---------------------------------------------------------------------------
# Chia chiều sâu các dải
# ---------------------------------------------------------------------------
def _min_depth(spec: dict, width: float, gara: str | None) -> float:
    if spec.get("co_dinh"):
        return spec["chieu_sau"]
    loai = spec["loai"]
    if loai in ("ban_cong", "san_phoi", "san"):
        return 1.0
    m = min_room(loai, gara)
    if not m:
        return 1.0
    d = max(m.get("canh", 0), m.get("dien_tich", 0) / width, m.get("chieu_dai", 0))
    return d


# Hệ số giãn tối đa so với diện tích mong muốn (None = không giới hạn)
MAX_FACTOR = {"wc": 1.25, "kho": 1.3, "tho": 1.6, "gara": 1.5, "hanh_lang": 1.5, "ngu": 1.8, "khach": 1.6,
              "bep": 1.6, "sinh_hoat": 1.8, "lam_viec": 1.8}


def allocate(specs: list[dict], total: float, widths: list[float], gara: str | None,
             absorb: bool = True) -> tuple[list[float], bool]:
    """Chia `total` mét chiều sâu cho các dải. Trả về (độ sâu, khả thi).

    Mỗi dải linh hoạt có độ sâu = clamp(scale × mong muốn, tối thiểu, tối đa); tìm `scale` bằng chia đôi
    sao cho tổng đúng bằng `total`.
    """
    if not specs:
        return [], total <= EPS
    desired, mins, maxs, fixed = [], [], [], []
    for s, w in zip(specs, widths):
        if s.get("co_dinh"):
            desired.append(s["chieu_sau"]); mins.append(s["chieu_sau"]); maxs.append(s["chieu_sau"])
            fixed.append(True)
            continue
        d = max(s["dien_tich"] / w, 0.5)
        mn = _min_depth(s, w, gara)
        fac = MAX_FACTOR.get(s["loai"])
        desired.append(d); mins.append(mn); maxs.append(max(mn, d * fac) if fac else float("inf"))
        fixed.append(False)
    flex = [i for i, f in enumerate(fixed) if not f]
    fixed_sum = sum(d for d, f in zip(desired, fixed) if f)
    remaining = total - fixed_sum
    if not flex:
        return desired, abs(remaining) < 0.05

    def f(scale: float) -> float:
        return sum(min(maxs[i], max(mins[i], desired[i] * scale)) for i in flex)

    if f(0) > remaining + EPS:
        depths = list(desired)
        for i in flex:
            depths[i] = mins[i]
        return depths, False
    lo, hi = 0.0, 1.0
    while f(hi) < remaining and hi < 1e6:
        hi *= 2
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid) < remaining:
            lo = mid
        else:
            hi = mid
    depths = list(desired)
    for i in flex:
        depths[i] = min(maxs[i], max(mins[i], desired[i] * hi))
    # làm tròn 0,05 m; dải không bị giới hạn lớn nhất nhận phần dư
    for i in flex:
        depths[i] = round(depths[i] * 20) / 20
    free = [i for i in flex if maxs[i] == float("inf")]
    if not free and not absorb and total - sum(depths) > 0.3:
        return depths, True  # còn dư, để hàm gọi chèn dải phụ
    free = free or flex
    biggest = max(free, key=lambda i: depths[i])
    depths[biggest] = round(depths[biggest] + total - sum(depths), 3)
    return depths, True


# ---------------------------------------------------------------------------
# Bố trí
# ---------------------------------------------------------------------------
def floor_keys(program: dict) -> list[str]:
    return sorted((k for k in program if k.startswith("tang_")), key=lambda k: int(k.split("_")[1]))


def _floor_heights(program: dict) -> list[float]:
    h = program.get("chieu_cao_tang", {})
    keys = floor_keys(program)
    return [h.get(k, h.get("tang_1", 3.6) if k == "tang_1" else h.get("tang_khac", 3.3)) for k in keys]


def _split_zones(rooms: list[dict]) -> tuple[list[dict], list[dict]]:
    front, back = [], []
    for r in rooms:
        if r["loai"] in ("thang", "gieng_troi"):
            continue
        vt = r.get("vi_tri", "trước")
        key = "nho" if r.get("nho") else vt
        if vt == "sau" or r.get("vung") == "sau":
            # phòng nhỏ có vi_tri "sau" nằm đầu vùng sau (sát lõi)
            back.append((BACK_ORDER.get(key, 2), r))
        else:
            front.append((FRONT_ORDER.get(key, 1), r))
    front.sort(key=lambda t: t[0])
    back.sort(key=lambda t: t[0])
    return [r for _, r in front], [r for _, r in back]


def compute_layout(brief: dict, program: dict) -> dict:
    lot_w = float(brief["lo_dat"]["rong"])
    lot_l = float(brief["lo_dat"]["dai"])
    gara = brief["yeu_cau_phong"].get("gara")
    sf = float(program.get("san_truoc", 0))
    sb = float(program.get("san_sau", 0))
    W = lot_w
    if lot_w <= 1.9:
        raise LayoutError("Mặt tiền quá hẹp cho lõi thang và lối đi của mẫu nhà ống hiện tại")
    L = round(lot_l - sf - sb, 3)
    y0, y1 = sf, sf + L
    if L < 8:
        raise LayoutError(f"Chiều sâu xây dựng {L} m quá ngắn")

    stair_w = 2.2 if W >= 4.5 else (2.0 if W >= 3.8 else 1.9)
    tune_stair = bool(program.get("doi_chieu_cau_thang"))
    if tune_stair:
        stair_w = max(stair_w, r2(2 * load_rules()["cau_thang"]["be_rong_ve_min"] + .1))
        if stair_w >= W:
            raise LayoutError("Không đủ bề ngang cho vế thang và lối đi theo ngưỡng đang đối chiếu")
    hall_w = 1.1 if W >= 4.5 else 1.0
    sky_w = round(W - stair_w - hall_w, 3)
    if sky_w < 0.8:
        hall_w = round(W - stair_w, 3)
        sky_w = 0.0
    small_w = round(W - hall_w, 3)

    heights = _floor_heights(program)
    stair = design_stair(heights, stair_w, tune=tune_stair)
    core_len = stair["chieu_dai"]
    avail = L - core_len
    keys = floor_keys(program)

    zones = {}
    front_min_max = back_min_max = 0.0
    ratios = []
    for k in keys:
        front, back = _split_zones(program[k])
        zones[k] = (front, back)

        def need(lst, mins=False):
            tot = 0.0
            for s in lst:
                w = small_w if s.get("nho") else W
                if s.get("co_dinh"):
                    tot += s["chieu_sau"]
                else:
                    tot += _min_depth(s, w, gara) if mins else s["dien_tich"] / w
            return tot

        fd, bd = need(front), need(back)
        front_min_max = max(front_min_max, need(front, True))
        back_min_max = max(back_min_max, need(back, True))
        if fd + bd > 0:
            ratios.append(fd / (fd + bd))
    ratio = sum(ratios) / len(ratios) if ratios else 0.6
    F = round(avail * ratio * 10) / 10
    lo_f, hi_f = front_min_max, avail - back_min_max
    warnings = []
    feasible = lo_f <= hi_f + EPS
    F = min(max(F, lo_f), hi_f) if feasible else lo_f
    F = round(F, 2)
    B = round(avail - F, 3)
    core_y = round(y0 + F, 3)

    floors = {}
    for idx, k in enumerate(keys, start=1):
        front, back = zones[k]
        rooms: list[dict] = []
        strips: list[dict] = []
        generated = {}

        def add_room(name, loai, x, y, w, h, spec=None):
            role = (loai, name)
            generated[role] = generated.get(role, 0) + 1
            room_id = (spec or {}).get("id") or f"T{idx}/{loai}/{name}/{generated[role]}"
            room = {"id": room_id, "ten": name, "loai": loai, "tang": idx,
                    "x": r2(x), "y": r2(y), "w": r2(w), "h": r2(h), "dien_tich": round(w * h, 2)}
            if spec and spec.get("ghi_chu"):
                room["ghi_chu"] = spec["ghi_chu"]
            rooms.append(room)
            return room["id"]

        def place_zone(specs, start, length, zone):
            specs = list(specs)
            widths = [small_w if s.get("nho") else W for s in specs]
            if specs:
                trial, _ = allocate(specs, length, widths, gara, absorb=False)
                left = length - sum(trial)
                if left > 1.2:
                    filler = None
                    if zone == "front" and idx > 1:
                        filler = {"ten": "Phòng thay đồ", "loai": "kho", "nho": True, "dien_tich": 0,
                                  "co_dinh": True, "chieu_sau": round(min(left, 3.0), 2)}
                        pos = next((i for i, s in enumerate(specs) if s.get("nho")), len(specs))
                        specs.insert(pos, filler)
                    elif zone == "back":
                        filler = ({"ten": "Lô gia sau", "loai": "ban_cong"} if idx > 1 else
                                  {"ten": "Sân trong sau", "loai": "san"})
                        filler.update({"dien_tich": 0, "co_dinh": True, "chieu_sau": round(min(left, 2.5), 2)})
                        specs.append(filler)
                    widths = [small_w if s.get("nho") else W for s in specs]
            if not specs:
                if length > 0.05:
                    name, loai = ("Sân trong", "san") if idx == 1 and zone == "back" else ("Sân phơi", "san_phoi")
                    rid = add_room(name, loai, 0, start, W, length)
                    strips.append({"y": r2(start), "d": r2(length), "kind": "full", "rooms": [rid], "zone": zone})
                return True
            depths, ok = allocate(specs, length, widths, gara)
            y = start
            for s, d in zip(specs, depths):
                if s.get("nho"):
                    a = add_room(s["ten"], s["loai"], 0, y, small_w, d, s)
                    b = add_room("Hành lang", "hanh_lang", small_w, y, hall_w, d)
                    strips.append({"y": r2(y), "d": r2(d), "kind": "small", "rooms": [a, b], "zone": zone})
                else:
                    a = add_room(s["ten"], s["loai"], 0, y, W, d, s)
                    strips.append({"y": r2(y), "d": r2(d), "kind": "full", "rooms": [a], "zone": zone})
                y += d
            return ok

        ok_f = place_zone(front, y0, F, "front")
        # Lõi
        core_specs = {room["loai"]: room for room in program[k] if room["loai"] in ("gieng_troi", "thang")}
        core_ids = []
        if sky_w > 0:
            core_ids.append(add_room("Sân trong" if idx == 1 else "Giếng trời", "gieng_troi", 0, core_y, sky_w, core_len,
                                     core_specs.get("gieng_troi")))
        core_ids.append(add_room("Cầu thang", "thang", sky_w, core_y, stair_w, core_len, core_specs.get("thang")))
        core_ids.append(add_room("Sảnh thang", "hanh_lang", sky_w + stair_w, core_y, hall_w, core_len))
        strips.append({"y": core_y, "d": core_len, "kind": "core", "rooms": core_ids, "zone": "core"})
        ok_b = place_zone(back, core_y + core_len, B, "back")
        if not (ok_f and ok_b):
            feasible = False
        # Sân trước / sau (tầng 1)
        if idx == 1:
            if sf > 0:
                add_room(program.get("ten_san_truoc", "Sân trước"), "san", 0, 0, W, sf)
            if sb > 0:
                add_room("Sân sau", "san", 0, y1, W, sb)
        floors[str(idx)] = {"id": f"tang_{idx}", "rooms": rooms, "strips": sorted(strips, key=lambda s: s["y"])}

    if not feasible:
        warnings.append("Không đủ chiều sâu để bố trí các phòng với kích thước tối thiểu")

    layout = {
        "lot": {"w": lot_w, "l": lot_l},
        "building": {"x": 0.0, "y": y0, "w": W, "l": L},
        "san_truoc": sf, "san_sau": sb,
        "core": {"y": core_y, "l": core_len, "sky_w": sky_w, "stair_w": stair_w, "hall_w": hall_w,
                 "stair_x": sky_w},
        "stair": stair,
        "heights": heights,
        "so_tang": len(keys),
        "floors": floors,
        "feasible": feasible,
        "warnings": warnings,
    }
    for k, fl in floors.items():
        fl["doors"], fl["windows"] = make_openings(layout, int(k))
    return layout


# ---------------------------------------------------------------------------
# Cửa đi, cửa sổ
# ---------------------------------------------------------------------------
def room_at(rooms: list[dict], x: float, y: float) -> dict | None:
    for r in rooms:
        if r["x"] + EPS < x < r["x"] + r["w"] - EPS and r["y"] + EPS < y < r["y"] + r["h"] - EPS:
            return r
    return None


DOOR_SIZE = {"di": (0.9, 2.2), "wc": (0.7, 2.2), "di_nhom": (0.9, 2.2), "kinh": (2.4, 2.4),
             "chinh": (1.6, 2.6), "cuon": (None, 3.0)}


def make_openings(layout: dict, floor: int) -> tuple[list[dict], list[dict]]:
    fl = layout["floors"][str(floor)]
    rooms = fl["rooms"]
    W = layout["building"]["w"]
    y_front = layout["building"]["y"]
    y_back = y_front + layout["building"]["l"]
    core = layout["core"]
    lane = W - core["hall_w"] / 2
    strips = [s for s in fl["strips"]]
    doors, windows = [], []

    def enclosed(r):
        return r is not None and r["loai"] not in OPEN_TYPES

    # Cửa giữa các dải liên tiếp
    for a, b in zip(strips, strips[1:]):
        yb = r2(a["y"] + a["d"])
        ra, rb = room_at(rooms, lane, yb - 0.01), room_at(rooms, lane, yb + 0.01)
        if ra is None or rb is None:
            continue
        types = {ra["loai"], rb["loai"]}
        if types <= CIRCULATION:
            continue
        if "ban_cong" in types:
            w = min(2.4, W - 1.6)
            doors.append({"orient": "h", "c": yb, "a": r2(W / 2 - w / 2), "b": r2(W / 2 + w / 2),
                          "loai": "kinh", "rooms": [ra["id"], rb["id"]], "swing": 0})
            continue
        kind = "wc" if "wc" in types else ("di_nhom" if types & {"san_phoi", "san", "gieng_troi"} else "di")
        w = DOOR_SIZE[kind][0]
        w = min(w, core["hall_w"] - 0.15) if kind != "di_nhom" else min(w, core["hall_w"] - 0.1)
        into = rb if rb["loai"] not in CIRCULATION | OPEN_TYPES else ra
        swing = 1 if into is rb else -1
        doors.append({"orient": "h", "c": yb, "a": r2(lane - w / 2), "b": r2(lane + w / 2), "loai": kind,
                      "rooms": [ra["id"], rb["id"]], "swing": swing})

    # Cửa phòng nhỏ mở ra hành lang
    for s in strips:
        if s["kind"] != "small":
            continue
        room = next(r for r in rooms if r["id"] == s["rooms"][0])
        w = min(0.7 if room["loai"] == "wc" else 0.8, s["d"] - 0.3)
        yc = s["y"] + s["d"] / 2
        doors.append({"orient": "v", "c": r2(W - core["hall_w"]), "a": r2(yc - w / 2), "b": r2(yc + w / 2),
                      "loai": "wc" if room["loai"] == "wc" else "di", "rooms": [room["id"]], "swing": -1})

    first = room_at(rooms, W / 2, y_front + 0.05)
    last = room_at(rooms, W / 2, y_back - 0.05)
    # Mặt tiền
    if floor == 1 and first is not None:
        if first["loai"] == "gara":
            doors.append({"orient": "h", "c": y_front, "a": 0.3, "b": r2(W - 0.3), "loai": "cuon",
                          "rooms": [first["id"]], "swing": 0})
        else:
            w = min(1.6, W - 1.2)
            doors.append({"orient": "h", "c": y_front, "a": r2(W / 2 - w / 2), "b": r2(W / 2 + w / 2),
                          "loai": "chinh", "rooms": [first["id"]], "swing": 1})
    elif enclosed(first):
        w = min(2.0, W - 1.6)
        windows.append({"orient": "h", "c": y_front, "a": r2(W / 2 - w / 2), "b": r2(W / 2 + w / 2),
                        "rooms": [first["id"]]})
    # Mặt sau
    if enclosed(last) and layout["san_sau"] > 0:
        if floor == 1:
            doors.append({"orient": "h", "c": r2(y_back), "a": r2(lane - 0.45), "b": r2(lane + 0.45),
                          "loai": "di_nhom", "rooms": [last["id"]], "swing": -1})
            windows.append({"orient": "h", "c": r2(y_back), "a": 0.6, "b": 2.0, "rooms": [last["id"]]})
        else:
            windows.append({"orient": "h", "c": r2(y_back), "a": r2(W / 2 - 0.7), "b": r2(W / 2 + 0.7),
                            "rooms": [last["id"]]})
    # Cửa sổ ra sân phơi
    for r in rooms:
        if r["loai"] != "san_phoi":
            continue
        prev = room_at(rooms, (W - core["hall_w"]) / 2, r["y"] - 0.01)
        if enclosed(prev) and prev["loai"] not in CIRCULATION:
            windows.append({"orient": "h", "c": r["y"], "a": 0.5, "b": r2(min(1.7, W - core["hall_w"] - 0.4)),
                            "rooms": [prev["id"]]})
    # Cửa sổ lấy sáng giếng trời
    if core["sky_w"] >= 0.8:
        xc = core["sky_w"] / 2
        w = min(1.2, core["sky_w"] - 0.3)
        for yb, dy in ((core["y"], -0.01), (core["y"] + core["l"], 0.01)):
            r = room_at(rooms, xc, yb + dy)
            if enclosed(r) and r["loai"] not in CIRCULATION:
                windows.append({"orient": "h", "c": r2(yb), "a": r2(xc - w / 2), "b": r2(xc + w / 2),
                                "rooms": [r["id"]]})
    return doors, windows


# ---------------------------------------------------------------------------
# Thống kê diện tích (nguồn số liệu chung cho Agent 1, 4, 5)
# ---------------------------------------------------------------------------
def build_area_table(layout: dict, brief: dict) -> dict:
    lot_area = round(layout["lot"]["w"] * layout["lot"]["l"], 2)
    footprint = round(layout["building"]["w"] * layout["building"]["l"], 2)
    floors_out = []
    tong_san = tong_bc = tong_sp = tong_gt = 0.0
    counts: dict[str, int] = {}
    top = str(layout["so_tang"])
    for k in sorted(layout["floors"], key=int):
        fl = layout["floors"][k]
        san = bc = sp = gt = 0.0
        phong = []
        for r in fl["rooms"]:
            if r["loai"] == "san":
                if "đỗ xe" in r["ten"]:
                    counts["gara"] = counts.get("gara", 0) + 1
                continue
            phong.append({"id": r["id"], "ten": r["ten"], "loai": r["loai"], "dien_tich": r["dien_tich"],
                          "kich_thuoc": f"{r['w']:.2f} × {r['h']:.2f}"})
            if r["loai"] == "ban_cong":
                bc += r["dien_tich"]
            elif r["loai"] == "san_phoi":
                sp += r["dien_tich"]
            elif r["loai"] == "gieng_troi":
                gt += r["dien_tich"]
            else:
                san += r["dien_tich"]
            if r["loai"] in ("ngu", "tho", "wc", "gara", "khach", "bep", "lam_viec", "sinh_hoat"):
                counts[r["loai"]] = counts.get(r["loai"], 0) + 1
        floors_out.append({"id": f"tang_{k}", "tang": int(k), "ten": f"Tầng {k}", "phong": phong,
                           "dien_tich_san": round(san, 2), "ban_cong": round(bc, 2),
                           "san_phoi": round(sp, 2), "gieng_troi": round(gt, 2)})
        tong_san += san; tong_bc += bc; tong_sp += sp; tong_gt += gt
    top_fl = floors_out[-1]
    roof = round(footprint - top_fl["san_phoi"], 2)
    heights = layout["heights"]
    return {
        "dien_tich_dat": lot_area,
        "dien_tich_xay_dung": footprint,
        "mat_do_xay_dung": round(footprint / lot_area, 4),
        "so_tang": layout["so_tang"],
        "chieu_cao_tang": heights,
        "chieu_cao_cong_trinh": round(sum(heights) + 1.0, 2),
        "tang": floors_out,
        "tong_dien_tich_san": round(tong_san, 2),
        "tong_ban_cong": round(tong_bc, 2),
        "tong_san_phoi": round(tong_sp, 2),
        "tong_gieng_troi": round(tong_gt, 2),
        "san_truoc": round(layout["san_truoc"] * layout["lot"]["w"], 2),
        "san_sau": round(layout["san_sau"] * layout["lot"]["w"], 2),
        "dien_tich_mai": roof,
        "so_phong": counts,
        "tang_tren_cung": int(top),
    }
