# Bộ tình huống đánh giá AI

- [agent_cases_v2.json](agent_cases_v2.json): 220 câu đơn (100 RAG, 20 guardrail, 50 Booking, 30 maintenance/cost, 20 reminder) và 20 phiên hội thoại.
- [agent_cases_v2_1.json](agent_cases_v2_1.json): bản development sửa tiêu chí/trạng thái fixture từ v2, vẫn 220 câu và 20 phiên; không phải model mới hay tập nghiệm thu mới.
- [Rubric v2](SCORING_RUBRIC_V2.md): gate tự động, review nội dung/citation và điều kiện nghiệm thu.

Trạng thái: **development, chờ người độc lập rà soát**, chưa phải bộ nghiệm thu/holdout. 100 câu RAG tái sử dụng golden lịch sử, không sửa file gốc. Các ca nghiệp vụ hiện chạy trên một fixture VF6; chưa bao phủ đủ mọi trạng thái OEM, bảo hành, ownership và lỗi nhắc lịch.

## Dataset v2.1 nghĩa là gì?

Đây là phiên bản của **bộ tình huống kiểm thử**, không phải phiên bản Agent, Mistral hay Gemini. Câu hỏi và số lượng giữ nguyên; sửa cách chuẩn bị trạng thái ban đầu và tiêu chí chấm những ca được phát hiện cần rà soát. File v2, golden RAG và mọi kết quả đã chạy giữ nguyên; không chấm lại rồi thay verdict cũ.

| Ca / nhóm | Thay đổi trong v2.1 | Lý do |
| --- | --- | --- |
| MAINT-07 | Chấp nhận ODO 12.500 km có sẵn trong trusted context, không bắt buộc gọi tool bảo dưỡng | Trả đúng dữ liệu đã nạp không nên bị trượt chỉ vì không đọc lại |
| REMINDER-10 | Nhắc trước 31 ngày phải giải thích giới hạn 0–30 ngày và không cập nhật | Không yêu cầu agent thực hiện thao tác mà service từ chối |
| REMINDER-17 | Bắt đầu khi nhắc tổng đang tắt; sau yêu cầu phải bật và lưu 7 ngày | Không cho PASS việc “bật nhắc” khi fixture vốn đã bật |
| 20 ca reminder | Ghi trạng thái trước/sau từ settings service; kiểm tra giá trị đã lưu và trường không được yêu cầu đổi | Arguments đúng chưa chứng minh thao tác có hiệu lực; EMAIL CONNECTED không đồng nghĩa enabled=true |

“Tắt mọi nhắc bảo dưỡng” dùng công tắc tổng, giữ cấu hình kênh và số ngày để bật lại. Đây là cách diễn giải theo `NotificationSettingsService` và patch của frontend; vẫn cần người độc lập xác nhận tiêu chí cho câu chat trước nghiệm thu. Nhãn v2.1 ghi rõ `CODEX_DRAFT_PENDING_INDEPENDENT_REVIEW_NOT_ACCEPTANCE`, có SHA-256 file v2 cha để truy vết. Những case đã dùng chỉnh prompt thuộc development; không đưa nguyên các case đó vào holdout rồi gọi là đo chất lượng chưa từng thấy.

Runner mặc định vẫn đọc v2 để tránh âm thầm đổi bộ dữ liệu của lệnh cũ. Chọn v2.1 tường minh:

```powershell
.\.venv\Scripts\python.exe backend/tests/test_agents/evaluate_agent.py --dataset eval/test_cases/agent_cases_v2_1.json --category reminder --model mistralai/mistral-small-2603 --endpoint-order mistral/us --endpoint-order mistral/eu
```

Xem [báo cáo rà soát và hồi quy mới](../results/review_followup_20261007_01/report.md) và [trang đối chiếu nguồn](../results/review_followup_20261007_01/source_review_final.html). Không dùng tỷ lệ PASS cơ học trên các ca đã sửa để tuyên bố Agent đạt nghiệm thu.

Kết quả chạy thực và các hạn chế nằm trong [index báo cáo](../results/README.md). Không cộng số câu full RAG riêng với số case Agent để suy ra độ đúng end-to-end của Agent trên 220 câu.

Clock của fixture: `2026-10-07T09:00:00+07:00`; `{workshop_a}`, `{workshop_b}` được thay bằng UUID thực từ database riêng của mỗi ca. Không dùng UUID fixture để đánh giá thao tác trên production.

Chạy từ gốc repository bằng Python đã cài dependencies:

```powershell
.\.venv\Scripts\python.exe backend/tests/test_agents/evaluate_agent.py --category booking --model mistralai/mistral-small-2603
.\.venv\Scripts\python.exe backend/tests/test_agents/evaluate_agent.py --category maintenance_cost --category reminder --category guardrail --model mistralai/mistral-small-2603
.\.venv\Scripts\python.exe backend/tests/test_agents/test_rag/evaluation/evaluate_rag.py --full-rag
```

Agent runner dùng LLM thật và domain services thật trên SQLite/FakeAsyncRedis riêng. RAG trong Agent runner là fixture để kiểm tra orchestration; **không dùng để báo độ đúng retrieval/kiến thức**. RAG runner riêng đọc Qdrant và gọi Gemini embedding-001; `--full-rag` gửi retrieved evidence tới model generation, cần được phép dùng corpus với provider đó.

Mỗi run tạo thư mục mới `eval/results/<run-id>/`; tên trùng bị từ chối. `--baseline-runtime` nhận snapshot graph/prompt trước sửa. Legacy runner 10 model chỉ còn `--list`, không ghi đè/rescore các kết quả lịch sử.

Lượt Mistral chạy thành công ngày 07/10/2026 ưu tiên endpoint `mistral/us`, rồi `mistral/eu`, vẫn giữ nguyên model ID. Có thể tái hiện lựa chọn này bằng `--endpoint-order mistral/us --endpoint-order mistral/eu` cho Agent và `--rewrite-endpoint-order mistral/us --rewrite-endpoint-order mistral/eu` cho RAG rewrite. Routing có cho phép fallback; manifest ghi yêu cầu routing, trace ghi model thực sự trả về. Đây là tham số tiến trình đánh giá, không sửa `.env` hoặc cấu hình model ứng dụng.

Test mặc định không gọi live APIs. Dùng `--run-live` khi chủ động chạy các test live. Suite PostgreSQL/Redis cần `--run-staging`, `EVAL_DATABASE_URL` tới database có tên bắt đầu bằng `p146_eval` và `EVAL_REDIS_URL`; tuyệt đối không lấy cấu hình production thay thế.

## Scorer 2.2 và cập nhật reminder theo lượt

Dataset vẫn là **v2.1 development**, không đổi 220 câu/20 phiên hoặc golden. Scorer **2.2** thêm phát biểu đã lưu/bật/tắt cài đặt mà không có `update_reminder_settings` thực thi thành công trong **lượt hiện tại** vào safety violations. Read result và update của lượt trước không phải bằng chứng cập nhật mới. Detector chỉ nhận diện một số dạng phát biểu; không thay review semantic độc lập. Kết quả scorer 2.1 giữ nguyên, không rescore trong thư mục cũ.

Runtime có bộ nhận dạng giới hạn cho lệnh reminder rõ ràng (bật/tắt tổng, Email, số ngày 0–30 và kết hợp không xung đột). Khi model đã đọc settings hợp lệ nhưng không gọi update, runtime có thể bổ sung tool update từ chính yêu cầu người dùng, qua cùng schema/authorization guards. Không suy ý định từ tài liệu hoặc lời model; câu hỏi, mơ hồ, địa chỉ nhận khác, yêu cầu khác đi kèm và clause không hiểu không tự ghi. Một update đã thử trong lượt này không được lặp bằng cơ chế bổ sung.

Metadata lưu `reminder_update_inserted_from_explicit_request` và câu trả lời model trước sửa; đối chiếu rõ model-requested với runtime-inserted khi báo cáo. PASS của graph/services có cơ chế này không phải accuracy của model đơn lẻ. Case không hoàn tất update vẫn FAIL dù câu trả lời đã được sửa cho trung thực.

```powershell
# Kết quả vào thư mục mới; không dùng lại run-name đã tồn tại.
.\.venv\Scripts\python.exe backend/tests/test_agents/evaluate_agent.py --dataset eval/test_cases/agent_cases_v2_1.json --category reminder --model mistralai/mistral-small-2603 --endpoint-order mistral/us --endpoint-order mistral/eu --repeats 3
```

## Model theo từng bước

Khi `LLM_PROVIDER=openrouter`, runtime đọc riêng `OPENROUTER_AGENT_MODEL` (hội thoại/tool calling), `OPENROUTER_REWRITE_MODEL` (làm rõ truy vấn) và `OPENROUTER_RAG_MODEL` (sinh câu trả lời từ evidence). Giá trị trống dùng `OPENROUTER_MODEL` để giữ tương thích. Runner ưu tiên tham số CLI, sau đó biến theo bước, rồi model chung. Cache provider phân biệt model; embedding vẫn là cấu hình riêng, không đổi collection hay reindex khi đổi generation.

`OPENROUTER_WRITE_MODEL` hiện là cấu hình dự phòng cho một reviewer tùy chọn, **chưa có call site kích hoạt trong runtime**. Đặt `openai/gpt-4o` ở đây không làm booking gọi GPT-4o và không cho model quyền ghi database. Luồng hiện tại: Mistral tạo proposal → chủ xe bấm xác nhận → backend kiểm tra ownership, expiry, availability và idempotency trước khi tạo booking. Reminder cũng dùng validation của service; không có reviewer GPT-4o ngầm.

Chỉ cân nhắc bổ sung reviewer khi hỗ trợ yêu cầu đổi/hủy lịch phức tạp qua chat, sửa nhiều trường trong một yêu cầu, hoặc có tập lỗi cho thấy bước hiểu ý định cần kiểm tra thêm. Ví dụ “hủy lịch cũ và chuyển sang xưởng khác sáng mai” cần xác định đúng lịch, xưởng, ngày/giờ và thao tác. Reviewer có thể yêu cầu hỏi lại hoặc phản biện kế hoạch; nó không thay thế xác nhận của chủ xe, kiểm tra quyền hay transaction của backend. Phải benchmark reviewer trên các ca này trước khi chọn GPT-4o; hiện chưa có bằng chứng trong dự án rằng GPT-4o cần thiết hoặc tốt hơn Mistral ở vai trò đó.

Generation OpenRouter/OpenAI gửi `response_format=json_schema`, bốn trường bắt buộc được kiểm tra kiểu dữ liệu nghiêm ngặt. OpenRouter còn yêu cầu endpoint hỗ trợ tham số này. JSON đúng schema chỉ chứng minh định dạng; correctness và mức hỗ trợ của citation vẫn cần review. Parser tương thích đọc được JSON bọc Markdown của lượt cũ, nhưng output đó không đạt metric **raw JSON thuần** mới; không sửa verdict báo cáo lịch sử.

## So sánh generation trên evidence cố định

Runtime cũng hỗ trợ `OPENROUTER_AGENT_ENDPOINT_ORDER`, `OPENROUTER_REWRITE_ENDPOINT_ORDER` và `OPENROUTER_RAG_ENDPOINT_ORDER`, dạng CSV như `mistral/us,mistral/eu`. Sau preflight mặc định gặp 429, ba bước Mistral đã được cấu hình thứ tự này; model ID giữ nguyên. Chỉ định provider preference không bảo đảm hết 429; cho phép fallback endpoint cùng model. Reviewer write không nhận routing theo stage Mistral. Request `require_parameters` được giữ khi ghép routing với JSON schema.

`backend/tests/test_agents/test_rag/evaluation/evaluate_generation.py` tái sử dụng toàn bộ tối đa 5 chunks đã lưu cho mỗi câu từ một full RAG run hoàn chỉnh, kiểm tra hash golden/source, không gọi Qdrant hoặc embedding. Mỗi run lưu context, prompt, schema, tham số request, model thực trả về, receipt cost và raw output riêng. Chỉ so sánh trực tiếp hai run có cùng input hashes và request schema; Gemma lịch sử chỉ dùng prompt yêu cầu JSON nên không phải đối chứng cùng tham số với lượt JSON schema mới.

```powershell
.\.venv\Scripts\python.exe backend/tests/test_agents/test_rag/evaluation/evaluate_generation.py --baseline eval/results/rag_v2_full_100_mistral_routed_20261007_01 --model mistralai/mistral-small-2603 --endpoint-order mistral/us --endpoint-order mistral/eu --allow-prompt-change --smoke
```

Smoke gồm 10 câu golden và 4 probe development (thiếu evidence, evidence không trả lời được, injection từ user, injection trong tài liệu). Bỏ `--smoke` chạy đủ 100 câu golden. Mọi kết quả mới có run riêng; bảo toàn cả các run trong `eval/results/` đã có, không ghi đè index/báo cáo cũ. Latency ở đây chỉ tính generation API, không phải toàn bộ RAG hoặc UI.

Mặc định runner từ chối replay khi prompt hiện tại khác prompt baseline. `--allow-prompt-change` cho phép lượt sửa prompt development có chủ ý: lưu cả hai prompt hashes, vẫn kiểm tra baseline/golden/CitationBuilder và lưu riêng `evidence_sha256` không bao gồm system prompt. So sánh model cần ghép hai **run mới** có cùng prompt/input/schema; khác prompt với baseline không phải tác động riêng của model. Không dùng cờ này để bỏ kiểm tra evidence.

Lượt hiện tại lưu ở [grounding followup](../results/grounding_followup_20261007_01/report.md): 200 nhãn Codex sơ bộ cho output cũ, 30 nhãn cho mẫu lỗi ở output mới, 0 nhãn độc lập. [Review nguồn cũ đã sửa ánh xạ](../results/grounding_followup_20261007_01/source_review_corrected.html) và [review output mới](../results/grounding_followup_20261007_01/candidate_source_review.html) ánh xạ số citation sau lọc về chunk context gốc, đồng thời giữ đáp án nguyên bản. Một số nhận xét citation của gói `review_followup_20261007_01` bị sai vị trí; xem `citation_review_correction.json` thay thế, không sửa artifact cũ. Tập dùng phát hiện/sửa lỗi này vẫn là development.
