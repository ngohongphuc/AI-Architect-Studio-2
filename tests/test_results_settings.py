"""Kiểm tra đọc lại phiên bản và trạng thái cấu hình cục bộ."""
from unittest.mock import Mock

import llm
from monitoring.releases import list_releases, read_artifact


def test_legacy_release_is_associated_with_matching_checkpoint(tmp_path):
    folder = tmp_path / "releases"
    old = folder / "old"
    unidentified = folder / "unidentified"
    old.mkdir(parents=True)
    unidentified.mkdir()
    state = {"run_id": "example", "revision_id": "r1",
             "program": {"phuong_an": "A", "option_version": 1, "revision_id": "r1"},
             "final_files": {"ban_ve_pdf": str(old / "ban_ve.pdf")},
             "area_table": {"so_tang": 2}}
    unrelated = state | {"run_id": "different"}
    wrong_version = state | {"revision_id": "r2"}
    history = Mock(return_value=iter([unrelated, wrong_version, state]))
    results, unknown = list_releases(tmp_path, "example", {}, history)
    assert unknown == 1
    assert len(results) == 1 and results[0].state == state
    assert read_artifact(old / "ban_ve.pdf", "ban_ve_pdf", "A:v1:r1") == (None, "Thiếu tệp.")
    assert not (old / "state.json").exists()


def test_api_status_checks_environment_without_constructing_model(monkeypatch):
    builder = Mock(side_effect=AssertionError("unexpected client construction"))
    monkeypatch.setattr(llm, "_build", builder)
    monkeypatch.setattr(llm.importlib.util, "find_spec", lambda _: object())
    monkeypatch.setenv("LLM_PROVIDER_ARCHITECT", "openai")
    monkeypatch.setenv("LLM_TEMPERATURE_ARCHITECT", "0.2")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm.configuration_status("architect")["status"] == "Thiếu OPENAI_API_KEY"
    test_secret = "example-key-for-test"
    monkeypatch.setenv("OPENAI_API_KEY", test_secret)
    monkeypatch.setenv("LLM_MODEL_ARCHITECT", test_secret)
    status = llm.configuration_status("architect")
    assert status["status"] == "Đã cấu hình · chưa thử kết nối"
    assert status["model"] == "—" and test_secret not in str(status)
    builder.assert_not_called()
