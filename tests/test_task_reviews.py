from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from unittest.mock import Mock

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from monitoring import events, rubrics, task_reviews, tasks
from state import DesignState


def concept(*, requested=2, drawn=2):
    return {
        "processed": 1,
        "rubric": rubrics.snapshot("concept_architect", "Có định hướng thiết kế"),
        "input": {"brief": {"yeu_cau_phong": {"so_tang": requested}}},
        "output": {"concept_plan": {"so_tang": drawn, "phong_cach": "Hiện đại", "vat_lieu": {"mat_tien": "gỗ"},
                                   "thong_gio": ["Sân sau"], "chieu_sang": ["Giếng trời"]},
                   "concept": "Lấy sáng ở giữa nhà", "route": "architect"},
    }


def test_criteria_weights_and_evidence_are_explicit_for_every_stage():
    assert set(rubrics.STAGE_RUBRICS) == set(tasks.STAGES)
    for stage, spec in tasks.STAGES.items():
        rubric = rubrics.snapshot(stage, spec.criteria)
        assert [row["points"] for row in rubric["criteria"]] == [40, 30, 20, 10]
        assert [row["group"] for row in rubric["criteria"] if row["rule"] == "manual"] == ["professional"]
        assert rubric["version"] == rubrics.VERSION

    score = rubrics.evaluate(concept(), manual_score=14, manual_evidence="Nêu rõ hai mặt thoáng.")
    assert score["status"] == "complete"
    assert score["automatic"] == {"earned": 80, "assessed": 80, "applicable": 80, "maximum": 80}
    assert score["manual"]["earned"] == 14 and score["total"]["earned"] == 94
    assert all(item["evidence"] for item in score["criteria"])


def test_missing_not_applicable_and_failures_have_different_denominators():
    result = rubrics.evaluate(concept(drawn=3))
    assert result["status"] == "partial"
    assert result["total"] == {"earned": 50, "assessed": 80, "applicable": 100, "maximum": 100}
    assert result["criteria"][1]["status"] == "failed" and result["criteria"][1]["score"] == 0

    result = rubrics.evaluate(concept(requested=None), manual_score=10, manual_evidence="Hợp hướng nhà.")
    assert result["status"] == "complete"
    assert result["total"] == {"earned": 60, "assessed": 70, "applicable": 70, "maximum": 100}
    assert result["criteria"][1]["status"] == "na" and result["criteria"][1]["score"] is None

    changed = concept()
    changed["input"]["brief"]["yeu_cau_phong"].pop("so_tang")
    assert rubrics.evaluate(changed)["total"] == {"earned": 50, "assessed": 50, "applicable": 100, "maximum": 100}
    unavailable = dict(concept(), processed=0, output=None, failure_category="infrastructure",
                       retry_category="user_change")
    blocked = rubrics.evaluate(unavailable)
    assert blocked["status"] == "partial" and blocked["total"]["assessed"] == 0
    assert all(item["score"] is None for item in blocked["criteria"])
    with pytest.raises(ValueError, match="đầu ra"):
        rubrics.evaluate(unavailable, manual_score=0, manual_evidence="Không có đầu ra")

    fallback = dict(concept(drawn=3), failure_category="missing_input")
    assert rubrics.evaluate(fallback)["criteria"][1]["status"] == "missing"
    with pytest.raises(ValueError, match="bằng chứng"):
        rubrics.evaluate(concept(), manual_score=14)


def test_cost_check_scores_arithmetic_independently_of_budget_and_model_metrics():
    attempt = {"processed": 1, "rubric": rubrics.snapshot("cost_estimator", ""), "input": {},
               "duration_s": 300, "tokens": 1000, "cost_usd": 2.0,
               "output": {"cost_file": "draft.xlsx", "cost": {
                   "hang_muc": [{"kl": 3, "don_gia": 200, "thanh_tien": 600}],
                   "chi_phi_xay_dung": 600, "du_phong_pct": 0.10, "du_phong": 60,
                   "tong_chi_phi": 660, "ngan_sach": 80, "chenh_lech": 580,
                   "tiet_kiem": [], "ghi_chu": "Vượt mốc ngân sách"}}}
    assert rubrics.evaluate(attempt)["automatic"]["earned"] == 80
    attempt["output"]["cost"]["tong_chi_phi"] = 662
    row = rubrics.evaluate(attempt)["criteria"][1]
    assert row["score"] == 0 and "660" in row["evidence"] and "662" in row["evidence"]


def test_review_history_idempotency_and_attempt_versions(tmp_path, monkeypatch):
    db = tmp_path / "logs.db"
    monkeypatch.setattr(events, "LOG_DB", db)
    events.record_run("run-a", "Thiết kế kiểm thử", "")
    output = deepcopy(concept()["output"])
    calls = Mock(side_effect=lambda state: {**output, "revision_id": "design-" + str(state["iteration"])})
    app = StateGraph(DesignState)
    app.add_node("concept_architect", tasks.track_stage("concept_architect", calls))
    app.add_edge(START, "concept_architect")
    app.add_edge("concept_architect", END)
    workflow = app.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "run-a"}}
    inputs = {"run_id": "run-a", "brief": concept()["input"]["brief"], "iteration": 1}
    stream = tasks.stream_tracked(workflow, inputs, config)
    for kind, payload in stream:
        if kind == "checkpoints" and "concept_architect" in payload["next"]:
            queued, = tasks.attempts("run-a:concept_architect")
            assert queued["status"] == "queued" and queued["rubric"]["version"] == "task-quality-v1"
            monkeypatch.setattr(rubrics, "VERSION", "task-quality-v2-test")
    latest, = tasks.attempts("run-a:concept_architect")
    assert latest["rubric"] == queued["rubric"] and latest["output_version"] == "design-1"

    form = {"expected_revision": 0, "submission_id": "nonce-first", "reviewer": "Minh",
            "manual_score": 12, "manual_evidence": "Giếng trời có vị trí rõ.", "comment": "Xem mặt cắt."}
    with ThreadPoolExecutor(max_workers=3) as pool:
        first, same, repeated = pool.map(lambda _: task_reviews.save("run-a", latest["attempt_id"], **form), range(3))
    assert first == same == repeated
    assert first["rubric_version"] == "task-quality-v1" and first["design_version"] == "design-1"
    assert first["reviewer_kind"] == "self_declared"
    assert len(task_reviews.history("run-a", latest["attempt_id"])) == 1
    with pytest.raises(task_reviews.ReviewConflict):
        task_reviews.save("run-a", latest["attempt_id"], **{**form, "submission_id": "stale", "manual_score": 10})

    edit = {**form, "expected_revision": 1, "submission_id": "nonce-second", "reviewer": "Anh", "manual_score": 16}
    second = task_reviews.save("run-a", latest["attempt_id"], **edit)
    assert second["revision"] == 2 and second["reviewer"] == "Anh"
    assert second["created_at"] >= first["created_at"] and second["score"]["total"]["earned"] == 96
    duplicate = task_reviews.save("run-a", latest["attempt_id"],
                                  **{**edit, "expected_revision": 2, "submission_id": "same-values"})
    assert duplicate == second
    assert task_reviews.history("run-a", latest["attempt_id"]) == [second, first]

    list(tasks.stream_tracked(workflow, {**inputs, "iteration": 2}, config))
    new, old = tasks.attempts("run-a:concept_architect")
    assert new["attempt_id"] != old["attempt_id"] and new["rubric"]["version"] == "task-quality-v2-test"
    assert new["output_version"] == "design-2"
    assert task_reviews.history("run-a", new["attempt_id"]) == []
    new_score = task_reviews.save("run-a", new["attempt_id"], **{
        **form, "submission_id": "nonce-new", "manual_score": None, "manual_evidence": ""})
    assert new_score["revision"] == 1 and new_score["score"]["total"]["assessed"] == 80
    assert task_reviews.history("run-a", old["attempt_id"])[1]["manual_score"] == 12
    assert tasks.find_attempt("run-a", old["attempt_id"])["acceptance"] is None
    assert calls.call_count == 2


def test_legacy_attempt_stays_without_a_rubric(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "LOG_DB", tmp_path / "before.db")
    original = tasks.SCHEMA.replace(", rubric_json TEXT", "")
    with events._conn() as con:
        con.executescript(original)
        con.execute("INSERT INTO tasks VALUES ('old', 'run-old', 'architect', 'architect', 'Old', '', '')")
        con.execute("""INSERT INTO task_attempts (attempt_id, task_id, execution_id, attempt_no, status, assigned_at,
                       input_json) VALUES ('old-attempt', 'old', 'old', 1, 'completed', '2024-01-01', '{}')""")
    assert tasks.find_attempt("run-old", "old-attempt")["rubric"] is None
    with pytest.raises(ValueError, match="bộ tiêu chí"):
        task_reviews.save("run-old", "old-attempt", expected_revision=0, submission_id="old", reviewer="Minh",
                          manual_score=None)
    assert task_reviews.history("run-old", "old-attempt") == []
