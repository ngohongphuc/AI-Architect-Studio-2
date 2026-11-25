"""Hồ sơ sơ bộ và chọn phương án với nguồn, dữ liệu đầu vào được mô phỏng."""
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

from agents import project_manager, reviewer
from agents.final_reviewer import audit
from graph import build_graph, initial_state, run_design, select_option
from main import SAMPLE
from monitoring import runner
from tools.design_option import option_stamp
from tools.review_display import MISSING, VIOLATION, preliminary_ready, quality_status
from tools.rules import EvidenceReport

AMPLE_BUDGET = SAMPLE.replace("2,5 tỷ", "8 tỷ")


def mock_evidence(monkeypatch, report):
    for agent in (project_manager, reviewer):
        monkeypatch.setattr(agent, "inspect_evidence", lambda *args, **kwargs: report)


def test_missing_input_assumptions_and_sources_do_not_trigger_repair(monkeypatch):
    mock_evidence(monkeypatch, EvidenceReport(blockers=["Thiếu bản ghi nguồn của lô đất (mock)."]))
    state = run_design("Đất 5×20 m, cần nhà hiện đại", persist=False, fengshui_enabled=False)
    assert state["outcome"] == "done"
    assert preliminary_ready(state)
    assert quality_status(state) == {"technical": "Đạt", "regulatory": MISSING}
    assert state["iteration"] == 0
    assert not state["review_issues"]
    assert not state["budget_issues"]
    assert all(item["phan_loai"] == "thieu_nguon" for item in state["review"]["chua_du_can_cu"])
    questions = state["brief_assessment"]["needs_confirmation"]
    assert any("ngân sách" in text for text in questions)
    assert any("số phòng ngủ" in text for text in questions)
    options = [o for o in state["options"] if o["eligible"]]
    assert 2 <= len(options) <= 3
    assert len({opt["chi_so"]["chi_phi"] for opt in options}) > 1
    assert state["recommended_option"] == state["program"]["phuong_an"]
    for option in options:
        assert option["cong_nang"] and option["vat_lieu"] and option["can_xac_minh"]
        assert option["gia_dinh"] and option["uu_diem"] and option["han_che"]
    report = Document(state["final_files"]["thuyet_minh_docx"])
    paragraphs = [p.text for p in report.paragraphs]
    assert any("THUYẾT MINH THIẾT KẾ SƠ BỘ" in p for p in paragraphs)
    assert any("Thiếu bản ghi nguồn của lô đất (mock)." in p for p in paragraphs)
    assert any("Xác nhận số phòng ngủ" in p for p in paragraphs)
    workbook = load_workbook(state["final_files"]["du_toan_xlsx"], read_only=True)
    try:
        assert workbook["Tong_hop"]["A5"].value == "Ngân sách giả định"
        assert any(row[0] == "Cần xác minh" for row in workbook["Gia_dinh"].values)
    finally:
        workbook.close()


def test_verified_violation_excludes_option_and_preserves_other_unknowns(monkeypatch):
    density = ("Mật độ xây dựng", "≤ 90,0%")
    source = {"nguon": "Nguồn mô phỏng", "pham_vi": "Lô QA-1 mô phỏng",
              "trich_dan": {"nguon": "qa.pdf", "muc": "Trang 1", "trich": "Trích dẫn mô phỏng"}}
    mock_evidence(monkeypatch, EvidenceReport(verified={density: source}))
    state = run_design(AMPLE_BUDGET + " Mã lô đất QA-1.", persist=False)
    rejected = {o["id"]: o for o in state["options"] if not o["eligible"]}
    assert rejected.keys() == {"A", "B"}
    for option in rejected.values():
        issue = next(i for i in option["loi"] if i["phan_loai"] == "vi_pham")
        assert issue["nguon"] == source["nguon"] and issue["pham_vi"] == source["pham_vi"]
        assert select_option(state, option["id"]) is None
    assert state["program"]["phuong_an"] == "C"
    assert state["iteration"] == 0
    assert preliminary_ready(state)
    assert quality_status(state)["regulatory"] == MISSING


def test_all_options_conflict_with_verified_scope(monkeypatch):
    # Mô phỏng một ràng buộc đã xác minh áp dụng cho tất cả biến thể.
    checks = reviewer.code_checks

    def rejected(state, **kwargs):
        evaluations, issues, warnings = checks(state, **kwargs)
        issue = {"ma": "SO_TANG", "muc": "Số tầng", "phan_loai": "vi_pham",
                 "noi_dung": "Xung đột phạm vi mô phỏng", "nguon": "Nguồn mô phỏng",
                 "pham_vi": "Lô QA-1 mô phỏng"}
        return evaluations, [*issues, issue], warnings

    monkeypatch.setattr(reviewer, "code_checks", rejected)
    state = run_design(AMPLE_BUDGET, max_iterations=0, persist=False)
    assert state["outcome"] == "not_passed"
    assert quality_status(state)["regulatory"] == VIOLATION
    assert not state.get("drawings") and not state.get("final_files")
    assert all(not opt["eligible"] for opt in state["options"])


def test_genuinely_infeasible_geometry_is_separate_from_missing_sources():
    state = run_design("Đất 1,1×16 m, 1 phòng ngủ, ngân sách 4 tỷ", max_iterations=0, persist=False)
    assert state["outcome"] == "not_passed"
    assert quality_status(state) == {"technical": "Không đạt", "regulatory": "Chưa có đánh giá"}
    assert not state.get("drawings") and not state.get("final_files")
    assert all(issue["phan_loai"] == "ky_thuat" for issue in state["remaining_issues"])


def test_switch_rebuilds_same_option_archives(monkeypatch):
    import json

    from monitoring.releases import ARTIFACTS, list_releases, read_artifact

    graph = build_graph()
    monkeypatch.setattr(runner, "get_graph", lambda: graph)
    state = initial_state(AMPLE_BUDGET, fengshui_enabled=False)
    run = runner.Run(run_id=state["run_id"], request=AMPLE_BUDGET)
    before = graph.invoke(state, run.config)
    run.status = before["outcome"]
    original = before["program"]["phuong_an"]
    target = next(o for o in before["options"] if o["eligible"] and o["id"] != original)
    pending = select_option(before, target["id"])
    assert all(pending[k] is None for k in ("drawings", "review", "cost", "draft_files", "final_files"))
    assert not run.choose_option(target["id"], expected_revision="stale")
    assert run.choose_option(target["id"], expected_revision=target["program"]["revision_id"])
    run.thread.join(timeout=50)
    assert run.status == "done", run.error
    after = run.state()
    assert after["selected_by_user"]
    assert after["program"]["phuong_an"] == target["id"]
    assert after["revision_id"] == target["program"]["revision_id"] != before["revision_id"]
    assert after["iteration"] == before["iteration"] == 0
    assert after["cost"]["tong_chi_phi"] == target["chi_so"]["chi_phi"]
    assert after["area_table"]["tong_dien_tich_san"] == target["chi_so"]["tong_dien_tich_san"]
    assert after["final_review"]["dat"]
    assert after["final_files"] != before["final_files"]
    assert all(Path(path).is_file() for path in before["final_files"].values())
    files = after["final_files"]
    stamp = option_stamp(target["program"])
    assert PdfReader(files["ban_ve_pdf"]).metadata.subject == stamp
    assert Document(files["thuyet_minh_docx"]).core_properties.identifier == stamp
    book = load_workbook(files["du_toan_xlsx"], read_only=True)
    try:
        assert book.properties.identifier == stamp
    finally:
        book.close()
    wrong_revision = files | {"du_toan_xlsx": before["final_files"]["du_toan_xlsx"]}
    assert {error.target for error in audit(after | {"draft_files": wrong_revision}).loi} == {"cost_estimator"}
    releases, unresolved = list_releases(Path(state["output_dir"]), state["run_id"], after)
    assert unresolved == 0
    by_revision = {edition.state["revision_id"]: edition for edition in releases}
    assert set(by_revision) == {before["revision_id"], after["revision_id"]}
    for snapshot in (before, after):
        saved = by_revision[snapshot["revision_id"]].state
        assert saved["area_table"] == snapshot["area_table"]
        assert saved["cost"] == json.loads(json.dumps(snapshot["cost"]))
        assert Path(saved["drawings"]["sheets"][0]["png"]).is_file()
        for kind in ARTIFACTS:
            assert read_artifact(Path(saved["final_files"][kind]), kind, option_stamp(saved["program"]))[0]
    assert read_artifact(Path(before["final_files"]["ban_ve_pdf"]), "ban_ve_pdf", stamp)[1] == "Tệp thuộc phiên bản khác."
