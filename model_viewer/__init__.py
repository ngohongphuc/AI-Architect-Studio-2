"""Trình xem mô hình 3D: hiển thị chính tệp GLB của hồ sơ, đã kiểm tra phiên bản."""
from base64 import b64encode
from pathlib import Path

from streamlit.components.v1 import declare_component

_viewer = declare_component("model_viewer", path=str(Path(__file__).with_name("frontend")))


def show(key: str, glb: bytes) -> None:
    _viewer(glb=b64encode(glb).decode("ascii"), key=key, default=None)
