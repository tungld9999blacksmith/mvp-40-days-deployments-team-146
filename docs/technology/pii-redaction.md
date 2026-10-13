# Che dữ liệu cá nhân (PII) và bí mật

> Cập nhật: 2026-10-12. Mỗi nơi dữ liệu rời khỏi tiến trình có một lớp che riêng.

| Nơi | Cơ chế | Code | Cấu hình |
| --- | --- | --- | --- |
| Log (stdout, file, OTLP → Loki) | Processor structlog `PiiRedactor` chạy trên **mọi** event trước khi render | `backend/src/infrastructure/logging/pii.py`, `config.py` | `LOG_REDACT_PII` (mặc định bật) |
| Trace LLM trên LangSmith | `create_anonymizer` dùng lại `redact_text` của log, áp cho mọi chuỗi vào/ra | `backend/src/infrastructure/observability/langsmith.py` | `LANGCHAIN_REDACT_PII` (`true` staging, `false` local) |
| Câu trả lời của trợ lý | Output guard luôn che VIN, CCCD, số điện thoại, biển số, email trước khi lưu và gửi client | `backend/src/agents/conversation_guards/output_guard.py` | Luôn bật |
| Tin người dùng gửi vào agent | Input guard phát hiện PII và dấu hiệu prompt injection (hiện chỉ ghi log) | `conversation_guards/input_guard.py` | — |
| Telemetry Grafana | Không đưa nội dung vào span; metric chỉ nhãn cố định | `tracing.py`, `metrics.py` | — |
| Payload outbox | Chỉ id và dữ liệu tối thiểu; `last_error` chỉ tên lớp lỗi | `infrastructure/outbox` | — |

## Quy tắc `PiiRedactor`

Hai lượt: (1) **theo khóa**, giá trị dưới khóa nhạy cảm bị bỏ (`[REDACTED]`) hoặc che (email, số điện thoại) ở mọi độ sâu dict/list; (2) **theo giá trị**, quét văn bản tự do (message, query string, traceback) tìm bearer/basic credentials, JWT, định dạng API key phổ biến, `key=value` bí mật, email và số điện thoại. Giá trị được sao chép, không sửa tại chỗ.

## Việc cần làm khi thêm dữ liệu mới

- Thêm khóa nhạy cảm vào `DEFAULT_SECRET_KEYS` nếu nó xuất hiện trong log dưới tên mới.
- Không đưa SĐT, email, VIN, nội dung chat vào payload outbox, nhãn metric hay thuộc tính span của Grafana.
- Token M2M, khóa riêng và access token OEM không bao giờ được ghi log.

## Lưu ý

Commit `d072b1d` nhắc đến `langchain-redact-pii`, nhưng gói này **không** có trong `backend/pyproject.toml`; việc che trên LangSmith hiện dùng `PiiRedactor` nội bộ ở trên.
