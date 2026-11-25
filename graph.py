"""Điều phối chín agent, điểm duyệt và các bước tái tạo hồ sơ."""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

import agent_settings
from agents import (architect, concept_architect, cost_estimator, custom_agent, drafter, fengshui_advisor,
                    final_reviewer, project_manager, requirements_analyst, reviewer)
from config import AGENT_LABELS, AGENT_ORDER, CHECKPOINT_DB, MAX_ITERATIONS, OUTPUT_DIR
from monitoring import events, tasks
from monitoring.redaction import redact
from state import DesignState
from tools.brief_parser import explicit_request_fields, project_title
from tools.review_display import quality_status

APPROVALS = {
    "project_manager": ("approve_start", "Duyệt cấu hình dự án"),
    "requirements_analyst": ("approve_brief", "Duyệt yêu cầu thiết kế"),
    "concept_architect": ("approve_concept", "Duyệt ý tưởng kiến trúc"),
    "architect": ("approve_program", "Chọn và chốt phương án công năng"),
    "drafter": ("approve_drawing", "Duyệt mặt bằng và bản vẽ"),
    "fengshui_advisor": ("approve_fengshui", "Xem tư vấn phong thủy"),
    "reviewer": ("approve_review", "Duyệt kết quả kiểm định"),
    "cost_estimator": ("approve_cost", "Duyệt dự toán"),
    "pm_report": ("approve_report", "Duyệt hồ sơ tổng hợp"),
    "final_reviewer": ("approve_final", "Duyệt kết quả đối chiếu cuối"),
}
APPROVAL_LABELS = {k: v[1] for k, v in APPROVALS.items()}
AGENT_NODES = list(APPROVALS)
NODE_AGENT = {**{key: key for key in AGENT_ORDER},
              "pm_report": "project_manager", "coordinate_repair": "project_manager",
              "plan_options": "project_manager", "compare_options": "cost_estimator",
              "check_edited_option": "cost_estimator",
              **{v[0]: ("project_manager" if k == "pm_report" else k) for k, v in APPROVALS.items()}}

# Giới hạn an toàn cho các node nội bộ và điểm duyệt, tách khỏi ngân sách vòng sửa.
WORKFLOW_RECURSION_LIMIT = 96

# Khi quay lại một bước, loại bỏ mọi kết quả phụ thuộc trong checkpoint mới.
STAGE_OUTPUTS = {
    "project_manager": (),
    "requirements_analyst": ("brief", "brief_assessment", "option_brief"),
    "concept_architect": ("concept", "concept_plan"),
    "architect": ("recommended_option", "revision_id"),
    "drafter": ("layout", "area_table", "drawings", "design_issues"),
    "fengshui_advisor": ("fengshui",),
    "reviewer": ("review", "review_issues"),
    "cost_estimator": ("cost", "cost_file", "budget_issues"),
    "pm_report": ("draft_files", "description_file"),
    "final_reviewer": ("final_review",),
}


def invalidate_from(target: str) -> dict:
    stages = list(STAGE_OUTPUTS)
    dependent = stages[stages.index(target):]  # Bản vẽ → Phong thủy → Kiểm định → Dự toán → ...
    return {key: None for stage in dependent for key in STAGE_OUTPUTS[stage]} | {
        "outcome": None, "remaining_issues": [], "final_files": None, "adjustment": None,
        "repair_target": None, "repair_fallback": None, "repair_limit_reached": False}


def outcome_for(state: dict) -> str:
    return state.get("outcome") or "not_passed"


def needs_approval(state: dict, node: str) -> bool:
    points = state.get("approval_points")
    if points is None:   # tương thích cũ: manual_review = duyệt sau Kiến trúc sư và Kiểm định viên
        points = ["architect", "reviewer"] if state.get("manual_review") else []
    return node in points


def _ev(state: dict, summary: str, to: str = "", feedback: bool = False, *, record: bool = True) -> dict:
    summary = redact(summary)
    now = datetime.now().strftime("%H:%M:%S")
    ev = {"time": now, "agent": "user", "status": "done", "to_agent": to, "summary": summary, "tokens": 0,
          "duration_s": 0.0, "version": 0, "feedback": feedback}
    if record:
        events.emit(state.get("run_id", "local"), ev)
    names = {**AGENT_LABELS, "pm_report": "Chủ nhiệm", "plan_options": "Chủ nhiệm", "end": "Kết thúc",
             **{v[0]: "điểm duyệt" for v in APPROVALS.values()}}
    return {"events": [ev], "log": [f"{now}  Người dùng → {names.get(to, to or '—')}: {summary}"]}


def select_option(state: dict, option_id: str, target: str = "drafter") -> dict | None:
    option = next((opt for opt in state.get("options") or [] if opt["id"] == option_id
                   and opt.get("eligible") is True), None)
    if option is None:
        return None
    program = option["program"]
    current = state.get("program") or {}
    latest = state.get("review") or {}
    if (current.get("revision_id") == program["revision_id"]
            and any(issue.get("phan_loai") == "vi_pham" for issue in latest.get("loi", []))):
        return None
    concept = {**(state.get("concept_plan") or {}), "so_tang": program["so_tang"],
               "phong_cach": program["phong_cach"], "vat_lieu": program["vat_lieu"]}
    return {**invalidate_from("drafter"), "program": program, "revision_id": program["revision_id"],
            "selected_by_user": True, "concept_plan": concept, "feedback": [], "route": target,
            "task_retry": {"reason": "Người dùng đổi phương án", "category": "user_change"},
            **_ev(state, f"Chọn {option['ten']} phiên bản {program['option_version']}", target, record=False)}


def _payload(state: dict, node: str) -> dict:
    """Nội dung hiển thị cho người duyệt (tùy agent vừa chạy)."""
    from agents.architect import program_to_rows

    p = {"title": APPROVALS[node][1], "agent": node, "next": state.get("route"), "brief": state.get("brief"),
         "user_request": state.get("user_request"), "trao_doi": state.get("trao_doi", [])[-10:],
         "forward": state.get("repair_fallback") if node == "cost_estimator"
         and state.get("route") == "coordinate_repair" and state.get("repair_fallback") != "end" else None,
         "clarification": state.get("brief_assessment") if node == "requirements_analyst"
         and state.get("outcome") == "needs_input" else None,
         "output": (state.get("history") or [{}])[-1].get("output"),
         "feedback": [item.get("noi_dung") for item in state.get("feedback") or [] if isinstance(item, dict)]
         if state.get("route") == "coordinate_repair" else [],
         "custom_notes": list((state.get("custom_outputs") or {}).values())}
    prog = state.get("program")
    if prog:
        h = prog.get("chieu_cao_tang", {})
        p.update(rows=program_to_rows(prog), lot=state["brief"]["lo_dat"], concept=state.get("concept", ""),
                 settings={"san_truoc": prog.get("san_truoc", 0.0), "san_sau": prog.get("san_sau", 0.0),
                           "cap_hoan_thien": prog.get("cap_hoan_thien", "khá"), "tang_1": h.get("tang_1", 3.6),
                           "tang_khac": h.get("tang_khac", 3.3)},
                 phuong_an_hien_tai=prog.get("phuong_an"))
    if node == "architect":
        p["options"] = [{k: v for k, v in o.items() if k != "program"} | {"rows": program_to_rows(o["program"])}
                        for o in state.get("options") or []]
        p["recommended_option"] = state.get("recommended_option")
    elif node == "drafter" and state.get("drawings"):
        p["sheets"] = [{"so_hieu": x["so_hieu"], "ten": x["ten"], "png": x["png"]} for x in state["drawings"]["sheets"]]
        a = state["area_table"]
        p["area"] = {"so_tang": a["so_tang"], "tong_dien_tich_san": a["tong_dien_tich_san"],
                     "mat_do": a["mat_do_xay_dung"]}
    elif node == "reviewer":
        r = state.get("review", {})
        p["review"] = {k: r.get(k) for k in ("dat", "nhan_xet", "loi", "canh_bao", "kiem_tra")}
    elif node == "cost_estimator":
        c = state.get("cost", {})
        p["cost"] = {k: c.get(k) for k in ("tong_chi_phi", "ngan_sach", "ngan_sach_gia_dinh", "vuot_pct", "chi_phi_m2_san", "cap_hoan_thien",
                                           "ghi_chu", "hang_muc", "du_phong", "tiet_kiem")}
    elif node == "pm_report":
        p["final_files"] = state.get("draft_files")
    return p


def make_approval(node: str):
    """Node duyệt thủ công đặt sau agent `node`. Giữ nguyên nhánh agent đã chọn trừ khi người dùng thay đổi."""

    def resolve(state: dict, d: dict, clarification: bool) -> dict:
        action = d.get("action", "approve")
        me = APPROVALS[node][0]
        if action == "approve" and not clarification:
            target = state.get("route", "")
            if node == "architect" and target == me:
                target = "drafter" if any(o.get("eligible") and o["program"]["revision_id"] == state["revision_id"]
                                          for o in state.get("options") or []) else "compare_options"
            return {"route": target, **_ev(state, f"Đồng ý: {APPROVALS[node][1]}", target)}
        if action == "stop":
            return {"route": "end", "outcome": "stopped", "final_files": None, **_ev(state, "Dừng thiết kế", "", True)}
        if action == "rerun":
            upd = {**invalidate_from(node), "route": node, "feedback": []}
            if node in ("project_manager", "requirements_analyst", "concept_architect", "architect"):
                upd["program"] = None
            return {**upd, **_ev(state, f"Chạy lại {node}", node)}
        if action == "forward" and _payload(state, node).get("forward"):
            target = state["repair_fallback"]
            return {"route": target, "feedback": [],
                    **_ev(state, "Đi tiếp và giữ lại lỗi đã phát hiện", target, True)}
        if action == "revise" and state.get("program"):
            text = redact((d.get("feedback") or "").strip())
            if not text:
                return {"route": me}
            return {**invalidate_from("architect"), "route": "architect", "feedback_source": "user",
                    "feedback": [{"loai": "Người dùng", "ma": "USER", "muc": "Góp ý", "noi_dung": text, "de_xuat": text,
                                  "lich_su": state.get("trao_doi", [])[-6:]}],
                    **_ev(state, f"Góp ý: {text}", "architect", True)}
        if action == "choose" and node == "architect":
            selection = select_option(state, d.get("option"), me if d.get("then_edit") else "drafter")
            if selection is None:
                return {"route": me}
            events.emit(state["run_id"], selection["events"][0])
            return selection
        if action == "edit":
            from agents.architect import apply_user_edit, candidate_with_program, version_option

            try:
                program, brief, changes = apply_user_edit(state["program"], d.get("rows", []), d.get("settings", {}),
                                                          state["brief"])
            except (ValueError, KeyError) as e:
                return {"route": me, **_ev(state, f"Chỉnh sửa không hợp lệ: {e}", "", True)}
            versions = dict(state.get("option_versions") or {})
            program = version_option(program, brief, state["run_id"], versions)
            options = [candidate_with_program(state.get("options") or [], program)]
            concept = {**state["concept_plan"], "so_tang": program["so_tang"], "vat_lieu": program["vat_lieu"]}
            assessment = {"questions": [], "conflicts": [], "needs_confirmation": requirements_analyst.needs_confirmation(brief)}
            return {**invalidate_from("architect"), "route": "check_edited_option", "program": program, "brief": brief,
                    "brief_assessment": assessment,
                    "revision_id": program["revision_id"], "concept_plan": concept, "options": options, "feedback": [],
                    "option_versions": versions, "selected_by_user": True,
                    **_ev(state, "Chốt chỉnh sửa: " + "; ".join(changes), "cost_estimator")}
        if action == "edit_brief":
            from pydantic import ValidationError

            from state import Brief

            try:
                brief = redact(Brief(**d["brief"]).model_dump())
            except (ValidationError, KeyError, TypeError) as e:
                return {"route": me, **_ev(state, f"Yêu cầu không hợp lệ: {e}", "", True)}
            assessment = {"questions": [], "conflicts": [], "needs_confirmation": requirements_analyst.needs_confirmation(brief)}
            return {**invalidate_from("concept_architect"), "brief": brief, "brief_assessment": assessment,
                    "program": None, "options": [], "feedback": [], "route": "plan_options",
                    **_ev(state, "Sửa yêu cầu thiết kế → Kiến trúc sư lập lại phương án", "architect", True)}
        if action == "edit_request":
            text = redact((d.get("request") or "").strip())
            if not text:
                return {"route": me}
            fields = {}
            if clarification:
                explicit = explicit_request_fields(text)
                fields = {key: value for key, value in (state.get("request_fields") or {}).items()
                          if not explicit.get(key)}
            return {**invalidate_from("requirements_analyst"), "user_request": text, "request_fields": fields,
                    "program": None, "options": [],
                    "feedback": [], "route": "requirements_analyst",
                    **_ev(state, f"Viết lại yêu cầu: {text[:80]}", "project_manager", True)}
        return {"route": me}

    def approval(state: dict) -> dict:
        clarification = (node == "requirements_analyst" and state.get("interactive")
                         and state.get("outcome") == "needs_input")
        if not clarification and not needs_approval(state, node):
            return {}
        tasks.approval_pending(state, node)
        decision = interrupt(_payload(state, node))
        data = decision if isinstance(decision, dict) else {"action": str(decision)}
        result = resolve(state, data, clarification)
        action = data.get("action", "approve")
        if result.get("route") != APPROVALS[node][0]:
            if action in ("approve", "choose"):
                tasks.approval_decided({**state, **result}, node, "accepted")
            elif action in ("stop", "forward"):
                tasks.approval_decided(state, node, "canceled" if action == "stop" else "forwarded")
            else:
                tasks.approval_decided(state, node, "changes_requested")
                category = "missing_input" if clarification else ("unknown" if action == "rerun" else "user_change")
                reason = ("Người dùng bổ sung đầu vào còn thiếu" if clarification else
                          "Người dùng yêu cầu chạy lại" if action == "rerun" else "Người dùng chỉnh yêu cầu hoặc thiết kế")
                result["task_retry"] = {"category": category, "reason": reason}
        return result

    approval.__name__ = APPROVALS[node][0]
    return approval


def _route(state: dict) -> str:
    return state.get("route") or "end"


def _after_approval(node: str):
    def route(state: dict) -> str:
        return custom_agent.hook_name(node) if custom_agent.pending(state, node) else _route(state)

    route.__name__ = f"after_{APPROVALS[node][0]}"
    return route


def build_graph(checkpointer=None):
    g = StateGraph(DesignState)
    stages = {
        "project_manager": project_manager.start,
        "requirements_analyst": requirements_analyst.run,
        "concept_architect": concept_architect.run,
        "architect": architect.run,
        "drafter": drafter.run,
        "fengshui_advisor": fengshui_advisor.run,
        "reviewer": reviewer.run,
        "cost_estimator": cost_estimator.run,
        "pm_report": project_manager.run_report,
        "final_reviewer": final_reviewer.run,
    }
    for name, fn in stages.items():
        g.add_node(name, tasks.track_stage(name, fn))

    def repair(state):
        result = project_manager.coordinate_repair(state)
        if "iteration" in result:
            source = state.get("feedback_source")
            category = "agent_error" if source in ("drafter", "final_reviewer") else "unknown"
            owner = AGENT_LABELS.get(NODE_AGENT.get(source), "Đối chiếu hồ sơ")
            cause = {"category": category, "reason": f"Điều phối sửa vòng {result['iteration']} · {owner}"}
            return {**invalidate_from(result["route"]), **result, "task_retry": cause}
        return result

    def dispatch(state):
        return {}

    for name, fn in {
        "coordinate_repair": repair, "plan_options": project_manager.plan_options,
        "compare_options": cost_estimator.compare_options, "check_edited_option": cost_estimator.compare_options,
        "publish": project_manager.publish, "propose_adjustment": project_manager.propose_adjustment,
    }.items():
        g.add_node(name, tasks.track_stage(name, fn))
    g.add_node("dispatch", dispatch)
    targets = {n: n for n in (*AGENT_NODES, "plan_options", "compare_options", "check_edited_option",
                              "coordinate_repair", "publish", "dispatch", "propose_adjustment")}
    targets.update({v[0]: v[0] for v in APPROVALS.values()})
    targets["end"] = END
    g.add_conditional_edges("coordinate_repair", _route, targets)
    g.add_conditional_edges("dispatch", _route, targets)
    g.add_conditional_edges("check_edited_option", _route, targets)
    g.add_edge("plan_options", "concept_architect")
    g.add_edge("compare_options", "approve_program")
    g.add_conditional_edges("publish", _route, targets)
    g.add_edge("propose_adjustment", END)
    for node in AGENT_NODES:
        name = APPROVALS[node][0]
        hook = custom_agent.hook_name(node)
        g.add_node(name, make_approval(node))
        g.add_node(hook, custom_agent.make_hook(node))   # agent tùy biến gắn sau bước này (nếu có)
        g.add_edge(node, "compare_options" if node == "architect" else name)
        # điểm duyệt -> agent tùy biến (khi luồng đi tiếp) -> nhánh agent đã chọn / người dùng chọn
        g.add_conditional_edges(name, _after_approval(node), {**targets, hook: hook})
        g.add_conditional_edges(hook, _route, targets)
    g.add_edge(START, "project_manager")
    return g.compile(checkpointer=checkpointer or MemorySaver())


def sqlite_checkpointer():
    from langgraph.checkpoint.sqlite import SqliteSaver

    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(CHECKPOINT_DB, check_same_thread=False))


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]


def initial_state(request: str, run_id: str | None = None, manual_review: bool = False,
                  max_iterations: int = MAX_ITERATIONS, approval_points: list | None = None,
                  fengshui_enabled: bool = True, interactive: bool = False, *,
                  request_fields: dict | None = None) -> dict:
    """approval_points: các node agent cần duyệt sau khi chạy (vd ["architect", "reviewer"]); "all" = mọi bước."""
    run_id = run_id or new_run_id()
    request = redact(request)
    request_fields = redact(request_fields)
    out = OUTPUT_DIR / run_id
    events.record_run(run_id, request, str(out), {"request_fields": request_fields} if request_fields else None)
    if approval_points == "all":
        approval_points = list(AGENT_NODES)
    if approval_points is None:
        approval_points = ["architect", "reviewer"] if manual_review else []
    return {"run_id": run_id, "user_request": request, "request_fields": request_fields or {},
            "output_dir": str(out), "iteration": 0,
            "max_iterations": min(3, max(0, max_iterations)), "manual_review": bool(approval_points),
            "fengshui_enabled": fengshui_enabled, "interactive": interactive,
            "approval_points": list(approval_points), "versions": {}, "feedback": [],
            "agent_settings": agent_settings.snapshot(), "custom_outputs": {}}


def run_design(request: str, manual_review: bool = False, max_iterations: int = MAX_ITERATIONS,
               on_update=None, persist: bool = True, fengshui_enabled: bool = True,
               approval_points: list | None = None, *, request_fields: dict | None = None) -> dict:
    """Chạy luồng cho CLI, đánh giá và kiểm thử. Có thể dừng ở checkpoint duyệt.

    Mặc định lưu checkpoint vào SQLite để mở lại được trên giao diện (trang Kết quả / Quản lý agent).
    """
    checkpointer = sqlite_checkpointer() if persist else None
    state = initial_state(request, manual_review=manual_review, max_iterations=max_iterations,
                          fengshui_enabled=fengshui_enabled, approval_points=approval_points,
                          interactive=manual_review or bool(approval_points), request_fields=request_fields)
    config = {"configurable": {"thread_id": state["run_id"]}, "recursion_limit": WORKFLOW_RECURSION_LIMIT}
    try:
        graph = build_graph(checkpointer)
        with closing(tasks.stream_tracked(graph, state, config)) as stream:
            for kind, update in stream:
                if kind == "updates" and on_update:
                    on_update(update)
        snapshot = graph.get_state(config)
        final = snapshot.values
        if snapshot.next:
            events.update_run(state["run_id"], "needs_input" if final.get("outcome") == "needs_input" else "awaiting_approval")
            return final
        project_manager.save_snapshot(final)
        events.update_run(state["run_id"], outcome_for(final), _run_summary(final))
        return final
    except Exception:
        tasks.cancel_open(state["run_id"], "Lượt thiết kế gặp lỗi")
        events.update_run(state["run_id"], "error")
        raise
    finally:
        if checkpointer is not None:
            checkpointer.conn.close()


def _run_summary(final: dict) -> dict:
    cost = (final.get("cost") or {})
    quality = quality_status(final)
    return {"so_tang": (final.get("area_table") or {}).get("so_tang"), "tong_chi_phi": cost.get("tong_chi_phi"),
            "ten_du_an": project_title(final.get("user_request", ""), final.get("brief")),
            "vong_sua": final.get("iteration"), "hoan_thanh": outcome_for(final) == "done",
            "ky_thuat": quality["technical"], "quy_chuan": quality["regulatory"],
            "files": final.get("final_files", {})}
