# Báo cáo đánh giá EV Care Agent và RAG

**Ngày chốt: 09/10/2026 — phạm vi: đánh giá development, hồi quy sau sửa và kiểm tra tích hợp.**

Báo cáo này tổng hợp hệ thống, bộ kiểm thử, phương pháp đánh giá, kết quả đã chạy, lựa chọn model, chi phí và hướng phát triển để mentor hoặc thành viên team đọc độc lập. Các đường dẫn evidence phục vụ đối chiếu chi tiết; không cần đọc bản plan để nắm tình hình.

**Kết luận:** giữ **Mistral Small 2603** cho Agent, Rewrite và RAG generation. Đã chạy đủ **30 câu ×3 lần/model** cho hai cấu hình Mistral/Gemma, chấm nội dung **60 đáp án** và đối soát **14 mẫu bị đánh dấu**. Sau sửa RAG/evaluator, bộ hồi quy offline đạt **256/256 PASS**, phát lại12 ca RAG từ dữ liệu đã lưu và bổ sung kiểm tra tích hợp PostgreSQL/Redis/HTTP/UI ở đợt67. **Phạm vi chốt hiện tại là đánh giá development.** Lộ trình kiểm chứng nội dung/nguồn, đánh giá độc lập, tối ưu độ trễ và nghiệm thu production được trình bày tại mục9.

### Kiểm thử tích hợp và smoke Mistral sau sửa

Sau sửa Agent/RAG, hai đợt kiểm tra tiếp theo gồm tích hợp ứng dụng và smoke Mistral. Kiểm thử tích hợp dùng dữ liệu tổng hợp, dịch vụ riêng và email giả lập; kết quả được báo riêng với chất lượng câu trả lời của LLM.

| Phạm vi mới | Kết quả | Phạm vi kiểm thử |
| --- | --- | --- |
| Persistence PostgreSQL/Redis thật | **1/1 PASS** | Mở lại kết nối, proposal còn tồn tại; confirm lặp tạo đúng một booking; schema/namespace riêng |
| HTTP nghiệp vụ, Firebase thật | **17/17 PASS** | Backend `src.main:app`, PostgreSQL đã migration, Redis thật; token Firebase custom của hai tài khoản tổng hợp. Chặn người dùng khác; proposal chưa tạo booking; giữ trường reminder; confirm đồng thời/replay; recheck chỗ cuối trả409 |
| Chrome và frontend/backend thật | **4/4 PASS với Firebase Auth Emulator** | Đăng nhập fixture Google; lưu reminder qua reload; xác nhận booking và giữ thẻ sau reload; chat HTTP với LLM stub. Không mock API trong trình duyệt, không bypass backend auth |
| Hồi quy HTTP/email/reminder/booking | **121/121 PASS** | SQLite/FakeRedis, auth/transport giả lập; có webhook và retry |
| Kiểm tra runner hạn mức | **8/8 PASS** | Chặn vượt reserve chung Agent/Generation, dừng khi thiếu receipt hoặc lỗi; không tính là chất lượng Agent |
| Smoke Mistral12 câu×1 | **1 API_ERROR,11 NOT_RUN — chờ chạy tiếp** | Agent request đầu tiên của NEW-R02 trả429 `upstream_provider_shared_pool` từ Mistral;0 đáp án mới,0 request Generation |

**Kết quả UI thuộc phạm vi Auth Emulator/LLM stub; Google OAuth thật là bước kiểm tra tiếp theo tại mục9.** HTTP nghiệp vụ dùng Firebase thật với custom token; backend giữ quy tắc chỉ nhận Google ở luồng đăng nhập ứng dụng. Database kiểm thử cuối lượt có **một booking CONFIRMED và bốn checkpoint** của graph main. Chi tiết từng lần kiểm thử được lưu trong báo cáo tích hợp.

Đợt2 khóa trước12 câu đã từng dùng development:6 RAG,2 booking,2 reminder,2 guardrail. Thiết kế dùng Mistral thật cho Agent/Generation khi runtime cho phép; dùng evidence sau mở rộng hàng xóm và QueryAnalysis/Rewrite đã lưu, không đo retrieval live. Dừng ngay lỗi API đầu, không retry ngầm, không judge/embedding/Qdrant, không đổi model. **Receipt LLM mới đã biết:0 USD;1 receipt429 chờ đối soát nên tổng phí mới vẫn để mở**, không khẳng định lời gọi lỗi miễn phí. Ngưỡng dừng theo receipt0,04 USD và reserve0,004 USD/request là kiểm soát runner, không phải mức trần thanh toán được bảo đảm.

Nguồn: [kết quả kiểm thử tích hợp và smoke](../eval/results/agent_stage12_validation_20261009_67/REPORT.md). Trình tự tiếp tục smoke và mở rộng đánh giá theo ngân sách được tập trung tại mục9.

## 1. Hệ thống và mục tiêu đánh giá

EV Care hỗ trợ chủ xe điện tra cứu bảo dưỡng, chi phí, bảo hành, tìm xưởng, chọn lịch và quản lý nhắc bảo dưỡng. Agent quyết định gọi tool; các service backend thực hiện nghiệp vụ và kiểm tra quyền, điều kiện đặt lịch, hiệu lực đề xuất và idempotency. Đề xuất lịch chỉ tạo thẻ; booking được tạo khi người dùng xác nhận qua backend.

Danh mục Agent hiện có **9 tools**:

| Tool | Vai trò |
| --- | --- |
| `get_due_maintenance` | Kiểm tra bảo dưỡng đến hạn theo xe và dữ liệu sử dụng |
| `estimate_service_cost` | Tra cứu/ước tính chi phí dịch vụ theo dữ liệu nghiệp vụ |
| `find_workshops` | Tìm xưởng phù hợp |
| `get_available_slots` | Tra cứu giờ còn chỗ của xưởng theo ngày |
| `propose_booking` | Tạo đề xuất đặt lịch để người dùng xác nhận |
| `get_reminder_settings` | Đọc cấu hình nhắc bảo dưỡng |
| `update_reminder_settings` | Cập nhật các trường nhắc bảo dưỡng được yêu cầu |
| `get_reminder_context` | Lấy ngữ cảnh liên quan nhắc bảo dưỡng |
| `search_ev_knowledge` | Truy xuất tài liệu và trả lời có evidence/citation |

Mục tiêu đánh giá gồm: chọn tool và đối số đúng; giữ trạng thái hội thoại; không tạo booking trước xác nhận; cập nhật reminder đúng phạm vi; trả lời RAG bám nguồn; cân đối chất lượng, độ trễ và phí LLM.

Các cấu hình được giữ sau đánh giá:

| Thành phần | Model/trạng thái | Lý do |
| --- | --- | --- |
| Agent | `mistralai/mistral-small-2603` | Baseline phù hợp hơn về tốc độ trong các đối chứng đã chạy |
| Rewrite | `mistralai/mistral-small-2603` | Gemma tiết kiệm rất ít phí nhưng chậm hơn rõ rệt |
| RAG generation | `mistralai/mistral-small-2603` | Nhanh hơn Gemma trong đối chứng cùng evidence |
| Embedding | `models/gemini-embedding-001`, 3.072 chiều | Chuyển query/tài liệu thành vector cho retrieval; không phải model chấm đáp án |
| Judge tự động | `google/gemini-3.5-flash-lite` qua OpenRouter | Chấm các đáp án đã lưu theo rubric; hiệu chuẩn độc lập nằm trong hướng phát triển |
| Write reviewer | Inactive | Không dùng GPT-4o; backend thực thi và kiểm soát nghiệp vụ ghi |

Đây là cấu hình dùng trong đánh giá và quyết định giữ baseline. Đánh giá dùng môi trường kiểm thử riêng; kiểm soát thao tác ghi thuộc các service backend.

## 2. Bộ kiểm thử và phương pháp

### Các bộ kiểm thử

| Tập dữ liệu | Phạm vi | Giá trị và giới hạn |
| --- | --- | --- |
| Benchmark10 model ngày05/10 | 30 case/model;6 tool schemas và tool fixture | So sánh ban đầu theo rubric cũ; khác runtime9 tools hiện tại |
| Golden RAG lịch sử | 100 câu | Giữ nguyên; dùng đo document retrieval theo golden draft |
| Development v2/v2.1 | 220 câu đơn và20 phiên trong thiết kế đánh giá | v2.1 điều chỉnh tiêu chí/state nghiệp vụ;100 câu RAG giữ nguyên câu hỏi và thứ tự của golden cũ; không phải holdout mới |
| Bộ30 ứng viên dùng ở bước5 | 6 RAG,5 guardrail,8 booking,6 bảo dưỡng/chi phí,5 reminder | Do AI tạo; đã dùng để sửa Agent nên được coi là **development regression** |

Tạo bộ30 nhằm có phạm vi nhỏ, khóa câu hỏi/tiêu chí để chạy so sánh lặp trong ngân sách team. Bộ này bổ sung cho golden cũ, không thay thế hoặc chứng nhận tính độc lập của golden. Không đổi tên bộ đã dùng sửa Agent thành holdout.

### Ba loại bằng chứng

1. **Kỹ thuật/nghiệp vụ:** kiểm tra tool, arguments, sequence, state và side effects. Khi chạy pipeline, retrieval dùng Qdrant/BM25/FlashRank/Gemini thật; nghiệp vụ dùng service trên SQLite/FakeRedis cô lập. PASS kỹ thuật không đồng nghĩa đáp án đúng về nội dung.
2. **Chấm nội dung tự động:** judge nhận câu hỏi, đáp án, tool results và evidence đã lưu; kiểm tra từng component/claim/citation. Runner kiểm schema/provenance và tổng hợp nhãn. Đây là nhãn tự động theo rubric; bước hiệu chuẩn độc lập được đặt trong hướng phát triển ở mục9.
3. **Kiểm thử offline sau sửa:** dùng evidence/raw generation đã lưu và LLM stub; chặn mạng ngoài. Kiểm tra logic code mới, không đo chất lượng model hoặc retrieval live trên revision mới.

Nhãn **PASS** là đạt theo scorer ở đúng phạm vi của lượt đó; **FAIL** là nhãn bất lợi được giữ để phân tích; **UNVERIFIABLE** là chưa đủ căn cứ xác minh, không tính thành PASS. ERROR provider/schema và lượt chưa hoàn tất được giữ riêng. Không cộng pilot, ca trùng hoặc run dở thành một full run đạt yêu cầu; không cộng các dataset/revision khác nhau thành accuracy chung.

## 3. Kết quả với LLM thật trước sửa66

### Kỹ thuật:30 câu ×3 lần cho mỗi cấu hình

Cấu hình đối chứng chỉ thay **Agent Mistral/Gemma**; Rewrite và RAG generation đều dùng Mistral. Agent có thể đổi query/evidence/số tool calls, nên đây là so sánh cấu hình toàn pipeline, không phải so sánh model generation với đầu vào cố định.

| Chỉ số | Mistral Agent | Gemma Agent |
| --- | ---: | ---: |
| Lượt kỹ thuật PASS | **90/90** | **90/90** |
| Booking kỹ thuật | 24/24 | 24/24 |
| Reminder kỹ thuật | 15/15 | 15/15 |
| Thời gian tác vụ trung bình | **4,9115 giây** | 8,3398 giây |
| p90 gộp ba lần | 10,9021 giây | 14,5153 giây |
| Receipt LLM cho ba full run | 0,1016905065 USD | **0,0467101035 USD** |

Sáu full run không ghi nhận safety/raw-argument/provider/retrieval errors hoặc receipt LLM thiếu theo detector/scorer của lượt chạy. **90 quan sát/model là30 câu lặp3 lần, không phải90 câu độc lập.** Gemma giảm54,07% receipt LLM nhưng thời gian trung bình tăng khoảng1,70 lần. Từ p90 đo được10,9021/14,5153 giây, hướng tối ưu tiếp theo đặt mục tiêu≤8 giây ở mục9. Nguồn: [technical comparison](../eval/results/agent_regression_resume_20261009_61/technical_comparison.json), [báo cáo kỹ thuật](../eval/results/agent_regression_resume_20261009_61/TECHNICAL_REPORT.md).

### Chấm nội dung:60 đáp án repeat1

Theo lựa chọn tiết kiệm, chấm nguyên30 đáp án repeat1/model, không chọn riêng câu thuận lợi. Sau lỗi403 do key limit,25 nhãn hợp lệ được giữ và chỉ chấm tiếp35 mẫu còn thiếu. Lỗi cũ vẫn còn trong artifact; không gọi/tính phí lại pilot hoặc25 nhãn tái sử dụng.

| Agent tạo đáp án | Đã chấm | PASS | FAIL | UNVERIFIABLE |
| --- | ---: | ---: | ---: | ---: |
| Mistral | 30 | 23 | 3 | 4 |
| Gemma | 30 | 23 | 2 | 5 |
| **Tổng** | **60** | **46** | **5** | **9** |

Phạm vi hiện tại gồm technical×3/model và chấm nội dung repeat1, tức60 đáp án. **120 đáp án ở các lượt lặp còn lại** được giữ cho phương án mở rộng đánh giá theo ngân sách tại mục9. Kết quả trên được dùng để so sánh development; quyết định giữ Mistral dựa thêm vào độ trễ và chi phí. Nguồn: [kết quả chấm](../eval/results/agent_judge_resume_20261009_64/result.json), [nhận xét](../eval/results/agent_judge_resume_20261009_64/ASSESSMENT_NOTES.md).

## 4. Đối soát lỗi và thay đổi sau đánh giá

Đã đối soát đủ **14/14 mẫu FAIL/UNVERIFIABLE** bằng trace/tool/evidence/request generation, không gọi judge mới và không sửa nhãn gốc.

| Vấn đề | Bằng chứng và nhận xét | Xử lý/giới hạn |
| --- | --- | --- |
| Ba FAIL booking: Mistral NEW-B01/NEW-B03, Gemma NEW-B03 | Đáp án khớp23 slot00:00–22:00,4 chỗ/slot, đúng ngày và xưởng; judge phản đối sai số lượng | Dùng code đối chiếu count/time/remaining/ngày/xưởng. Không đổi FAIL thành PASS hoặc chứng nhận toàn bộ đáp án |
| NEW-R02 ở cả hai cấu hình | Cùng chunk có đủ3 bước tìm trạm sạc và đã gửi đầy đủ vào generation Mistral, nhưng đáp án bỏ sót; judge phát hiện ở Gemma và bỏ qua omission trong các component nội dung Mistral | Sửa generator để trả các bước trực tiếp từ một đoạn phù hợp, giữ citation; không ghép bước từ nguồn khác |
| Mistral NEW-R05 | Đáp án giới hạn thiếu bằng chứng trong các đoạn cung cấp, không đưa cam kết bảo hành cụ thể; judge yêu cầu citation như một factual claim | Phân biệt abstention hẹp với claim kỹ thuật/phủ định toàn bộ tài liệu. Không tự cấp nhãn PASS cho abstention |
| Chín UNVERIFIABLE | Tất cả có fallback=true; chỉ hai NEW-R04 có source_rule_verified=false rõ ràng; bảy mẫu thiếu trường này | Evaluator mới tách answerability khỏi source authority. Trường xác minh vắng mặt không chứng minh nguồn đúng |
| Nguồn coolant đáng ngờ | Dòng nguồn có mốc12.000km; hệ thống giữ cảnh báo về giá trị và hiệu lực nguồn | Giữ nguyên số liệu gốc; đưa việc xác nhận tài liệu/phạm vi/phiên bản vào mục9 |

Nguồn: [đối soát14 mẫu](../eval/results/agent_judge_audit_20261009_65/audit.json).

### Sửa trên revision66 và kiểm thử offline

- **Quy trình tìm trạm sạc:** nhánh trả lời trực tiếp chỉ kích hoạt khi query phù hợp và một đoạn nguồn có chuỗi bước đánh số qua các kiểm tra định dạng/phạm vi. Giữ nội dung xuống hàng, citation và cảnh báo chưa xác minh phiên bản/hiệu lực ứng dụng. Các ca thiếu/cắt bước, sai mục/dòng xe, số thứ tự đứt hoặc chỉ thị đáng ngờ không kích hoạt nhánh này. Câu hỏi ghép giá/bảo hành/đặt lịch vẫn qua generation thông thường.
- **Citation:** claim không có citation hợp lệ bị thay bằng lời giới hạn thiếu bằng chứng kể cả khi model đặt fallback=true. Nội dung trước thay được lưu trong metadata; raw output cũ giữ nguyên. Citation tồn tại không chứng minh claim được nguồn hỗ trợ.
- **Abstention và nguồn:** evaluator phân loại lời giới hạn hẹp và báo riêng answerability, source authority, nghĩa vụ citation. Kiểm chứng correctness, claim support và tính đúng của abstention được đặt trong hướng phát triển ở mục9; kết quả phân loại không thay cho kiểm chứng nội dung.
- **Booking/reminder đã sửa trước đó:** cập nhật reminder chỉ đổi trường được yêu cầu, giữ công tắc tổng/Email/số ngày khi thích hợp; booking phân biệt yêu cầu tạo proposal với xác nhận hoặc hỏi trạng thái thẻ. Các sửa này là một phần runtime đạt technical×3 ở trên.

| Bằng chứng sau sửa66 | Kết quả | Cách hiểu |
| --- | --- | --- |
| Hồi quy offline | **256/256 PASS**,0 FAIL/ERROR/SKIP; Ruff PASS | 36 kiểm thử mới và220 có sẵn; không cộng các lượt kiểm thử overlap |
| Phát lại RAG từ dữ liệu đã lưu | 12 ca | Generator mới nhận evidence sau neighbor expansion và query analysis cuối đã lưu |
| Hai ca NEW-R02 | Mỗi ca trả đủ3 bước,1 citation | Sửa được omission trên fixture replay |
| Hai ca NEW-R04 | Giữ gate/cảnh báo coolant chưa xác minh | Không hạ điều kiện nguồn để tăng điểm |
| Tám ca RAG còn lại | Dùng raw generation cũ qua provider giả lập | Không gọi model/embedding/Qdrant |
| Diagnostics trên60 đáp án cũ | Giữ toàn bộ46/5/9 nhãn; sáu ca liệt kê slot khớp tool, gồm ba FAIL booking | Không cấp verdict tổng thể mới |
| API phát sinh sau sửa và khi tổng hợp | **0 lời gọi,0 USD** | Không đo lại latency hoặc chất lượng LLM thật |

Suite offline66 bao phủ RAG intent/evidence/citation, business grounding, booking follow-up, quyền/capacity, proposal→confirm, không tạo booking sớm, cập nhật reminder một phần, persistence sau mở lại engine SQLite và confirm lặp idempotent. Dùng SQLite cô lập/FakeRedis/LLM stub, chặn mạng ngoài. Đợt67 bổ sung PostgreSQL/Redis thật, HTTP với Firebase thật và UI với Auth Emulator trên code ứng dụng66; kết quả được báo riêng ở đầu tài liệu.

Lỗi replay đầu tiên do runner lấy ranked chunks trước mở rộng hàng xóm được lưu, sửa đầu vào và thêm hai kiểm thử. Các lần kiểm thử trước có overlap không cộng vào256. Nguồn: [báo cáo sau sửa](../eval/results/agent_offline_revision_20261009_66/REPORT.md), [JUnit](../eval/results/agent_offline_revision_20261009_66/regression_suite_02.xml), [replay12](../eval/results/agent_offline_revision_20261009_66/rag_recording_replays.json), [diagnostics60](../eval/results/agent_offline_revision_20261009_66/saved_answer_diagnostics.json).

## 5. Retrieval, Rewrite và generation

### Retrieval với golden100 câu

Full RAG Mistral hoàn tất **100/100 câu,0 lỗi**. Document Hit@1 **76%**, Hit@3 **97%**, Hit@5 **98%**, MRR **0,8592**. Đây là document hits theo golden draft. Hướng phát triển bổ sung golden chunk IDs để đo evidence-chunk recall ở mục9. **Hit@5=98% không đồng nghĩa98% đáp án đúng.** Nguồn: [full RAG100](../eval/results/rag_v2_full_100_mistral_routed_20261007_01/report.md).

### Rewrite: cùng30 query/model

Cả ba model đạt **30/30 JSON thuần và trường đầu vào khớp**,0 lỗi API/retrieval; Document Hit@5 **23/24** trên phần golden draft.

| Rewrite | Thời gian provider TB | Receipt30 query |
| --- | ---: | ---: |
| Mistral | **1,127 giây** | 0,003173066 USD |
| Gemma | 4,039 giây | **0,003073576 USD** |
| Gemini Flash Lite | 1,353 giây | 0,016533600 USD |

Gemma tiết kiệm3,14% phí nhưng chậm3,58 lần; Gemini Flash Lite tốn5,21 lần Mistral theo workload này. **Giữ Mistral Rewrite.** Nguồn: [CSV](../eval/results/step4_rewrite_contract_completion_20261008_22/stage_comparison.csv), [nhận xét Rewrite](../eval/results/step4_rewrite_contract_completion_20261008_22/NHAN_XET_REWRITE.md).

### Generation: cùng30 query và evidence

Mỗi model đạt **30/30 kỹ thuật**, gồm **25/25 model responses JSON thuần** và5 ca runtime trả trước provider. Không tính5 ca này là model tự trả lời đúng.

| Generation | Thời gian provider TB | Receipt full |
| --- | ---: | ---: |
| Mistral | **1,870 giây** | 0,013030908 USD |
| Gemma | 3,992 giây | **0,010831068 USD** |

Gemma tiết kiệm16,88% phí nhưng chậm2,13 lần. **Giữ Mistral generation.** Đối chứng này đo kỹ thuật/cost/latency; kiểm chứng chất lượng nội dung nằm trong lộ trình mục9. Nguồn: [CSV](../eval/results/step4_generation_completion_20261008_24/stage_comparison.csv), [nhận xét generation](../eval/results/step4_generation_completion_20261008_24/NHAN_XET_GENERATION.md).

## 6. Benchmark10 model ban đầu

Benchmark05/10 chạy đủ30 case/model trên cùng prompt,6 tool schemas, dataset và tool outputs fixture. Final là điểm tổng hợp của rubric cũ, có Answer Quality heuristic; **không phải tỷ lệ đáp án đúng** và không xếp hạng chung với đánh giá9 tools hiện tại. Eligible là theo rubric MVP cũ, không chứng nhận production readiness.

| Model | Final cũ | TB/P95 giây | Receipt30 case | Eligible MVP cũ |
| --- | ---: | ---: | ---: | --- |
| `mistralai/mistral-small-2603` | **93,25** | 5,452/9,119 | 0,02368239 USD | Có |
| `google/gemma-4-26b-a4b-it` | 91,36 | 11,257/19,422 | 0,01368375 USD | Có |
| `openai/gpt-4o` | 89,81 | 6,104/10,895 | 0,47800000 USD | Có |
| `google/gemini-3.5-flash-lite` | 82,95 | 4,009/5,798 | 0,09495675 USD | Không |
| `qwen/qwen3.8-27b` | 79,76 | 10,658/16,988 | 0,10159134 USD | Không |
| `qwen/qwen3.7-flash` | 77,46 | 12,522/21,016 | **0,01017323 USD** | Không |
| `openai/gpt-5-mini` | 73,92 | 14,991/23,731 | 0,06666960 USD | Không |
| `deepseek/deepseek-v4-flash` | 71,65 | 5,792/10,238 | 0,05129958 USD | Không |
| `anthropic/claude-haiku-4.5` | 69,19 | 7,533/10,953 | 0,58853200 USD | Không |
| `google/gemini-3.5-flash` | 64,40 | 11,728/15,571 | 0,77794290 USD | Không |

Cả10 hoàn tất30/30; tổng receipt benchmark cũ **2,20653154 USD**. Mistral có Final cao nhất trong rubric này; Gemma rẻ hơn nhưng chậm. Các endpoint rẻ khác không đạt điều kiện rubric cũ, nên quyết định baseline dựa trên cả kết quả và chi phí. Nguồn: [benchmark gốc](../backend/tests/test_agents/evaluationLLM/results/benchmark_report.md).

Lượt Agent GPT-4o sau đó phủ30 ID PASS qua hai run, receipt **0,479205 USD**, khoảng16,4 lần Mistral Agent30 trong đối chứng đó. Không phải một full run hoàn chỉnh hoặc chứng minh chất lượng độc lập cao hơn. **GPT-4o đã bị loại khỏi các lượt đánh giá tiếp theo để phù hợp ngân sách**; bảng trên chỉ giữ lịch sử. [Báo cáo GPT-4o lịch sử](../eval/results/step4_agent_gpt4o_followup_20261008_15/report.md).

## 7. Các kết quả lịch sử có giá trị

Những kết quả dưới đây thuộc dataset/runtime/scorer khác nhau; giữ làm bằng chứng tiến triển, không cộng thành accuracy hiện tại.

| Phần | Kết quả | Giới hạn/bằng chứng |
| --- | --- | --- |
| Booking trước/sau ban đầu | Cùng10 câu: **6/10→10/10**; lượt50 câu sau sửa **49/50** | [Đối chứng](../eval/results/implementation_20261007_122213_010409/report.md); khác contracts benchmark ban đầu |
| Booking grounding | **150/150** kiểm tra runtime trên50 câu×3;0 provider errors | Runtime dựng lại36/150 đáp án, còn9 raw argument format errors; [báo cáo](../eval/results/booking_grounding_mistral_20261008_04/report.md) |
| Chuẩn hóa giờ proposal | **54/54** trên18 câu×3;0 raw argument errors | Runtime vẫn chặn/bổ sung prerequisites; [báo cáo](../eval/results/booking_time_mistral_20261008_11/report.md) |
| Bảo dưỡng/chi phí | **89/90** trên30 câu×3 | Một lỗi UUID COST-03; render từ tool là một phần runtime; [báo cáo](../eval/results/business_grounding_mistral_20261008_03/report.md) |
| Reminder | **60/60** trên20 câu×3 | Runtime bổ sung update24/60; không phải model đơn lẻ; [báo cáo](../eval/results/provider_recheck_mistral_20261008_01/report.md) |
| Hội thoại nhiều lượt | Có các đợt20 phiên/80 lượt kiểm tra state, proposal và write safety | Không có booking trước confirm theo detector;20/20 write safety không chứng minh20/20 task success; [báo cáo](../eval/results/booking_grounding_mistral_20261008_04/report.md) |
| RAG bảo toàn evidence | Chặn tự sửa số coolant, giữ phạm vi xe/pin/phiên bản và cảnh báo nguồn | Không chứng nhận nguồn hiện hành; [báo cáo](../eval/results/maintenance_evidence_mistral_20261008_13/report.md) |
| Staging persistence lịch sử | propose→confirm→replay qua3 tiến trình, vẫn1 booking/2 messages sau confirm/replay | PostgreSQL/Redis cô lập; không phải staging/UI revision66; [kết quả](../eval/results/booking_grounding_mistral_20261008_04/staging_result.json) |

Ngoài các lượt đánh giá Agent, nhật ký kiểm thử main ngày09/10 ghi nhận Firebase thật, xác nhận booking trên backend và luồng chủ xưởng check-in→in_progress→completed, có đối chiếu database. Một lượt nhắc bảo dưỡng cho xe mẫu qua job main→Resend→Gmail được người dùng xác nhận nhận thư; liên kết lời nhắc đã mở trong phiên frontend người dùng. Đây là bằng chứng các luồng cụ thể trên bản main tại thời điểm đó. Mở rộng kiểm tra trên revision mới, webhook thật, lịch gửi tự động và nghiệm thu production được đặt trong mục9. Bằng chứng từng bước được ghi trong nhật ký integration main; không suy ra gửi thành công chỉ từ provider accepted.

Trước đợt30 câu mới, pipeline49 đạt30/30 kỹ thuật mỗi cấu hình; review54 trên60 đáp án cho Mistral25PASS/2FAIL/3UNVERIFIABLE và Gemma25PASS/1FAIL/4UNVERIFIABLE. Không so trực tiếp với46/5/9 mới như thay đổi accuracy vì dataset/runtime đã khác. [Review54](../eval/results/automatic_review_aggregate_20261009_54/REPORT.md).

### Những vấn đề lịch sử ảnh hưởng cách đọc kết quả

- Các pilot judge trước đó gặp quote không nguyên văn, chọn đáp án tool RAG làm bằng chứng gốc, sai mapping citation/card, thiếu claim/card hoặc enum/schema không hợp lệ. Runner giữ ERROR, không coi là Agent FAIL và không sửa raw output để ép PASS. Giao thức chuyển sang evidence cards/citation refs và validator local có kiểm provenance. Pilot đạt không thay thế hiệu chuẩn judge độc lập. [Giao thức evidence](../eval/results/automatic_review_20261008_38/NHAN_XET_REVIEW_TU_DONG.md), [giao thức/schema](../eval/results/automatic_review_20261008_46/manifest.json).
- Bốn request400 ở các lượt schema trước không có receipt. Probe plain/JSON gọi được tại thời điểm kiểm tra, nên không kết luận từ lỗi400 rằng key/quota toàn bộ đã hỏng. [Probe](../eval/results/automatic_review_provider_probe_20261008_43/provenance.json).
- Pilot judge62 tính sai thứ của10/10/2026; sửa evidence calendar/slot ở runner63 và kiểm lại controls, không sửa raw label62. Full63 dừng vì403 key spending limit;64 tái sử dụng25 nhãn và chấm35 còn thiếu, không loại nhãn bất lợi.
- Đã phát hiện **3 file pilot Gemma57 thay đổi so với seal57**: case_results.jsonl, metrics.json, closed_run_hashes.json. Seal57 cũ không còn hợp lệ cho ba file này; giữ manifest/file hiện có, không giả lập khôi phục. Phí Gemma lỗi cũ được giữ trong ledger và lượt thay thế được tính đúng một lần. [Audit toàn vẹn](../eval/results/agent_regression_revision_20261009_58/historical_integrity_audit.json), [ledger đối soát](../eval/results/agent_regression_revision_20261009_58/reconciled_prior_cost.json).

## 8. Chi phí đã ghi nhận và cách đối soát

### Phạm vi mới nhất55–67

| Phạm vi | Receipt LLM đã biết |
| --- | ---: |
| Pipeline55–61, gồm pilots/lượt lỗi/lượt dở và full mới | 0,25706310225 USD |
| Judge62–64, gồm pilot lỗi +pilot đạt +60 assessment | 0,20227562000 USD |
| **Tổng55–64** | **0,45933872225 USD** |
| Đối soát65, sửa/kiểm thử66 và tổng hợp báo cáo | **0 USD API mới** |
| Kiểm thử tích hợp67 | **0 USD LLM mới** |
| Smoke67 bị429 ở request đầu | **0 USD receipt đã biết;1 receipt chờ đối soát, phí để mở** |

Trong judge62–64: pilot lỗi62 tốn0,0121085 USD; pilot đạt63 tốn0,0213586 USD;60 nhãn full tốn0,16880852 USD. Riêng180 đáp án full có receipt0,14840061 USD, **đã nằm trong pipeline55–61**, không cộng lại. [Ledger pipeline/judge](../eval/results/agent_judge_resume_20261009_64/all_attempts_cost.json), [ledger sau sửa](../eval/results/agent_offline_revision_20261009_66/all_attempts_cost.json).

**Các khoản chờ đối soát:**69 embedding calls,1 receipt judge403, phí request đang chạy lúc dừng60 và1 receipt Agent429 ở67. Tổng receipt đã biết55–67 vẫn0,45933872225 USD; các khoản để mở không tính bằng0 hoặc gộp thành hóa đơn đầy đủ. Reserve0,01 USD của lượt cũ là dự phòng, không phải receipt hay trần thanh toán. Chiến dịch cũ dùng cap receipt0,75 USD; đợt67 dùng ngưỡng dừng riêng0,04 USD cho smoke12, không judge. Công việc đối soát tiếp theo nằm ở mục9.

### Các phạm vi lịch sử khác

| Phạm vi | Receipt đã biết | Khoản chờ đối soát / cách đọc |
| --- | ---: | --- |
| Benchmark10 model05/10 | 2,20653154 USD | Không phải tổng hóa đơn dự án |
| Rewrite mới, pilot +mọi full attempts | 0,026972684 USD | Receipt của101 embedding calls |
| Generation23–24, pilot +full +lượt lỗi | 0,038296139 USD | 1 receipt request lỗi thiếu |
| Pipeline48–49 | 0,064661938 USD | Phí của22 embedding calls |
| Riêng60 nhãn full judge54 | 0,143072570 USD | Nằm trong các aggregate judge lớn hơn |
| Toàn đợt sửa/chạy tiếp48–54 | 0,284533698 USD | Gồm pipeline/judge lỗi;phí của22 embedding calls để mở |
| Judge lịch sử cộng dồn theo ledger54 | 0,549382090 USD | 4 receipt lỗi lịch sử thiếu |

**Các dòng có phạm vi chồng nhau; không cộng hai bảng thành tổng chi phí dự án.** Không ghi các khoản chờ đối soát thành0. Các con số là receipt workload đã chạy, không phải bảng giá nhà cung cấp hiện tại. Đối soát tổng hóa đơn dự án với các khoản thiếu receipt được đặt trong mục9; các bảng trên phản ánh chi phí đã biết theo từng phạm vi. [Ledger54](../eval/results/automatic_review_aggregate_20261009_54/all_attempts_cost.json), [Rewrite](../eval/results/step4_rewrite_contract_completion_20261008_22/all_attempts_cost.json), [generation](../eval/results/step4_generation_completion_20261008_24/all_attempts_cost.json).

## 9. Tổng kết development và hướng phát triển tiếp theo

**Kết quả đã chốt:** technical90/90/model cho hai cấu hình;60 nhãn nội dung repeat1; đối soát14 mẫu; sửa RAG/evaluator và256 kiểm thử offline; đợt tích hợp67 đạt1/1 persistence,17/17 HTTP,4/4 UI với emulator và121/121 hồi quy email/booking/reminder giả lập. Giữ Mistral cho Agent/Rewrite/generation, Write reviewer inactive. Đây là cơ sở trình bày tiến độ development và quyết định cấu hình hiện tại.

### Lộ trình ưu tiên theo ngân sách

| Ưu tiên | Hướng phát triển | Công việc và đầu ra | Điều kiện/chi phí |
| --- | --- | --- | --- |
| 1 — làm offline | Kiểm tra tải nghiệp vụ và rà bộ kiểm thử/evidence | Tăng số request local với LLM stub để kiểm tra capacity, confirm/retry đồng thời; rà citation/document/chunk, metadata phiên bản, nguồn mâu thuẫn và câu trùng. Báo riêng độ trễ backend, không dùng thời gian stub làm tốc độ LLM | **0 USD LLM mới**; dùng service local/evidence đã lưu, không gọi dịch vụ ngoài |
| 2 — tiếp tục smoke | Đánh giá Mistral trên code ứng dụng sau sửa | Khi upstream gọi được, tiếp tục12 câu×1 đã khóa:6 RAG/2 booking/2 reminder/2 guardrail, evidence/Rewrite đã lưu; kiểm lỗi quy trình tìm trạm sạc, citation/abstention và state nghiệp vụ. Lưu đáp án mới riêng với lượt429 | Không judge/embedding/Qdrant; ngưỡng dừng receipt **0,04 USD**, reserve0,004 USD/request là dự phòng, không bảo đảm mức trần hóa đơn |
| 3 — củng cố nguồn và tiêu chí | Kiểm chứng nội dung RAG và hiệu chuẩn evaluator | Đối chiếu tài liệu chính thức, dòng xe/phạm vi/phiên bản/ngày hiệu lực; làm rõ nguồn coolant; kiểm claim support, abstention và citation; bổ sung golden chunk IDs để đo evidence-chunk recall. Kiểm chứng độ đúng độc lập bổ sung cho nhãn tự động | Rà metadata/evidence có thể làm offline; xác nhận hiệu lực cần nguồn có thẩm quyền. LLM judge bổ sung chỉ là tùy chọn theo ngân sách |
| 4 — tích hợp dịch vụ thật | Kiểm tra ứng dụng trên môi trường gần production | Chạy Google OAuth thật qua browser, backend/frontend và PostgreSQL/Redis với LLM thật; kiểm booking/reminder sau sửa; Resend thực tế, webhook có xác thực, job gửi theo lịch, retry/concurrency, trạng thái giao thư và mở liên kết | Môi trường/identity/người nhận kiểm thử riêng; giới hạn số lời gọi và gửi thư trước khi chạy |
| 5 — tối ưu hiệu năng | Độ trễ và trải nghiệm dưới tải | Đo p50/p90/p95, TTFT và concurrency với LLM thật; phân tách thời gian Agent, retrieval và Generation để tối ưu. Mục tiêu **p90≤8 giây**, từ mức đo development10,9021 giây của Mistral | Đo tải local/stub trước; phần LLM thật cần ngân sách cho số request cụ thể |
| 6 — đánh giá tổng quát | Bộ kiểm thử độc lập và đánh giá lặp | Khóa holdout do bên độc lập chuẩn bị/xác minh, có nguồn/đáp án/rubric; tách khỏi các câu đã dùng sửa Agent. Chạy lặp theo phạm vi được duyệt, báo độ biến động và chất lượng nội dung trên tập độc lập | Thực hiện khi phù hợp ngân sách; bộ30 hiện tại tiếp tục là development regression |
| 7 — đưa vào vận hành | Thử người dùng và nghiệm thu production | Thử các luồng chủ xe/chủ xưởng, ghi phản hồi và lỗi, đối chiếu tiêu chí nghiệp vụ/chất lượng/hiệu năng để quyết định triển khai | Tiếp nối bằng chứng từ các bước trên và xác nhận của team |

**Mở rộng tùy ngân sách:** chiến dịch220 câu +20 phiên, chấm thêm120 đáp án đã lưu và so sánh/lặp thêm model là các phương án về sau, không bắt buộc để dùng kết quả development hiện có. Team ưu tiên bước1 offline và tiếp tục smoke nhỏ khi provider khả dụng, giữ Mistral thay vì mở rộng số model.

**Đối soát chi phí:** đối chiếu hóa đơn provider/embedding với ledger để bổ sung69 embedding calls, receipt judge403, request dừng ở60 và Agent429 ở67; ghi rõ khoản xác nhận được và khoản tiếp tục thiếu chứng từ. Không cộng lại các phạm vi chồng nhau hoặc ghi khoản thiếu thành0 USD.

Các bước phát triển tiếp theo báo riêng bằng chứng mới với kết quả lịch sử, phân biệt đánh giá development, kiểm thử offline/fixture và kiểm chứng độc lập/production.
