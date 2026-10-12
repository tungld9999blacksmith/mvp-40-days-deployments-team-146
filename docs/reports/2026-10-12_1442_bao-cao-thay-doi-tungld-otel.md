# Báo cáo thay đổi nhánh `tungld-otel` — EV Care MVP

| Mục | Giá trị |
|---|---|
| Thời điểm lập | **12/10/2026 14:42 (GMT+7)** |
| Người lập | Claude Code (theo yêu cầu của Lê Đức Tùng) |
| Tác giả commit | Lê Đức Tùng (`tung leduc`) |
| Phạm vi | 21 commit (không tính merge), 11/10/2026 16:33 → 12/10/2026 13:58 |
| Nhánh | `tungld-otel` → merge vào `develop` (commit merge `4ab77fa`) |
| Quy mô | 229 file, +21.400 / −610 dòng (≈ 14.600 dòng là spec/tài liệu) |

---

## 1. Tóm tắt

1. **Observability:** tích hợp OpenTelemetry cho backend API và agent, gửi về Grafana Cloud (qua OTel Collector) và LangSmith; có che PII trong trace và metric riêng cho agent.
2. **Bảo mật OEM M2M v2.0:** backend gọi OEM bằng access token do OEM cấp (OAuth2 `client_credentials` + `private_key_jwt`) thay cho JWT tự ký từng request; webhook JWT gắn chặt với body request.
3. **Transactional outbox:** hạ tầng ghi event cùng transaction với nghiệp vụ, Celery worker xử lý có retry, backoff và dead-letter.
4. **Prompt:** tách toàn bộ prompt của agent ra file `.txt` có khoá phiên bản.
5. **Tài liệu:** thêm API / entity / frontend spec cho 33 tính năng Phase 2, gom theo miền nghiệp vụ.
6. **Sửa lỗi agent:** nâng ngân sách input của memory, giữ `AGENT_MEMORY_CONTEXT_MODE=off`, bổ sung tool `get_planned_trip`.

---

## 2. Chi tiết theo nhóm

### 2.1 Observability (OpenTelemetry, Grafana, LangSmith)

| Commit | Nội dung |
|---|---|
| `a3ad6ec` | Cờ `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT` cho container backend local; thêm gói OpenTelemetry |
| `cf1bd77` | Triển khai OTel, tích hợp vào backend API |
| `b032bfd`, `235c906` | Cập nhật tài liệu, hướng dẫn SRE |
| `a8136dc`, `1a5b988` | Tài liệu và triển khai Grafana tracing cho agent |
| `6af5b45` | Hook trace cho agent |
| `d072b1d` | Tích hợp `langchain-redact-pii`, ghi metric cho agent |

- Code mới trong `backend/src/infrastructure/observability/` (`telemetry`, `tracing`, `metrics`, `langsmith`, `agent_hooks`, `context`, `log_handler`), `backend/src/infrastructure/llm/traced.py`, `backend/src/agents/telemetry.py`.
- Phân vai: **LangSmith** giữ trace đầy đủ cùng token/chi phí; **Grafana** chỉ nhận span mỏng cùng metric tool / guardrail / RAG.
- Tài liệu: `docs/observability/GRAFANA_GUIDE.md`, `GRAFANA_ALERTING.md`.
- Test: `test_observability.py`, `test_agent_observability.py`.

### 2.2 Bảo mật OEM M2M v2.0 (SPEC-SEC-OEM-M2M-001)

| Commit | Nội dung |
|---|---|
| `26cf759` | Thay giao thức xác thực backend ↔ mock-ev-system bằng cặp khoá public/private hai phía + JWT |
| `b692c8a` | `ev-contracts`: thêm các loại token M2M cho luồng OAuth2 |
| `989e9d6` | Backend xin access token từ OEM (`POST /oauth/token`), cache Redis, gửi token trong mọi lệnh gọi nghiệp vụ |
| `5d8147c` | Webhook JWT gắn claim `body_sha256`; `OEM_AUTH_MODE=hmac` không còn nhận JWT; leeway JWT 60s thay vì 300s |
| `055de75` | Test backend không đọc khoá M2M từ `.env` gốc |
| `7e9a618` | Cập nhật spec lên v2.0 |

- Luồng: backend ký client assertion bằng `EVCARE_PRIVATE_KEY` → mock xác minh bằng `EVCARE_PUBLIC_KEY`, chặn `jti` dùng lại, cấp access token ký bằng `MOCK_PRIVATE_KEY` → backend xác minh bằng `OEM_PUBLIC_KEY` và cache `expires_in − OEM_ACCESS_TOKEN_REFRESH_MARGIN_SECONDS`.
- Lỗ hổng đã vá: trước đây webhook JWT không gắn với body nên token bắt được có thể gửi lại kèm body bất kỳ.
- File mới: `backend/src/infrastructure/oem/auth.py`, `mock_ev_system/auth.py`, `routers/oauth.py`, `ev_contracts/auth.py`; test `test_m2m_auth.py`.
- Biến môi trường mới: `OEM_ACCESS_TOKEN_REFRESH_MARGIN_SECONDS`, `MOCK_ACCESS_TOKEN_TTL_SECONDS` (cùng `EVCARE_*`, `OEM_PUBLIC_KEY`, `MOCK_*`, `OEM_AUTH_MODE`).

### 2.3 Transactional outbox (`73b77d1`)

- Event ghi vào bảng `outbox_event` **trong transaction của nơi tạo event**; handler kiểu `OutboxHandler` chạy trong Celery worker.
- Dispatcher: claim bằng `SKIP LOCKED` kèm lease + claim token, xử lý tuần tự, backoff luỹ thừa có jitter, dead-letter, purge, requeue.
- Celery beat: `outbox.dispatch` mỗi 10 giây (lưới an toàn), `outbox.purge` hằng ngày 03:30; `publish()` đánh thức dispatch ngay sau commit.
- Migration `12b82210986d` (bảng, index, RLS); cấu hình `OUTBOX_*`; hướng dẫn `backend/guide/outbox.md`; test `test_outbox.py`.

### 2.4 Prompt tách file (`5b41e13`, `0737659`, `75ca009`)

- Prompt của agent chuyển sang `backend/src/infrastructure/prompts/texts/*.txt` (chat khách, RAG rewrite/generate, phân loại hỏi thăm, review tool…), có `versions.lock.json`, `registry.py`, `hub.py`, script `scripts/prompt_sync.py`.
- `.gitattributes` giữ line ending LF cho file prompt để hash phiên bản ổn định.
- Test: `test_prompt_versions.py`.

### 2.5 Sửa lỗi agent (`94339ec`)

- System prompt và schema tool đã chiếm ~12k token nên ngân sách 12000 khiến mọi lượt chat báo `ContextBudgetExceeded` khi bật context mode. `AGENT_MEMORY_INPUT_TOKEN_BUDGET` 12000 → 20000.
- `AGENT_MEMORY_CONTEXT_MODE` trong `.env.example` về `off` cho tới khi chế độ `on` hết chặn nhầm tool result do graph tự chèn.
- Thêm `get_planned_trip` vào `CUSTOMER_AGENT_TOOLS` (danh sách tĩnh bị lệch so với runtime). Có test hồi quy: còn ≥ 4000 token cho lượt chat.

### 2.6 Tài liệu Phase 2 (`3dd94a2`, `f02a4bd`)

- Gom spec Phase 2 thành một thư mục cho mỗi miền nghiệp vụ trong `docs/specs/phase2/`; bổ sung API, entity và frontend spec cho 33 tính năng (≈ 176 file, +14.600 dòng).

---

## 3. Việc cần làm khi deploy

1. **Migration:** chạy `alembic upgrade head` (có `12b82210986d_outbox_event`).
2. **Biến môi trường mới** (đã thêm vào `.railway.env`, file không commit): cặp khoá M2M (`EVCARE_PRIVATE_KEY`, `EVCARE_PUBLIC_KEY`, `MOCK_PRIVATE_KEY`, `OEM_PUBLIC_KEY`), `OEM_AUTH_MODE`, `OEM_ACCESS_TOKEN_REFRESH_MARGIN_SECONDS`, `MOCK_AUTH_REQUIRED`, `MOCK_ACCESS_TOKEN_TTL_SECONDS`, `OUTBOX_DISPATCH_INTERVAL_SECONDS`, `OUTBOX_WAKEUP_ENABLED`.
3. **Deploy đồng thời backend, worker và mock-ev-system:** mock đã có `EVCARE_PUBLIC_KEY` sẽ bắt buộc access token, nên nếu chỉ một bên nhận khoá mới thì lệnh gọi OEM trả 401.
4. **Worker phải chạy cả Celery beat** để dispatcher outbox quét định kỳ.
5. **Bật tracing sau cùng:** `OTEL_ENABLED=false` trong staging cho tới khi service `otel-collector` được deploy.

## 4. Rủi ro và lưu ý

- `OEM_AUTH_MODE=both` vẫn nhận HMAC cũ để chuyển đổi êm; chuyển sang `jwt` khi OEM thật đã dùng JWT gắn body.
- `AGENT_MEMORY_CONTEXT_MODE` phải giữ `off` / `shadow` (xem 2.5).
- Khoá M2M staging khác khoá local; không dùng chung giữa các môi trường.
