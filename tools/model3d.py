"""Dựng mô hình 3D của ngôi nhà từ đúng `layout` mà các bản vẽ 2D sử dụng.

Mọi cấu kiện là khối hộp song song trục, đơn vị mét: x ngang lô đất, y sâu vào trong (mặt tiền y nhỏ), z cao.
Bề dày tường, chiều cao cửa, tường chắn mái… lấy chung hằng số với bản vẽ 2D. Mặt trong tường bao trùng mặt bằng 2D,
phần tường vượt ra ngoài ranh nhà được cắt bỏ để mô hình nằm gọn trong lô đất.
Xuất GLB (trục Y hướng lên, mặt tiền quay về +Z) và DXF 3D (mm). Không dùng LLM; cùng dữ liệu luôn cho cùng mô hình.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import NamedTuple

import numpy as np

from tools.design_option import option_stamp
from tools.drawing_elevation import PARAPET, ROAD_Z, SLAB, _levels
from tools.drawing_plan import EXT_T, INT_T, draw_furniture, wall_segments
from tools.layout_algorithm import DOOR_SIZE, room_at

YARD_Z = -SLAB
SILL, HEAD = 0.9, 2.3            # bậu và đỉnh cửa sổ (theo mặt đứng)
RAIL_H, RAIL_T = 1.1, 0.04
BEAM = 0.3                       # dầm biên mặt tiền (theo mặt đứng)
OUTDOOR = ("ban_cong", "san_phoi")
INSET = 0.02

# vật liệu: (tên hiển thị, màu sRGB, độ đục, độ nhám, kim loại)
MATERIALS = {
    "tuong_ngoai": ("Tường ngoài", "#efece4", 1.0, 0.90, 0.0),
    "tuong_trong": ("Tường trong", "#f8f5ef", 1.0, 0.95, 0.0),
    "san_go": ("Sàn phòng ở", "#c8a27b", 1.0, 0.70, 0.0),
    "san_gach": ("Sàn gạch", "#d8d2c6", 1.0, 0.60, 0.0),
    "san_uot": ("Sàn khu ướt", "#afc1c6", 1.0, 0.55, 0.0),
    "san_ngoai": ("Sàn ban công, sân thượng", "#b5a998", 1.0, 0.85, 0.0),
    "dam": ("Dầm biên", "#565b60", 1.0, 0.80, 0.0),
    "khung": ("Khung nhôm", "#2f3539", 1.0, 0.45, 0.6),
    "kinh": ("Kính", "#8fc1d6", 0.35, 0.08, 0.0),
    "cua_go": ("Cửa gỗ", "#8a5c38", 1.0, 0.60, 0.0),
    "cua_cuon": ("Cửa cuốn", "#8d9499", 1.0, 0.50, 0.5),
    "thang": ("Cầu thang", "#b48a5f", 1.0, 0.65, 0.0),
    "mai": ("Mái bê tông", "#aaa59c", 1.0, 0.95, 0.0),
    "noi_that": ("Nội thất minh họa", "#cdbfa9", 1.0, 0.85, 0.0),
    "san_vuon": ("Sân", "#9db28a", 1.0, 1.00, 0.0),
    "nen": ("Nền, vỉa hè", "#c6c2b9", 1.0, 1.00, 0.0),
}
TRANSPARENT = {name for name, spec in MATERIALS.items() if spec[2] < 1}
FLOOR_MATERIAL = {"ngu": "san_go", "lam_viec": "san_go", "tho": "san_go", "khach": "san_go",
                  "sinh_hoat": "san_go", "wc": "san_uot", "ban_cong": "san_ngoai", "san_phoi": "san_ngoai"}


class Box(NamedTuple):
    group: int      # 0 khu đất, 1..n tầng, n+1 mái
    mat: str
    x0: float
    y0: float
    z0: float
    x1: float
    y1: float
    z1: float


def group_name(group: int, floors: int) -> str:
    return "Khu đất" if group == 0 else "Mái" if group > floors else f"Tầng {group}"


class _Identity:
    @staticmethod
    def T(x, y):
        return (x, y)

    @staticmethod
    def Ts(pts):
        return list(pts)


class _Footprints:
    """Ghi lại hình chiếu nội thất mà mặt bằng 2D đã vẽ."""

    def __init__(self):
        self.rects = []

    def pline(self, pts, *_, **__):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.rects.append((min(xs), min(ys), max(xs), max(ys)))


def _furniture_height(kind: str, index: int) -> float:
    if kind == "ngu":
        return (0.50, 0.62, 0.62, 2.10)[min(index, 3)]
    if kind == "khach":
        return (0.80, 0.42, 0.50)[min(index, 2)]
    if kind == "bep":
        return (0.85, 0.75)[min(index, 1)]
    if kind == "wc":
        return (0.42, 0.80)[min(index, 1)]
    return {"gara": 1.0, "tho": 1.1}.get(kind, 0.75)


class _Builder:
    def __init__(self, layout: dict):
        self.layout = layout
        self.b = layout["building"]
        self.lv = _levels(layout)
        self.n = layout["so_tang"]
        self.boxes: list[Box] = []

    def box(self, group, mat, x0, y0, z0, x1, y1, z1):
        if x1 - x0 > 1e-4 and y1 - y0 > 1e-4 and z1 - z0 > 1e-4:
            self.boxes.append(Box(group, mat, *(round(float(v), 4) for v in (x0, y0, z0, x1, y1, z1))))

    # ---------- hệ trục theo tường ----------
    def across(self, orient: str, c: float, t: float) -> tuple[float, float]:
        """Khoảng bề dày của tường tim tại c; tường trên ranh nhà chỉ giữ nửa phía trong."""
        lo, hi = ((self.b["y"], self.b["y"] + self.b["l"]) if orient == "h"
                  else (self.b["x"], self.b["x"] + self.b["w"]))
        if abs(c - lo) < 1e-3:
            return lo, lo + t / 2
        if abs(c - hi) < 1e-3:
            return hi - t / 2, hi
        return c - t / 2, c + t / 2

    def strip(self, group, mat, orient, span, a, b, z0, z1, inside=INSET):
        """Khối nằm dọc tường: span là khoảng vuông góc, a..b dọc theo tường.

        Đầu khối được giữ trong ranh nhà; cấu kiện không phải tường bao lùi thêm `inside` để không lộ vệt ra mặt ngoài.
        """
        lo, hi = ((self.b["x"], self.b["x"] + self.b["w"]) if orient == "h"
                  else (self.b["y"], self.b["y"] + self.b["l"]))
        if inside is not None:
            a, b = max(a, lo + inside), min(b, hi - inside)
        if orient == "h":
            self.box(group, mat, a, span[0], z0, b, span[1], z1)
        else:
            self.box(group, mat, span[0], a, z0, span[1], b, z1)

    def rail(self, group, orient, c, a, b, z0, height=RAIL_H):
        span = self.across(orient, c, RAIL_T)
        self.strip(group, "kinh", orient, span, a, b, z0 + 0.06, z0 + height - 0.05)
        self.strip(group, "khung", orient, span, a, b, z0 + height - 0.05, z0 + height)
        self.strip(group, "khung", orient, span, a, b, z0, z0 + 0.06)

    # ---------- tường và cửa ----------
    @staticmethod
    def segments(rooms: list[dict]):
        """Đoạn tường như mặt bằng 2D, tách thêm ở chỗ đổi từ phòng kín sang sân / sân thượng."""
        open_air = {None, "san", *OUTDOOR}
        for s in wall_segments(rooms, []):
            o, c = s["orient"], s["c"]
            marks = {s["a"], s["b"]}
            for r in rooms:
                marks |= {v for v in ((r["x"], r["x"] + r["w"]) if o == "h" else (r["y"], r["y"] + r["h"]))
                          if s["a"] < v < s["b"]}
            marks, run = sorted(marks), None
            for a, b in zip(marks, marks[1:]):
                mid = (a + b) / 2
                sides = ([room_at(rooms, mid, c - 0.01), room_at(rooms, mid, c + 0.01)] if o == "h"
                         else [room_at(rooms, c - 0.01, mid), room_at(rooms, c + 0.01, mid)])
                kinds = {r["loai"] if r else None for r in sides}
                key = frozenset(kinds) if kinds <= open_air else None
                if run and run[4] == key and abs(run[1] - a) < 1e-6:
                    run[1] = b
                    continue
                if run:
                    yield o, c, run[0], run[1], s["type"], run[3]
                run = [a, b, mid, kinds, key]
            if run:
                yield o, c, run[0], run[1], s["type"], run[3]

    def walls(self, k: int):
        fl = self.layout["floors"][str(k)]
        rooms, z0, z1 = fl["rooms"], self.lv[k - 1], self.lv[k]
        openings = [(d, True) for d in fl["doors"]] + [(w, False) for w in fl["windows"]]
        for o, c, a, b, typ, kinds in self.segments(rooms):
            if typ == "rao" or kinds == {"san", None}:
                self.fence(o, c, a, b)
                continue
            if typ == "lan_can":
                self.rail(k, o, c, a, b, z0)
                continue
            outside = typ == "ngoai"
            t, mat = (EXT_T, "tuong_ngoai") if outside else (INT_T, "tuong_trong")
            top = z1 if outside else z1 - SLAB
            if k == self.n and None in kinds and kinds <= {None, "san_phoi", "ban_cong"}:
                top = z0 + RAIL_H            # tường chắn hai bên sân thượng lộ thiên
            span = self.across(o, c, t)
            cuts = sorted((max(op["a"], a), min(op["b"], b), op, door) for op, door in openings
                          if op["orient"] == o and abs(op["c"] - c) < 1e-3
                          and min(op["b"], b) - max(op["a"], a) > 1e-3) if openings else []
            at, start = a, True
            inside = 0.0 if outside else 0.05
            for p, q, op, door in cuts:
                self.strip(k, mat, o, span, at - (t / 2 if start else 0), p, z0, top, inside)
                sill, head = self.opening_heights(op, door)
                head = min(head, top - z0 - 0.05)
                self.strip(k, mat, o, span, p, q, z0, z0 + sill, inside)
                front_door = (door and k == 1 and op["loai"] in ("cuon", "chinh") and outside
                              and top - z0 - BEAM - head > 0.25)
                if front_door:               # ô thoáng kính trên cửa chính / cửa cuốn như mặt đứng
                    self.glazing(k, o, span, p, q, z0 + head + 0.05, top - BEAM, panes=3)
                    self.strip(k, mat, o, span, p, q, z0 + head, z0 + head + 0.05, inside)
                    self.strip(k, mat, o, span, p, q, top - BEAM, top, inside)
                else:
                    self.strip(k, mat, o, span, p, q, z0 + head, top, inside)
                if a - 1e-3 <= (op["a"] + op["b"]) / 2 <= b + 1e-3:
                    if door:
                        self.door(k, o, span, op, z0, z0 + head)
                    else:
                        self.glazing(k, o, span, p, q, z0 + sill, z0 + head, panes=2)
                at, start = q, False
            self.strip(k, mat, o, span, at - (t / 2 if start else 0), b + t / 2, z0, top, inside)

    @staticmethod
    def opening_heights(op: dict, door: bool) -> tuple[float, float]:
        return (0.0, DOOR_SIZE.get(op["loai"], (None, 2.2))[1]) if door else (SILL, HEAD)

    def glazing(self, k, o, span, a, b, z0, z1, panes=2):
        m, f = sum(span) / 2, 0.05
        frame, glass = (m - 0.04, m + 0.04), (m - 0.01, m + 0.01)
        self.strip(k, "khung", o, frame, a, b, z0, z0 + f)
        self.strip(k, "khung", o, frame, a, b, z1 - f, z1)
        for i in range(panes + 1):
            u = a + (b - a - f) * i / panes
            self.strip(k, "khung", o, frame, u, u + f, z0 + f, z1 - f)
        self.strip(k, "kinh", o, glass, a + f, b - f, z0 + f, z1 - f)

    def door(self, k, o, span, op, z0, z1):
        a, b, m, kind = op["a"], op["b"], sum(span) / 2, op["loai"]
        if kind == "cuon":
            self.strip(k, "cua_cuon", o, (m - 0.03, m + 0.03), a, b, z0, z1)
            steps = int((z1 - z0) / 0.2)
            for i in range(1, steps):
                self.strip(k, "khung", o, (m - 0.036, m + 0.036), a, b, z0 + i * 0.2 - 0.008, z0 + i * 0.2 + 0.008)
        elif kind in ("kinh", "di_nhom"):
            self.glazing(k, o, span, a, b, z0, z1, panes=4 if kind == "kinh" else 1)
        else:
            f = 0.05
            for u0, u1 in ((a, a + f), (b - f, b)):
                self.strip(k, "khung", o, span, u0, u1, z0, z1)
            self.strip(k, "khung", o, span, a + f, b - f, z1 - f, z1)
            leaves = 2 if kind == "chinh" else 1
            width = (b - a - 2 * f) / leaves
            for i in range(leaves):
                u = a + f + i * width
                self.strip(k, "cua_go", o, (m - 0.02, m + 0.02), u + 0.004, u + width - 0.004, z0 + 0.01, z1 - f)

    def fence(self, o, c, a, b):
        front = (c if o == "h" else (a + b) / 2) < self.b["y"]
        lot = self.layout["lot"]
        span = (c, c + 0.1) if c < 1e-3 else (c - 0.1, c) if abs(c - (lot["w"] if o == "v" else lot["l"])) < 1e-3 \
            else (c - 0.05, c + 0.05)
        if front and o == "h":               # rào cổng thưa phía đường
            self.strip(0, "khung", o, span, a, b, YARD_Z + 1.35, YARD_Z + 1.4, None)
            self.strip(0, "khung", o, span, a, b, YARD_Z + 0.1, YARD_Z + 0.15, None)
            m, count = sum(span) / 2, max(2, int((b - a) / 0.18))
            for i in range(count + 1):
                u = a + (b - a - 0.03) * i / count
                self.strip(0, "khung", o, (m - 0.015, m + 0.015), u, u + 0.03, YARD_Z, YARD_Z + 1.4, None)
        else:
            self.strip(0, "tuong_ngoai", o, span, a, b, YARD_Z, YARD_Z + (1.2 if front else 1.8), None)

    # ---------- sàn, thang, mái ----------
    def slabs(self, k: int):
        z, b = self.lv[k - 1], self.b
        core, st = self.layout["core"], self.layout["stair"]
        for r in self.layout["floors"][str(k)]["rooms"]:
            x0, y0, x1, y1 = r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]
            kind = r["loai"]
            if kind == "san":
                self.box(0, "san_vuon", x0, y0, YARD_Z - 0.1, x1, y1, YARD_Z)
                continue
            if kind == "gieng_troi" and k > 1:
                continue
            if kind == "thang" and k > 1:    # chỉ còn chiếu tới, phần còn lại là ô thang
                y1 = core["y"] + st["chieu_nghi"]
            # mép sàn lùi vào trong tường bao để không trùng mặt
            x0, x1 = max(x0, b["x"] + 0.02), min(x1, b["x"] + b["w"] - 0.02)
            if kind not in OUTDOOR:
                y0, y1 = max(y0, b["y"] + 0.02), min(y1, b["y"] + b["l"] - 0.02)
            mat = "san_vuon" if kind == "gieng_troi" else FLOOR_MATERIAL.get(kind, "san_gach")
            self.box(k, mat, x0, y0, z - SLAB, x1, y1, z)

    def beams(self):
        b = self.b
        for i in range(1, self.n + 1):
            first = room_at(self.layout["floors"][str(i)]["rooms"], b["x"] + b["w"] / 2, b["y"] + 0.05)
            if i == self.n and (first is None or first["loai"] in OUTDOOR):
                continue
            self.box(i, "dam", b["x"] + INSET, b["y"] - 0.04, self.lv[i] - BEAM, b["x"] + b["w"] - INSET, b["y"] + 0.1,
                     self.lv[i] + 0.01)

    def stair(self, k: int):
        core, st = self.layout["core"], self.layout["stair"]
        info = st["cac_tang"][min(k, len(st["cac_tang"])) - 1]
        x0, sw, fw = core["stair_x"], st["rong"], st["ve_rong"]
        ys, yend = core["y"] + st["chieu_nghi"], core["y"] + core["l"]
        tread = info["bac_rong"]
        rise = self.layout["heights"][k - 1] / (info["bac_ve_1"] + info["bac_ve_2"])
        n1, n2, z = info["bac_ve_1"] - 1, info["bac_ve_2"] - 1, self.lv[k - 1]
        xa, xb = (x0 + sw - fw, x0 + sw), (x0, x0 + fw)
        landing = z + info["bac_ve_1"] * rise
        for i in range(n1):
            top = z + (i + 1) * rise
            self.box(k, "thang", xa[0], ys + i * tread, max(z, top - 0.28), xa[1], ys + (i + 1) * tread, top)
        for j in range(n2):
            top = landing + (j + 1) * rise
            self.box(k, "thang", xb[0], ys + (n2 - j - 1) * tread, top - 0.28, xb[1], ys + (n2 - j) * tread, top)
        mid = ys + max(n1, n2) * tread
        self.box(k, "thang", x0, mid, landing - 0.12, x0 + sw, yend, landing)
        self.box(k, "thang", xa[0], ys + n1 * tread, landing - 0.12, xa[1], mid, landing)
        self.box(k, "thang", xb[0], ys + n2 * tread, landing - 0.12, xb[1], mid, landing)

    def stair_guard(self, k: int):
        """Lan can dọc mép ô thang phía sảnh."""
        core, st = self.layout["core"], self.layout["stair"]
        x = core["stair_x"] + st["rong"]
        hall = room_at(self.layout["floors"][str(k)]["rooms"], x + 0.05, core["y"] + core["l"] / 2)
        if hall and hall["loai"] == "hanh_lang":
            self.rail(k, "v", x, core["y"] + st["chieu_nghi"], core["y"] + core["l"] - 0.06, self.lv[k - 1], 1.0)

    def roof(self):
        z, g = self.lv[-1], self.n + 1
        covered = [r for r in self.layout["floors"][str(self.n)]["rooms"] if r["loai"] not in (*OUTDOOR, "san")]
        for r in covered:
            x0, y0, x1, y1 = r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"]
            if r["loai"] != "gieng_troi":
                self.box(g, "mai", max(x0, self.b["x"] + 0.02), max(y0, self.b["y"] + 0.02), z - SLAB,
                         min(x1, self.b["x"] + self.b["w"] - 0.02), min(y1, self.b["y"] + self.b["l"] - 0.02), z + 0.02)
                continue
            for o, c, a, b in (("h", y0, x0, x1), ("h", y1, x0, x1), ("v", x0, y0, y1), ("v", x1, y0, y1)):
                self.strip(g, "tuong_ngoai", o, (c - 0.05, c + 0.05) if c > self.b["x"] + 1e-3 or o == "h" else (c, c + 0.1),
                           a, b, z, z + 0.55, 0.0)
            self.box(g, "kinh", x0, y0, z + 0.56, x1, y1, z + 0.6)
            count = max(1, int((y1 - y0) / 0.6))
            for i in range(count + 1):       # lam nhôm che nắng
                y = y0 + (y1 - y0 - 0.05) * i / count
                self.box(g, "khung", x0, y, z + 0.6, x1, y + 0.05, z + 0.66)
        outline = wall_segments([{**r, "loai": "mai"} for r in covered], [])
        for s in outline:
            if s["type"] == "ngoai":
                span = self.across(s["orient"], s["c"], EXT_T)
                self.strip(g, "tuong_ngoai", s["orient"], span, s["a"] - EXT_T / 2, s["b"] + EXT_T / 2, z, z + PARAPET, 0.0)

    def furniture(self, k: int):
        z = self.lv[k - 1]
        for r in self.layout["floors"][str(k)]["rooms"]:
            record = _Footprints()
            draw_furniture(record, _Identity, r, self.b["w"])
            for i, (x0, y0, x1, y1) in enumerate(record.rects):
                x0, x1 = max(x0, r["x"], self.b["x"] + EXT_T / 2), min(x1, r["x"] + r["w"], self.b["x"] + self.b["w"] - EXT_T / 2)
                y0, y1 = max(y0, r["y"] + EXT_T / 2), min(y1, r["y"] + r["h"] - EXT_T / 2)
                self.box(k, "noi_that", x0, y0, z, x1, y1, z + _furniture_height(r["loai"], i))

    def site(self):
        lot, b = self.layout["lot"], self.b
        for y0, y1 in ((0, b["y"]), (b["y"] + b["l"], lot["l"])):   # nền sân trước và sân sau
            self.box(0, "nen", 0, y0, ROAD_Z, lot["w"], y1, YARD_Z - 0.1)
        self.box(0, "nen", -1.5, -2.0, ROAD_Z - 0.1, lot["w"] + 1.5, 0, ROAD_Z)
        x0, y0, x1, y1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["l"]
        for rect in ((x0, y0, x1, y0 + INSET), (x0, y1 - INSET, x1, y1), (x0, y0, x0 + INSET, y1), (x1 - INSET, y0, x1, y1)):
            self.box(0, "tuong_ngoai", *rect[:2], ROAD_Z, *rect[2:], 0)      # mặt bệ nhà, vừa khít mép sàn tầng 1

    def build(self) -> list[Box]:
        self.site()
        for k in range(1, self.n + 1):
            self.slabs(k)
            self.walls(k)
            self.furniture(k)
            if k < self.n:
                self.stair(k)
            if k > 1:
                self.stair_guard(k)
        self.beams()
        self.roof()
        return self.boxes


def build_boxes(layout: dict) -> list[Box]:
    return _Builder(layout).build()


# ---------------------------------------------------------------------------
# Xuất tệp
# ---------------------------------------------------------------------------
# mỗi mặt: 4 đỉnh (chỉ số 0/1 theo x, y, z), thứ tự ngược chiều kim đồng hồ nhìn từ ngoài
FACES = (
    ((1, 0, 0), ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))),
    ((-1, 0, 0), ((0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1))),
    ((0, 1, 0), ((1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1))),
    ((0, -1, 0), ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))),
    ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))),
    ((0, 0, -1), ((0, 1, 0), (1, 1, 0), (1, 0, 0), (0, 0, 0))),
)


def box_quads(boxes: list[Box]) -> tuple[np.ndarray, np.ndarray]:
    """(N·6, 4, 3) đỉnh và (N·6, 3) pháp tuyến."""
    lo = np.array([b[2:5] for b in boxes], float)
    hi = np.array([b[5:8] for b in boxes], float)
    pick = np.array([f[1] for f in FACES], float)                     # 6,4,3
    quads = lo[:, None, None, :] + pick[None] * (hi - lo)[:, None, None, :]
    normals = np.broadcast_to(np.array([f[0] for f in FACES], float), (len(boxes), 6, 3))
    return quads.reshape(-1, 4, 3), normals.reshape(-1, 3)


def _grouped(boxes: list[Box]) -> dict[int, dict[str, list[Box]]]:
    groups: dict[int, dict[str, list[Box]]] = {}
    for b in boxes:
        groups.setdefault(b.group, {}).setdefault(b.mat, []).append(b)
    return {g: {m: groups[g][m] for m in MATERIALS if m in groups[g]} for g in sorted(groups)}


def rgb(name: str) -> tuple[float, float, float]:
    value = MATERIALS[name][1]
    return tuple(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _linear(c: float) -> float:
    return round(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 5)


def glb_bytes(layout: dict, program: dict) -> bytes:
    floors = layout["so_tang"]
    used = list(MATERIALS)
    materials = []
    for name in used:
        _, _, alpha, rough, metal = MATERIALS[name]
        item = {"name": MATERIALS[name][0], "pbrMetallicRoughness": {
            "baseColorFactor": [*(_linear(c) for c in rgb(name)), alpha], "roughnessFactor": rough, "metallicFactor": metal}}
        if alpha < 1:
            item.update(alphaMode="BLEND", doubleSided=True)
        materials.append(item)
    nodes, meshes, accessors, views, chunks, offset = [], [], [], [], [], 0

    def push(data: np.ndarray, target: int) -> int:
        nonlocal offset
        raw = data.tobytes()
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(raw), "target": target})
        raw += b"\0" * (-len(raw) % 4)
        chunks.append(raw)
        offset += len(raw)
        return len(views) - 1

    roots = []
    for group, by_material in _grouped(build_boxes(layout)).items():
        primitives = []
        for name, items in by_material.items():
            quads, normals = box_quads(items)
            points = quads.reshape(-1, 3)
            pos = np.stack([points[:, 0], points[:, 2], -points[:, 1]], 1).astype("<f4")
            per_vertex = np.repeat(normals, 4, axis=0)
            nrm = np.stack([per_vertex[:, 0], per_vertex[:, 2], -per_vertex[:, 1]], 1).astype("<f4")
            base = np.arange(len(quads), dtype="<u4")[:, None] * 4
            idx = (base + np.array([0, 1, 2, 0, 2, 3], dtype="<u4")).reshape(-1).astype("<u4")
            first = len(accessors)
            accessors.append({"bufferView": push(pos, 34962), "componentType": 5126, "count": len(pos), "type": "VEC3",
                              "min": [float(v) for v in pos.min(0)], "max": [float(v) for v in pos.max(0)]})
            accessors.append({"bufferView": push(nrm, 34962), "componentType": 5126, "count": len(nrm), "type": "VEC3"})
            accessors.append({"bufferView": push(idx, 34963), "componentType": 5125, "count": len(idx), "type": "SCALAR"})
            primitives.append({"attributes": {"POSITION": first, "NORMAL": first + 1}, "indices": first + 2,
                               "material": used.index(name)})
        meshes.append({"name": group_name(group, floors), "primitives": primitives})
        nodes.append({"name": group_name(group, floors), "mesh": len(meshes) - 1, "extras": {"group": group}})
        roots.append(len(nodes) - 1)
    nodes.append({"name": "Ngôi nhà", "children": roots})
    doc = {"asset": {"version": "2.0", "generator": "AI Architect Studio",
                     "extras": {"AI_ARCHITECT_OPTION": option_stamp(program), "so_tang": floors}},
           "scene": 0, "scenes": [{"nodes": [len(nodes) - 1]}], "nodes": nodes, "meshes": meshes, "materials": materials,
           "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": offset}]}
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    blob = b"".join(chunks)
    return (struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(text) + 8 + len(blob))
            + struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(blob), 0x004E4942) + blob)


def glb_header(data: bytes) -> dict:
    magic, version, length = struct.unpack_from("<III", data)
    size, kind = struct.unpack_from("<II", data, 12)
    if magic != 0x46546C67 or version != 2 or length != len(data) or kind != 0x4E4F534A:
        raise ValueError("Tệp GLB không hợp lệ")
    return json.loads(data[20:20 + size])


def write_dxf3d(layout: dict, program: dict, path: Path) -> None:
    """DXF 3D (mm) cho AutoCAD: mỗi lớp là một tầng + vật liệu."""
    import ezdxf
    from ezdxf import colors
    from ezdxf.render import MeshBuilder

    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    if option_stamp(program):
        doc.ezdxf_metadata()["AI_ARCHITECT_OPTION"] = option_stamp(program)
    msp = doc.modelspace()
    for group, by_material in _grouped(build_boxes(layout)).items():
        for name, items in by_material.items():
            layer = dxf_layer(group, name, layout["so_tang"])
            entry = doc.layers.add(layer)
            entry.rgb = tuple(round(c * 255) for c in rgb(name))
            if name in TRANSPARENT:
                entry.transparency = 1 - MATERIALS[name][2]
            quads, _ = box_quads(items)
            mesh = MeshBuilder()
            for box in quads.reshape(-1, 6, 4, 3) * 1000:
                corners = {}
                faces = []
                for quad in box:
                    face = []
                    for point in quad:
                        key = tuple(round(float(v), 3) for v in point)
                        face.append(corners.setdefault(key, len(corners)))
                    faces.append(face)
                mesh.add_mesh(vertices=list(corners), faces=faces)
            mesh.render_mesh(msp, dxfattribs={"layer": layer, "color": colors.BYLAYER})
    doc.saveas(path)


def dxf_layer(group: int, material: str, floors: int) -> str:
    prefix = "KHU_DAT" if group == 0 else "MAI" if group > floors else f"TANG_{group}"
    return f"{prefix}_{material.upper()}"


def dxf_matches(path, layout: dict, program: dict) -> bool:
    """Đọc lại DXF 3D: mã phương án, lớp theo tầng, kích thước và số khối phải khớp mô hình dựng từ mặt bằng."""
    import ezdxf

    doc = ezdxf.readfile(path)
    stamp = option_stamp(program)
    if stamp and doc.ezdxf_metadata().get("AI_ARCHITECT_OPTION") != stamp:
        return False
    expected = {dxf_layer(g, m, layout["so_tang"]): items
                for g, by_material in _grouped(build_boxes(layout)).items() for m, items in by_material.items()}
    found = {e.dxf.layer: e for e in doc.modelspace().query("MESH")}
    if set(found) != set(expected):
        return False
    for layer, items in expected.items():
        points = np.array([tuple(v) for v in found[layer].vertices], float)
        lo = np.array([b[2:5] for b in items]).min(0) * 1000
        hi = np.array([b[5:8] for b in items]).max(0) * 1000
        if len(found[layer].faces) != 6 * len(items) or not (
                np.allclose(points.min(0), lo, atol=0.5) and np.allclose(points.max(0), hi, atol=0.5)):
            return False
    return True


def export_model(layout: dict, program: dict, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    glb, dxf = out_dir / "mo_hinh_3d.glb", out_dir / "mo_hinh_3d.dxf"
    glb.write_bytes(glb_bytes(layout, program))
    write_dxf3d(layout, program, dxf)
    return {"glb": str(glb), "dxf_3d": str(dxf)}
