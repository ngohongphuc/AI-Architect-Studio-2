"""Định nghĩa trạng thái dùng chung (DesignState), sự kiện (AgentEvent) và schema brief."""
from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class AgentEvent(TypedDict, total=False):
    time: str          # "14:03:22"
    agent: str         # "reviewer"
    status: str        # "running" | "done" | "revising" | "error"
    to_agent: str      # Agent nhận việc tiếp theo
    summary: str       # "Mật độ XD 100% > 90%"
    tokens: int
    duration_s: float
    version: int       # Lần chạy thứ mấy của agent
    feedback: bool     # True nếu là phản hồi lỗi (tô đỏ trên timeline)


class DesignState(TypedDict, total=False):
    run_id: str
    user_request: str        # Yêu cầu gốc
    request_fields: dict     # Giá trị người dùng điền trong biểu mẫu
    brief_assessment: dict
    option_brief: dict
    concept_plan: dict
    interactive: bool
    fengshui_enabled: bool
    fengshui: dict
    revision_id: str
    draft_files: dict
    final_review: dict
    outcome: str
    repair_target: str
    repair_fallback: str
    repair_limit_reached: bool
    design_issues: list
    review_issues: list
    budget_issues: list
    brief: dict              # Brief có cấu trúc          (Agent 1)
    concept: str             # Ý tưởng thiết kế          (Agent 2)
    program: dict            # Danh sách phòng theo tầng (Agent 2)
    layout: dict             # Tọa độ, kích thước phòng  (Agent 3)
    area_table: dict         # Thống kê diện tích        (Agent 3)
    drawings: dict           # Đường dẫn PDF, DXF        (Agent 3)
    review: dict             # Kết quả kiểm tra          (Agent 4)
    cost: dict               # Kết quả chi phí           (Agent 5)
    cost_file: str           # Đường dẫn du_toan.xlsx    (Agent 5)
    description_file: str    # Đường dẫn thuyet_minh     (Agent 1)
    iteration: int           # Số vòng sửa hiện tại
    max_iterations: int      # Giới hạn số vòng sửa
    manual_review: bool      # Bật duyệt thủ công
    feedback: list           # Phản hồi đang chờ Kiến trúc sư xử lý
    feedback_source: str     # "reviewer" | "cost_estimator" | "user"
    task_retry: dict          # Lý do và nhóm nguyên nhân của nhánh cần thực hiện lại
    route: str               # Nhánh tiếp theo do agent quyết định
    remaining_issues: list   # Lỗi còn tồn tại khi hết số vòng sửa
    adjustment: dict         # Đề xuất điều chỉnh yêu cầu của Chủ nhiệm khi lượt chưa đạt
    versions: dict           # Số lần chạy của từng agent
    output_dir: str
    final_files: dict
    approval_points: list    # các agent cần duyệt thủ công sau khi chạy xong
    options: list            # các phương án Kiến trúc sư đề xuất để chủ nhà chọn
    option_versions: dict
    recommended_option: str
    selected_by_user: bool
    agent_settings: dict     # Bản chụp model theo agent + agent tùy biến lúc bắt đầu lượt
    custom_outputs: dict     # Nhận xét của agent tùy biến, theo mã agent
    trao_doi: Annotated[list, operator.add]  # hội thoại chủ nhà ↔ kiến trúc sư
    log: Annotated[list, operator.add]       # Nhật ký hoạt động các agent
    events: Annotated[list, operator.add]    # Danh sách AgentEvent
    history: Annotated[list, operator.add]   # Đầu ra từng phiên bản (so sánh v1, v2, v3)


# ---------------------------------------------------------------------------
# Schema brief (dùng cho structured output của LLM và kiểm tra dữ liệu)
# ---------------------------------------------------------------------------
class LoDat(BaseModel):
    rong: float = Field(gt=0, allow_inf_nan=False, description="Chiều rộng mặt tiền lô đất (m)")
    dai: float = Field(gt=0, allow_inf_nan=False, description="Chiều sâu lô đất (m)")
    huong: str = Field("Nam", description="Hướng mặt tiền: Bắc, Nam, Đông, Tây, Đông Nam, ...")
    tinh: str = Field("Hà Nội", description="Tỉnh/thành phố")
    ma_lo_dat: str | None = Field(None, description="Mã lô đất nếu người dùng cung cấp")


class GiaDinh(BaseModel):
    so_nguoi: int = Field(4, gt=0)
    nam_sinh_chu_nha: Optional[int] = Field(None, description="Năm sinh chủ nhà (người đứng tên)")
    gioi_tinh_chu_nha: str = Field("nam", description="nam | nữ")
    nam_sinh_thanh_vien: list[int] = Field(default_factory=list)


class YeuCauPhong(BaseModel):
    phong_ngu: int = Field(3, ge=1, le=12)
    phong_tho: int = Field(0, ge=0)
    gara: Optional[Literal["xe máy", "ô tô"]] = Field(None, description="'xe máy' | 'ô tô' | None")
    phong_lam_viec: int = Field(0, ge=0)
    so_tang: Optional[int] = Field(None, ge=1, le=5, description="Số tầng nếu khách yêu cầu")


class Brief(BaseModel):
    lo_dat: LoDat
    gia_dinh: GiaDinh = Field(default_factory=GiaDinh)
    yeu_cau_phong: YeuCauPhong = Field(default_factory=YeuCauPhong)
    ngan_sach: int = Field(gt=0, description="Ngân sách (VNĐ)")
    phong_cach: str = "hiện đại"
    yeu_cau_khac: list[str] = Field(default_factory=list)
    gia_dinh_bo_sung: list[str] = Field(default_factory=list, description="Các giả định tự điền khi thiếu thông tin")


class BriefAssessment(BaseModel):
    questions: list[str]
    conflicts: list[str]
    needs_confirmation: list[str] = Field(default_factory=list)


class RequestFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rong: float | None = Field(None, gt=0, allow_inf_nan=False)
    dai: float | None = Field(None, gt=0, allow_inf_nan=False)
    tinh: str | None = None
    ma_lo_dat: str | None = Field(None, pattern=r"^[^\s,;!]+$")
    so_tang: int | None = Field(None, ge=1, le=5)
    so_nguoi: int | None = Field(None, gt=0)
    phong_ngu: int | None = Field(None, ge=1, le=12)
    ngan_sach: int | None = Field(None, gt=0)


class ConceptPlan(BaseModel):
    so_tang: int = Field(ge=1, le=5)
    phong_cach: str
    vat_lieu: dict[str, str]
    thong_gio: list[str]
    chieu_sang: list[str]


class DesignIssue(BaseModel):
    ma: str
    muc: str
    noi_dung: str
    target: str | None = None


class FinalReview(BaseModel):
    dat: bool
    loi: list[DesignIssue]


class VerifiedRule(BaseModel):
    muc: str
    tinh: str
    ma_lo_dat: str
    nguong: str
    nguon: str = Field(min_length=1)
    pham_vi: str = Field(min_length=1)
    tai_lieu: str
    trang: int = Field(ge=1)
    trich: str = Field(min_length=10)
