"""Tờ bản vẽ trung gian: các agent vẽ một lần, xuất ra cả Matplotlib (PDF/PNG) và ezdxf (DXF).

- Đối tượng "model" có tọa độ theo mét trong hệ tọa độ bản vẽ (đã xoay nếu cần).
- Đối tượng "paper" có tọa độ theo mm trên khổ giấy A3 (khung, khung tên, bảng).
- Kích thước chữ luôn tính theo mm trên giấy.
"""
from __future__ import annotations

import math

PAPER = (420.0, 297.0)                    # A3 ngang
FRAME = (20.0, 10.0, 410.0, 287.0)        # khung bản vẽ
DRAW_AREA = (28.0, 58.0, 402.0, 280.0)    # vùng đặt hình vẽ
STD_SCALES = [20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 500, 1000]

# layer: (màu ACI cho DXF, nét mm, màu matplotlib)
LAYERS = {
    "TUONG": (7, 0.50, "#111111"),
    "TUONG_FILL": (8, 0.00, "#4a4a4a"),
    "CUA": (4, 0.18, "#1f5fa8"),
    "CUA_SO": (5, 0.18, "#1f5fa8"),
    "LAN_CAN": (2, 0.18, "#5a5a5a"),
    "THANG": (6, 0.18, "#333333"),
    "GIENG_TROI": (140, 0.13, "#3d8bbf"),
    "THIET_BI": (8, 0.13, "#7a7a7a"),
    "CHU": (7, 0.18, "#111111"),
    "CHU_PHONG": (7, 0.18, "#111111"),
    "KICH_THUOC": (3, 0.13, "#2e7d32"),
    "TRUC": (1, 0.13, "#c62828"),
    "HATCH": (8, 0.09, "#9e9e9e"),
    "SAN": (7, 0.35, "#222222"),
    "MAI": (30, 0.25, "#8d5a2b"),
    "DAT": (8, 0.35, "#5d4037"),
    "RANH_GIOI": (1, 0.35, "#c62828"),
    "PHU": (8, 0.13, "#9e9e9e"),
    "KHUNG": (7, 0.35, "#000000"),
    "KHUNG_TEN": (7, 0.25, "#000000"),
}
LINESTYLES = {"solid": "CONTINUOUS", "dashed": "DASHED", "dashdot": "DASHDOT", "center": "CENTER"}


class Sheet:
    def __init__(self, code: str, title: str, info: dict):
        self.code, self.title, self.info = code, title, info
        self.ents: list[dict] = []
        self.pents: list[dict] = []
        self.scale = 100
        self.origin = (0.0, 0.0)

    # ---------- tỉ lệ ----------
    def choose_scale(self, width_m: float, height_m: float) -> int:
        aw = DRAW_AREA[2] - DRAW_AREA[0]
        ah = DRAW_AREA[3] - DRAW_AREA[1]
        for s in STD_SCALES:
            if width_m * 1000 / s <= aw and height_m * 1000 / s <= ah:
                self.scale = s
                return s
        self.scale = STD_SCALES[-1]
        return self.scale

    def m(self, mm: float) -> float:
        """Đổi kích thước mm trên giấy sang mét trong model."""
        return mm * self.scale / 1000.0

    # ---------- thêm đối tượng ----------
    def _add(self, ent: dict, paper: bool):
        (self.pents if paper else self.ents).append(ent)

    def line(self, a, b, layer="PHU", ls="solid", paper=False, lw=None):
        self._add({"t": "pline", "pts": [tuple(a), tuple(b)], "layer": layer, "ls": ls, "closed": False,
                   "lw": lw}, paper)

    def pline(self, pts, layer="PHU", closed=False, ls="solid", width=0.0, paper=False, lw=None):
        self._add({"t": "pline", "pts": [tuple(p) for p in pts], "layer": layer, "ls": ls, "closed": closed,
                   "width": width, "lw": lw}, paper)

    def rect(self, x, y, w, h, layer="PHU", **kw):
        self.pline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], layer, closed=True, **kw)

    def fill(self, pts, layer="TUONG_FILL", color=None, paper=False):
        self._add({"t": "fill", "pts": [tuple(p) for p in pts], "layer": layer, "color": color}, paper)

    def text(self, p, s, layer="CHU", h=2.5, ha="center", va="center", rot=0.0, bold=False, paper=False):
        lines = str(s).split("\n")
        step = h * 1.55 if paper else self.m(h * 1.55)
        n = len(lines)
        # căn giữa theo chiều đứng cho cả khối chữ
        if va == "center":
            offs = [((n - 1) / 2 - i) * step for i in range(n)]
        elif va == "bottom":
            offs = [(n - 1 - i) * step for i in range(n)]
        else:
            offs = [-i * step for i in range(n)]
        ang = math.radians(rot)
        for line, off in zip(lines, offs):
            px = p[0] - off * math.sin(ang)
            py = p[1] + off * math.cos(ang)
            self._add({"t": "text", "p": (px, py), "s": line, "layer": layer, "h": h, "ha": ha, "va": va,
                       "rot": rot, "bold": bold}, paper)

    def circle(self, c, r, layer="PHU", paper=False, fill=False):
        self._add({"t": "circle", "c": tuple(c), "r": r, "layer": layer, "fill": fill}, paper)

    def arc_pts(self, c, r, a1, a2, n=16):
        return [(c[0] + r * math.cos(math.radians(a1 + (a2 - a1) * i / n)),
                 c[1] + r * math.sin(math.radians(a1 + (a2 - a1) * i / n))) for i in range(n + 1)]

    # ---------- bố cục ----------
    def bounds(self):
        xs, ys = [], []
        for e in self.ents:
            if e["t"] in ("pline", "fill"):
                for x, y in e["pts"]:
                    xs.append(x); ys.append(y)
            elif e["t"] == "circle":
                xs += [e["c"][0] - e["r"], e["c"][0] + e["r"]]; ys += [e["c"][1] - e["r"], e["c"][1] + e["r"]]
            elif e["t"] == "text":
                xs.append(e["p"][0]); ys.append(e["p"][1])
        if not xs:
            return 0, 0, 1, 1
        return min(xs), min(ys), max(xs), max(ys)

    def fit(self):
        x0, y0, x1, y1 = self.bounds()
        k = 1000.0 / self.scale
        cx = (DRAW_AREA[0] + DRAW_AREA[2]) / 2
        cy = (DRAW_AREA[1] + DRAW_AREA[3]) / 2
        self.origin = (cx - (x0 + x1) / 2 * k, cy - (y0 + y1) / 2 * k)

    def to_paper(self, p):
        k = 1000.0 / self.scale
        return (self.origin[0] + p[0] * k, self.origin[1] + p[1] * k)

    def to_dxf(self, p, paper=False):
        if paper:
            return ((p[0] - self.origin[0]) * self.scale, (p[1] - self.origin[1]) * self.scale)
        return (p[0] * 1000.0, p[1] * 1000.0)


# ---------------------------------------------------------------------------
# Xuất Matplotlib
# ---------------------------------------------------------------------------
def render_mpl(sheet: Sheet):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon

    fig = plt.figure(figsize=(PAPER[0] / 25.4, PAPER[1] / 25.4))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, PAPER[0]); ax.set_ylim(0, PAPER[1]); ax.set_aspect("equal"); ax.axis("off")
    pt = 72 / 25.4
    k = 1000.0 / sheet.scale
    mpl_ls = {"solid": "-", "dashed": (0, (6, 3)), "dashdot": (0, (8, 2, 1.5, 2)), "center": (0, (10, 2, 2, 2))}

    def draw(ents, paper):
        tp = (lambda p: p) if paper else sheet.to_paper
        for e in ents:
            color = LAYERS.get(e["layer"], LAYERS["PHU"])[2]
            if e["t"] == "fill":
                ax.add_patch(Polygon([tp(p) for p in e["pts"]], closed=True, facecolor=e.get("color") or color,
                                     edgecolor="none", zorder=2))
            elif e["t"] == "pline":
                pts = [tp(p) for p in e["pts"]]
                if e.get("closed"):
                    pts.append(pts[0])
                width = e.get("width") or 0.0
                if width and not paper:
                    lw = width * k * pt
                    cap = "butt"
                else:
                    lw = (e.get("lw") or LAYERS.get(e["layer"], LAYERS["PHU"])[1] or 0.1) * pt * 1.6
                    cap = "round"
                xs, ys = zip(*pts)
                ax.plot(xs, ys, color=color, lw=lw, ls=mpl_ls.get(e["ls"], "-"), solid_capstyle=cap,
                        zorder=3 if width else 4)
            elif e["t"] == "circle":
                r = e["r"] if paper else e["r"] * k
                ax.add_patch(Circle(tp(e["c"]), r, facecolor=color if e.get("fill") else "none",
                                    edgecolor=color, lw=0.25 * pt, zorder=5))
            elif e["t"] == "text":
                x, y = tp(e["p"])
                ax.text(x, y, e["s"], fontsize=e["h"] * pt / 0.72, ha=e["ha"],
                        va={"center": "center", "bottom": "bottom", "top": "top"}[e["va"]],
                        rotation=e["rot"], color=color, fontweight="bold" if e["bold"] else "normal",
                        zorder=6, rotation_mode="anchor")

    draw(sheet.ents, False)
    draw(sheet.pents, True)
    return fig


# ---------------------------------------------------------------------------
# Xuất DXF
# ---------------------------------------------------------------------------
def render_dxf(sheet: Sheet, path) -> None:
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2010", setup=True)
    if sheet.info.get("ma_phuong_an"):
        doc.ezdxf_metadata()["AI_ARCHITECT_OPTION"] = sheet.info["ma_phuong_an"]
    doc.units = ezdxf.units.MM
    doc.header["$LTSCALE"] = sheet.scale * 2
    if "VN" not in doc.styles:
        doc.styles.add("VN", font="arial.ttf")
    for name, (color, lw, _) in LAYERS.items():
        if name not in doc.layers:
            doc.layers.add(name, color=color, lineweight=int(lw * 100) if lw else -3)
    msp = doc.modelspace()
    align = {("left", "bottom"): "BOTTOM_LEFT", ("center", "bottom"): "BOTTOM_CENTER",
             ("right", "bottom"): "BOTTOM_RIGHT", ("left", "center"): "MIDDLE_LEFT",
             ("center", "center"): "MIDDLE_CENTER", ("right", "center"): "MIDDLE_RIGHT",
             ("left", "top"): "TOP_LEFT", ("center", "top"): "TOP_CENTER", ("right", "top"): "TOP_RIGHT"}

    def draw(ents, paper):
        for e in ents:
            attribs = {"layer": e["layer"]}
            if e["t"] == "fill":
                hatch = msp.add_hatch(color=LAYERS.get(e["layer"], LAYERS["PHU"])[0], dxfattribs=attribs)
                hatch.paths.add_polyline_path([sheet.to_dxf(p, paper) for p in e["pts"]], is_closed=True)
            elif e["t"] == "pline":
                if e.get("ls", "solid") != "solid":
                    attribs["linetype"] = LINESTYLES[e["ls"]]
                pl = msp.add_lwpolyline([sheet.to_dxf(p, paper) for p in e["pts"]], close=e.get("closed", False),
                                        dxfattribs=attribs)
                if e.get("width") and not paper:
                    pl.dxf.const_width = e["width"] * 1000
            elif e["t"] == "circle":
                r = e["r"] * sheet.scale if paper else e["r"] * 1000
                msp.add_circle(sheet.to_dxf(e["c"], paper), r, dxfattribs=attribs)
            elif e["t"] == "text":
                h = e["h"] * sheet.scale
                t = msp.add_text(e["s"], height=h, rotation=e["rot"], dxfattribs={**attribs, "style": "VN"})
                t.set_placement(sheet.to_dxf(e["p"], paper),
                                align=TextEntityAlignment[align[(e["ha"], e["va"])]])

    draw(sheet.ents, False)
    draw(sheet.pents, True)
    doc.saveas(path)
