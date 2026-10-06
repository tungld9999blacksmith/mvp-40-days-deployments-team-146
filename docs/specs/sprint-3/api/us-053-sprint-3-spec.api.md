# API Technical Specification — Booking Ticket, QR check-in, huỷ & đổi lịch

> **Cập nhật phạm vi (02/10/2026):** các phần dưới đây trong tài liệu này không còn áp dụng.
>
> - Báo giá / duyệt báo giá (`quote`, `quote_item`, us-049): **đã bỏ**. Đặt lịch không gắn báo giá; mọi con số chi phí là ước tính (F5), chi phí cuối cùng do xưởng xác nhận khi kiểm tra xe.

> Backend cho Feature `FEAT-BOOK-002` — PRD F6b (US-053 → US-056).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-053-sprint-3-spec.ff.md) là chuẩn; API chỉ trỏ `BR-12xx` / `EF-12xx` / `EDGE-12xx`.
>
> **Entity:** [Entity Spec](../entity/us-053-sprint-3-spec.entity.md) — `booking_reschedule` (ENT-428, mới); cột mới `booking.odo_milestone`, `booking.reschedule_count`; `booking.booking_code` giữ nguyên (sinh khi tạo, chỉ lộ khi `confirmed`).
>
> **Tái dùng, không định nghĩa lại:** `API-BK-02` (availability), `API-BK-04` (huỷ giữ chỗ) — [us-029 API](us-029-sprint-3-spec.api.md); `API-BR-01` (chi tiết), `API-BR-03` (huỷ `confirmed`) — [us-033 API](us-033-sprint-3-spec.api.md); `API-WB-03` (tra mã khi check-in) — [us-037 API](us-037-sprint-3-spec.api.md).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-BOOK-002` |
| Feature | `FEAT-BOOK-002` — F6b |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Author | Team 4 Người |
| Base URL | `/api/v1` |
| Auth | Firebase ID token (Bearer) |
| Created Date | `2026-09-30` |
| Updated Date | `2026-09-30` |
| Related Functional Spec | [us-053-sprint-3-spec.ff.md](../feature-functional/us-053-sprint-3-spec.ff.md) |
| Related Frontend Spec | [us-053-sprint-3-spec.fe.md](../frontend/us-053-sprint-3-spec.fe.md) |

---

# 1. Overview

## 1.1 API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-BT-01` | `GET` | `/api/v1/bookings` | "Lịch của tôi" — sắp tới / đã qua | UC-1202, BR-1213 |
| `API-BR-01` (mở rộng) | `GET` | `/api/v1/bookings/{bookingId}` | Chi tiết = **Booking Ticket**; thêm trường ticket §3 | UC-1201, BR-1201, BR-1202 |
| `API-BT-02` | `GET` | `/api/v1/bookings/{bookingId}/qr` | Ảnh QR PNG (tải/chia sẻ) | BR-1203 |
| `API-BT-03` | `GET` | `/api/v1/bookings/by-code/{bookingCode}` | Mở ticket từ URL QR `/c/{code}` (chủ xe) | BR-1203 |
| `API-BK-02` (mở rộng) | `GET` | `/api/v1/workshops/{workshopId}/availability?rescheduleBookingId=…` | Kiểm tra khung mới khi đổi lịch; token mục đích `RESCHEDULE` | BR-1204 |
| `API-BT-04` | `POST` | `/api/v1/bookings/{bookingId}/reschedule` | Đổi lịch nguyên tử | UC-1203, BR-1204 → BR-1211 |
| `HOOK-BT-01` | Internal | `_new_booking_code()` (đã có) | Mã sinh khi tạo booking; chỉ lộ khi `confirmed` | BR-1203 |

## 1.2 Tool mapping (AI-004)

| Tool | Gọi | Ghi chú |
|---|---|---|
| `TOOL-404 list_my_bookings` | `BookingQueryService.list_for_user(scope=UPCOMING)` | = `API-BT-01` |
| `TOOL-405 cancel_booking` | `pending` ≤ 10' ⇒ logic `API-BK-04`; `confirmed` ⇒ logic `API-BR-03` | Yêu cầu `confirmation_token` (BR-1212) |
| `TOOL-406 reschedule_booking` | `BookingService.reschedule(...)` = `API-BT-04` | Trả **cùng** `booking_id` (không phải "booking mới" như AI-004 §10.1 ghi) |

## 1.3 Configuration

| Env | Default | FF |
|---|---|---|
| `RESCHEDULE_MIN_LEAD_MINUTES` | `60` | BR-1206 |
| `RESCHEDULE_MAX_COUNT` | `2` | BR-1207 |
| `BOOKING_SEARCH_HORIZON_DAYS` | `7` (us-029) | BR-1206 |
| `APP_BASE_URL` | theo môi trường | BR-1203 |
| `BOOKING_DOCUMENTS_TO_BRING` | JSON list 3 mục (BR-1208) | BR-1208 |
| `MY_BOOKINGS_PAST_DAYS` | `90` | BR-1213 |

---

# 2. Authentication & Authorization

- Chủ xe `active` (`require_active_user`); `booking.user_id = currentUser.user_id`, sai ⇒ `404 BOOKING_NOT_FOUND` (không lộ tồn tại).
- Chủ xưởng dùng API Board (us-037), không dùng nhóm này.
- Tool AI-004 gọi service dưới danh nghĩa chủ xe của phiên chat.

---

# 3. API-BR-01 (mở rộng) — trường Ticket

> Endpoint, quyền và `allowedActions` gốc định nghĩa ở us-033 §3. F6b **bổ sung** các trường và quy tắc sau (không đổi các trường hiện có).

## 3.1 Trường bổ sung

| Field | Type | Nullable | Description | FF |
|---|---|---:|---|---|
| `qrPayload` | `string` | Yes | `{APP_BASE_URL}/c/{bookingCode}`; chỉ khi `status = CONFIRMED` | BR-1201, BR-1203 |
| `qrUrl` | `string` | Yes | `/api/v1/bookings/{id}/qr` — chỉ khi `CONFIRMED` (đã có ở us-033) | |
| `odoMilestone` | `integer` | Yes | Mốc của booking | BR-1202 |
| `items` | `array` | No | `[{ itemName, covered }]` — từ `quote_item` nếu gắn báo giá, ngược lại từ `maintenance_rule` của `odoMilestone`; `[]` nếu không có mốc | BR-1202 |
| `cost` | `object` | No | `{ amount: number \| null, label: "APPROVED_QUOTE" \| "ESTIMATE" \| "NONE", quoteId }` | BR-1202 |
| `documentsToBring` | `string[]` | No | Từ cấu hình | BR-1208 |
| `workshop.address`, `workshop.phone` | `string` | Yes | Địa chỉ, SĐT xưởng để liên hệ | BR-1202 |
| `rescheduleCount` | `integer` | No | Số lần đã đổi | BR-1207 |
| `rescheduleDeadline` | `datetime` | Yes | `appointmentAt − RESCHEDULE_MIN_LEAD_MINUTES`; `null` khi không `CONFIRMED` | BR-1206 |
| `history` | `array` | No | Gộp `booking_status_event` + `booking_reschedule`, mới nhất trước, tối đa 20 | BR-1211 |

## 3.2 `allowedActions` — cập nhật quy tắc `RESCHEDULE`

| Action | Điều kiện (thay cho us-033 §3.4) |
|---|---|
| `RESCHEDULE` | `status = confirmed` ∧ `now < appointment_at − RESCHEDULE_MIN_LEAD_MINUTES` ∧ `reschedule_count < RESCHEDULE_MAX_COUNT` |

`rescheduleMode = "F6B"` khi F6b đã bật (`FEATURE_RESCHEDULE_ENABLED = true`).

Khi `RESCHEDULE` không có mặt vì lý do nghiệp vụ, trả `rescheduleBlockedReason`: `TOO_CLOSE_TO_APPOINTMENT` / `MAX_RESCHEDULES_REACHED` / `NOT_CONFIRMED` để FE hiển thị lý do (AC-1207).

---

# 4. API-BT-01 — `GET /api/v1/bookings`

## 4.1 Query

| Field | Type | Required | Constraints |
|---|---|---:|---|
| `scope` | `string` | No | `UPCOMING` (default) / `PAST` |
| `limit` | `integer` | No | 1..50, default 20 |
| `cursor` | `string` | No | Keyset `(appointment_at, id)` |

## 4.2 Processing

```sql
-- UPCOMING
SELECT … FROM booking b JOIN workshop w ON w.id = b.workshop_id
 WHERE b.user_id = :uid AND b.status IN ('pending','confirmed','checked_in','in_progress')
 ORDER BY b.booking_date, b.time_slot, b.id
-- PAST
 WHERE b.user_id = :uid AND b.status IN ('completed','cancelled')
   AND b.booking_date >= current_date - :past_days
 ORDER BY b.booking_date DESC, b.time_slot DESC, b.id DESC
```

## 4.3 Response `200 OK`

```json
{
  "data": {
    "items": [
      {
        "bookingId": "8d2e6f10-…",
        "bookingCode": "EVC-7F3A9C21",
        "status": "CONFIRMED",
        "appointmentAt": "2026-10-04T02:00:00Z",
        "bookingDate": "2026-10-04",
        "timeSlot": "09:00",
        "workshop": { "workshopId": "3f1e…", "name": "VinFast Smart City" },
        "cost": { "amount": 1270000, "label": "APPROVED_QUOTE" },
        "allowedActions": ["CONFIRM_ATTENDANCE", "RESCHEDULE", "CANCEL"]
      }
    ],
    "nextCursor": null
  }
}
```

---

# 5. API-BT-02 — `GET /api/v1/bookings/{bookingId}/qr`

- Chỉ khi `status = confirmed` ⇒ `200 image/png` (QR của `qrPayload`, mức sửa lỗi M, 512×512), `Cache-Control: private, max-age=3600`.
- Khác `confirmed` ⇒ `409 QR_NOT_AVAILABLE`.
- FE ưu tiên tự vẽ QR từ `qrPayload`; endpoint này dùng cho tải về/chia sẻ.

---

# 6. API-BT-03 — `GET /api/v1/bookings/by-code/{bookingCode}`

Dùng khi chủ xe mở URL `/c/{code}` từ QR. Chuẩn hoá upper-case; `^EVC-[0-9A-F]{8}$` (định dạng hiện tại của code — Q-1204). Booking có mã đó **và** thuộc user ⇒ `200 { bookingId }`; ngược lại ⇒ `404 BOOKING_NOT_FOUND` (EDGE-1208 — không lộ booking người khác). Rate limit 30 req/phút/user.

---

# 7. API-BK-02 (mở rộng) — availability cho đổi lịch

Thêm query `rescheduleBookingId` (uuid, tuỳ chọn):

| Khi có `rescheduleBookingId` | Hành vi |
|---|---|
| Quyền | Booking thuộc user, `status = confirmed`, qua được BR-1206/1207 ⇒ ngược lại `409 RESCHEDULE_NOT_ALLOWED` + `details.reason` |
| Xưởng | `workshopId` phải = `booking.workshop_id` ⇒ ngược lại `422 RESCHEDULE_WORKSHOP_MISMATCH` (Q-1201) |
| Sức chứa | `occupied` **loại trừ** chính booking (BR-1204) |
| Khung trùng | `(date, timeSlot)` = khung hiện tại ⇒ `422 RESCHEDULE_SAME_SLOT` (EDGE-1202) |
| Phương án | Chỉ cùng xưởng (FF AF-1203) |
| Token | `confirmationToken` mang `purpose = RESCHEDULE`, `bookingId`, `workshopId`, `date`, `timeSlot`, TTL như us-029; không dùng được cho `POST /bookings` và ngược lại |

---

# 8. API-BT-04 — `POST /api/v1/bookings/{bookingId}/reschedule`

## 8.1 Request

```json
{ "confirmationToken": "cft_r_4b1c…", "source": "APP" }
```

| Field | Type | Required | Constraints |
|---|---|---:|---|
| `confirmationToken` | `string` | Yes | `purpose = RESCHEDULE`, cùng `bookingId`, chưa dùng, chưa hết hạn |
| `source` | `string` | No | `APP` (default) / `REMINDER_24H`; tool AI-004 ghi `CHAT` |

Header `Idempotency-Key` khuyến nghị.

## 8.2 Processing (nguyên tử — BR-1205)

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Svc as BookingService
    participant Redis
    participant DB

    Client->>API: POST /bookings/{id}/reschedule (token)
    API->>Svc: reschedule(user, bookingId, token)
    Svc->>Svc: verify token (purpose, bookingId, slot, TTL, unused)
    Svc->>Redis: lock keys sorted([oldSlotKey, newSlotKey])
    Svc->>DB: BEGIN; SELECT booking FOR UPDATE
    Svc->>Svc: check status=confirmed, BR-1206, BR-1207, booking_date/time_slot = token.old
    Svc->>DB: recompute capacity(new slot) excluding this booking (BR-1204)
    alt still available
        Svc->>DB: UPDATE booking SET booking_date, time_slot, reschedule_count+1, attendance_confirmed_at=NULL
        Svc->>DB: INSERT booking_reschedule(from, to, actor, source)
        Svc->>DB: mark token used; COMMIT
        Svc->>Svc: after-commit: BookingReminderScheduler.on_rescheduled(booking)
        Svc-->>API: 200 booking
    else full
        Svc->>DB: ROLLBACK
        Svc-->>API: 409 SLOT_FULL + alternatives (same workshop)
    end
    Svc->>Redis: unlock
```

- Khoá Redis theo thứ tự chuỗi tăng dần của `(workshop_id, date, slot)` để hai lần đổi chéo không deadlock.
- Ràng buộc DB chống vượt sức chứa của us-029 (Q-ENT-451) áp dụng cho `UPDATE` như `INSERT`.
- Token lưu giờ cũ lúc cấp; nếu booking đã đổi giờ bởi thiết bị khác ⇒ `409 BOOKING_CHANGED` (EDGE-1205).
- `on_rescheduled`: nhắc 24h cũ chưa gửi ⇒ `skipped` (`skip_reason = RESCHEDULED`), lên lịch nhắc mới theo us-033 BR-ENT-480 (BR-1210).

## 8.3 Response `200 OK`

Chi tiết như `API-BR-01` (ticket) với ngày giờ mới, **cùng** `bookingId`, `bookingCode`, `qrPayload`.

## 8.4 Errors

| Case | Code | HTTP | FF |
|---|---|---:|---|
| Token sai / sai mục đích / đã dùng | `INVALID_CONFIRMATION_TOKEN` | `409` | EF-1202 |
| Token hết hạn | `CONFIRMATION_TOKEN_EXPIRED` | `409` | EF-1202 |
| Không còn `confirmed` | `BOOKING_NOT_CONFIRMED` | `409` | EF-1203 |
| Quá hạn đổi | `RESCHEDULE_TOO_LATE` | `409` | BR-1206, EDGE-1203 |
| Quá số lần | `RESCHEDULE_LIMIT_REACHED` | `409` | BR-1207, EDGE-1204 |
| Giờ booking đã đổi từ nơi khác | `BOOKING_CHANGED` | `409` | EDGE-1205 |
| Khung mới hết chỗ | `SLOT_FULL` (+ `details.alternatives`) | `409` | EF-1201 |
| Khung mới ngoài giờ | `SLOT_OUT_OF_HOURS` | `422` | EDGE-1207 |
| Booking không thuộc user | `BOOKING_NOT_FOUND` | `404` | |
| Lỗi khoá/DB | `SERVICE_UNAVAILABLE` | `503` | EF-1204 |

> **Tên mã lỗi token:** us-029 dùng `HOLD_EXPIRED` cho "token thẻ hết hạn" — dễ nhầm với "hết cửa sổ giữ chỗ". F6b dùng `CONFIRMATION_TOKEN_EXPIRED`; đề nghị us-029 đổi theo (xem báo cáo rà soát).

---

# 9. HOOK-BT-01 — Sinh `booking_code`

Theo implementation hiện tại (`_new_booking_code()` trong `backend/src/modules/booking/service.py`), mã được sinh **ngay khi INSERT booking** ở `API-BK-03` — `booking.booking_code` giữ `NOT NULL`, không cần migration. F6b chỉ quy định **khi nào lộ mã**:

```text
code = "EVC-" + secrets.token_hex(4).upper()      -- 8 ký tự hex, ví dụ EVC-7F3A9C21
va chạm unique khi INSERT → sinh lại, tối đa 5 lần, sau đó 500 + log ERROR   [cần bổ sung vào code]
Chỉ trả bookingCode / qrPayload / qrUrl khi status = confirmed (code đã làm ở API-BK-03)
Không sinh lại khi đổi lịch (AC-1205)
```

> **Lệch đường dẫn QR:** code trả `qrUrl = /api/v1/bookings/qr/{code}.png` (theo mã, không kèm id), còn us-033 và tài liệu này dùng `/api/v1/bookings/{bookingId}/qr` (theo id, có kiểm tra chủ sở hữu). Đề nghị code đổi theo spec để ảnh QR không truy cập được chỉ bằng việc đoán mã.

---

# 10. Database / Entity Interaction

| Entity | Operation | Purpose |
|---|---|---|
| `booking` | Read / Update | Ticket, đổi lịch, mã |
| `booking_reschedule` (ENT-428) | Insert / Read | Lịch sử đổi |
| `booking_status_event` (ENT-426) | Read | Lịch sử trạng thái trên ticket |
| `booking_reminder` (ENT-424) | Update / Insert (qua scheduler) | Nhắc theo giờ mới |
| `quote`, `quote_item` | Read | Hạng mục + chi phí đã duyệt |
| `maintenance_rule` | Read | Hạng mục theo `booking.odo_milestone` |
| `workshop`, `workshop_operating_hour`, `workshop_slot_block` | Read | Địa chỉ, giờ, sức chứa |

---

# 11. Observability & Performance

- Log `booking.rescheduled` (`booking_id`, `from`, `to`, `source`, `duration_ms`), `booking.reschedule_rejected` (`reason`).
- Metric `booking_reschedule_total{result}`, `booking_reschedule_conflict_total`.
- p90: `API-BT-01` ≤ 300 ms (50 dòng), `API-BR-01` ≤ 300 ms, `API-BT-04` ≤ 500 ms.

---

# 12. Test Checklist

- [ ] Đổi thành công: khung cũ +1, khung mới −1, cùng `bookingCode` (AC-1204, AC-1205).
- [ ] Khung mới hết chỗ ở bước cuối ⇒ booking giữ giờ cũ (AC-1203).
- [ ] Đổi cùng ngày sang khung khác khi khung đó còn đúng 1 chỗ: thành công (BR-1204 loại trừ chính booking — EDGE-1201).
- [ ] 2 thiết bị đổi cùng lúc ⇒ 1 thành công, 1 `BOOKING_CHANGED`.
- [ ] Hai booking đổi chéo khung của nhau cùng lúc không deadlock.
- [ ] Nhắc 24h cũ `skipped`, nhắc mới đúng giờ (AC-1206); `attendanceConfirmedAt` về `null`.
- [ ] `< 60'` hoặc đã đổi 2 lần ⇒ bị chặn + `rescheduleBlockedReason` (AC-1207).
- [ ] `qrPayload` chỉ chứa URL + mã (AC-1208); `pending` không có QR (AC-1202).
- [ ] `by-code` với mã của người khác ⇒ `404`.

---

# 13. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu |

# 14. References

- [FF us-053](../feature-functional/us-053-sprint-3-spec.ff.md) · [Entity us-053](../entity/us-053-sprint-3-spec.entity.md) · [FE us-053](../frontend/us-053-sprint-3-spec.fe.md)
- [us-029 API](us-029-sprint-3-spec.api.md) · [us-033 API](us-033-sprint-3-spec.api.md) · [us-037 API](us-037-sprint-3-spec.api.md) · [AI-004](../../ai-agent/ai-004-sprint-3-spec.agent.md)
