"""Test đơn vị và test tích hợp.   Chạy:  pytest -q"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.architect import apply_feedback, initial_program
from agents.reviewer import review_design
from tools.brief_parser import parse_request
from tools.cost_calc import compute_cost
from tools.fengshui import analyze, can_chi, cung_menh
from tools.layout_algorithm import build_area_table, compute_layout
from tools.rules import max_density

SAMPLE = ("Lô đất 5×20m, mặt tiền hướng Đông Nam, ở Hà Nội. Gia đình 4 người (vợ chồng sinh năm 1990 và 1992, "
          "2 con nhỏ). Cần 3 phòng ngủ, 1 phòng thờ, có gara xe máy. Ngân sách 2,5 tỷ. Phong cách hiện đại, "
          "nhiều ánh sáng tự nhiên.")
CASES = json.loads((Path(__file__).parent / "test_requests.json").read_text(encoding="utf-8"))


# ---------------- Agent 1: phân tích brief ----------------
def test_parse_sample():
    b = parse_request(SAMPLE)
    assert b["lo_dat"] == {"rong": 5.0, "dai": 20.0, "huong": "Đông Nam", "tinh": "Hà Nội", "ma_lo_dat": None}
    assert b["gia_dinh"]["nam_sinh_chu_nha"] == 1990
    assert b["yeu_cau_phong"]["phong_ngu"] == 3 and b["yeu_cau_phong"]["phong_tho"] == 1
    assert b["yeu_cau_phong"]["gara"] == "xe máy"
    assert b["ngan_sach"] == 2_500_000_000


def test_parse_missing_info_records_assumptions():
    b = parse_request("Tôi muốn xây nhà")
    assert b["lo_dat"]["rong"] == 5.0 and b["gia_dinh_bo_sung"]


@pytest.mark.parametrize("text,budget", [("ngân sách 800 triệu", 800e6), ("2 tỷ 500 triệu", 2.5e9),
                                         ("3.2 tỷ", 3.2e9)])
def test_parse_budget(text, budget):
    assert parse_request(f"đất 5x20 {text}")["ngan_sach"] == budget


# ---------------- Quy chuẩn, phong thủy ----------------
def test_density_table():
    assert max_density(80) == 1.0
    assert max_density(100) == 0.9
    assert max_density(150) == pytest.approx(0.8)
    assert max_density(2000) == 0.4


@pytest.mark.parametrize("year,sex,cung", [(1990, "nam", "Khảm"), (1990, "nữ", "Cấn"), (1992, "nữ", "Đoài"),
                                           (1992, "nam", "Cấn"), (2000, "nam", "Ly"), (2000, "nữ", "Càn"),
                                           (1986, "nam", "Khôn")])
def test_cung_menh(year, sex, cung):
    assert cung_menh(year, sex) == cung


def test_fengshui_direction():
    assert can_chi(1990) == "Canh Ngọ"
    info = analyze(1990, "nam", "Đông Nam")
    assert info["sao_huong_nha"] == "Sinh khí" and info["hop_huong"]


# ---------------- Agent 3: thuật toán bố trí ----------------
def _overlap(a, b):
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return w > 1e-6 and h > 1e-6


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_layout_geometry(case):
    brief = parse_request(case["request"])
    layout = compute_layout(brief, initial_program(brief))
    area = build_area_table(layout, brief)
    stairs = set()
    for fl in layout["floors"].values():
        rooms = [r for r in fl["rooms"] if r["loai"] != "san"]
        assert not any(_overlap(a, b) for i, a in enumerate(rooms) for b in rooms[i + 1:])
        assert sum(r["dien_tich"] for r in rooms) == pytest.approx(area["dien_tich_xay_dung"], abs=0.5)
        st = next(r for r in rooms if r["loai"] == "thang")
        stairs.add((st["x"], st["y"], st["w"], st["h"]))
        assert fl["doors"], "mỗi tầng phải có cửa đi"
    assert len(stairs) == 1, "cầu thang phải thẳng hàng giữa các tầng"


def test_stair_meets_rules():
    brief = parse_request(SAMPLE)
    layout = compute_layout(brief, initial_program(brief))
    for f in layout["stair"]["cac_tang"]:
        assert f["bac_cao"] <= 0.18 and 0.58 <= f["blondel"] <= 0.65
    assert layout["stair"]["ve_rong"] >= 0.9


# ---------------- Agent 4 + Agent 2: vòng phản hồi ----------------
def _state(request, program=None):
    brief = parse_request(request)
    program = program or initial_program(brief)
    layout = compute_layout(brief, program)
    return {"brief": brief, "program": program, "layout": layout, "area_table": build_area_table(layout, brief),
            "iteration": 0}


def test_density_reference_is_advisory():
    st = _state(SAMPLE)
    review = review_design(st)
    assert not review["dat"] and review["dat_ky_thuat"]
    assert not any(issue["ma"] == "MAT_DO" for issue in review["loi"])
    assert any(issue["ma"] == "MAT_DO" for issue in review["canh_bao"])


def test_budget_feedback_downgrades_grade():
    brief = parse_request(SAMPLE)
    program = initial_program(brief)
    p2, changes = apply_feedback(program, [{"ma": "VUOT_NGAN_SACH", "du_lieu": {"vuot_pct": 0.12}}], brief)
    assert program["cap_hoan_thien"] == "khá" and p2["cap_hoan_thien"] == "trung bình"


def test_wc_above_altar_detected():
    st = _state(SAMPLE)
    layout = st["layout"]
    # biến phòng ngủ tầng 2 thành phòng thờ, dời WC tầng 3 lên ngay phía trên nó
    tho = next(r for r in layout["floors"]["2"]["rooms"] if r["loai"] == "ngu")
    tho["loai"] = "tho"
    wc3 = next(r for r in layout["floors"]["3"]["rooms"] if r["loai"] == "wc")
    wc3["y"] = tho["y"] + 0.5
    from agents.fengshui_advisor import fengshui_checks

    suggestions = fengshui_checks(st)[2]
    assert any(i["ma"] == "WC_TREN_THO" for i in suggestions)
    assert all(i["ma"] != "WC_TREN_THO" for i in review_design(st)["loi"])
    # Kiến trúc sư xử lý: dời WC tầng 3 ra phía sau lõi thang
    fb = [i for i in suggestions if i["ma"] == "WC_TREN_THO"]
    program, _ = apply_feedback(st["program"], fb, st["brief"])
    assert next(r for r in program["tang_3"] if r["loai"] == "wc")["vi_tri"] == "sau"


# ---------------- Agent 5: chi phí + công thức Excel ----------------
def test_cost_excel_formulas_match_python(tmp_path):
    from tools.pycel_compat import ExcelCompiler

    from tools.xlsx_writer import write_cost_xlsx

    st = _state(SAMPLE)
    cost = compute_cost(st["area_table"], st["layout"], st["program"], st["brief"]["ngan_sach"])
    path = write_cost_xlsx(cost, st["area_table"], st["brief"], tmp_path / "du_toan.xlsx")
    xl = ExcelCompiler(filename=str(path))
    assert xl.evaluate("Tong_hop!B4") == pytest.approx(cost["tong_chi_phi"], abs=1)
    assert xl.evaluate("Tong_hop!B9") == pytest.approx(cost["dt_quy_doi"], abs=0.01)
    assert xl.evaluate("Tong_hop!B7") == pytest.approx(cost["vuot_pct"], abs=1e-3)


# ---------------- Tích hợp: luồng LangGraph đầy đủ ----------------
@pytest.fixture(scope="module")
def full_run():
    from graph import run_design

    return run_design(SAMPLE, persist=False)


def test_end_to_end_three_products(full_run):
    files = full_run["final_files"]
    for key in ("ban_ve_pdf", "ban_ve_dxf_zip", "thuyet_minh_docx", "du_toan_xlsx"):
        assert Path(files[key]).exists() and Path(files[key]).stat().st_size > 1000
    assert full_run["final_review"]["dat"]
    assert full_run["outcome"] == "done"
    assert full_run["review"]["chua_du_can_cu"]
    assert 0 < full_run["iteration"] <= 3
    assert full_run["cost"]["vuot_pct"] <= 0.10


def test_end_to_end_consistency(full_run):
    from evaluate import consistency

    assert consistency(full_run) == 1.0


def test_dxf_readable(full_run):
    import ezdxf

    doc = ezdxf.readfile(Path(full_run["final_files"]["ban_ve_dxf_zip"]).parent / "dxf" / "KT-02.dxf")
    layers = {e.dxf.layer for e in doc.modelspace()}
    assert {"TUONG", "CUA", "CHU_PHONG", "KICH_THUOC", "TRUC", "KHUNG_TEN"} <= layers


# ---------------- Duyệt thủ công: người dùng sửa phương án công năng ----------------
def test_user_feedback_text_changes_program():
    from agents.architect import _user_feedback

    brief = parse_request(SAMPLE)
    program = initial_program(brief)
    p2, b2, changes, reply = _user_feedback(program, "phòng khách 30 m2, thêm phòng ngủ, sân sau 3", brief)
    assert b2["yeu_cau_phong"]["phong_ngu"] == 4 and p2["san_sau"] == 3.0
    assert next(r for r in p2["tang_1"] if r["loai"] == "khach")["dien_tich"] == 30.0
    assert changes and reply


def test_natural_language_rules():
    from agents.architect import _user_feedback

    brief = parse_request(SAMPLE)
    program = initial_program(brief)
    p2, _, changes, _ = _user_feedback(program, "nhà hơi tối, chuyển phòng thờ xuống tầng 3, tầng 1 cao 3,9", brief)
    assert p2["san_sau"] == 1.0 and p2["chieu_cao_tang"]["tang_1"] == 3.9
    assert any(r["loai"] == "tho" for r in p2["tang_3"])
    # "tối giản" là phong cách, không phải "nhà tối"
    p3, _, _, _ = _user_feedback(program, "phong cách tối giản", brief)
    assert p3["san_sau"] == 0 and p3["phong_cach"] == "tối giản"


def test_three_design_options():
    from agents.architect import identify_program, make_options
    from agents.cost_estimator import evaluate_option

    brief = parse_request(SAMPLE)
    opts = [evaluate_option(brief, opt | {"program": identify_program(opt["program"], brief, "test")})
            for opt in make_options(brief, initial_program(brief))]
    assert [o["id"] for o in opts] == ["A", "B", "C"]
    assert opts[1]["chi_so"]["chi_phi"] < opts[0]["chi_so"]["chi_phi"]      # B rẻ hơn A
    assert opts[2]["chi_so"]["mat_do"] < opts[0]["chi_so"]["mat_do"]         # C chừa sân sau


def test_user_direct_edit():
    from agents.architect import apply_user_edit, program_to_rows

    brief = parse_request(SAMPLE)
    program = initial_program(brief)
    rows = [r for r in program_to_rows(program) if r["ten"] != "Phòng sinh hoạt chung"]
    rows.append({"tang": 3, "ten": "Phòng đọc", "loai": "lam_viec", "dien_tich": 12, "vi_tri": "sau"})
    p2, b2, changes = apply_user_edit(program, rows, {"san_sau": 2, "cap_hoan_thien": "trung bình"}, brief)
    assert any(r["ten"] == "Phòng đọc" for r in p2["tang_3"]) and p2["cap_hoan_thien"] == "trung bình"
    assert b2["yeu_cau_phong"]["phong_lam_viec"] == 1
    assert any(r["loai"] == "thang" for r in p2["tang_3"])  # lõi thang được giữ
    with pytest.raises(ValueError):
        apply_user_edit(program, [{"tang": 2, "ten": "X", "loai": "ngu", "dien_tich": 10, "vi_tri": "trước"}], {}, brief)
