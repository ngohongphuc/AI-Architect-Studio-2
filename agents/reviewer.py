"""Đối chiếu hình học và ghi rõ giới hạn nguồn quy chuẩn."""
from __future__ import annotations

from agents.base import agent_node
from tools.design_option import requires_repair
from tools.docx_writer import vn_num as vf
from llm import invoke_text
from tools import rag
from tools.layout_algorithm import EPS, OPEN_TYPES
from tools.rules import inspect_evidence, load_rules, max_density, min_room

NEED_LIGHT_TYPES = {"ngu", "lam_viec", "sinh_hoat", "khach", "bep", "tho"}


def _pct(v: float) -> str:
    return f"{vf(v * 100)}%".replace(".", ",")


def _overlap(a: dict, b: dict) -> float:
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return w * h if w > EPS and h > EPS else 0.0


def _adjacent(a: dict, b: dict) -> bool:
    """Hai phòng có chung một đoạn tường (> 0,3 m)."""
    if abs(a["y"] + a["h"] - b["y"]) < 1e-3 or abs(b["y"] + b["h"] - a["y"]) < 1e-3:
        return min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]) > 0.3
    if abs(a["x"] + a["w"] - b["x"]) < 1e-3 or abs(b["x"] + b["w"] - a["x"]) < 1e-3:
        return min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]) > 0.3
    return False


def has_daylight(room: dict, rooms: list[dict], layout: dict) -> bool:
    """Phòng được chiếu sáng trực tiếp: chạm mặt tiền, hoặc kề ban công / sân / giếng trời,
    hoặc chạm mặt sau khi có sân sau."""
    b = layout["building"]
    if abs(room["y"] - b["y"]) < 1e-3:
        return True
    if abs(room["y"] + room["h"] - (b["y"] + b["l"])) < 1e-3 and layout["san_sau"] > 0:
        return True
    return any(o["loai"] in OPEN_TYPES and _adjacent(room, o) for o in rooms if o is not room)


def code_checks(state: dict, *, lookup_citations: bool = True) -> tuple[list, list, list]:
    """Trả về (danh sách kiểm tra, lỗi, cảnh báo)."""
    brief, program, layout, area = state["brief"], state["program"], state["layout"], state["area_table"]
    rules = load_rules()
    checks, issues, warns = [], [], []
    gara = brief["yeu_cau_phong"].get("gara")

    assumed_location = any(a.startswith("Địa điểm:") for a in brief.get("gia_dinh_bo_sung", []))
    evidence_report = inspect_evidence(brief["lo_dat"], assumed_location=assumed_location)
    sources = {
        "Mật độ xây dựng": ("mat_do_xay_dung", "Lô nhà ở riêng lẻ, còn phụ thuộc quy hoạch địa phương", "qcvn_01"),
        "Số tầng": ("so_tang_toi_da", "Phạm vi phần mềm 1–5 tầng. Giới hạn tại lô đất cần hồ sơ quy hoạch.", None),
        "Chiều cao tầng": ("chieu_cao_tang", "Nhà ở riêng lẻ, chỉ đối chiếu khoảng tham chiếu", "tcvn_4451"),
        "Chiều cao thông thủy": ("chieu_cao_tang", "Phòng ở, chiều cao tính sơ bộ từ chiều cao tầng", "tcvn_4451"),
        "Diện tích, kích thước tối thiểu phòng": ("dien_tich_toi_thieu", "Phòng trong phương án nhà ở sơ bộ", "tcvn_4451"),
        "Chiếu sáng tự nhiên phòng ở": (None, "Phòng ở. Hình học chỉ xác định khả năng tiếp giáp mặt thoáng.", "tcvn_4451"),
    }

    def add(muc, hien_tai, cho_phep, dat, query, issue=None):
        c = {"muc": muc, "hien_tai": hien_tai, "cho_phep": cho_phep,
             "dat": dat, "ket_luan": "Đạt" if dat else "Không đạt", "trich_dan": None,
             "nguon": "Brief và bảng diện tích" if muc in ("Số phòng khớp yêu cầu", "Số tầng khớp yêu cầu")
             else "Phép kiểm hình học của ứng dụng",
             "pham_vi": "Hình học và chương trình phòng của phương án hiện tại.", "loai": "Kỹ thuật"}
        if query:
            key, scope, prefix = sources.get(
                muc, ("cau_thang", "Cầu thang trong phương án nhà ở sơ bộ", "tcvn_4451"))
            citation = rag.cite(query, source_prefix=prefix) if prefix and lookup_citations else None
            c.update(dat=None, ket_luan="chưa đủ căn cứ", ket_qua_tham_chieu=dat, loai="Quy chuẩn",
                     nguon=rules.get(key, {}).get("nguon") if key else "data/rules.json – chieu_sang_bat_buoc",
                     pham_vi=scope, trich_dan=citation)
            evidence = evidence_report.verified.get((muc, cho_phep))
            if evidence:
                c.update(evidence, dat=dat, da_xac_minh=True, ket_luan="Đạt" if dat else "Không đạt do vi phạm")
            else:
                c["ly_do"] = evidence_report.reason(muc, cho_phep)
                c["du_lieu_thieu"], c["cach_bo_sung"] = evidence_report.gaps(muc, cho_phep)
                input_only = evidence_report.input_gaps and evidence_report.input_gaps == evidence_report.blockers
                c["phan_loai"] = "thieu_thong_tin" if input_only else "thieu_nguon"
        checks.append(c)
        if not dat:
            if issue is None and query:
                code = "CAU_THANG" if muc not in sources else None
                if code:
                    issue = {"loai": "Kỹ thuật", "ma": code, "noi_dung": f"{muc} ngoài ngưỡng tham chiếu",
                             "de_xuat": "Rà soát hình học cầu thang"}
            if issue:
                issues.append({**issue, "muc": muc, "hien_tai": hien_tai, "cho_phep": cho_phep,
                               **issue_evidence(c)})
        return c

    def issue_evidence(check):
        return {
            "phan_loai": ("tham_chieu" if check["dat"] is None else
                          "vi_pham" if check.get("da_xac_minh") else "ky_thuat"),
            "nguon": check.get("nguon"), "ly_do": check.get("ly_do"), "trich_dan": check.get("trich_dan"),
            "pham_vi": check.get("pham_vi"),
        }

    # 1. Mật độ xây dựng
    lot = area["dien_tich_dat"]
    dmax = max_density(lot)
    d = area["mat_do_xay_dung"]
    allowed_m2 = round(dmax * lot, 2)
    add("Mật độ xây dựng", _pct(d), f"≤ {_pct(dmax)}", d <= dmax + 1e-4,
        f"mật độ xây dựng thuần tối đa lô đất nhà ở riêng lẻ {lot:.0f} m²",
        {"loai": "Quy chuẩn", "ma": "MAT_DO", "du_lieu": {"cho_phep_m2": allowed_m2},
         "noi_dung": f"Diện tích xây dựng {vf(area['dien_tich_xay_dung'])} m² vượt mức {vf(allowed_m2)} m²",
         "de_xuat": f"Thêm sân sau khoảng {vf((area['dien_tich_xay_dung'] - allowed_m2) / layout['lot']['w'])} m"})
    # 2. Số tầng
    fmax = rules["so_tang_toi_da"]["gia_tri"]
    add("Số tầng", f"{area['so_tang']} tầng", f"≤ {fmax} tầng", area["so_tang"] <= fmax, "số tầng chiều cao công trình",
        {"loai": "Quy chuẩn", "ma": "SO_TANG", "noi_dung": "Vượt số tầng cho phép", "de_xuat": "Giảm 1 tầng"})
    # 3. Chiều cao tầng
    h = rules["chieu_cao_tang"]
    hs = layout["heights"]
    ok_h = h["tang_1_min"] <= hs[0] <= h["tang_1_max"] and all(h["tang_khac_min"] <= x <= h["tang_khac_max"]
                                                              for x in hs[1:])
    thong_thuy = min(hs) - h["chieu_day_san"] - 0.1
    add("Chiều cao tầng", " / ".join(vf(x) for x in hs) + " m",
        f"T1 {h['tang_1_min']}–{h['tang_1_max']} m; tầng khác {h['tang_khac_min']}–{h['tang_khac_max']} m",
        ok_h, "chiều cao tầng nhà ở liền kề",
        {"loai": "Quy chuẩn", "ma": "CHIEU_CAO_TANG", "noi_dung": "Chiều cao tầng ngoài giới hạn",
         "de_xuat": "Điều chỉnh chiều cao tầng"})
    add("Chiều cao thông thủy", f"{vf(thong_thuy, 2)} m", f"≥ {h['thong_thuy_min']} m", thong_thuy >= h["thong_thuy_min"],
        "chiều cao thông thủy phòng ở", {"loai": "Quy chuẩn", "ma": "CHIEU_CAO_TANG",
                                        "noi_dung": "Thông thủy thấp", "de_xuat": "Tăng chiều cao tầng"})
    # 4. Cầu thang
    st, cr = layout["stair"], rules["cau_thang"]
    worst = max(st["cac_tang"], key=lambda f: f["bac_cao"])
    add("Bề rộng vế thang", f"{vf(st['ve_rong'], 2)} m", f"≥ {cr['be_rong_ve_min']} m", st["ve_rong"] >= cr["be_rong_ve_min"],
        "chiều rộng vế thang nhà ở riêng lẻ", {"loai": "Quy chuẩn", "ma": "CAU_THANG", "noi_dung": "Vế thang hẹp",
                                              "de_xuat": "Tăng bề rộng thang"})
    add("Chiều cao bậc thang", f"{worst['bac_cao'] * 1000:.0f} mm", f"≤ {cr['bac_cao_max'] * 1000:.0f} mm",
        worst["bac_cao"] <= cr["bac_cao_max"], "chiều cao bậc thang",
        {"loai": "Quy chuẩn", "ma": "CAU_THANG", "noi_dung": "Bậc thang cao", "de_xuat": "Tăng số bậc"})
    min_tread = min(f["bac_rong"] for f in st["cac_tang"])
    add("Chiều rộng bậc thang", f"{min_tread * 1000:.0f} mm", f"≥ {cr['bac_rong_min'] * 1000:.0f} mm",
        min_tread >= cr["bac_rong_min"], "chiều rộng mặt bậc", None)
    blondel = [f["blondel"] for f in st["cac_tang"]]
    add("Công thức 2h + b", f"{min(blondel):.3f}–{max(blondel):.3f} m", f"{cr['blondel_min']}–{cr['blondel_max']} m",
        all(cr["blondel_min"] <= value <= cr["blondel_max"] for value in blondel), "kích thước bậc 2h + b", None)
    max_steps = max(max(f["bac_ve_1"], f["bac_ve_2"]) for f in st["cac_tang"])
    add("Số bậc mỗi vế", f"{max_steps} bậc", f"≤ {cr['so_bac_ve_max']} bậc", max_steps <= cr["so_bac_ve_max"],
        "mỗi vế thang không quá bậc chiếu nghỉ", None)

    # 5. Kích thước tối thiểu phòng + chiếu sáng
    small = []
    dark = []
    room_thresholds = {}
    for k, fl in layout["floors"].items():
        for r in fl["rooms"]:
            m = min_room(r["loai"], gara)
            if m:
                need_a = m.get("dien_tich", 0)
                need_c = m.get("canh", 0)
                room_thresholds[r["loai"]] = f"{r['loai']}: ≥ {need_a:g} m² và cạnh ≥ {need_c:g} m"
                short_side = min(r["w"], r["h"])
                if r["dien_tich"] + 1e-6 < need_a or short_side + 1e-6 < need_c:
                    small.append((k, r, need_a, need_c))
            if r["loai"] in NEED_LIGHT_TYPES and not has_daylight(r, fl["rooms"], layout):
                dark.append((k, r))
    room_check = add("Diện tích, kích thước tối thiểu phòng",
        "Đủ theo phép kiểm" if not small else f"{len(small)} phòng dưới ngưỡng",
        " | ".join(room_thresholds[k] for k in sorted(room_thresholds)) or "Không có loại phòng có ngưỡng",
        not small, "diện tích kích thước tối thiểu phòng ngủ phòng khách bếp")
    for k, r, need_a, need_c in small:
        issues.append({"loai": "Quy chuẩn", "ma": "PHONG_NHO", "muc": "Diện tích phòng tối thiểu",
                       "noi_dung": f"{r['ten']} tầng {k}: {vf(r['dien_tich'])} m², cạnh ngắn {vf(min(r['w'], r['h']), 2)} m",
                       "hien_tai": f"{vf(r['dien_tich'])} m²", "cho_phep": f"≥ {need_a} m², cạnh ≥ {need_c} m",
                       "de_xuat": f"Tăng diện tích {r['ten']}", "du_lieu": {"tang": int(k), "phong": r["ten"],
                                                                           "can": need_a},
                       **issue_evidence(room_check)})
    must = set(rules["chieu_sang_bat_buoc"])
    dark_must = [(k, r) for k, r in dark if r["loai"] in must]
    light_check = add("Chiếu sáng tự nhiên phòng ở",
        "Có tiếp giáp mặt thoáng" if not dark_must else f"{len(dark_must)} phòng thiếu tiếp giáp mặt thoáng",
        "Tiếp giáp mặt thoáng theo hình học bố trí (" + ", ".join(sorted(must)) + ")",
        not dark_must, "phòng ở chiếu sáng tự nhiên trực tiếp giếng trời")
    for k, r in dark:
        item = {"loai": "Quy chuẩn", "ma": "THIEU_SANG", "muc": "Chiếu sáng tự nhiên",
                "noi_dung": f"{r['ten']} tầng {k} không tiếp giáp mặt thoáng / giếng trời",
                "de_xuat": f"Dời {r['ten']} sát giếng trời hoặc mặt tiền",
                "du_lieu": {"tang": int(k), "phong": r["ten"]}, "phan_loai": "tham_chieu"}
        if r["loai"] in must:
            item.update(issue_evidence(light_check))
        (issues if r["loai"] in must else warns).append(item)

    # 6. Kiểm tra kỹ thuật bằng code
    overlaps = []
    gaps = []
    outside = []
    stair_rects = []
    for k, fl in layout["floors"].items():
        rooms = [r for r in fl["rooms"] if r["loai"] != "san"]
        bounds = layout["building"]
        for r in rooms:
            if (r["w"] <= 0 or r["h"] <= 0 or r["x"] < bounds["x"] - 0.001 or r["y"] < bounds["y"] - 0.001
                    or r["x"] + r["w"] > bounds["x"] + bounds["w"] + 0.001
                    or r["y"] + r["h"] > bounds["y"] + bounds["l"] + 0.001):
                outside.append(f"T{k}: {r['ten']}")
        for i, a in enumerate(rooms):
            for b in rooms[i + 1:]:
                if _overlap(a, b) > 1e-4:
                    overlaps.append(f"T{k}: {a['ten']} × {b['ten']}")
        total = sum(r["dien_tich"] for r in rooms)
        if abs(total - area["dien_tich_xay_dung"]) > 0.5:
            gaps.append(f"T{k}: tổng {vf(total, 2)} ≠ {vf(area['dien_tich_xay_dung'], 2)}")
        s = next(r for r in rooms if r["loai"] == "thang")
        stair_rects.append((s["x"], s["y"], s["w"], s["h"]))
    add("Phòng nằm trong vùng xây dựng", "Đạt" if not outside else ", ".join(outside[:3]),
        "Tọa độ trong biên, rộng và sâu dương", not outside, None,
        {"loai": "Kỹ thuật", "ma": "KHONG_DU_CHO", "noi_dung": "Phòng nằm ngoài biên hoặc có kích thước không hợp lệ",
         "de_xuat": "Điều chỉnh chương trình và bố trí lại"})
    add("Không chồng lấn phòng", "Đạt" if not overlaps else "; ".join(overlaps[:3]), "0 chồng lấn", not overlaps,
        None, {"loai": "Kỹ thuật", "ma": "KHONG_DU_CHO", "noi_dung": "Phòng chồng lấn",
                           "de_xuat": "Bố trí lại"})
    add("Phủ kín diện tích xây dựng", "Đạt" if not gaps else "; ".join(gaps[:3]), "Tổng phòng = DT xây dựng",
        not gaps, None, {"loai": "Kỹ thuật", "ma": "KHONG_DU_CHO", "noi_dung": "Có khoảng trống",
                                        "de_xuat": "Bố trí lại"})
    aligned = len(set(stair_rects)) == 1
    add("Cầu thang thẳng hàng các tầng", "Thẳng hàng" if aligned else "Lệch", "Thẳng hàng", aligned, None,
        {"loai": "Kỹ thuật", "ma": "KHONG_DU_CHO", "noi_dung": "Cầu thang lệch giữa các tầng", "de_xuat": "Cố định lõi"})
    add("Đủ chỗ bố trí phòng", "Đạt" if layout["feasible"] else "Thiếu chiều sâu", "Mọi phòng ≥ kích thước tối thiểu",
        layout["feasible"], None, {"loai": "Kỹ thuật", "ma": "KHONG_DU_CHO",
                                                     "noi_dung": "Không đủ chiều sâu", "de_xuat": "Giảm diện tích phòng"})

    # 7. Nhất quán với brief
    yc = brief["yeu_cau_phong"]
    cnt = area["so_phong"]
    want = {"ngu": yc["phong_ngu"], "tho": yc["phong_tho"], "gara": int(bool(yc.get("gara"))),
            "lam_viec": yc["phong_lam_viec"]}
    mismatch = [f"{k}: {cnt.get(k, 0)}/{v}" for k, v in want.items() if cnt.get(k, 0) != v]
    add("Số phòng khớp yêu cầu", "Khớp" if not mismatch else ", ".join(mismatch), "Theo brief", not mismatch, None,
        {"loai": "Nhất quán", "ma": "THIEU_PHONG", "noi_dung": "Số phòng khác yêu cầu: " + ", ".join(mismatch),
         "de_xuat": "Bố trí theo số phòng trong brief"})
    expected_floors = yc.get("so_tang")
    if expected_floors is not None:
        add("Số tầng khớp yêu cầu", str(area["so_tang"]), str(expected_floors),
            area["so_tang"] == expected_floors, None,
            {"loai": "Nhất quán", "ma": "SAI_SO_TANG", "noi_dung": "Số tầng khác brief đã chốt.",
             "de_xuat": "Xem lại yêu cầu số tầng và quy mô."})
    return checks, issues, warns


def verification_items(checks: list[dict]) -> list[dict]:
    return [{"ma": "THIEU_CAN_CU", "muc": check["muc"], "phan_loai": check["phan_loai"],
             "noi_dung": check["ly_do"], "pham_vi": check["pham_vi"], "hien_tai": check.get("hien_tai"),
             "cho_phep": check.get("cho_phep"), "nguon_tham_chieu": check.get("nguon"),
             "du_lieu_thieu": check.get("du_lieu_thieu", []), "cach_bo_sung": check.get("cach_bo_sung", "")}
            for check in checks if check["dat"] is None]


def repair_target(issues: list) -> str:
    scale_codes = {"MAT_DO", "SO_TANG", "CHIEU_CAO_TANG", "THIEU_PHONG", "SAI_SO_TANG"}
    return "concept_architect" if any(i["ma"] in scale_codes for i in issues) else "architect"


def review_design(state: dict) -> dict:
    checks, issues, warns = code_checks(state)
    # loại trùng mã + dữ liệu
    seen, uniq = set(), []
    for i in issues:
        key = (i.get("ma"), str(i.get("du_lieu")), i.get("noi_dung"))
        if key not in seen:
            seen.add(key)
            uniq.append(i)
    blockers = [i for i in uniq if requires_repair(i)]
    advisory = [i for i in uniq if not requires_repair(i)]
    evidence = verification_items(checks)
    review = {"dat": not (blockers or evidence),
              "dat_ky_thuat": not any(c["dat"] is False for c in checks if c["loai"] == "Kỹ thuật"),
              "loi": blockers, "chua_du_can_cu": evidence,
              "canh_bao": advisory + warns, "kiem_tra": checks, "vong": state.get("iteration", 0)}
    if blockers:
        txt = invoke_text("Bạn là kỹ sư thẩm tra thiết kế nhà ở Việt Nam.",
                          "Tóm tắt ngắn gọn (≤ 60 từ) các lỗi sau cho kiến trúc sư sửa:\n" +
                          "\n".join(f"- {i['muc']}: {i['noi_dung']} (đề xuất: {i['de_xuat']})" for i in blockers))
        review["nhan_xet"] = f"Phát hiện {len(blockers)} vấn đề kỹ thuật hoặc vi phạm có căn cứ."
        if evidence:
            review["nhan_xet"] += " Kết luận quy chuẩn: chưa đủ căn cứ."
        if txt:
            review["dien_giai_loi"] = txt
    else:
        review["nhan_xet"] = ("Các phép kiểm tra sơ bộ chưa phát hiện sai lệch. Kết luận quy chuẩn: chưa đủ căn cứ."
                              if evidence else "Đạt các tiêu chí đã đối chiếu trong phạm vi kiểm tra.")
    return review


@agent_node("reviewer")
def run(state: dict) -> dict:
    review = review_design(state)
    fallback = "cost_estimator"
    issues = [issue for issue in review["loi"] if requires_repair(issue)]
    result = {"review": review, "review_issues": issues,
              "route": fallback, "_to": fallback, "_output": review, "_summary": review["nhan_xet"]}
    if issues:
        for option in state.get("options") or []:
            if option["program"].get("revision_id") == state.get("revision_id"):
                rejected = {k: v for k, v in option.items() if k != "ly_do_uu_tien"}
                rejected.update(eligible=False, loi=issues, can_xac_minh=review.get("chua_du_can_cu", []))
                result["options"] = [rejected if o["id"] == option["id"] else o for o in state["options"]]
                if state.get("recommended_option") == option["id"]:
                    result["recommended_option"] = None
                break
        result.update(route="coordinate_repair", repair_target=repair_target(issues), repair_fallback="end",
                      feedback=issues, feedback_source="reviewer", _to="project_manager", _feedback=True)
    return result
