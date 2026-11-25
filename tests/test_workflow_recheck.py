"""Kiểm tra nhánh sửa qua workflow thật và nguồn quy chuẩn chỉ dùng trong fixture."""
import json

import pytest
from matplotlib.figure import Figure

import graph
from agents import architect, drafter, reviewer
from monitoring import events, runner
from tools import layout_algorithm, rules
from tools.brief_parser import inspect_request
from tools.layout_algorithm import build_area_table, compute_layout
from tools.review_display import MISSING, VERIFIED, VIOLATION, preliminary_ready, quality_status, review_rows


REQUEST = "Đất 4.5×16 m tại Hà Nội; 2 tầng; 1 phòng ngủ; ngân sách 12 tỷ"
FIELDS = {"ma_lo_dat": "QA/A-01"}


@pytest.fixture(autouse=True)
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(graph, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(events, "LOG_DB", tmp_path / "events.db")
    monkeypatch.setattr(rules, "DATA_DIR", tmp_path)


@pytest.fixture
def evidence(tmp_path):
    brief, _, _ = inspect_request(REQUEST, FIELDS)
    program = architect.initial_program(brief)
    layout = compute_layout(brief, program)
    checks, _, _ = reviewer.code_checks(
        {"brief": brief, "program": program, "layout": layout, "area_table": build_area_table(layout, brief)},
        lookup_citations=False,
    )
    folder = tmp_path / "quy_chuan"
    folder.mkdir()
    text = "Mock source for automated workflow tests only"
    pdf = Figure()
    pdf.text(.12, .8, text)
    pdf.savefig(folder / "qa.pdf")
    records = [{"muc": check["muc"], "nguong": check["cho_phep"], "tinh": "Hà Nội",
                "ma_lo_dat": FIELDS["ma_lo_dat"], "nguon": "Nguồn kiểm thử",
                "pham_vi": "Lô kiểm thử QA/A-01", "tai_lieu": "qa.pdf", "trang": 1, "trich": text}
               for check in checks if check["loai"] == "Quy chuẩn"]
    (folder / rules.MANIFEST).write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def design(limit):
    return graph.run_design(REQUEST, persist=False, request_fields=FIELDS, max_iterations=limit, fengshui_enabled=False)


def test_first_inspection_passes_in_scope(evidence):
    state = design(3)
    assert state["outcome"] == "done" and state["iteration"] == 0
    assert state["review"]["dat"]
    assert quality_status(state) == {"technical": "Đạt", "regulatory": VERIFIED}
    assert state["versions"]["reviewer"] == 1
    assert state["brief"]["lo_dat"]["ma_lo_dat"] == FIELDS["ma_lo_dat"]


@pytest.mark.parametrize("still_faulty,limit", [(False, 1), (True, 2)])
def test_failed_stair_check_reaches_owner_and_rechecks(evidence, monkeypatch, still_faulty, limit):
    def layout_on_drawing(brief, program):
        layout = compute_layout(brief, program)
        if still_faulty or not program.get("doi_chieu_cau_thang"):
            for flight in layout["stair"]["cac_tang"]:
                flight["bac_rong"] = 0.23
        return layout

    monkeypatch.setattr(drafter, "compute_layout", layout_on_drawing)
    state = design(limit)
    assert state["iteration"] == limit and state["max_iterations"] == limit
    versions = state["versions"]
    assert versions["reviewer"] == versions["drafter"] == versions["architect"] == limit + 1
    assert versions["requirements_analyst"] == versions["concept_architect"] == 1
    first, *rechecks = [entry for entry in state["history"] if entry["stage"] == "reviewer"]
    assert first["attempt_id"] and first["iteration"] == 0
    assert first["output"]["loi"][0]["ma"] == "CAU_THANG"
    assert [entry["iteration"] for entry in rechecks] == list(range(1, limit + 1))
    assert any(entry["stage"] == "coordinate_repair" and entry["iteration"] == 1 and entry["to_agent"] == "architect"
               for entry in state["history"])
    assert any(entry["stage"] == "architect" and entry["iteration"] == 1 and entry["output"]["thay_doi"]
               for entry in state["history"])
    if still_faulty:
        assert state["outcome"] == "not_passed" and state["repair_limit_reached"]
        assert state["remaining_issues"][0]["phan_loai"] == "vi_pham"
        assert not state.get("final_files")
        assert quality_status(state)["regulatory"] == VIOLATION
    else:
        assert state["outcome"] == "done" and state["review"]["dat"]
        assert state["final_files"] and state["program"]["doi_chieu_cau_thang"]
        assert quality_status(state)["regulatory"] == VERIFIED


def test_missing_documents_yield_preliminary_with_criterion_details():
    state = design(3)
    assert state["outcome"] == "done" and state["iteration"] == 0
    assert preliminary_ready(state)
    unknown = [row for row in review_rows(state["review"], state["brief"]) if row["status"] == MISSING]
    assert len(unknown) == 11
    assert all(row["actual"] and row["threshold"] and row["missing"] and rules.MANIFEST in row["action"]
               for row in unknown)
    assert all(row["regulatory"] for row in unknown)
    assert not any(entry["stage"] == "coordinate_repair" for entry in state["history"])


def test_added_evidence_rechecks_existing_layout_without_restarting_design(evidence, tmp_path, monkeypatch):
    manifest = tmp_path / "quy_chuan" / rules.MANIFEST
    contents = manifest.read_bytes()
    manifest.write_text("[]", encoding="utf-8")
    workflow = graph.build_graph()
    monkeypatch.setattr(runner, "get_graph", lambda: workflow)
    initial = graph.initial_state(REQUEST, request_fields=FIELDS)
    run = runner.Run(initial["run_id"], REQUEST)
    before = workflow.invoke(initial, run.config)
    assert preliminary_ready(before) and before["versions"]["fengshui_advisor"] == 1
    run.status = before["outcome"]
    manifest.write_bytes(contents)
    assert run.rerun_agent("reviewer", expected_revision=before["revision_id"])
    run.thread.join(timeout=35)
    assert run.status == "done", run.error
    after = run.state()
    assert quality_status(after)["regulatory"] == VERIFIED
    assert after["iteration"] == 0 and after["revision_id"] == before["revision_id"]
    assert after["drawings"] == before["drawings"]
    unchanged = ("requirements_analyst", "concept_architect", "architect", "drafter", "fengshui_advisor")
    assert all(after["versions"][agent] == before["versions"][agent] for agent in unchanged)
    assert after["versions"]["reviewer"] == before["versions"]["reviewer"] + 1
    assert after["versions"]["cost_estimator"] == before["versions"]["cost_estimator"] + 1


def test_budget_uses_all_three_rounds_without_graph_recursion_error():
    state = graph.run_design(REQUEST.replace("12 tỷ", "100 triệu"), persist=False, max_iterations=3)
    assert state["iteration"] == 3
    assert state["repair_limit_reached"] and state["outcome"] == "not_passed"
    assert any(item["ma"] == "VUOT_NGAN_SACH" for item in state["remaining_issues"])


def test_parcel_id_is_not_a_location_and_user_conflicts_are_caught():
    brief, _, _ = inspect_request("Đất 5×20 m tại Đà Nẵng; mã lô đất: HN/A.01.", {"ma_lo_dat": "hn/a.01"})
    assert brief["lo_dat"]["tinh"] == "Đà Nẵng"
    assert brief["lo_dat"]["ma_lo_dat"] == "HN/A.01"
    brief, _, conflicts = inspect_request("Đất 5×20 m; mã lô đất: A-1", {"ma_lo_dat": "A-2"})
    assert brief is None and "Mã lô đất khác nhau" in conflicts[0]


def test_stair_repair_uses_same_thresholds_as_the_check(monkeypatch):
    local = rules.load_rules()["cau_thang"] | {"bac_rong_min": 0.28}
    monkeypatch.setattr(layout_algorithm, "load_rules", lambda: {"cau_thang": local})
    baseline = layout_algorithm.design_stair([3.4, 3.3], 2.2)
    revised = layout_algorithm.design_stair([3.4, 3.3], 2.2, tune=True)
    assert all(flight["bac_rong"] < local["bac_rong_min"] for flight in baseline["cac_tang"])
    for flight in revised["cac_tang"]:
        assert flight["bac_rong"] >= local["bac_rong_min"]
        assert flight["bac_cao"] <= local["bac_cao_max"]
        assert local["blondel_min"] <= flight["blondel"] <= local["blondel_max"]
