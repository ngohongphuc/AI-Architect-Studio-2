"""Chấm và xem lại chất lượng công việc theo lần thực hiện."""
from datetime import datetime
from uuid import uuid4

import streamlit as st

import ui_theme as ui
from monitoring import rubrics, task_reviews, tasks


def _date(value: str) -> str:
    return datetime.fromisoformat(value).astimezone().strftime("%d/%m/%Y %H:%M:%S")


def _show_score(score: dict) -> None:
    total = score["total"]
    if score["status"] == "partial":
        st.markdown("**Chấm một phần**")
    else:
        st.markdown("**Đã chấm đủ tiêu chí áp dụng**")
    columns = st.columns(3)
    for col, key, name in zip(columns, ("automatic", "manual", "total"),
                              ("Điểm tự động", "Điểm thủ công", "Điểm tổng"), strict=True):
        marks = score[key]
        value = "—"
        if marks["assessed"]:
            value = (f"{marks['earned']}/{marks['applicable']}" if marks["assessed"] == marks["applicable"]
                     else f"{marks['earned']} điểm")
        col.metric(name, value)
        col.caption(f"Đã đánh giá {marks['assessed']}/{marks['applicable']} điểm áp dụng")
    if excluded := total["maximum"] - total["applicable"]:
        st.caption(f"Loại {excluded}/{total['maximum']} điểm không áp dụng khỏi mẫu số. "
                   "Điểm giữ nguyên trọng số gốc.")
    st.caption(f"Khung {total['maximum']} điểm. Điểm tổng là tổng điểm đã chấm bằng code và điểm chuyên môn đã nhập.")
    for row in score["criteria"]:
        group = rubrics.GROUPS[row["group"]][0]
        status = {"missing": "Chưa chấm", "na": "Không áp dụng"}.get(row["status"])
        status = (f"{status} · {row['points']} điểm" if status else f"{row['score']}/{row['points']} điểm")
        with st.container(border=True):
            method = "Thủ công" if row["method"] == "manual" else "Tự động"
            st.markdown(f"**{group}** · {status} · {method}")
            st.write(row["label"])
            st.caption(row["evidence"])


def _review_form(run_id: str, attempt: dict, latest: dict | None, *, notice_key: str) -> None:
    if attempt["status"] in ("queued", "running"):
        st.caption("Có thể lưu đánh giá sau khi lần thực hiện kết thúc xử lý.")
        return

    attempt_id = attempt["attempt_id"]
    revision = latest["revision"] if latest else 0
    draft_key = f"review_draft_{attempt_id}"
    draft = st.session_state.setdefault(draft_key, {"revision": revision, "submission": uuid4().hex})
    if draft["revision"] != revision:
        st.warning("Một người chấm đã lưu bản mới trong lúc chỉnh sửa.")
        if st.button("Nạp đánh giá mới nhất", key=f"reload_review_{attempt_id}"):
            st.session_state.pop(draft_key, None)
            st.rerun()
        return

    values = latest or {}
    maximum = next(item["points"] for item in attempt["rubric"]["criteria"] if item["rule"] == "manual")
    enabled = rubrics.assessable(attempt)
    with st.form(f"review_form_{attempt_id}_{draft['submission']}"):
        ui.section("Chỉnh đánh giá" if latest else "Lưu đánh giá",
                   "Tên người chấm là tên tự khai. Mỗi lần thay đổi được lưu thành một bản riêng.")
        names, points = st.columns([2, 1])
        reviewer = names.text_input("Tên người chấm (tự khai)", value=values.get("reviewer", ""), max_chars=80)
        manual = points.number_input("Điểm chuyên môn", min_value=0, max_value=maximum, step=1,
                                     value=values.get("manual_score"), placeholder="Bỏ trống nếu chưa chấm",
                                     disabled=not enabled)
        evidence = st.text_area("Bằng chứng chuyên môn", value=values.get("manual_evidence", ""), max_chars=4000,
                                disabled=not enabled,
                                help="Nêu quan sát hoặc vị trí trong đầu ra để giải thích điểm chuyên môn.")
        comment = st.text_area("Nhận xét chung", value=values.get("comment", ""), max_chars=4000)
        fault = False
        fault_evidence = ""
        if task_reviews.can_confirm_fault(attempt):
            fault = st.checkbox("Xác nhận lần sửa này do lỗi của agent", value=bool(values.get("agent_fault_confirmed")),
                                help="Chỉ xác nhận khi có bằng chứng về lỗi của chính agent thực hiện task này.")
            fault_evidence = st.text_area("Bằng chứng lỗi dẫn đến lần sửa",
                                          value=values.get("agent_fault_evidence", ""), max_chars=4000)
        submitted = st.form_submit_button("Lưu đánh giá", type="primary", icon=":material/save:")
    if submitted:
        try:
            saved = task_reviews.save(run_id, attempt_id, expected_revision=draft["revision"],
                                      submission_id=draft["submission"], reviewer=reviewer, manual_score=manual,
                                      manual_evidence=evidence, comment=comment, agent_fault_confirmed=fault,
                                      agent_fault_evidence=fault_evidence)
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state.pop(draft_key, None)
            st.session_state[notice_key] = saved["revision"]
            st.rerun()


def _show_attempt_reviews(run_id: str, attempt: dict) -> None:
    rubric = attempt["rubric"]
    if not rubric:
        st.info("Lần thực hiện này chưa có bộ tiêu chí lưu khi giao việc. Các lần giao mới sẽ có bộ tiêu chí theo phiên bản.")
        return

    version = attempt["output_version"] or attempt["input_version"] or "Chưa xác định"
    st.caption(f"Bộ tiêu chí {rubric['version']} · Phiên bản phương án {version}")
    st.write(rubric["acceptance"])
    st.caption("Đánh giá chất lượng dựa trên đầu vào và đầu ra của lần đã chọn. "
               "Tốc độ, token và chi phí chạy model được theo dõi ở Công việc và Timeline.")
    attempt_id = attempt["attempt_id"]
    notice_key = f"review_notice_{attempt_id}"
    display_key = f"review_display_{attempt_id}"
    history = task_reviews.history(run_id, attempt_id)
    latest = history[0] if history else None
    shown = latest
    if revision := st.session_state.pop(notice_key, None):
        st.success(f"Đánh giá đã lưu · Bản {revision}")
        st.session_state[display_key] = revision
    if history:
        versions = {entry["revision"]: entry for entry in history}
        with st.expander(f"Lịch sử chỉnh sửa · {len(history)} bản"):
            revision = st.radio("Bản đánh giá để xem", list(versions),
                                format_func=lambda num: f"Bản {num} · {versions[num]['reviewer']} · "
                                                        f"{_date(versions[num]['created_at'])}",
                                key=display_key)
        shown = versions[revision]
        st.caption(f"Bản {shown['revision']} · {shown['reviewer']} (tự khai) · {_date(shown['created_at'])}")
        if shown["comment"]:
            st.markdown("**Nhận xét chung**")
            st.text(shown["comment"])
        if shown["agent_fault_confirmed"]:
            st.markdown("**Đã xác nhận lần sửa do lỗi agent**")
            st.text(shown["agent_fault_evidence"])
    else:
        st.caption("Điểm tự động xem trước. Chưa có bản đánh giá đã lưu.")
    _show_score(shown["score"] if shown else rubrics.evaluate(attempt))
    if shown is latest:
        _review_form(run_id, attempt, latest, notice_key=notice_key)
    else:
        st.caption("Đang xem bản lịch sử. Chọn bản mới nhất để chỉnh đánh giá.")


def show_task_reviews(run_id: str, task_id: str) -> None:
    attempts = {entry["attempt_id"]: entry for entry in tasks.attempts(task_id)}
    if not attempts:
        st.info("Chưa có lần thực hiện để đánh giá.")
        return
    attempt_id = st.selectbox(
        "Lần thực hiện cần đánh giá", list(attempts),
        format_func=lambda ident: f"Lần {attempts[ident]['attempt_no']} · "
                                  f"{attempts[ident]['output_version'] or attempts[ident]['input_version'] or 'Chưa có phiên bản phương án'}",
        key=f"review_attempt_{task_id}",
    )
    _show_attempt_reviews(run_id, attempts[attempt_id])
