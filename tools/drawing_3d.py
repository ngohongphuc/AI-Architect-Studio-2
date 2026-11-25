"""Các tờ bản vẽ 3D: phối cảnh mặt tiền, trục đo tổng thể, trục đo tách tầng.

Kết xuất bằng bộ đệm độ sâu viết bằng numpy (không cần GPU hay dịch vụ ngoài). Mỗi tờ có ảnh nền tô bóng (PDF/PNG)
và nét vẽ đã khử khuất dạng vector (PDF, PNG và DXF).
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from tools.model3d import FACES, TRANSPARENT, Box, box_quads, build_boxes, rgb
from tools.sheet import DRAW_AREA, Sheet

PIXELS = 1700                    # cạnh dài của ảnh kết xuất
CUT = 1.35                       # cao độ cắt của tờ tách tầng
LIGHT = np.array([0.36, -0.78, 1.05])
AMBIENT, DIFFUSE = 0.58, 0.46


class Camera(NamedTuple):
    eye: np.ndarray
    right: np.ndarray
    up: np.ndarray
    forward: np.ndarray
    perspective: bool

    def project(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(u, v) chưa tỉ lệ và độ sâu dọc hướng nhìn."""
        rel = points - self.eye
        depth = rel @ self.forward
        uv = np.stack([rel @ self.right, rel @ self.up], -1)
        return (uv / depth[..., None] if self.perspective else uv), depth


def axonometric(azimuth: float, elevation: float) -> Camera:
    """Nhìn từ phía trước nhà, lệch `azimuth` độ sang phải, cao `elevation` độ."""
    a, e = np.radians([azimuth, elevation])
    forward = np.array([-np.sin(a) * np.cos(e), np.cos(a) * np.cos(e), -np.sin(e)])
    right = np.array([np.cos(a), np.sin(a), 0.0])
    return Camera(np.zeros(3), right, np.cross(right, forward), forward, False)


def street_view(layout: dict) -> Camera:
    """Phối cảnh hai điểm tụ từ vỉa hè đối diện (trục nhìn nằm ngang nên cạnh đứng không bị nghiêng)."""
    b, height = layout["building"], sum(layout["heights"])
    eye = np.array([b["x"] + b["w"] * 1.15 + 4.0, b["y"] - max(9.0, height * 1.05), max(1.7, height * 0.42)])
    look = np.array([b["x"] + b["w"] * 0.5, b["y"] + 2.0, eye[2]]) - eye
    forward = look / np.linalg.norm(look)
    right = np.array([forward[1], -forward[0], 0.0])
    return Camera(eye, right, np.array([0.0, 0.0, 1.0]), forward, True)


class _Raster:
    """Bộ đệm độ sâu cho các mặt phẳng lồi; giá trị lưu `w` càng lớn càng gần và tuyến tính trên màn hình."""

    def __init__(self, width: int, height: int):
        self.w = np.full((height, width), -np.inf)
        self.face = np.full((height, width), -1, np.int32)

    def draw(self, screen: np.ndarray, w: np.ndarray, ids) -> None:
        for quad, depth, ident in zip(screen, w, ids):
            patch = self._cover(quad, depth)
            if patch is None:
                continue
            area, inside, values = patch
            closer = inside & (values > self.w[area])
            self.w[area][closer] = values[closer]
            self.face[area][closer] = ident

    def _cover(self, quad, depth):
        height, width = self.w.shape
        x0, y0 = np.maximum(np.floor(quad.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(quad.max(0)).astype(int), (width - 1, height - 1))
        if x1 < x0 or y1 < y0:
            return None
        base = np.array([quad[1] - quad[0], quad[2] - quad[0]])
        det = base[0, 0] * base[1, 1] - base[0, 1] * base[1, 0]
        if abs(det) < 1e-6:
            return None
        xs = np.arange(x0, x1 + 1) + 0.5
        ys = (np.arange(y0, y1 + 1) + 0.5)[:, None]
        inside = np.ones((len(ys), len(xs)), bool)
        sign = 1.0 if det > 0 else -1.0
        for p, q in zip(quad, np.roll(quad, -1, axis=0)):
            inside &= sign * ((q[0] - p[0]) * (ys - p[1]) - (q[1] - p[1]) * (xs - p[0])) >= -1e-9
        if not inside.any():
            return None
        d1, d2 = depth[1] - depth[0], depth[2] - depth[0]
        gx = (d1 * base[1, 1] - d2 * base[0, 1]) / det
        gy = (d2 * base[0, 0] - d1 * base[1, 0]) / det
        values = depth[0] + gx * (xs - quad[0, 0]) + gy * (ys - quad[0, 1])
        return (slice(y0, y1 + 1), slice(x0, x1 + 1)), inside, values


def _w(camera: Camera, depth: np.ndarray) -> np.ndarray:
    return 1.0 / depth if camera.perspective else -depth


def render(boxes: list[Box], camera: Camera, *, shadows: bool = True) -> dict:
    """Ảnh RGB, nét khuất đã loại bỏ và phép đổi điểm 3D → đơn vị ảnh (mét trên tờ vẽ, gốc góc dưới trái)."""
    quads, normals = box_quads(boxes)
    mats = np.repeat([b.mat for b in boxes], 6)
    clear = np.isin(mats, list(TRANSPARENT))
    uv, depth = camera.project(quads)
    lo, hi = uv.reshape(-1, 2).min(0), uv.reshape(-1, 2).max(0)
    size = hi - lo
    scale = PIXELS / size.max()
    width, height = (int(np.ceil(v)) + 8 for v in size * scale)

    def to_screen(points_uv):
        s = (points_uv - lo) * scale + 4
        return np.stack([s[..., 0], height - s[..., 1]], -1)

    # bỏ mặt quay lưng
    view = (camera.eye - quads.mean(1)) if camera.perspective else np.broadcast_to(-camera.forward, normals.shape)
    facing = (view * normals).sum(1) > 1e-9
    screen, w = to_screen(uv), _w(camera, depth)
    raster = _Raster(width, height)
    solid = np.flatnonzero(facing & ~clear)
    raster.draw(screen[solid], w[solid], solid)

    image = np.ones((height, width, 3))
    hit = raster.face >= 0
    faces = raster.face[hit]
    light = LIGHT / np.linalg.norm(LIGHT)
    lambert = np.clip(normals[faces] @ light, 0, 1)
    rows, cols = np.nonzero(hit)
    if shadows:
        world = _unproject(camera, rows, cols, raster.w[hit], lo, scale, height)
        lambert = lambert * _lit(quads[~clear], normals[~clear], world, normals[faces], light)
    palette = np.array([rgb(m) for m in mats])
    image[hit] = palette[faces] * np.minimum(AMBIENT + DIFFUSE * lambert + 0.04 * (normals[faces][:, 2] > 0), 1.08)[:, None]

    # kính: hòa màu phía trước mặt đặc, từ xa đến gần
    panes = np.flatnonzero(facing & clear)
    for i in panes[np.argsort(w[panes].mean(1))]:
        patch = raster._cover(screen[i], w[i])
        if patch:
            area, inside, values = patch
            front = inside & (values > raster.w[area])
            image[area][front] = image[area][front] * 0.62 + palette[i] * 0.38

    def place(points: np.ndarray) -> np.ndarray:
        s = to_screen(camera.project(np.atleast_2d(points))[0])
        return np.stack([s[:, 0], height - s[:, 1]], 1)

    planes = _plane_ids(quads, normals, mats)
    lines = _visible_edges(boxes, camera, to_screen, raster, planes, height)
    return {"image": (np.clip(image, 0, 1) * 255).astype(np.uint8), "size": (width, height), "lines": lines, "place": place}


def _unproject(camera, rows, cols, w, lo, scale, height):
    u = (cols + 0.5 - 4) / scale + lo[0]
    v = (height - rows - 0.5 - 4) / scale + lo[1]
    z = 1.0 / w if camera.perspective else -w
    side = np.outer(u, camera.right) + np.outer(v, camera.up)
    return camera.eye + (side * z[:, None] if camera.perspective else side) + np.outer(z, camera.forward)


def _lit(quads, normals, world, surface, light) -> np.ndarray:
    """1 nơi có nắng, 0 nơi bị đổ bóng (bản đồ bóng trực giao theo hướng nắng)."""
    forward = -light
    right = np.cross(forward, (0.0, 0.0, 1.0))
    right /= np.linalg.norm(right)
    sun = Camera(np.zeros(3), right, np.cross(right, forward), forward, False)
    uv, depth = sun.project(quads)
    lo, hi = uv.reshape(-1, 2).min(0), uv.reshape(-1, 2).max(0)
    scale = 1300 / (hi - lo).max()
    width, height = (int(np.ceil(v)) + 4 for v in (hi - lo) * scale)
    raster = _Raster(width, height)
    keep = normals @ light > 1e-6
    raster.draw(((uv - lo) * scale + 2)[keep], -depth[keep], np.flatnonzero(keep))
    point_uv, point_depth = sun.project(world + surface * 0.03)
    s = ((point_uv - lo) * scale + 2).astype(int)
    total = np.zeros(len(world))
    offsets = ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))
    for dx, dy in offsets:
        x, y = np.clip(s[:, 0] + dx, 0, width - 1), np.clip(s[:, 1] + dy, 0, height - 1)
        total += -point_depth + 0.05 >= raster.w[y, x]
    return total / len(offsets)


def _plane_ids(quads, normals, mats) -> np.ndarray:
    """Các mặt đồng phẳng, cùng hướng, cùng vật liệu chung một mã (để bỏ vết nối giữa các khối)."""
    axis = np.abs(normals).argmax(1)
    coord = np.round(quads[np.arange(len(quads)), 0, axis], 3)
    keys = zip(axis.tolist(), normals.sum(1).tolist(), coord.tolist(), mats.tolist())
    seen: dict = {}
    return np.array([seen.setdefault(key, len(seen)) for key in keys])


EDGES = sorted({tuple(sorted((a, b))) for _, f in FACES for a, b in zip(f, f[1:] + f[:1])})


def _visible_edges(boxes, camera, to_screen, raster, planes, height) -> list:
    solid = [b for b in boxes if b.mat not in TRANSPARENT]
    lo = np.array([b[2:5] for b in solid], float)
    hi = np.array([b[5:8] for b in solid], float)
    ends = np.array(EDGES, float)                                        # 12,2,3
    pts = (lo[:, None, None] + ends[None] * (hi - lo)[:, None, None]).reshape(-1, 2, 3)
    pts = np.unique(np.round(pts, 4), axis=0)                            # cạnh trùng nhau chỉ xét một lần
    uv, depth = camera.project(pts)
    screen, w = to_screen(uv), _w(camera, depth)
    length = np.linalg.norm(screen[:, 1] - screen[:, 0], axis=1)
    keep = length > 2.5
    screen, w, length = screen[keep], w[keep], length[keep]
    counts = np.maximum(2, np.ceil(length / 2).astype(int) + 1)
    edge = np.repeat(np.arange(len(counts)), counts)
    start = np.concatenate([[0], np.cumsum(counts)[:-1]])
    t = (np.arange(counts.sum()) - start[edge]) / (counts[edge] - 1)
    p = screen[edge, 0] + (screen[edge, 1] - screen[edge, 0]) * t[:, None]
    ws = w[edge, 0] + (w[edge, 1] - w[edge, 0]) * t
    direction = (screen[:, 1] - screen[:, 0]) / length[:, None]
    across = np.stack([-direction[:, 1], direction[:, 0]], 1)[edge]

    def sample(buffer, q):
        x = np.clip(q[:, 0].astype(int), 0, buffer.shape[1] - 1)
        y = np.clip(q[:, 1].astype(int), 0, buffer.shape[0] - 1)
        return buffer[y, x]

    nearest = np.min([sample(raster.w, p + np.array(o)) for o in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))], axis=0)
    with np.errstate(divide="ignore"):
        z_edge = 1 / ws if camera.perspective else -ws
        z_seen = np.where(np.isneginf(nearest), np.inf,
                          1 / np.where(nearest == 0, 1e-12, nearest) if camera.perspective else -nearest)
    visible = z_edge <= z_seen + 0.04
    face_a, face_b = sample(raster.face, p + across * 2.2), sample(raster.face, p - across * 2.2)
    plane = np.append(planes, -1)
    visible &= plane[face_a] != plane[face_b]

    lines = []
    for i in np.unique(edge[visible]):
        run = visible[start[i]:start[i] + counts[i]]
        jumps = np.flatnonzero(np.diff(np.concatenate([[0], run.astype(np.int8), [0]])))
        for first, last in zip(jumps[::2], jumps[1::2] - 1):
            if last - first >= 2:
                a, b = p[start[i] + first], p[start[i] + last]
                lines.append(((a[0], height - a[1]), (b[0], height - b[1])))
    return lines


# ---------------------------------------------------------------------------
# Tờ bản vẽ
# ---------------------------------------------------------------------------
def _place(sheet: Sheet, shot: dict, margin: float = 0.96):
    """Đặt kết quả kết xuất vừa vùng vẽ; trả về hàm đổi điểm 3D sang tọa độ tờ vẽ."""
    sheet.scale = 100
    area = ((DRAW_AREA[2] - DRAW_AREA[0]) * sheet.scale / 1000, (DRAW_AREA[3] - DRAW_AREA[1]) * sheet.scale / 1000)
    width, height = shot["size"]
    k = min(area[0] / width, area[1] / height) * margin
    sheet.image(shot["image"], (0, 0, width * k, height * k))
    sheet.lines([((a[0] * k, a[1] * k), (b[0] * k, b[1] * k)) for a, b in shot["lines"]], "PHOI_CANH")
    return lambda point: tuple(shot["place"](np.array(point, float))[0] * k)


def draw_perspective(sheet: Sheet, layout: dict) -> None:
    _place(sheet, render(build_boxes(layout), street_view(layout)))


def draw_axonometric(sheet: Sheet, layout: dict) -> None:
    _place(sheet, render(build_boxes(layout), axonometric(38, 32)))


def floor_cutaways(layout: dict) -> tuple[list[Box], dict[int, tuple[float, float]]]:
    """Mỗi tầng cắt ngang ở cao độ CUT, xếp cạnh nhau theo phương ngang."""
    b, boxes, offsets = layout["building"], [], {}
    z = 0.0
    floors = layout["so_tang"]
    model = build_boxes(layout)
    for k in range(1, floors + 1):
        dx = (k - 1) * (b["w"] + max(3.0, b["w"] * 0.55))
        offsets[k] = (dx, z)
        for box in model:
            if box.group == k and box.z0 - z < CUT - 1e-3 and box.mat != "dam":
                limit = CUT if box.mat == "tuong_ngoai" else CUT - 0.006     # tránh hai mặt cắt trùng cao độ
                boxes.append(box._replace(x0=box.x0 + dx, x1=box.x1 + dx, z0=box.z0 - z, z1=min(box.z1 - z, limit)))
        z += layout["heights"][k - 1]
    return boxes, offsets


def draw_floor_stack(sheet: Sheet, layout: dict) -> None:
    boxes, offsets = floor_cutaways(layout)
    place = _place(sheet, render(boxes, axonometric(-24, 52), shadows=False))
    b = layout["building"]
    for k, (dx, _) in offsets.items():
        x, y = place((b["x"] + b["w"] / 2 + dx, b["y"] - 1.4, 0))
        sheet.text((x, y), f"TẦNG {k}", "CHU", h=3.2, bold=True)
        for room in layout["floors"][str(k)]["rooms"]:
            if room["loai"] in ("hanh_lang", "thang", "san"):
                continue
            center = (room["x"] + room["w"] / 2 + dx, room["y"] + room["h"] / 2, 0.02)
            sheet.text(place(center), room["ten"], "CHU", h=1.5, bold=True)
