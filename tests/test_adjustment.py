"""Chủ nhiệm đề xuất điều chỉnh yêu cầu khi lượt thiết kế chưa đạt."""
import pytest

from config import BUDGET_TOLERANCE
from graph import outcome_for, run_design
from tools.adjustment import find_adjustments, request_text
from tools.brief_parser import inspect_request

OVER_BUDGET = ("Lô đất 5x20m hướng Nam tại Hà Nội. Gia đình 5 người, chủ nhà là chồng, sinh năm 1985. "
               "Cần 4 phòng ngủ, 1 phòng thờ, 1 phòng làm việc, gara ô tô. Ngân sách 2 tỷ.")
SHALLOW_LOT = "Lô đất 7x10m tại Hưng Yên. Gia đình 5 người. Cần 5 tầng, 6 phòng ngủ. Ngân sách 5 tỷ."


@pytest.fixture(scope="module")
def over_budget_run():
    return run_design(OVER_BUDGET, max_iterations=1, persist=False)


def test_request_text_round_trips_brief():
    brief = inspect_request(OVER_BUDGET, {})[0]
    parsed = inspect_request(request_text(brief), {})[0]
    for key in ("lo_dat", "yeu_cau_phong", "ngan_sach", "phong_cach"):
        assert parsed[key] == brief[key]


def test_not_passed_run_gets_feasible_proposals(over_budget_run):
    state = over_budget_run
    assert outcome_for(state) == "not_passed"
    proposals = state["adjustment"]["de_xuat"]
    assert 1 <= len(proposals) <= 3
    assert any(p["tieu_de"].startswith("Tăng ngân sách") for p in proposals)
    for proposal in proposals:
        assert proposal["vuot_pct"] <= BUDGET_TOLERANCE
        assert inspect_request(proposal["request"], {})[0] is not None


def test_applying_first_proposal_passes(over_budget_run):
    proposal = over_budget_run["adjustment"]["de_xuat"][0]
    rerun = run_design(proposal["request"], max_iterations=1, persist=False)
    assert outcome_for(rerun) == "done"


def test_infeasible_lot_suggests_minimum_dimension():
    brief = inspect_request(SHALLOW_LOT, {})[0]
    proposals = find_adjustments(brief)
    assert len(proposals) == 1 and proposals[0]["can_xac_nhan"]
    assert "chiều sâu tối thiểu" in proposals[0]["tieu_de"]


def test_passing_run_has_no_adjustment():
    state = run_design(OVER_BUDGET.replace("2 tỷ", "4 tỷ"), max_iterations=1, persist=False)
    assert outcome_for(state) == "done" and not state.get("adjustment")
