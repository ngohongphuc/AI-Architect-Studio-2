"""Biểu đồ công việc cục bộ, chạy bên trong Streamlit."""
from pathlib import Path

from streamlit.components.v1 import declare_component

_chart = declare_component("task_timeline", path=str(Path(__file__).parent / "frontend"))


def show(data: dict, *, run_id: str, tones: dict, statuses: dict, marks: dict) -> dict | None:
    return _chart(data=data, tones=tones, statuses=statuses, marks=marks, key=f"timeline_{run_id}", default=None)
