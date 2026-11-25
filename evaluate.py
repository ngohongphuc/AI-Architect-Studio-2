"""Đánh giá hệ thống trên bộ yêu cầu thử nghiệm (mục 9 kế hoạch).

    python evaluate.py                 # có vòng lặp phản hồi (tối đa 3 vòng)
    python evaluate.py --ablation      # thêm cấu hình KHÔNG có vòng lặp phản hồi để so sánh
Kết quả: outputs/evaluation/ket_qua_danh_gia.md + .csv
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import time
from pathlib import Path

from agents.final_reviewer import audit

from config import BUDGET_TOLERANCE, OUTPUT_DIR, ROOT
from graph import run_design
from monitoring.tracker import estimate_cost_usd, tracker

TESTS = ROOT / "tests" / "test_requests.json"


def consistency(final: dict) -> float:
    """Đối chiếu bộ tệp đã bàn giao bằng cùng phép kiểm tra như trong luồng."""
    files = final.get("final_files")
    return float(bool(files) and audit({**final, "draft_files": files}).dat)


def requirement_match(final: dict, expect: dict) -> float:
    cnt = final["area_table"]["so_phong"]
    oks = [cnt.get("ngu", 0) >= expect["phong_ngu"], cnt.get("tho", 0) >= expect["phong_tho"],
           (cnt.get("gara", 0) >= 1) == bool(expect["gara"])]
    if expect.get("phong_lam_viec"):
        oks.append(cnt.get("lam_viec", 0) >= 1)
    if expect["gara"]:
        oks.append(any(r["loai"] in ("gara", "san") and (expect["gara"] in r["ten"] or
                                                         (expect["gara"] == "ô tô" and "đỗ xe ô tô" in r["ten"]))
                       for r in final["layout"]["floors"]["1"]["rooms"]))
    return sum(oks) / len(oks)


def evaluate(max_iterations: int, label: str) -> list[dict]:
    cases = json.loads(TESTS.read_text(encoding="utf-8"))
    rows = []
    for c in cases:
        t0 = time.time()
        try:
            final = run_design(c["request"], max_iterations=max_iterations, persist=False)
            files = final.get("final_files") or {}
            ok = bool(files) and all(Path(p).is_file() for p in files.values())
            if not final.get("cost"):
                assessment = final.get("brief_assessment") or {}
                notes = (assessment.get("questions", []) + assessment.get("conflicts", [])
                         + [issue["noi_dung"] for issue in final.get("remaining_issues") or []])
                rows.append({"cau_hinh": label, "id": c["id"], "hoan_thanh": False,
                             "vong_sua": final["iteration"], "loi_con_lai": " | ".join(notes)})
                continue
            cost = final["cost"]
            tokens = tracker.tokens(final["run_id"])
            rows.append({
                "cau_hinh": label, "id": c["id"], "hoan_thanh": ok,
                "dat_quy_chuan": bool(final["review"]["dat"]),
                "vong_sua": final.get("iteration", 0),
                "khop_yeu_cau": round(requirement_match(final, c["expect"]), 3),
                "nhat_quan": round(consistency(final), 3) if ok else 0.0,
                "so_tang": final["area_table"]["so_tang"],
                "mat_do": final["area_table"]["mat_do_xay_dung"],
                "chi_phi_ty": round(cost["tong_chi_phi"] / 1e9, 3),
                "ngan_sach_ty": round(cost["ngan_sach"] / 1e9, 3),
                "lech_ngan_sach_pct": round(cost["vuot_pct"] * 100, 1),
                "trong_nguong_ngan_sach": cost["vuot_pct"] <= BUDGET_TOLERANCE,
                "chi_phi_m2": cost["chi_phi_m2_san"],
                "thoi_gian_s": round(time.time() - t0, 1),
                "token": tokens, "chi_phi_api_usd": estimate_cost_usd(tokens),
                "loi_con_lai": "; ".join(i["muc"] for i in final.get("remaining_issues") or []),
            })
        except Exception as e:  # noqa: BLE001
            rows.append({"cau_hinh": label, "id": c["id"], "hoan_thanh": False, "loi_con_lai": f"Exception: {e}",
                         "thoi_gian_s": round(time.time() - t0, 1)})
        print(f"[{label}] {c['id']}: {rows[-1].get('hoan_thanh')} – vòng {rows[-1].get('vong_sua')} – "
              f"{rows[-1].get('chi_phi_ty')} tỷ / {rows[-1].get('ngan_sach_ty')} tỷ – {rows[-1].get('thoi_gian_s')} s")
    return rows


def summarize(rows: list[dict]) -> dict:
    done = [r for r in rows if r.get("hoan_thanh")]
    n = len(rows)

    def avg(key):
        vals = [r[key] for r in done if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0

    return {
        "Số yêu cầu": n,
        "Tỉ lệ hoàn thành (đủ 3 sản phẩm)": f"{len(done) / n * 100:.0f}%",
        "Tỉ lệ đạt quy chuẩn": f"{sum(r['dat_quy_chuan'] for r in done) / n * 100:.0f}%",
        "Tỉ lệ trong ngưỡng ngân sách (≤ +10%)": f"{sum(r['trong_nguong_ngan_sach'] for r in done) / n * 100:.0f}%",
        "Số vòng sửa trung bình": f"{avg('vong_sua'):.2f}",
        "Độ khớp yêu cầu": f"{avg('khop_yeu_cau') * 100:.0f}%",
        "Tính nhất quán 3 sản phẩm": f"{avg('nhat_quan') * 100:.0f}%",
        "Sai lệch chi phí TB so với ngân sách": f"{avg('lech_ngan_sach_pct'):+.1f}%",
        "Chi phí bình quân / m² sàn": f"{avg('chi_phi_m2') / 1e6:.2f} triệu đ",
        "Thời gian xử lý TB": f"{avg('thoi_gian_s'):.1f} s",
        "Token TB / lần thiết kế": f"{avg('token'):.0f}",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ablation", action="store_true", help="So sánh với cấu hình không có vòng lặp phản hồi")
    args = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)
    out = OUTPUT_DIR / "evaluation"
    out.mkdir(parents=True, exist_ok=True)
    configs = [(3, "Có vòng lặp (≤3)")] + ([(0, "Không vòng lặp")] if args.ablation else [])
    all_rows, summaries = [], {}
    for it, label in configs:
        rows = evaluate(it, label)
        all_rows += rows
        summaries[label] = summarize(rows)
    keys = sorted({k for r in all_rows for k in r}, key=lambda k: list(all_rows[0]).index(k)
                  if k in all_rows[0] else 99)
    with open(out / "ket_qua_danh_gia.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(all_rows)
    md = ["# Kết quả đánh giá AI Architect Studio", ""]
    labels = list(summaries)
    md.append("| Tiêu chí | " + " | ".join(labels) + " |")
    md.append("|---|" + "---|" * len(labels))
    for k in summaries[labels[0]]:
        md.append(f"| {k} | " + " | ".join(str(summaries[lb][k]) for lb in labels) + " |")
    md += ["", "## Chi tiết từng yêu cầu", "",
           "| Cấu hình | ID | Hoàn thành | Đạt QC | Vòng sửa | Khớp YC | Nhất quán | Tầng | Mật độ | Chi phí (tỷ) | Ngân sách (tỷ) | Lệch | Thời gian (s) | Lỗi còn lại |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in all_rows:
        md.append(f"| {r['cau_hinh']} | {r['id']} | {'✅' if r.get('hoan_thanh') else '❌'} | "
                  f"{'✅' if r.get('dat_quy_chuan') else '❌'} | {r.get('vong_sua', '')} | "
                  f"{r.get('khop_yeu_cau', 0) * 100:.0f}% | {r.get('nhat_quan', 0) * 100:.0f}% | {r.get('so_tang', '')} | "
                  f"{r.get('mat_do', 0) * 100:.0f}% | {r.get('chi_phi_ty', '')} | {r.get('ngan_sach_ty', '')} | "
                  f"{r.get('lech_ngan_sach_pct', '')}% | {r.get('thoi_gian_s', '')} | {r.get('loi_con_lai', '')} |")
    (out / "ket_qua_danh_gia.md").write_text("\n".join(md), encoding="utf-8")
    print("\n" + "\n".join(md[:len(summaries[labels[0]]) + 4]))
    print(f"\nĐã lưu {out}")


if __name__ == "__main__":
    main()
