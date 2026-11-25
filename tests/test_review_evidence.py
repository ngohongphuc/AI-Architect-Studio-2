import json
from types import SimpleNamespace

import pypdf

from tools import rag, rules
from tools.review_display import MISSING, VIOLATION, regulatory_label, review_rows


def test_missing_manifest_and_parcel_are_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(rules, "DATA_DIR", tmp_path)
    report = rules.inspect_evidence({"tinh": "Hà Nội"})
    reason = report.reason("Số tầng", "Ngưỡng của phép kiểm")
    assert "thiếu mã lô đất" in reason
    assert rules.MANIFEST in reason
    assert not report.verified


def test_each_rejected_source_explains_the_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(rules, "DATA_DIR", tmp_path)
    folder = tmp_path / "quy_chuan"
    folder.mkdir()
    base = {"tinh": "Hà Nội", "ma_lo_dat": "a1", "nguon": "Nguồn thử",
            "pham_vi": "Phạm vi thử", "trich": "Doan van ban thu nghiem", "nguong": "Ngưỡng thử"}
    records = [
        base | {"muc": "A", "tai_lieu": "missing.pdf", "trang": 1},
        base | {"muc": "B", "tai_lieu": "mock.pdf", "trang": 3},
        base | {"muc": "C", "tai_lieu": "mock.pdf", "trang": 1},
        base | {"muc": "D", "tai_lieu": "mock.pdf", "trang": 2},
    ]
    (folder / rules.MANIFEST).write_text(json.dumps(records), encoding="utf-8")
    (folder / "mock.pdf").touch()
    monkeypatch.setattr(pypdf, "PdfReader", lambda _: SimpleNamespace(pages=[
        SimpleNamespace(extract_text=lambda: "Một đoạn khác"),
        SimpleNamespace(extract_text=lambda: base["trich"]),
    ]))
    report = rules.inspect_evidence({"tinh": "Hà Nội", "ma_lo_dat": "A1"})
    assert ("D", base["nguong"]) in report.verified
    assert "Thiếu tệp PDF" in report.reason("A", base["nguong"])
    assert "không có trang 3" in report.reason("B", base["nguong"])
    assert "không khớp văn bản" in report.reason("C", base["nguong"])
    assert "khác ngưỡng" in report.reason("D", "Khác")


def test_display_distinguishes_verified_violation_missing_and_technical():
    rows = review_rows({"kiem_tra": [
        {"muc": "Mật độ", "loai": "Quy chuẩn", "dat": None, "ket_qua_tham_chieu": False,
         "nguon": "Ngưỡng nội bộ", "ly_do": "Thiếu hồ sơ xác minh."},
        {"muc": "Số tầng", "loai": "Quy chuẩn", "dat": False, "da_xac_minh": True,
         "nguon": "Hồ sơ kiểm thử", "trich_dan": {"nguon": "lo.pdf", "muc": "Trang 3"}},
        {"muc": "Chồng lấn", "loai": "Kỹ thuật", "dat": False},
    ]})
    assert [row["status"] for row in rows] == [MISSING, VIOLATION, "Không đạt kỹ thuật"]
    assert rows[0]["reason"] == "Thiếu hồ sơ xác minh."
    assert rows[0]["source"] == "Tham chiếu: Ngưỡng nội bộ"
    assert rows[1]["source"] == "Hồ sơ kiểm thử · lo.pdf · Trang 3"
    assert regulatory_label(rows) == VIOLATION


def test_reviewer_rag_notices_a_replaced_file(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "SOURCES", [tmp_path])
    source = tmp_path / "qcvn_01_thu.txt"
    source.write_text("alpha bocuc", encoding="utf-8")
    assert rag.cite("alpha", source_prefix="qcvn_01")
    source.write_text("beta bocuc thu nghiem", encoding="utf-8")
    assert not rag.cite("alpha", source_prefix="qcvn_01")
    assert rag.cite("beta", source_prefix="qcvn_01")
