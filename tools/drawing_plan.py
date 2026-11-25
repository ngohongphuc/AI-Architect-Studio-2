"""Vẽ mặt bằng tổng thể (KT-01), mặt bằng các tầng (KT-02…) và mặt bằng mái."""
from __future__ import annotations

import math

from tools.layout_algorithm import CIRCULATION, EPS, OPEN_TYPES, room_at
from tools.sheet import Sheet

EXT_T, INT_T = 0.22, 0.11
NO_WALL = [{"hanh_lang"}, {"hanh_lang", "thang"}, {"thang"}]
RAIL_PAIRS = [{"hanh_lang", "gieng_troi"}, {"thang", "gieng_troi"}]


def fmt_area(a: float) -> str:
    return f"{a:.1f}".replace(".", ",") + " m²"


def fmt_mm(v_m: float) -> str:
    return f"{round(v_m * 1000):d}"


class Plan:
    """Phép xoay mặt bằng: mặt tiền ở bên trái giấy. (x, y) nhà -> (y, W - x) bản vẽ."""

    def __init__(self, W: float):
        self.W = W

    def T(self, x, y):
        return (y, self.W - x)

    def Ts(self, pts):
        return [self.T(*p) for p in pts]


# ---------------------------------------------------------------------------
# Tường
# ---------------------------------------------------------------------------
def wall_segments(rooms: list[dict], openings: list[dict]) -> list[dict]:
    xs = sorted({round(v, 3) for r in rooms for v in (r["x"], r["x"] + r["w"])})
    ys = sorted({round(v, 3) for r in rooms for v in (r["y"], r["y"] + r["h"])})
    building_types = [r for r in rooms if r["loai"] != "san"]

    def classify(a, b, orient):
        if a is b or (a is None and b is None):
            return None
        ta = a["loai"] if a else None
        tb = b["loai"] if b else None
        if a and b and {ta, tb} in NO_WALL:
            return None
        if a and b and {ta, tb} in RAIL_PAIRS:
            return "lan_can"
        if a is None or b is None:
            other = a or b
            if other["loai"] == "san":
                return "rao" if orient == "h" else "ngoai"
            if other["loai"] in ("ban_cong", "san_phoi") and orient == "h":
                return "lan_can"
            return "ngoai"
        if "san" in (ta, tb):
            other = b if ta == "san" else a
            return "lan_can" if other["loai"] in OPEN_TYPES else "ngoai"
        if {ta, tb} <= OPEN_TYPES:
            return "lan_can"
        if (ta in OPEN_TYPES) != (tb in OPEN_TYPES):
            return "ngoai"
        return "trong"

    segs = []
    for y in ys:
        for x1, x2 in zip(xs, xs[1:]):
            mid = (x1 + x2) / 2
            typ = classify(room_at(rooms, mid, y - 0.01), room_at(rooms, mid, y + 0.01), "h")
            if typ:
                segs.append(["h", y, x1, x2, typ])
    for x in xs:
        for y1, y2 in zip(ys, ys[1:]):
            mid = (y1 + y2) / 2
            typ = classify(room_at(rooms, x - 0.01, mid), room_at(rooms, x + 0.01, mid), "v")
            if typ:
                segs.append(["v", x, y1, y2, typ])
    # trừ lỗ cửa
    out = []
    for o, c, a, b, typ in segs:
        parts = [(a, b)]
        for op in openings:
            if op["orient"] != o or abs(op["c"] - c) > 1e-3 or typ in ("lan_can", "rao"):
                continue
            nxt = []
            for p, q in parts:
                if op["b"] <= p + EPS or op["a"] >= q - EPS:
                    nxt.append((p, q)); continue
                if op["a"] > p:
                    nxt.append((p, op["a"]))
                if op["b"] < q:
                    nxt.append((op["b"], q))
            parts = nxt
        out += [[o, c, p, q, typ] for p, q in parts if q - p > 1e-3]
    # gộp đoạn thẳng hàng cùng loại
    out.sort(key=lambda s: (s[0], s[1], s[4], s[2]))
    merged = []
    for s in out:
        if merged and merged[-1][0] == s[0] and abs(merged[-1][1] - s[1]) < 1e-6 and merged[-1][4] == s[4] \
                and abs(merged[-1][3] - s[2]) < 1e-6:
            merged[-1][3] = s[3]
        else:
            merged.append(list(s))
    _ = building_types
    return [{"orient": o, "c": c, "a": a, "b": b, "type": t} for o, c, a, b, t in merged]


def draw_walls(sheet: Sheet, P: Plan, segs: list[dict]) -> None:
    for s in segs:
        if s["orient"] == "h":
            a, b = (s["a"], s["c"]), (s["b"], s["c"])
        else:
            a, b = (s["c"], s["a"]), (s["c"], s["b"])
        if s["type"] in ("ngoai", "trong"):
            t = EXT_T if s["type"] == "ngoai" else INT_T
            # kéo dài nửa bề dày để góc tường kín
            ext = t / 2
            if s["orient"] == "h":
                a, b = (a[0] - ext, a[1]), (b[0] + ext, b[1])
            else:
                a, b = (a[0], a[1] - ext), (b[0], b[1] + ext)
            sheet.pline([P.T(*a), P.T(*b)], "TUONG", width=t)
        elif s["type"] == "lan_can":
            for off in (-0.03, 0.03):
                if s["orient"] == "h":
                    sheet.line(P.T(a[0], a[1] + off), P.T(b[0], b[1] + off), "LAN_CAN")
                else:
                    sheet.line(P.T(a[0] + off, a[1]), P.T(b[0] + off, b[1]), "LAN_CAN")
        elif s["type"] == "rao":
            sheet.line(P.T(*a), P.T(*b), "RANH_GIOI", ls="dashdot")


def wall_type_at(segs, orient, c, pos):
    for s in segs:
        if s["orient"] == orient and abs(s["c"] - c) < 1e-3 and s["a"] - 0.3 <= pos <= s["b"] + 0.3:
            return s["type"]
    return "trong"


# ---------------------------------------------------------------------------
# Cửa
# ---------------------------------------------------------------------------
def draw_door(sheet: Sheet, P: Plan, d: dict, thick: float) -> None:
    a, b, c = d["a"], d["b"], d["c"]
    w = b - a
    kind = d["loai"]

    def pt(u, v):  # u dọc theo tường, v vuông góc
        return P.T(u, c + v) if d["orient"] == "h" else P.T(c + v, u)

    # vạch má cửa
    for u in (a, b):
        sheet.line(pt(u, -thick / 2), pt(u, thick / 2), "CUA")
    if kind == "cuon":
        sheet.line(pt(a, 0.15), pt(b, 0.15), "CUA", ls="dashed")
        sheet.line(pt(a, 0), pt(b, 0), "CUA")
        sheet.text(P.T((a + b) / 2, c - sheet.m(4)) if d["orient"] == "h" else P.T(c - sheet.m(4), (a + b) / 2),
                   "CỬA CUỐN", "CUA", h=1.8, rot=90)
        return
    if kind == "kinh":
        half = w / 2
        sheet.line(pt(a, -0.02), pt(a + half + 0.05, -0.02), "CUA")
        sheet.line(pt(b - half - 0.05, 0.03), pt(b, 0.03), "CUA")
        return
    sw = d.get("swing", 1) or 1
    if kind == "chinh":
        # cửa 2 cánh
        for hinge, sign in ((a, 1), (b, -1)):
            leaf = w / 2
            pts = [pt(hinge + sign * leaf * math.cos(math.radians(t)), sw * leaf * math.sin(math.radians(t)))
                   for t in range(0, 91, 6)]
            sheet.pline(pts, "CUA", ls="dashed" if False else "solid")
            sheet.line(pt(hinge, 0), pt(hinge, sw * leaf), "CUA")
        return
    pts = [pt(a + w * math.cos(math.radians(t)), sw * w * math.sin(math.radians(t))) for t in range(0, 91, 6)]
    sheet.pline(pts, "CUA")
    sheet.line(pt(a, 0), pt(a, sw * w), "CUA")


def draw_window(sheet: Sheet, P: Plan, wdw: dict, thick: float) -> None:
    a, b, c = wdw["a"], wdw["b"], wdw["c"]

    def pt(u, v):
        return P.T(u, c + v) if wdw["orient"] == "h" else P.T(c + v, u)

    for v in (-thick / 2, 0, thick / 2):
        sheet.line(pt(a, v), pt(b, v), "CUA_SO")
    for u in (a, b):
        sheet.line(pt(u, -thick / 2), pt(u, thick / 2), "CUA_SO")


# ---------------------------------------------------------------------------
# Cầu thang, giếng trời, thiết bị
# ---------------------------------------------------------------------------
def draw_stair(sheet: Sheet, P: Plan, layout: dict, floor: int) -> None:
    core, st = layout["core"], layout["stair"]
    x0, y0 = core["stair_x"], core["y"]
    sw, fw, landing = st["rong"], st["ve_rong"], st["chieu_nghi"]
    info = st["cac_tang"][min(floor, len(st["cac_tang"])) - 1]
    top = floor == layout["so_tang"]
    tread = info["bac_rong"]
    ys = y0 + landing
    # vế 1 (sát sảnh, phía phải), vế 2 (phía giếng trời)
    xa0, xa1 = x0 + sw - fw, x0 + sw
    xb0, xb1 = x0, x0 + fw
    n1 = info["bac_ve_1"] - 1
    n2 = info["bac_ve_2"] - 1
    ymid = ys + max(n1, n2) * tread
    if not top:
        for i in range(n1 + 1):
            y = ys + i * tread
            sheet.line(P.T(xa0, y), P.T(xa1, y), "THANG")
        sheet.line(P.T(xa0, ys), P.T(xa0, ymid), "THANG")
    for i in range(n2 + 1):
        y = ys + i * tread
        sheet.line(P.T(xb0, y), P.T(xb1, y), "THANG")
    sheet.line(P.T(xb1, ys), P.T(xb1, ymid), "THANG")
    sheet.line(P.T(x0, ymid), P.T(x0 + sw, ymid), "THANG")  # mép chiếu nghỉ
    # mũi tên đường lên
    cx_a, cx_b = (xa0 + xa1) / 2, (xb0 + xb1) / 2
    yl = ymid + (core["y"] + core["l"] - ymid) / 2
    path = [(cx_a, ys + 0.1), (cx_a, yl), (cx_b, yl), (cx_b, ys + 0.1)] if not top else \
        [(cx_b, yl), (cx_b, ys + 0.1)]
    sheet.pline(P.Ts(path), "THANG", ls="dashed")
    end = path[-1]
    ah = 0.18
    sheet.pline(P.Ts([(end[0] - ah / 2, end[1] + ah), end, (end[0] + ah / 2, end[1] + ah)]), "THANG")
    label_pt = (cx_a, ys - 0.3) if not top else (cx_b, ys - 0.3)
    sheet.text(P.T(*label_pt), "LÊN" if not top else "XUỐNG", "THANG", h=1.8)
    if floor > 1 and not top:
        sheet.text(P.T(cx_b, ys - 0.3), "XUỐNG", "THANG", h=1.6)


def draw_void(sheet: Sheet, P: Plan, r: dict, ground: bool) -> None:
    x0, y0, x1, y1 = r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]
    if not ground:
        sheet.line(P.T(x0, y0), P.T(x1, y1), "GIENG_TROI", ls="dashed")
        sheet.line(P.T(x1, y0), P.T(x0, y1), "GIENG_TROI", ls="dashed")
    else:  # tiểu cảnh: vài khóm cây
        for i in range(3):
            cy = y0 + (i + 1) * (y1 - y0) / 4
            sheet.circle(P.T((x0 + x1) / 2, cy), min(0.35, r["w"] / 3), "THIET_BI")


def draw_furniture(sheet: Sheet, P: Plan, r: dict, W: float) -> None:
    L = "THIET_BI"
    x, y, w, h = r["x"], r["y"], r["w"], r["h"]

    def box(bx, by, bw, bh):
        sheet.pline(P.Ts([(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh)]), L, closed=True)

    t = r["loai"]
    if t == "ngu" and w >= 2.6 and h >= 2.6:
        bw, bl = (1.8, 2.0) if r["dien_tich"] >= 14 else (1.4, 2.0)
        bx = x + 0.3
        by = y + (h - bw) / 2
        box(bx, by, bl, bw)                    # giường quay đầu vào tường bên
        box(bx, by + 0.1, 0.45, bw / 2 - 0.15)  # gối
        box(bx, by + bw / 2 + 0.05, 0.45, bw / 2 - 0.15)
        if w >= 4.2:
            box(x + w - 0.75, y + 0.3, 0.6, min(1.8, h - 0.6))  # tủ áo
    elif t == "khach" and h >= 3:
        box(x + 0.3, y + h / 2 - 1.1, 0.85, 2.2)         # sofa
        box(x + 1.6, y + h / 2 - 0.5, 0.7, 1.0)          # bàn trà
        box(x + w - 0.55, y + h / 2 - 0.9, 0.4, 1.8)     # kệ tivi
    elif t == "bep":
        box(x + 0.0, y + 0.3, 0.6, min(h - 0.6, 3.0))     # tủ bếp dọc tường
        if w >= 3.5 and h >= 3.2:
            box(x + 1.4, y + h - 1.9, 0.9, 1.6)          # bàn ăn
    elif t == "wc":
        box(x + 0.15, y + h / 2 - 0.2, 0.7, 0.4)         # bồn cầu
        box(x + w - 1.2, y + 0.1, 0.5, 0.4)               # lavabo
    elif t == "gara":
        n = max(1, int((w - 0.6) // 0.9))
        for i in range(min(n, 5)):
            box(x + 0.3 + i * 0.9, y + 0.4, 0.6, 1.8)    # xe máy
    elif t == "tho":
        box(x + 0.2, y + h / 2 - 0.9, 0.6, 1.8)           # bàn thờ


# ---------------------------------------------------------------------------
# Kích thước, trục
# ---------------------------------------------------------------------------
def dim_chain(sheet: Sheet, pts: list[tuple], direction: tuple, offset_m: float) -> None:
    """Chuỗi kích thước qua các điểm thẳng hàng (tọa độ bản vẽ), đặt lệch theo `direction` (đơn vị)."""
    dx, dy = direction
    tick = sheet.m(1.2)
    pts = sorted(pts, key=lambda p: (p[0], p[1]))
    shifted = [(p[0] + dx * offset_m, p[1] + dy * offset_m) for p in pts]
    for p, s in zip(pts, shifted):
        sheet.line((p[0] + dx * sheet.m(1.5), p[1] + dy * sheet.m(1.5)),
                   (s[0] + dx * sheet.m(1.5), s[1] + dy * sheet.m(1.5)), "KICH_THUOC")
        sheet.line((s[0] - tick, s[1] - tick), (s[0] + tick, s[1] + tick), "KICH_THUOC", lw=0.35)
    sheet.line(shifted[0], shifted[-1], "KICH_THUOC")
    for a, b in zip(shifted, shifted[1:]):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 1e-3:
            continue
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        if ang > 90 or ang <= -90:
            ang -= 180 * (1 if ang > 0 else -1)
        nx, ny = -math.sin(math.radians(ang)), math.cos(math.radians(ang))
        sheet.text((mid[0] + nx * sheet.m(1.6), mid[1] + ny * sheet.m(1.6)), fmt_mm(length), "KICH_THUOC",
                   h=1.8 if length * 1000 / sheet.scale > 7 else 1.3, rot=ang)


def axis_bubble(sheet: Sheet, p_from, p_to, label: str) -> None:
    sheet.line(p_from, p_to, "TRUC", ls="center")
    r = sheet.m(3.2)
    dx, dy = p_to[0] - p_from[0], p_to[1] - p_from[1]
    n = math.hypot(dx, dy) or 1
    c = (p_to[0] + dx / n * r, p_to[1] + dy / n * r)
    sheet.circle(c, r, "TRUC")
    sheet.text(c, label, "TRUC", h=2.4)


def north_arrow(sheet: Sheet, c, huong: str, rotate_cw: float = 90.0, size_mm: float = 9.0) -> None:
    """Vẽ mũi tên chỉ Bắc. Mặt tiền (cạnh y=0) quay về `huong`; bản vẽ đã xoay `rotate_cw` độ."""
    from tools.fengshui import BEARING

    ang_cw = (180 - BEARING.get(huong, 180) + rotate_cw) % 360
    a = math.radians(90 - ang_cw)
    r = sheet.m(size_mm)
    tip = (c[0] + r * math.cos(a), c[1] + r * math.sin(a))
    left = (c[0] + r * 0.4 * math.cos(a + 2.5), c[1] + r * 0.4 * math.sin(a + 2.5))
    right = (c[0] + r * 0.4 * math.cos(a - 2.5), c[1] + r * 0.4 * math.sin(a - 2.5))
    sheet.circle(c, r * 0.75, "CHU")
    sheet.fill([tip, left, c], "CHU", color="#111111")
    sheet.pline([tip, right, c], "CHU", closed=True)
    sheet.text((c[0] + r * 1.35 * math.cos(a), c[1] + r * 1.35 * math.sin(a)), "B", "CHU", h=3, bold=True)


def level_mark(sheet: Sheet, p, text: str, layer="CHU") -> None:
    s = sheet.m(2.0)
    sheet.pline([(p[0] - s, p[1] + s), p, (p[0] + s, p[1] + s)], layer, closed=True)
    sheet.line((p[0], p[1] + s), (p[0] + sheet.m(14), p[1] + s), layer)
    sheet.text((p[0] + sheet.m(1), p[1] + s + sheet.m(1.6)), text, layer, h=2.0, ha="left")


# ---------------------------------------------------------------------------
# Mặt bằng tầng
# ---------------------------------------------------------------------------
def draw_floor_plan(sheet: Sheet, layout: dict, floor: int, brief: dict) -> None:
    W = layout["building"]["w"]
    lot_l = layout["lot"]["l"]
    P = Plan(W)
    sheet.choose_scale(lot_l + 6.0, W + 7.0)
    fl = layout["floors"][str(floor)]
    rooms = fl["rooms"]
    openings = fl["doors"] + fl["windows"]
    segs = wall_segments(rooms, openings)
    draw_walls(sheet, P, segs)
    for d in fl["doors"]:
        t = EXT_T if wall_type_at(segs, d["orient"], d["c"], (d["a"] + d["b"]) / 2) == "ngoai" else INT_T
        draw_door(sheet, P, d, t)
    for wdw in fl["windows"]:
        t = EXT_T if wall_type_at(segs, wdw["orient"], wdw["c"], (wdw["a"] + wdw["b"]) / 2) == "ngoai" else INT_T
        draw_window(sheet, P, wdw, t)
    # ranh giới lô đất (chỉ thể hiện ở mặt bằng tầng 1)
    lot_w = layout["lot"]["w"]
    if floor == 1:
        sheet.pline(P.Ts([(0, 0), (lot_w, 0), (lot_w, lot_l), (0, lot_l)]), "RANH_GIOI", closed=True, ls="dashdot",
                    lw=0.18)
    draw_stair(sheet, P, layout, floor)
    for r in rooms:
        cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
        if r["loai"] == "gieng_troi":
            draw_void(sheet, P, r, floor == 1)
            sheet.text(P.T(cx, cy), r["ten"].upper() + "\n" + fmt_area(r["dien_tich"]), "CHU_PHONG", h=1.7, rot=90)
            continue
        if r["loai"] == "thang":
            continue
        if r["loai"] == "hanh_lang":
            if r["h"] > 2.5:
                sheet.text(P.T(cx, cy), r["ten"], "CHU_PHONG", h=1.6, rot=90)
            continue
        draw_furniture(sheet, P, r, W)
        txt = r["ten"].upper() + "\n" + fmt_area(r["dien_tich"])
        if r["h"] < 1.5:
            sheet.text(P.T(cx, cy), r["ten"].upper() + " " + fmt_area(r["dien_tich"]), "CHU_PHONG", h=1.6, rot=90)
        else:
            sheet.text(P.T(cx + 0.6 if r["loai"] in ("ngu", "khach") else cx, cy), txt, "CHU_PHONG",
                       h=2.2 if r["dien_tich"] > 8 else 1.8, bold=False)
    # Cao độ sàn
    z = sum(layout["heights"][:floor - 1])
    first = next((r for r in rooms if r["loai"] not in ("san",) and r["y"] >= layout["building"]["y"] - EPS), rooms[0])
    level_mark(sheet, P.T(W * 0.25, first["y"] + min(first["h"] * 0.5, 1.2)), f"{z:+.3f}".replace("+0.000", "±0.000"))

    # Kích thước: theo chiều sâu (phía trên giấy, x = 0 nhà -> trên cùng)
    y_bounds = sorted({round(s["y"], 3) for s in fl["strips"]} | {round(layout["building"]["y"] + layout["building"]["l"], 3)})
    top_v = W
    chain = [P.T(0, y) for y in y_bounds]
    dim_chain(sheet, chain, (0, 1), sheet.m(9))
    overall = [P.T(0, 0), P.T(0, lot_l)]
    dim_chain(sheet, overall, (0, 1), sheet.m(17))
    # theo chiều ngang (bên trái giấy)
    core = layout["core"]
    xb = sorted({0.0, round(core["sky_w"], 3), round(core["sky_w"] + core["stair_w"], 3), round(W, 3)})
    dim_chain(sheet, [P.T(x, 0) for x in xb], (-1, 0), sheet.m(11))
    dim_chain(sheet, [P.T(0, 0), P.T(W, 0)], (-1, 0), sheet.m(19))
    # Trục
    letters = "ABCDE"
    for i, x in enumerate([0.0, W]):
        axis_bubble(sheet, P.T(x, lot_l), P.T(x, lot_l + sheet.m(10)), letters[i])
    main_y = [layout["building"]["y"], core["y"], core["y"] + core["l"], layout["building"]["y"] + layout["building"]["l"]]
    for i, y in enumerate(main_y, start=1):
        axis_bubble(sheet, P.T(W, y), P.T(W + sheet.m(8), y), str(i))
    sheet.text(P.T(W / 2, -sheet.m(6)), "MẶT TIỀN", "CHU", h=2.4, rot=90, bold=True)
    if floor == 1:
        north_arrow(sheet, P.T(-sheet.m(14), -sheet.m(30)), brief["lo_dat"]["huong"])
    _ = top_v


# ---------------------------------------------------------------------------
# Mặt bằng tổng thể
# ---------------------------------------------------------------------------
def hatch_rect(sheet: Sheet, x0, y0, x1, y1, spacing, layer="HATCH"):
    """Gạch chéo 45° trong hình chữ nhật (tọa độ bản vẽ)."""
    w, h = x1 - x0, y1 - y0
    k = 0.0
    while k < w + h:
        p1 = (x0 + max(0, k - h), y0 + min(k, h))
        p2 = (x0 + min(k, w), y0 + max(0, k - w))
        sheet.line(p1, p2, layer)
        k += spacing


def draw_site_plan(sheet: Sheet, layout: dict, area: dict, brief: dict) -> None:
    W, lot_l = layout["lot"]["w"], layout["lot"]["l"]
    P = Plan(W)
    sheet.choose_scale(lot_l + 22, W + 22)
    road = 8.0
    # đường phía trước (bên trái giấy)
    sheet.pline(P.Ts([(-6, -road), (W + 6, -road)]), "DAT")
    sheet.pline(P.Ts([(-6, 0), (W + 6, 0)]), "DAT")
    sheet.line(P.T(-6, -road / 2), P.T(W + 6, -road / 2), "PHU", ls="dashed")
    sheet.text(P.T(W / 2, -road / 2 - 1.2), "ĐƯỜNG / NGÕ HIỆN TRẠNG", "CHU", h=2.4, rot=90)
    # lô đất + nhà bên cạnh
    sheet.pline(P.Ts([(0, 0), (W, 0), (W, lot_l), (0, lot_l)]), "RANH_GIOI", closed=True, ls="dashdot", lw=0.5)
    for side in (-1, 1):
        x0 = -5.0 if side < 0 else W
        sheet.pline(P.Ts([(x0, 0), (x0 + 5, 0), (x0 + 5, lot_l * 0.85), (x0, lot_l * 0.85)]), "PHU", closed=True)
        sheet.text(P.T(x0 + 2.5, lot_l * 0.42), "NHÀ LIỀN KỀ", "PHU", h=2.0)
    b = layout["building"]
    p0, p1 = P.T(b["x"], b["y"]), P.T(b["x"] + b["w"], b["y"] + b["l"])
    bx0, by0 = min(p0[0], p1[0]), min(p0[1], p1[1])
    bx1, by1 = max(p0[0], p1[0]), max(p0[1], p1[1])
    hatch_rect(sheet, bx0, by0, bx1, by1, 0.8)
    sheet.pline([(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)], "TUONG", closed=True, lw=0.6)
    sheet.text(((bx0 + bx1) / 2, (by0 + by1) / 2), f"NHÀ Ở {area['so_tang']} TẦNG\nDT XD {fmt_area(area['dien_tich_xay_dung'])}",
               "CHU", h=2.6, bold=True)
    if layout["san_truoc"] > 0:
        sheet.text(P.T(W / 2, layout["san_truoc"] / 2), "SÂN TRƯỚC", "CHU", h=2.0, rot=90)
    if layout["san_sau"] > 0:
        sheet.text(P.T(W / 2, lot_l - layout["san_sau"] / 2), "SÂN SAU", "CHU", h=2.0, rot=90)
    sheet.text(P.T(W / 2, -1.0), "LỐI VÀO", "CHU", h=2.0, rot=90)
    sheet.pline(P.Ts([(W / 2, -2.6), (W / 2, -0.4)]), "CHU")
    sheet.pline(P.Ts([(W / 2 - 0.3, -0.9), (W / 2, -0.4), (W / 2 + 0.3, -0.9)]), "CHU")
    # kích thước
    dim_chain(sheet, [P.T(0, y) for y in sorted({0.0, b["y"], b["y"] + b["l"], lot_l})], (0, 1), 6.5)
    dim_chain(sheet, [P.T(0, 0), P.T(0, lot_l)], (0, 1), 8.5)
    dim_chain(sheet, [P.T(0, lot_l), P.T(W, lot_l)], (1, 0), 3.0)
    north_arrow(sheet, P.T(W + 3.5, lot_l + 4), brief["lo_dat"]["huong"], size_mm=12)

    # bảng chỉ tiêu (giấy)
    rows = [
        ("Diện tích lô đất", fmt_area(area["dien_tich_dat"])),
        ("Diện tích xây dựng", fmt_area(area["dien_tich_xay_dung"])),
        ("Mật độ xây dựng", f"{area['mat_do_xay_dung'] * 100:.1f}%".replace(".", ",")),
        ("Số tầng", f"{area['so_tang']} tầng"),
        ("Tổng diện tích sàn", fmt_area(area["tong_dien_tich_san"])),
        ("Chiều cao công trình", f"{area['chieu_cao_cong_trinh']:.2f} m".replace(".", ",")),
        ("Hướng mặt tiền", brief["lo_dat"]["huong"]),
    ]
    x0, ytop = 30.0, 120.0
    sheet.text((x0, ytop + 6), "CHỈ TIÊU KỸ THUẬT", "CHU", h=3.0, ha="left", bold=True, paper=True)
    for i, (k, v) in enumerate(rows):
        y = ytop - i * 7
        sheet.rect(x0, y - 7, 46, 7, "KHUNG_TEN", paper=True)
        sheet.rect(x0 + 46, y - 7, 34, 7, "KHUNG_TEN", paper=True)
        sheet.text((x0 + 2, y - 3.5), k, "CHU", h=2.0, ha="left", paper=True)
        sheet.text((x0 + 48, y - 3.5), v, "CHU", h=2.0, ha="left", paper=True)


# ---------------------------------------------------------------------------
# Mặt bằng mái
# ---------------------------------------------------------------------------
def draw_roof_plan(sheet: Sheet, layout: dict, brief: dict) -> None:
    W, lot_l = layout["lot"]["w"], layout["lot"]["l"]
    P = Plan(W)
    sheet.choose_scale(lot_l + 6.0, W + 7.0)
    top = layout["floors"][str(layout["so_tang"])]
    b = layout["building"]
    y_front, y_back = b["y"], b["y"] + b["l"]
    sheet.pline(P.Ts([(0, 0), (W, 0), (W, lot_l), (0, lot_l)]), "RANH_GIOI", closed=True, ls="dashdot")
    # các vùng: mái BTCT trên phần kín tầng trên cùng, sân thượng hở
    covered = [r for r in top["rooms"] if r["loai"] not in ("san_phoi", "ban_cong", "san")]
    open_ = [r for r in top["rooms"] if r["loai"] in ("san_phoi", "ban_cong")]
    ys = sorted({round(r["y"], 3) for r in covered} | {round(r["y"] + r["h"], 3) for r in covered})
    ry0, ry1 = ys[0], ys[-1]
    sheet.pline(P.Ts([(0, ry0), (W, ry0), (W, ry1), (0, ry1)]), "MAI", closed=True, lw=0.5)
    off = 0.11
    sheet.pline(P.Ts([(off, ry0 + off), (W - off, ry0 + off), (W - off, ry1 - off), (off, ry1 - off)]), "MAI",
                closed=True)
    sheet.text(P.T(W * 0.55, (ry0 + layout["core"]["y"]) / 2), "MÁI BTCT\nCHỐNG NÓNG, i = 2%", "CHU", h=2.0)
    # giếng trời
    core = layout["core"]
    if core["sky_w"] > 0:
        gx0, gy0, gx1, gy1 = 0, core["y"], core["sky_w"], core["y"] + core["l"]
        sheet.pline(P.Ts([(gx0, gy0), (gx1, gy0), (gx1, gy1), (gx0, gy1)]), "GIENG_TROI", closed=True, lw=0.35)
        sheet.line(P.T(gx0, gy0), P.T(gx1, gy1), "GIENG_TROI")
        sheet.line(P.T(gx1, gy0), P.T(gx0, gy1), "GIENG_TROI")
        for i in range(1, int(core["l"] / 0.3)):
            sheet.line(P.T(gx0, gy0 + i * 0.3), P.T(gx1, gy0 + i * 0.3), "PHU")
        sheet.text(P.T((gx0 + gx1) / 2 + 0.9, (gy0 + gy1) / 2), "GIẾNG TRỜI\nMÁI KÍNH + LAM NHÔM", "CHU", h=1.8)
    # ô mái cầu thang (tum)
    sx = core["stair_x"]
    sheet.text(P.T(sx + core["stair_w"] / 2, core["y"] + core["l"] / 2), "MÁI SẢNH THANG", "CHU", h=1.8, rot=90)
    # hướng dốc + phễu thu
    for yy in (ry0 + 0.8, ry1 - 0.8):
        if ry1 - ry0 < 2:
            break
    drains = [(W - 0.4, ry1 - 0.4), (0.4 + (core["sky_w"] if ry1 - 0.4 > core["y"] and ry1 - 0.4 < core["y"] + core["l"] else 0), ry1 - 0.4)]
    for d in drains:
        sheet.circle(P.T(*d), 0.12, "MAI")
    sheet.text(P.T(W - 0.4, ry1 - 1.1), "ỐNG THOÁT\nD90", "CHU", h=1.5, rot=90)
    mid_x = W * 0.75
    for yy in (ry0 + (ry1 - ry0) * 0.3, ry0 + (ry1 - ry0) * 0.7):
        sheet.pline(P.Ts([(mid_x, yy - 0.8), (mid_x, yy + 0.8)]), "MAI")
        sheet.pline(P.Ts([(mid_x - 0.15, yy + 0.55), (mid_x, yy + 0.8), (mid_x + 0.15, yy + 0.55)]), "MAI")
    # sênh thoát nước dọc mép sau mái
    sheet.line(P.T(0.15, ry1 - 0.25), P.T(W - 0.15, ry1 - 0.25), "MAI", ls="dashed")
    sheet.text(P.T(W * 0.3, ry1 - 0.55), "SÊNH THOÁT NƯỚC", "CHU", h=1.5)
    for r in open_:
        sheet.pline(P.Ts([(0, r["y"]), (W, r["y"]), (W, r["y"] + r["h"]), (0, r["y"] + r["h"])]), "LAN_CAN",
                    closed=True)
        sheet.text(P.T(W / 2, r["y"] + r["h"] / 2), f"{r['ten'].upper()} TẦNG {layout['so_tang']}\n(sàn mái tầng dưới)",
                   "CHU", h=1.8, rot=90)
    z_roof = sum(layout["heights"])
    level_mark(sheet, P.T(W * 0.2, ry0 + 1.0), f"+{z_roof:.3f}")
    dim_chain(sheet, [P.T(0, y) for y in sorted({0.0, y_front, ry0, ry1, y_back, lot_l})], (0, 1), sheet.m(9))
    dim_chain(sheet, [P.T(0, 0), P.T(W, 0)], (-1, 0), sheet.m(12))
