# AI Architect Studio

Ứng dụng Python/Streamlit chuyển yêu cầu thiết kế nhà ở bằng tiếng Việt thành bản vẽ PDF/DXF, mô hình 3D GLB/DXF, thuyết minh DOCX và dự toán XLSX. Chín agent phối hợp qua LangGraph và dùng chung brief, chương trình phòng, hình học mặt bằng và bảng diện tích. [Kế hoạch đề tài ban đầu](docs/planqlda.md) mô tả mô hình 5 agent trước khi nâng cấp.

## Chạy trên Windows PowerShell

Dùng Python 3.11 và Streamlit 1.67 trở lên. Chạy từ thư mục gốc của dự án.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```
# chạy trên mac

cd ~/Downloads/AI-Architect-Studio_final
source .venv-mac/bin/activate
python -m streamlit run app.py


Mở [http://localhost:8501](http://localhost:8501). Thanh bên có năm mục **Dự án**, **Studio AI**, **Công việc & Hiệu suất**, **Kết quả** và **Cấu hình**. Dùng nút ở góc trên bên trái để mở thanh bên trên màn hình nhỏ.

Trong **Dự án**, xem số lượt đã lưu theo trạng thái, tiếp tục dự án gần nhất hoặc tìm trong danh sách có lọc và phân trang. Chọn **Tạo thiết kế mới**, mô tả yêu cầu bằng tiếng Việt và bổ sung các ô có cấu trúc nếu cần. Hai nguồn cùng xuất hiện phải khớp nhau. Xem bản tóm tắt và giả định tính cục bộ, rồi chọn **Bắt đầu thiết kế** và **Mở Studio AI**. Bản nháp được giữ khi chuyển trang trong phiên. **Tùy chọn nâng cao** áp dụng cho lượt đang soạn, còn **Cấu hình** đặt giá trị mặc định cho bản nháp mới.

Trong **Studio AI**, chọn dự án hoặc mở biểu mẫu yêu cầu mới. Thanh điều khiển hiển thị bước hiện tại, vòng sửa và thao tác theo trạng thái của lượt. **Văn phòng 3D** và **Luồng công việc** dùng cùng lượt và cùng bảng chi tiết agent. Mở **Nhật ký bàn giao** để lọc bàn giao, trả sửa hoặc chờ duyệt. **Dữ liệu kỹ thuật** chứa phiên bản, prompt, nhật ký và tệp tải. Tại điểm duyệt công năng, chọn phương án, chỉnh bảng phòng hoặc gửi góp ý.

Mở **Công việc & Hiệu suất** ở thanh bên. Tab **Công việc** lọc theo lượt thiết kế, agent và trạng thái. Bấm một dòng trong bảng (hoặc chọn công việc) rồi bấm **Mở chi tiết** hoặc **Đánh giá task**. Trong hộp thoại, ô **Chuyển công việc** đổi nhanh sang task của agent khác. Bấm **Mở chi tiết** để xem các lần thực hiện, đầu vào, đầu ra, thời gian xử lý, lý do chạy lại và quyết định nghiệm thu. Mỗi bước trong một lượt có một mã công việc ổn định và mỗi lần thực hiện có mã riêng.

Tab **Timeline** dùng chung bộ lọc lượt và agent. Chọn thanh để xem một lần thực hiện, chọn mốc để xem bàn giao, yêu cầu sửa hoặc mời duyệt. Dùng **Phóng to** rồi di chuyển khoảng xem hoặc chọn **Xem toàn bộ lượt chạy**. Khoảng xử lý và khoảng chờ duyệt được vẽ riêng. Sự kiện cũ chỉ có giờ trong ngày sẽ được báo thiếu mốc.

Trong hộp thoại chi tiết, mở **Đánh giá task** và chọn lần thực hiện. Khung 100 điểm gồm đáp ứng yêu cầu (40), chính xác và nhất quán (30), chất lượng chuyên môn do người dùng chấm (20), bàn giao (10). Bộ tiêu chí được lưu theo phiên bản lúc giao việc. Phép kiểm tự động đối chiếu dữ liệu đã lưu. Với tham chiếu tệp, điểm phản ánh thông tin trong manifest.

Mục thiếu dữ liệu được ghi **Chấm một phần** ở kết quả tổng, kèm số điểm đã đánh giá. Mục không áp dụng có lý do và được loại khỏi mẫu số. Điểm không quy đổi về 100. Nhập tên tự khai và bằng chứng để lưu điểm chuyên môn. Mỗi thay đổi có lịch sử riêng theo lần thực hiện. Các lần cũ chưa gắn bộ tiêu chí hiển thị thông báo.

Tab **Hiệu suất** mặc định xem dữ liệu thật và có biểu đồ phân bố trạng thái, số task theo ngày giao hoặc nghiệm thu. Lọc theo lượt, khoảng ngày giao lần đầu (gồm cả hai đầu kỳ) và agent. Mở **Tùy chỉnh báo cáo** để lọc nguồn, loại task và model. Với bộ lọc model, một task được chọn nếu có ít nhất một lần ghi model đó. Số liệu của task vẫn gồm tất cả lần thử và sửa. Bấm ô chỉ số trong bảng hoặc dùng mục **Task tạo nên chỉ số** để xem mẫu số, từng task và điểm lần đầu. Chọn agent trong văn phòng 3D rồi bấm **Mở hồ sơ hiệu suất** để mở bộ lọc tương ứng.

- **Tỷ lệ hoàn thành** là số task đã xử lý ít nhất một lần chia cho số task đã giao. **Đạt lần đầu** là số task được nghiệm thu ở lần số 1 chia cho cùng mẫu số.
- **Đã chấm đủ** đếm task có ít nhất một lần được chấm đủ theo bản đánh giá mới nhất của lần đó. **Điểm chất lượng TB** dùng lần cuối được nghiệm thu của mỗi task, hoặc với bước chạy tự động không có điểm duyệt là lần cuối đã xử lý, nếu lần đó đã chấm đủ. Bảng hiển thị trung bình điểm gốc và trung bình điểm tối đa của cùng mẫu.
- **Sửa do lỗi agent** chỉ đếm lần chạy lại có xác nhận kèm bằng chứng trong bản mới nhất ở **Đánh giá task**. Rút xác nhận sẽ cập nhật số liệu và giữ lịch sử.
- **Trung vị xử lý** và **trung vị chờ** có mẫu số riêng theo các lần có số đo. **Token** và **chi phí model** công bố phần đã ghi. **Chi phí/task nghiệm thu** dùng tổng chi phí mọi lần đã bắt đầu của nhóm task đã nghiệm thu, chia cho số task trong nhóm khi đủ số liệu.
- **Xuất CSV dữ liệu đang lọc** xuất một dòng mỗi lần thực hiện, với các cột số liệu và mã tham chiếu. Phần nhận xét, bằng chứng, prompt và đầu vào được giữ trong ứng dụng.

Để demo, mở **Hiệu suất → Tùy chỉnh báo cáo**, chọn nguồn **Mock kiểm thử** và khoảng **Tất cả thời gian**. Mẫu tháng 1/2025 của **Thiết kế công năng** có 3 task đã giao, 2 nghiệm thu, tỷ lệ đạt lần đầu 1/3, điểm trung bình 80/85 và chi phí 0,30 USD/task nghiệm thu (gồm dữ liệu ước tính). Nguồn demo có nhãn **Dữ liệu minh họa** và dùng mẫu cố định tại máy khi không có task mock đã lưu. Nguồn **Mô phỏng** hiển thị tình trạng riêng vì hoạt ảnh văn phòng 3D không ghi dữ liệu task vào SQLite.

Bảng ghi công việc thực thi từ backend vào SQLite `monitoring/logs.db`. Các lượt cũ vẫn có nhật ký bàn giao. Kịch bản mô phỏng 3D chạy trong trình duyệt và tách khỏi bảng công việc. Số lượt gọi phản ánh lời gọi model mà ứng dụng quan sát được. Chi phí được ghi khi model cung cấp giá trị hoặc khi có đơn giá `LLM_PRICE_PER_MTOK` để tính ước lượng từ token.

Trong **Kết quả**, chọn **Dự án** và **Phương án / phiên bản**. Tab **Bản vẽ** mở đầu tiên và cho chọn tờ, phóng to, kéo, vừa khung hoặc mở rộng. Tab **Mô hình 3D** cho xoay, ẩn/hiện từng tầng và cắt ngang ngôi nhà. Các tab **Thuyết minh**, **Dự toán** và **Kiểm định** hiển thị theo cùng phiên bản. Panel **Tải hồ sơ** bật nút PDF, ZIP DXF, GLB, DXF 3D, DOCX và XLSX theo tệp đã đối chiếu. Mở **So sánh các phương án hiện hành** để xem các phương án và những giả định đã lưu. Chọn phiên bản chỉ đổi nội dung đang xem. Dùng nút **Chọn phương án và tạo lại hồ sơ** khi muốn áp dụng phương án khả thi khác vào lượt có checkpoint. Thao tác này chạy lại các bước phụ thuộc và có thể dùng model đã cấu hình.

Trong **Cấu hình**, tab **Chế độ chạy** lưu tùy chọn duyệt, vòng sửa và phong thủy cho bản nháp mới trong phiên hiện tại. Danh sách bước duyệt chỉ chỉnh được ở chế độ **Chọn bước cần duyệt**. **Model & API** hiển thị trạng thái cấu hình tại máy. **Tài liệu tham chiếu** cho tìm, xem văn bản và tải tệp dữ liệu đang có. Việc bổ sung hoặc gỡ tài liệu thực hiện trong thư mục dữ liệu của máy chủ.

### Văn phòng 3D

Mở **Studio AI → Văn phòng 3D** để xem bảy khu làm việc của chín agent. Chọn nguồn **Dữ liệu thật** hoặc **Mô phỏng** trên thanh đầu trang. Kéo để xoay, cuộn để thu phóng, chọn tên khu để đổi nhanh góc nhìn hoặc chọn avatar để xem tác vụ, đầu vào, đầu ra và phản hồi. Khi vùng sa bàn có tiêu điểm, dùng các phím mũi tên, `+`, `-` và `Home` để điều khiển bằng bàn phím.

- **Dữ liệu thật** đọc trạng thái và timeline của lượt đã chọn. Agent gửi mang hồ sơ màu xanh hoặc hổ phách (trả sửa) qua cửa, trao tận tay người nhận rồi quay về bàn. Khi đang chờ duyệt, sự kiện nằm trong nhật ký và chưa chạy hoạt cảnh.
- **Mô phỏng** chạy một kịch bản trong trình duyệt và có thể tạm dừng hoặc chạy lại. Chế độ này dùng minh họa riêng và không gọi API.
- **Mô hình minh họa** xuất hiện khi chưa có hình học mặt bằng phù hợp. Khi có dữ liệu, bàn trung tâm dựng khối đúng tỷ lệ mặt bằng và cao độ các tầng của lượt đã chọn.
- **Giảm chuyển động** tạm giữ hoạt cảnh đang xem và dùng nhật ký cho các sự kiện mới. Đổi tab trong Studio hoặc ẩn cửa sổ tạm dừng cảnh đang chạy. **Danh sách** dùng chung phần chi tiết với sa bàn và tự xuất hiện nếu WebGL 2 gặp lỗi.
- **Hoạt động khi rảnh** cho phép tối đa hai avatar rời bàn cùng lúc. Avatar có thể đi dọc hành lang, đến **Góc nghỉ**, xem mô hình hoặc đứng gần đồng nghiệp. Khi tắt, avatar tìm đường về ghế. Chuyển động tạm ngừng khi bật giảm chuyển động hoặc ẩn tab, rồi tiếp tục từ vị trí đang đứng.

Avatar dùng vùng đi lại từ tường, cửa và nội thất trong sa bàn. Tuyến đi và vị trí trao được giữ khoảng trống. Mỗi agent thực hiện một lượt bàn giao tại một thời điểm. Bộ đếm và trạng thái xử lý cập nhật từ backend, độc lập với hoạt cảnh. Có thể chạy `node --test tests/studio_motion.test.mjs` để kiểm tra điều hướng, bàn giao và hàng đợi. `pytest` tự dùng thư mục tạm qua biến `ARCHITECT_STATE_DIR` nên không ghi lượt thử vào danh sách dự án.

Component Streamlit dùng [Three.js r181](https://github.com/mrdoob/three.js/tree/r181) đóng gói cục bộ theo [giấy phép MIT](studio3d/frontend/vendor/LICENSE). Không cần Node.js, CDN hoặc tệp mô hình bên ngoài khi chạy ứng dụng.

```powershell
.\.venv\Scripts\python.exe main.py --sample
.\.venv\Scripts\python.exe main.py --no-fengshui "Đất 4x15m ở Đà Nẵng, hướng Tây, 2 phòng ngủ, ngân sách 1,8 tỷ"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe evaluate.py --ablation
```

Trên macOS/Linux, dùng `python3 -m venv .venv` và thay `.\.venv\Scripts\python.exe` bằng `.venv/bin/python`. CLI trả mã `0` khi hoàn thành hồ sơ sơ bộ, `1` khi còn lỗi ngăn bàn giao và `2` khi cần bổ sung yêu cầu. Trạng thái xác minh quy chuẩn được báo riêng.

## Chín vai trò

| Agent | Đầu vào | Đầu ra và cách xử lý lỗi |
|---|---|---|
| Chủ nhiệm dự án (`project_manager`) | Yêu cầu, cấu hình lượt, phản hồi hoặc kết quả các bước | Mở lượt, giao việc, dùng chung bộ đếm vòng sửa, tổng hợp DOCX và hồ sơ nháp. Khi hết vòng sửa, giữ các vấn đề còn lại. |
| Phân tích yêu cầu (`requirements_analyst`) | Mô tả tiếng Việt | `Brief` Pydantic, giả định, câu hỏi và mâu thuẫn. Hỏi trước khi vẽ nếu thiếu kích thước hoặc yêu cầu xung đột. Số phòng ngủ và ngân sách có thể dùng giá trị tạm để lập phương án. |
| Kiến trúc sư ý tưởng (`concept_architect`) | Brief và phản hồi quy mô | Số tầng đề xuất, phong cách, vật liệu, giải pháp thông gió và chiếu sáng. Chuyển định hướng sang công năng để lập hoặc điều chỉnh chương trình phòng. |
| Thiết kế công năng (`architect`) | Brief, ý tưởng và phản hồi | Ba phương án A/B/C hoặc phương án đã chỉnh, tầng và danh mục phòng, diện tích mong muốn, kích thước tham chiếu, quan hệ kề và vị trí ưu tiên. |
| Triển khai bản vẽ (`drafter`) | Brief và chương trình phòng | Hình học, bảng diện tích thực tế, PDF/DXF và mô hình 3D đồng nguồn. Nếu không thể bố trí, gửi lỗi về công năng. |
| Kiểm định quy chuẩn (`reviewer`) | Brief, hình học và bảng diện tích | Kiểm tra hình học bằng Python, ngưỡng tham chiếu, nguồn, phạm vi và kết luận cho từng tiêu chí. Trả lỗi bố trí về công năng và lỗi quy mô về ý tưởng. |
| Tư vấn phong thủy (`fengshui_advisor`) | Hướng nhà, dữ liệu gia chủ và bố trí | Gợi ý Bát trạch và cách bố trí. Chỉ chạy khi bật và không ảnh hưởng kết luận quy chuẩn. |
| Dự toán chi phí (`cost_estimator`) | Bố trí của từng phương án, bảng diện tích và ngân sách | Tính chi phí từng phương án bằng Python trước khi vẽ. Xuất XLSX có công thức cho phương án chọn. Phản hồi khi chi phí vượt ngân sách đã nhập quá 10%. |
| Kiểm tra hồ sơ cuối (`final_reviewer`) | Brief, hình học, PDF, ZIP DXF, mô hình 3D, DOCX và XLSX | Kiểm tra số phòng, số tầng, diện tích, chi phí và công thức từ tệp thực. Sai lệch được chuyển về bước tạo dữ liệu sai. |

## Luồng và trạng thái

```text
Chủ nhiệm → Phân tích yêu cầu → Chủ nhiệm giao lập phương án
   → Ý tưởng → Công năng → So sánh hình học và chi phí → Bản vẽ
   → Phong thủy (nếu bật) → Kiểm định → Dự toán
   → Chủ nhiệm tổng hợp → Kiểm tra hồ sơ cuối → Xuất kết quả
   (Chưa đạt → Chủ nhiệm đề xuất điều chỉnh)
```

Khi lượt **Chưa đạt**, Chủ nhiệm tự thử các biến thể yêu cầu (số tầng, số phòng ngủ, phòng làm việc, gara, phòng thờ, ngân sách) bằng chính công cụ bố trí, kiểm tra và dự toán của các agent. Tối đa 3 đề xuất bố trí được và nằm trong ngân sách hiện ở Studio AI và Kết quả, ưu tiên ít thay đổi nhất. Nút **Thiết kế lại theo đề xuất** tạo lượt mới với yêu cầu đã điều chỉnh. Nếu không biến thể nào bố trí được, Chủ nhiệm nêu kích thước lô tối thiểu cần kiểm tra lại.

Mỗi phương án có mã và phiên bản. Công cụ bố trí và dự toán dùng chung để so sánh số tầng, công năng, diện tích và ngân sách. Đề xuất ưu tiên xét yêu cầu, tính khả thi hình học, chi phí và phần diện tích phụ thuộc vào giả định. Phương án có vi phạm đã xác minh hoặc lỗi hình học cần sửa trước khi chọn.

Chủ nhiệm điều phối tối đa **3 vòng sửa tự động** cho các lỗi thực sự cần điều chỉnh. Thiếu thông tin xác minh, thiếu nguồn hoặc chưa rõ phạm vi áp dụng xuất hiện ở danh sách cần xác minh. Phong thủy và kiểm định chạy tuần tự (phong thủy trước, kiểm định sau) để giữ các điểm duyệt riêng.

Ứng dụng hiển thị riêng trạng thái thực thi, kiểm tra kỹ thuật và xác minh quy chuẩn. Bộ hồ sơ nhất quán và còn thiếu căn cứ hiển thị **Đã tạo phương án sơ bộ — cần xác minh quy chuẩn**. Cảnh báo ngân sách được báo riêng. Vi phạm đã xác minh và lỗi kỹ thuật còn tồn tại sẽ ngăn bàn giao.

Kết quả lưu trong `outputs/<mã-lượt>/releases/`. Mỗi lần xuất lưu tệp, ảnh xem trước và trạng thái dùng để hiển thị đúng phiên bản. DOCX và trang `Gia_dinh` trong XLSX lưu giả định và tiêu chí còn thiếu căn cứ. Các hồ sơ cũ được tra từ bản lưu hoặc checkpoint còn gắn được với thư mục xuất. Ứng dụng báo khi thiếu dữ liệu đối chiếu hay thiếu tệp.

## Cấu hình

- Mặc định `LLM_PROVIDER=none`. Phân tích, phương án và nội dung dùng regex, thuật toán và mẫu. Đây là chế độ quy tắc; bộ kiểm thử sử dụng chế độ này hoặc mock có ghi nhãn, không gọi API thật.
- Để bật LLM, chép `.env.example` thành `.env`, cài gói LangChain tương ứng trong `requirements.txt`, rồi đặt `LLM_PROVIDER`, `LLM_MODEL` và biến khóa của nhà cung cấp. Hỗ trợ Gemini, OpenAI, Anthropic và Ollama. Biến theo agent có dạng `LLM_PROVIDER_CONCEPT_ARCHITECT` hoặc `LLM_MODEL_REQUIREMENTS_ANALYST`. Xem danh sách hậu tố trong `.env.example`. Các bước hình học, phong thủy, công thức và đối chiếu tệp dùng code.
- `MAX_ITERATIONS` đặt mặc định từ 0 đến 3. Có thể chọn giới hạn trong **Cấu hình → Chế độ chạy** hoặc trong biểu mẫu của từng lượt. **0** thực hiện kiểm tra ban đầu. Mỗi lần Chủ nhiệm giao trả sửa tính một vòng chung cho lỗi phương án, ngân sách hoặc sai lệch hồ sơ. **Studio AI → Lịch sử kiểm định và vòng sửa** hiển thị agent, lần chạy, phản hồi, thay đổi và kết quả dựa trên log của lượt. `BUDGET_TOLERANCE` là 10%. `USE_CHROMA=1` áp dụng cho tra cứu RAG tùy chọn.
- `data/don_gia.xlsx` chứa đơn giá giả định. `data/rules.json` và các bản tóm tắt là ngưỡng tham chiếu cho thiết kế sơ bộ. Với dữ liệu mẫu, báo cáo ghi **chưa đủ căn cứ**. Một đoạn RAG liên quan không xác nhận khả năng áp dụng.

### Bổ sung căn cứ cho lô đất

1. Xác nhận tỉnh/thành phố và thêm `mã lô đất: <mã>` vào yêu cầu hoặc điền **Mã lô đất** trong **Thông tin có cấu trúc**. Dùng cùng một mã trong hồ sơ xác minh. Địa chỉ, phường/xã, số tờ bản đồ và số thửa giúp xác định hồ sơ địa phương tương ứng.
2. Đặt các PDF có lớp văn bản trong `data/quy_chuan/`, gồm hồ sơ quy hoạch hoặc văn bản áp dụng đúng lô và văn bản quy chuẩn/tiêu chuẩn được viện dẫn. PDF scan cần có lớp văn bản để trích xuất. Bản .md/.txt hoặc kết quả BM25 chỉ là tài liệu tra cứu. Bộ tra cứu của agent lọc theo tiền tố `qcvn_01` hoặc `tcvn_4451`. Bộ xác minh đọc trực tiếp PDF có tên đã ghi trong JSON.
3. Người đối chiếu xác nhận văn bản, phạm vi, ngưỡng và cách đo cho từng tiêu chí trước khi thêm bản ghi vào mảng JSON UTF-8 `data/quy_chuan/can_cu_da_xac_minh.json`. Mỗi bản ghi có `tinh`, `ma_lo_dat`, `muc`, `nguong`, `nguon`, `pham_vi`, `tai_lieu` (tên PDF), `trang` (số thứ tự trang vật lý, từ 1) và `trich` (đoạn nguyên văn trên trang đó). Chép `muc` và `nguong` từ **Kết quả → Kiểm định → Chi tiết tiêu chí** của phiên bản hiện hành, sau khi kiểm tra chúng phù hợp với nguồn. Nếu chỉ tiêu hoặc cách đo khác phép kiểm hiện tại, cần cập nhật và kiểm chứng phép kiểm đó. Sửa chữ trong JSON không thay đổi công thức.
4. Với lượt đã có đúng định danh lô đất và checkpoint, dùng **Kết quả → Kiểm định → Kiểm định lại sau khi bổ sung nguồn** để đối chiếu lại mặt bằng hiện hành. Nếu brief thiếu định danh, bổ sung vào yêu cầu thiết kế trước. Bước xác minh đọc lại JSON và PDF mỗi lần chạy. Kết quả đã lưu giữ kết luận của lần kiểm định trước. Bảng tiêu chí ghi dữ liệu thiếu và cách bổ sung khi thiếu mã lô, sai ngưỡng, thiếu PDF, sai trang hoặc trích dẫn không khớp.

Mức 1–5 tầng là phạm vi phần mềm. Phép kiểm chiếu sáng hiện dùng tiếp giáp mặt thoáng theo hình học sơ bộ. Khi hồ sơ địa phương hoặc văn bản yêu cầu dữ liệu hay cách đo khác, mục đó cần đối chiếu riêng trước khi xác minh.

Mô hình bố trí hiện dành cho nhà ống trên lô chữ nhật, 1–5 tầng, ở mức thiết kế sơ bộ. Phạm vi chưa gồm kết cấu, hồ sơ thi công hoặc thẩm tra chuyên ngành. Công suất bố trí phụ thuộc kích thước lô và chương trình phòng.
