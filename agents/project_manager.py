"""Khởi tạo lượt thiết kế, điều phối sửa và tổng hợp thuyết minh."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from agents.base import agent_node
from llm import invoke_text, llm_enabled
from monitoring.events import export_timeline
from monitoring.releases import archive_release, read_json, release_path
from tools.adjustment import find_adjustments
from tools.design_option import requires_repair
from tools.docx_writer import vn_num, write_description_docx
from tools.rules import inspect_evidence


@agent_node("project_manager")
def start(state: dict) -> dict:
    Path(state["output_dir"]).mkdir(parents=True, exist_ok=True)
    return {"route": "requirements_analyst", "_to": "requirements_analyst",
            "_summary": "Mở lượt thiết kế và giao phân tích yêu cầu",
            "_output": {"run_id": state["run_id"], "max_iterations": state["max_iterations"],
                        "fengshui_enabled": state.get("fengshui_enabled", True)}}


def outstanding(state: dict) -> list[dict]:
    return [issue for key in ("design_issues", "review_issues", "budget_issues")
            for issue in (state.get(key) or [])]


@agent_node("project_manager", stage="plan_options")
def plan_options(state: dict) -> dict:
    brief = state["brief"]
    assumed_location = any(a.startswith("Địa điểm:") for a in brief["gia_dinh_bo_sung"])
    evidence = inspect_evidence(brief["lo_dat"], assumed_location=assumed_location)
    direction = {
        "thong_tin_can_bo_sung": (state.get("brief_assessment") or {}).get("needs_confirmation", []),
        "vuong_mac_nguon": [reason for reason in evidence.blockers if reason not in evidence.input_gaps],
        "da_co_can_cu": [criterion for criterion, _ in evidence.verified],
        "huong_so_sanh": ["Cân bằng công năng", "Giảm chi phí", "Tăng khoảng thoáng nếu bố trí được"],
    }
    return {"option_brief": direction, "route": "concept_architect", "_to": "concept_architect",
            "_summary": "Giao lập các phương án sơ bộ và đối chiếu các điểm còn thiếu căn cứ",
            "_output": direction}


@agent_node("project_manager", stage="coordinate_repair")
def coordinate_repair(state: dict) -> dict:
    target = state["repair_target"]
    iteration = state["iteration"]
    issues = [issue for issue in (state.get("feedback") or []) if requires_repair(issue)]
    fallback = state["repair_fallback"]
    if not issues:
        return {"route": fallback, "feedback": [], "_to": fallback,
                "_summary": "Chuyển tiếp danh sách cần xác minh, giữ nguyên vòng sửa"}
    if iteration >= state["max_iterations"]:
        remaining = outstanding(state)
        remaining.extend(issue for issue in issues if issue not in remaining)
        return {"route": fallback, "remaining_issues": remaining, "repair_limit_reached": True,
                "outcome": "not_passed" if fallback == "end" else None,
                **({"route": "propose_adjustment"} if fallback == "end" else {}),
                "feedback": [], "_to": "project_manager" if fallback == "end" else fallback, "_feedback": True,
                "_summary": f"Hết {iteration} vòng sửa tự động",
                "_output": {"loi": issues, "vong_sua": iteration, "het_vong": True}}
    return {"route": target, "iteration": iteration + 1, "_to": target, "_feedback": True,
            "_summary": f"Giao sửa vòng {iteration + 1}/{state['max_iterations']}",
            "_output": {"dich": target, "loi": issues, "vong_sua": iteration + 1}}


@agent_node("project_manager", stage="propose_adjustment")
def propose_adjustment(state: dict) -> dict:
    """Lượt chưa đạt: thử các biến thể yêu cầu bằng công cụ bố trí và dự toán, đề xuất cách điều chỉnh khả thi."""
    issues = state.get("remaining_issues") or outstanding(state)
    proposals = find_adjustments(state["brief"]) if state.get("brief") else []
    reasons = list(dict.fromkeys(issue.get("noi_dung", "") for issue in issues if issue.get("noi_dung")))[:5]
    adjustment = {"ly_do": reasons, "de_xuat": proposals}
    if proposals:
        summary = f"Đề xuất {len(proposals)} cách điều chỉnh. Ưu tiên: {proposals[0]['tieu_de']}"
        narrative = invoke_text(
            "Bạn là chủ nhiệm đồ án kiến trúc nhà ở, giải thích ngắn gọn cho chủ nhà.",
            "Thiết kế chưa đạt vì: " + "; ".join(reasons or ["không bố trí được"]) +
            ". Các cách điều chỉnh đã kiểm tra khả thi: " + " | ".join(p["tieu_de"] for p in proposals) +
            ". Viết 2 câu (≤ 50 từ) khuyên chủ nhà nên chọn cách nào và vì sao. Không thêm con số mới.")
        if narrative and set(numeric_literals(narrative)) <= set(
                numeric_literals(" ".join([*reasons, *(p["tieu_de"] for p in proposals)]))):
            adjustment["loi_khuyen"] = narrative.strip()
    else:
        summary = "Chưa tìm được cách điều chỉnh khả thi trong phạm vi bố trí của hệ thống"
    return {"adjustment": adjustment, "route": "end", "_to": "user", "_feedback": True,
            "_summary": summary, "_output": adjustment}


def numeric_literals(text: str) -> list[str]:
    return re.findall(r"\d+(?:[.,]\d+)?", text)


def _texts(state: dict) -> dict:
    """Các đoạn văn bản tự do của thuyết minh (LLM viết lại nếu có, luôn có bản mẫu)."""
    area, layout, program = state["area_table"], state["layout"], state["program"]
    core = layout["core"]
    texts = {}
    for t in area["tang"]:
        names = []
        for ph in t["phong"]:
            if ph["loai"] in ("hanh_lang",) or ph["ten"] in names:
                continue
            names.append(ph["ten"])
        names = [n if n.startswith("WC") else n[0].lower() + n[1:] for n in names]
        base = f"bố trí lần lượt từ mặt tiền vào trong gồm {', '.join(names)}; diện tích sàn {vn_num(t['dien_tich_san'])} m²"
        texts[f"tang_{t['tang']}"] = base + "."
    texts["thong_gio"] = (
        f"Giếng trời rộng {vn_num(core['sky_w'])} m × {vn_num(core['l'])} m đặt cạnh cầu thang, xuyên suốt từ tầng 1 lên mái, "
        f"trên phủ mái kính có lam nhôm che nắng. Các phòng phía trước và phía sau lõi thang đều có cửa sổ mở ra giếng "
        f"trời hoặc mặt tiền, tạo thông gió xuyên phòng theo hiệu ứng ống khói. "
        + ("Ban công các tầng lùi 1,2 m vào trong giúp che nắng trực tiếp cho mặt tiền. " if any(
            r["loai"] == "ban_cong" for fl in layout["floors"].values() for r in fl["rooms"]) else "")
        + (f"Sân sau sâu {vn_num(layout['san_sau'])} m giúp lấy gió và ánh sáng cho phòng phía sau."
           if layout["san_sau"] > 0 else ""))
    fs = (state.get("fengshui") or {}).get("thong_tin", {})
    if fs.get("co_du_lieu"):
        texts["phong_thuy"] = (f"Gia chủ cung {fs['cung_menh']} thuộc {fs['nhom']}; nhà hướng {fs['huong_nha']} "
                               f"({fs['sao_huong_nha']}) – {'hợp mệnh' if fs['hop_huong'] else 'chưa hợp mệnh, nên bố trí cửa chính, bàn thờ và bếp quay về các hướng tốt để hóa giải'}.")
    cost = state.get("cost")
    if cost:
        texts["chi_phi"] = cost.get("ghi_chu", "")
    if llm_enabled():
        prompt = ("Viết lại các đoạn sau cho văn phong thuyết minh kiến trúc chuyên nghiệp, giữ nguyên MỌI con số, "
                  "không thêm số liệu. Trả về JSON cùng khóa.\n" + json.dumps({"thong_gio": texts["thong_gio"]}, ensure_ascii=False))
        out = invoke_text("Bạn là chủ nhiệm đồ án kiến trúc.", prompt)
        if out:
            try:
                start, end = out.index("{"), out.rindex("}") + 1
                new = json.loads(out[start:end])
                texts.update({k: v for k, v in new.items() if k == "thong_gio" and isinstance(v, str) and numeric_literals(v) == numeric_literals(texts[k])})
            except ValueError:
                pass
    return texts


@agent_node("project_manager", stage="pm_report")
def run_report(state: dict) -> dict:
    out = Path(state["output_dir"]) / "drafts" / uuid4().hex
    out.mkdir(parents=True)
    issues = outstanding(state)
    doc = write_description_docx({**state, "remaining_issues": issues}, _texts(state), out / "thuyet_minh.docx")
    drawings = state["drawings"]
    files = {"ban_ve_pdf": drawings["pdf"], "ban_ve_dxf_zip": drawings["dxf_zip"],
             "thuyet_minh_docx": str(doc), "du_toan_xlsx": state["cost_file"]}
    return {"draft_files": files, "description_file": str(doc), "remaining_issues": issues,
            "route": "final_reviewer", "_to": "final_reviewer",
            "_summary": "Tổng hợp bản vẽ, thuyết minh và dự toán để đối chiếu",
            "_output": files}


def publish(state: dict) -> dict:
    out = Path(state["output_dir"]) / "releases" / uuid4().hex
    out.mkdir(parents=True)
    files = {}
    for key, source in state["draft_files"].items():
        files[key] = str(shutil.copyfile(source, out / Path(source).name))
    shutil.copytree(state["drawings"]["dxf_dir"], out / "dxf")
    files["timeline_csv"] = str(export_timeline(state["run_id"], out / "timeline.csv"))
    archive_release({**state, "final_files": files}, out, copy_previews=True)
    # Xuất bộ tham khảo nhưng vẫn chưa đạt (vd. hết vòng sửa mà còn vượt ngân sách) -> Chủ nhiệm đề xuất điều chỉnh.
    return {"final_files": files, "route": "propose_adjustment" if state.get("outcome") == "not_passed" else "end"}


def save_snapshot(state: dict) -> None:
    out = Path(state["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    previous = read_json(out / "state.json")
    prior_release = release_path(previous, out)
    if (prior_release and prior_release.is_dir() and previous.get("run_id") == state["run_id"]
            and not (prior_release / "state.json").exists()):
        archive_release(previous, prior_release)
    snapshot = {k: v for k, v in state.items() if k not in ("events", "log", "history")}
    snapshot["history"] = []
    for entry in state.get("history") or []:
        raw = entry.get("output")
        detail = {key: raw[key] for key in ("thay_doi", "loi", "kiem_tra", "dich") if isinstance(raw, dict) and key in raw}
        snapshot["history"].append({k: v for k, v in entry.items() if k not in ("input", "output")} | {"output": detail})
    temporary = out / "state.json.tmp"
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    temporary.replace(out / "state.json")
