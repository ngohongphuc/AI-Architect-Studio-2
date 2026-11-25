"""Bóc khối lượng sơ bộ và tính chi phí (mọi phép tính bằng Python, khớp công thức trong du_toan.xlsx)."""
from __future__ import annotations

from functools import lru_cache

from openpyxl import load_workbook

from config import PRICE_FILE
from tools.layout_algorithm import DOOR_SIZE

GRADE_CODE = {"tiết kiệm": "HT_TIET_KIEM", "trung bình": "HT_TRUNG_BINH", "khá": "HT_KHA", "cao cấp": "HT_CAO_CAP"}
WINDOW_H = 1.4


@lru_cache(maxsize=1)
def load_prices() -> dict:
    if not PRICE_FILE.exists():
        from tools.make_don_gia import build

        build()
    wb = load_workbook(PRICE_FILE, data_only=True)
    prices = {}
    for row in wb["Don_gia"].iter_rows(min_row=2, values_only=True):
        if row[0]:
            prices[row[0]] = {"ma": row[0], "hang_muc": row[1], "don_vi": row[2], "don_gia": row[3],
                              "ghi_chu": row[4], "nguon": row[5], "thoi_diem": row[6]}
    coef = {}
    for row in wb["He_so"].iter_rows(min_row=2, values_only=True):
        if row[0]:
            coef[row[0]] = {"ma": row[0], "dien_giai": row[1], "he_so": row[2]}
    return {"don_gia": prices, "he_so": coef}


def foundation_code(so_tang: int) -> str:
    return "HS_MONG_DON" if so_tang <= 2 else ("HS_MONG_BANG" if so_tang == 3 else "HS_MONG_COC")


def opening_quantities(layout: dict, program: dict) -> dict:
    """Diện tích cửa theo vật liệu (m²)."""
    q = {"CUA_NHOM": 0.0, "CUA_GO": 0.0, "CUA_CUON": 0.0, "so_cua_di": 0, "so_cua_so": 0}
    for fl in layout["floors"].values():
        for d in fl["doors"]:
            w = d["b"] - d["a"]
            h = DOOR_SIZE[d["loai"]][1]
            area = w * h
            if d["loai"] == "cuon":
                q["CUA_CUON"] += area
            elif d["loai"] == "di":
                q["CUA_GO"] += area
            else:
                q["CUA_NHOM"] += area
            q["so_cua_di"] += 1
        for wdw in fl["windows"]:
            q["CUA_NHOM"] += (wdw["b"] - wdw["a"]) * WINDOW_H
            q["so_cua_so"] += 1
    for k in ("CUA_NHOM", "CUA_GO", "CUA_CUON"):
        q[k] = round(q[k], 2)
    q["ma_cua_go"] = "CUA_GO_TN" if program.get("vat_lieu", {}).get("cua_phong") == "gỗ tự nhiên" else "CUA_GO_CN"
    return q


def compute_cost(area: dict, layout: dict, program: dict, budget: float) -> dict:
    P = load_prices()
    dg, hs = P["don_gia"], P["he_so"]
    so_tang = area["so_tang"]
    mong = foundation_code(so_tang)
    mai_code = "HS_MAI_TON" if program.get("loai_mai") == "tôn" else "HS_MAI_BTCT"

    # --- Bảng diện tích quy đổi (thứ tự khớp sheet Dien_tich) ---
    rows = [{"hang_muc": f"Móng ({hs[mong]['dien_giai'].split('(')[0].replace('Hệ số ', '').strip()})",
             "dien_tich": area["dien_tich_xay_dung"], "ma_he_so": mong}]
    for t in area["tang"]:
        rows.append({"hang_muc": f"Sàn tầng {t['tang']}", "dien_tich": t["dien_tich_san"], "ma_he_so": "HS_SAN"})
    rows.append({"hang_muc": "Ban công, lô gia", "dien_tich": area["tong_ban_cong"], "ma_he_so": "HS_BAN_CONG"})
    rows.append({"hang_muc": "Sân phơi, sân thượng", "dien_tich": area["tong_san_phoi"], "ma_he_so": "HS_SAN_PHOI"})
    rows.append({"hang_muc": "Sân trước, sân sau", "dien_tich": round(area["san_truoc"] + area["san_sau"], 2),
                 "ma_he_so": "HS_SAN_NGOAI"})
    rows.append({"hang_muc": f"Mái ({'tôn' if mai_code == 'HS_MAI_TON' else 'BTCT'})", "dien_tich": area["dien_tich_mai"],
                 "ma_he_so": mai_code})
    for r in rows:
        r["he_so"] = hs[r["ma_he_so"]]["he_so"]
        r["quy_doi"] = r["dien_tich"] * r["he_so"]
    dt_quy_doi = sum(r["quy_doi"] for r in rows)
    dt_san = area["tong_dien_tich_san"] + area["tong_ban_cong"]   # diện tích sàn hoàn thiện

    q = opening_quantities(layout, program)
    grade = program.get("cap_hoan_thien", "khá")
    items = [
        {"stt": 1, "ma": "THO", "kl": dt_quy_doi, "dien_giai": "DT quy đổi"},
        {"stt": 2, "ma": GRADE_CODE[grade], "kl": dt_san, "dien_giai": "DT sàn + ban công"},
        {"stt": 3, "ma": "DIEN_NUOC", "kl": dt_san, "dien_giai": "DT sàn + ban công"},
        {"stt": 4, "ma": "CUA_NHOM", "kl": q["CUA_NHOM"], "dien_giai": "Cửa đi nhôm kính + cửa sổ"},
        {"stt": 5, "ma": q["ma_cua_go"], "kl": q["CUA_GO"], "dien_giai": "Cửa đi các phòng"},
        {"stt": 6, "ma": "CUA_CUON", "kl": q["CUA_CUON"], "dien_giai": "Cửa cuốn mặt tiền"},
        {"stt": 7, "ma": "THIET_KE", "kl": dt_san, "dien_giai": "DT sàn + ban công"},
    ]
    for it in items:
        p = dg[it["ma"]]
        it.update(hang_muc=p["hang_muc"], don_vi=p["don_vi"], don_gia=p["don_gia"],
                  thanh_tien=it["kl"] * p["don_gia"])
    xay_dung = sum(it["thanh_tien"] for it in items)
    du_phong_pct = dg["DU_PHONG"]["don_gia"]
    du_phong = xay_dung * du_phong_pct
    total = xay_dung + du_phong
    over = (total - budget) / budget if budget else 0.0

    # --- Phương án tiết kiệm ---
    savings = []
    grades = list(GRADE_CODE)
    gi = grades.index(grade)
    if gi > 0:
        lower = grades[gi - 1]
        s = (dg[GRADE_CODE[grade]]["don_gia"] - dg[GRADE_CODE[lower]]["don_gia"]) * dt_san * (1 + du_phong_pct)
        savings.append({"phuong_an": f"Hạ gói hoàn thiện '{grade}' → '{lower}'", "tiet_kiem": s,
                        "cong_thuc": ("grade", GRADE_CODE[grade], GRADE_CODE[lower])})
    if q["ma_cua_go"] == "CUA_GO_TN":
        s = (dg["CUA_GO_TN"]["don_gia"] - dg["CUA_GO_CN"]["don_gia"]) * q["CUA_GO"] * (1 + du_phong_pct)
        savings.append({"phuong_an": "Đổi cửa gỗ tự nhiên → gỗ công nghiệp", "tiet_kiem": s,
                        "cong_thuc": ("door",)})
    top = area["tang"][-1]
    if so_tang >= 3:
        s = top["dien_tich_san"] * (dg["THO"]["don_gia"] + dg[GRADE_CODE[grade]]["don_gia"] +
                                    dg["DIEN_NUOC"]["don_gia"] + dg["THIET_KE"]["don_gia"]) * (1 + du_phong_pct)
        savings.append({"phuong_an": f"Bớt tầng {top['tang']} (gộp phòng thờ xuống tầng dưới)", "tiet_kiem": s,
                        "cong_thuc": ("floor",)})
    s = layout["lot"]["w"] * 1.0 * so_tang * (dg["THO"]["don_gia"] + dg[GRADE_CODE[grade]]["don_gia"]) * \
        (1 + du_phong_pct)
    savings.append({"phuong_an": "Giảm 1 m chiều sâu nhà (tăng sân sau)", "tiet_kiem": s, "cong_thuc": ("depth",)})

    return {
        "dien_tich": rows,
        "dt_quy_doi": round(dt_quy_doi, 2),
        "dt_san_hoan_thien": round(dt_san, 2),
        "hang_muc": items,
        "chi_phi_xay_dung": round(xay_dung),
        "du_phong_pct": du_phong_pct,
        "du_phong": round(du_phong),
        "tong_chi_phi": round(total),
        "ngan_sach": budget,
        "chenh_lech": round(total - budget),
        "vuot_pct": round(over, 4),
        "chi_phi_m2_san": round(total / dt_san) if dt_san else 0,
        "cap_hoan_thien": grade,
        "cua": q,
        "tiet_kiem": savings,
        "don_gia_dung": sorted({it["ma"] for it in items} | {"DU_PHONG"}),
    }
