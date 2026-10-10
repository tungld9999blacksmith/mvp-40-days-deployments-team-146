# Platform Specification — Xử lý lỗi (Backend API + Frontend)

> Tài liệu dùng chung cho mọi feature. Các spec API (`docs/specs/sprint-*/api/*.api.md`) mô tả lỗi riêng của từng endpoint. Tài liệu này quy định **định dạng chung**, **danh mục mã lỗi** và **cách frontend hiển thị lỗi**. Hành vi khi một phụ thuộc (LLM, Redis, OEM, Firebase, Qdrant…) gặp sự cố nằm ở [architecture-deep-dive.md §4.2](../../architecture-deep-dive.md#42-hành-vi-khi-một-phụ-thuộc-gặp-sự-cố). Tài liệu này không lặp lại phần đó.

| Field | Value |
| --- | --- |
| Spec ID | `PLAT-ERR-001` |
| Version | `v1.0` |
| Status | Draft |
| Updated Date | `2026-10-07` |
| Nguồn đối chiếu | `backend/src/main.py` (exception handlers), `backend/src/modules/*/errors.py`, `backend/src/infrastructure/redis/ratelimit/dependency.py`, `frontend/src/shared/api/client.ts`, `frontend/src/shared/ui/{States,Toast}.tsx` |

---

# 1. Định dạng lỗi của API

## 1.1 Envelope

Mọi lỗi nghiệp vụ trả về:

```json
{
  "error": {
    "code": "SLOT_FULL",
    "message": "The selected slot is full.",
    "details": { "alternatives": [] },
    "traceId": "9b2f0c4e7d…"
  }
}
```

| Trường | Bắt buộc | Quy ước |
| --- | --- | --- |
| `code` | Có | `UPPER_SNAKE_CASE`, ổn định. Frontend và AI Agent rẽ nhánh theo `code`, **không** theo `message` |
| `message` | Có | Tiếng Anh, dành cho log và lập trình viên. **Không** hiển thị thẳng cho người dùng (xem §4.3) |
| `details` | Không | Dữ liệu để UI tự xử lý. Các khoá đang dùng: `field` (trường sai), `retryAfterSeconds`, `alternatives` (khung giờ thay thế khi `SLOT_FULL`), `validMilestones`, `status` (trạng thái hiện tại khi xung đột) |
| `traceId` | Có | Bằng header `X-Request-ID` của request. Xuất hiện trong mọi dòng log của request đó |

## 1.2 Header

| Header | Chiều | Ý nghĩa |
| --- | --- | --- |
| `X-Request-ID` | Request và Response | Frontend tự sinh cho mỗi request. Backend (`CorrelationIdMiddleware`) nhận, tự sinh nếu thiếu hoặc sai định dạng, rồi gửi lại ở response |
| `Retry-After` | Response | Số giây nên chờ trước khi thử lại: `429` (`RATE_LIMITED`, `RATE_LIMIT_EXCEEDED`, `VERIFICATION_ATTEMPTS_EXCEEDED`) |
| `X-RateLimit-Limit`, `-Remaining`, `-Reset` | Response | Kèm `429 RATE_LIMIT_EXCEEDED` từ rate limiter dùng chung |

## 1.3 Quy ước HTTP status

| Status | Dùng khi | Ví dụ |
| --- | --- | --- |
| `400` | Request sai định dạng hoặc thiếu trường | `INVALID_REQUEST`, `INVALID_FIELD_FORMAT`, `CONSENT_REQUIRED` |
| `401` | Chưa đăng nhập, token sai/hết hạn/bị thu hồi, chữ ký webhook sai | `UNAUTHORIZED`, `INVALID_TOKEN`, `TOKEN_REVOKED` |
| `403` | Đã đăng nhập nhưng không có quyền hoặc chưa onboard | `FORBIDDEN`, `ONBOARDING_REQUIRED`, `ACCOUNT_SUSPENDED` |
| `404` | Không tìm thấy, hoặc tài nguyên không thuộc người gọi (không phân biệt để tránh dò ID) | `BOOKING_NOT_FOUND`, `QUOTE_NOT_FOUND` |
| `409` | Xung đột trạng thái hoặc đồng thời: thao tác hợp lệ nhưng trạng thái hiện tại không cho phép | `SLOT_FULL`, `QUOTE_NOT_DRAFT`, `INVALID_STATUS_TRANSITION` |
| `422` | Dữ liệu đúng định dạng nhưng vi phạm quy tắc nghiệp vụ | `SLOT_OUT_OF_HOURS`, `NO_MAINTENANCE_RULE`, `COVERED_ITEM_LOCKED` |
| `429` | Vượt giới hạn tần suất | `RATE_LIMITED`, `RATE_LIMIT_EXCEEDED`, `VERIFICATION_ATTEMPTS_EXCEEDED` |
| `503` | Phụ thuộc tạm thời không dùng được, **thử lại được** | `SERVICE_UNAVAILABLE`, `OEM_UNAVAILABLE`, `AUTH_PROVIDER_UNAVAILABLE` |
| `504` | Hết thời gian chờ phụ thuộc | `CHAT_TIMEOUT` |
| `500` | Lỗi không lường trước. Không bao giờ chủ động trả | — |

Mỗi module ánh xạ `code → status` bằng bảng `ERROR_STATUS` trong `errors.py`. Mã không có trong bảng thì nhận status mặc định: `400` ở hầu hết module, `500` ở `auth` và `workshop_owner_auth`.

## 1.4 Các ngoại lệ chưa theo envelope (hiện trạng code)

| Trường hợp | Response thực tế | Frontend xử lý |
| --- | --- | --- |
| Request validation (Pydantic) trên route **ngoài** danh sách `_ONBOARDING_PREFIXES` trong `main.py` (ví dụ `/vehicles`, `/conversations`, `/notification-settings`, `/notifications`, `/workshop/*`) | `422 {"detail": [...]}` của FastAPI | `client.ts` quy về `INVALID_REQUEST` |
| Firebase ID token bị từ chối ở `modules/oauth/dependency.py` | `401 {"detail": "Invalid or expired Firebase token."}` | Quy về `UNAUTHORIZED` |
| Webhook email Resend (`POST /api/v1/notifications/email/webhook`) | `HTTPException` 400/401/413/503 dạng `{"detail": ...}` | Không áp dụng (server gọi server) |
| Exception không bắt (ví dụ Redis mất kết nối khi đặt lịch qua API thường) | `500 Internal Server Error` dạng text, **không** có envelope | Quy về `INTERNAL_SERVER_ERROR`; `traceId` lấy từ header `X-Request-ID` |
| Lỗi nghiệp vụ khi client không gửi `X-Request-ID` | `traceId: null` trong body (handler đọc header của request, không đọc ID do middleware sinh) | Frontend luôn gửi header nên không gặp |

Xem §6 về việc dọn các ngoại lệ này.

---

# 2. Danh mục mã lỗi

## 2.1 Mã dùng chung nhiều module

| Code | Status | Ý nghĩa | Module |
| --- | --- | --- | --- |
| `INVALID_REQUEST` | 400 | Request sai định dạng; `details.field` chỉ trường sai | Hầu hết |
| `UNAUTHORIZED` | 401 | Chưa đăng nhập hoặc token không hợp lệ | booking, conversation, workshop_owner_auth |
| `FORBIDDEN` | 403 | Không có quyền với tài nguyên | booking, conversation, quote, user_vehicle |
| `ONBOARDING_REQUIRED` | 403 | Tài khoản chưa hoàn tất onboarding | booking, user_vehicle, onboarding, workshop_board |
| `ACCOUNT_SUSPENDED` / `ACCOUNT_INACTIVE` | 403 | Tài khoản bị khoá / ngừng hoạt động | user_vehicle, onboarding, workshop_owner_auth |
| `USER_NOT_REGISTERED` | 404 | Firebase user chưa có tài khoản chủ xe | booking, user_vehicle, onboarding |
| `VEHICLE_NOT_FOUND` | 404 | Xe không tồn tại hoặc không thuộc chủ xe | booking, conversation, cost_estimate, quote, user_vehicle |
| `WORKSHOP_NOT_FOUND` | 404 | Xưởng không tồn tại | booking, cost_estimate |
| `BOOKING_NOT_FOUND` | 404 | Lịch hẹn không tồn tại hoặc không thuộc người gọi | booking, workshop_board, service_progress |
| `FEATURE_DISABLED` | 404 | Tính năng đang tắt bằng cờ cấu hình | booking, service_progress |
| `VEHICLE_NOT_ACTIVE` | 409 | Xe chưa xác minh hoặc đã huỷ liên kết | booking, conversation, user_vehicle, quick_booking |
| `SLOT_FULL` | 409 | Khung giờ hết chỗ; `details.alternatives` gợi ý khung khác | booking, quick_booking |
| `OPEN_BOOKING_EXISTS` | 409 | Xe đang có lịch hẹn mở | booking, quick_booking |
| `SLOT_OUT_OF_HOURS` | 422 | Ngoài giờ hoạt động của xưởng | booking, quick_booking, workshop_board |
| `MILESTONE_NOT_FOUND` | 422 | Mốc bảo dưỡng không có trong định mức của model; `details.validMilestones` | cost_estimate, quote |
| `IDEMPOTENCY_KEY_REUSED` | 422 | Cùng `Idempotency-Key` nhưng nội dung khác | onboarding (chủ xe, chủ xưởng) |
| `RATE_LIMITED` | 429 | Vượt giới hạn gửi tin của chat | conversation, quick_booking |
| `RATE_LIMIT_EXCEEDED` | 429 | Vượt giới hạn của rate limiter dùng chung (Redis) | `infrastructure/redis/ratelimit` |
| `SERVICE_UNAVAILABLE` | 503 | Redis/khoá/dịch vụ phụ tạm lỗi, thử lại được | booking, cost_estimate, follow_up, quick_booking, workshop_board |
| `AUTH_PROVIDER_UNAVAILABLE` | 503 | Không gọi được Firebase khi kiểm tra thu hồi phiên. Khác `INVALID_TOKEN`: **không** đăng xuất người dùng | auth, conversation, workshop_owner_auth |

## 2.2 Mã riêng theo module

| Module (spec) | Code → status |
| --- | --- |
| Đăng ký chủ xe `vehicle_owner_onboarding` (us-001) | `INVALID_FIELD_FORMAT` 400 · `CONSENT_REQUIRED` 400 · `EMAIL_NOT_VERIFIED` 403 · `UNSUPPORTED_SIGN_IN_PROVIDER` 403 · `EMAIL_ALREADY_LINKED` 409 · `PHONE_ALREADY_IN_USE` 409 · `NATIONAL_ID_ALREADY_IN_USE` 409 · `ONBOARDING_ALREADY_COMPLETED` 409 · `PROFILE_INCOMPLETE` 409 · `VERIFICATION_IN_PROGRESS` 409 · `VEHICLE_ALREADY_LINKED` 409 · `VERIFICATION_ATTEMPTS_EXCEEDED` 429 (+`Retry-After`) · `OEM_UNAVAILABLE` 503 |
| Đăng ký chủ xưởng `workshop_owner_onboarding` (us-009) | Như trên (trừ `VEHICLE_ALREADY_LINKED`, `OEM_UNAVAILABLE`) · `WORKSHOP_OWNER_NOT_REGISTERED` 404 · `WORKSHOP_ALREADY_CLAIMED` 409 |
| Phiên chủ xưởng `workshop_owner_auth` (us-013) | `INVALID_TOKEN` 401 · `TOKEN_REVOKED` 401 · `WORKSHOP_OWNER_NOT_REGISTERED` 404 |
| Đặt lịch `booking` (us-029, us-033, us-053) | `LOCATION_ANCHOR_REQUIRED` 422 · `HOLD_EXPIRED` 409 · `HOLD_WINDOW_CLOSED` 409 · `INVALID_CONFIRMATION_TOKEN` 409 · `CONFIRMATION_TOKEN_EXPIRED` 409 · `IDEMPOTENCY_CONFLICT` 409 · `QUOTE_EXPIRED` 409 · `BOOKING_NOT_CONFIRMED` 409 · `APPOINTMENT_STARTED` 409 · `QR_NOT_AVAILABLE` 409 · `BOOKING_CHANGED` 409 · `RESCHEDULE_NOT_ALLOWED` 409 · `RESCHEDULE_TOO_LATE` 409 · `RESCHEDULE_LIMIT_REACHED` 409 · `RESCHEDULE_WORKSHOP_MISMATCH` 422 · `RESCHEDULE_SAME_SLOT` 422 |
| Đặt nhanh từ chat `quick_booking` (us-061) | `PROPOSAL_NOT_FOUND` 404 · `CONVERSATION_NOT_FOUND` 404 · `CONVERSATION_BUSY` 409 · `PROPOSAL_IN_PROGRESS` 409 · `PROPOSAL_INACTIVE` 409 · `PROPOSAL_EXPIRED` 409 · `PROPOSAL_SLOT_FULL` 409 · `PROPOSAL_ALREADY_CONFIRMED` 409 · `SLOT_TOO_SOON` 422 · `REVISE_WORKSHOP_NOT_OFFERED` 422 |
| Chat `conversation` (us-025) | `CONVERSATION_NOT_FOUND` 404 · `CONVERSATION_EXCERPT_NOT_AVAILABLE` 404 · `SEMANTIC_SEARCH_DISABLED` 404 · `CONVERSATION_BUSY` 409 · `RATE_LIMITED` 429 (+`Retry-After`) · `CHAT_TIMEOUT` 504 |
| Dự toán `cost_estimate` (us-045) | `MILESTONE_REQUIRED` 422 · `WORKSHOP_REQUIRED` 422 |
| Báo giá HITL `quote` (us-049) | `QUOTE_NOT_FOUND` 404 · `QUOTE_NOT_DRAFT` 409 · `QUOTE_DRAFT_REFRESHED` 409 · `QUOTE_ALREADY_PENDING` 409 · `QUOTE_ALREADY_REVIEWED` 409 · `WORKSHOP_INACTIVE` 422 · `NO_MAINTENANCE_RULE` 422 · `COVERED_ITEM_LOCKED` 422 · `REVIEWER_NOTE_REQUIRED` 422 |
| Workshop Board `workshop_board` (us-037) | `REASON_REQUIRED` 400 · `WORKSHOP_INACTIVE` 403 · `INVALID_STATUS_TRANSITION` 409 · `CHECK_IN_NOT_TODAY` 409 · `CONFIRM_DEADLINE_PASSED` 409 · `NO_SHOW_TOO_EARLY` 409 · `BLOCK_EXCEEDS_FREE_CAPACITY` 409 · `BLOCK_DATE_OUT_OF_RANGE` 422 |
| Tiến độ `service_progress` (us-057) | `BOOKING_NOT_IN_PROGRESS` 409 · `PROGRESS_CHANGED` 409 · `INVALID_STAGE_TRANSITION` 422 · `NOTE_REQUIRED` 422 |
| Hỏi thăm `follow_up` (us-041) | `FOLLOW_UP_NOT_FOUND` 404 · `FOLLOW_UP_NOT_OPEN` 409 · `FOLLOW_UP_ALREADY_RESPONDED` 409 · `FOLLOW_UP_CLOSED` 409 |
| Nhắc bảo dưỡng `notification` (us-021, us-069) | `REMINDER_NOT_FOUND` 404 · `INVALID_LEAD_DAYS` 422 · `CHANNEL_NOT_AVAILABLE` 422 |
| Webhook hãng `oem_integration` (us-017) | `WEBHOOK_SIGNATURE_INVALID` 401 · `WEBHOOK_TIMESTAMP_EXPIRED` 401 · `UNSUPPORTED_EVENT_TYPE` 422 · `WEBHOOK_PROCESSING` 503 |

## 2.3 Lỗi trong luồng chat (SSE)

Khi lượt trả lời đã bắt đầu stream, lỗi được gửi bằng **event `error`** thay vì HTTP status:

```
event: error
data: {"code": "AGENT_ERROR", "message": "Trợ lý tạm thời không trả lời được.", "traceId": "…"}
```

| Code | Khi nào | Hành vi |
| --- | --- | --- |
| `AGENT_ERROR` | LLM/agent ném lỗi giữa chừng | Không lưu câu trả lời dở. Người dùng gửi lại được |
| `CHAT_TIMEOUT` | Lượt trả lời quá `CHAT_RUN_TIMEOUT_SECONDS` (mặc định 30 giây) | Như trên |

Gửi lại cùng `clientMessageId` thì backend phát lại câu trả lời đã có, không gọi LLM lần nữa (us-025, platform API).

## 2.4 Mã lỗi phía client

`frontend/src/shared/api/client.ts` tự sinh 2 mã khi request không tới được backend (`status = 0`):

| Code | Khi nào |
| --- | --- |
| `NETWORK_ERROR` | `fetch` thất bại: mất mạng, DNS, CORS, backend sập |
| `TIMEOUT_ERROR` | Vượt `timeoutMs` của request |

---

# 3. Quy tắc cho backend

1. **Ném lỗi miền, không ném `HTTPException`.** Mỗi module có `errors.py` gồm một lớp gốc (`BookingError`, `QuoteError`…), các lớp con khai `code`, và bảng `ERROR_STATUS`. Handler trong `main.py` chuyển lỗi thành envelope.
2. **Thêm mã mới:** khai lớp lỗi, thêm vào `ERROR_STATUS`, bổ sung vào §2 của tài liệu này **và** vào mục Error Handling của spec API liên quan, trong cùng PR.
3. **Dùng lại mã ở §2.1** khi ý nghĩa trùng. Không đặt tên mới cho cùng một tình huống (ví dụ dùng `VEHICLE_NOT_FOUND`, không tạo `CAR_NOT_FOUND`).
4. **Cùng một mã phải cùng một status ở mọi module.** Các trường hợp đang lệch nằm ở §6.
5. **`message` là tiếng Anh, không chứa dữ liệu cá nhân** (email, SĐT, biển số đầy đủ). Dữ liệu cần cho UI đưa vào `details`.
6. **Lỗi tạm thời** của phụ thuộc trả `503` kèm `Retry-After` nếu biết. Không để thành `500`.
7. **Ghi log** lỗi `5xx` ở mức `error` kèm `traceId`. Lỗi `4xx` nghiệp vụ ghi ở mức `info`. Log đã che PII khi `LOG_REDACT_PII=true`.

---

# 4. Quy tắc cho frontend

## 4.1 Luồng xử lý trong API client

`rawRequest` / `apiRequest` trong `frontend/src/shared/api/client.ts`:

1. Gắn `Authorization: Bearer <Firebase ID token>` và một `X-Request-ID` mới cho mỗi request.
2. Nhận `401`: lấy token mới (`forceRefresh`) và **thử lại đúng 1 lần**. Vẫn `401`, hoặc lấy token mới thất bại: gọi `onUnauthorized()` để kết thúc phiên và về màn đăng nhập. Route đăng nhập/đăng xuất truyền `skipSessionExpiry` để tự xử lý.
3. Response lỗi: chuyển thành `ApiError { status, code, message, details, traceId, retryAfter }`. Body không theo envelope (`{"detail": …}` hoặc text) được quy về `UNAUTHORIZED` / `INVALID_REQUEST` / `INTERNAL_SERVER_ERROR` / `HTTP_<status>`.
4. Kiểm tra lỗi bằng `isApiError(error, 'SLOT_FULL')`. Không so sánh chuỗi `message`.

## 4.2 Chọn cách hiển thị

| Tình huống | Thành phần (`frontend/src/shared/ui`) | Quy tắc |
| --- | --- | --- |
| Không tải được dữ liệu của cả màn/khối | `ErrorState` | Có nút "Thử lại" (`refetch`) và dòng "Mã lỗi: {traceId}" để người dùng gửi cho hỗ trợ |
| Danh sách rỗng hợp lệ | `EmptyState` | Không dùng kiểu lỗi cho dữ liệu rỗng |
| Thao tác (bấm nút) thất bại nhưng màn vẫn dùng được | `Toast` tone `error` | Tự ẩn sau 4,5 giây, tối đa 3 toast cùng lúc. Không dùng cho lỗi cần người dùng làm gì tiếp |
| Lỗi cần đọc kỹ hoặc kèm hành động (phiên hết hạn, dữ liệu ODO cũ, đang xác minh với hãng) | `Notice` tone `warning`/`error` | Banner trong trang, có thể kèm nút |
| Lỗi theo trường của form | Thông báo dưới trường | Lấy tên trường từ `ApiError.field` (`details.field`) |
| `Retry-After` / `retryAfter` | Nút bị khoá kèm đếm ngược | Áp dụng cho `429` và `VERIFICATION_ATTEMPTS_EXCEEDED` |
| `409` có `details.alternatives` (`SLOT_FULL`) | Danh sách khung giờ thay thế | Không chỉ báo lỗi; đưa lựa chọn tiếp theo |
| Mất mạng | `useOnlineStatus()` + `Notice` | Khoá các nút gửi khi offline, tự bỏ khoá khi có mạng lại |
| `503` / `NETWORK_ERROR` / `TIMEOUT_ERROR` | `ErrorState` hoặc `Toast` | Ghi rõ "thử lại sau". Không đăng xuất người dùng |

## 4.3 Thông điệp cho người dùng

- Mỗi feature có hàm ánh xạ `code → câu tiếng Việt`, ví dụ `bookingErrorMessage()` trong `frontend/src/features/bookings/utils.ts`. Trả `null` thì hiển thị câu chung "Không thể thực hiện. Vui lòng thử lại."
- **Không** hiển thị `error.message` của backend (tiếng Anh, dành cho kỹ thuật).
- Viết ngắn, nói điều người dùng làm được tiếp theo: "Khung giờ này vừa hết chỗ" + gợi ý khung khác, thay vì "Đặt lịch thất bại".
- Lỗi do AI không chắc chắn (không có nguồn, ngoài phạm vi) **không** phải lỗi kỹ thuật. Trợ lý trả lời bình thường theo PRD §7, không hiện `ErrorState`.
- Màu và kiểu chữ theo [DESIGN.md](../../../DESIGN.md): `error` dùng cho trạng thái lỗi, quá hạn, bị từ chối. Không dùng màu đỏ cho cảnh báo thông thường.

---

# 5. Quy tắc cho AI Agent

- Tool gọi API thật thì đọc `error.code` để chọn câu trả lời. Không chép `message` tiếng Anh vào câu trả lời.
- Gặp `409` xung đột trạng thái (`QUOTE_NOT_DRAFT`, `PROPOSAL_EXPIRED`, `SLOT_FULL`…): đọc lại trạng thái thật bằng tool tra cứu trước khi trả lời. Không giả định thao tác đã thành công.
- Gặp `503` / timeout: báo tạm thời chưa thực hiện được, **không** tự thử lại thao tác có side effect (đặt lịch, gửi báo giá) khi chưa có xác nhận mới của người dùng (PRD §7).
- Chi tiết theo từng agent: mục 22 "AI-specific Error & Edge Cases" trong `docs/specs/ai-agent/ai-00x-*.agent.md`.

---

# 6. Khoảng trống đã biết

| # | Vấn đề | Ảnh hưởng | Đề xuất |
| --- | --- | --- | --- |
| G-01 | Không có handler cho `Exception` chung trong `main.py` | Lỗi chưa bắt trả `500` dạng text, không có envelope; người dùng chỉ thấy lỗi chung | Thêm handler trả `INTERNAL_SERVER_ERROR` theo envelope, kèm `traceId` từ `request.state.correlation_id`, và log `error` |
| G-02 | Đặt lịch qua API thường khi Redis mất kết nối | Ra `500`, không tạo lịch (architecture-deep-dive §4.2) | Bắt lỗi kết nối Redis ở `BookingService` và trả `SERVICE_UNAVAILABLE` 503 như luồng đặt từ chat |
| G-03 | Validation lỗi chỉ theo envelope `400` với các prefix trong `_ONBOARDING_PREFIXES` | Route chat, thông báo, xe trả `422 {"detail": [...]}` | Áp dụng envelope `400 INVALID_REQUEST` cho mọi route `/api/v1`. Phải cập nhật spec API của các route đó cùng lúc |
| G-04 | Token Firebase sai trả `{"detail": …}` qua `HTTPException` | Không có `code`/`traceId` trong body | Ném lỗi miền `UNAUTHORIZED` / `INVALID_TOKEN` |
| G-05 | `WORKSHOP_INACTIVE` là `422` ở `quote` nhưng `403` ở `workshop_board` | Cùng mã, khác status | Chốt một status cho cả hai module, cập nhật spec API us-037 hoặc us-049 theo quyết định |
| G-06 | Hai mã cho cùng tình huống quá tần suất: `RATE_LIMITED` (chat) và `RATE_LIMIT_EXCEEDED` (rate limiter dùng chung) | Frontend phải xử lý cả hai | Gộp về một mã, giữ mã kia làm alias trong một phiên bản |
| G-07 | Handler đọc `traceId` từ header request thay vì ID do middleware sinh | `traceId: null` khi client không gửi `X-Request-ID` (Postman, webhook, server khác) | Đọc `request.state.correlation_id` |
| G-08 | Frontend chưa có Error Boundary | Lỗi render làm trắng toàn trang | Thêm Error Boundary ở `App.tsx` cho mỗi nhánh route, hiển thị `ErrorState` kèm nút tải lại |

---

# 7. Tài liệu liên quan

- [architecture-deep-dive.md §4](../../architecture-deep-dive.md#4-độ-tin-cậy-và-xử-lý-lỗi): quy ước chung, hành vi khi phụ thuộc sự cố, chống trùng.
- [conversation-messaging.api.md](conversation-messaging.api.md): lỗi của API hội thoại và WebSocket.
- Spec API theo feature: mục "Error Handling" / "Errors" trong `docs/specs/sprint-*/api/*.api.md`.
- Spec FF theo feature: mục "Exception Flow" và "Business Error & Edge Cases" trong `docs/specs/sprint-*/feature-functional/*.ff.md`.

---

# 8. Change Log

| Version | Date | Author | Changes |
| --- | --- | --- | --- |
| `v1.0` | `2026-10-07` | Team 4 Người | Bản đầu: envelope, quy ước status, danh mục mã lỗi lấy từ `errors.py` của 14 module, lỗi SSE, quy tắc backend/frontend/agent, khoảng trống G-01…G-08 |
