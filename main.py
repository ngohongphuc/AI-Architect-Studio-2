"""Chạy AI Architect Studio từ dòng lệnh.

    python main.py "Lô đất 5×20m, hướng Đông Nam, Hà Nội, 3 phòng ngủ, phòng thờ, gara xe máy, ngân sách 2,5 tỷ"
    python main.py --sample
"""
from __future__ import annotations

import argparse
import logging
import time

from config import MAX_ITERATIONS
from graph import outcome_for, run_design
from llm import mode_label
from tools.review_display import PRELIMINARY, preliminary_ready, quality_status

SAMPLE = ("Lô đất 5×20m, mặt tiền hướng Đông Nam, ở Hà Nội. Gia đình 4 người (vợ chồng sinh năm 1990 và 1992, "
          "2 con nhỏ). Cần 3 phòng ngủ, 1 phòng thờ, có gara xe máy. Ngân sách 2,5 tỷ. Phong cách hiện đại, "
          "nhiều ánh sáng tự nhiên.")


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Architect Studio – multi-agent thiết kế nhà ở")
    ap.add_argument("request", nargs="?", help="Yêu cầu thiết kế bằng tiếng Việt")
    ap.add_argument("--sample", action="store_true", help="Dùng yêu cầu mẫu trong kế hoạch")
    ap.add_argument("--max-iterations", type=int, default=MAX_ITERATIONS)
    ap.add_argument("--no-fengshui", action="store_true", help="Tắt tư vấn phong thủy")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    request = SAMPLE if args.sample or not args.request else args.request
    print(f"▶ {mode_label()}\n▶ Yêu cầu: {request}\n")
    t0 = time.time()

    def on_update(update: dict):
        for node, val in update.items():
            for line in (val or {}).get("log", []) if isinstance(val, dict) else []:
                print("  " + line)

    final = run_design(request, max_iterations=args.max_iterations, on_update=on_update,
                       fengshui_enabled=not args.no_fengshui)
    outcome = outcome_for(final)
    status = {"done": "Đã tạo hồ sơ sơ bộ", "not_passed": "Chưa đạt",
              "needs_input": "Cần bổ sung yêu cầu"}
    headline = PRELIMINARY if preliminary_ready(final) else status.get(outcome, outcome)
    if final.get("repair_limit_reached"):
        headline += " · đã hết số vòng sửa tự động"
    print(f"\n{headline} sau {time.time() - t0:.1f} s – {final.get('iteration', 0)}/{final['max_iterations']} vòng sửa")
    quality = quality_status(final)
    print(f"  Kỹ thuật · {quality['technical']} | Xác minh quy chuẩn · {quality['regulatory']}")
    assessment = final.get("brief_assessment") or {}
    for note in [*assessment.get("conflicts", []), *assessment.get("questions", []),
                 *assessment.get("needs_confirmation", [])]:
        print("  - " + note)
    for k, v in (final.get("final_files") or {}).items():
        print(f"  {k:18s} {v}")
    issues = final.get("remaining_issues") or []
    if issues:
        print("⚠ Lỗi còn tồn tại:", "; ".join(i["noi_dung"] for i in issues))
    return {"done": 0, "not_passed": 1, "needs_input": 2}.get(outcome, 1)


if __name__ == "__main__":
    raise SystemExit(main())
