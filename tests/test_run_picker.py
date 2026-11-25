"""Lượt đang xem không bị thay bằng giá trị lạc khi nhãn ô chọn dự án đổi (vd. sau bước duyệt)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from graph import APPROVALS
from monitoring.runner import manager

REQUEST = "Lô đất 5x20m, mặt tiền hướng Đông Nam, tại Hà Nội. Gia đình 5 người. Cần 4 phòng ngủ. Ngân sách 3 tỷ."


def test_unknown_run_id_falls_back_to_real_run_and_header_shows_next_step():
    run = manager.start(REQUEST, approval_points=list(APPROVALS))
    run.thread.join()
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90)
    at.session_state["run_id"] = "Lô đất 5x20m, mặt tiền hướng Đông Nam"  # nhãn hiển thị lạc vào session
    at.run()
    at.switch_page("views/studio.py").run()
    assert not at.exception
    assert at.session_state["run_id"] == run.run_id
    header = next(body for element in at.get("html") if "aa-studio-run" in (body := element.proto.body))
    assert "Chờ bạn duyệt" in header and "Tiếp theo" in header and "Phân tích yêu cầu" in header
