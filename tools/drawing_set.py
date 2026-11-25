"""Lập và xuất bộ bản vẽ thiết kế sơ bộ: PDF đóng tập, DXF từng bản vẽ, PNG xem trước, ZIP."""
from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

from tools.design_option import option_label, option_stamp
from tools.drawing_elevation import draw_front_elevation, draw_long_section
from tools.drawing_plan import draw_floor_plan, draw_roof_plan, draw_site_plan
from tools.sheet import Sheet, render_dxf, render_mpl
from tools.title_block import draw_frame


def sheet_info(brief: dict, version: int) -> dict:
    ld = brief["lo_dat"]
    nam = brief["gia_dinh"].get("nam_sinh_chu_nha")
    return {
        "du_an": f"Nhà ở riêng lẻ {ld['rong']:g}×{ld['dai']:g} m – phong cách {brief.get('phong_cach', 'hiện đại')}",
        "chu_dau_tu": f"Hộ gia đình ({brief['gia_dinh']['so_nguoi']} người{', chủ hộ sinh năm ' + str(nam) if nam else ''})",
        "dia_diem": f"{ld['tinh']} – mặt tiền hướng {ld['huong']}",
        "ngay": date.today().strftime("%d/%m/%Y"),
        "phien_ban": f"v{version}",
    }


def build_sheets(brief: dict, program: dict, layout: dict, area: dict, version: int = 1) -> list[Sheet]:
    info = sheet_info(brief, version)
    if option_stamp(program):
        info.update(phien_ban=f"{program['phuong_an']} · v{program['option_version']}",
                    ma_phuong_an=option_stamp(program),
                    ghi_chu_ban_ve="Xem giả định và nội dung cần xác minh trong thuyết minh.")
    sheets: list[Sheet] = []

    s = Sheet("KT-01", "Mặt bằng tổng thể", info)
    draw_site_plan(s, layout, area, brief)
    sheets.append(s)
    n = layout["so_tang"]
    for k in range(1, n + 1):
        s = Sheet(f"KT-{k + 1:02d}", f"Mặt bằng tầng {k}", info)
        draw_floor_plan(s, layout, k, brief)
        sheets.append(s)
    s = Sheet(f"KT-{n + 2:02d}", "Mặt bằng mái", info)
    draw_roof_plan(s, layout, brief)
    sheets.append(s)
    s = Sheet(f"KT-{n + 3:02d}", "Mặt đứng chính", info)
    draw_front_elevation(s, layout, program)
    sheets.append(s)
    s = Sheet(f"KT-{n + 4:02d}", "Mặt cắt dọc A-A", info)
    draw_long_section(s, layout)
    sheets.append(s)
    for s in sheets:
        s.fit()
        draw_frame(s)
    return sheets


def export_drawings(brief: dict, program: dict, layout: dict, area: dict, out_dir: Path,
                    version: int = 1, dpi: int = 110) -> dict:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    out_dir = Path(out_dir)
    dxf_dir = out_dir / "dxf"
    png_dir = out_dir / "png"
    dxf_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)
    sheets = build_sheets(brief, program, layout, area, version)
    pdf_path = out_dir / "ban_ve.pdf"
    index = []
    with PdfPages(pdf_path) as pdf:
        meta = pdf.infodict()
        meta["Title"] = "Bộ bản vẽ thiết kế sơ bộ – AI Architect Studio"
        meta["Author"] = "AI Architect Studio"
        if option_stamp(program):
            meta["Subject"] = option_stamp(program)
        for s in sheets:
            fig = render_mpl(s)
            pdf.savefig(fig)
            png = png_dir / f"{s.code}.png"
            fig.savefig(png, dpi=dpi, metadata={"Description": option_stamp(program)})
            plt.close(fig)
            dxf = dxf_dir / f"{s.code}.dxf"
            render_dxf(s, dxf)
            index.append({"so_hieu": s.code, "ten": s.title, "ti_le": f"1:{s.scale}", "png": str(png),
                          "dxf": str(dxf)})
    zip_path = out_dir / "ban_ve_dxf.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for item in index:
            z.write(item["dxf"], arcname=Path(item["dxf"]).name)
    return {"pdf": str(pdf_path), "dxf_zip": str(zip_path), "dxf_dir": str(dxf_dir), "sheets": index,
            "version": version, "phuong_an": option_label(program)}
