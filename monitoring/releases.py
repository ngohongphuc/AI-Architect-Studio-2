"""Lưu và tìm các bộ hồ sơ đã xuất của đúng lượt và phiên bản."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

from tools.design_option import option_stamp, selected_assumptions

ARTIFACTS = {
    "ban_ve_pdf": "ban_ve.pdf",
    "ban_ve_dxf_zip": "ban_ve_dxf.zip",
    "thuyet_minh_docx": "thuyet_minh.docx",
    "du_toan_xlsx": "du_toan.xlsx",
}

VIEW_KEYS = ("run_id", "program", "brief", "user_request", "concept", "area_table", "review", "cost",
             "fengshui", "fengshui_enabled", "remaining_issues", "outcome", "final_files", "revision_id",
             "brief_assessment", "drawings", "repair_limit_reached", "iteration", "max_iterations")


@dataclass
class Release:
    path: Path
    state: dict
    modified: float


def archive_release(state: dict, path: Path, *, copy_previews: bool = False) -> None:
    snapshot = {key: state[key] for key in VIEW_KEYS if key in state}
    snapshot["assumptions"] = selected_assumptions(state)
    drawings = dict(snapshot.get("drawings") or {})
    if copy_previews and drawings.get("sheets"):
        folder = path / "previews"
        folder.mkdir(exist_ok=True)
        sheets = []
        for sheet in drawings["sheets"]:
            source = Path(sheet["png"])
            target = folder / source.name
            if source.is_file():
                shutil.copyfile(source, target)
            sheets.append({**sheet, "png": str(target)})
        drawings["sheets"] = sheets
        snapshot["drawings"] = drawings
    temporary = path / "state.json.tmp"
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(path / "state.json")


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def release_path(state: dict, root: Path) -> Path | None:
    files = state.get("final_files") or {}
    if not isinstance(files, dict):
        return None
    try:
        parents = {Path(files[key]).resolve().parent for key in ARTIFACTS if files.get(key)}
    except (OSError, TypeError, ValueError):
        return None
    if not parents:
        return None
    if len(parents) != 1:
        return None
    path = parents.pop()
    return path if path.parent == (root / "releases").resolve() else None


def _valid_state(state: dict, run_id: str) -> bool:
    if not state.get("final_files") or state.get("run_id") != run_id:
        return False
    program = state.get("program") or {}
    stamp = option_stamp(program)
    return not stamp or state.get("revision_id") == program.get("revision_id")


def list_releases(root: Path, run_id: str, current: dict, history=None) -> tuple[list[Release], int]:
    """Đọc bản lưu riêng, rồi khôi phục bản cũ từ snapshot hoặc checkpoint nếu còn."""
    root = root.resolve()
    folder = root / "releases"
    paths = {path.resolve() for path in folder.iterdir() if path.is_dir() and not path.is_symlink()} if folder.is_dir() else set()
    found: dict[Path, Release] = {}

    def collect(state: dict) -> None:
        path = release_path(state, root)
        if path not in paths or path in found or not _valid_state(state, run_id):
            return
        manifest = path / "state.json"
        modified = (manifest if manifest.is_file() else path).stat().st_mtime
        found[path] = Release(path, state, modified)

    for path in paths:
        saved = read_json(path / "state.json")
        if release_path(saved, root) == path:
            collect(saved)
    collect(current)
    if paths - found.keys():
        collect(read_json(root / "state.json"))
    if history is not None and paths - found.keys():
        for state in history():
            collect(state)
            if not paths - found.keys():
                break
    return sorted(found.values(), key=lambda item: (item.modified, item.path.name), reverse=True), len(paths - found.keys())


def read_artifact(path: Path, kind: str, stamp: str) -> tuple[bytes | None, str]:
    try:
        data = path.read_bytes()
        if stamp and not _matches_stamp(data, kind, stamp):
            return None, "Tệp thuộc phiên bản khác."
    except FileNotFoundError:
        return None, "Thiếu tệp."
    except Exception:  # Các định dạng có bộ đọc và kiểu lỗi khác nhau.
        return None, "Không đọc được tệp."
    return data, ""


def _matches_stamp(data: bytes, kind: str, stamp: str) -> bool:
    stream = BytesIO(data)
    if kind == "ban_ve_pdf":
        from pypdf import PdfReader

        return (PdfReader(stream).metadata or {}).get("/Subject") == stamp
    if kind == "thuyet_minh_docx":
        from docx import Document

        return Document(stream).core_properties.identifier == stamp
    if kind == "du_toan_xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(stream, read_only=True)
        try:
            return workbook.properties.identifier == stamp
        finally:
            workbook.close()
    if kind == "ban_ve_dxf_zip":
        import ezdxf

        with ZipFile(stream) as archive:
            names = archive.namelist()
            if not names or any(not name.lower().endswith(".dxf") for name in names):
                return False
            for name in names:
                doc = ezdxf.read(StringIO(archive.read(name).decode("utf-8-sig"), newline=None))
                if doc.ezdxf_metadata().get("AI_ARCHITECT_OPTION") != stamp:
                    return False
            return True
    return False
