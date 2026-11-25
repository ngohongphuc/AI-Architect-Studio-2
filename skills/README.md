# Bộ skill của 9 agent

> **Trạng thái: bản thiết kế, chưa áp dụng.** Thư mục này chỉ lưu trong source code để tham khảo và thuyết trình.
> Không module Python nào đọc các file ở đây; workflow, prompt và kết quả của ứng dụng không thay đổi.

Mỗi agent có một bộ skill riêng, viết theo dạng `SKILL.md`. Mỗi bộ gồm phần đầu (frontmatter) để máy đọc và phần thân để người và model đọc. Một bộ skill gom lại năng lực vốn đang nằm rải rác trong code: vai trò, đầu vào, các kỹ năng con, công cụ dùng, quy tắc, prompt, đầu ra, tiêu chí nghiệm thu và cách xử lý lỗi.

## Danh sách

| Agent | Bộ skill | Số kỹ năng | Gọi model AI |
|---|---|---|---|
| Chủ nhiệm dự án | [project_manager/SKILL.md](project_manager/SKILL.md) | 6 | Diễn giải, lời khuyên |
| Phân tích yêu cầu | [requirements_analyst/SKILL.md](requirements_analyst/SKILL.md) | 4 | Trích brief có cấu trúc |
| Kiến trúc sư ý tưởng | [concept_architect/SKILL.md](concept_architect/SKILL.md) | 4 | Diễn giải ý tưởng |
| Thiết kế công năng | [architect/SKILL.md](architect/SKILL.md) | 5 | Hiểu góp ý tự nhiên |
| Triển khai bản vẽ | [drafter/SKILL.md](drafter/SKILL.md) | 4 | Không |
| Tư vấn phong thủy | [fengshui_advisor/SKILL.md](fengshui_advisor/SKILL.md) | 3 | Không |
| Kiểm định quy chuẩn | [reviewer/SKILL.md](reviewer/SKILL.md) | 4 | Tóm tắt lỗi |
| Dự toán chi phí | [cost_estimator/SKILL.md](cost_estimator/SKILL.md) | 4 | Ghi chú chi phí |
| Kiểm tra hồ sơ cuối | [final_reviewer/SKILL.md](final_reviewer/SKILL.md) | 4 | Không |

## Cấu trúc một file `SKILL.md`

```yaml
---
name: <mã-skill>                # duy nhất, chữ thường, gạch ngang
agent: <mã agent trong config.AGENT_ORDER>
version: 0.1.0
status: draft-not-wired         # chưa nối vào workflow
description: <một câu: skill làm gì và khi nào dùng>
stages: [<node LangGraph mà agent phụ trách>]
inputs: [<khóa DesignState được đọc>]
outputs: [<khóa DesignState được ghi>]
tools: [<module trong tools/ hoặc agents/ được gọi>]
llm: none | optional | required
---
```

Phần thân luôn có các mục theo cùng thứ tự: **Vai trò → Khi nào kích hoạt → Kỹ năng → Quy trình → Prompt hệ thống → Đầu ra và bàn giao → Tiêu chí nghiệm thu → Ranh giới → Lỗi và leo thang → Ví dụ**.

## Nguyên tắc chung cho mọi skill

1. **Số liệu do code tính, model chỉ diễn giải.** Diện tích, hình học, chi phí và kết quả kiểm tra không lấy từ model. Đoạn văn của model chứa con số khác bản gốc thì bị loại.
2. **Không bịa thông tin.** Thiếu dữ liệu thì ghi giả định có nhãn, hoặc chuyển thành câu hỏi xác nhận.
3. **Bàn giao có địa chỉ.** Mọi đầu ra đặt `route` (bước kế tiếp) và `_summary` (một câu cho nhật ký bàn giao).
4. **Lỗi đi về Chủ nhiệm.** Agent không tự gọi agent khác để sửa. Agent ghi `feedback` và `repair_target`, rồi Chủ nhiệm điều phối trong giới hạn 0–3 vòng.
5. **Tách kỹ thuật, quy chuẩn và tư vấn.** Lỗi kỹ thuật thì tốn vòng sửa. Thiếu căn cứ thì không tốn vòng sửa. Phong thủy chỉ để tham khảo.

## Nếu muốn áp dụng sau này (gợi ý, chưa làm)

- Viết một hàm `load_skill(agent)` đọc frontmatter và phần **Prompt hệ thống**, thay cho câu vai trò đang viết cứng trong từng file agent (ví dụ `SYSTEM_BRIEF` trong `agents/requirements_analyst.py`).
- Dùng mục **Tiêu chí nghiệm thu** để sinh hoặc đối chiếu `STAGE_RUBRICS` trong `monitoring/rubrics.py`.
- Hiển thị mục **Vai trò** và **Kỹ năng** trong bảng chi tiết agent của Studio AI.
- Thêm test kiểm tra mọi khóa trong `inputs`/`outputs` đều có trong `state.DesignState`.
