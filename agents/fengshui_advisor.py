"""Tư vấn Bát trạch và cách bố trí, độc lập với kiểm định kỹ thuật."""
from agents.base import agent_node
from agents.reviewer import _adjacent, _overlap
from tools import fengshui
from tools.layout_algorithm import room_at

def fengshui_checks(state: dict) -> tuple[dict, list, list, list]:
    brief, layout = state["brief"], state["layout"]
    gd, ld = brief["gia_dinh"], brief["lo_dat"]
    info = fengshui.analyze(gd.get("nam_sinh_chu_nha"), gd.get("gioi_tinh_chu_nha", "nam"), ld["huong"])
    checks, issues, warns = [], [], []
    if info.get("co_du_lieu") and not info["hop_huong"]:
        warns.append({"loai": "Phong thủy", "muc": "Hướng nhà",
                      "noi_dung": f"Hướng {ld['huong']} là {info['sao_huong_nha']} với cung {info['cung_menh']}",
                      "de_xuat": f"Xoay cửa chính / bàn thờ về {', '.join(info['huong_tot'])}"})
    floors = layout["floors"]
    n = layout["so_tang"]
    # WC trên phòng thờ
    wc_over = []
    for k in range(1, n):
        for tho in (r for r in floors[str(k)]["rooms"] if r["loai"] == "tho"):
            for wc in (r for r in floors[str(k + 1)]["rooms"] if r["loai"] == "wc"):
                if _overlap(tho, wc) > 0.05:
                    wc_over.append((k, k + 1))
    checks.append({"noi_dung": "Không đặt WC phía trên phòng thờ", "dat": not wc_over})
    for k, k2 in wc_over:
        issues.append({"loai": "Phong thủy", "ma": "WC_TREN_THO", "muc": "Vị trí WC",
                       "noi_dung": f"WC tầng {k2} nằm trên phòng thờ tầng {k}",
                       "de_xuat": f"Dời WC tầng {k2} ra phía sau", "du_lieu": {"tang_wc": k2}})
    # Bếp kề WC
    bep_wc = []
    for k, fl in floors.items():
        for bep in (r for r in fl["rooms"] if r["loai"] == "bep"):
            for wc in (r for r in fl["rooms"] if r["loai"] == "wc"):
                if _adjacent(bep, wc):
                    bep_wc.append(int(k))
    checks.append({"noi_dung": "Bếp không kề sát / đối diện WC", "dat": not bep_wc})
    for k in bep_wc:
        issues.append({"loai": "Phong thủy", "ma": "BEP_KE_WC", "muc": "Vị trí bếp",
                       "noi_dung": f"Bếp tầng {k} chung tường với WC", "de_xuat": "Đổi vị trí WC",
                       "du_lieu": {"tang": k}})
    # Phòng thờ ở tầng trên cùng
    tho_floor = [int(k) for k, fl in floors.items() if any(r["loai"] == "tho" for r in fl["rooms"])]
    if tho_floor:
        ok = max(tho_floor) == n
        checks.append({"noi_dung": "Phòng thờ đặt ở tầng trên cùng", "dat": ok})
        if not ok:
            warns.append({"loai": "Phong thủy", "muc": "Phòng thờ",
                          "noi_dung": "Phòng thờ không ở tầng trên cùng", "de_xuat": "Ưu tiên đặt phòng thờ tầng trên cùng"})
    # WC ở tâm nhà
    b = layout["building"]
    cx, cy = b["w"] / 2, b["y"] + b["l"] / 2
    center_wc = [k for k, fl in floors.items() if (r := room_at(fl["rooms"], cx, cy)) and r["loai"] == "wc"]
    checks.append({"noi_dung": "WC không nằm ở tâm nhà", "dat": not center_wc})
    if center_wc:
        warns.append({"loai": "Phong thủy", "muc": "WC giữa nhà",
                      "noi_dung": f"WC tầng {', '.join(center_wc)} nằm ở tâm nhà",
                      "de_xuat": "Có thể dời WC lệch khỏi tâm nhà ở giai đoạn thiết kế kỹ thuật"})
    return info, checks, issues, warns


@agent_node("fengshui_advisor")
def run(state: dict) -> dict:
    info, checks, issues, warnings = fengshui_checks(state)
    result = {"thong_tin": info, "bo_tri": checks, "goi_y": issues + warnings}
    return {"fengshui": result, "route": "reviewer", "_to": "reviewer",
            "_summary": f"{len(checks)} mục tư vấn, {len(result['goi_y'])} gợi ý",
            "_output": result}
