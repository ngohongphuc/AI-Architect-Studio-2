"""Đọc bộ tham số quy chuẩn (data/rules.json) và các hàm tra cứu."""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from config import DATA_DIR, RULES_FILE


@lru_cache(maxsize=1)
def load_rules() -> dict:
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


def max_density(lot_area: float) -> float:
    """Mật độ xây dựng thuần tối đa (0–1) theo QCVN 01:2021 Bảng 2.8, nội suy tuyến tính."""
    table = load_rules()["mat_do_xay_dung"]["bang"]
    if lot_area <= table[0][0]:
        return table[0][1]
    if lot_area >= table[-1][0]:
        return table[-1][1]
    for (a1, d1), (a2, d2) in zip(table, table[1:]):
        if a1 <= lot_area <= a2:
            return round(d1 + (d2 - d1) * (lot_area - a1) / (a2 - a1), 4)
    return table[-1][1]


def min_room(loai: str, gara: str | None = None) -> dict:
    """Diện tích và cạnh tối thiểu theo loại phòng (rỗng nếu không quy định)."""
    table = load_rules()["dien_tich_toi_thieu"]
    if loai == "gara" and gara == "ô tô":
        return table["gara_o_to"]
    return table.get(loai, {})


MANIFEST = "can_cu_da_xac_minh.json"


@dataclass
class EvidenceReport:
    verified: dict[tuple[str, str], dict] = field(default_factory=dict)
    rejected: dict[tuple[str, str], str] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    input_gaps: list[str] = field(default_factory=list)

    def reason(self, criterion: str, threshold: str) -> str:
        if self.blockers:
            return " ".join(self.blockers)
        key = (criterion, threshold)
        if key in self.rejected:
            return self.rejected[key]
        if any(name == criterion for name, _ in (*self.verified, *self.rejected)):
            return "Ngưỡng trong hồ sơ xác minh khác ngưỡng phép kiểm đang chạy. Cần đối chiếu và cập nhật phép kiểm nếu cần."
        return "Hồ sơ xác minh chưa có bản ghi cho tiêu chí và ngưỡng này của đúng lô đất."

    def gaps(self, criterion: str, threshold: str) -> tuple[list[str], str]:
        source_gaps = [item for item in self.blockers if item not in self.input_gaps]
        if not self.blockers:
            source_gaps.append(f"Căn cứ áp dụng cho “{criterion}” với ngưỡng “{threshold}”. {self.reason(criterion, threshold)}")
        actions = []
        if self.input_gaps:
            actions.append("Xác nhận tỉnh/thành phố và nhập mã lô đất theo hồ sơ trong Thông tin có cấu trúc.")
        if source_gaps:
            actions.append(f"Đặt PDF có văn bản trích xuất được vào data/quy_chuan/ và đối chiếu bản ghi trong {MANIFEST}. "
                           "Bản ghi phải khớp lô đất, tiêu chí, ngưỡng, phạm vi, trang PDF và đoạn trích. "
                           "Nếu nguồn dùng ngưỡng hoặc cách đo khác, cần cập nhật và kiểm chứng phép tính tương ứng.")
        return [*self.input_gaps, *source_gaps], " ".join(actions)


def inspect_evidence(lot: dict, *, assumed_location: bool = False) -> EvidenceReport:
    """Đối chiếu hồ sơ do người có chuyên môn xác nhận và ghi lý do khi thiếu căn cứ."""
    from pathlib import Path

    from pydantic import TypeAdapter, ValidationError
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    from state import VerifiedRule

    result = EvidenceReport()
    parcel = (lot.get("ma_lo_dat") or "").strip()
    province = (lot.get("tinh") or "").strip()
    if not parcel:
        result.input_gaps.append("Brief thiếu mã lô đất.")
    if not province or assumed_location:
        result.input_gaps.append("Brief thiếu tỉnh/thành phố đã xác nhận.")
    result.blockers.extend(result.input_gaps)
    folder = DATA_DIR / "quy_chuan"
    try:
        manifest = (folder / MANIFEST).read_text(encoding="utf-8-sig")
        rules = TypeAdapter(list[VerifiedRule]).validate_json(manifest)
    except FileNotFoundError:
        result.blockers.append(f"Thiếu hồ sơ xác minh {MANIFEST}.")
        return result
    except OSError:
        result.blockers.append(f"Không đọc được hồ sơ xác minh {MANIFEST}.")
        return result
    except (UnicodeError, ValidationError):
        result.blockers.append(f"Hồ sơ xác minh {MANIFEST} sai định dạng UTF-8/JSON hoặc thiếu trường bắt buộc.")
        return result
    if result.blockers:
        return result
    def normalized(value: str) -> str:
        return unicodedata.normalize("NFC", " ".join(value.split())).casefold()

    matching = [rule for rule in rules if (normalized(rule.tinh), normalized(rule.ma_lo_dat))
                == (normalized(province), normalized(parcel))]
    if not matching:
        result.blockers.append("Hồ sơ xác minh chưa có bản ghi khớp tỉnh/thành phố và mã lô đất.")
        return result
    for rule in matching:
        key = (rule.muc, rule.nguong)
        name = Path(rule.tai_lieu)
        if name.name != rule.tai_lieu or name.suffix.lower() != ".pdf" or any(c in rule.tai_lieu for c in "/\\"):
            result.rejected[key] = "Trường tai_lieu phải là tên tệp PDF trong data/quy_chuan/."
            continue
        try:
            path = folder / name
            if not path.resolve().is_relative_to(folder.resolve()):
                result.rejected[key] = "Tệp PDF phải nằm trong thư mục data/quy_chuan/."
                continue
            with path.open("rb") as document:
                text = PdfReader(document).pages[rule.trang - 1].extract_text()
        except FileNotFoundError:
            result.rejected[key] = f"Thiếu tệp PDF {name.name} được khai báo trong hồ sơ xác minh."
            continue
        except IndexError:
            result.rejected[key] = f"PDF {name.name} không có trang {rule.trang}."
            continue
        except (OSError, PdfReadError, ValueError):
            result.rejected[key] = f"Không đọc được trang {rule.trang} của PDF {name.name}."
            continue
        if not (text or "").strip():
            result.rejected[key] = f"Trang {rule.trang} của PDF {name.name} không có văn bản trích xuất được."
            continue
        excerpt = " ".join(rule.trich.split())
        if not excerpt or excerpt not in " ".join(text.split()):
            result.rejected[key] = f"Trích dẫn không khớp văn bản ở trang {rule.trang} của PDF {name.name}."
            continue
        result.verified[key] = {
            "nguon": rule.nguon, "pham_vi": rule.pham_vi,
            "trich_dan": {"nguon": name.name, "muc": f"Trang {rule.trang}", "trich": rule.trich}}
    return result


def verified_evidence(lot: dict) -> dict[tuple[str, str], dict]:
    return inspect_evidence(lot).verified
