"""Hàm dùng chung cho các trang Streamlit."""
from __future__ import annotations

import time
from uuid import uuid4

import streamlit as st

from config import AGENT_LABELS, AGENT_ORDER, MAX_ITERATIONS
from monitoring import events
from monitoring.runner import manager
from tools.brief_parser import project_title
from tools.design_option import option_label, selected_assumptions
from tools.docx_writer import vn_num, vnd
from tools.review_display import (MISSING, PRELIMINARY, VIOLATION, issue_label, preliminary_ready,
                                  quality_status, regulatory_label, review_rows)

import ui_theme as ui

RUN_STATUS = {k: v[0] for k, v in ui.RUN_STATUS_TONE.items()}


def current_run():
    rid = st.session_state.get("run_id")
    if rid and rid not in manager.runs and events.run_status(rid) is None:
        rid = None  # mã lượt không tồn tại (vd. giá trị lạc từ ô chọn) -> quay về lượt gần nhất
    if not rid:
        runs = events.list_runs(1)
        if runs:
            rid = runs[0]["run_id"]
            st.session_state["run_id"] = rid
    return manager.get(rid) if rid else None


def run_picker(runs: list[dict], run, key: str, *, current_name: str = "", show_current_status: bool = True,
               label_visibility: str = "collapsed") -> None:
    entries = {}
    for row in runs:
        name = row["summary"].get("ten_du_an") or " ".join(row["request"].split())[:62] or row["run_id"]
        status = RUN_STATUS.get(row["status"], row["status"])
        entries[row["run_id"]] = f"{name} · {status}"
    if run:
        status = RUN_STATUS.get(run.status, run.status)
        entries[run.run_id] = f"{current_name} · {status}" if show_current_status else current_name
    if not entries:
        return
    ids = list(entries)
    selected_id = run.run_id if run else ids[0]
    if st.session_state.get(key) != selected_id:
        st.session_state[key] = selected_id

    def select() -> None:
        # Streamlit ghi nhớ ô chọn theo nhãn hiển thị; khi tên dự án/trạng thái đổi (vd. sau bước duyệt),
        # ô chọn có thể gửi về nhãn cũ thay vì mã lượt. Chỉ nhận mã lượt hợp lệ.
        if st.session_state.get(key) in entries:
            st.session_state["run_id"] = st.session_state[key]

    st.selectbox("Dự án", ids, format_func=entries.get, key=key, on_change=select, label_visibility=label_visibility)


def project_name(run, state: dict | None = None) -> str:
    if run is None:
        return "AI Architect Studio"
    state = state if state is not None else run.state()
    return project_title(state.get("user_request", run.request), state.get("brief"))


def run_preferences() -> dict:
    return st.session_state.get("run_preferences", {
        "max_iterations": min(3, max(0, MAX_ITERATIONS)), "approval_points": [], "fengshui_enabled": True,
    })


def adjustment_panel(run, state: dict, key: str) -> None:
    """Đề xuất điều chỉnh của Chủ nhiệm khi lượt chưa đạt, kèm nút tạo lượt mới theo đề xuất."""
    adjustment = state.get("adjustment") or {}
    proposals = adjustment.get("de_xuat") or []
    if run.status != "not_passed" or not adjustment:
        return
    with st.container(border=True, key=f"{key}_adjustment"):
        ui.section("Chủ nhiệm đề xuất điều chỉnh", "Các cách dưới đây đã được kiểm tra: bố trí được trên lô đất "
                   "và nằm trong ngân sách với cùng công cụ của đội ngũ agent.", glyph="target")
        if adjustment.get("loi_khuyen"):
            st.info(adjustment["loi_khuyen"])
        if not proposals:
            st.caption("Chưa tìm được cách điều chỉnh khả thi trong phạm vi bố trí nhà ống của hệ thống. "
                       "Có thể mở Dự án để chỉnh yêu cầu thủ công.")
            return
        for index, proposal in enumerate(proposals):
            with st.container(border=True, key=f"{key}_proposal_{index}"):
                title = proposal["tieu_de"]
                st.markdown(f"**{'Ưu tiên · ' if index == 0 else ''}{title}**")
                over = proposal["vuot_pct"]
                st.caption(f"{proposal['ten_phuong_an']} · {proposal['so_tang']} tầng · "
                           f"{vn_num(proposal['tong_dien_tich_san'])} m² sàn · dự toán {vnd(proposal['chi_phi'])} "
                           f"({'+' if over >= 0 else ''}{vn_num(over * 100)}% so với ngân sách {vnd(proposal['ngan_sach'])})")
                if proposal.get("can_xac_nhan"):
                    st.warning("Đề xuất này thay đổi kích thước lô. Chỉ áp dụng khi kích thước thực tế của lô đúng như vậy.")
                with st.expander("Yêu cầu thiết kế mới"):
                    st.write(proposal["request"])
                if st.button("Thiết kế lại theo đề xuất", key=f"{key}_apply_{index}", icon=":material/auto_fix_high:",
                             type="primary" if index == 0 else "secondary", width="stretch"):
                    preferences = {"max_iterations": state.get("max_iterations", run_preferences()["max_iterations"]),
                                   "approval_points": state.get("approval_points") or [],
                                   "fengshui_enabled": state.get("fengshui_enabled", True)}
                    new_run = manager.start(proposal["request"], request_fields={},
                                            submission_id=f"{run.run_id}:{key}:{index}", **preferences)
                    st.session_state["run_id"] = new_run.run_id
                    st.switch_page("views/studio.py")


def begin_draft() -> None:
    session = st.session_state
    if session.pop("project_submitted", None):
        session["project_draft_values"] = {}
        session["project_submission_id"] = uuid4().hex
    session["project_form_open"] = True


def agent_stats(run_id: str, evs: list[dict] | None = None) -> dict:
    """Thống kê từng agent từ dòng sự kiện."""
    if evs is None:
        evs = events.get_events(run_id)
    stats = {a: {"status": "waiting", "runs": 0, "tokens": 0, "duration": 0.0, "errors": 0, "last": ""}
             for a in AGENT_ORDER}
    for e in evs:
        a = e["agent"]
        if a not in stats:
            continue
        s = stats[a]
        s["status"] = e["status"]
        if e["status"] == "done":
            s["runs"] += 1
            s["tokens"] += e["tokens"] or 0
            s["duration"] += e["duration_s"] or 0
            s["last"] = e["summary"]
            if e["feedback"]:
                s["errors"] += 1
        elif e["status"] == "error":
            s["last"] = e["summary"]
    return stats


def fmt_time(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"


def auto_refresh(run, interval: float = 1.0) -> None:
    if run is not None and run.status == "running":
        time.sleep(interval)
        st.rerun()


# ---------------------------------------------------------------------------
# Khung duyệt thủ công (dùng chung cho mọi điểm duyệt)
# ---------------------------------------------------------------------------
STEP_LABELS = {
    "project_manager": "Chủ nhiệm khởi tạo lượt", "plan_options": "Chủ nhiệm giao lập phương án",
    "compare_options": "Dự toán so sánh phương án", "check_edited_option": "Dự toán kiểm tra phương án vừa chỉnh",
    "coordinate_repair": "Chủ nhiệm điều phối sửa", "pm_report": "Chủ nhiệm tổng hợp hồ sơ",
    "publish": "Xuất bộ hồ sơ", "propose_adjustment": "Chủ nhiệm đề xuất điều chỉnh", "end": "Kết thúc",
    "dispatch": "Chuyển bước",
}
NEXT_LABEL = STEP_LABELS  # tương thích tên cũ


def step_label(node: str | None) -> str:
    """Tên bước dễ hiểu cho mọi node của workflow (agent, node điều phối hoặc điểm duyệt)."""
    if not node:
        return "Chưa xác định"
    if node in STEP_LABELS:
        return STEP_LABELS[node]
    from graph import APPROVALS
    for agent, (approval, title) in APPROVALS.items():
        if node == approval:
            return f"Chờ duyệt · {title}"
    if node.startswith("custom_after_"):
        return "Agent tùy biến"
    return label(node)


def _sig(p: dict) -> str:
    import hashlib
    import json

    return hashlib.md5(json.dumps(p, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:8]


def _money(v) -> str:
    return f"{(v or 0) / 1e9:.2f} tỷ".replace(".", ",")


def show_remaining_issues(issues: list[dict]) -> None:
    for issue in issues:
        message = f"{issue_label(issue)} · {issue['muc']} — {issue['noi_dung']}"
        if issue.get("ma") in ("THIEU_CAN_CU", "VUOT_NGAN_SACH") or issue.get("phan_loai") == "tham_chieu":
            st.warning(message)
        else:
            st.error(message)


def show_quality(state: dict, status: str) -> None:
    quality = quality_status(state)
    ready = preliminary_ready(state)
    execution = "Hoàn thành" if ready else RUN_STATUS.get(status, status)
    cols = st.columns(3)
    cols[0].markdown(f"**Thực thi** · {execution}")
    cols[1].markdown(f"**Kiểm tra kỹ thuật** · {quality['technical']}")
    cols[2].markdown(f"**Xác minh quy chuẩn** · {quality['regulatory']}")
    if ready:
        st.warning(PRELIMINARY, icon=":material/fact_check:")
    elif state.get("final_files") and status == "done":
        st.success("Đã tạo bộ hồ sơ thiết kế sơ bộ.", icon=":material/task_alt:")


def show_review(review: dict, brief: dict | None, key: str) -> None:
    rows = review_rows(review, brief)
    if not rows:
        st.info("Chưa có kết quả kiểm định.")
        return
    label = regulatory_label(rows)
    violations = sum(row["status"] == VIOLATION for row in rows)
    missing = sum(row["status"] == MISSING for row in rows)
    technical = sum(not row["regulatory"] and row["tone"] == "error" for row in rows)
    if violations:
        st.error(f"{VIOLATION} · {violations} tiêu chí quy chuẩn")
    if missing:
        st.warning(f"{MISSING} · {missing} tiêu chí quy chuẩn")
    if technical:
        st.error(f"Không đạt kỹ thuật · {technical} phép kiểm hình học hoặc brief")
    if not (violations or missing or technical):
        if label == "Chưa có đánh giá":
            st.info(label)
        else:
            st.success(label)
    st.dataframe([
        {"Tiêu chí": row["criterion"], "Kết quả": row["status"], "Số liệu hiện tại": row["actual"],
         "Nguồn": row["source"], "Lý do chưa đánh giá": row["reason"]}
        for row in rows
    ], hide_index=True, width="stretch", height=380)
    index = st.selectbox("Chi tiết tiêu chí", range(len(rows)), format_func=lambda i: rows[i]["criterion"], key=key)
    item = rows[index]
    if item["status"] == MISSING:
        st.caption(f"Giá trị đối chiếu tham khảo · {item['threshold']}")
    else:
        st.write(f"**Ngưỡng phép kiểm** · {item['threshold']}")
    if item["scope"]:
        st.write(f"**Phạm vi** · {item['scope']}")
    if item["source"]:
        st.write(f"**Nguồn** · {item['source']}")
    if item["reason"]:
        st.write(f"**Lý do chưa đánh giá** · {item['reason']}")
    if item["missing"]:
        st.markdown("**Dữ liệu hoặc căn cứ cần bổ sung**")
        for note in item["missing"]:
            st.write(f"• {note}")
    if item["action"]:
        st.write(f"**Cách bổ sung** · {item['action']}")
    if item["excerpt"]:
        st.text(item["excerpt"])
    for issue in review.get("loi") or []:
        st.write(f"**{issue_label(issue)}** · {issue['muc']} — {issue['noi_dung']}")
        if issue.get("de_xuat"):
            st.caption(f"Đề xuất · {issue['de_xuat']}")
    for warning in review.get("canh_bao") or []:
        st.caption(f"Khuyến nghị · {warning.get('muc')}: {warning.get('noi_dung')}")


def _show_result(p: dict, k: str) -> None:
    """Kết quả agent vừa chạy."""
    agent = p.get("agent")
    if agent == "requirements_analyst" and p.get("brief"):
        b = p["brief"]
        ld, gd, yc = b["lo_dat"], b["gia_dinh"], b["yeu_cau_phong"]
        c = st.columns(4)
        c[0].metric("Lô đất", f"{ld['rong']:g} × {ld['dai']:g} m", ld["huong"], delta_color="off")
        c[1].metric("Phòng ngủ", yc["phong_ngu"], f"thờ: {'có' if yc.get('phong_tho') else 'không'}", delta_color="off")
        c[2].metric("Gara", yc.get("gara") or "không", f"{yc.get('so_tang') or 'KTS đề xuất'} tầng", delta_color="off")
        c[3].metric("Ngân sách", _money(b["ngan_sach"]), b.get("phong_cach"), delta_color="off")
        if b.get("gia_dinh_bo_sung"):
            st.info("Giả định: " + "; ".join(b["gia_dinh_bo_sung"]), icon=":material/info:")
        with st.expander("Brief đầy đủ (JSON)"):
            st.json(b)
    elif agent in ("architect",) and p.get("rows"):
        st.write(p.get("concept", ""))
        _rooms_by_floor(p["rows"])
    elif agent == "drafter" and p.get("sheets"):
        a = p["area"]
        c = st.columns(3)
        c[0].metric("Số tầng", a["so_tang"])
        c[1].metric("Tổng DT sàn", f"{a['tong_dien_tich_san']:.1f} m²".replace(".", ","))
        c[2].metric("Mật độ XD", f"{a['mat_do'] * 100:.1f}%".replace(".", ","))
        names = [f"{x['so_hieu']} – {x['ten']}" for x in p["sheets"]]
        i = st.selectbox("Bản vẽ", range(len(names)), format_func=lambda j: names[j], key=f"{k}_sheet")
        st.image(p["sheets"][i]["png"], width="stretch")
    elif agent == "reviewer" and p.get("review"):
        show_review(p["review"], p.get("brief"), f"{k}_check")
    elif agent == "cost_estimator" and p.get("cost"):
        c = p["cost"]
        m = st.columns(3)
        m[0].metric("Tổng chi phí", _money(c["tong_chi_phi"]), f"{c['vuot_pct'] * 100:+.1f}% ngân sách",
                    delta_color="inverse")
        m[1].metric("Ngân sách", _money(c["ngan_sach"]))
        m[2].metric("Gói hoàn thiện", c["cap_hoan_thien"])
        st.write(c.get("ghi_chu", ""))
        st.dataframe([{"Hạng mục": it["hang_muc"], "Thành tiền": f"{it['thanh_tien']:,.0f} đ".replace(",", ".")}
                      for it in c.get("hang_muc") or []], hide_index=True, width="stretch")
        for t in c.get("tiet_kiem") or []:
            st.caption(f"Tiết kiệm · {t['phuong_an']}: ~{_money(t['tiet_kiem'])}")
    elif agent == "pm_report":
        st.info("Chủ nhiệm đã tổng hợp bộ hồ sơ nháp. Bước tiếp theo sẽ đối chiếu số liệu giữa các tệp.")
        names = {"ban_ve_pdf": "Bộ bản vẽ PDF", "ban_ve_dxf_zip": "Bản vẽ DXF (ZIP)",
                 "thuyet_minh_docx": "Thuyết minh DOCX", "du_toan_xlsx": "Dự toán XLSX"}
        ui.html_block(ui.kv([(names.get(key, key), ui.esc(str(path).replace("\\", "/").rsplit("/", 1)[-1]))
                             for key, path in (p.get("final_files") or {}).items()]))
    elif agent == "project_manager":
        out = p.get("output") or {}
        b = p.get("brief") or {}
        st.info("Chủ nhiệm đã mở lượt thiết kế. Đồng ý để giao Phân tích yêu cầu chuẩn hóa brief.")
        ui.html_block(ui.kv([("Mã lượt", ui.esc(out.get("run_id", "—"))),
                             ("Số vòng sửa tối đa", ui.esc(out.get("max_iterations", "—"))),
                             ("Tư vấn phong thủy", "Bật" if out.get("fengshui_enabled", True) else "Tắt"),
                             ("Yêu cầu", ui.esc((p.get("user_request") or "")[:300]))]))
    elif agent == "concept_architect" and p.get("output"):
        out = p["output"]
        c = st.columns(3)
        c[0].metric("Số tầng đề xuất", out.get("so_tang", "—"))
        c[1].metric("Phong cách", out.get("phong_cach") or "—")
        c[2].metric("Thay đổi", len(out.get("thay_doi") or []))
        if out.get("thay_doi"):
            st.info("Điều chỉnh theo phản hồi: " + "; ".join(out["thay_doi"]), icon=":material/edit:")
        if out.get("vat_lieu"):
            names = {"san": "Sàn", "mat_tien": "Mặt tiền", "cua": "Cửa đi, cửa sổ", "cua_phong": "Cửa phòng",
                     "lan_can": "Lan can", "mai": "Mái"}
            ui.html_block(ui.kv([(names.get(key, key.replace("_", " ").capitalize()), ui.esc(value))
                                 for key, value in out["vat_lieu"].items()]))
        for title, key in (("Thông gió", "thong_gio"), ("Chiếu sáng", "chieu_sang")):
            if out.get(key):
                st.markdown(f"**{title}:** " + "; ".join(out[key]))
        if out.get("dien_giai"):
            with st.expander("Diễn giải của kiến trúc sư"):
                st.write(out["dien_giai"])
    elif agent == "fengshui_advisor" and p.get("output"):
        out = p["output"]
        info = out.get("thong_tin") or {}
        if info.get("co_du_lieu"):
            st.markdown(f"Gia chủ cung **{info.get('cung_menh')}** ({info.get('nhom')}), nhà hướng "
                        f"**{info.get('huong_nha')}** · {'hợp' if info.get('hop_huong') else 'chưa hợp'} hướng.")
        else:
            st.info(info.get("ghi_chu") or "Thiếu năm sinh chủ nhà nên bỏ qua phần cung mệnh.")
        for check in out.get("bo_tri") or []:
            st.markdown(f"{'✅' if check.get('dat') else '⚠️'} {check.get('noi_dung')}")
        for tip in out.get("goi_y") or []:
            st.caption(f"Gợi ý · {tip.get('noi_dung')} → {tip.get('de_xuat', '')}")
    elif agent == "final_reviewer" and p.get("output"):
        out = p["output"]
        if out.get("dat"):
            st.success("Bộ hồ sơ nhất quán: số tầng, phòng, diện tích, chi phí và phiên bản khớp giữa các tệp.")
        for issue in out.get("loi") or []:
            st.error(f"{issue.get('muc', '')}: {issue.get('noi_dung', '')}")
    elif p.get("output") is not None:
        st.json(p["output"])
    if p.get("output") is not None and agent not in ("requirements_analyst",):
        with st.expander("Dữ liệu kỹ thuật (JSON)"):
            st.json(p["output"], expanded=False)



def _rooms_by_floor(rows: list[dict]) -> None:
    floors: dict[int, list] = {}
    for r in rows:
        floors.setdefault(r["tang"], []).append(r)
    cols = st.columns(max(1, len(floors)))
    for c, (t, rs) in zip(cols, sorted(floors.items())):
        with c.container(border=True):
            ui.html_block(f'<div class="aa-eyebrow">Tầng {t}</div>'
                          + ui.kv([(r["ten"], f"{r['dien_tich']:g} m²".replace(".", ",")) for r in rs]))


def _compare_options(options: list[dict], current: str | None) -> None:
    rows = []
    for opt in options:
        m = opt.get("chi_so") or {}
        badges = ["Đang chọn"] if opt["id"] == current and opt.get("eligible") is not False else []
        if opt.get("ly_do_uu_tien"):
            badges.append("Đề xuất")
        if opt.get("eligible") is False:
            badges.append("Cần sửa trước khi chọn")
        rows.append({"Phương án": opt["ten"], "Phiên bản": opt.get("phien_ban"), "Trạng thái": " · ".join(badges),
                     "Tầng": m.get("so_tang"), "Diện tích sàn (m²)": m.get("tong_dien_tich_san"),
                     "Diện tích xây dựng (m²)": m.get("dien_tich_xay_dung"),
                     "Sân sau (m)": m.get("san_sau"), "Gói hoàn thiện": m.get("cap_hoan_thien"),
                     "Chi phí dự kiến": vnd(m["chi_phi"]) if "chi_phi" in m else "—"})
    st.table(rows)
    for opt in options:
        if opt.get("ly_do_uu_tien"):
            st.info(f"Đề xuất {opt['id']} · {opt['ly_do_uu_tien']}")
        with st.expander(opt["ten"]):
            st.write(opt["mo_ta"])
            for floor, names in opt.get("cong_nang", {}).items():
                st.write(f"**{floor}** · {', '.join(names)}")
            if not opt.get("cong_nang") and opt.get("rows"):
                _rooms_by_floor(opt["rows"])
            if opt.get("vat_lieu"):
                st.markdown("**Vật liệu**")
                fields = {"san": "Sàn", "mat_tien": "Mặt tiền", "cua": "Cửa", "cua_phong": "Cửa phòng",
                          "lan_can": "Lan can", "mai": "Mái"}
                st.write(" · ".join(f"{fields.get(k, k)} — {v}" for k, v in opt["vat_lieu"].items()))
            for name, notes in (("Ưu điểm", opt.get("uu_diem")), ("Hạn chế", opt.get("han_che")),
                                ("Giả định thiết kế", opt.get("gia_dinh"))):
                if notes:
                    st.markdown(f"**{name}**")
                    for note in notes:
                        st.write("• " + note)
            if opt.get("can_xac_minh"):
                st.markdown("**Nội dung cần xác minh**")
                st.table([{"Tiêu chí": i["muc"], "Phân loại": issue_label(i), "Lý do": i["noi_dung"]}
                          for i in opt["can_xac_minh"]])
            show_remaining_issues(opt.get("loi") or [])
            for issue in opt.get("loi") or []:
                if issue.get("phan_loai") == "vi_pham":
                    citation = issue.get("trich_dan") or {}
                    st.caption(" · ".join(filter(None, (issue.get("nguon"), citation.get("nguon"),
                                                       citation.get("muc"), issue.get("pham_vi")))))


def show_result_options(state: dict) -> None:
    options = state.get("options") or []
    brief_assessment = state.get("brief_assessment") or {}
    pending = brief_assessment.get("needs_confirmation", [])
    program = state.get("program") or {}
    if not (options or pending):
        return
    st.subheader("Phương án sơ bộ")
    label = option_label(program)
    if label and any(o.get("eligible") and o["id"] == program.get("phuong_an") for o in options):
        st.caption(f"Đang dùng · {label}")
    if options:
        _compare_options(options, program.get("phuong_an"))
    if pending:
        st.markdown("**Thông tin cần bổ sung**")
        for note in pending:
            st.write("• " + note)
    assumptions = selected_assumptions(state)
    if assumptions:
        with st.expander("Giả định của phương án đang dùng"):
            for note in assumptions:
                st.write("• " + note)


def _options_tab(run, p: dict, k: str) -> None:
    options = p.get("options") or []
    current = p.get("phuong_an_hien_tai")
    _compare_options(options, current)
    names = {o["id"]: o["ten"] for o in options if o.get("eligible")}
    if not names:
        return
    ids = list(names)
    chosen = st.selectbox("Phương án để triển khai", ids, index=ids.index(current) if current in ids else 0,
                          format_func=names.get, key=f"{k}_pick")
    a, b = st.columns(2)
    if a.button("Chọn và chuyển vẽ", key=f"{k}_commit", type="primary"):
        run.answer("choose", option=chosen)
        st.rerun()
    if b.button("Chọn rồi chỉnh sửa", key=f"{k}_edit_option"):
        run.answer("choose", option=chosen, then_edit=True)
        st.rerun()


def _program_editor(run, p: dict, k: str) -> None:
    """Bảng chỉnh sửa trực tiếp chương trình công năng."""
    from agents.architect import GRADES, POSITIONS, ROOM_TYPES

    code_of = {v: c for c, v in ROOM_TYPES.items()}
    rows = [{"ID": r.get("id"), "Tầng": r["tang"], "Tên phòng": r["ten"], "Loại": ROOM_TYPES.get(r["loai"], r["loai"]),
             "Diện tích (m²)": r["dien_tich"], "Vị trí": r["vi_tri"]} for r in p["rows"]]
    s_ = p["settings"]
    lot_l = float((p.get("lot") or {}).get("dai", 30))
    with st.form(f"{k}_form_edit"):
        st.caption("Sửa ô trong bảng, thêm dòng ở cuối, chọn dòng rồi 🗑 để xóa. Cầu thang + giếng trời là lõi cố định. "
                   "Bấm “Áp dụng & chốt” để Họa viên vẽ lại theo bảng này.")
        edited = st.data_editor(
            rows, num_rows="dynamic", width="stretch", hide_index=True, key=f"{k}_ed",
            disabled=["ID"],
            column_config={
                "ID": None,
                "Tầng": st.column_config.NumberColumn(min_value=1, max_value=5, step=1, required=True),
                "Tên phòng": st.column_config.TextColumn(required=True),
                "Loại": st.column_config.SelectboxColumn(options=list(ROOM_TYPES.values()), required=True),
                "Diện tích (m²)": st.column_config.NumberColumn(min_value=1.0, max_value=200.0, step=0.5, required=True),
                "Vị trí": st.column_config.SelectboxColumn(options=POSITIONS, required=True,
                                                          help="mặt tiền → trước → giữa (sát giếng trời) → sau")})
        c = st.columns(5)
        san_truoc = c[0].number_input("Sân trước (m)", 0.0, lot_l / 2, float(s_["san_truoc"]), 0.5)
        san_sau = c[1].number_input("Sân sau (m)", 0.0, lot_l / 2, float(s_["san_sau"]), 0.5)
        grade = c[2].selectbox("Gói hoàn thiện", GRADES,
                               GRADES.index(s_["cap_hoan_thien"]) if s_["cap_hoan_thien"] in GRADES else 2)
        h1 = c[3].number_input("Cao tầng 1 (m)", 3.0, 4.5, float(s_["tang_1"]), 0.1)
        hk = c[4].number_input("Cao tầng khác (m)", 3.0, 4.2, float(s_["tang_khac"]), 0.1)
        submit = st.form_submit_button("Áp dụng & chốt chỉnh sửa", type="primary", icon=":material/save:")
    if submit:
        out = [{"id": r.get("ID"), "tang": r.get("Tầng"), "ten": r.get("Tên phòng"), "loai": code_of.get(r.get("Loại")),
                "dien_tich": r.get("Diện tích (m²)"), "vi_tri": r.get("Vị trí")} for r in edited]
        bad = [i for i, r in enumerate(out, 1) if (r["ten"] or r["loai"]) and
               (not r["loai"] or not r["dien_tich"] or not r["tang"])]
        if bad:
            st.error(f"Dòng {bad} thiếu tầng / loại / diện tích.")
        else:
            run.answer("edit", rows=out, settings={"san_truoc": san_truoc, "san_sau": san_sau, "cap_hoan_thien": grade,
                                                   "tang_1": h1, "tang_khac": hk})
            st.rerun()


def _chat_tab(run, p: dict, k: str) -> None:
    st.caption("Nói chuyện tự nhiên với Kiến trúc sư, ví dụ: “nhà hơi tối”, “bố mẹ già lên xuống khó”, "
               "“phòng khách 30 m2 và bếp rộng hơn”, “chuyển phòng thờ lên tầng 4”, “tiết kiệm hơn”.")
    for h in p.get("trao_doi") or []:
        with st.chat_message("user"):
            st.write(h["nguoi_dung"])
        with st.chat_message("assistant", avatar=":material/architecture:"):
            st.write(h["kien_truc_su"])
    with st.form(f"{k}_form_chat", clear_on_submit=True):
        text = st.text_area("Góp ý của bạn", height=80, label_visibility="collapsed",
                            placeholder="Nhập mong muốn của bạn…")
        if st.form_submit_button("Gửi cho Kiến trúc sư", type="primary", icon=":material/send:"):
            if text.strip():
                run.answer("revise", text.strip()); st.rerun()
            else:
                st.warning("Hãy nhập nội dung.")


def _brief_tab(run, p: dict, k: str) -> None:
    from tools.brief_parser import DIRS

    b = p.get("brief") or {}
    if not b:
        st.caption("Chưa có brief.")
        return
    ld, gd, yc = b["lo_dat"], b["gia_dinh"], b["yeu_cau_phong"]
    dirs = [d.title() for d in DIRS]
    styles = ["hiện đại", "tối giản", "tân cổ điển", "Indochine", "Japandi", "Bắc Âu", "nhiệt đới", "cổ điển"]
    st.caption("Sửa yêu cầu → Kiến trúc sư lập lại 3 phương án từ yêu cầu mới. Bộ đếm vòng sửa tự động được giữ nguyên.")
    with st.form(f"{k}_form_brief"):
        c = st.columns(4)
        rong = c[0].number_input("Rộng lô (m)", 3.0, 20.0, float(ld["rong"]), 0.1)
        dai = c[1].number_input("Dài lô (m)", 8.0, 60.0, float(ld["dai"]), 0.5)
        huong = c[2].selectbox("Hướng mặt tiền", dirs, dirs.index(ld["huong"]) if ld["huong"] in dirs else 4)
        tinh = c[3].text_input("Tỉnh / thành", ld["tinh"])
        c = st.columns(4)
        so_nguoi = c[0].number_input("Số người", 1, 20, int(gd["so_nguoi"]))
        nam = c[1].number_input("Năm sinh chủ nhà (0 = không rõ)", 0, 2025, int(gd.get("nam_sinh_chu_nha") or 0))
        gt = c[2].selectbox("Giới tính chủ nhà", ["nam", "nữ"], 0 if gd.get("gioi_tinh_chu_nha", "nam") == "nam" else 1)
        ns = c[3].number_input("Ngân sách (tỷ)", 0.3, 100.0, float(b["ngan_sach"]) / 1e9, 0.1)
        c = st.columns(5)
        pn = c[0].number_input("Phòng ngủ", 1, 12, int(yc["phong_ngu"]))
        tho = c[1].checkbox("Phòng thờ", bool(yc.get("phong_tho")))
        lv = c[2].checkbox("Phòng làm việc", bool(yc.get("phong_lam_viec")))
        gara_opts = ["không", "xe máy", "ô tô"]
        gara = c[3].selectbox("Gara", gara_opts, gara_opts.index(yc.get("gara") or "không"))
        so_tang = c[4].number_input("Số tầng (0 = KTS đề xuất)", 0, 5, int(yc.get("so_tang") or 0))
        c = st.columns(3)
        pc = c[0].selectbox("Phong cách", styles, styles.index(b.get("phong_cach")) if b.get("phong_cach") in styles else 0)
        khac = c[1].text_input("Yêu cầu khác (cách nhau dấu phẩy)", ", ".join(b.get("yeu_cau_khac", [])))
        parcel = c[2].text_input("Mã lô đất", ld.get("ma_lo_dat") or "")
        if st.form_submit_button("Cập nhật yêu cầu & thiết kế lại", type="primary", icon=":material/restart_alt:"):
            new = {"lo_dat": {"rong": rong, "dai": dai, "huong": huong, "tinh": tinh, "ma_lo_dat": parcel.strip() or None},
                   "gia_dinh": {**gd, "so_nguoi": so_nguoi, "nam_sinh_chu_nha": nam or None, "gioi_tinh_chu_nha": gt},
                   "yeu_cau_phong": {"phong_ngu": pn, "phong_tho": int(tho), "phong_lam_viec": int(lv),
                                     "gara": None if gara == "không" else gara, "so_tang": so_tang or None},
                   "ngan_sach": int(ns * 1e9), "phong_cach": pc,
                   "yeu_cau_khac": [x.strip() for x in khac.split(",") if x.strip()],
                   "gia_dinh_bo_sung": [note for note in b.get("gia_dinh_bo_sung", [])
                                        if not note.startswith(("Kích thước lô đất:", "Hướng mặt tiền:", "Địa điểm:",
                                                                "Số phòng ngủ:", "Ngân sách:", "Phong cách:"))]}
            run.answer("edit_brief", brief=new); st.rerun()
    with st.form(f"{k}_form_req"):
        req = st.text_area("Hoặc viết lại toàn bộ yêu cầu bằng lời (Chủ nhiệm sẽ phân tích lại từ đầu)",
                           p.get("user_request", ""), height=90)
        if st.form_submit_button("Gửi yêu cầu mới cho Chủ nhiệm", icon=":material/edit_note:"):
            run.answer("edit_request", request=req); st.rerun()


def show_custom_notes(notes: list[dict], revision: str | None = None) -> None:
    """Nhận xét của agent tùy biến (mỗi agent một khối), ghi chú khi thuộc phiên bản khác."""
    import agent_settings

    for note in notes:
        stage = agent_settings.STAGE_LABELS.get(note.get("after"), note.get("after") or "—")
        meta = f"Sau bước {stage} · {note.get('model') or '—'}"
        if revision and note.get("revision_id") and note["revision_id"] != revision:
            meta += " · lập cho phiên bản trước"
        st.markdown(f"**{note.get('name') or note.get('id')}**")
        st.caption(meta)
        if note.get("status") == "done":
            st.write(note.get("text") or "")
        else:
            st.info(note.get("text") or "Chưa có nhận xét.", icon=":material/info:")


def approval_box(run, key: str = "ap") -> None:
    """Khung duyệt thủ công khi graph dừng ở interrupt (sau bất kỳ agent nào)."""
    if run is None or run.status not in ("awaiting_approval", "needs_input") or not run.interrupt_payload:
        return
    p = run.interrupt_payload or {}
    k = f"{key}_{p.get('agent')}_{_sig({x: p.get(x) for x in ('agent', 'next', 'rows', 'trao_doi', 'phuong_an_hien_tai')})}"
    agent = p.get("agent")
    if p.get("clarification"):
        with st.container(border=True):
            st.subheader("Cần xác nhận yêu cầu thiết kế")
            for note in p["clarification"]["conflicts"] + p["clarification"]["questions"]:
                st.write(f"• {note}")
            with st.form(f"{k}_clarification"):
                st.caption("Thông tin mới thay thế trường tương ứng. Các trường biểu mẫu còn lại được giữ.")
                corrected = st.text_area("Yêu cầu đã bổ sung", p.get("user_request", ""))
                if st.form_submit_button("Gửi yêu cầu đã bổ sung") and corrected.strip():
                    run.answer("edit_request", request=corrected)
                    st.rerun()
            if st.button("Dừng lượt thiết kế", key=f"{k}_stop"):
                run.answer("stop")
                st.rerun()
        return
    with st.container(border=True):
        nxt = p.get("next")
        back = nxt == "coordinate_repair"
        ui.html_block(
            f'<div class="aa-approval-head"><div><div class="aa-eyebrow">Điểm duyệt thủ công</div>'
            f'<h3>{ui.esc(p.get("title", "Chờ duyệt"))}</h3>'
            f'<div class="aa-sub" style="font-size:.875rem;margin-top:6px">Nếu đồng ý, bước tiếp theo: '
            f'<b>{ui.esc(step_label(nxt))}</b>'
            f'{" — Chủ nhiệm sẽ điều phối phản hồi" if back else ""}</div></div>'
            f'{ui.pill("Chờ bạn duyệt", "warning", live=True)}</div>')
        reasons = [item for item in p.get("feedback") or [] if item]
        if back and reasons:
            st.warning("Kết quả bước này cần sửa nên sẽ được trả về Chủ nhiệm điều phối:\n"
                       + "\n".join(f"- {item}" for item in reasons[:5]), icon=":material/assignment_return:")
        st.caption("Đồng ý để chuyển sang bước tiếp theo. Chạy lại để agent làm lại bước này. "
                   "Xem kết quả và các tab chỉnh sửa bên dưới trước khi quyết định.")
        if p.get("custom_notes"):
            with st.expander(f"Nhận xét của agent tùy biến ({len(p['custom_notes'])})", icon=":material/smart_toy:"):
                show_custom_notes(p["custom_notes"])
        actions = [("ok", "Đồng ý & tiếp tục", ":material/check_circle:", "primary", "approve")]
        if p.get("forward"):
            actions.append(("fw", "Đi tiếp với cảnh báo ngân sách", ":material/skip_next:", "secondary", "forward"))
        actions += [("rerun", f"Chạy lại {label(agent)}", ":material/replay:", "secondary", "rerun"),
                    ("stop", "Dừng", ":material/stop_circle:", "secondary", "stop")]
        widths = [1.4] + [1.2] * (len(actions) - 2) + [0.8]
        cols = st.columns(widths + [max(0.1, 6 - sum(widths))])
        for c, (sk, text, ic, kind, act) in zip(cols, actions):
            if c.button(text, key=f"{k}_{sk}", type=kind, width="stretch", icon=ic):
                run.answer(act); st.rerun()
        names = [":material/insights: Kết quả"]
        if agent == "architect" and p.get("options"):
            names.append(":material/dashboard: Chọn phương án")
        if p.get("rows"):
            names.append(":material/table_edit: Chỉnh sửa phương án")
        if p.get("rows"):
            names.append(":material/forum: Trao đổi với KTS")
        if p.get("brief"):
            names.append(":material/edit_note: Sửa yêu cầu")
        tabs = dict(zip(names, st.tabs(names)))
        with tabs[names[0]]:
            _show_result(p, k)
        for n, t in tabs.items():
            with t:
                if "Chọn phương án" in n:
                    _options_tab(run, p, k)
                elif "Chỉnh sửa phương án" in n:
                    _program_editor(run, p, k)
                elif "Trao đổi" in n:
                    _chat_tab(run, p, k)
                elif "Sửa yêu cầu" in n:
                    _brief_tab(run, p, k)


def label(agent: str) -> str:
    extra = {"coordinate_repair": "Chủ nhiệm điều phối", "publish": "Xuất kết quả", "pm_report": "Chủ nhiệm tổng hợp", "end": "Kết thúc", "approve_program": "Duyệt phương án", "propose_adjustment": "Chủ nhiệm đề xuất điều chỉnh"}
    if agent and agent.startswith("custom_"):
        import agent_settings

        return agent_settings.custom_label(agent) or agent
    return AGENT_LABELS.get(agent, extra.get(agent, agent or "—"))


def run_stepper(run, stats: dict) -> None:
    """Thanh tiến trình theo agent: hoàn thành / đang chạy / có phản hồi lỗi / chờ."""
    _, current = run.step()
    fengshui_enabled = run.state().get("fengshui_enabled", True)
    steps = []
    for a in AGENT_ORDER:
        s = stats[a]
        if run.status in ("running",) and a == current:
            stt, sub = "active", "Đang chạy"
        elif s["status"] == "error":
            stt, sub = "err", "Lỗi"
        elif s["runs"]:
            stt = "warn" if s["errors"] and a in ("reviewer", "cost_estimator") and s["status"] != "done" else "done"
            sub = f"{s['runs']} lần chạy" + (f" · {s['errors']} phản hồi" if s["errors"] else "")
        elif a == "fengshui_advisor" and not fengshui_enabled:
            stt, sub = "todo", "Đã tắt"
        else:
            stt, sub = "todo", "Chờ"
        if run.status == "awaiting_approval" and a == current:
            stt, sub = "active", "Chờ duyệt"
        steps.append((label(a), sub, stt))
    ui.stepper(steps)
