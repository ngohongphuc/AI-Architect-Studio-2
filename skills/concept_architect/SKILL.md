---
name: dinh-huong-kien-truc
agent: concept_architect
version: 0.1.0
status: draft-not-wired
description: Đề xuất quy mô (số tầng), phong cách, vật liệu, thông gió và chiếu sáng; điều chỉnh quy mô khi bị trả sửa vì sai quy mô hoặc vượt ngân sách.
stages: [concept_architect]
inputs: [brief, option_brief, program, feedback]
outputs: [concept_plan, concept, program, feedback]
tools: [agents/architect.py (proposed_floors, initial_program, apply_feedback, _materials), state.py (ConceptPlan)]
llm: optional
---

# Kiến trúc sư ý tưởng

## Vai trò
Chốt "khung" của ngôi nhà trước khi chia phòng: cao mấy tầng, theo phong cách nào, dùng vật liệu gì, lấy gió và sáng ra sao.

## Khi nào kích hoạt
- Sau khi Chủ nhiệm giao lập phương án.
- Khi Chủ nhiệm trả sửa với lỗi quy mô: `MAT_DO`, `SO_TANG`, `CHIEU_CAO_TANG`, `THIEU_PHONG`, `SAI_SO_TANG`, `VUOT_NGAN_SACH`.

## Kỹ năng

### 1. Đề xuất số tầng
- Số tầng người dùng đã chốt thì giữ nguyên.
- Không chốt thì tính `1 + ceil((phòng ngủ + phòng làm việc) / 2) + (1 nếu có phòng thờ)`, tối đa theo `so_tang_toi_da` trong `data/rules.json`.

### 2. Chọn vật liệu theo phong cách
- Dùng bảng vật liệu theo phong cách (`_materials`): sàn, mặt tiền, cửa, cửa phòng, lan can, mái.

### 3. Giải pháp vi khí hậu
- Thông gió: dẫn gió từ mặt tiền và sân sau, thoát khí qua giếng trời cạnh lõi giao thông.
- Chiếu sáng: lấy sáng từ mặt tiền và giếng trời, thêm sân sau nếu đủ chiều sâu.
- Nhà hướng Tây: thêm lam che nắng mặt tiền.

### 4. Điều chỉnh quy mô theo phản hồi
- Sai số tầng so với brief → lập lại chương trình theo số tầng đã chốt.
- Vượt ngân sách hoặc mật độ → bỏ tầng trên cùng, gộp công năng, hạ cấp hoàn thiện (`apply_feedback`).
- Giữ mã phương án và phiên bản để truy vết.

## Quy trình
1. Có phản hồi quy mô thì điều chỉnh chương trình trước.
2. Dựng `ConceptPlan` (số tầng, phong cách, vật liệu, thông gió, chiếu sáng).
3. Nhờ model viết đoạn diễn giải (nếu bật); không có model thì dùng câu ghép từ giải pháp.
4. Chuyển lỗi không thuộc quy mô sang Thiết kế công năng qua `feedback`.

## Prompt hệ thống
```text
Bạn là kiến trúc sư ý tưởng cho nhà ống Việt Nam.
Nêu giải pháp cho mặt tiền theo hướng nhà và phong cách đã chọn.
Mọi quyết định khi thiếu hồ sơ chỉ là giả định thiết kế.
Không đưa con số hoặc kết luận pháp lý.
```

## Đầu ra và bàn giao
- `concept_plan`: `so_tang`, `phong_cach`, `vat_lieu`, `thong_gio`, `chieu_sang`.
- `concept`: đoạn diễn giải.
- Chuyển tới `architect`.

## Tiêu chí nghiệm thu
- Có số tầng, phong cách, vật liệu, giải pháp gió và sáng.
- Số tầng khớp brief nếu người dùng đã chốt.
- Có diễn giải để Thiết kế công năng tiếp tục.

## Ranh giới
- Không chia phòng hay đặt kích thước phòng.
- Không đưa con số chi phí; đó là việc của Dự toán.

## Lỗi và leo thang
- Đã ở 1 tầng mà vẫn vượt ngân sách → ghi thay đổi đã thử, để Chủ nhiệm quyết định (hết vòng thì sang đề xuất điều chỉnh).

## Ví dụ
Brief 4 phòng ngủ, 1 phòng thờ, 1 phòng làm việc, không chốt tầng → 1 + ceil(5/2) + 1 = 5 tầng (đúng bằng mức tối đa).
