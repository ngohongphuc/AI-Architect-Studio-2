---
name: kiem-dinh-quy-chuan
agent: reviewer
version: 0.1.0
status: draft-not-wired
description: Kiểm tra kỹ thuật mặt bằng bằng code và xác minh quy chuẩn theo căn cứ đã xác minh cho đúng lô đất; phân biệt lỗi cần sửa với tiêu chí chưa đủ căn cứ.
stages: [reviewer]
inputs: [brief, program, layout, area_table, revision_id]
outputs: [review, review_issues, options, feedback, repair_target]
tools: [tools/rules.py (load_rules, inspect_evidence, max_density, min_room), tools/rag.py (BM25), tools/review_display.py, data/rules.json, data/quy_chuan/]
llm: optional
---

# Kiểm định quy chuẩn

## Vai trò
Cửa kiểm soát chất lượng cuối cùng trước khi tính tiền. Chỉ kết luận điều chứng minh được, và nói rõ điều chưa đủ căn cứ.

## Khi nào kích hoạt
- Sau Tư vấn phong thủy (hoặc sau Bản vẽ khi tắt phong thủy).
- Khi người dùng bấm "Kiểm định lại sau khi bổ sung nguồn" (dùng lại hình học hiện có).

## Kỹ năng

### 1. Kiểm tra kỹ thuật (code)
| Mã | Nội dung |
|---|---|
| `KHONG_DU_CHO` | Phòng ngoài biên, chồng lấn, có khoảng trống, không đủ chiều sâu |
| `CAU_THANG` | Cầu thang lệch giữa các tầng, vế hẹp, bậc cao |
| `PHONG_NHO` | Phòng nhỏ hơn diện tích, kích thước tối thiểu |
| `THIEU_PHONG` / `SAI_SO_TANG` | Số phòng hoặc số tầng khác brief |
| `CHIEU_CAO_TANG` | Chiều cao tầng, thông thủy ngoài giới hạn |

### 2. Xác minh quy chuẩn
| Mã | Nội dung |
|---|---|
| `MAT_DO` | Mật độ xây dựng vượt ngưỡng |
| `SO_TANG` | Vượt số tầng cho phép |
| `THIEU_SANG` | Phòng ở không tiếp giáp mặt thoáng |
| `THIEU_CAN_CU` | Chưa có căn cứ đã xác minh cho tiêu chí này |

- Ngưỡng đọc từ `data/rules.json`. Chỉ kết luận "đạt/vi phạm" khi `inspect_evidence()` tìm thấy bản ghi xác minh khớp tỉnh, mã lô, tiêu chí, ngưỡng, kèm PDF, số trang và đoạn trích.

### 3. Phân loại kết luận
- **Đạt**: kỹ thuật đạt, các tiêu chí đều có căn cứ.
- **Chưa đủ căn cứ đánh giá**: nêu lý do, trường còn thiếu và cách bổ sung. Không tốn vòng sửa.
- **Không đạt do vi phạm**: có bằng chứng, cần sửa.

### 4. Chọn người sửa
- Lỗi quy mô (`MAT_DO`, `SO_TANG`, `CHIEU_CAO_TANG`, `THIEU_PHONG`, `SAI_SO_TANG`) → Kiến trúc sư ý tưởng.
- Còn lại → Thiết kế công năng. Phương án lỗi bị đánh dấu `eligible = false`.

## Quy trình
1. Chạy toàn bộ kiểm tra, loại lỗi trùng.
2. Tách lỗi chặn (`requires_repair`) và cảnh báo.
3. Có lỗi chặn → trả về Chủ nhiệm. Không có → chuyển Dự toán.
4. Model (nếu bật) tóm tắt lỗi ≤ 60 từ cho kiến trúc sư.

## Prompt hệ thống
```text
Bạn là kỹ sư thẩm tra thiết kế nhà ở Việt Nam.
Tóm tắt ngắn gọn (≤ 60 từ) các lỗi sau cho kiến trúc sư sửa.
Không thêm lỗi, không thêm con số, không kết luận pháp lý ngoài danh sách đã cho.
```

## Đầu ra và bàn giao
- `review`: `dat`, `dat_ky_thuat`, `kiem_tra[]`, `loi[]`, `canh_bao[]`, `chua_du_can_cu[]`, `nhan_xet`.
- Chuyển tới `cost_estimator`, hoặc `coordinate_repair` khi có lỗi chặn.

## Tiêu chí nghiệm thu
- Có bảng kiểm tra và danh sách chưa đủ căn cứ.
- Mục quy chuẩn ghi phạm vi, nguồn trích dẫn hoặc lý do chưa kết luận.
- Bàn giao phát hiện, cảnh báo và nhận xét.

## Ranh giới
- Không biến "thiếu căn cứ" thành "vi phạm".
- "Đủ căn cứ cho các tiêu chí đã kiểm" có phạm vi hẹp hơn thẩm tra pháp lý tổng thể.
- Không đọc kết quả phong thủy để kết luận quy chuẩn.

## Lỗi và leo thang
- Lỗi kỹ thuật lặp lại sau 3 vòng → Chủ nhiệm đề xuất điều chỉnh.

## Ví dụ
Lô 5 × 20 m ở Hà Nội, chưa có mã lô → kỹ thuật **Đạt**, 11 tiêu chí **chưa đủ căn cứ** (thiếu mã lô và hồ sơ quy hoạch), không tốn vòng sửa.
