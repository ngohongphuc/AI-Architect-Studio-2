"""Điểm gắn component Streamlit. Cảnh và tương tác chạy trong trình duyệt."""
from pathlib import Path

import streamlit.components.v1 as components

_studio = components.declare_component("architect_office_3d", path=str(Path(__file__).parent / "frontend"))


def show(data: dict, *, mode: str = "live") -> dict | None:
    return _studio(data=data, mode=mode, key="architect_office_3d", default=None)
