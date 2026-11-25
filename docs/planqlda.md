# AI Architect Studio
## Hệ thống multi-agent tự động thiết kế nhà ở

> Bài tập lớn – Nhóm 5 thành viên
> Thời gian thực hiện: 8 tuần

---

## 1. Giới thiệu

### 1.1. Bối cảnh
Thiết kế một ngôi nhà ở cần sự phối hợp của nhiều vai trò: chủ nhiệm dự án, kiến trúc sư, họa viên, kỹ sư kiểm định quy chuẩn và kỹ sư dự toán. Ở giai đoạn **thiết kế sơ bộ**, phần lớn công việc mang tính lặp lại (phân tích yêu cầu, chia công năng, vẽ mặt bằng, kiểm tra quy chuẩn, bóc khối lượng, tính chi phí) và thường mất từ vài ngày đến vài tuần.

### 1.2. Ý tưởng
Xây dựng một **"văn phòng kiến trúc ảo"**, trong đó mỗi vai trò là một **AI agent**. Người dùng chỉ nhập yêu cầu bằng ngôn ngữ tự nhiên. Các agent **tự động phối hợp, kiểm tra chéo và sửa lỗi cho nhau**, sau đó xuất ra **3 sản phẩm**: bản vẽ thiết kế, file mô tả chi tiết dự án và file ước tính chi phí.

### 1.3. Mục tiêu
- Xây dựng hệ thống 5 agent chuyên biệt, phối hợp qua luồng điều phối có **vòng lặp phản hồi** (feedback loop).
- Tự động tạo đủ 3 sản phẩm đầu ra, thống nhất số liệu với nhau (cùng diện tích, cùng danh sách phòng).
- Đảm bảo phương án tuân thủ các quy chuẩn xây dựng cơ bản (QCVN 01:2021/BXD) và có tư vấn phong thủy.
- Đánh giá hệ thống bằng bộ yêu cầu thử nghiệm với tiêu chí định lượng.

### 1.4. Phạm vi
| Trong phạm vi | Ngoài phạm vi |
|---|---|
| Nhà ở riêng lẻ (nhà phố, nhà ống) 1–5 tầng | Chung cư, công trình công cộng |
| Lô đất hình chữ nhật | Lô đất hình dạng phức tạp |
| Bản vẽ 2D thiết kế sơ bộ | Mô hình 3D, ảnh phối cảnh |
| Kiểm tra quy chuẩn cơ bản | Tính toán kết cấu chi tiết, bản vẽ thi công |
| Ước tính chi phí theo hạng mục | Dự toán chi tiết theo định mức nhà nước |

---

## 2. Đầu vào và đầu ra

### 2.1. Đầu vào (ví dụ)
> *"Lô đất 5×20m, mặt tiền hướng Đông Nam, ở Hà Nội. Gia đình 4 người (vợ chồng sinh năm 1990 và 1992, 2 con nhỏ). Cần 3 phòng ngủ, 1 phòng thờ, có gara xe máy. Ngân sách 2,5 tỷ. Phong cách hiện đại, nhiều ánh sáng tự nhiên."*

### 2.2. Đầu ra (3 sản phẩm)

| # | Sản phẩm | Định dạng | Nội dung |
|---|---|---|---|
| 1 | **Bộ bản vẽ thiết kế** | PDF (đóng tập) + DXF (mở bằng AutoCAD) | Mặt bằng tổng thể, mặt bằng từng tầng, mặt bằng mái, mặt đứng chính, mặt cắt dọc |
| 2 | **File mô tả chi tiết dự án** (thuyết minh thiết kế) | DOCX hoặc PDF | Thông tin dự án, ý tưởng, giải pháp công năng, bảng thống kê diện tích, kết quả kiểm tra quy chuẩn và phong thủy |
| 3 | **File ước tính chi phí** | XLSX (có công thức) | Bảng diện tích quy đổi, chi phí theo hạng mục, tổng hợp và so sánh với ngân sách, phương án tiết kiệm |

**Yêu cầu chung:** cả 3 sản phẩm phải dùng **cùng một nguồn dữ liệu** (trạng thái chung của hệ thống), để diện tích trên bản vẽ, trong thuyết minh và trong file chi phí luôn khớp nhau.

---

## 3. Kiến trúc hệ thống

### 3.1. Năm agent

| # | Agent | Vai trò như ngoài đời | Sản phẩm phụ trách |
|---|---|---|---|
| 1 | **Chủ nhiệm dự án** | Chủ trì, làm việc với khách hàng | Brief + **File mô tả chi tiết dự án** |
| 2 | **Kiến trúc sư** | Lên ý tưởng, chia công năng | Ý tưởng + chương trình công năng |
| 3 | **Họa viên** | Triển khai bản vẽ | **Bộ bản vẽ thiết kế** |
| 4 | **Kiểm định viên** | Thẩm tra quy chuẩn, phong thủy | Báo cáo kiểm tra + phản hồi sửa lỗi |
| 5 | **Kỹ sư dự toán** | Bóc khối lượng, tính chi phí | **File ước tính chi phí** |

### 3.2. Sơ đồ luồng xử lý

```
                 ┌──────────────────────┐
  Yêu cầu  ───▶  │ 1. Chủ nhiệm         │
  người dùng     │    Phân tích brief   │
                 └──────────┬───────────┘
                            ▼
                 ┌──────────────────────┐
           ┌───▶ │ 2. Kiến trúc sư      │
           │     │    Ý tưởng+công năng │
           │     └──────────┬───────────┘
           │                ▼
           │     ┌──────────────────────┐
           │     │ 3. Họa viên          │
           │     │    Bố trí + vẽ       │
           │     └──────────┬───────────┘
           │                ▼
           │     ┌──────────────────────┐
           └──── │ 4. Kiểm định viên    │
         Vi phạm │    Quy chuẩn+phong   │
       (tối đa 3 │    thủy              │
          vòng)  └──────────┬───────────┘
                            ▼ Đạt
                 ┌──────────────────────┐
                 │ 5. Kỹ sư dự toán     │──▶ du_toan.xlsx
                 └──────────┬───────────┘
              (vượt ngân sách > 10% → quay lại Kiến trúc sư)
                            ▼
                 ┌──────────────────────┐
                 │ 1. Chủ nhiệm         │──▶ thuyet_minh.docx
                 │    Tổng hợp hồ sơ    │──▶ ban_ve.pdf / .dxf
                 └──────────────────────┘
```

Hệ thống có **2 vòng lặp phản hồi**:
- **Vòng quy chuẩn:** Kiểm định viên phát hiện vi phạm → Kiến trúc sư sửa → Họa viên vẽ lại.
- **Vòng ngân sách:** Kỹ sư dự toán thấy vượt ngân sách quá 10% → Kiến trúc sư giảm diện tích hoặc đổi vật liệu.

Tổng số vòng sửa giới hạn ở **3** để hệ thống không lặp vô hạn.

### 3.3. Trạng thái dùng chung (Shared State)

```python
class DesignState(TypedDict):
    user_request: str        # Yêu cầu gốc
    brief: dict              # Brief có cấu trúc          (Agent 1)
    concept: str             # Ý tưởng thiết kế          (Agent 2)
    program: dict            # Danh sách phòng theo tầng (Agent 2)
    layout: dict             # Tọa độ, kích thước phòng  (Agent 3)
    area_table: dict         # Thống kê diện tích        (Agent 3)
    drawings: dict           # Đường dẫn PDF, DXF        (Agent 3)
    review: dict             # Kết quả kiểm tra          (Agent 4)
    cost: dict               # Kết quả chi phí           (Agent 5)
    cost_file: str           # Đường dẫn du_toan.xlsx    (Agent 5)
    description_file: str    # Đường dẫn thuyet_minh     (Agent 1)
    iteration: int           # Số vòng sửa hiện tại
    log: list[str]           # Nhật ký hoạt động các agent
```

### 3.4. Công nghệ sử dụng
| Thành phần | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.11+ |
| Khung multi-agent | LangGraph (hỗ trợ vòng lặp, rẽ nhánh có điều kiện) |
| Mô hình ngôn ngữ | Gemini / GPT / Claude qua LangChain; Ollama nếu chạy offline |
| Kiểm soát định dạng đầu ra | Pydantic (structured output) |
| RAG tra quy chuẩn | ChromaDB + PyPDF |
| Bố trí mặt bằng | Thuật toán Python tự viết |
| Vẽ bản vẽ 2D | ezdxf (DXF) + Matplotlib (xuất PDF) |
| File mô tả | python-docx (DOCX), có thể xuất thêm PDF |
| File chi phí | openpyxl (XLSX có công thức) |
| Giao diện | Streamlit |
| Quản lý mã nguồn | GitHub |

---

## 4. Mô tả chi tiết 5 agent

### Agent 1 – Chủ nhiệm dự án (Project Manager)
**Vai trò:** Tiếp nhận yêu cầu, điều phối, viết **file mô tả chi tiết dự án**.

**Nhiệm vụ:**
1. Phân tích yêu cầu tự nhiên thành brief JSON (kích thước đất, hướng, số người, số phòng, ngân sách, phong cách, năm sinh gia chủ).
2. Phát hiện thông tin thiếu, tự điền giá trị mặc định hợp lý và ghi rõ là giả định.
3. Theo dõi số vòng sửa; dừng sau 3 vòng và ghi nhận lỗi còn tồn tại.
4. Khi các agent khác xong việc: viết **thuyết minh thiết kế** và đóng gói 3 sản phẩm.

**Ví dụ brief:**
```json
{
  "lo_dat": {"rong": 5, "dai": 20, "huong": "Đông Nam", "tinh": "Hà Nội"},
  "gia_dinh": {"so_nguoi": 4, "nam_sinh_chu_nha": 1990},
  "yeu_cau_phong": {"phong_ngu": 3, "phong_tho": 1, "gara": "xe máy"},
  "ngan_sach": 2500000000,
  "phong_cach": "hiện đại",
  "gia_dinh_bo_sung": ["Số tầng: để Kiến trúc sư đề xuất"]
}
```

**Cấu trúc file mô tả chi tiết dự án (thuyet_minh.docx):**
1. Thông tin chung: chủ đầu tư, địa điểm, diện tích đất, quy mô (số tầng, tổng diện tích sàn).
2. Yêu cầu của chủ đầu tư (tóm tắt brief).
3. Ý tưởng thiết kế: phong cách, hình khối mặt tiền, vật liệu chủ đạo.
4. Giải pháp công năng từng tầng.
5. Giải pháp thông gió, chiếu sáng tự nhiên (giếng trời, ban công, cửa sổ).
6. Bảng thống kê diện tích từng phòng, từng tầng.
7. Kết quả kiểm tra quy chuẩn (mật độ xây dựng, chiều cao, cầu thang…).
8. Tư vấn phong thủy (cung mệnh, hướng nhà, vị trí bếp, phòng thờ, WC).
9. Tóm tắt chi phí (trích từ file chi phí).
10. Các giả định và lưu ý.

> Mọi con số trong thuyết minh được **lấy trực tiếp từ trạng thái chung**, LLM chỉ viết phần văn bản, không tự nghĩ ra số liệu.

### Agent 2 – Kiến trúc sư (Architect)
**Vai trò:** Đề xuất ý tưởng và chương trình công năng.

**Nhiệm vụ:**
1. Đề xuất số tầng, phong cách, giải pháp thông gió, chiếu sáng.
2. Lập danh sách phòng theo tầng: tên, diện tích mong muốn, kích thước tối thiểu, các phòng cần kề nhau, vị trí ưu tiên (mặt tiền / giữa / sau).
3. Đề xuất vật liệu hoàn thiện chính (dùng cho dự toán và mặt đứng).
4. Khi nhận phản hồi từ Agent 4 hoặc Agent 5: điều chỉnh phương án (giảm diện tích, đổi vị trí, bớt tầng, đổi vật liệu).

**Ví dụ đầu ra:**
```json
{
  "so_tang": 4,
  "chieu_cao_tang": {"tang_1": 3.6, "tang_khac": 3.3},
  "vat_lieu": {"san": "gạch 60x60", "mat_tien": "sơn + kính cường lực"},
  "tang_1": [
    {"ten": "Gara", "dien_tich": 15, "vi_tri": "mặt tiền"},
    {"ten": "Phòng khách", "dien_tich": 22, "ke_ben": ["Gara"]},
    {"ten": "Bếp + ăn", "dien_tich": 20, "vi_tri": "sau"},
    {"ten": "WC", "dien_tich": 3},
    {"ten": "Cầu thang", "dien_tich": 8, "co_dinh": true},
    {"ten": "Giếng trời", "dien_tich": 6, "co_dinh": true}
  ],
  "tang_2": ["..."]
}
```

### Agent 3 – Họa viên (Drafter)
**Vai trò:** Bố trí phòng và xuất **bộ bản vẽ thiết kế**.

> **Lưu ý kỹ thuật:** LLM không vẽ được bản vẽ chính xác về hình học. Agent này dùng **thuật toán Python** để tính tọa độ và vẽ; LLM chỉ hỗ trợ chọn thứ tự ưu tiên khi có nhiều cách xếp.

**Nhiệm vụ:**
1. Xác định vùng xây dựng (trừ khoảng lùi, sân trước/sau nếu có).
2. Xếp phòng theo chiều dài nhà ống, giữ cầu thang và giếng trời cố định thẳng hàng giữa các tầng.
3. Kiểm tra không chồng lấn, đủ kích thước tối thiểu.
4. Lập **bảng thống kê diện tích** (dùng chung cho Agent 1, 4, 5).
5. Vẽ bộ bản vẽ trên các layer riêng (tường, cửa, chữ, kích thước, trục):

| Số hiệu | Tên bản vẽ | Nội dung |
|---|---|---|
| KT-01 | Mặt bằng tổng thể | Ranh giới lô đất, vị trí nhà, khoảng lùi, hướng Bắc |
| KT-02…05 | Mặt bằng tầng 1…4 | Tường, cửa đi, cửa sổ, tên phòng, diện tích, kích thước, trục |
| KT-06 | Mặt bằng mái | Mái, sênh thoát nước, giếng trời |
| KT-07 | Mặt đứng chính | Mặt tiền: cao độ tầng, cửa, ban công, vật liệu |
| KT-08 | Mặt cắt dọc | Cao độ sàn, cầu thang, giếng trời |

6. Mỗi bản vẽ có **khung tên** (tên dự án, tên bản vẽ, số hiệu, tỉ lệ, ngày).
7. Xuất **DXF** (từng bản vẽ) và **PDF** đóng tập.

**Thuật toán bố trí (phiên bản cơ bản):**
1. Chia vùng xây dựng thành dải theo chiều dài.
2. Sắp xếp phòng theo vị trí ưu tiên: mặt tiền → giữa → sau.
3. Mỗi phòng chiếm một đoạn dải; phòng nhỏ (WC, kho) chia chung chiều ngang với cầu thang.
4. Kiểm tra ràng buộc kề nhau và kích thước tối thiểu; nếu sai thì đổi thứ tự và thử lại.

**Phiên bản nâng cao (nếu kịp):** dùng OR-Tools (tối ưu ràng buộc) hoặc thuật toán di truyền.

### Agent 4 – Kiểm định viên (Reviewer)
**Vai trò:** Thẩm tra phương án, trả phản hồi để sửa.

**Nhiệm vụ:**
1. **Kiểm tra quy chuẩn** (tra cứu bằng RAG trên QCVN 01:2021/BXD và quy định địa phương):
   - Mật độ xây dựng tối đa theo diện tích lô đất.
   - Chiều cao tầng, chiều cao công trình, số tầng cho phép.
   - Cầu thang: bề rộng vế, chiều cao và bề rộng bậc.
   - Diện tích tối thiểu phòng ở; yêu cầu thông gió, chiếu sáng.
2. **Kiểm tra kỹ thuật bằng code** (không dùng LLM): tổng diện tích, kích thước phòng, chồng lấn, cầu thang thẳng hàng giữa các tầng.
3. **Kiểm tra phong thủy:** cung mệnh theo năm sinh, hướng nhà, vị trí bếp, phòng thờ, WC (WC không đặt trên phòng thờ, bếp không đối diện WC…).
4. **Kiểm tra tính nhất quán:** số phòng trên bản vẽ khớp với yêu cầu trong brief.
5. Trả kết quả có cấu trúc:

```json
{
  "dat": false,
  "loi": [
    {"loai": "Quy chuẩn", "muc": "Mật độ xây dựng",
     "hien_tai": "100%", "cho_phep": "≤ 90%",
     "de_xuat": "Thêm sân sau 2m"},
    {"loai": "Phong thủy", "noi_dung": "WC tầng 4 nằm trên phòng thờ",
     "de_xuat": "Dời WC tầng 4 ra phía sau"}
  ]
}
```

### Agent 5 – Kỹ sư dự toán (Cost Estimator)
**Vai trò:** Bóc khối lượng sơ bộ và lập **file ước tính chi phí**.

**Nhiệm vụ:**
1. Lấy bảng diện tích từ Agent 3, tính **diện tích sàn quy đổi**:
   - Móng: 30–50% diện tích tầng 1 (tùy loại móng).
   - Các tầng: 100% diện tích sàn; sân, ban công: 50–70%.
   - Mái: 30–50% diện tích mái (tùy loại mái).
2. Tính chi phí theo **hạng mục**: phần thô, hoàn thiện, điện nước, cửa, chi phí thiết kế, dự phòng (5–10%).
3. Đơn giá lấy từ file `don_gia.xlsx` (nhóm tự thu thập từ giá thị trường tham khảo).
4. **Mọi phép tính làm bằng Python và công thức Excel**, LLM chỉ viết phần ghi chú, đề xuất.
5. So sánh với ngân sách; nếu vượt quá 10% thì đề xuất phương án tiết kiệm và gửi phản hồi về Kiến trúc sư.

**Cấu trúc file ước tính chi phí (du_toan.xlsx):**

| Sheet | Nội dung |
|---|---|
| `Tong_hop` | Tổng chi phí, so sánh ngân sách, chi phí/m² sàn |
| `Dien_tich` | Diện tích từng tầng, hệ số quy đổi, diện tích quy đổi |
| `Chi_tiet` | Hạng mục – đơn vị – khối lượng – đơn giá – thành tiền |
| `Don_gia` | Bảng đơn giá tham khảo đã dùng, nguồn, thời điểm |
| `Tiet_kiem` | Phương án giảm chi phí (nếu vượt ngân sách) |

> Các ô thành tiền dùng **công thức Excel** (không ghi số cứng), để người dùng có thể sửa đơn giá và file tự tính lại.

---

## 5. Giao diện người dùng

Ứng dụng web Streamlit gồm **3 trang**:

| Trang | Mục đích |
|---|---|
| **Thiết kế** | Nhập yêu cầu, bấm "Thiết kế", theo dõi nhanh tiến trình |
| **Quản lý agent** | Theo dõi và điều khiển chi tiết từng agent (mục 5.1) |
| **Kết quả** | Xem trước và tải 3 sản phẩm đầu ra (mục 5.2) |

### 5.1. Giao diện quản lý tiến trình agent

#### a) Bố cục màn hình

```
┌──────────────────────────────────────────────────────────────────┐
│  AI ARCHITECT STUDIO – QUẢN LÝ AGENT        [⏸ Tạm dừng] [⏹ Dừng] │
├──────────────────────────────────────────────────────────────────┤
│  Tiến trình: ████████████░░░░░░░░  Bước 3/5 – Họa viên đang vẽ    │
│  Vòng sửa: 2/3      Thời gian: 01:42      Token: 18.250  (~$0,02) │
├────────────┬────────────┬────────────┬────────────┬──────────────┤
│ 1.Chủ nhiệm│2.Kiến trúc │ 3.Họa viên │4.Kiểm định │ 5.Dự toán    │
│   ✅ Xong  │   ✅ Xong  │ 🔄 Đang    │  ⏳ Chờ    │  ⏳ Chờ      │
│   12 giây  │  2 lần chạy│   chạy     │  1 lỗi ở   │              │
│   1.200 tk │  6.400 tk  │  35 giây   │  vòng 1    │              │
│ [Xem][↻]   │ [Xem][↻]   │ [Xem][↻]   │ [Xem][↻]   │ [Xem][↻]     │
├────────────┴────────────┴────────────┴────────────┴──────────────┤
│  DÒNG THỜI GIAN                                                   │
│  14:02:05  Chủ nhiệm    → Kiến trúc sư : Gửi brief                │
│  14:02:31  Kiến trúc sư → Họa viên     : 4 tầng, 14 phòng         │
│  14:03:10  Họa viên     → Kiểm định    : Mặt bằng nháp v1         │
│  14:03:22  Kiểm định    → Kiến trúc sư : ❌ Mật độ XD 100% > 90%   │
│  14:03:45  Kiến trúc sư → Họa viên     : Thêm sân sau 2m (v2)     │
├──────────────────────────────────────────────────────────────────┤
│  CHI TIẾT AGENT: Kiểm định viên                    [Đầu vào|Đầu ra]│
│  { "dat": false, "loi": [ { "muc": "Mật độ xây dựng", ... } ] }   │
└──────────────────────────────────────────────────────────────────┘
```

#### b) Các thành phần

**1. Thanh điều khiển tổng**
- **Tạm dừng / Tiếp tục:** dừng hệ thống sau khi agent hiện tại chạy xong; trạng thái được lưu lại để chạy tiếp.
- **Dừng:** hủy lượt thiết kế hiện tại.
- **Chế độ chạy:** *Tự động hoàn toàn* hoặc *Có duyệt thủ công* (xem thành phần 6 bên dưới).

**2. Thanh tiến trình tổng thể**
- Bước hiện tại trong luồng (x/5) và tên agent đang chạy.
- Số vòng sửa hiện tại / tối đa (ví dụ 2/3).
- Tổng thời gian chạy, tổng số token và chi phí API ước tính.

**3. Thẻ trạng thái của 5 agent**

| Trạng thái | Biểu tượng | Ý nghĩa |
|---|---|---|
| Chờ | ⏳ | Chưa đến lượt |
| Đang chạy | 🔄 | Agent đang xử lý |
| Xong | ✅ | Hoàn thành, đầu ra hợp lệ |
| Đang sửa | 🔁 | Chạy lại do nhận phản hồi lỗi |
| Lỗi | ❌ | Gặp lỗi (API, JSON sai định dạng…) |

Mỗi thẻ hiển thị: thời gian chạy, số lần chạy, số token, nút **[Xem]** (mở chi tiết) và nút **[↻]** (chạy lại riêng agent đó).

**4. Dòng thời gian (timeline)**
- Ghi lại mọi lần chuyển việc giữa các agent: thời điểm, agent gửi, agent nhận, nội dung tóm tắt.
- Các lần phản hồi lỗi được tô đỏ, giúp thấy rõ vòng lặp sửa lỗi.
- Có thể xuất timeline ra file để đưa vào báo cáo.

**5. Khung chi tiết agent**
- **Đầu vào:** dữ liệu agent nhận được (brief, danh sách phòng…).
- **Đầu ra:** kết quả agent trả về (JSON, mặt bằng nháp dạng ảnh, danh sách lỗi…).
- **Lịch sử phiên bản:** so sánh đầu ra giữa các vòng sửa (v1, v2, v3).
- **Prompt đã dùng** (dành cho nhóm phát triển khi gỡ lỗi).

**6. Duyệt thủ công (tùy chọn)**
Khi bật chế độ *Có duyệt thủ công*, hệ thống dừng ở 2 điểm để người dùng xác nhận:
- Sau khi **Kiến trúc sư** đề xuất phương án công năng.
- Sau khi **Kiểm định viên** cho kết quả đạt, trước khi lập dự toán.

Người dùng có thể **Đồng ý**, **Yêu cầu sửa** (nhập góp ý bằng chữ) hoặc **Dừng**.

#### c) Cách cài đặt

| Chức năng | Cách làm |
|---|---|
| Cập nhật trạng thái theo thời gian thực | `graph.stream(..., stream_mode="updates")` của LangGraph: mỗi khi một agent chạy xong, giao diện nhận sự kiện và cập nhật thẻ |
| Hiển thị | Streamlit: `st.columns` (5 thẻ), `st.progress`, `st.status`, `st.expander`, `st.json` |
| Tạm dừng / tiếp tục, chạy lại agent | *Checkpointer* của LangGraph (`MemorySaver` hoặc `SqliteSaver`) lưu trạng thái sau mỗi bước |
| Duyệt thủ công | Cơ chế `interrupt` của LangGraph, tiếp tục bằng lệnh `Command(resume=...)` |
| Đếm token, thời gian | Callback của LangChain ghi lại token và thời gian mỗi lần gọi LLM |
| Lưu nhật ký, timeline | Ghi vào trường `log` của trạng thái chung và file SQLite |
| Gỡ lỗi khi phát triển | LangGraph Studio hoặc LangSmith (chỉ dùng nội bộ nhóm) |

**Mô tả sự kiện gửi lên giao diện:**
```python
class AgentEvent(TypedDict):
    time: str          # "14:03:22"
    agent: str         # "reviewer"
    status: str        # "running" | "done" | "revising" | "error"
    to_agent: str      # Agent nhận việc tiếp theo
    summary: str       # "Mật độ XD 100% > 90%"
    tokens: int
    duration_s: float
    version: int       # Vòng sửa thứ mấy
```

### 5.2. Trang kết quả
- **3 tab:** Bản vẽ (xem trước PDF) | Mô tả dự án | Chi phí (bảng tóm tắt).
- **3 nút tải xuống:** `ban_ve.pdf` (+ DXF nén ZIP), `thuyet_minh.docx`, `du_toan.xlsx`.
- **Lịch sử thiết kế:** danh sách các lượt thiết kế trước, mở lại được kết quả và timeline.

---

## 6. Phân công nhiệm vụ

| Thành viên | Phụ trách chính | Phụ trách thêm |
|---|---|---|
| **A** | Agent 1 – Chủ nhiệm, file mô tả dự án, ghép luồng LangGraph | Trưởng nhóm, quản lý GitHub |
| **B** | Agent 2 – Kiến trúc sư | Thu thập mẫu nhà phố, tối ưu prompt |
| **C** | Agent 3 – Họa viên (phần khó nhất) | Thuật toán bố trí, khung tên bản vẽ |
| **D** | Agent 4 – Kiểm định viên | Xây dựng kho RAG quy chuẩn, phong thủy |
| **E** | Agent 5 – Kỹ sư dự toán | Bảng đơn giá, giao diện Streamlit + giao diện quản lý agent, slide |

> Giao Agent 3 cho thành viên lập trình tốt nhất. Giao diện quản lý agent: E làm phần hiển thị, A làm phần kết nối với LangGraph (stream, checkpointer, interrupt). Mỗi thành viên gửi sự kiện `AgentEvent` từ agent của mình theo đúng định dạng chung. Viết báo cáo: mỗi người viết phần agent của mình, A tổng hợp.

---

## 7. Kế hoạch thực hiện (8 tuần)

| Tuần | Công việc | Kết quả |
|---|---|---|
| 1 | Chốt phạm vi, định dạng JSON giữa các agent, định dạng `AgentEvent`, mẫu 3 sản phẩm đầu ra, tạo repo | Tài liệu giao tiếp + mẫu đầu ra |
| 2 | Thu thập dữ liệu: QCVN, tài liệu phong thủy, đơn giá, mẫu nhà phố | Thư mục `data/` hoàn chỉnh |
| 3 | Mỗi người làm phiên bản đầu của agent mình, chạy độc lập với dữ liệu giả | 5 agent chạy riêng lẻ |
| 4 | Hoàn thiện agent, viết test đơn vị | Agent ổn định |
| 5 | Agent 3 hoàn thiện mặt bằng + mặt đứng + mặt cắt; Agent 1, 5 hoàn thiện file DOCX, XLSX | 3 sản phẩm xuất được với dữ liệu mẫu |
| 6 | Ghép bằng LangGraph, 2 vòng lặp phản hồi, checkpointer; giao diện thiết kế + giao diện quản lý agent | Hệ thống chạy từ đầu đến cuối, theo dõi được từng agent |
| 7 (đầu tuần) | Hoàn thiện tạm dừng, chạy lại agent, duyệt thủ công | Bảng điều khiển agent đầy đủ |
| 7 | Chạy thử nghiệm, đo đạc, sửa lỗi | Bảng kết quả đánh giá |
| 8 | Viết báo cáo, slide, quay video demo | Nộp bài |

---

## 8. Cấu trúc thư mục dự án

```
ai-architect-studio/
├── data/
│   ├── quy_chuan/            # PDF QCVN, quy định địa phương
│   ├── phong_thuy/           # Tài liệu phong thủy
│   └── don_gia.xlsx          # Đơn giá tham khảo
├── agents/
│   ├── project_manager.py    # Agent 1
│   ├── architect.py          # Agent 2
│   ├── drafter.py            # Agent 3
│   ├── reviewer.py           # Agent 4
│   └── cost_estimator.py     # Agent 5
├── tools/
│   ├── layout_algorithm.py   # Thuật toán xếp phòng
│   ├── drawing_plan.py       # Vẽ mặt bằng
│   ├── drawing_elevation.py  # Vẽ mặt đứng, mặt cắt
│   ├── title_block.py        # Khung tên bản vẽ
│   ├── rag.py                # Tra cứu quy chuẩn
│   ├── docx_writer.py        # Xuất file mô tả dự án
│   └── xlsx_writer.py        # Xuất file chi phí
├── templates/                # Mẫu DOCX, XLSX, khung tên
├── graph.py                  # Luồng LangGraph
├── state.py                  # Định nghĩa DesignState, AgentEvent
├── app.py                    # Trang chính Streamlit
├── pages/
│   ├── 1_Thiet_ke.py         # Trang nhập yêu cầu
│   ├── 2_Quan_ly_agent.py    # Trang quản lý tiến trình agent
│   └── 3_Ket_qua.py          # Trang xem và tải kết quả
├── monitoring/
│   ├── events.py             # Gửi / nhận AgentEvent
│   ├── tracker.py            # Đếm token, thời gian
│   └── logs.db               # Lưu timeline (SQLite)
├── tests/
├── outputs/                  # ban_ve.pdf, *.dxf, thuyet_minh.docx, du_toan.xlsx
├── requirements.txt
└── README.md
```

---

## 9. Phương pháp đánh giá

### 9.1. Bộ dữ liệu thử nghiệm
Soạn **10–15 yêu cầu thiết kế** khác nhau về kích thước lô đất (4×15m, 5×20m, 6×25m…), số tầng, số phòng, ngân sách và hướng nhà.

### 9.2. Tiêu chí định lượng
| Tiêu chí | Cách đo |
|---|---|
| Tỉ lệ hoàn thành | % yêu cầu xuất đủ 3 sản phẩm |
| Tỉ lệ đạt quy chuẩn | % phương án đạt sau tối đa 3 vòng sửa |
| Số vòng sửa trung bình | Số lần quay lại Kiến trúc sư |
| Độ khớp yêu cầu | % yêu cầu người dùng được đáp ứng (số phòng, gara…) |
| Tính nhất quán | % số liệu khớp giữa bản vẽ – thuyết minh – file chi phí |
| Sai lệch chi phí | So với ngân sách; so với báo giá thị trường tham khảo |
| Thời gian xử lý | Giây từ lúc nhập đến lúc có đủ 3 file |
| Chi phí API | Số token / tiền cho mỗi lần thiết kế |

### 9.3. Đánh giá định tính
- Nhờ 2–3 người có chuyên môn (sinh viên/giảng viên kiến trúc, xây dựng) chấm điểm bản vẽ và thuyết minh theo thang 1–5.
- So sánh hệ thống **có** và **không có** vòng lặp phản hồi để chứng minh giá trị của multi-agent.

---

## 10. Rủi ro và giải pháp

| Rủi ro | Giải pháp |
|---|---|
| LLM trả về JSON sai định dạng | Pydantic structured output, tự động thử lại |
| Mặt bằng không hợp lý | Bắt đầu với nhà ống đơn giản; tăng dần độ phức tạp |
| Bản vẽ thiếu chi tiết (cửa, kích thước) | Làm thư viện ký hiệu dùng chung (cửa, cầu thang, thiết bị WC) |
| Số liệu giữa 3 file không khớp | Mọi file đọc từ cùng một trạng thái chung; có test kiểm tra |
| LLM tính toán sai | Mọi phép tính làm bằng Python / công thức Excel |
| Vòng lặp sửa không hội tụ | Giới hạn 3 vòng, ghi lỗi còn tồn tại vào thuyết minh |
| Hết hạn mức API miễn phí | Cache kết quả; dùng Ollama khi thử nghiệm |
| API lỗi khi thuyết trình | Quay sẵn video demo, chuẩn bị bộ kết quả mẫu |

---

## 11. Hướng phát triển
- Hỗ trợ lô đất hình dạng bất kỳ, biệt thự, nhà vườn.
- Bổ sung bản vẽ mặt bằng bố trí nội thất, mặt bằng điện nước.
- Cho người dùng chỉnh sửa trực tiếp mặt bằng, agent tự cập nhật thuyết minh và chi phí.
- Bổ sung mô hình 3D và ảnh phối cảnh.
- Xuất sang định dạng BIM (IFC) để mở trong Revit.

---

## 12. Cấu trúc báo cáo cuối kỳ
1. Mở đầu: bối cảnh, lý do chọn đề tài, mục tiêu, phạm vi.
2. Cơ sở lý thuyết: LLM, AI agent, hệ multi-agent, RAG, LangGraph, quy trình thiết kế kiến trúc sơ bộ.
3. Phân tích và thiết kế hệ thống: kiến trúc, luồng xử lý, mô tả 5 agent.
4. Cài đặt: công nghệ, thuật toán bố trí, xuất bản vẽ, xuất file DOCX/XLSX, giao diện.
5. Thử nghiệm và đánh giá: kết quả định lượng, định tính, so sánh.
6. Kết luận và hướng phát triển.
7. Tài liệu tham khảo và phụ lục (prompt, mã nguồn chính, bộ hồ sơ mẫu).
