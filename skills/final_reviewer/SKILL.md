---
name: doi-chieu-ho-so-cuoi
agent: final_reviewer
version: 0.1.0
status: draft-not-wired
description: Đối chiếu số tầng, số phòng, diện tích, chi phí và mã phiên bản giữa chương trình, bảng diện tích và bốn tệp PDF, DXF, DOCX, XLSX trước khi phát hành.
stages: [final_reviewer]
inputs: [brief, program, layout, area_table, cost, draft_files, revision_id, remaining_issues, repair_limit_reached]
outputs: [final_review, outcome, remaining_issues, repair_target]
tools: [pypdf (PdfReader), ezdxf, python-docx (Document), openpyxl, tools/pycel_compat.py (ExcelCompiler), tools/cost_calc.py, tools/layout_algorithm.py (build_area_table), tools/design_option.py (option_stamp)]
llm: none
---

# Kiểm tra hồ sơ cuối

## Vai trò
Người "soát lỗi chính tả" của cả bộ hồ sơ: đảm bảo bốn tệp nói cùng một con số và cùng một phiên bản trước khi đến tay chủ nhà.

## Khi nào kích hoạt
Sau khi Chủ nhiệm tổng hợp hồ sơ nháp, trước bước Xuất hồ sơ.

## Kỹ năng

### 1. Đối chiếu dữ liệu nguồn
- Số phòng theo loại: chương trình ↔ brief ↔ bản vẽ (`THIEU_PHONG`, `THUA_PHONG`, `SAI_SO_PHONG`).
- Số tầng: brief ↔ chương trình ↔ bảng diện tích (`SAI_SO_TANG`, `MAT_BANG_SAI_TANG`).
- Bảng diện tích ↔ tính lại từ hình học (`SAI_BANG_DIEN_TICH`).

### 2. Đọc và đối chiếu tệp
| Tệp | Cách đọc | Đối chiếu |
|---|---|---|
| PDF | pypdf | Số tờ, nhãn phòng, diện tích, dấu phiên bản |
| DXF | ezdxf | Số tờ, số tầng, nhãn |
| DOCX | python-docx | Số tầng, danh mục phòng, diện tích, chi phí |
| XLSX | openpyxl + pycel | Khối lượng, ngân sách, **giá trị công thức** khớp chi phí tính lại |

### 3. Phân loại sai lệch theo đầu mối
- Sai lệch gán `target`: `concept_architect`, `architect`, `drafter`, `cost_estimator`, `pm_report`. Sửa từ đầu mối sớm nhất trong chuỗi phụ thuộc.

### 4. Kết luận
- Nhất quán → chuyển Xuất hồ sơ (`outcome = done`, hoặc `not_passed` nếu đã hết vòng mà còn vấn đề).
- Sai lệch → trả Chủ nhiệm kèm `repair_target`.
- Còn lỗi kỹ thuật hoặc vi phạm chưa xử lý → giữ hồ sơ, `not_passed`, sang đề xuất điều chỉnh.

## Quy trình
1. Kiểm tra lỗi chặn còn tồn đọng.
2. Đối chiếu dữ liệu nguồn.
3. Đọc bốn tệp; tệp không đọc được tính là sai lệch, kèm tên lỗi.
4. Kết luận và chuyển tiếp.

## Prompt hệ thống
Không dùng model. Kết luận chỉ dựa trên phép so khớp.

## Đầu ra và bàn giao
- `final_review`: `dat`, `loi[]` (mỗi lỗi có `ma`, `muc`, `noi_dung`, `target`).
- Chuyển tới `publish`, `coordinate_repair` hoặc `propose_adjustment`.

## Tiêu chí nghiệm thu
- Có kết quả đối chiếu và danh sách sai lệch.
- Báo đúng chênh lệch số tầng giữa công năng và bảng diện tích.
- Chuyển xuất hồ sơ hoặc điều phối sửa đúng theo danh sách sai lệch.

## Ranh giới
- "Nhất quán" là nhất quán giữa các tệp, không phải xác minh pháp lý.
- Không tự sửa tệp.

## Lỗi và leo thang
- Thư viện đọc tệp lỗi (ví dụ pycel trên Python 3.14 trước bản vá `tools/pycel_compat.py`) sẽ bị ghi thành sai lệch `HO_SO_KHONG_KHOP`. Khi lỗi lặp lại qua nhiều vòng với cùng tệp không đổi, kiểm tra môi trường trước khi sửa thiết kế.

## Ví dụ
DOCX ghi 4 tầng nhưng bảng diện tích 5 tầng → `HO_SO_KHONG_KHOP` mục Thuyết minh, `target = pm_report` → Chủ nhiệm tổng hợp lại.
