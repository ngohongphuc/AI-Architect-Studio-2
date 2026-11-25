"""Mô hình 3D và các tờ phối cảnh phải khớp mặt bằng 2D."""
import json
from pathlib import Path

import pytest

from agents.architect import initial_program
from agents.final_reviewer import audit
from graph import run_design
from main import SAMPLE
from monitoring.releases import read_artifact
from tools.brief_parser import parse_request
from tools.design_option import option_stamp
from tools.drawing_3d import axonometric, floor_cutaways, render, street_view
from tools.drawing_set import SHEETS_3D
from tools.layout_algorithm import DOOR_SIZE, compute_layout
from tools.model3d import HEAD, build_boxes, dxf_matches, export_model, glb_bytes, glb_header

REQUESTS = json.loads(Path(__file__).with_name("test_requests.json").read_text(encoding="utf-8"))


def layouts():
    for item in REQUESTS:
        try:
            brief = parse_request(item["request"])
            program = initial_program(brief)
            yield item["id"], program, compute_layout(brief, program)
        except Exception:  # yêu cầu thiếu dữ liệu hoặc không bố trí được thuộc phạm vi của test khác
            continue


def yard_layout():
    brief = parse_request(REQUESTS[0]["request"])
    program = {**initial_program(brief), "san_truoc": 3.0, "san_sau": 2.0}
    return "san_truoc", program, compute_layout(brief, program)


LAYOUTS = [*layouts(), yard_layout()]


def test_enough_layouts():
    assert len(LAYOUTS) >= 5


@pytest.mark.parametrize(("ident", "program", "layout"), LAYOUTS, ids=[item[0] for item in LAYOUTS])
def test_model_matches_plan(ident, program, layout):
    boxes, b = build_boxes(layout), layout["building"]
    levels = [sum(layout["heights"][:k]) for k in range(layout["so_tang"] + 1)]
    for box in boxes:
        assert box.x1 > box.x0 and box.y1 > box.y0 and box.z1 > box.z0
        if box.group:   # nhà nằm trong ranh xây dựng (dầm biên nhô 4 cm ở mặt tiền)
            assert box.x0 >= b["x"] - 1e-3 and box.x1 <= b["x"] + b["w"] + 1e-3
            assert box.y0 >= b["y"] - 0.041 and box.y1 <= b["y"] + b["l"] + 1e-3
    assert {box.group for box in boxes} == set(range(layout["so_tang"] + 2))
    for k in range(1, layout["so_tang"] + 1):
        floor = [box for box in boxes if box.group == k]
        data = layout["floors"][str(k)]
        for room in data["rooms"]:   # mỗi phòng kín có sàn đúng cao độ tại tâm phòng
            if room["loai"] in ("san", "gieng_troi", "thang"):
                continue
            x, y = room["x"] + room["w"] / 2, room["y"] + room["h"] / 2
            assert any(s.mat.startswith("san_") and s.x0 < x < s.x1 and s.y0 < y < s.y1
                       and abs(s.z1 - levels[k - 1]) < 1e-3 for s in floor), (ident, k, room["ten"])
        walls = [box for box in floor if box.mat.startswith("tuong_")]
        for op, head in ([(d, DOOR_SIZE[d["loai"]][1]) for d in data["doors"]] + [(w, HEAD) for w in data["windows"]]):
            u, c, z = (op["a"] + op["b"]) / 2, op["c"], levels[k - 1] + head - 0.2   # ô cửa phải thông
            for shift in (-0.02, 0.02):
                x, y = (u, c + shift) if op["orient"] == "h" else (c + shift, u)
                assert not any(w.x0 < x < w.x1 and w.y0 < y < w.y1 and w.z0 < z < w.z1 for w in walls), (ident, k, op)
    if layout["so_tang"] > 1:   # bậc cuối của thang tới sát sàn tầng trên
        steps = [box for box in boxes if box.group == 1 and box.mat == "thang"]
        info = layout["stair"]["cac_tang"][0]
        assert max(s.z1 for s in steps) == pytest.approx(levels[1] - info["bac_cao"], abs=0.01)


def test_exports_are_deterministic_and_detect_changes(tmp_path):
    _, program, layout = LAYOUTS[0]
    files = export_model(layout, program, tmp_path)
    data = Path(files["glb"]).read_bytes()
    assert data == glb_bytes(layout, program)
    header = glb_header(data)
    names = [node["name"] for node in header["nodes"]]
    assert names[:2] == ["Khu đất", "Tầng 1"] and "Mái" in names
    top = max(a["max"][1] for a in header["accessors"] if "max" in a)
    assert top == pytest.approx(sum(layout["heights"]) + 1.0, abs=0.01)   # trục Y hướng lên, tới đỉnh tường chắn mái
    assert dxf_matches(files["dxf_3d"], layout, program)
    changed = json.loads(json.dumps(layout))
    changed["heights"][0] += 0.3
    assert glb_bytes(changed, program) != data and not dxf_matches(files["dxf_3d"], changed, program)


def test_render_produces_visible_lines():
    _, _, layout = LAYOUTS[0]
    for boxes, camera in ((build_boxes(layout), street_view(layout)), (build_boxes(layout), axonometric(38, 32)),
                          (floor_cutaways(layout)[0], axonometric(-24, 52))):
        shot = render(boxes, camera)
        assert shot["image"].shape[:2] == shot["size"][::-1]
        assert (shot["image"] < 250).any(axis=2).mean() > 0.1 and len(shot["lines"]) > 50


@pytest.fixture(scope="module")
def run():
    return run_design(SAMPLE.replace("2,5 tỷ", "8 tỷ"), persist=False)


def test_package_contains_3d(run):
    assert run["outcome"] == "done" and run["final_review"]["dat"]
    sheets = run["drawings"]["sheets"]
    assert len(sheets) == run["layout"]["so_tang"] + 4 + len(SHEETS_3D)
    assert [s["ten"] for s in sheets[-3:]] == [title for title, _ in SHEETS_3D] and not sheets[-1]["ti_le"]
    stamp = option_stamp(run["program"])
    for kind in ("mo_hinh_3d_glb", "mo_hinh_3d_dxf"):
        path = Path(run["final_files"][kind])
        assert path.parent == Path(run["final_files"]["ban_ve_pdf"]).parent
        assert read_artifact(path, kind, stamp)[0]
        assert read_artifact(path, kind, "X:v9:other") == (None, "Tệp thuộc phiên bản khác.")


def test_final_review_rejects_wrong_model(run, tmp_path):
    wrong = tmp_path / "mo_hinh_3d.glb"
    data = bytearray(Path(run["draft_files"]["mo_hinh_3d_glb"]).read_bytes())
    data[-1] ^= 1
    wrong.write_bytes(data)
    review = audit({**run, "draft_files": {**run["draft_files"], "mo_hinh_3d_glb": str(wrong)}})
    assert [(i.muc, i.target) for i in review.loi] == [("Mô hình 3D", "drafter")]
    missing = {k: v for k, v in run["draft_files"].items() if not k.startswith("mo_hinh_3d")}
    assert [i.muc for i in audit({**run, "draft_files": missing}).loi] == ["Mô hình 3D"]
