"""Trình xem tờ bản vẽ đã kiểm tra phiên bản."""
from base64 import b64encode
from pathlib import Path

from streamlit.components.v1 import declare_component

_viewer = declare_component("drawing_viewer", path=str(Path(__file__).with_name("frontend")))


def show(clear_id: str, png: bytes, title: str) -> None:
    _viewer(source="data:image/png;base64," + b64encode(png).decode("ascii"),
            title=title, key=clear_id)
