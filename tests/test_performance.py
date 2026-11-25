import csv
import io
from dataclasses import replace

import pytest

from monitoring import events, performance as perf, performance_demo, task_reviews, tasks


def architecture():
    return perf.filter_tasks(performance_demo.sample(), agent="architect")


def test_known_demo_formulas():
    data = architecture()
    result = perf.summarize(data)
    assert [result[key].value for key in ("assigned", "completed", "accepted", "scored", "repairs")] == [3, 3, 2, 3, 1]
    assert result["quality"].value == 80 and result["quality"].scale == 85
    assert result["quality"].task_ids == (data[0].id, data[1].id)
    assert result["first_pass"].value == pytest.approx(1 / 3)
    assert (result["first_pass"].assessed, result["first_pass"].population) == (1, 3)
    assert result["completion"].value == 1
    assert result["processing"].value == 15 and result["waiting"].value == 3
    assert result["tokens"].value == 600 and result["tokens"].assessed == 4 and result["tokens"].population == 5
    assert result["cost"].value == pytest.approx(.6) and result["cost"].estimated
    assert result["unit_cost"].value == pytest.approx(.3) and result["unit_cost"].population == 4
    assert data[0].first["earned"] == 82 and data[0].accepted["earned"] == 90
    assert [row["earned"] for row in perf.quality_series(data)] == [90, 70]


def test_filter_keeps_whole_task_family_and_never_rescales_partial_points():
    data = architecture()
    first = perf.local_day(data[0].first["assigned_at"])
    filtered = perf.filter_tasks(data, start=first, end=first, run=data[0].run, model="mock-2",
                                 stage="architect", agent="architect")
    assert len(filtered) == 1 and len(filtered[0].attempts) == 2
    assert perf.summarize(filtered)["unit_cost"].value == pytest.approx(.3)
    assert perf.filter_tasks(data, model=perf.UNRECORDED_MODEL) == [data[2]]
    data[0] = replace(data[0], attempts=(data[0].first, {**data[0].accepted, "score_status": "partial", "earned": 60}))
    summary = perf.summarize(data)
    assert summary["scored"].value == 3
    assert summary["quality"].value == 70 and summary["quality"].assessed == 1 and summary["quality"].population == 2
    assert summary["first_pass"].value == pytest.approx(1 / 3)


def test_missing_measurements_and_unstarted_attempts():
    assert all(item.value is None for item in perf.summarize([]).values())
    data = architecture()
    queued = {**data[0].first, "attempt_no": 3, "started_at": None, "processed": False, "status": "queued",
              "acceptance": None, "tokens": None, "cost_usd": None, "processing_s": None, "wait_s": None}
    data[0] = replace(data[0], attempts=(*data[0].attempts, queued))
    assert perf.summarize(data)["unit_cost"].value == pytest.approx(.3)
    data[1] = replace(data[1], attempts=({**data[1].first, "cost_usd": None}, data[1].accepted))
    summary = perf.summarize(data)
    assert summary["cost"].value == pytest.approx(.55)
    assert summary["unit_cost"].value is None
    drafter = perf.filter_tasks(performance_demo.sample(), agent="drafter")
    result = perf.summarize(drafter)
    assert result["accepted"].value == 0 and result["first_pass"].value == 0
    assert result["cost"].value is result["tokens"].value is result["unit_cost"].value is None


def test_sources_and_audited_fault_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "LOG_DB", tmp_path / "performance.db")

    def stage(run, number):
        state = {"run_id": run, "brief": {"yeu_cau_phong": {"so_tang": 2}},
                 "task_retry": {"reason": "Cần đối chiếu", "category": "agent_error"}}
        tasks.queue_ready(state, [(f"execution-{number}", "concept_architect")])
        with events._conn() as con:
            con.execute("UPDATE task_attempts SET status='completed', processed=1, output_json='{}' WHERE task_id=?",
                        (f"{run}:concept_architect",))
        return tasks.attempts(f"{run}:concept_architect")[0]["attempt_id"]

    for run, source in (("real", "live"), ("sample", "mock"), ("scene", "simulation")):
        events.record_run(run, "", "", data_source=source)
        stage(run, 1)
    for run, source in (("real", "live"), ("sample", "mock"), ("scene", "simulation")):
        assert [item.run for item in perf.load(source)] == [run]
    assert [item["run_id"] for item in events.list_runs()] == ["real"]
    with pytest.raises(ValueError, match="nguồn dữ liệu khác"):
        events.record_run("real", "", "", data_source="mock")

    second = stage("real", 2)
    assert perf.summarize(perf.load("live"))["repairs"].value == 0
    args = {"reviewer": "Minh", "manual_score": None, "agent_fault_confirmed": True}
    with pytest.raises(ValueError, match="bằng chứng"):
        task_reviews.save("real", second, expected_revision=0, submission_id="missing", **args)
    evidence = "Có bản vẽ ghi sai số tầng so với brief đã giao."
    first = task_reviews.save("real", second, expected_revision=0, submission_id="yes", agent_fault_evidence=evidence, **args)
    assert first["agent_fault_confirmed"] == 1
    assert perf.summarize(perf.load("live"))["repairs"].value == 1
    task_reviews.save("real", second, expected_revision=1, submission_id="withdraw", reviewer="Minh", manual_score=None)
    assert perf.summarize(perf.load("live"))["repairs"].value == 0
    assert task_reviews.history("real", second)[1]["agent_fault_evidence"] == evidence


def test_csv_exports_filtered_attempts_with_no_comments_prompts_or_keys(monkeypatch):
    secret = "secret-for-csv-export-test-1234"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    data = architecture()
    item = replace(data[0], id="=SUM(1,2)", attempts=(
        {**data[0].first, "model": f"model {secret}", "prompt": "private prompt",
         "agent_fault_evidence": "private note"}, data[0].accepted))
    csv_file = perf.csv_export([item], "mock").decode("utf-8-sig")
    assert secret not in csv_file and "private prompt" not in csv_file and "private note" not in csv_file
    rows = list(csv.DictReader(io.StringIO(csv_file)))
    assert len(rows) == 2 and rows[0]["task_id"] == "'=SUM(1,2)"
    assert all(row["data_source"] == "mock" for row in rows)
