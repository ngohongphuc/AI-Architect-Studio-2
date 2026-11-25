---
name: trien-khai-ban-ve
agent: drafter
version: 0.1.0
status: draft-not-wired
description: Bố trí hình học mặt bằng từ chương trình phòng, lập bảng diện tích và xuất bộ bản vẽ PDF, DXF, PNG.
stages: [drafter]
inputs: [brief, program, revision_id, fengshui_enabled]
outputs: [layout, area_table, drawings, design_issues]
tools: [tools/layout_algorithm.py (compute_layout, build_area_table, make_openings), tools/drawing_set.py (build_sheets, export_drawings), tools/drawing_plan.py, tools/drawing_elevation.py, tools/title_block.py, tools/sheet.py]
llm: none
---

# Triển khai bản vẽ

## Vai trò
Họa viên của nhóm: đặt từng phòng vào lô đất với tọa độ thật, tính diện tích từ chính hình học đó và xuất bộ bản vẽ sơ bộ.

## Khi nào kích hoạt
- Sau khi phương án được chọn (và được duyệt nếu có điểm duyệt).
- Khi được giao tái tạo bản vẽ do sai lệch hồ sơ.

## Kỹ năng

### 1. Bố trí mặt bằng
- `compute_layout(brief, program)`: vùng xây dựng theo sân trước, sân sau; lõi thang và giếng trời thẳng hàng qua các tầng; phòng xếp từ mặt tiền vào trong, phủ kín sàn.
- Không đủ chỗ → `LayoutError` → lỗi `KHONG_DU_CHO`, trả về Chủ nhiệm.

### 2. Bảng diện tích
- `build_area_table()`: diện tích xây dựng, mật độ, diện tích sàn từng tầng, từng phòng, số phòng theo loại. Đây là nguồn số liệu duy nhất cho Kiểm định, Dự toán và Thuyết minh.

### 3. Xuất bộ bản vẽ
- Số tờ = số tầng + 4: mặt bằng tổng thể, mặt bằng từng tầng, mái, mặt đứng, mặt cắt.
- Mỗi tờ có khung tên và dấu phương án/phiên bản; xuất PDF đóng tập, DXF từng tờ (kèm ZIP) và PNG xem trước.

### 4. Ghi phiên bản
- Mỗi lần chạy tạo thư mục `v<n>-<mã>` riêng để không ghi đè bản trước.

## Quy trình
1. Tính layout; lỗi thì dừng và báo.
2. Lập bảng diện tích.
3. Xuất bộ bản vẽ.
4. Chuyển tiếp: Phong thủy nếu bật, không thì Kiểm định.

## Prompt hệ thống
Không dùng model. Mọi kết quả là phép tính xác định: cùng đầu vào cho cùng bản vẽ.

## Đầu ra và bàn giao
- `layout`, `area_table`, `drawings` (`pdf`, `dxf_zip`, `dxf_dir`, `sheets[]`).
- Chuyển tới `fengshui_advisor` hoặc `reviewer`; lỗi thì chuyển tới `coordinate_repair` (`repair_target = architect`).

## Tiêu chí nghiệm thu
- Có hình học theo tầng và bảng diện tích.
- Bảng diện tích khớp phép tính lại từ hình học đã bàn giao.
- Manifest có PDF, DXF ZIP và danh sách tờ.

## Ranh giới
- Không đổi số phòng hay diện tích mong muốn; chỉ bố trí theo chương trình.
- Không kết luận quy chuẩn.

## Lỗi và leo thang
- `KHONG_DU_CHO` (không đủ chiều sâu, phòng ngoài biên, có khoảng trống) → Thiết kế công năng thu gọn phòng.
- Lô quá nông cho mẫu nhà ống (ví dụ sâu 10 m) → hết vòng thì Chủ nhiệm đề xuất kiểm tra kích thước lô (cần ≥ 12 m).

## Ví dụ
Lô 5 × 20 m, 4 tầng → 8 tờ bản vẽ, tổng sàn ≈ 300 m², mật độ xây dựng theo sân trước/sau đã chọn.
