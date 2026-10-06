# Báo cáo đối chiếu Spec ↔ Code và chức năng chưa triển khai — EV Care MVP

| Mục | Giá trị |
|---|---|
| Thời điểm lập | **03/10/2026 02:45 (GMT+7)** |
| Người lập | Claude Code (theo yêu cầu của Lê Đức Tùng) |
| Nhánh | `develop` (commit `b64a5a7`) |
| Phạm vi | `docs/specs/**`, PRD ↔ `backend/src` (route, entity, migration, Celery, agent), `frontend/src` |
| Báo cáo trước | [Phần chưa xử lý 30/09](2026-09-30_1102_bao-cao-phan-chua-xu-ly.md) · [Rà soát logic 30/09](2026-09-30_1102_bao-cao-ra-soat-logic-nghiep-vu.md) |

Cách kiểm tra: dump OpenAPI của app thật (75 endpoint) và so với bảng endpoint của từng API spec; so `__tablename__` của model với `create_table` trong migration; đọc beat schedule Celery; đọc tool của agent; dò các lệnh gọi API và việc dùng `mocks/` ở frontend; chạy test (BE: 458 pass / 2 fail / 2 lỗi collect; FE: typecheck sạch, 59/59 test pass).

---

## 1. Tóm tắt

1. **Backend API gần như khớp hoàn toàn với spec.** Mọi endpoint trong API spec của US-001 → US-057 đều đã có route, có xác thực, có job nền tương ứng; tham số cấu hình khớp giá trị trong spec (500 km/14 ngày, nhắc trước 2 ngày, giữ chỗ 10', xưởng xác nhận trong 12h, đổi lịch trước 60' và tối đa 2 lần, hỏi thăm sau 12h…). Phần lớn đề xuất `[Đề xuất]` của báo cáo 30/09 đã được **code áp dụng** (cột `odo_milestone`, `reschedule_count`, `booking_reschedule`, `quote_item.is_covered_by_warranty`, `service_progress.actor_*`, QR theo `bookingId`, auth cho hội thoại).
2. **Có 3 lỗi chặn demo:** (a) thiếu migration cho 2 bảng mà job đang ghi; (b) agent lỗi import khi dùng Gemini; (c) tool của agent đang là **mock**, không dùng chung service với UI như PRD/spec yêu cầu.
3. **Khoảng trống lớn nhất là frontend:** FE mới nối ~25/75 endpoint. Các màn F5, F5b, F6b, F8, F8b, F9 hoặc còn mock hoặc chưa có trang.
4. **Tài liệu gốc chưa được cập nhật theo code** (PRD vẫn v3.5, `booking.entity.md`, AI-004, AI-005 lỗi thời) ⇒ code đang đi trước spec ở nhiều chỗ.

---

## 2. Ma trận độ phủ theo tính năng PRD

Ký hiệu: ✅ khớp spec · 🟡 có nhưng lệch / chưa đủ · 🧪 mock · ❌ chưa có

| PRD | Tính năng | Backend API + job | AI Agent | Frontend | Phụ trách (chucnang.md) |
|---|---|---|---|---|---|
| F1 | Đăng ký/đăng nhập chủ xe (us-001, us-005) | ✅ | — | ✅ Login + onboarding nối API; ❌ `/profile` (us-005 FE) | Tùng |
| F2 | Đăng ký/đăng nhập chủ xưởng (us-009, us-013) | ✅ | — | ✅ nối API; ❌ `/customers` (us-009 FE) | Tùng |
| F3 | Hồ sơ xe & trạng thái đến hạn (us-017) | ✅ + đồng bộ OEM 120' + webhook | 🧪 `get_due_maintenance` dùng lịch hard-code | ✅ Xe của tôi; 🧪 Dashboard, 🧪 `/history` | Trung |
| F4 | Chat RAG + lưu hội thoại (us-025, platform) | ✅ (SSE + WebSocket `/stream`) ; ❌ job xoá 180 ngày | 🟡 RAG đọc Qdrant, không qua `document_chunk` | ✅ `/ai` nối API thật | Thái |
| F5 | Dự toán chi phí (us-045) | ✅ `API-EST-01…03` | 🧪 `estimate_service_cost` dùng bảng giá hard-code | 🧪 `/estimate`; ❌ `/estimate/compare` | Thái |
| F6 | Đặt lịch theo sức chứa (us-029) | ✅ | 🧪 `find_workshops` / `get_available_slots` / `create_booking_draft` không ghi DB | ✅ Wizard 3 bước nối API | Tiến |
| F5b | Báo giá HITL (us-049) | ✅ 9 API + job dọn nháp | ❌ không có tool quote (TOOL-501…503) | 🧪 `/technician/quotes`, `/technician/quote-review`; ❌ `/quotes`, `/quotes/new` | Tiến |
| F7 | Nhắc mốc + nhắc lịch 24h (us-021, us-033) | ✅ job; 🟡 adapter Discord chỉ ghi log, chưa có API liên kết Discord | — | ✅ Cài đặt thông báo; 🧪 `/notifications`; ❌ xác nhận sẽ đến, huỷ booking `confirmed` | Trung / Tiến |
| F6b | Ticket + QR, huỷ/đổi lịch (us-053) | ✅ | ❌ không có `list_my_bookings`, `cancel_booking`, `reschedule_booking` | 🟡 `/bookings/:id` chỉ đọc từ `location.state` (F5 là mất); ❌ "Lịch của tôi", `/c/:code`, đổi lịch, QR | Tiến |
| F8 | Workshop Board (us-037) | ✅ | — | 🧪 `/technician` dashboard; ❌ `/technician/board`, `/capacity`, `/check-in`, `/settings/booking` | Tùng |
| F9 | Hỏi thăm + phiếu hỗ trợ (us-041) | ✅ API + job | — | ❌ `/follow-ups/:id`, `/support-tickets`, `/technician/tickets` | — (chưa giao) |
| F8b | Tiến độ 6 bước (us-057) | ✅ API-PG-01…03 | — | ❌ | — (chưa giao) |

---

## 3. Lệch giữa Spec và Code

**Mức độ:** 🔴 chặn demo / sai dữ liệu · 🟠 lệch spec, cần chốt · 🟢 dọn dẹp

### 🔴 C-01 — Thiếu migration cho `booking_reminder_delivery` và `follow_up_delivery`

| | |
|---|---|
| Bằng chứng | Model ở `backend/src/common/core/notification/event_delivery.py:130`, `:161`; được ghi bởi `modules/booking/reminders.py:251` và `modules/follow_up/jobs.py:98`. Không file nào trong `backend/alembic/versions/` tạo hai bảng này (bảng `booking_reminder` thì có). |
| Tác động | Trên Postgres (staging/Railway), job `booking_reminder.send_due` (mỗi 15') và `follow_up.send_due` (mỗi 15') lỗi `relation does not exist` ⇒ F7 nhắc lịch 24h và F9 hỏi thăm không chạy. Test không phát hiện vì test tạo schema bằng `create_all` từ model. |
| Đề xuất | Thêm migration mới (down_revision `f1d3b5a7c9e2`); thêm một test so `alembic upgrade head` với `SQLModel.metadata` để chặn tái diễn. |

### 🔴 C-02 — Agent lỗi import khi môi trường có `GEMINI_API_KEY`

| | |
|---|---|
| Bằng chứng | `backend/src/agents/graph.py:46-48` ưu tiên Gemini khi có key và `import langchain_google_genai`, nhưng `pyproject.toml` chỉ khai báo `langchain-openai`. `graph.py:194` dựng agent ngay lúc import. |
| Tác động | Mọi lượt chat (`ChatService` import `src.agents.orchestrator` ở `conversation/service.py:285`) ném `ModuleNotFoundError`. Đây là nguyên nhân của **toàn bộ 2 test fail + 2 lỗi collect** hiện tại. Ngoài ra `graph.py` bỏ qua cấu hình `LLM_PROVIDER` (`config.py:43`) — chọn provider theo key nào có mặt. |
| Đề xuất | Khai báo `langchain-google-genai` trong `pyproject.toml`/`uv.lock`; chọn LLM theo `settings.llm_provider` (đã có sẵn factory ở `infrastructure/llm`); dựng graph lười (lazy) thay vì lúc import. |

### 🔴 C-03 — Tool của agent là mock, không dùng chung service với UI

| | |
|---|---|
| Bằng chứng | `agents/tools/booking_tools.py:14` (`MOCK_WORKSHOPS` 4 xưởng Hà Nội hard-code), `:178` `create_booking_draft` sinh `uuid` + mã `EVC-…` giả, **không ghi DB**, không khoá sức chứa; `cost_tools.py:11` `ITEM_PRICE_CATALOG` hard-code; `maintenance_tools.py` lịch bảo dưỡng hard-code. |
| Spec yêu cầu | PRD F6 + us-029 BR-011 "một service dùng chung cho Agent và UI"; us-045 BR-1001 dự toán tất định từ `maintenance_rule` + `service_price`; AI-003 TOOL-301, AI-004 TOOL-401…406, AI-005 TOOL-501…503, AI-001 TOOL-101 `get_vehicle_context`. |
| Tác động | Chủ xe đặt lịch qua chat nhận mã booking **không tồn tại**; xưởng không thấy; giá trong chat khác giá ở `/estimate` (vi phạm AC-F5-01). Agent cũng chưa có tool báo giá, xem/huỷ/đổi lịch. |
| Đề xuất | Viết lại tool như lớp mỏng gọi `CostEstimationService`, `BookingService` (`/workshops/nearby`, `/availability`, `POST /bookings` có `confirmationToken`), `QuoteService`, `UserVehicleService`; thêm tool còn thiếu theo AI-004/AI-005. |

### 🟠 C-04 — RAG lúc chạy đọc Qdrant, spec quy định `document_chunk` (pgvector)

`ai-008` dòng 44: "pgvector là nguồn duy nhất lúc chạy"; `maintenance_rule_source` trỏ FK tới `document_chunk` để trích dẫn (TOOL-202 `get_rule_sources`). Code: `agents/tools/RAG/query/rag_tool.py:17`, `hybrid.py:172` dùng `QdrantVectorStore` riêng; adapter `infrastructure/vectorstore/knowledge_store.py` trên `document_chunk` có sẵn nhưng RAG không dùng. ⇒ Hai kho tri thức song song, trích dẫn không nối được về định mức. Cần chốt: sửa AI-002/AI-008 theo Qdrant (kèm cách liên kết `maintenance_rule_source`), hoặc chuyển RAG sang `KnowledgeVectorStore`.

### 🟠 C-05 — Kênh thông báo chưa gửi được thật

`modules/notification/adapters.py:26` `LoggingDiscordAdapter` chỉ ghi log; không có API liên kết Discord (us-021 FE §4.3 ghi rõ "chưa có API", FE hiển thị dialog "sắp có"). Code khớp spec, nhưng hệ quả là **F7 (AC-F7-01) và F9 không thể nghiệm thu đầu-cuối**. Cần spec + API cho luồng OAuth2/bot Discord (ENT-417), hoặc một webhook demo.

### 🟠 C-06 — Chưa có job xoá hội thoại quá 180 ngày

us-025 BR-609 (PQ-09). `config.py:204-205` có `chat_retention_days`, `chat_purge_batch` nhưng không có code dùng và không có task trong beat schedule.

### 🟠 C-07 — Code đi trước tài liệu (doc lỗi thời so với code)

| Tài liệu | Đang ghi | Code hiện tại |
|---|---|---|
| `entity/maintenance/booking.entity.md` (v1.2) | Không có `odo_milestone`, `reschedule_count`; ví dụ mã `BK-20261003-0012` | Có cả hai cột (`booking.py:76-78`); mã `EVC-` + 8 hex (`booking/service.py:62`, `ticket.py:47`) |
| `entity/maintenance/quote*.entity.md`, `service_progress.entity.md` | Chưa có cột mới | Đã có `submitted_at`, `result_seen_at`, `reviewer_note`, `price_source`, `is_covered_by_warranty`, `actor_type`, `actor_workshop_owner_id` |
| `ai-agent/ai-005` TOOL-501 | Nhận `items[]` từ LLM | `POST /quotes` chỉ nhận (xe, xưởng, mốc), backend tự tính (BR-1101) |
| `ai-agent/ai-004` | AI-Q-401/402/403 vẫn Open; TOOL-406 trả "booking mới" | Theo us-029/us-053: giữ chỗ khi bấm Xác nhận, đổi lịch tại chỗ |
| PRD (bảng thông tin **v3.5**) | `:228`, `:234` AC-F6-03 pending hết hạn ⇒ huỷ; `:256` AC-F7-01; `:322` Next.js | Cửa sổ huỷ 10' + xưởng xác nhận 12h; Vite + React 19 |
| `us-001` API-004 | Dropdown chọn model | Vẫn có `GET /onboarding/vehicle-models` (PRD F1: "không có dropdown") |

Đây là các mục D-01…D-08 của báo cáo 30/09 — **chưa mục nào được sửa**.

### 🟠 C-08 — Chủ xe vẫn không huỷ được booking `pending` sau 10 phút (L-03 / Q-1208)

`booking/service.py:583-586` chỉ cho huỷ khi còn trong `hold_expires_at`; `ticket.py:336` `cancel_by_owner` chỉ nhận `confirmed`. Code đúng theo us-029, nhưng tình huống "kẹt 12h" ở xưởng `manual` vẫn còn. Chờ PO chốt Q-1208.

### 🟢 C-09 — Dọn dẹp

- Module mẫu `/api/v1/vehicles` (CRUD, `modules/examples`) và `agents/tools/example_tool.py`, `agents/example_agent/` vẫn mount trên API thật, không thuộc spec nào. Nên gỡ khỏi `main.py` trước staging.
- `backend/deprecated/tests` lỗi collect khi chạy `pytest` ở thư mục `backend/` (import `api.src…`). Nên thêm vào `norecursedirs`.
- `config.py:39-45` mặc định `openai` / `gpt-4o-mini` trong khi PRD §9 chọn Gemini Flash-tier — vẫn chưa có Tech Spec chốt (U-01).

---

## 4. Chức năng chưa triển khai

### 4.1 Frontend (khoảng trống lớn nhất)

| # | Màn / luồng | Spec | Backend sẵn sàng? | Hiện trạng |
|---|---|---|---|---|
| FE-01 | Dự toán `/estimate`, so sánh `/estimate/compare` | us-045 FE | ✅ | 🧪 mock `mocks/maintenance-estimate.ts`; compare chưa có |
| FE-02 | Báo giá chủ xe `/quotes`, `/quotes/new`, `/quotes/:id` | us-049 FE | ✅ | ❌ |
| FE-03 | Duyệt báo giá chủ xưởng | us-049 FE §3.2 | ✅ | 🧪 mock, còn cho thêm/xoá dòng (trái BR-ENT-417, L-17) |
| FE-04 | "Lịch của tôi" `/bookings`, Ticket theo id, `/c/:bookingCode`, QR, đổi lịch | us-053 FE | ✅ | ❌; Ticket hiện chỉ dựng từ `location.state` |
| FE-05 | Xác nhận sẽ đến, huỷ booking `confirmed` | us-033 FE | ✅ | ❌ |
| FE-06 | Workshop Board, sức chứa, check-in QR, cài đặt auto/manual | us-037 FE | ✅ | ❌ (`/technician` dashboard còn mock) |
| FE-07 | Tiến độ 6 bước (xưởng cập nhật, chủ xe xem) | us-057 FE | ✅ | ❌ |
| FE-08 | Hỏi thăm sau dịch vụ, phiếu hỗ trợ (2 phía) | us-041 FE | ✅ | ❌ |
| FE-09 | Dashboard chủ xe | us-017 FE | ✅ `/user-vehicles` | 🧪 `mocks/dashboard.ts` |
| FE-10 | Hồ sơ người dùng `/profile` | us-005 FE | ✅ `/oauth/profile` | ❌ |

### 4.2 Backend / AI

| # | Hạng mục | Ghi chú |
|---|---|---|
| BE-01 | Migration 2 bảng delivery | C-01 |
| BE-02 | Tool agent thật + tool còn thiếu (TOOL-101, 202, 203, 404–406, 501–503) | C-03 |
| BE-03 | Job xoá hội thoại 180 ngày | C-06 |
| BE-04 | Adapter Discord thật + API liên kết | C-05, cần spec trước |
| BE-05 | Seed `maintenance_rule` + `service_price` | U-08/U-09 vẫn mở: `seed.sql` không có `INSERT`, không có script seed ⇒ F3 `UNKNOWN`, F5 `NO_RULE` trên DB thật |

### 4.3 Thiếu spec (có màn hình nhưng chưa có đặc tả API)

| # | Màn | Hiện trạng |
|---|---|---|
| SP-01 | `/history` — danh sách lịch sử dịch vụ | us-017 chỉ có `lastService` trong hồ sơ xe; không có API liệt kê `vehicle_service_record` cho chủ xe. FE đang mock |
| SP-02 | `/notifications` — hộp thư thông báo in-app | Không có entity/API (Q-ENT-1103 để "phase sau"); FE mock |
| SP-03 | `/customers` (chủ xưởng) | Có trong menu và us-009 FE, không có FF/API |
| SP-04 | Liên kết Discord (ENT-417) | us-021 ghi "chưa có API" |

### 4.4 Eval và tài liệu (cập nhật từ báo cáo 30/09)

| Mã | Hạng mục | 30/09 | Hôm nay |
|---|---|---|---|
| U-02 | Bộ eval | Chưa có | 🟡 `backend/tests/test_agents/test_rag/evaluation/golden_set.jsonl` có **100 câu RAG** (đạt ≥ 60; MRR 0,90, context recall 82,8 %). **Chưa có** ≥ 15 câu bẫy và ≥ 50 câu NLU đặt lịch. `eval/datasets/` vẫn trống — nên dời bộ eval về đây hoặc sửa README |
| U-01 | Tech Spec chốt LLM | Chưa có | Chưa có (xem C-02, C-09) |
| U-03…U-07 | Danh sách tài liệu ingest, Prompt Spec, Test Cases, Runbook staging, khảo sát | Chưa có | Có `docs/deployments/RAILWAY_*` cho triển khai; các mục khác chưa có |
| U-10 | Migration các cột mới | Chưa có | ✅ đã có trong `f1d3b5a7c9e2` (trừ C-01) |
| L-22 | Auth route hội thoại | Thiếu | ✅ đã gắn |
| L-10 | Endpoint QR | Theo mã | ✅ `/bookings/{bookingId}/qr` |
| L-04, L-06, L-13 | `odo_milestone`, cờ bảo hành dòng báo giá, actor tiến độ | Đề xuất | ✅ code đã làm; tài liệu entity chưa cập nhật (C-07) |
| L-05 | TOOL-501 nhận `items[]` | Đề xuất | ✅ API làm đúng; agent chưa có tool (C-03); AI-005 chưa sửa |

---

## 5. Đề xuất thứ tự xử lý

| Ưu tiên | Việc | Mã | Người gợi ý |
|---|---|---|---|
| 1 | Migration 2 bảng delivery + test so migration với model | C-01 | Trung / Tiến |
| 2 | Khai báo `langchain-google-genai`, chọn LLM theo `LLM_PROVIDER`, dựng graph lười | C-02 | Thái |
| 3 | Seed định mức + bảng giá cho 3–5 xưởng mock | BE-05 | Trung / Thái |
| 4 | Nối tool agent với service thật (dự toán, đặt lịch) trước Demo 1 (11/10) | C-03 | Thái + Tiến |
| 5 | FE: Dự toán, Lịch của tôi/Ticket, Board, Báo giá | FE-01…06 | theo bảng phân công |
| 6 | PO chốt Q-1208; cập nhật PRD v3.7 + entity/agent spec theo code | C-07, C-08 | PO + owner tài liệu |
| 7 | Chốt kho vector (Qdrant hay pgvector), viết spec Discord, lịch sử dịch vụ, thông báo in-app | C-04, SP-01…04 | Tech Lead |
| 8 | Job xoá hội thoại, gỡ module mẫu, bộ eval câu bẫy + NLU | C-06, C-09, U-02 | Thái / Tùng |
