"""Nhãn và dữ liệu trình bày theo từng tiêu chí, kể cả các lượt đã lưu."""

MISSING = "Chưa đủ căn cứ đánh giá"
VIOLATION = "Không đạt do vi phạm"
VERIFIED = "Đủ căn cứ cho các tiêu chí đã kiểm"
PRELIMINARY = "Đã tạo phương án sơ bộ — cần xác minh quy chuẩn"


def review_rows(review: dict, brief: dict | None = None) -> list[dict]:
    brief = brief or {}
    rows = []
    for check in review.get("kiem_tra") or []:
        value = check.get("dat")
        citation = check.get("trich_dan") or {}
        kind = check.get("loai")
        regulatory = kind == "Quy chuẩn" or value is None or (not kind and bool(citation))
        file_name = citation.get("nguon") or ""
        page = citation.get("muc") or ""
        verified = check.get("da_xac_minh") is True
        source = check.get("nguon")
        reason = check.get("ly_do") or ""
        missing = check.get("du_lieu_thieu") or []
        action = check.get("cach_bo_sung") or ""
        if regulatory and (value is None or not verified):
            status, tone = MISSING, "warning"
            if not reason:
                lot = brief.get("lo_dat") or {}
                parcel = "Brief của lượt này thiếu mã lô đất. " if lot and not lot.get("ma_lo_dat") else ""
                reason = parcel + "Lượt này chưa lưu căn cứ xác minh đúng tiêu chí và ngưỡng."
            refs = dict.fromkeys(item for item in (file_name, source) if item)
            source = "Tham chiếu: " + " · ".join(refs) if refs else "—"
            if not missing:
                missing = [reason]
                action = ("Đối chiếu mã lô đất và tỉnh/thành trong brief với PDF và bản ghi "
                          "can_cu_da_xac_minh.json trong data/quy_chuan/. Chạy lại Kiểm định quy chuẩn sau khi bổ sung.")
        elif regulatory:
            status, tone = (VIOLATION, "error") if value is False else ("Đạt theo nguồn xác minh", "success")
            source = " · ".join(item for item in (source, file_name, page) if item)
        else:
            status, tone = ("Không đạt kỹ thuật", "error") if value is False else ("Đạt phép kiểm kỹ thuật", "success")
            source = source or ("Brief và bảng diện tích" if check["muc"] == "Số phòng khớp yêu cầu"
                                else "Phép kiểm hình học của ứng dụng")
        rows.append({
            "criterion": check["muc"], "actual": check.get("hien_tai", ""), "threshold": check.get("cho_phep", ""),
            "regulatory": regulatory, "status": status, "tone": tone, "source": source,
            "reason": reason, "scope": check.get("pham_vi") or "", "missing": missing, "action": action,
            "excerpt": citation.get("trich") or "",
        })
    return rows


def regulatory_label(rows: list[dict]) -> str:
    rules = [row for row in rows if row["regulatory"]]
    if not rules:
        return "Chưa có đánh giá"
    if any(row["status"] == VIOLATION for row in rules):
        return VIOLATION
    if any(row["status"] == MISSING for row in rules):
        return MISSING
    return VERIFIED


def quality_status(state: dict) -> dict:
    rows = review_rows(state.get("review") or {}, state.get("brief"))
    technical = [row for row in rows if not row["regulatory"]]
    issues = state.get("remaining_issues") or []
    regulatory = regulatory_label(rows)
    if any(issue.get("phan_loai") == "vi_pham" for issue in issues):
        regulatory = VIOLATION
    technical_fail = (any(row["tone"] == "error" for row in technical)
                      or any(issue.get("phan_loai") == "ky_thuat" for issue in issues))
    return {"technical": "Không đạt" if technical_fail else "Đạt" if technical else "Chưa kiểm tra",
            "regulatory": regulatory}


def preliminary_ready(state: dict) -> bool:
    quality = quality_status(state)
    return (bool(state.get("final_files")) and state.get("outcome") in (None, "done") and quality["technical"] != "Không đạt"
            and quality["regulatory"] in (MISSING, "Chưa có đánh giá"))


def issue_label(issue: dict) -> str:
    if issue.get("ma") == "THIEU_CAN_CU":
        return {"thieu_nguon": "Thiếu nguồn hoặc phạm vi áp dụng",
                "thieu_thong_tin": "Thiếu thông tin lô đất"}.get(issue.get("phan_loai"), MISSING)
    return {
        "vi_pham": VIOLATION, "tham_chieu": "Cần xem lại theo ngưỡng tham chiếu",
        "ky_thuat": "Không đạt kỹ thuật", "ngan_sach": "Vượt ngân sách",
    }.get(issue.get("phan_loai"), "Vấn đề còn lại")
