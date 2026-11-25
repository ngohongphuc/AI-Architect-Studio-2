"""Chốt chặn hai ứng dụng cùng chạy và ứng dụng còn giữ mã cũ."""
import subprocess
import sys
import types

import pytest

import app_guard
from config import ROOT


@pytest.mark.skipif(app_guard.fcntl is None, reason="Windows không có fcntl")
def test_second_process_is_reported():
    assert app_guard.other_instance() == "" and app_guard.other_instance() == ""
    result = subprocess.run([sys.executable, "-c", "import os, app_guard; print(app_guard.other_instance(), os.getppid())"],
                            cwd=ROOT, capture_output=True, text=True, check=True)
    owner, parent = result.stdout.split()
    assert owner == parent                      # tiến trình thứ hai nêu đúng PID đang giữ khóa


def test_changed_module_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(app_guard, "ROOT", tmp_path)
    source = tmp_path / "demo_module.py"
    source.write_text("x = 1\n", encoding="utf-8")
    module = types.ModuleType("demo_module")
    module.__file__ = str(source)
    monkeypatch.setitem(sys.modules, "demo_module", module)
    assert app_guard.stale_modules() == []
    import os

    os.utime(source, ns=(1, 1))
    assert app_guard.stale_modules() == ["demo_module.py"]
    reloaded = types.ModuleType("demo_module")  # Streamlit nạp lại module thì hết cảnh báo
    reloaded.__file__ = str(source)
    monkeypatch.setitem(sys.modules, "demo_module", reloaded)
    assert app_guard.stale_modules() == []
