"""Kiểm tra biểu mẫu, lịch sử và cơ chế gửi lượt thiết kế bằng mock."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import Mock

from agents import requirements_analyst as analyst
from main import SAMPLE
from monitoring import events
from monitoring.runner import Run, RunManager
from tools.brief_parser import inspect_request


def test_preview_combines_text_and_fields_before_applying_assumptions():
    request = "Đất rộng 5 m, ở Hà Nội. Gia đình 4 người cần 3 phòng ngủ, phòng khách 4×5 m."
    fields = {"dai": 20, "tinh": "HN", "so_tang": 3, "ngan_sach": 2_500_000_000}
    brief, questions, conflicts = inspect_request(request, fields)
    assert not questions and not conflicts
    assert brief["lo_dat"] | {"rong": 5, "dai": 20, "tinh": "Hà Nội"} == brief["lo_dat"]
    assert brief["gia_dinh"]["so_nguoi"] == 4
    assert brief["yeu_cau_phong"]["so_tang"] == 3
    assert brief["yeu_cau_phong"]["phong_ngu"] == 3
    assert brief["ngan_sach"] == fields["ngan_sach"]
    assert not any(note.startswith(("Kích thước", "Ngân sách", "Địa điểm")) for note in brief["gia_dinh_bo_sung"])


def test_conflicting_values_and_missing_required_fields_are_explicit():
    brief, questions, conflicts = inspect_request(SAMPLE, {"rong": 6, "tinh": "Long An", "ngan_sach": 2_000_000_000})
    assert brief is None and not questions
    assert [text.split(" khác nhau")[0] for text in conflicts] == ["Chiều rộng mặt tiền", "Địa điểm", "Ngân sách"]
    brief, questions, conflicts = inspect_request("Cần nhà hiện đại", {"rong": 5})
    assert brief is None and questions == ["Bổ sung chiều sâu lô đất (m)."] and not conflicts
    brief, _, _ = inspect_request("Đất 5×20 m")
    assert any(note.startswith("Ngân sách:") for note in brief["gia_dinh_bo_sung"])


def test_labelled_values_and_budget_followed_by_room_count():
    brief, _, conflicts = inspect_request("Đất 5×20 m. Số tầng: 2. Ngân sách 2 tỷ 4 phòng ngủ",
                                         {"ngan_sach": 2_000_000_000, "phong_ngu": 4})
    assert not conflicts and brief["yeu_cau_phong"]["so_tang"] == 2
    brief, _, conflicts = inspect_request("Đất 5×20 m. Ngân sách: 2.500.000.000 đồng. Số phòng ngủ: 4",
                                         {"phong_ngu": 3})
    assert brief is None and conflicts[0].startswith("Số phòng ngủ khác nhau")


def test_preview_and_failed_intake_never_invoke_model(monkeypatch):
    invoke = Mock()
    monkeypatch.setattr(analyst, "llm_enabled", lambda: True)
    monkeypatch.setattr(analyst, "invoke_structured", invoke)
    assert inspect_request(SAMPLE)[0]
    result = analyst.run({"user_request": SAMPLE, "request_fields": {"phong_ngu": 5}})
    assert result["outcome"] == "needs_input"
    invoke.assert_not_called()


def test_confirmed_form_values_reach_agent_even_if_mock_model_disagrees(monkeypatch):
    mock_brief, _, _ = inspect_request(SAMPLE)
    invoke = Mock(return_value=mock_brief)
    monkeypatch.setattr(analyst, "llm_enabled", lambda: True)
    monkeypatch.setattr(analyst, "invoke_structured", invoke)
    fields = {"rong": 6, "dai": 18, "tinh": "Long An", "so_tang": 2, "so_nguoi": 5,
              "phong_ngu": 4, "ngan_sach": 3_000_000_000}
    preview, _, _ = inspect_request("Cần nhà hiện đại", fields)
    result = analyst.run({"user_request": "Cần nhà hiện đại", "request_fields": fields})
    invoke.assert_called_once()
    assert "Long An" in invoke.call_args.args[1]
    for key in ("lo_dat", "ngan_sach", "gia_dinh_bo_sung"):
        assert result["brief"][key] == preview[key]
    assert result["brief"]["gia_dinh"]["so_nguoi"] == 5
    assert result["brief"]["yeu_cau_phong"]["phong_ngu"] == 4
    assert result["brief"]["yeu_cau_phong"]["so_tang"] == 2


def test_double_submission_starts_one_run(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "LOG_DB", tmp_path / "log.db")
    start = Mock()
    monkeypatch.setattr(Run, "_start", start)
    manager = RunManager()
    fields = {"rong": 5, "dai": 20}
    with ThreadPoolExecutor(max_workers=4) as executor:
        runs = list(executor.map(lambda _: manager.start("", request_fields=fields, submission_id="draft"), range(4)))
    assert len({run.run_id for run in runs}) == 1
    start.assert_called_once()
    assert start.call_args.args[0]["request_fields"] == fields
    assert len(events.list_runs()) == 1
    assert manager.start("", request_fields=fields, submission_id="another").run_id != runs[0].run_id


def test_history_migrates_legacy_records_and_tracks_activity(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, created TEXT, request TEXT, "
                     "status TEXT, output_dir TEXT, summary TEXT)")
        conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                     ("old", "2025-05-07T10:00:00", SAMPLE, "done", "saved", "{}"))
    monkeypatch.setattr(events, "LOG_DB", db)
    row, = events.list_runs(recent_activity=True)
    assert row["created"] == "2025-05-07T10:00:00" and row["updated"] is None
    events.update_run("old", "running")
    row, = events.list_runs(recent_activity=True)
    assert row["updated"] > row["created"] and row["request"] == SAMPLE
