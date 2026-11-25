"""Cấu hình chung của AI Architect Studio."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
MONITOR_DIR = ROOT / "monitoring"
# Có thể đổi nơi lưu dữ liệu chạy (vd. kiểm thử dùng thư mục tạm, không ghi vào dự án thật).
_STATE_DIR = os.environ.get("ARCHITECT_STATE_DIR")
OUTPUT_DIR = Path(_STATE_DIR) / "outputs" if _STATE_DIR else ROOT / "outputs"
LOG_DB = Path(_STATE_DIR) / "logs.db" if _STATE_DIR else MONITOR_DIR / "logs.db"
CHECKPOINT_DB = Path(_STATE_DIR) / "checkpoints.db" if _STATE_DIR else MONITOR_DIR / "checkpoints.db"
# Cấu hình model và agent tùy biến chỉnh trên giao diện Quản lý agent (không chứa khóa API).
AGENT_SETTINGS_FILE = Path(_STATE_DIR) / "agent_settings.json" if _STATE_DIR else DATA_DIR / "agent_settings.json"
RULES_FILE = DATA_DIR / "rules.json"
PRICE_FILE = DATA_DIR / "don_gia.xlsx"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Đọc file .env đơn giản (KEY=VALUE), không ghi đè biến đã có."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()

# Tổng số vòng sửa tối đa (vòng quy chuẩn + vòng ngân sách)
MAX_ITERATIONS = min(3, max(0, int(os.getenv("MAX_ITERATIONS", "3"))))
# Ngưỡng vượt ngân sách để quay lại Kiến trúc sư
BUDGET_TOLERANCE = 0.10

PROJECT_NAME = "AI Architect Studio"

AGENT_LABELS = {
    "project_manager": "Chủ nhiệm dự án",
    "requirements_analyst": "Phân tích yêu cầu",
    "concept_architect": "Kiến trúc sư ý tưởng",
    "architect": "Thiết kế công năng",
    "drafter": "Triển khai bản vẽ",
    "fengshui_advisor": "Tư vấn phong thủy",
    "reviewer": "Kiểm định quy chuẩn",
    "cost_estimator": "Dự toán chi phí",
    "final_reviewer": "Kiểm tra hồ sơ cuối",
    "user": "Người dùng",
}
AGENT_ORDER = [agent for agent in AGENT_LABELS if agent != "user"]
