"""Nạp pycel an toàn trên Python 3.12+.

pycel 1.0b30 (bản mới nhất) vẫn gọi ``ast.Str(...)`` khi biên dịch công thức Excel,
nhưng Python 3.14 đã gỡ ``ast.Str``. Khi thiếu, mọi lần đọc công thức XLSX báo
``FormulaParserError`` và bước Kiểm tra hồ sơ cuối luôn kết luận dự toán sai lệch.
pycel chỉ dùng ``ast.Str`` để tạo hằng chuỗi, nên thay bằng ``ast.Constant`` là tương đương.
"""
import ast

if not hasattr(ast, "Str"):
    def _str(s=None, *args, **kwargs):
        return ast.Constant(s, *args, **kwargs)

    ast.Str = _str

from pycel import ExcelCompiler  # noqa: E402

__all__ = ["ExcelCompiler"]
