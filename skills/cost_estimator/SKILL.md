---
name: du-toan-chi-phi-xay-dung
agent: cost_estimator
version: 0.1.0
status: draft-not-wired
description: So sánh và xếp hạng các phương án trước khi vẽ; sau kiểm định lập dự toán chi tiết XLSX có công thức, so ngân sách và đề xuất tiết kiệm.
stages: [compare_options, check_edited_option, cost_estimator]
inputs: [brief, program, options, selected_by_user, layout, area_table, review, revision_id]
outputs: [options, recommended_option, program, cost, cost_file, budget_issues]
tools: [tools/cost_calc.py (compute_cost), tools/xlsx_writer.py (write_cost_xlsx), tools/layout_algorithm.py, data/don_gia.xlsx, agents/reviewer.py (code_checks)]
llm: optional
---

# Dự toán chi phí

## Vai trò
Trả lời câu hỏi "xây hết bao nhiêu và có vừa túi tiền không", với mọi con số truy được tới khối lượng × đơn giá.

## Khi nào kích hoạt
- Ngay sau Thiết kế công năng: so sánh A/B/C (`compare_options`).
- Khi người dùng vừa chỉnh phương án (`check_edited_option`).
- Sau Kiểm định quy chuẩn: lập dự toán chi tiết (`cost_estimator`).

## Kỹ năng

### 1. Đánh giá từng phương án
- Bố trí thử, lập bảng diện tích, tính chi phí, chạy kiểm tra kỹ thuật (`evaluate_option`).
- Phương án lỗi chặn → `eligible = false` kèm lỗi.

### 2. Xếp hạng và đề xuất
- Thứ tự ưu tiên: không vượt quá 10% ngân sách → ưu tiên của chủ nhà (tiết kiệm/cao cấp) → ít tiêu chí chưa xác minh → diện tích chiếm đất nhỏ → chi phí thấp.
- Ghi `ly_do_uu_tien` một đoạn ngắn; giữ lựa chọn của người dùng nếu vẫn khả thi.

### 3. Lập dự toán chi tiết
- `compute_cost()`: diện tích quy đổi (móng, tầng, mái, sân), hạng mục phần thô và nhân công, vật tư hoàn thiện theo gói, điện nước, cửa nhôm, cửa gỗ, cửa cuốn, thiết kế, dự phòng.
- `write_cost_xlsx()`: các sheet `Tong_hop`, `Dien_tich`, `Chi_tiet`, `Don_gia`, `Tiet_kiem`, `Gia_dinh`, **có công thức Excel**, kèm dấu phương án/phiên bản.

### 4. So ngân sách và đề xuất tiết kiệm
- `vuot_pct = (tổng − ngân sách) / ngân sách`. Vượt > 10% (`BUDGET_TOLERANCE`) và ngân sách do người dùng nhập → lỗi `VUOT_NGAN_SACH`.
- Liệt kê các cách tiết kiệm (bớt tầng, hạ gói hoàn thiện…) kèm số tiền tiết kiệm ước tính.

## Quy trình
1. So sánh: đánh giá tất cả phương án → chọn đề xuất → chuyển Bản vẽ. Không phương án nào khả thi → trả Chủ nhiệm.
2. Chi tiết: tính chi phí → xuất XLSX → vượt ngưỡng thì trả Chủ nhiệm, không thì chuyển Chủ nhiệm tổng hợp.

## Prompt hệ thống
```text
Bạn là kỹ sư dự toán xây dựng nhà phố tại Việt Nam.
Viết lại ghi chú chi phí cho chủ nhà dễ hiểu, giữ nguyên mọi con số và thứ tự đề xuất tiết kiệm.
Không thêm đơn giá, hạng mục hay con số mới.
```

## Đầu ra và bàn giao
- So sánh: `options[]` (kèm `chi_so`, `uu_diem`, `han_che`, `loi`), `recommended_option`, `program`.
- Chi tiết: `cost` (`hang_muc`, `tong_chi_phi`, `ngan_sach`, `vuot_pct`, `tiet_kiem`, `ghi_chu`), `cost_file`.

## Tiêu chí nghiệm thu
- So sánh: mã phương án đầy đủ; mã đề xuất thuộc nhóm khả thi; có lý do đề xuất.
- Chi tiết: có hạng mục, chi phí xây dựng, dự phòng, ngân sách; thành tiền và chênh lệch khớp phép tính; có XLSX, ghi chú và phương án tiết kiệm.

## Ranh giới
- Ngân sách là giả định → chỉ ghi chênh lệch để tham khảo, không báo lỗi.
- Đơn giá là giả định tham khảo trong `data/don_gia.xlsx`, chưa đối chiếu thị trường.

## Lỗi và leo thang
- `VUOT_NGAN_SACH` → Chủ nhiệm giao Kiến trúc sư ý tưởng giảm quy mô. Hết vòng → vẫn tổng hợp hồ sơ tham khảo, rồi đề xuất điều chỉnh (có lựa chọn tăng ngân sách).

## Ví dụ
4 phòng ngủ, ngân sách 3 tỷ → phương án B 3,43 tỷ (+14,3%) → `VUOT_NGAN_SACH`; đề xuất tiết kiệm: "Bớt tầng 5 (gộp phòng thờ xuống tầng dưới)".
