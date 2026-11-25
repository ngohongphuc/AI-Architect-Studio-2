"""Chọn phương án và đọc đúng bộ hồ sơ của phiên bản đã lưu."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st
from PIL import Image

import drawing_viewer
import model_viewer
import ui_theme as ui
from monitoring import events
from monitoring.releases import ARTIFACTS, list_releases, read_artifact, release_path
from monitoring.runner import get_graph
from tools.design_option import option_label, option_stamp, selected_assumptions
from tools.docx_writer import vn_num, vnd
from tools.review_display import MISSING, VERIFIED, VIOLATION, issue_label, preliminary_ready, quality_status, review_rows
from ui_common import (adjustment_panel, approval_box, auto_refresh, current_run, project_name, run_picker,
                       show_custom_notes, show_result_options)

DOWNLOADS = (
    ("ban_ve_pdf", "PDF", "Bộ bản vẽ", "application/pdf"),
    ("ban_ve_dxf_zip", "DXF", "Bản vẽ AutoCAD ZIP", "application/zip"),
    ("mo_hinh_3d_glb", "GLB", "Mô hình 3D cho Blender, SketchUp và trình xem 3D", "model/gltf-binary"),
    ("mo_hinh_3d_dxf", "DXF 3D", "Mô hình 3D cho AutoCAD", "application/dxf"),
    ("thuyet_minh_docx", "DOCX", "Thuyết minh", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("du_toan_xlsx", "XLSX", "Dự toán có công thức", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
)


MODEL_KINDS = ("mo_hinh_3d_glb", "mo_hinh_3d_dxf")


def version_name(program: dict, *, saved: bool = False) -> str:
    return option_label(program) or (f"Phương án {program['phuong_an']}" if program.get("phuong_an")
                                     else "Hồ sơ đã lưu" if saved else "Phiên bản đang xử lý")


@st.cache_data(show_spinner=False, max_entries=64)
def cached_document(path: Path, kind: str, stamp: str, modified: int, size: int) -> tuple[bytes | None, str]:
    return read_artifact(path, kind, stamp)


def asset_path(value, root: Path, release: Path | None = None) -> Path | None:
    if not value:
        return None
    try:
        path = Path(value).resolve()
    except (OSError, TypeError, ValueError):
        return None
    if not path.is_relative_to(root) or (release and path.parent != release):
        return None
    return path


def download_cards(state: dict, root: Path, release: Path | None, edition: str, version: str, updated: str) -> bool:
    files = state.get("final_files") or {}
    stamp = option_stamp(state.get("program") or {})
    unavailable = False
    with st.container(border=True, key="result_downloads"):
        ui.section("Tải hồ sơ", glyph="download")
        if not files:
            st.caption("Phiên bản này chưa xuất tệp.")
        for kind, label, title, mime in DOWNLOADS:
            if files and kind in MODEL_KINDS and not files.get(kind):
                continue            # hồ sơ xuất trước khi có mô hình 3D
            path = asset_path(files.get(kind), root, release)
            data, note = None, "Thiếu tệp." if files else ""
            if path is not None:
                try:
                    if path.is_file():
                        info = path.stat()
                        data, note = cached_document(path, kind, stamp, info.st_mtime_ns, info.st_size)
                except OSError:
                    note = "Không đọc được tệp."
            elif files.get(kind):
                note = "Đường dẫn tệp không khớp bộ hồ sơ."
            st.download_button(f"Tải {label}", data or b"", file_name=ARTIFACTS[kind], mime=mime, help=title,
                               disabled=data is None, on_click="ignore", width="stretch",
                               icon={"PDF": ":material/picture_as_pdf:", "DXF": ":material/architecture:",
                                     "GLB": ":material/view_in_ar:", "DXF 3D": ":material/deployed_code:",
                                     "DOCX": ":material/description:", "XLSX": ":material/table_chart:"}[label],
                               key=f"download_{edition}_{kind}")
            if note:
                st.caption(note)
            unavailable |= data is None
        ui.section("Thông tin phiên bản", glyph="info")
        ui.html_block("<div>" + "".join((
            ui.fact("Phiên bản", version, "layers"),
            ui.fact("Cập nhật", updated, "calendar", "info"),
            ui.fact("Hồ sơ", "Chưa xuất" if not files else "Thiếu tệp" if unavailable else "Đã tạo", "file",
                    "neutral" if not files else "warning" if unavailable else "success", status=True),
        )) + "</div>")
    return unavailable


def concise_money(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"{vn_num(value / 1_000_000_000, 2)} tỷ đ"
    if abs(value) >= 1_000_000:
        return f"{vn_num(value / 1_000_000, 1)} triệu đ"
    return vnd(value)


def summary_metrics(state: dict, candidate: dict | None) -> None:
    area = state.get("area_table") or {}
    cost = state.get("cost") or {}
    if candidate:
        estimates = candidate.get("chi_so") or {}
        area = estimates
        cost = {"tong_chi_phi": estimates.get("chi_phi"), "chenh_lech": estimates.get("chenh_lech"),
                "vuot_pct": estimates.get("vuot_pct")}
    floors, sfa = area.get("so_tang"), area.get("tong_dien_tich_san")
    counts = area.get("so_phong")
    total = cost.get("tong_chi_phi")
    budget = (state.get("brief") or {}).get("ngan_sach")
    delta = cost.get("chenh_lech")
    if delta is None and total is not None and budget is not None:
        delta = total - budget
    pct = cost.get("vuot_pct")
    assumed = cost.get("ngan_sach_gia_dinh") or any(
        note.startswith("Ngân sách:") for note in (state.get("brief") or {}).get("gia_dinh_bo_sung", []))
    quality = quality_status(state) if candidate is None else None
    if candidate:
        pending = candidate.get("can_xac_minh") or []
        regulation = ("Có tiêu chí vi phạm" if any(i.get("phan_loai") == "vi_pham" for i in candidate.get("loi") or [])
                      else f"Cần xác minh {len(pending)} mục" if pending else "Chưa có hồ sơ kiểm định")
    else:
        regulation = quality["regulatory"]
    unknown = "Chưa xác định"
    delta_amount = f"{'+' if delta > 0 else '−' if delta < 0 else ''}{concise_money(abs(delta))}" if delta is not None else unknown
    reg_tone = "danger" if regulation in (VIOLATION, "Có tiêu chí vi phạm") else "success" if regulation == VERIFIED else "warning"
    ui.kpi_grid([
        ui.kpi("Số tầng", floors if floors is not None else unknown, "layers", compact=floors is None),
        ui.kpi("Số phòng", sum(counts.values()) if isinstance(counts, dict) else unknown, "bed", "success",
               f"{counts.get('ngu', 0)} phòng ngủ" if isinstance(counts, dict) else "", compact=not isinstance(counts, dict)),
        ui.kpi("Diện tích sàn", f"{vn_num(sfa, 2)} m²" if sfa is not None else unknown, "area", "info",
               compact=sfa is None),
        ui.kpi("Tổng chi phí", concise_money(total) if total is not None else unknown, "coins", "warning",
               (("Ước tính · " if candidate else "") + vnd(total)) if total is not None else "", compact=total is None),
        ui.kpi("Chênh lệch ngân sách", delta_amount, "target",
               "warning" if delta is not None and delta > 0 else "neutral",
               f"{pct * 100:+.1f}% · {'Ngân sách giả định' if assumed else 'Ngân sách đã nhập'}" if pct is not None else "",
               compact=delta is None),
        ui.kpi("Xác minh quy chuẩn", regulation, "shield", reg_tone,
               f"Kỹ thuật · {quality['technical']}" if quality else "", compact=True),
    ])
    if candidate is None and preliminary_ready(state):
        st.caption("Đã tạo phương án sơ bộ · cần xác minh quy chuẩn. Chi tiết trong tab Kiểm định.")


def drawing_preview(state: dict, root: Path, release: Path | None, edition: str) -> None:
    drawings = state.get("drawings") or {}
    sheets = drawings.get("sheets") or []
    if not sheets:
        st.info("Phiên bản này chưa có bản vẽ xem trước.")
        return
    first_floor = next((i for i, sheet in enumerate(sheets) if sheet.get("ten") == "Mặt bằng tầng 1"), 0)
    index = st.selectbox("Tờ bản vẽ", range(len(sheets)), index=first_floor,
                         format_func=lambda i: f"{sheets[i]['so_hieu']} · {sheets[i]['ten']}",
                         key=f"sheet_{edition}")
    item = sheets[index]
    png = asset_path(item.get("png"), root)
    drawing_pdf = asset_path(drawings.get("pdf"), root)
    possible_folders = {diagram for diagram in (drawing_pdf.parent / "png" if drawing_pdf else None,
                                                release / "previews" if release else None) if diagram is not None}
    if png is None or png.parent not in possible_folders or not png.is_file():
        st.info("Thiếu ảnh xem trước của tờ này. Dùng tệp PDF nếu còn trong bộ hồ sơ.")
        return
    try:
        with Image.open(png) as image:
            stamp = image.info.get("Description")
            if stamp and stamp != option_stamp(state.get("program") or {}):
                st.warning("Ảnh xem trước thuộc phiên bản khác.")
                return
        viewer_key = f"drawing_{edition}_{state.get('run_id', root.name)}_{index}"
        drawing_viewer.show(viewer_key, png.read_bytes(), f"{item['ten']} · " + (f"Tỉ lệ {item['ti_le']}" if item.get("ti_le") else "Không theo tỉ lệ"))
    except (OSError, ValueError):
        st.info("Không đọc được ảnh xem trước. Dùng tệp PDF nếu còn trong bộ hồ sơ.")


def model_preview(state: dict, root: Path, release: Path | None, edition: str) -> None:
    ui.section("Mô hình 3D", "Dựng từ đúng mặt bằng của phiên bản đang xem. Nội thất và chi tiết cửa chỉ để minh họa.")
    path = asset_path((state.get("final_files") or {}).get("mo_hinh_3d_glb"), root, release)
    if path is None and release is None:
        path = asset_path((state.get("drawings") or {}).get("glb"), root)
    if path is None or not path.is_file():
        st.info("Phiên bản này chưa có mô hình 3D. Hồ sơ xuất trước khi có tính năng cần tạo lại để có mô hình.")
        return
    info = path.stat()
    stamp = option_stamp(state.get("program") or {})
    data, note = cached_document(path, "mo_hinh_3d_glb", stamp, info.st_mtime_ns, info.st_size)
    if data is None:
        st.warning(note)
        return
    model_viewer.show(f"model_{edition}_{state.get('run_id', root.name)}", data)


def description(state: dict, candidate: dict | None) -> None:
    ui.section("Thuyết minh phương án", glyph="file")
    if candidate:
        st.write(candidate.get("mo_ta") or "Chưa có thuyết minh cho phương án này.")
        for floor, rooms in (candidate.get("cong_nang") or {}).items():
            st.write(f"**{floor}** · {', '.join(rooms)}")
        assumptions = candidate.get("gia_dinh") or []
    else:
        if state.get("concept"):
            st.write(state["concept"])
        else:
            st.caption("Chưa có thuyết minh hiện hành.")
        assumptions = state.get("assumptions") or selected_assumptions(state)
        floors = (state.get("area_table") or {}).get("tang") or []
        if floors:
            st.markdown("**Công năng theo tầng**")
        for floor in floors:
            with st.expander(floor["ten"]):
                st.table([{"Phòng": room["ten"], "Kích thước (m)": room["kich_thuoc"],
                           "Diện tích (m²)": room["dien_tich"]} for room in floor["phong"]])
        advice = state.get("fengshui") or {}
        fs = advice.get("thong_tin") or {}
        if state.get("fengshui_enabled") is False:
            st.caption("Đã tắt tư vấn phong thủy.")
        elif advice.get("goi_y") or fs.get("co_du_lieu"):
            with st.expander("Tư vấn phong thủy"):
                if fs.get("co_du_lieu"):
                    st.write(f"Cung {fs['cung_menh']} · Hướng {fs['huong_nha']} · {fs['sao_huong_nha']}")
                    st.caption(f"{fs['goi_y_bep']} {fs['goi_y_ban_tho']}")
                for item in advice.get("goi_y") or []:
                    st.write(f"{item['noi_dung']}. {item['de_xuat']}")
    if assumptions:
        with st.expander("Giả định thiết kế"):
            for line in assumptions:
                st.write("• " + line)


def estimate(state: dict, candidate: dict | None) -> None:
    cost = state.get("cost") or {}
    if not cost or candidate:
        st.info("Phiên bản này chưa có bảng dự toán chi tiết. Tổng ước tính, nếu có, được hiển thị ở phần tóm tắt.")
        return
    if cost.get("ghi_chu"):
        st.write(cost["ghi_chu"])
    ui.section("Bảng hạng mục dự toán", glyph="coins")
    items = [{"Hạng mục": item["hang_muc"], "Đơn vị": item["don_vi"], "Khối lượng": vn_num(item["kl"], 2),
              "Đơn giá": vnd(item["don_gia"]), "Thành tiền": vnd(item["thanh_tien"])} for item in cost.get("hang_muc", [])]
    if cost.get("du_phong") is not None:
        items.append({"Hạng mục": "Dự phòng", "Đơn vị": "—", "Khối lượng": "—", "Đơn giá": "—",
                      "Thành tiền": vnd(cost["du_phong"])})
    if items:
        st.dataframe(items, hide_index=True, width="stretch")
    if cost.get("tiet_kiem"):
        with st.expander("Phương án tiết kiệm"):
            for item in cost["tiet_kiem"]:
                st.write(f"{item['phuong_an']} · khoảng {vnd(item['tiet_kiem'])}")


def review_panel(state: dict, candidate: dict | None, edition: str) -> None:
    review = state.get("review") or {}
    if candidate is not None:
        st.caption("Đối chiếu sơ bộ cho phương án đang xem.")
        review = {"kiem_tra": candidate.get("kiem_tra"), "loi": candidate.get("loi")}
        missing = [] if review["kiem_tra"] else candidate.get("can_xac_minh") or []
        for issue in missing:
            with st.expander(issue["muc"]):
                st.write(issue_label(issue))
                st.write(issue["noi_dung"])
                if issue.get("nguon"):
                    st.caption(issue["nguon"])
                for note in issue.get("du_lieu_thieu", []):
                    st.write(f"• {note}")
                if issue.get("cach_bo_sung"):
                    st.write(issue["cach_bo_sung"])
    checks = review_rows(review, state.get("brief"))
    if checks:
        selected = st.selectbox("Chi tiết tiêu chí", range(len(checks)), format_func=lambda i: checks[i]["criterion"],
                                key=f"criterion_{edition}")
        row = checks[selected]
        with st.container(border=True):
            st.write(f"**{row['criterion']}** · {row['status']}")
            threshold = "Giá trị tham khảo" if row["status"] == MISSING else "Ngưỡng phép kiểm"
            for label, key in ((threshold, "threshold"), ("Nguồn", "source"), ("Phạm vi", "scope"),
                               ("Lý do", "reason"), ("Trích dẫn", "excerpt")):
                if row.get(key) and row[key] != "—":
                    st.write(f"**{label}** · {row[key]}")
            if row["missing"]:
                st.markdown("**Dữ liệu hoặc căn cứ cần bổ sung**")
                for item in row["missing"]:
                    st.write(f"• {item}")
            if row["action"]:
                st.write(f"**Cách bổ sung** · {row['action']}")
        st.table([{"Tiêu chí": item["criterion"], "Phân loại": item["status"], "Số liệu": item["actual"]}
                  for item in checks])
    else:
        st.info("Phiên bản này chưa có kết quả kiểm định.")
    notes = list(review.get("loi") or []) + (review.get("canh_bao") or [])
    if candidate is None:
        notes.extend(item for item in state.get("remaining_issues") or [] if item not in notes)
    if notes:
        with st.expander("Lỗi và khuyến nghị"):
            for issue in notes:
                st.write(f"**{issue.get('muc', 'Kiểm tra')}** · {issue_label(issue)}")
                st.write(issue["noi_dung"])
                if issue.get("de_xuat"):
                    st.caption(issue["de_xuat"])


run = current_run()
live = run.state() if run else {}
if not run:
    with st.container(key="page_heading"):
        ui.page_header("Kết quả", "Xem bản vẽ và tải hồ sơ theo phiên bản phương án.")
    st.info("Chưa có dự án để xem hồ sơ.")
    st.page_link("views/projects.py", label="Tạo thiết kế mới", icon=":material/add_circle:")
    st.stop()

runs = events.list_runs(None, recent_activity=True)
record = next((row for row in runs if row["run_id"] == run.run_id), {})
root = Path(record.get("output_dir") or live.get("output_dir") or (Path("outputs") / run.run_id)).resolve()
current_release = release_path(live, root)
releases, unidentified = list_releases(root, run.run_id, live,
                                       lambda: (snap.values for snap in get_graph().get_state_history(run.config)))
active = next((release for release in releases if release.path == current_release), None)
current_program = live.get("program") or {}
choices = {"current": (f"{version_name(current_program, saved=bool(live.get('final_files')))} · Hiện hành", active.state if active else live,
                       active.path if active else current_release, None)}
published_stamps = set()
for release in releases:
    program = release.state.get("program") or {}
    stamp = option_stamp(program)
    if stamp:
        published_stamps.add(stamp)
    if release is active:
        continue
    date = datetime.fromtimestamp(release.modified, tz=timezone(timedelta(hours=7))).strftime("%d/%m %H:%M")
    choices[f"release_{release.path.name}"] = (
        f"{version_name(program, saved=True)} · Bản lưu {date} · {release.path.name[:6]}", release.state, release.path, None)
options = live.get("options") or []
for option in options:
    program = option.get("program") or {}
    stamp = option_stamp(program)
    if option["id"] != current_program.get("phuong_an") and (not stamp or stamp not in published_stamps):
        choices[f"option_{option['id']}"] = (f"{version_name(program)} · Ước tính", {}, None, option)

with st.container(key="page_heading"):
    ui.page_header("Kết quả", "Xem bản vẽ và bộ hồ sơ theo từng phiên bản phương án.")
    projects, versions, _ = st.columns([1.2, 1.4, .8], vertical_alignment="bottom")
    with projects:
        run_picker(runs, run, "results_run", current_name=project_name(run, live), show_current_status=False,
                   label_visibility="visible")
    with versions:
        key = f"results_edition_{run.run_id}"
        if st.session_state.pop("results_follow_current", None) == run.run_id or st.session_state.get(key) not in choices:
            st.session_state[key] = "current"
        edition = st.selectbox("Phương án / phiên bản", list(choices), format_func=lambda ident: choices[ident][0], key=key)

_, state, release, candidate = choices[edition]
if candidate:
    state = {"brief": live.get("brief")}
elif state.get("final_files") and option_stamp(state.get("program") or {}) and (
        state.get("revision_id") != state["program"].get("revision_id")):
    state = {}
    st.warning("Chưa đối chiếu được số liệu và mã phiên bản của hồ sơ.")
with st.container(key="result_metrics"):
    summary_metrics(state, candidate)
if candidate is None and (state.get("outcome") == "not_passed" or edition == "current" and run.status == "not_passed"):
    exhausted = state.get("repair_limit_reached")
    st.warning("Chưa đạt · đã hết số vòng sửa tự động. Xem vấn đề còn lại trong Kiểm định."
               if exhausted else "Chưa đạt · xem vấn đề còn lại trong Kiểm định.")
    if edition == "current":
        adjustment_panel(run, live, "results")  # đề xuất có sau bản lưu hồ sơ nên đọc trạng thái mới nhất
tabs = st.tabs([":material/image: Bản vẽ", ":material/view_in_ar: Mô hình 3D", ":material/description: Thuyết minh",
                ":material/calculate: Dự toán", ":material/verified_user: Kiểm định"],
               key="results_view", on_change="rerun")
tab_index = next(index for index, tab in enumerate(tabs) if tab.open)
with tabs[tab_index]:
    main, downloads = st.columns([2.6, 1], gap="medium")
with main.container(border=True, key="result_preview"):
    if tab_index == 0:
        drawing_preview(state, root, release, edition)
    elif tab_index == 1:
        model_preview(state, root, release, edition)
    elif tab_index == 2:
        description(state, candidate)
    elif tab_index == 3:
        estimate(state, candidate)
    else:
        scoped_candidate = candidate
        if edition == "current" and candidate is None and not state.get("review"):
            revision = state.get("revision_id")
            scoped_candidate = next((item for item in options if revision and item["program"].get("revision_id") == revision
                                     and item.get("kiem_tra")), None)
        review_panel(state, scoped_candidate, edition)
        if (edition == "current" and (state.get("review") or {}).get("chua_du_can_cu")
                and run.status in ("done", "not_passed") and run.can_rerun("reviewer", live)):
            brief = state.get("brief") or {}
            lot = brief.get("lo_dat") or {}
            missing_identity = (not lot.get("ma_lo_dat") or not lot.get("tinh") or
                                any(note.startswith("Địa điểm:") for note in brief.get("gia_dinh_bo_sung", [])))
            if st.button("Kiểm định lại sau khi bổ sung nguồn", icon=":material/replay:", disabled=missing_identity,
                         help="Bổ sung mã lô đất và tỉnh/thành đã xác nhận trong yêu cầu thiết kế."
                         if missing_identity else None):
                if run.rerun_agent("reviewer", expected_revision=state.get("revision_id")):
                    st.rerun()
                st.warning("Lượt đang cập nhật. Hãy thử lại sau khi xử lý xong.")
with downloads:
    saved_release = next((item for item in releases if item.path == release), None)
    updated = "Chưa xác định"
    if saved_release:
        updated = datetime.fromtimestamp(saved_release.modified, timezone(timedelta(hours=7))).strftime("%d/%m/%Y · %H:%M")
    elif edition == "current" and record.get("updated"):
        try:
            updated = datetime.fromisoformat(record["updated"]).strftime("%d/%m/%Y · %H:%M")
        except ValueError:
            pass
    version = version_name((candidate or state).get("program") or {}, saved=bool(state.get("final_files")))
    unavailable = download_cards(state, root, release, edition, version, updated)
    missing_model = not (state.get("final_files") or {}).get("mo_hinh_3d_glb")
    if edition != "current" and not candidate:
        st.caption("Đang xem hồ sơ đã lưu của phiên bản này.")
    if edition == "current" and not state.get("final_files"):
        st.caption("Hồ sơ sẽ tải được sau khi hoàn tất đối chiếu.")
        if run.status == "error":
            st.caption("Lượt gặp lỗi. Mở Studio AI để xem bước xử lý.")
        if run.status in ("awaiting_approval", "running", "needs_input"):
            st.page_link("views/studio.py", label="Mở Studio AI", icon=":material/view_in_ar:")

    program = (candidate or state).get("program") or {}
    revision = program.get("revision_id")
    selectable = next((o for o in options if o.get("eligible") is True
                       and revision and o["program"].get("revision_id") == revision
                       and o["id"] != current_program.get("phuong_an")), None)
    restartable = run.status in ("done", "not_passed") and bool(live.get("history"))
    if restartable and selectable:
        st.caption("Hành động này chạy lại các bước xuất hồ sơ và có thể dùng model đã cấu hình.")
        if st.button("Chọn phương án và tạo lại hồ sơ", type="primary", width="stretch"):
            if run.choose_option(selectable["id"], expected_revision=revision):
                st.session_state["results_follow_current"] = run.run_id
                st.rerun()
            st.warning("Phương án vừa thay đổi. Chọn lại phiên bản để tiếp tục.")
    elif restartable and (unavailable or missing_model) and edition == "current" and state.get("final_files") and run.can_rerun("drafter", live):
        st.caption("Tạo lại sẽ chạy lại các bước xuất hồ sơ và có thể dùng model đã cấu hình.")
        if st.button("Tạo lại hồ sơ hiện hành", width="stretch"):
            if run.rerun_agent("drafter", expected_revision=revision):
                st.rerun()
            st.warning("Lượt đang cập nhật. Thử lại sau khi kết thúc.")

if options:
    with st.expander("So sánh các phương án hiện hành"):
        show_result_options(live)
custom_notes = list(((live if edition == "current" else state).get("custom_outputs") or {}).values())
if custom_notes and not candidate:
    with st.expander(f"Nhận xét của agent tùy biến ({len(custom_notes)})", icon=":material/smart_toy:"):
        show_custom_notes(custom_notes, (live if edition == "current" else state).get("revision_id"))
if unidentified:
    st.caption(f"{unidentified} thư mục hồ sơ cũ thiếu snapshot để đối chiếu phiên bản.")
if edition == "current" and run.status in ("awaiting_approval", "needs_input") and run.interrupt_payload:
    with st.expander("Cần bổ sung yêu cầu" if run.status == "needs_input" else "Tác vụ đang chờ duyệt"):
        approval_box(run, "results")
elif edition == "current" and not state.get("final_files"):
    assessment = live.get("brief_assessment") or {}
    for note in [*assessment.get("questions", []), *assessment.get("conflicts", [])]:
        st.write("• " + note)
if edition == "current":
    auto_refresh(run)
