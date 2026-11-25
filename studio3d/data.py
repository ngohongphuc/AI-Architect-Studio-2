"""Chuyển trạng thái và sự kiện thật thành dữ liệu hiển thị của sa bàn."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from agents.base import describe_input
from config import AGENT_LABELS, AGENT_ORDER
from graph import NODE_AGENT
from tools.review_display import MISSING, issue_label, preliminary_ready, quality_status, review_rows


ROOMS = (
    {"id": "management", "name": "Điều hành", "description": "Điều phối tiến độ, vòng sửa và tổng hợp hồ sơ."},
    {"id": "reception", "name": "Tiếp nhận", "description": "Tiếp nhận yêu cầu và làm rõ dữ liệu đầu vào."},
    {"id": "design", "name": "Thiết kế", "description": "Phát triển ý tưởng kiến trúc và chương trình công năng."},
    {"id": "drawing", "name": "Bản vẽ", "description": "Triển khai hình học mặt bằng, PDF và DXF."},
    {"id": "review", "name": "Thẩm định", "description": "Kiểm định kỹ thuật và tư vấn phong thủy theo tùy chọn."},
    {"id": "finance", "name": "Tài chính", "description": "Đối chiếu khối lượng, đơn giá và ngân sách."},
    {"id": "archive", "name": "Kiểm soát hồ sơ", "description": "Đối chiếu và kiểm tra bộ hồ sơ trước khi xuất."},
)


@dataclass(frozen=True)
class Desk:
    room: str
    short: str
    color: str
    task: str
    outputs: tuple[str, ...]
    issue_fields: tuple[str, ...] = ()


DESKS = {
    "project_manager": Desk("management", "Chủ nhiệm", "#1a786e",
                            "Điều phối lượt thiết kế, giao vòng sửa và tổng hợp thuyết minh.",
                            ("draft_files", "final_files")),
    "requirements_analyst": Desk("reception", "Tiếp nhận", "#ba683c",
                                 "Chuẩn hóa yêu cầu, ghi giả định và hỏi lại khi thiếu dữ liệu.",
                                 ("brief", "brief_assessment")),
    "concept_architect": Desk("design", "Ý tưởng", "#8455a3",
                              "Đề xuất quy mô, vật liệu, thông gió và chiếu sáng.",
                              ("concept_plan", "concept")),
    "architect": Desk("design", "Công năng", "#2d8a8d",
                      "Chia phòng theo tầng và điều chỉnh vị trí, diện tích theo phản hồi.",
                      ("program", "options")),
    "drafter": Desk("drawing", "Triển khai", "#3a699f",
                    "Tính hình học, lập bảng diện tích và xuất bản vẽ PDF/DXF.",
                    ("drawings", "area_table"), ("design_issues",)),
    "reviewer": Desk("review", "Quy chuẩn", "#ad5367",
                     "Kiểm tra hình học, nguồn và phạm vi áp dụng của các tiêu chí.",
                     ("review",), ("review_issues",)),
    "fengshui_advisor": Desk("review", "Phong thủy", "#638443",
                             "Gợi ý phong thủy khi được bật cho lượt thiết kế.",
                             ("fengshui",)),
    "cost_estimator": Desk("finance", "Dự toán", "#aa751d",
                           "Tính chi phí, so sánh với ngân sách và xuất bảng XLSX.",
                           ("cost", "cost_file"), ("budget_issues",)),
    "final_reviewer": Desk("archive", "Hồ sơ", "#525c85",
                           "Đối chiếu brief và các tệp PDF/DXF, DOCX, XLSX trước khi bàn giao.",
                           ("final_review", "remaining_issues")),
}


def _finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def project_geometry(state: dict) -> dict | None:
    """Lấy cao độ và khối phòng từ layout hiện hành, giữ nguyên tỷ lệ các trục."""
    layout = state.get("layout") or {}
    building = layout.get("building") or {}
    x, y, width, depth = (building.get(key) for key in ("x", "y", "w", "l"))
    heights = layout.get("heights") or []
    floors = layout.get("floors") or {}
    if (not all(_finite_number(value) for value in (x, y, width, depth))
            or width <= 0 or depth <= 0
            or not heights or len(heights) != len(floors) or len(heights) != layout.get("so_tang")
            or not all(_finite_number(h) and h > 0 for h in heights)):
        return None
    result = []
    for index, height in enumerate(heights, 1):
        floor = floors.get(str(index)) or {}
        rooms = []
        for room in floor.get("rooms", []):
            rx, ry, rw, rd = (room.get(key) for key in ("x", "y", "w", "h"))
            if not all(_finite_number(value) for value in (rx, ry, rw, rd)) or rw <= 0 or rd <= 0:
                return None
            in_footprint = (rx >= x - 0.002 and ry >= y - 0.002
                            and rx + rw <= x + width + 0.002 and ry + rd <= y + depth + 0.002)
            if not in_footprint:
                if room.get("loai") == "san":  # sân ngoài nhà không thuộc khối trưng bày
                    continue
                return None
            rooms.append({"x": rx - x, "z": ry - y, "w": rw, "d": rd, "kind": room.get("loai")})
        if not rooms:
            return None
        result.append({"height": height, "rooms": rooms})
    return {"width": width, "depth": depth, "floors": result}


def _target(node: str) -> str | None:
    if node == "publish":
        return "showcase"
    target = NODE_AGENT.get(node, node)
    return target if target in DESKS else None


def _issues(agent: str, state: dict, latest: dict) -> list[str]:
    if agent == "requirements_analyst":
        assessment = state.get("brief_assessment") or {}
        messages = [*assessment.get("conflicts", []), *assessment.get("questions", [])]
    else:
        messages = [f"{issue_label(issue)} · {issue['noi_dung']}" for field in DESKS[agent].issue_fields
                    for issue in state.get(field) or [] if issue.get("noi_dung")]
    if agent == "final_reviewer":
        messages.extend(issue["noi_dung"] for issue in (state.get("final_review") or {}).get("loi", []))
    if latest.get("status") == "error" or (latest.get("feedback") and not messages):
        messages.append(latest["summary"])
    return list(dict.fromkeys(messages))


def _quality(state: dict, checks: list[dict]) -> dict:
    findings = [row for row in checks if row["tone"] in ("warning", "error")]
    titles = {row["criterion"] for row in findings}
    for issue in state.get("remaining_issues") or []:
        if issue.get("muc") in titles or (issue.get("ma") == "THIEU_CAN_CU" and any(
                row["status"] == MISSING for row in findings)):
            continue
        advisory = (issue.get("ma") in ("THIEU_CAN_CU", "VUOT_NGAN_SACH")
                    or issue.get("phan_loai") in ("tham_chieu", "thieu_can_cu", "thieu_nguon", "thieu_thong_tin"))
        findings.append({"criterion": issue.get("muc") or "Vấn đề cần xử lý", "status": issue_label(issue),
                         "tone": "warning" if advisory else "error",
                         "source": issue.get("nguon"), "scope": issue.get("pham_vi"), "reason": issue.get("noi_dung")})
    return {**quality_status(state), "preliminary": preliminary_ready(state),
            "unverified": sum(row["status"] == MISSING for row in checks), "findings": findings}


def _transfers(event_rows: list[dict], approval_points: list[str], status: str, current: str | None) -> list[dict]:
    transfers = []
    for event in event_rows:
        source = event["agent"]
        target = _target(event.get("to_agent") or "")
        pending = transfers[-1] if transfers and transfers[-1].get("pending") else None
        if source == "user" and pending and event["status"] == "done":
            if target == pending["from"]:  # chỉnh phương án tại điểm duyệt hiện tại
                continue
            transfers.pop()
            if target:
                summary = event["summary"]
                if target == pending["to"] and summary.startswith("Đồng ý:"):
                    summary = pending["summary"]
                transfers.append({"id": event["id"], "from": pending["from"], "to": target,
                                  "time": event["time"], "summary": summary, "approved": True,
                                  "feedback": pending["feedback"] and pending["to"] == target})
        elif pending and source == pending["to"] and event["status"] in ("running", "revising"):
            # Các lượt cũ có thể chỉ ghi nhận người nhận bắt đầu xử lý.
            pending.update(id=event["id"], pending=False, time=event["time"])
        elif event["status"] == "done" and source in DESKS and target and target != source:
            stage = source
            if source == "project_manager" and target != "requirements_analyst":
                stage = "pm_report" if target == "final_reviewer" else "coordinate_repair"
            transfers.append({"id": event["id"], "from": source, "to": target, "time": event["time"],
                              "summary": event["summary"], "feedback": bool(event["feedback"]),
                              "pending": stage in approval_points})
    if transfers and status == "awaiting_approval" and transfers[-1]["from"] == current:
        transfers[-1]["pending"] = True
    return transfers[-100:]


def office_data(state: dict, event_rows: list[dict], stats: dict, *,
                run_id: str | None, status: str, current: str | None) -> dict:
    latest_events = {row["agent"]: row for row in event_rows}
    history = {item["agent"]: item for item in state.get("history") or []}
    agents = []
    checks = review_rows(state.get("review") or {}, state.get("brief"))
    for agent in AGENT_ORDER:
        desk = DESKS[agent]
        latest = latest_events.get(agent, {})
        info = stats.get(agent, {})
        step = latest.get("status", "waiting")
        if agent == "fengshui_advisor" and state.get("fengshui_enabled") is False:
            step = "skipped"
        elif agent == current and status in ("awaiting_approval", "needs_input"):
            step = status
        elif step in ("running", "revising") and status != "running":
            step = status if status in ("paused", "stopped", "error") else "waiting"
        elif step == "done" and latest.get("feedback"):
            step = "feedback"

        previous = history.get(agent, {})
        # Một phiên bản đang chạy có đầu vào riêng. Đầu ra bên dưới là dữ liệu hiện hành
        # hoặc bản ghi của phiên bản gần nhất đã hoàn tất.
        params = (describe_input(agent, state) if step in ("running", "revising")
                  else previous.get("input") or (describe_input(agent, state) if latest else {}))
        output = {key: state[key] for key in desk.outputs if state.get(key) is not None}
        if not output and previous.get("output") is not None:
            output = {"phien_ban_gan_nhat": previous["output"]}
        agents.append({
            "id": agent, "room": desk.room, "name": AGENT_LABELS[agent], "short": desk.short,
            "color": desk.color, "task": desk.task, "status": step, "input": params, "output": output,
            "issues": _issues(agent, state, latest), "summary": (
                latest.get("summary") if step in ("running", "revising", "error")
                else info.get("last") or previous.get("summary") or latest.get("summary")),
            "runs": info.get("runs") if latest else None,
            "duration": info.get("duration") if info.get("runs") else None,
            "version": latest.get("version") or previous.get("version"),
            "tokens": info.get("tokens") if info.get("runs") else None,
            "feedback_count": info.get("errors") if info.get("runs") else None,
        })

    transfers = _transfers(event_rows, state.get("approval_points") or [], status, current)
    cost = state.get("cost") or {}
    amounts = [row["thanh_tien"] for row in cost.get("hang_muc") or []
               if _finite_number(row.get("thanh_tien")) and row["thanh_tien"] >= 0]
    return {"rooms": ROOMS, "agents": agents, "transfers": transfers, "geometry": project_geometry(state),
            "quality": _quality(state, checks),
            "cost_amounts": amounts, "run": {"id": run_id, "status": status, "current": current,
                                              "fengshui_enabled": state.get("fengshui_enabled"),
                                              "iteration": state.get("iteration"),
                                              "max_iterations": state.get("max_iterations")}}
