# API Technical Specification — Chuyển sang người thật

> Backend cho Feature `FEAT-P2-PL02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](pl-02-phase2-spec.ff.md). **Entity:** [Entity Spec](pl-02-phase2-spec.entity.md).
>
> **Tái dùng:** follow-up F9 (`modules/follow_up`, `classifier.py` → `has_issue`, `rating`, us-041), router ý định AI-001, `SafetySignalDetector` (AD-02), PS-05 tín hiệu bực, thông báo trong app (chủ xe) và Workshop Portal (chủ xưởng), Workshop Board. Không dùng / tạo `support_ticket` (AC-PL02-03).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-PL02` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/handoff/` (mới: `service.py`, `summary.py`, `route.py`, `jobs.py`) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `SVC-PL02-01` | Internal | `HandoffService.create(user, reason, *, conversation?, follow_up?, booking?, urgency?)` | Cổng tạo duy nhất | UC-PL02-01, 02, BR-PL02-01, 02 |
| `TOOL-PL02-01` | Agent tool | `request_human` | Chủ xe yêu cầu gặp người / agent tự chuyển | UC-PL02-01 |
| `API-PL02-01` | `POST` | `/conversations/{conversationId}/handoff` | Chip "Gặp người của xưởng" | UC-PL02-01 |
| `API-PL02-02` | `GET` | `/handoffs?status=ACTIVE` | Trạng thái của chủ xe (SCR-PL02-01) | BR-PL02-04 |
| `API-PL02-03` | `POST` | `/handoffs/{handoffId}/cancel` | Chủ xe huỷ | AF-PL02-01 |
| `API-PL02-04` | `GET` | `/workshop-owner/handoffs?status` | Hàng "cần liên hệ khách" (SCR-PL02-02) | UC-PL02-03 |
| `API-PL02-05` | `POST` | `/workshop-owner/handoffs/{handoffId}/status` | `SEEN` / `CONTACTED` / `RESOLVED` | UC-PL02-03 |
| `HOOK-PL02-01` | Internal | Follow-up đã phân loại ⇒ tự chuyển | | UC-PL02-02, AC-PL02-01 |
| `JOB-PL02-01` | Celery | `handoff.reminders` (mỗi 15 phút) | Nhắc / báo vận hành | EF-PL02-01 |

---

# 2. Authorization & Guards

- Chủ xe: chỉ yêu cầu của mình.
- Chủ xưởng: chỉ `workshop_id` của mình (FF §16). KTV (WS-03) không thấy hàng này ở P2-B.
- Chủ xưởng thấy SĐT khách theo quyền MVP hiện có của Board (SCR-PL02-02) — không mở rộng quyền.

---

# 3. SVC-PL02-01 — `HandoffService.create`

1. Có yêu cầu đang mở cho cùng `conversation_id` (hoặc cùng `follow_up_id`) ⇒ trả yêu cầu đó (BR-PL02-05), cập nhật `urgency` lên `URGENT` nếu cần; không tạo mới.
2. Chọn xưởng (entity §3).
3. Dựng `summary` (§4).
4. Chèn `handoff_request` (`open`), một transaction.
5. Sau commit (≤ 1 phút tổng, FF §18): thông báo Workshop Portal "Cần liên hệ khách" (+ email chủ xưởng khi `URGENT`); tin hệ thống trong hội thoại chủ xe với thẻ `HANDOFF_STATUS` (§6); PL-03 `handoff_created` (`reason`).
6. Không bao giờ tạo `support_ticket`.

## 3.1 Nguồn kích hoạt (BR-PL02-01)

| `reason` | Kích hoạt |
|---|---|
| `OWNER_REQUEST` | Chip / câu "gặp người", "nói chuyện với nhân viên" (ý định AI-001 `HUMAN_REQUEST`) ⇒ `TOOL-PL02-01` hoặc `API-PL02-01` |
| `NO_SOURCE` | Trong cùng hội thoại, `HANDOFF_NO_SOURCE_RETRY` lượt liên tiếp trả lời "không có nguồn" (đếm trong `conversation_flow_state` / Redis theo hội thoại) ⇒ agent **đề nghị** chuyển bằng chip "Gặp người của xưởng"; chủ xe bấm mới tạo |
| `WARRANTY_DISPUTE` | Ý định `WARRANTY_DISPUTE` (AD-03 HOOK-AD03-01) ⇒ tạo ngay |
| `FRUSTRATION` | Tín hiệu bực của PS-05 (`frustration = HIGH` trên lượt) ⇒ đề nghị bằng chip, chủ xe bấm mới tạo |
| `LOW_RATING` / `FOLLOW_UP_ISSUE` | HOOK-PL02-01 |

`urgency = URGENT` khi `SafetySignalDetector` khớp trong nội dung liên quan (EF-PL02-02); lời khuyên an toàn đã được gửi trước theo AD-02.

---

# 4. Tóm tắt (BR-PL02-02, AC-PL02-02)

`summary.py`:
- `vehicle`, `booking`: điền bằng code từ DB (không LLM).
- `issue`: LLM tóm tắt ≤ 300 ký tự từ 20 tin gần nhất (hoặc phản hồi follow-up), prompt "chỉ nêu sự việc khách kể, không đánh giá ai đúng sai"; lỗi / timeout 5 s ⇒ mẫu "{lý do}: {tin gần nhất của khách (≤ 200 ký tự)}".
- `agentAnswered`: liệt kê ≤ 3 câu trả lời gần nhất của trợ lý dạng rút gọn (câu đầu mỗi tin) + đánh dấu có / không trích nguồn.
- `customerQuote`: nguyên văn câu khách (≤ 300 ký tự).
- Guard: không đưa VIN, SĐT, email vào `summary` (Board đã có SĐT riêng theo quyền).

---

# 5. HOOK-PL02-01 — từ follow-up

Khi `FollowUpService` lưu kết quả phân loại: `has_issue = true` **hoặc** `rating ≤ LOW_RATING_MAX` ⇒ `create(reason = FOLLOW_UP_ISSUE | LOW_RATING, follow_up = …, booking = follow_up.booking_id)`. Chạy đồng bộ sau commit (AC-PL02-01 ≤ 1 phút). Lặp lại cho cùng follow-up ⇒ unique index chặn.

---

# 6. Chủ xe — API-PL02-01..03

- `POST /conversations/{conversationId}/handoff` `{ "note": "…" }` (tuỳ chọn) ⇒ `201 HandoffDto`.
- `GET /handoffs?status=ACTIVE|ALL` ⇒ `[HandoffDto]`.
- `POST /handoffs/{id}/cancel` ⇒ `cancelled` (chỉ khi `open` / `seen`; `contacted` trở đi ⇒ `409 HANDOFF_IN_PROGRESS`).

`HandoffDto` (chủ xe): `{ handoffId, status, statusLabel, workshop: { name, hotline }, reason, createdAt, timeline: [{ status, at }] }` — **không** có `resolution_note`.

Thẻ `HANDOFF_STATUS` (CH-02, `entity = { type: HANDOFF, id }`): làm giàu trạng thái hiện tại; `actions`: "Huỷ yêu cầu" khi được phép, LINK gọi hotline.

---

# 7. Chủ xưởng — API-PL02-04/05

- `GET /workshop-owner/handoffs?status=OPEN|ACTIVE|ALL` ⇒ `[{ handoffId, status, reason, urgency, summary, customer: { displayName, phone (theo quyền Board) }, booking, createdAt, ageMinutes }]`, `URGENT` trước rồi cũ nhất trước. Mở chi tiết lần đầu ⇒ tự `open → seen`.
- `POST …/status` `{ "status": "CONTACTED" | "RESOLVED", "note": "…" }` — chỉ tiến (không lùi); `RESOLVED` từ `seen` / `contacted`. Thông báo chủ xe mỗi lần đổi (BR-PL02-04).

`GET /workshop-owner/bookings` thêm cờ `needsContact` khi lịch có handoff đang mở (nhãn trên Board).

---

# 8. JOB-PL02-01 — nhắc

Theo giờ làm việc của xưởng (`workshop_operating_hour`): `open` quá 24 giờ làm việc ⇒ nhắc lại chủ xưởng (`reminded_at`); quá 48 giờ làm việc ⇒ log `handoff.escalated` mức `WARNING` + cảnh báo vận hành (Grafana / email vận hành) (`escalated_at`) (EF-PL02-01, Q-PL02-01: chưa có vai trò vận hành nhận chuyển).

---

# 9. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 404 | `HANDOFF_NOT_FOUND` / `CONVERSATION_NOT_FOUND` | |
| 409 | `HANDOFF_IN_PROGRESS` | Huỷ khi xưởng đã liên hệ |
| 409 | `INVALID_STATUS_TRANSITION` | Lùi trạng thái |

---

# 10. Test Checklist

| Layer | What | Count |
|---|---|---|
| Service | Follow-up 2 sao ⇒ yêu cầu `open` ≤ 1 phút (AC-PL02-01) | +1 |
| Service | `summary` luôn đủ 4 thành phần, kể cả LLM lỗi (AC-PL02-02) | +2 |
| Service | Một yêu cầu đang mở mỗi hội thoại (BR-PL02-05) | +1 |
| Service | Chọn xưởng: lịch → yêu thích → gần nhất (EDGE-PL02-01) | +3 |
| Service | Không có dòng `support_ticket` nào sau mọi luồng (AC-PL02-03) — kiểm schema không có bảng | +1 |
| Service | `NO_SOURCE` sau N lượt chỉ đề nghị, không tự tạo | +1 |
| Job | Nhắc 24 giờ, báo vận hành 48 giờ làm việc | +2 |
| API | Chủ xe không thấy `resolution_note`; xưởng khác ⇒ `404` | +2 |

---

# 11. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
