"""Kiểm tra điều phối và dữ liệu, dùng quy tắc hoặc mock cục bộ."""
import pytest
from langgraph.types import Command
from openpyxl import load_workbook

from agents import final_reviewer, project_manager, requirements_analyst, reviewer
from agents.final_reviewer import audit
from graph import build_graph, initial_state, outcome_for, run_design
from main import SAMPLE
from state import Brief


@pytest.mark.parametrize(("request_text", "field"), [
    ("Cần nhà hiện đại", "questions"),
    ("Đất 5x20, 3 phòng ngủ, ngân sách 2 tỷ, nhà 2 tầng hoặc 3 tầng", "conflicts"),
    ("Đất 0x20, 3 phòng ngủ, ngân sách 2 tỷ", "conflicts"),
])
def test_invalid_or_incomplete_request(request_text, field):
    state = run_design(request_text, persist=False)
    assert state["outcome"] == "needs_input"
    assert state["brief_assessment"][field]
    assert not state.get("drawings")
    assert not state.get("final_files")


def test_mock_structured_output_respects_explicit_request(monkeypatch):
    mocked = Brief(lo_dat={"rong": 7, "dai": 30},
                   yeu_cau_phong={"phong_ngu": 8}, ngan_sach=9_000_000_000)
    monkeypatch.setattr(requirements_analyst, "llm_enabled", lambda: True)
    monkeypatch.setattr(requirements_analyst, "invoke_structured", lambda *args: mocked)
    brief = requirements_analyst.analyze_brief(SAMPLE)
    assert (brief["lo_dat"]["rong"], brief["lo_dat"]["dai"]) == (5, 20)
    assert brief["yeu_cau_phong"]["phong_ngu"] == 3
    assert brief["ngan_sach"] == 2_500_000_000


def test_web_clarification_reuses_run():
    graph = build_graph()
    state = initial_state("Cần nhà hiện đại", interactive=True, approval_points=["concept_architect"])
    cfg = {"configurable": {"thread_id": state["run_id"]}}
    graph.invoke(state, cfg)
    assert graph.get_state(cfg).next == ("approve_brief",)
    graph.invoke(Command(resume={"action": "edit_request", "request": SAMPLE}), cfg)
    current = graph.get_state(cfg)
    assert current.next == ("approve_concept",)
    assert current.values["brief"]["ngan_sach"] == 2_500_000_000
    assert current.values["iteration"] == 0


@pytest.mark.parametrize(("code", "target"), [("MAT_DO", "concept_architect"), ("PHONG_NHO", "architect")])
def test_regulation_feedback_routes_to_owner(monkeypatch, code, target):
    issue = {"ma": code, "muc": "Mock", "noi_dung": "Phản hồi mô phỏng"}
    monkeypatch.setattr(reviewer, "review_design", lambda s: {
        "loi": [issue], "chua_du_can_cu": [], "nhan_xet": "Mock"})
    result = reviewer.run({"fengshui_enabled": False})
    assert result["route"] == "coordinate_repair"
    assert result["repair_target"] == target
    assert result["repair_fallback"] == "end"


def test_repair_limit_is_shared_across_error_types():
    current = initial_state(SAMPLE, max_iterations=50)
    assert current["max_iterations"] == 3
    for source, target in [("reviewer", "architect"), ("cost_estimator", "concept_architect"),
                           ("final_reviewer", "pm_report"), ("final_reviewer", "drafter")]:
        current.update(feedback_source=source, repair_target=target, repair_fallback="end",
                       feedback=[{"ma": "MOCK", "muc": "Mock", "noi_dung": source}])
        current.update(project_manager.coordinate_repair(current))
    assert current["iteration"] == 3
    assert current["route"] == "propose_adjustment"  # hết vòng sửa -> Chủ nhiệm đề xuất điều chỉnh rồi kết thúc
    assert outcome_for(current) == "not_passed"
    assert current["remaining_issues"][0]["noi_dung"] == "final_reviewer"


@pytest.fixture(scope="module")
def no_fengshui_run():
    return run_design(SAMPLE.replace("2,5 tỷ", "8 tỷ"), max_iterations=0, persist=False, fengshui_enabled=False)


def test_no_fengshui_and_no_unsubstantiated_pass(no_fengshui_run):
    state = no_fengshui_run
    assert state["iteration"] == 0
    assert not state.get("fengshui")
    assert "fengshui_advisor" not in state["versions"]
    assert "final_reviewer" in state["versions"]
    assert state["final_review"]["dat"]
    assert outcome_for(state) == "done"
    assert not state["review"]["dat"]
    for c in state["review"]["kiem_tra"]:
        if c["loai"] == "Quy chuẩn":
            assert c["dat"] is None
            assert c["ket_luan"] == "chưa đủ căn cứ"
            assert c["nguon"] and c["pham_vi"]


def test_invalid_export_is_detected_and_routed(no_fengshui_run, tmp_path):
    state = dict(no_fengshui_run)
    files = dict(state["draft_files"])
    book = load_workbook(files["du_toan_xlsx"])
    book["Tong_hop"]["B4"] = "=123"
    path = tmp_path / "du_toan.xlsx"
    book.save(path)
    book.close()
    files["du_toan_xlsx"] = str(path)
    corrupted = state | {"draft_files": files}
    result = final_reviewer.run(corrupted)
    assert result["route"] == "coordinate_repair"
    assert result["repair_target"] == "cost_estimator"
    assert {i["target"] for i in result["final_review"]["loi"]} == {"cost_estimator"}
    files["thuyet_minh_docx"] = str(tmp_path / "missing.docx")
    assert {i.target for i in audit(state | {"draft_files": files}).loi} == {"cost_estimator", "pm_report"}


def test_stable_ids_and_dependent_outputs(no_fengshui_run):
    state = no_fengshui_run
    from agents.architect import identify_program
    from graph import invalidate_from

    original = state["program"]
    new = identify_program(original, state["brief"], state["run_id"])
    assert original["revision_id"] != new["revision_id"]
    assert original["floor_ids"] == new["floor_ids"]
    assert [r["id"] for r in original["tang_1"]] == [r["id"] for r in new["tang_1"]]
    reset = invalidate_from("drafter")
    assert all(reset[k] is None for k in ("drawings", "review", "fengshui", "cost", "draft_files", "final_files"))
    assert "iteration" not in reset


def test_mock_invalid_llm_output_falls_back(monkeypatch):
    monkeypatch.setattr(requirements_analyst, "llm_enabled", lambda: True)
    monkeypatch.setattr(requirements_analyst, "invoke_structured", lambda *args: {"ngan_sach": -1})
    brief = requirements_analyst.analyze_brief(SAMPLE)
    assert brief["ngan_sach"] == 2_500_000_000
    assert any("sai schema" in note for note in brief["gia_dinh_bo_sung"])


def test_final_feedback_regenerates_only_dependent_files(monkeypatch):
    original = final_reviewer._cost_matches
    checked = []

    def mismatch_once(path, area, cost):
        checked.append(path)
        # Mô phỏng một sai lệch trong lần đối chiếu XLSX đầu tiên.
        return len(checked) > 1 and original(path, area, cost)

    monkeypatch.setattr(final_reviewer, "_cost_matches", mismatch_once)
    state = run_design(SAMPLE.replace("2,5 tỷ", "8 tỷ"), persist=False)
    assert state["iteration"] == 1  # Tái tạo XLSX và DOCX; thiếu nguồn không dùng vòng sửa.
    assert state["versions"]["drafter"] == 1
    assert state["versions"]["cost_estimator"] == 3  # So sánh phương án và hai lần xuất dự toán.
    assert len(set(checked)) == 2
    assert state["final_review"]["dat"]
    assert state.get("final_files")


def test_verified_reference_is_bound_to_parcel_page_and_threshold(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    import pypdf

    from tools import rules

    folder = tmp_path / "quy_chuan"
    folder.mkdir()
    monkeypatch.setattr(rules, "DATA_DIR", tmp_path)
    (folder / "mock.pdf").write_bytes(b"mock document")
    mock_excerpt = "Trich dan gia lap de kiem tra pham vi"
    record = {"muc": "Mật độ xây dựng", "tinh": "Hà Nội", "ma_lo_dat": "a1",
              "nguong": "≤ 90,0%", "nguon": "Nguồn mô phỏng", "pham_vi": "Lô a1 (mô phỏng)",
              "tai_lieu": "mock.pdf", "trang": 1, "trich": mock_excerpt}
    (folder / "can_cu_da_xac_minh.json").write_text(json.dumps([record]), encoding="utf-8")
    monkeypatch.setattr(pypdf, "PdfReader",
                        lambda _: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: mock_excerpt)]))
    assert ("Mật độ xây dựng", "≤ 90,0%") in rules.verified_evidence({"tinh": "Hà Nội", "ma_lo_dat": "A1"})
    assert not rules.verified_evidence({"tinh": "Hà Nội", "ma_lo_dat": "A2"})
