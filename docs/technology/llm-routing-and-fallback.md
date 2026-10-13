# LLM: provider, định tuyến theo giai đoạn và fallback

> Cập nhật: 2026-10-12. Code: `backend/src/infrastructure/llm/` (`base.py`, `factory.py`, `routing.py`, `fallback.py`, `openrouter_routing.py`, `traced.py`).

## 1. Provider

Interface `LLMProvider` (`chat`, `chat_stream`) với provider Anthropic, Gemini và nhóm OpenAI-compatible (OpenAI, OpenRouter, Grok, DeepSeek). `LLM_PROVIDER` chọn mặc định toàn hệ thống; mỗi provider có khóa `<PROVIDER>_API_KEY` và tên model riêng.

## 2. Định tuyến theo giai đoạn

Mỗi giai đoạn của agent có thể dùng provider/model riêng để cân bằng chi phí và độ chính xác:

| Giai đoạn (`LLMStage`) | Việc | Biến |
| --- | --- | --- |
| `orchestrator` (bí danh `agent`) | Vòng ReAct chính của agent | `LLM_ORCHESTRATOR_PROVIDER`, `LLM_ORCHESTRATOR_MODEL` |
| `rewrite` | Viết lại câu hỏi cho RAG | `LLM_REWRITE_PROVIDER`, `LLM_REWRITE_MODEL` |
| `rag` | Sinh câu trả lời RAG có trích dẫn | `LLM_RAG_PROVIDER`, `LLM_RAG_MODEL` |
| `booking` (bí danh `write`) | Duyệt lời gọi tool nhạy cảm (`tool_review`), bật bằng `LLM_BOOKING_CHECK_ENABLED` | `LLM_BOOKING_PROVIDER`, `LLM_BOOKING_MODEL` |

- `settings_for_stage()` trả bản sao `Settings` đã thay provider/model của giai đoạn; **để trống thì kế thừa** `LLM_PROVIDER` và model mặc định. Provider theo giai đoạn chỉ nhận `openai`, `gemini`, `openrouter`.
- Với OpenRouter, nếu `LLM_<STAGE>_MODEL` trống thì dùng cấu hình cũ `OPENROUTER_AGENT_MODEL` / `_REWRITE_` / `_RAG_` / `_WRITE_MODEL` rồi mới tới `OPENROUTER_MODEL`.
- OpenRouter còn có thứ tự endpoint theo giai đoạn (`OPENROUTER_*_ENDPOINT_ORDER`); gặp HTTP 429 thì chuyển sang endpoint kế tiếp trong danh sách (`openrouter_routing.py`), không nới lỏng ràng buộc provider do caller đặt.

## 3. Fallback

`LLM_FALLBACK_PROVIDER` (hiện chỉ `gemini`) bọc provider chính bằng `FallbackLLMProvider`:

- Khi lỗi **tạm thời** (`LLMRateLimitError`, `LLMProviderUnavailableError`) và **chưa phát token nào** thì chuyển sang fallback. Đã phát token thì không chuyển, tránh trộn hai câu trả lời.
- Fallback thiếu API key thì bị tắt và ghi cảnh báo, không làm hỏng provider chính.
- Mỗi lời gọi bị giới hạn `LLM_CALL_TIMEOUT_SECONDS` (mặc định 10 giây); khi có fallback, model chính không retry để fallback còn kịp trong hạn một lượt chat (30 giây).
- Phản hồi rỗng kết thúc bằng `finish_reason="error"` được gọi lại đúng một lần.

## 4. Trace và chi phí

Lời gọi qua LangChain được trace tự động. Lời gọi ngoài LangChain (RAG rewrite/generate, tool review, phân loại hỏi thăm) đi qua `traced.py`: LangSmith nhận run `llm` có message, câu trả lời và token (chi phí do LangSmith tính theo bảng giá model); Grafana (khi `OTEL_AGENT_ENABLED=true`) nhận span mỏng `chat <model>` (provider, model, status, số token; không văn bản) và metric độ trễ / token / chi phí — xem [AGENT_COST_LATENCY.md](../observability/AGENT_COST_LATENCY.md). Xem [observability.md](observability.md).

## 5. Kiểm thử

Test dùng provider giả; giá trị `LLM_*_MODEL` trong `.env` gốc có thể làm test định tuyến đỏ ở máy local (xem CLAUDE.md, mục Testing): đặt rỗng khi chạy.
