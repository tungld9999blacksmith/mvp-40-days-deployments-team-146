# API Technical Specification — Chat theo từng lịch hẹn giữa xưởng và chủ xe

> Backend cho Feature `FEAT-P2-MC01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](mc-01-phase2-spec.ff.md). **Entity:** [Entity Spec](mc-01-phase2-spec.entity.md).
>
> **Hạ tầng (P2Q-12 / ADR-02 — PO chốt 2026-10-12, giữ nguyên công nghệ):** Postgres + Redis pub/sub + WebSocket theo mẫu `conversation/ws.py` (API-MSG-001: kênh chỉ nhận, khung `auth` đầu tiên mang Firebase ID token) — tái dùng hạ tầng chat MVP.
>
> **Tái dùng:** `MessageService` pattern (lưu rồi phát), WebSocket + Redis pub/sub, lưu ảnh như `booking_line_photo`, `WorkshopActor` (WS-03), thẻ CH-02, thông báo trong app / Workshop Portal, `workshop_operating_hour` (giờ làm cho SLA).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-MC01` |
| Version | `v0.2` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/booking_thread/` (mới): `service.py`, `redact.py`, `route.py`, `ws.py`, `jobs.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `HOOK-MC01-01` | Internal | Booking ⇒ `confirmed`: mở luồng; đổi giờ / huỷ / hoàn tất / đổi KTV: tin hệ thống, người tham gia, `close_at` | | UC-MC01-01, 04, AF-MC01-01/02, EDGE-MC01-01 |
| `API-MC01-01` | `GET` | `/booking-threads?status` | Danh sách luồng của người gọi (chủ xe / xưởng / KTV) | SCR-MC01-02 |
| `API-MC01-02` | `GET` | `/booking-threads/{threadId}` · `/bookings/{bookingId}/thread` | Chi tiết + người tham gia | SCR-MC01-01 |
| `API-MC01-03` | `GET` | `/booking-threads/{threadId}/messages?before&limit` | Tin nhắn (keyset) | — |
| `API-MC01-04` | `POST` | `/booking-threads/{threadId}/messages` | Gửi chữ / ảnh | UC-MC01-02, BR-MC01-03, 07 |
| `API-MC01-05` | `POST` | `/booking-threads/{threadId}/attachments` | Tải ảnh (trả `attachmentId`) | BR-MC01-03 |
| `API-MC01-06` | `POST` | `/booking-threads/{threadId}/read` | Đánh dấu đã đọc | — |
| `API-MC01-07` | `POST` | `/booking-threads/{threadId}/messages/{messageId}/report` | Báo cáo nội dung | EF-MC01-02 |
| `WS-MC01-01` | WebSocket | `/ws/booking-threads/{threadId}` | Đẩy tin mới realtime | AC-MC01-03 |
| `JOB-MC01-01` | Celery | `threads.sla` (mỗi phút) | Nhắc xưởng quá `WS_REPLY_SLA_MIN` | UC-MC01-03 |
| `JOB-MC01-02` | Celery | `threads.close` (mỗi giờ) | Đóng luồng | UC-MC01-04 |

---

# 2. Authorization & Guards

1. Người gọi phải là người tham gia luồng (`booking_thread_participant` theo vai trò): chủ xe của booking; chủ xưởng của `workshop_id`; KTV có phân công `active` (WS-03). Không ⇒ `404 THREAD_NOT_FOUND`.
2. Gửi: luồng `open` (AC-MC01-02 ⇒ `409 THREAD_CLOSED`), người tham gia `can_send` (KTV cũ ⇒ `403 CANNOT_SEND`).
3. Vận hành (claim `ops`) chỉ đọc qua `/internal/booking-threads/{id}` khi có báo cáo / tranh chấp; mỗi lần ghi `booking_thread_access_log` (FF §16).
4. Giới hạn: 30 tin / phút / người; ảnh ≤ 8 MB, tối đa 5 ảnh mỗi tin.

---

# 3. HOOK-MC01-01 — vòng đời

| Sự kiện booking | Việc |
|---|---|
| ⇒ `confirmed` (lần đầu) | Tạo luồng + người tham gia (chủ xe, chủ xưởng, KTV được giao nếu có); tin hệ thống "Bạn có thể nhắn với xưởng về lịch hẹn này" |
| Đổi giờ (us-053) | Tin hệ thống "Lịch đã đổi sang {giờ}" (AF-MC01-01) |
| Phân công KTV đổi (WS-03) | KTV mới thêm vào (`can_send = true`), KTV cũ `can_send = false`, `left_at` (EDGE-MC01-01); tin hệ thống |
| Tiến độ (us-057) | Tin thẻ `PROGRESS_UPDATE` (bước, giờ) |
| Phát sinh gửi chủ xe (AD-04) | Tin thẻ `EXTRA_QUOTE` (cùng thẻ CH-02; quyết định vẫn qua API AD-04) |
| ⇒ `completed` / `cancelled` | `close_at = now + THREAD_CLOSE_DAYS` |

---

# 4. API-MC01-04 — gửi tin

```json
{ "clientMessageId": "…", "kind": "TEXT", "content": "Tôi để xe từ 7h45 được không?", "attachmentIds": [] }
```

1. Guards §2. Idempotent theo `clientMessageId`.
2. **Che thông tin (BR-MC01-07, EF-MC01-01):** `redact.py` thay SĐT VN (`0[0-9 .-]{8,12}`, `+84…`), email bằng `[đã ẩn]`; ghi `redactions` (không lưu bản gốc). Có che ⇒ trả `notice: "CONTACT_REDACTED"` để frontend nhắc "Hãy trao đổi trong app".
3. Lưu tin (chữ ≤ 2.000 ký tự; `IMAGE` cần ≥ 1 `attachmentId` thuộc luồng, chưa gắn tin khác).
4. Cập nhật SLA: tin của chủ xe khi `awaiting_workshop_since` rỗng ⇒ đặt `now`; tin của chủ xưởng / KTV ⇒ xoá `awaiting_workshop_since`, `sla_reminded_at`.
5. Sau commit: publish Redis `thread:{threadId}` ⇒ WS (AC-MC01-03 ≤ 2 s p90); thông báo trong app cho người tham gia không đang kết nối WS; MC-02 hook (khi `agent_enabled`).
6. Response `201 ThreadMessageDto`: `{ id, seq, kind, content, attachments: [{ url (ký 10 phút), width, height }], card, sender: { role, displayName }, createdAt, redacted: bool }`.

**AC-MC01-01:** DTO không có trường liên hệ; test quét payload gửi cho bên kia không chứa mẫu SĐT / email.

---

# 5. API-MC01-05 — ảnh

`multipart/form-data`; kiểm loại; xoá EXIF; nén cạnh dài ≤ 2.048 px; lưu bucket Phase 2; trả `{ attachmentId, url }`. Ảnh chưa gắn tin sau 24 giờ ⇒ job xoá.

---

# 6. WS-MC01-01

Như API-MSG-001: khung đầu `{ "type": "auth", "token": "<Firebase ID token>" }`, server xác định danh tính (chủ xe / chủ xưởng / KTV), kiểm người tham gia; sau đó chỉ nhận sự kiện `message.created`, `participant.changed`, `thread.closed`. Mất kết nối ⇒ client gọi `API-MC01-03` với `after = lastSeq` để bù (ngoại tuyến theo ADR-02).

---

# 7. Jobs

- `threads.sla`: luồng `open` có `awaiting_workshop_since` và số phút **trong giờ làm** (theo `workshop_operating_hour`) ≥ `WS_REPLY_SLA_MIN`, chưa nhắc ⇒ thông báo chủ xưởng (+ KTV được giao) "Khách chờ trả lời {phút} phút", `sla_reminded_at = now` (UC-MC01-03). Danh sách luồng phía xưởng trả `overdue = true`.
- `threads.close`: `close_at ≤ now` ⇒ `closed`, tin hệ thống "Cuộc trò chuyện đã đóng", publish `thread.closed`.

---

# 8. API-MC01-07 — báo cáo

`{ "reason": "ABUSIVE" | "SPAM" | "OTHER", "note": "…" }` ⇒ `booking_thread_report (open)`; thông báo chủ xưởng (nếu người bị báo không phải chủ xưởng) và hàng đợi vận hành. Không tự ẩn tin (lưu đầy đủ để giải quyết).

---

# 9. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 400 | `INVALID_REQUEST` | Nội dung rỗng / quá dài, ảnh sai loại |
| 403 | `CANNOT_SEND` | KTV không còn được giao |
| 404 | `THREAD_NOT_FOUND` | Không phải người tham gia |
| 409 | `THREAD_CLOSED` | Luồng đã đóng (AC-MC01-02) |
| 413 | `FILE_TOO_LARGE` | |
| 429 | `RATE_LIMITED` | |

---

# 10. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `redact.py`: SĐT nhiều định dạng, email; không che biển số / mã lịch | +6 |
| Service | Luồng mở khi `confirmed`; đóng sau `THREAD_CLOSE_DAYS` | +2 |
| Service | Luồng đóng không gửi được (AC-MC01-02) | +1 |
| Service | Đổi KTV ⇒ KTV cũ không gửi được (EDGE-MC01-01) | +1 |
| Security | Payload bên kia không có SĐT / email (AC-MC01-01); người ngoài ⇒ `404` | +2 |
| Job | SLA chỉ tính giờ làm; nhắc một lần | +2 |
| Perf | Tin tới bên kia ≤ 2 s p90 qua WS (AC-MC01-03) | +1 |
| Audit | Vận hành mở luồng ⇒ có access log | +1 |

---

# 11. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
| `v0.2` | `2026-10-12` | PO chốt hạ tầng chat: giữ công nghệ MVP |
