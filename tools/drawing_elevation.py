"""Vẽ mặt đứng chính (KT-07) và mặt cắt dọc (KT-08). Hệ tọa độ: u ngang, z cao độ (m)."""
from __future__ import annotations

from tools.drawing_plan import dim_chain, fmt_mm, hatch_rect, level_mark
from tools.layout_algorithm import room_at
from tools.sheet import Sheet

ROAD_Z = -0.45
SLAB = 0.15
PARAPET = 1.0


def _levels(layout: dict) -> list[float]:
    z, out = 0.0, []
    for h in layout["heights"]:
        out.append(round(z, 3))
        z += h
    out.append(round(z, 3))
    return out


def _fmt_level(z: float) -> str:
    return "±0.000" if abs(z) < 1e-6 else f"{z:+.3f}"


# ---------------------------------------------------------------------------
# Mặt đứng chính
# ---------------------------------------------------------------------------
def draw_front_elevation(sheet: Sheet, layout: dict, program: dict) -> None:
    W = layout["building"]["w"]
    lv = _levels(layout)
    z_roof = lv[-1]
    top = z_roof + PARAPET
    sheet.choose_scale(W + 14, top + 6)
    L = "TUONG"
    # đất
    sheet.line((-3, ROAD_Z), (W + 3, ROAD_Z), "DAT", lw=0.6)
    hatch_rect(sheet, -3, ROAD_Z - 0.5, W + 3, ROAD_Z, 0.35, "HATCH")
    # bậc tam cấp
    for i in range(3):
        sheet.line((0.3, ROAD_Z + i * 0.15), (W - 0.3, ROAD_Z + i * 0.15), "PHU")
    # khối nhà
    sheet.pline([(0, ROAD_Z), (W, ROAD_Z), (W, top), (0, top)], L, closed=True, lw=0.6)
    for z in lv[1:-1]:
        sheet.rect(0, z - 0.3, W, 0.3, "SAN")          # dầm biên / mép sàn
    sheet.rect(0, z_roof - 0.3, W, 0.3, "SAN")
    sheet.line((0, z_roof + PARAPET - 0.1), (W, z_roof + PARAPET - 0.1), "PHU")
    floors = layout["floors"]
    for i in range(layout["so_tang"]):
        z0, z1 = lv[i], lv[i + 1] - 0.3
        fl = floors[str(i + 1)]
        first = room_at(fl["rooms"], W / 2, layout["building"]["y"] + 0.05)
        if i == 0:
            if first and first["loai"] == "gara":
                sheet.rect(0.3, z0, W - 0.6, 3.0, "CUA", lw=0.35)
                for k in range(1, 15):
                    sheet.line((0.3, z0 + k * 0.2), (W - 0.3, z0 + k * 0.2), "CUA")
                sheet.text((W / 2, z0 + 2.7), "CỬA CUỐN", "CHU", h=1.8)
            else:
                w = min(1.6, W - 1.2)
                sheet.rect(W / 2 - w / 2, z0, w, 2.6, "CUA", lw=0.35)
                sheet.line((W / 2, z0), (W / 2, z0 + 2.6), "CUA")
            # ô thoáng phía trên
            sheet.rect(0.3, z0 + 3.05, W - 0.6, max(0.1, z1 - z0 - 3.15), "CUA_SO")
            continue
        if first and first["loai"] == "ban_cong":
            w = min(2.4, W - 1.6)
            sheet.rect(W / 2 - w / 2, z0, w, 2.4, "CUA", lw=0.3)
            sheet.line((W / 2, z0), (W / 2, z0 + 2.4), "CUA")
            sheet.rect(W / 2 - w / 2, z0 + 2.4, w, min(0.5, z1 - z0 - 2.5), "CUA_SO")
            # lan can kính
            sheet.rect(0.15, z0, W - 0.3, 1.1, "LAN_CAN", lw=0.35)
            for k in range(1, 4):
                sheet.line((0.15 + k * (W - 0.3) / 4, z0), (0.15 + k * (W - 0.3) / 4, z0 + 1.1), "LAN_CAN")
            sheet.line((0.15, z0 + 1.1), (W - 0.15, z0 + 1.1), "LAN_CAN", lw=0.5)
        elif first and first["loai"] == "san_phoi":
            sheet.rect(0.15, z0, W - 0.3, 1.1, "LAN_CAN", lw=0.35)
            # tường lùi phía sau sân thượng (phòng thờ)
            sheet.rect(W / 2 - 0.9, z0 + 0.9, 1.8, 1.4, "CUA_SO")
            sheet.text((W / 2, z0 + 1.6), "(lùi vào)", "PHU", h=1.4)
            for k in range(4):  # chậu cây
                sheet.circle((0.6 + k * (W - 1.2) / 3, z0 + 1.35), 0.25, "THIET_BI")
        else:
            w = min(2.0, W - 1.6)
            sheet.rect(W / 2 - w / 2, z0 + 0.9, w, 1.4, "CUA_SO", lw=0.3)
            sheet.line((W / 2, z0 + 0.9), (W / 2, z0 + 2.3), "CUA_SO")
    # khung bao mặt tiền + lam đứng (phong cách hiện đại)
    sheet.rect(-0.05, lv[1] - 0.3, 0.35, top - lv[1] + 0.3, "TUONG", lw=0.35)
    sheet.rect(W - 0.3, lv[1] - 0.3, 0.35, top - lv[1] + 0.3, "TUONG", lw=0.35)
    if layout["so_tang"] >= 3:
        for k in range(5):
            x = W - 0.45 - k * 0.12
            sheet.line((x, lv[2]), (x, z_roof), "PHU")
    # cao độ
    for i, z in enumerate(lv):
        level_mark(sheet, (-1.6, z), _fmt_level(z))
    level_mark(sheet, (-1.6, top), _fmt_level(top))
    level_mark(sheet, (-3.4, ROAD_Z), _fmt_level(ROAD_Z) + " (vỉa hè)")
    dim_chain(sheet, [(W, z) for z in [ROAD_Z] + lv + [top]], (1, 0), sheet.m(14))
    dim_chain(sheet, [(W, ROAD_Z), (W, top)], (1, 0), sheet.m(24))
    dim_chain(sheet, [(0, ROAD_Z), (W, ROAD_Z)], (0, -1), sheet.m(12))
    # ghi chú vật liệu
    vl = program.get("vat_lieu", {})
    notes = [(lv[-1] + 0.5, f"Tường mái: {vl.get('mat_tien', 'sơn ngoại thất')}"),
             (lv[min(2, len(lv) - 2)] + 0.55, f"Lan can: {vl.get('lan_can', 'kính cường lực')}"),
             (lv[min(2, len(lv) - 2)] + 1.8, f"Cửa: {vl.get('cua', 'nhôm kính')}"),
             (1.5, "Cửa cuốn / cửa chính tầng 1"),
             (lv[1] - 0.15, "Dầm biên sơn màu xám đậm")]
    xt = W + sheet.m(32)
    for z, s in notes:
        sheet.line((W - 0.3, z), (xt - sheet.m(1), z), "PHU")
        sheet.circle((W - 0.3, z), sheet.m(0.6), "PHU", fill=True)
        sheet.text((xt, z), s, "CHU", h=2.0, ha="left")


# ---------------------------------------------------------------------------
# Mặt cắt dọc
# ---------------------------------------------------------------------------
def draw_long_section(sheet: Sheet, layout: dict) -> None:
    b = layout["building"]
    y_front, y_back = b["y"], b["y"] + b["l"]
    lot_l = layout["lot"]["l"]
    lv = _levels(layout)
    z_roof = lv[-1]
    sheet.choose_scale(lot_l + 12, z_roof + PARAPET + 7)
    core, st = layout["core"], layout["stair"]
    cut_x = core["stair_x"] + st["rong"] - st["ve_rong"] / 2     # cắt qua vế 1
    fill = "#5b5b5b"

    # đất
    sheet.line((-3, ROAD_Z), (0, ROAD_Z), "DAT", lw=0.6)
    sheet.line((0, ROAD_Z), (0, -SLAB), "DAT")
    sheet.line((0, -SLAB), (lot_l + 2, -SLAB), "DAT", lw=0.6)
    hatch_rect(sheet, -3, -1.2, lot_l + 2, ROAD_Z, 0.4, "HATCH")
    # móng (ký hiệu)
    for y in (y_front, core["y"], core["y"] + core["l"], y_back):
        sheet.rect(y - 0.6, -1.2, 1.2, 0.35, "SAN", ls="dashed")
    n = layout["so_tang"]
    stair_open = (core["y"] + st["chieu_nghi"], core["y"] + core["l"] - st["chieu_nghi"])
    for i in range(n + 1):
        z = lv[i]
        if i == 0:
            sheet.fill([(y_front, -SLAB), (y_back, -SLAB), (y_back, 0), (y_front, 0)], "TUONG_FILL", color=fill)
            continue
        fl = layout["floors"][str(min(i + 1, n))] if i < n else None
        # sàn tầng i+1 (hoặc mái) – khoét lỗ cầu thang
        segments = [(y_front, stair_open[0]), (core["y"] + core["l"], y_back)] if i < n else [(y_front, y_back)]
        if i == n:
            top_fl = layout["floors"][str(n)]
            open_back = [r for r in top_fl["rooms"] if r["loai"] in ("san_phoi",)]
            segs = []
            covered = [r for r in top_fl["rooms"] if r["loai"] not in ("san_phoi", "ban_cong", "san")]
            ry0 = min(r["y"] for r in covered)
            ry1 = max(r["y"] + r["h"] for r in covered)
            segs.append((ry0, ry1))
            segments = segs
            _ = open_back
        for a, c in segments:
            sheet.fill([(a, z - SLAB), (c, z - SLAB), (c, z), (a, z)], "TUONG_FILL", color=fill)
        # chiếu nghỉ giữa
        if i < n:
            info = st["cac_tang"][i - 1]
            zl = lv[i - 1] + info["bac_ve_1"] * info["bac_cao"]
            sheet.fill([(stair_open[1], zl - 0.12), (core["y"] + core["l"], zl - 0.12),
                        (core["y"] + core["l"], zl), (stair_open[1], zl)], "TUONG_FILL", color=fill)
            # vế 1 (bị cắt) – răng cưa
            pts = []
            y0s = core["y"] + st["chieu_nghi"]
            z0s = lv[i - 1]
            for k in range(info["bac_ve_1"]):
                pts += [(y0s + k * info["bac_rong"], z0s + k * info["bac_cao"]),
                        (y0s + k * info["bac_rong"], z0s + (k + 1) * info["bac_cao"])]
            pts.append((stair_open[1], zl))
            sheet.pline(pts, "THANG", lw=0.35)
            sheet.line((y0s, z0s - 0.12), (stair_open[1], zl - 0.12), "THANG", lw=0.35)
            # vế 2 (nhìn thấy) – nét mảnh
            y2 = core["y"] + st["chieu_nghi"]
            sheet.line((stair_open[1], zl), (y2, lv[i]), "THANG", ls="dashed")
            # lan can
            sheet.line((y0s, z0s + 0.9), (stair_open[1], zl + 0.9), "LAN_CAN")
    # tường cắt mặt trước / sau và vách ngăn
    for i in range(n):
        z0, z1 = lv[i], lv[i + 1] - SLAB
        fl = layout["floors"][str(i + 1)]
        first = room_at(fl["rooms"], cut_x, y_front + 0.05)
        last = room_at(fl["rooms"], cut_x, y_back - 0.05)
        # mặt tiền
        if first and first["loai"] in ("ban_cong", "san_phoi"):
            sheet.rect(y_front, z0, 0.05, 1.1, "LAN_CAN")
            ywall = first["y"] + first["h"]
        else:
            ywall = y_front
        if i == 0 and first and first["loai"] == "gara":
            sheet.fill([(ywall, z0 + 3.0), (ywall + 0.22, z0 + 3.0), (ywall + 0.22, z1), (ywall, z1)], "TUONG_FILL",
                       color=fill)
        else:
            sheet.fill([(ywall, z0), (ywall + 0.22, z0), (ywall + 0.22, z0 + 0.9), (ywall, z0 + 0.9)], "TUONG_FILL",
                       color=fill)
            sheet.fill([(ywall, z0 + 2.4), (ywall + 0.22, z0 + 2.4), (ywall + 0.22, z1), (ywall, z1)], "TUONG_FILL",
                       color=fill)
            sheet.line((ywall + 0.11, z0 + 0.9), (ywall + 0.11, z0 + 2.4), "CUA_SO")
        # mặt sau
        if last and last["loai"] in ("san_phoi", "ban_cong"):
            sheet.rect(y_back - 0.05, z0, 0.05, 1.1, "LAN_CAN")
            yb = last["y"]
        else:
            yb = y_back
        sheet.fill([(yb - 0.22, z0), (yb, z0), (yb, z1), (yb - 0.22, z1)], "TUONG_FILL", color=fill)
        # vách ngăn giữa các dải (theo đường cắt)
        for s in fl["strips"]:
            for y in (s["y"],):
                if y <= ywall + 0.3 or y >= yb - 0.3:
                    continue
                ra, rb = room_at(fl["rooms"], cut_x, y - 0.01), room_at(fl["rooms"], cut_x, y + 0.01)
                if ra is None or rb is None or ra["loai"] in ("thang",) or rb["loai"] in ("thang",):
                    continue
                if ra["loai"] in ("ban_cong", "san_phoi") and rb["loai"] in ("ban_cong", "san_phoi"):
                    continue
                sheet.fill([(y - 0.055, z0), (y + 0.055, z0), (y + 0.055, z1), (y - 0.055, z1)], "TUONG_FILL",
                           color="#8a8a8a")
        # tên phòng
        for r in fl["rooms"]:
            if r["x"] - 1e-6 <= cut_x <= r["x"] + r["w"] + 1e-6 and r["loai"] not in ("thang", "san") and r["h"] > 1.4:
                sheet.text((r["y"] + r["h"] / 2, z0 + 1.6), r["ten"].upper(), "CHU_PHONG",
                           h=1.8 if r["h"] > 2.5 else 1.4)
    # tường chắn mái
    top_fl = layout["floors"][str(n)]
    covered = [r for r in top_fl["rooms"] if r["loai"] not in ("san_phoi", "ban_cong", "san")]
    ry0 = min(r["y"] for r in covered)
    ry1 = max(r["y"] + r["h"] for r in covered)
    for y in (ry0, ry1 - 0.22):
        sheet.fill([(y, z_roof), (y + 0.22, z_roof), (y + 0.22, z_roof + PARAPET), (y, z_roof + PARAPET)],
                   "TUONG_FILL", color=fill)
    # giếng trời (phía sau mặt cắt)
    if core["sky_w"] > 0:
        sheet.pline([(core["y"], lv[1]), (core["y"], z_roof + 0.6), (core["y"] + core["l"], z_roof + 0.6),
                     (core["y"] + core["l"], lv[1])], "GIENG_TROI", ls="dashed")
        sheet.line((core["y"], z_roof + 0.6), (core["y"] + core["l"], z_roof + 0.6), "GIENG_TROI", lw=0.5)
        sheet.text((core["y"] + core["l"] / 2, z_roof + 0.95), "MÁI KÍNH GIẾNG TRỜI", "CHU", h=1.6, va="bottom")
    # cao độ & kích thước
    for z in lv:
        level_mark(sheet, (-1.6, z), _fmt_level(z))
    level_mark(sheet, (-1.6, z_roof + PARAPET), _fmt_level(z_roof + PARAPET))
    dim_chain(sheet, [(y_back + 0.0, z) for z in [ROAD_Z] + lv + [z_roof + PARAPET]], (1, 0),
              (lot_l - y_back) + sheet.m(10))
    ys = sorted({round(s["y"], 3) for s in layout["floors"]["1"]["strips"]} | {round(y_back, 3)})
    dim_chain(sheet, [(y, -1.2) for y in ys], (0, -1), sheet.m(8))
    dim_chain(sheet, [(0, -1.2), (lot_l, -1.2)], (0, -1), sheet.m(15))
    sheet.text((-2.4, ROAD_Z + 0.4), "MẶT TIỀN", "CHU", h=2.0, bold=True, ha="right")
    sheet.text((lot_l / 2, z_roof + PARAPET + sheet.m(8)),
               f"MẶT CẮT A-A (cắt dọc qua cầu thang, cách mép trái {fmt_mm(cut_x)} mm)", "CHU", h=2.4)
