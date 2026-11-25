"""Test luôn chạy chế độ quy tắc (không gọi API thật) để nhanh, ổn định và không tốn quota."""
import atexit
import os
import shutil
import tempfile

# Kiểm thử ghi lượt thiết kế, checkpoint và hồ sơ vào thư mục tạm, không đụng dữ liệu dự án thật.
if not os.environ.get("ARCHITECT_STATE_DIR"):
    _state_dir = tempfile.mkdtemp(prefix="architect-tests-")
    os.environ["ARCHITECT_STATE_DIR"] = _state_dir
    atexit.register(shutil.rmtree, _state_dir, ignore_errors=True)
os.environ["LLM_PROVIDER"] = "none"
for _agent in ("PROJECT_MANAGER", "REQUIREMENTS_ANALYST", "CONCEPT_ARCHITECT", "ARCHITECT",
               "DRAFTER", "REVIEWER", "FENGSHUI_ADVISOR", "COST_ESTIMATOR", "FINAL_REVIEWER"):
    os.environ[f"LLM_PROVIDER_{_agent}"] = "none"
os.environ["USE_CHROMA"] = "0"
