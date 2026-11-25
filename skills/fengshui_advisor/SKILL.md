---
name: tu-van-phong-thuy-bat-trach
agent: fengshui_advisor
version: 0.1.0
status: draft-not-wired
description: Tư vấn Bát trạch theo năm sinh, giới tính chủ nhà và hướng nhà; kiểm tra vị trí WC, bếp, phòng thờ trên mặt bằng. Chỉ để tham khảo, không chặn workflow.
stages: [fengshui_advisor]
inputs: [brief, layout, fengshui_enabled, revision_id]
outputs: [fengshui]
tools: [tools/fengshui.py (analyze), tools/layout_algorithm.py (room_at), agents/reviewer.py (_overlap, _adjacent), data/phong_thuy/bat_trach_tom_tat.md]
llm: none
---

# Tư vấn phong thủy

## Vai trò
Đưa góc nhìn văn hóa mà nhiều chủ nhà Việt Nam quan tâm, tách bạch hoàn toàn với kết luận kỹ thuật và quy chuẩn.

## Khi nào kích hoạt
Ngay sau Triển khai bản vẽ, **chỉ khi** `fengshui_enabled = true`. Chạy trước Kiểm định quy chuẩn.

## Kỹ năng

### 1. Phân tích cung mệnh và hướng nhà
- `analyze(năm sinh, giới tính, hướng)` → cung mệnh, nhóm Đông/Tây tứ mệnh, sao của hướng nhà, danh sách hướng tốt.
- Thiếu năm sinh → `co_du_lieu = false`, ghi chú và bỏ qua phần cung mệnh.

### 2. Kiểm tra bố trí trên mặt bằng
| Mã | Kiểm tra | Mức |
|---|---|---|
| `WC_TREN_THO` | WC tầng trên chồng lên phòng thờ tầng dưới | Gợi ý |
| `BEP_KE_WC` | Bếp chung tường với WC | Gợi ý |
| — | Phòng thờ ở tầng trên cùng | Gợi ý |
| — | WC nằm ở tâm nhà | Gợi ý |

### 3. Gợi ý hóa giải
- Hướng chưa hợp → xoay cửa chính, bàn thờ, bếp về hướng tốt.
- Mỗi gợi ý có `noi_dung` và `de_xuat` ngắn, có thể áp dụng ở giai đoạn thiết kế kỹ thuật.

## Quy trình
1. Phân tích cung mệnh (nếu đủ dữ liệu).
2. Chạy bốn phép kiểm tra trên layout.
3. Gom kết quả, chuyển cho Kiểm định quy chuẩn.

## Prompt hệ thống
Không dùng model. Nội dung diễn đạt dựa trên bản tóm tắt Bát trạch trong `data/phong_thuy/`.

## Đầu ra và bàn giao
- `fengshui`: `thong_tin`, `bo_tri` (danh sách đạt/không đạt), `goi_y`.
- Chuyển tới `reviewer`.

## Tiêu chí nghiệm thu
- Có trạng thái dữ liệu gia chủ và danh sách kiểm tra bố trí.
- Kết quả kiểm tra khớp phép tính lại từ hình học và brief.
- Gợi ý nằm trong mục phong thủy riêng, không trộn với quy chuẩn.

## Ranh giới
- Không bao giờ tạo lỗi cần sửa; không làm lượt "Chưa đạt".
- Không khẳng định tốt/xấu tuyệt đối; luôn dùng giọng tham khảo.

## Lỗi và leo thang
- Không có lỗi chặn. Thiếu dữ liệu chỉ làm giảm phạm vi tư vấn.

## Ví dụ
Chủ nhà nam sinh 1988, nhà hướng Đông Nam → cung mệnh và đánh giá hợp/chưa hợp hướng; WC tầng 4 chồng lên phòng thờ tầng 3 → gợi ý "Dời WC tầng 4 ra phía sau".
