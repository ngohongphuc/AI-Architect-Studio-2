"""Nội dung tin nhắn Telegram (văn bản thuần) từ dữ liệu của lượt."""
from __future__ import annotations

from pathlib import Path

from config import AGENT_LABELS, AGENT_ORDER
from graph import APPROVALS
from monitoring.redaction import redact
from monitoring.tasks import STAGES
from tools.docx_writer import vn_num, vnd

STATUS = {"running": "Đang chạy", "awaiting_approval": "Chờ bạn duyệt", "needs_input": "Cần bổ sung yêu cầu",
          "paused": "Tạm dừng", "done": "Đã hoàn thành", "not_passed": "Chưa đạt", "stopped": "Đã dừng",
          "error": "Gặp lỗi", "idle": "Chưa chạy"}
FILES = (("ban_ve_pdf", "Bộ bản vẽ"), ("ban_ve_dxf_zip", "Bản vẽ AutoCAD"), ("mo_hinh_3d_glb", "Mô hình 3D"),
         ("mo_hinh_3d_dxf", "Mô hình 3D cho AutoCAD"), ("thuyet_minh_docx", "Thuyết minh"), ("du_toan_xlsx", "Dự toán"))

HELP = ("AI Architect Studio\n\n"
        "Gửi yêu cầu thiết kế bằng tin nhắn thường, ví dụ:\n"
        "Đất 5x20 m ở Hà Nội, hướng Đông Nam, 4 người, 3 phòng ngủ, ngân sách 3 tỷ.\n\n"
        "/trangthai – agent nào đang làm, đang rảnh\n"
        "/agent – giao lại việc cho một agent\n"
        "/duyet – mở lại điểm duyệt đang chờ\n"
        "/hoso – nhận lại bộ hồ sơ\n"
        "/duan – các lượt bạn đã giao\n"
        "/tamdung, /tieptuc, /dung – điều khiển lượt\n"
        "/id – xem mã tài khoản Telegram của bạn")


def clip(text, limit: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def step_name(node: str | None) -> str:
    if not node or node == "end":
        return "Kết thúc"
    if node in STAGES:
        return STAGES[node].name
    return next((title for name, title in APPROVALS.values() if name == node), AGENT_LABELS.get(node, node))


def agent_name(agent: str, state: dict | None = None) -> str:
    if agent in AGENT_LABELS:
        return AGENT_LABELS[agent]
    custom = ((state or {}).get("agent_settings") or {}).get("custom_agents") or []
    return next((item["name"] for item in custom if item["id"] == agent), agent)


def agent_lines(run, state: dict, rows: list[dict]) -> list[str]:
    """Trạng thái từng agent, cùng cách gọi với bảng Trạng thái agent trên web."""
    latest = {row["agent"]: row for row in rows if row["agent"] != "user"}
    current = run.step()[1]
    active = run.status in ("running", "paused", "awaiting_approval", "needs_input")
    custom = [item["id"] for item in (state.get("agent_settings") or {}).get("custom_agents") or []]
    lines = []
    for agent in [*AGENT_ORDER, *custom]:
        status = latest.get(agent, {}).get("status")
        if agent == "fengshui_advisor" and state.get("fengshui_enabled") is False:
            mark, text = "➖", "Đã tắt"
        elif agent == current and run.status in ("awaiting_approval", "needs_input"):
            mark, text = "🟡", "Chờ bạn"
        elif agent == current and run.status == "paused":
            mark, text = "⏸", "Tạm dừng"
        elif status in ("running", "revising") and run.status == "running":
            mark, text = "⏳", "Đang sửa lại" if status == "revising" else "Đang làm việc"
        elif status == "error":
            mark, text = "❌", "Gặp lỗi"
        elif status == "done":
            mark, text = "✅", "Rảnh, đã xong việc được giao"
        else:
            mark, text = "▫️", "Chờ đến lượt" if active else "Rảnh"
        lines.append(f"{mark} {agent_name(agent, state)}: {text}")
    return lines


def progress(run, state: dict, rows: list[dict]) -> str:
    return redact("\n".join([f"Lượt {run.run_id} · {STATUS.get(run.status, run.status)}",
                             *([f"Vòng sửa {state['iteration']}/{state['max_iterations']}"] if state.get("iteration") else []),
                             "", *agent_lines(run, state, rows)]))


def approval(payload: dict) -> str:
    agent, lines = payload.get("agent"), [f"🟡 {payload.get('title', 'Chờ duyệt')}", ""]
    brief = payload.get("brief") or {}
    if agent == "requirements_analyst" and brief:
        lot, rooms = brief.get("lo_dat") or {}, brief.get("yeu_cau_phong") or {}
        lines += [f"Lô đất: {vn_num(lot.get('rong') or 0, 1)} × {vn_num(lot.get('dai') or 0, 1)} m, hướng {lot.get('huong', '—')}, {lot.get('tinh', '—')}",
                  f"Phòng ngủ: {rooms.get('phong_ngu', '—')} · Phòng thờ: {rooms.get('phong_tho', '—')} · "
                  f"Số tầng: {rooms.get('so_tang') or 'chưa chốt'}",
                  f"Ngân sách: {vnd(brief['ngan_sach'])}" if brief.get("ngan_sach") else "Ngân sách: chưa có"]
        lines += [f"• Giả định: {clip(note, 200)}" for note in (brief.get("gia_dinh_bo_sung") or [])[:5]]
    elif agent == "architect":
        for option in payload.get("options") or []:
            numbers = option.get("chi_so") or {}
            mark = "⭐ " if option["id"] == payload.get("recommended_option") else ""
            if option.get("eligible") and numbers.get("chi_phi") is not None:
                lines.append(f"{mark}{option['ten']}: {numbers['so_tang']} tầng, {vn_num(numbers['tong_dien_tich_san'])} m² sàn, "
                             f"{vnd(numbers['chi_phi'])} ({numbers['vuot_pct'] * 100:+.1f}% ngân sách)")
            else:
                lines.append(f"{option['ten']}: chưa đủ điều kiện triển khai")
    elif payload.get("area"):
        area = payload["area"]
        lines.append(f"{area['so_tang']} tầng · {vn_num(area['tong_dien_tich_san'])} m² sàn · mật độ {vn_num(area['mat_do'] * 100)}%")
    elif payload.get("review"):
        review = payload["review"]
        lines += [clip(review.get("nhan_xet"), 900), *(f"• {clip(i.get('noi_dung'), 200)}" for i in (review.get("loi") or [])[:6])]
    elif payload.get("cost"):
        cost = payload["cost"]
        lines += [f"Tổng chi phí: {vnd(cost['tong_chi_phi'])} ({cost['vuot_pct'] * 100:+.1f}% ngân sách)", clip(cost.get("ghi_chu"), 700)]
    elif agent == "concept_architect":
        lines.append(clip(payload.get("concept") or (payload.get("output") or {}).get("phong_cach"), 900))
    elif agent == "pm_report":
        lines.append("Đã tổng hợp bản vẽ, mô hình 3D, thuyết minh và dự toán.")
    for note in payload.get("custom_notes") or []:
        if note.get("status") == "done":
            lines += ["", f"Ý kiến {note['name']}: {clip(note.get('text'), 500)}"]
    reasons = [item for item in payload.get("feedback") or [] if item]
    if payload.get("next") == "coordinate_repair":
        lines += ["", "Kết quả này cần sửa:", *(f"• {clip(item, 250)}" for item in reasons[:5])]
    lines += ["", f"Nếu đồng ý, bước tiếp theo: {step_name(payload.get('next'))}."]
    return redact("\n".join(line for line in lines if line is not None))


def clarification(payload: dict) -> tuple[str, bool]:
    """(nội dung, phải viết lại toàn bộ). Yêu cầu mâu thuẫn thì bổ sung thêm không gỡ được mâu thuẫn."""
    info = payload["clarification"]
    conflicts = info.get("conflicts") or []
    lines = ["❓ Cần bạn xác nhận yêu cầu thiết kế", "", *(f"• {note}" for note in [*conflicts, *(info.get("questions") or [])]), ""]
    if conflicts:
        lines += ["Yêu cầu có chỗ mâu thuẫn. Hãy gửi lại toàn bộ yêu cầu đã sửa.", "", f"Yêu cầu hiện tại: {payload.get('user_request', '')}"]
    else:
        lines.append("Hãy nhắn phần còn thiếu, tôi sẽ ghép vào yêu cầu hiện tại.")
    return redact("\n".join(lines)), bool(conflicts)


def result(run, state: dict) -> str:
    head = {"done": "✅ Đã hoàn thành hồ sơ sơ bộ", "not_passed": "⚠️ Lượt thiết kế chưa đạt", "stopped": "⏹ Lượt đã dừng",
            "error": "❌ Lượt gặp lỗi", "paused": "⏸ Lượt đang tạm dừng"}.get(run.status, STATUS.get(run.status, run.status))
    lines = [f"{head} · {run.run_id}"]
    area, cost = state.get("area_table") or {}, state.get("cost") or {}
    if run.status in ("done", "not_passed"):
        if area:
            lines.append(f"{area['so_tang']} tầng · {vn_num(area['tong_dien_tich_san'])} m² sàn")
        if cost:
            lines.append(f"Dự toán {vnd(cost['tong_chi_phi'])} ({cost['vuot_pct'] * 100:+.1f}% ngân sách)")
        issues = [i.get("noi_dung") for i in state.get("remaining_issues") or [] if i.get("noi_dung")]
        if issues:
            lines += ["", "Cần xem lại hoặc xác minh:", *(f"• {clip(i, 220)}" for i in issues[:8])]
            if len(issues) > 8:
                lines.append(f"… và {len(issues) - 8} mục khác trên web.")
    if run.status == "not_passed":
        for index, item in enumerate((state.get("adjustment") or {}).get("de_xuat") or [], 1):
            lines += ["", f"Đề xuất {index}: {item['tieu_de']} – {vnd(item['chi_phi'])}"]
            if item.get("can_xac_nhan"):
                lines.append("Đề xuất này đổi kích thước lô, chỉ chọn khi đúng thực tế.")
    if run.status == "error":
        lines.append("Dùng /agent để giao agent làm lại, hoặc mở web để xem chi tiết.")
    if run.status == "paused":
        lines.append("Dùng /tieptuc để chạy tiếp hoặc /dung để dừng hẳn.")
    return redact("\n".join(lines))


def _inside(value, root: Path) -> Path | None:
    try:
        path = Path(value).resolve()
    except (OSError, TypeError, ValueError):
        return None
    return path if path.is_relative_to(root) and path.is_file() else None


def documents(state: dict) -> list[tuple[Path, str]]:
    root, files = Path(state.get("output_dir") or "/nonexistent").resolve(), state.get("final_files") or {}
    found = [(_inside(files.get(key), root), title) for key, title in FILES]
    return [(path, title) for path, title in found if path]


def previews(state: dict) -> list[tuple[Path, str]]:
    root = Path(state.get("output_dir") or "/nonexistent").resolve()
    found = [(_inside(s.get("png"), root), f"{s['so_hieu']} · {s['ten']}") for s in (state.get("drawings") or {}).get("sheets") or []
             if s["ten"].startswith(("Mặt bằng tầng", "Phối cảnh"))]
    return [item for item in found if item[0]][:10]


