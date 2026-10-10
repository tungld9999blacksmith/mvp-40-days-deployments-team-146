# Chốt đánh giá development và sửa offline — revision66

Ngày: 09/10/2026. Đã thực hiện đủ bốn việc trong lộ trình tiết kiệm: tổng hợp kết quả đã có, sửa RAG/evaluator, kiểm thử offline và ghi báo cáo sau sửa. **API mới: 0 lời gọi, 0 USD. Giữ Mistral Small 2603; không sửa `.env`, không dùng GPT-4o.** Bước5 development theo phạm vi đã duyệt đã hoàn tất; chưa nghiệm thu production.

## 1. Kết quả LLM cũ được chốt, không chấm lại

Nguồn kỹ thuật: [revision61](../agent_regression_resume_20261009_61/REPORT.md). Nhãn nội dung: [revision64](../agent_judge_resume_20261009_64/ASSESSMENT_NOTES.md). Đối soát: [revision65](../agent_judge_audit_20261009_65/REPORT.md). Các kết quả này được tạo trước sửa66; không dùng kiểm thử offline để tăng điểm LLM cũ.

| Kết quả lịch sử | Mistral Agent | Gemma Agent | Cách hiểu |
| --- | ---: | ---: | --- |
| Kỹ thuật, 30 câu ×3 | 90/90 PASS | 90/90 PASS | Regression development, chưa phải độ đúng nội dung |
| Booking kỹ thuật | 24/24 | 24/24 | Tool/state assertions trên sandbox |
| Reminder kỹ thuật | 15/15 | 15/15 | Tool/state assertions trên sandbox |
| Thời gian trung bình | 4,9115 giây | 8,3398 giây | Workload cũ, chưa đo lại sau sửa |
| p90 gộp ba lần | 10,9021 giây | 14,5153 giây | Cả hai vượt mục tiêu 8 giây |
| Receipt LLM full90 | 0,1016905065 USD | 0,0467101035 USD | Không cộng lại vào ledger55–64 |
| Nội dung repeat1, 30 đáp án/model | 23 PASS /3 FAIL /4 UNVERIFIABLE | 23 PASS /2 FAIL /5 UNVERIFIABLE | Nhãn tự động chưa hiệu chuẩn độc lập |

Tổng giữ nguyên **46 PASS /5 FAIL /9 UNVERIFIABLE** trên60 đáp án. Hai lượt còn lại/model chưa chấm nội dung:120 đáp án được tạm hoãn. Bộ30 đã dùng để sửa Agent là **development regression**, không phải holdout độc lập. Không cộng các lần chạy lịch sử thành một accuracy chung.

Đối soát65 đã kiểm tra14/14 mẫu bị đánh dấu:

- Ba FAIL booking (Mistral NEW-B01/NEW-B03, Gemma NEW-B03) khớp23 slot, từng giờ,4 chỗ/slot, ngày và xưởng của tool. Phản đối của judge bị đối chiếu này bác bỏ; không tự đổi verdict hoặc kết luận toàn bộ đáp án PASS.
- NEW-R02 của cả hai cấu hình bỏ sót ba bước trong cùng chunk đã gửi đầy đủ vào generation Mistral. Judge phát hiện ở Gemma nhưng bỏ qua omission trong các thành phần nội dung Mistral; chưa thể xếp hạng chất lượng Agent bằng chênh lệch nhãn.
- Mistral NEW-R05 giới hạn phát biểu trong các đoạn đã cung cấp, không đưa cam kết bảo hành cụ thể. Cần phân biệt lời giới hạn này với claim kỹ thuật cần citation; vẫn giữ FAIL cũ.
- Chín UNVERIFIABLE đều có fallback; chỉ hai NEW-R04 có `source_rule_verified=false` rõ ràng. Bảy trường xác minh vắng mặt không chứng minh nguồn đúng. Quy tắc coolant còn chưa xác minh hiệu lực và không được tự sửa số liệu nguồn.

**Quyết định model:** giữ `mistralai/mistral-small-2603` cho Agent, Rewrite và RAG generation. Gemma giảm54,07% receipt LLM trong full90 nhưng thời gian trung bình tăng khoảng1,70 lần; chưa có bằng chứng chất lượng độc lập đủ để thay baseline. Embedding giữ Gemini001, không gọi trong đợt66.

## 2. Sửa trên revision66

Runtime chỉ sửa `backend/src/agents/tools/RAG/query/generator.py`, thêm hai module `documented_procedure.py` và `answer_scope.py`; generator trước sửa được giữ nguyên trong [before_generator.py](before_generator.py).

**Quy trình tìm trạm sạc:** khi câu hỏi phù hợp và một đoạn hướng dẫn ứng dụng có chuỗi bước đánh số đầy đủ theo định dạng được kiểm tra, trả trực tiếp các bước từ đoạn đó, giữ dòng xuống hàng và citation. Không nối bước từ nhiều chunk hoặc bổ sung thao tác ngoài nguồn. Nguồn sai dòng xe/mục, bước thiếu, số thứ tự đứt, phần bị cắt và chỉ thị đáng ngờ không kích hoạt nhánh này. Câu hỏi ghép thêm giá/bảo hành/đặt lịch vẫn đi qua generation thông thường. Câu trả lời giữ cảnh báo chưa xác minh phiên bản/hiệu lực ứng dụng; kiểm tra định dạng không chứng nhận quy trình là đầy đủ ngoài đoạn nguồn.

**Citation và abstention:** claim không có citation hợp lệ bị thay bằng lời giới hạn thiếu bằng chứng kể cả khi model đã đặt fallback=true. Nội dung trước thay được giữ trong metadata, raw recording cũ không đổi. Lời giới hạn hẹp trong tập đoạn cung cấp không bị tự gán citation; nhận diện này là ứng viên abstention, không chứng minh việc từ chối trả lời đúng. Có citation cũng chưa chứng minh nguồn hỗ trợ mọi claim.

**Evaluator mới:** [offline_evaluator66.py](../../offline_evaluator66.py) xuất riêng answerability, source authority và nghĩa vụ citation; correctness, claim support và tính đúng của abstention ghi `NOT_EVALUATED`. Quy tắc nguồn không đồng nghĩa xác minh độc lập. Kiểm tra slot dùng phép đối chiếu count/time/remaining/ngày/xưởng; không để một phản đối đếm của judge thay thế dữ liệu tool. Không sửa runner/rubric đã đóng hoặc nhãn cũ; diagnostics không cấp verdict tổng thể mới.

## 3. Bằng chứng kiểm thử sau sửa — hoàn toàn offline

**256 kiểm thử PASS, 0 FAIL/ERROR/SKIP** trong [regression_suite_02.xml](regression_suite_02.xml), Ruff PASS. Trong256 có36 kiểm thử mới và220 kiểm thử sẵn có; các lượt28/248/12 trước đó có overlap, không cộng thành tổng số ca độc lập.

Phạm vi: quy trình/citation/phạm vi nguồn/abstention, intent RAG, booking follow-up, availability/capacity/quyền, proposal→confirm, không tạo booking sớm, giữ các trường reminder khi cập nhật một phần, business grounding, persistence sau mở lại engine SQLite và xác nhận lặp idempotent. Các controls evaluator có đáp án đúng và đáp án sai count, giờ trùng, slot không khả dụng, ngày, xưởng. Dùng LLM stub, SQLite cô lập và FakeRedis; plugin chặn kết nối mạng ngoài. Không chạy integration Postgres/Redis staging, Firebase/HTTP/UI hoặc gửi Resend thật.

[Replay](rag_recording_replays.json) thực thi generator mới trên12 ca RAG, dùng đúng `evidence_chunks` sau mở rộng hàng xóm và `query_analysis` cuối đã lưu, kèm vehicle context. Hai NEW-R02 trả đủ3 bước,1 citation, không cần gọi stub generation; hai NEW-R04 vẫn giữ gate nguồn coolant chưa xác minh. Tám ca còn lại dùng raw output LLM cũ qua provider giả lập, **không sinh câu trả lời LLM mới**. Mistral NEW-R05 vẫn giữ lời giới hạn và0 citation. Replay không đo retrieval hiện tại, chất lượng model sau sửa hoặc latency thật.

[Diagnostics60](saved_answer_diagnostics.json) giữ toàn bộ nhãn gốc; sáu ca liệt kê slot khớp tool trong phạm vi kiểm tra, gồm ba FAIL booking. Mẫu sample-005 được nhận diện là ứng viên lời giới hạn; không chuyển FAIL thành PASS. Replay lần đầu thất bại offline vì runner dùng ranked chunks trước mở rộng; đã sửa đầu vào replay và thêm hai kiểm thử khóa lỗi này. [Lỗi lần đầu](replay_attempt_01_error.json) được giữ, không có lời gọi API.

## 4. Chi phí, bảo toàn và phần tạm hoãn

| Phạm vi | Receipt đã biết |
| --- | ---: |
| Pipeline55–61, kể cả pilots/lượt dở | 0,25706310225 USD |
| Judge62–64, kể cả pilot lỗi | 0,20227562000 USD |
| Tổng55–64, tham chiếu một lần | **0,45933872225 USD** |
| Công việc66 | **0 USD API mới** |

[Ledger](all_attempts_cost.json) không cộng lại phí dữ liệu đã lưu.69 embedding calls cũ chưa định giá,1 receipt403 thiếu và phí request dở lúc dừng60 chưa biết vẫn chưa biết; không ghi thành0. Đây không phải hóa đơn toàn dự án; không tăng cap0,75 USD hoặc cấp ngân sách API mới.

Đối soát trước/sau bảo toàn **2.986 file lịch sử/dataset/test_agents**, các master64/65 và `.env`. Trong341 source đã đóng trước đó, **340 giữ nguyên, generator thay đổi có chủ đích**; source manifest mới và snapshot trước sửa ghi riêng. Không xóa/ghi đè golden, corpus, raw results, receipt hoặc test_agents. [Đối soát](after_preservation.json), [kiểm thử](offline_validation.json), [manifest nguồn mới](source_revision.json), [checkpoint](completion_checkpoint.json).

**Đã hoàn thành phạm vi bốn việc offline được duyệt.** Tạm hoãn220 câu +20 phiên, chấm120 đáp án, so sánh/lặp model, holdout độc lập, hiệu chuẩn judge/nguồn, staging/UI thật và nghiệm thu production. p90≤8s vẫn chưa đạt theo đo cũ. Khi có ngân sách có thể kiểm tra Mistral thật sau sửa theo phạm vi được duyệt riêng; không cần mở đợt đó để chốt báo cáo development này.
