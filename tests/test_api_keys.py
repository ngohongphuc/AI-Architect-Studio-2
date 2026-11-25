"""Nhập / gỡ khóa API từ giao diện: ghi .env tạm, không đụng tệp .env thật của dự án."""
import os
import stat

import pytest

import api_keys
import llm
from monitoring.redaction import redact

KEY = "AIzaTestKey_1234567890abcdefghijklmno"


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("# ghi chú\nLLM_PROVIDER=openai\nGOOGLE_API_KEY=old-value-000000000\nOTHER=1\n", encoding="utf-8")
    monkeypatch.setattr(api_keys, "ENV_FILE", path)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    yield path
    os.environ.pop("GOOGLE_API_KEY", None)


def test_set_key_replaces_line_and_applies_now(env_file):
    api_keys.set_key("gemini", f"  {KEY}  ")
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert lines == ["# ghi chú", "LLM_PROVIDER=openai", f"GOOGLE_API_KEY={KEY}", "OTHER=1"]
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert os.environ["GOOGLE_API_KEY"] == KEY
    info = api_keys.status("gemini")
    assert info == {"env": "GOOGLE_API_KEY", "set": True, "hint": "…lmno", "source": ".env"}
    assert KEY not in str(info) and KEY not in redact(f"lỗi gọi model với khóa {KEY}")


def test_remove_key(env_file):
    api_keys.set_key("gemini", KEY)
    assert api_keys.remove_key("gemini")
    assert "GOOGLE_API_KEY" not in env_file.read_text(encoding="utf-8")
    assert "GOOGLE_API_KEY" not in os.environ and not api_keys.status("gemini")["set"]


@pytest.mark.parametrize("value", ["", "short", "có dấu cách 1234567890", "abc\nLLM_PROVIDER=none1234567"])
def test_invalid_key_rejected(env_file, value):
    before = env_file.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        api_keys.set_key("gemini", value)
    assert env_file.read_text(encoding="utf-8") == before


def test_new_key_rebuilds_client(env_file, monkeypatch):
    llm._exhausted.add(("gemini", "gemini-2.5-flash"))
    api_keys.set_key("gemini", KEY)
    assert ("gemini", "gemini-2.5-flash") not in llm._exhausted
    assert llm._build.cache_info().currsize == 0


def test_ollama_needs_no_key():
    assert api_keys.status("ollama")["set"] is True
    with pytest.raises(ValueError):
        api_keys.set_key("ollama", KEY)
