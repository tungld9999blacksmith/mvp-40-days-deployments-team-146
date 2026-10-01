# API Technical Specification — Workshop Board

> Backend cho Feature `FEAT-BOARD-001` — F8 (US-037 → US-040).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-037-sprint-3-spec.ff.md) là chuẩn; API chỉ trỏ `BR-8xx` / `EF-8xx` / `EDGE-8xx`.
>
> **Entity:** [Entity Spec](../entity/us-037-sprint-3-spec.entity.md) — `booking_status_event` (ENT-426, mới); ghi `booking`, `workshop.booking_confirmation_mode`, `workshop_slot_block`, `vehicle_service_record`, `follow_up`.
>
> **Nguyên tắc:** mọi chuyển trạng thái booking đi qua **một** `BookingStateMachine` dùng chung với F6 (us-029) và F7 (us-033). Khoá chỗ đi qua **cùng** Redis lock + transaction với đặt lịch (us-029 BR-001).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-BOARD-001` |
| Feature | `FEAT-BOARD-001` — F8 |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Author | Team 4 Người |
| Base URL | `/api/v1/workshop-owner` |
| Auth | Firebase ID token (Bearer) của **chủ xưởng** + phiên hợp lệ (FEAT-AUTH-004) |
| Created Date | `2026-09-29` |
| Updated Date | `2026-09-29` |
| Related Functional Spec | [us-037-sprint-3-spec.ff.md](../feature-functional/us-037-sprint-3-spec.ff.md) |
| Related Entity Spec | [us-037-sprint-3-spec.entity.md](../entity/us-037-sprint-3-spec.entity.md) |
| Related Frontend Spec | [us-037-sprint-3-spec.fe.md](../frontend/us-037-sprint-3-spec.fe.md) |

---

# 1. Overview

## 1.1 API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-WB-01` | `GET` | `/api/v1/workshop-owner/bookings` | Danh sách lịch hẹn của xưởng theo khoảng ngày + lọc + tóm tắt | UC-801, BR-812 |
| `API-WB-02` | `GET` | `/api/v1/workshop-owner/bookings/{bookingId}` | Chi tiết + lịch sử trạng thái + hành động hợp lệ | UC-801 |
| `API-WB-03` | `GET` | `/api/v1/workshop-owner/bookings/by-code/{bookingCode}` | Tìm booking theo mã (QR / nhập tay) để check-in | UC-803, BR-805 |
| `API-WB-04` | `POST` | `/api/v1/workshop-owner/bookings/{bookingId}/transitions` | Chuyển trạng thái: `ACCEPT` / `REJECT` / `CHECK_IN` / `START` / `COMPLETE` / `CANCEL` | UC-802 → UC-805, BR-802 |
| `API-WB-05` | `GET` | `/api/v1/workshop-owner/capacity` | Sức chứa theo ngày × khung: công suất, đã đặt, đã khoá, còn nhận | UC-806 |
| `API-WB-06` | `PUT` | `/api/v1/workshop-owner/slot-blocks` | Đặt số chỗ khoá cho 1 khung (0 = gỡ khoá) | UC-806, BR-809 |
| `API-WB-07` | `GET` | `/api/v1/workshop-owner/booking-settings` | Xem chế độ xác nhận | UC-807 |
| `API-WB-08` | `PUT` | `/api/v1/workshop-owner/booking-settings` | Đổi chế độ xác nhận `AUTO` / `MANUAL` | UC-807, BR-811 |

## 1.2 Scope

**In Scope** — các endpoint trên; tác động khi hoàn tất (lịch sử `ev_care`, hỏi thăm); thông báo cho chủ xe khi xưởng chấp nhận/từ chối/huỷ.

**Out of Scope** — duyệt báo giá (F5b); `service_progress` (F8b); phiếu hỗ trợ (us-041); đổi giờ hẹn (F6b); job huỷ quá hạn xưởng (us-029 — chỉ dùng chung `BookingStateMachine`).

---

# 2. Authentication & Authorization

## 2.1 Authentication

```http
Authorization: Bearer <firebase_id_token>
```

- Verify bằng Firebase Admin SDK ⇒ `workshop_owner` theo `firebase_uid`.
- Phiên bị thu hồi (FEAT-AUTH-004) ⇒ `401 SESSION_REVOKED`.

## 2.2 Allowed Roles

| Role | Access |
|---|---|
| `WORKSHOP_OWNER` (onboarding hoàn tất, gắn xưởng) | ✅ Allowed |
| `VEHICLE_USER` | ❌ Denied |
| `ANONYMOUS` | ❌ Denied |

## 2.3 Authorization Rules

- Xưởng của chủ xưởng: `workshop WHERE owner_id = :owner_id` (đúng 1 — W-05). Không có ⇒ `403 ONBOARDING_REQUIRED`.
- Mọi truy vấn booking lọc `workshop_id = :ws`; booking xưởng khác ⇒ `404 BOOKING_NOT_FOUND` (FF BR-801, AC-801).
- `workshop.status <> active` ⇒ endpoint **đọc** vẫn dùng được; endpoint **ghi** trả `403 WORKSHOP_INACTIVE` (FF EDGE-812).

---

# 3. API-WB-01 — `GET /api/v1/workshop-owner/bookings`

## 3.1 Query Parameters

| Field | Type | Required | Description | Constraints |
|---|---|---:|---|---|
| `from` | `date` | No | Ngày bắt đầu (giờ VN) | Mặc định hôm nay; ≥ hôm nay − `BOARD_HISTORY_DAYS` |
| `to` | `date` | No | Ngày kết thúc (gồm) | Mặc định = `from`; `to − from < BOARD_MAX_RANGE_DAYS` (7) |
| `status` | `string[]` | No | Lọc trạng thái (lặp tham số) | `PENDING`…`CANCELLED` |
| `q` | `string` | No | Tìm theo mã lịch hẹn hoặc biển số (không dấu, không phân biệt hoa thường) | 2..20 ký tự |

## 3.2 Validation

| Validation | Rule | Error |
|---|---|---|
| Khoảng ngày | `from ≤ to`, ≤ 7 ngày, không quá 30 ngày trước | `400 INVALID_REQUEST` |
| `status` | Giá trị hợp lệ | `400 INVALID_REQUEST` |

## 3.3 Internal Processing

```text
1. Auth → workshop_owner → workshop (ws).
2. SELECT booking b JOIN vehicle_user u JOIN user_vehicle v
    WHERE b.workshop_id = :ws AND b.booking_date BETWEEN :from AND :to
      [AND b.status IN :status]
      [AND (b.booking_code ILIKE :q
            OR regexp_replace(upper(v.license_plate), '[^A-Z0-9]', '', 'g') LIKE :q_norm)]   -- q_norm: bỏ '-', '.', khoảng trắng
    ORDER BY b.booking_date, b.time_slot, b.created_at
3. summary = COUNT theo status (không áp bộ lọc status, để thẻ tóm tắt luôn đủ).
4. Với booking pending: confirmDeadline = min(created_at + BOOKING_WS_CONFIRM_DEADLINE_HOURS, appointment_at) (us-029 BR-015).
5. allowedActions tính theo §6.2.
```

## 3.4 Success Response `200 OK`

```json
{
  "data": {
    "workshopId": "3f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b",
    "confirmationMode": "MANUAL",
    "from": "2026-10-04",
    "to": "2026-10-04",
    "summary": { "PENDING": 1, "CONFIRMED": 6, "CHECKED_IN": 1, "IN_PROGRESS": 1, "COMPLETED": 2, "CANCELLED": 1 },
    "items": [
      {
        "bookingId": "8d2e6f10-3c4b-4a59-8e7d-1f2a3b4c5d6e",
        "bookingCode": "EVC-7K2M",
        "status": "CONFIRMED",
        "bookingDate": "2026-10-04",
        "timeSlot": "09:00",
        "customer": { "fullName": "Nguyễn Văn A", "phone": "0912345678" },
        "vehicle": { "modelName": "VF 6", "licensePlate": "30A-123.45" },
        "milestoneLabel": "Mốc 12.000 km",
        "estimatedCost": 1850000,
        "quote": { "quoteId": "q_123", "status": "APPROVED" },
        "attendanceConfirmedAt": "2026-10-03T07:12:40Z",
        "confirmDeadline": null,
        "allowedActions": ["CHECK_IN", "CANCEL"]
      }
    ]
  }
}
```

---

# 4. API-WB-02 — `GET /api/v1/workshop-owner/bookings/{bookingId}`

Trả như một phần tử `items` ở §3.4, thêm:

```json
{
  "data": {
    "...": "như API-WB-01 item",
    "actualCost": null,
    "note": "Bảo dưỡng mốc 12.000 km",
    "statusHistory": [
      { "fromStatus": null, "toStatus": "PENDING", "actorType": "VEHICLE_OWNER", "source": "CHAT", "reasonCode": null, "note": null, "at": "2026-09-30T02:09:58Z" },
      { "fromStatus": "PENDING", "toStatus": "CONFIRMED", "actorType": "SYSTEM", "source": "AUTO_CONFIRM", "reasonCode": null, "note": null, "at": "2026-09-30T02:09:58Z" }
    ]
  }
}
```

`statusHistory` từ `booking_status_event` theo `created_at` tăng dần (FF AC-811). Không trả tên/ID người thực hiện chủ xe khác ngoài `actorType`.

Lỗi: `404 BOOKING_NOT_FOUND` (không thuộc xưởng).

---

# 5. API-WB-03 — `GET /api/v1/workshop-owner/bookings/by-code/{bookingCode}`

## 5.1 Purpose

Tra booking từ nội dung QR / mã nhập tay. **Chỉ đọc** — check-in thực hiện bằng API-WB-04 `CHECK_IN` sau khi chủ xưởng bấm xác nhận (FF SCR-803).

## 5.2 Path Parameters

| Field | Type | Required | Description | Constraints |
|---|---|---:|---|---|
| `bookingCode` | `string` | Yes | Mã lịch hẹn; QR có thể chứa URL — FE tách mã trước khi gọi | Chuẩn hoá upper-case, `^[A-Z0-9-]{4,20}$` |

## 5.3 Processing

```text
booking WHERE booking_code = :code AND workshop_id = :ws
  → không có ⇒ 404 BOOKING_NOT_FOUND (không phân biệt "không tồn tại" và "xưởng khác" — EDGE-803)
Trả item như API-WB-01 + checkInEligibility:
  ELIGIBLE        — confirmed, booking_date = today
  NOT_TODAY       — confirmed, khác ngày (kèm bookingDate)            (EDGE-804)
  ALREADY_CHECKED_IN — checked_in/in_progress/completed (kèm checkedInAt) (EDGE-805)
  NOT_CONFIRMED   — pending/cancelled
```

## 5.4 Success Response `200 OK`

```json
{ "data": { "bookingId": "8d2e...", "bookingCode": "EVC-7K2M", "status": "CONFIRMED", "bookingDate": "2026-10-04", "timeSlot": "09:00",
            "customer": { "fullName": "Nguyễn Văn A" }, "vehicle": { "modelName": "VF 6", "licensePlate": "30A-123.45" },
            "checkInEligibility": "ELIGIBLE", "checkedInAt": null } }
```

---

# 6. API-WB-04 — `POST /api/v1/workshop-owner/bookings/{bookingId}/transitions`

## 6.1 Request Body

```json
{ "action": "COMPLETE", "expectedStatus": "IN_PROGRESS", "actualCost": 1850000, "source": "BOARD" }
```

## 6.2 Actions

| Action | Từ → Sang | Field bắt buộc | Điều kiện thêm | FF |
|---|---|---|---|---|
| `ACCEPT` | `pending → confirmed` | — | `now ≤ confirmDeadline` ∧ `now < appointment_at` | BR-803 |
| `REJECT` | `pending → cancelled` | `reasonCode` ∈ {`FULLY_BOOKED`,`NOT_SUPPORTED_SERVICE`,`WORKSHOP_UNAVAILABLE`,`OTHER`} | | BR-804 |
| `CHECK_IN` | `confirmed → checked_in` | — | `booking_date = today (VN)` | BR-805 |
| `START` | `checked_in → in_progress` | — | | BR-802 |
| `COMPLETE` | `in_progress → completed` | — (`actualCost` tuỳ chọn ≥ 0) | | BR-807 |
| `CANCEL` | `confirmed → cancelled` | `reasonCode` ∈ {`NO_SHOW`,`WORKSHOP_UNAVAILABLE`,`CUSTOMER_REQUEST`,`OTHER`} | `NO_SHOW` ⇒ `now ≥ appointment_at + NO_SHOW_GRACE_MINUTES` | BR-806 |

## 6.3 Request Fields

| Field | Type | Required | Nullable | Description | Constraints |
|---|---|---:|---:|---|---|
| `action` | `string` | Yes | No | Hành động | §6.2 |
| `expectedStatus` | `string` | Yes | No | Trạng thái FE đang thấy — chống thao tác trên dữ liệu cũ | Phải khớp "Từ" của action |
| `reasonCode` | `string` | Theo action | Yes | Lý do | §6.2 |
| `note` | `string` | Khi `reasonCode = OTHER` | Yes | Ghi chú | Max 255 |
| `actualCost` | `number` | No | Yes | Chi phí thực tế (VND) | `0 ≤ x ≤ 999,999,999.99` |
| `source` | `string` | No | No | `BOARD` (mặc định) / `QR_SCAN` | Chỉ `CHECK_IN` được `QR_SCAN` |

## 6.4 Internal Processing

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant SM as BookingStateMachine
    participant DB
    participant NS as NotificationService

    Client->>API: POST /bookings/{id}/transitions
    API->>SM: transition(ws, id, action, expectedStatus, ...)
    SM->>SM: validate action ↔ expectedStatus, fields, time rules
    SM->>DB: BEGIN
    SM->>DB: UPDATE booking SET status=:to WHERE id AND workshop_id=:ws AND status=:from
    alt 1 row
        SM->>DB: INSERT booking_status_event
        opt ACCEPT
            SM->>DB: gen booking_code (nếu chưa có); on_confirmed → booking_reminder (us-033)
        end
        opt REJECT / CANCEL
            SM->>DB: booking_reminder scheduled → skipped; quote.booking_id = NULL
        end
        opt COMPLETE
            SM->>DB: booking.actual_cost; INSERT vehicle_service_record(ev_care); INSERT follow_up(pending, +12h ngoài giờ yên lặng — us-041)
        end
        SM->>DB: COMMIT
        opt ACCEPT / REJECT / CANCEL (≠ NO_SHOW)
            SM-->>NS: notify vehicle owner (sau commit, best effort)
        end
        SM-->>API: booking mới
    else 0 row
        SM->>DB: ROLLBACK; re-read
        SM-->>API: 409 INVALID_STATUS_TRANSITION (currentStatus)
    end
    API-->>Client: 200 / 4xx
```

- **Idempotent theo trạng thái:** nếu booking **đã** ở trạng thái đích của action và sự kiện cuối do cùng chủ xưởng thực hiện (vd. quét QR hai lần) ⇒ `200` với dữ liệu hiện tại (FF EDGE-805).
- **COMPLETE nguyên tử** (FF BR-807, AC-808): lỗi insert lịch sử / hỏi thăm ⇒ rollback toàn bộ ⇒ `500`/`503`, booking vẫn `in_progress`. Unique `vehicle_service_record.booking_id` và `follow_up.booking_id` chống trùng.
- **Thông báo** (FF BR-810) gửi sau commit qua `NotificationService`, nội dung:

  | Action | Nội dung |
  |---|---|
  | `ACCEPT` | `✅ {workshop_name} đã xác nhận lịch hẹn {HH:mm dd/mm}. Mã: {booking_code}. Chi tiết: {link}` |
  | `REJECT` | `❌ {workshop_name} chưa nhận được lịch {HH:mm dd/mm}. Mời bạn chọn khung/xưởng khác: {link}` |
  | `CANCEL` | `⚠️ {workshop_name} đã huỷ lịch hẹn {HH:mm dd/mm}. Lý do: {reason_label}. Đặt lại: {link}` |

## 6.5 Success Response `200 OK`

```json
{
  "data": {
    "bookingId": "8d2e...",
    "status": "COMPLETED",
    "actualCost": 1850000,
    "effects": { "serviceRecordId": "c7d8...", "followUpId": "f1a2...", "followUpScheduledAt": "2026-10-05T01:00:00Z" },
    "allowedActions": []
  }
}
```

`effects` chỉ có khi `COMPLETE` (hoặc `reminderScheduled` khi `ACCEPT`).

---

# 7. API-WB-05 — `GET /api/v1/workshop-owner/capacity`

## 7.1 Query Parameters

| Field | Type | Required | Description | Constraints |
|---|---|---:|---|---|
| `from` | `date` | No | Mặc định hôm nay | ≥ hôm nay |
| `days` | `integer` | No | Số ngày | 1..7, mặc định 7 |

## 7.2 Processing

Với mỗi ngày mở cửa và mỗi khung trong giờ hoạt động (us-029 BR-006), tính theo us-029 BR-005:

```text
capacityBase = total_technicians − emergency_slots_reserved
occupied     = COUNT(booking open statuses)
blocked      = workshop_slot_block.blocked_count (0 nếu không có)
remaining    = max(capacityBase − blocked − occupied, 0)
maxBlock     = max(capacityBase − occupied, 0)          -- trần khoá cho FF BR-809
```

## 7.3 Success Response `200 OK`

```json
{
  "data": {
    "totalTechnicians": 8,
    "emergencySlotsReserved": 1,
    "days": [
      {
        "date": "2026-10-04", "isClosed": false, "openTime": "08:00", "closeTime": "17:00",
        "slots": [
          { "timeSlot": "09:00", "occupied": 4, "blocked": 2, "remaining": 1, "maxBlock": 3, "blockReason": "PHONE_BOOKING", "blockNote": "2 khách gọi điện" }
        ]
      }
    ]
  }
}
```

---

# 8. API-WB-06 — `PUT /api/v1/workshop-owner/slot-blocks`

## 8.1 Request Body

```json
{ "date": "2026-10-04", "timeSlot": "09:00", "blockedCount": 2, "reason": "PHONE_BOOKING", "note": "2 khách gọi điện" }
```

| Field | Type | Required | Description | Constraints |
|---|---|---:|---|---|
| `date` | `date` | Yes | Ngày | `today ≤ date ≤ today + SLOT_BLOCK_MAX_DAYS_AHEAD` |
| `timeSlot` | `time` | Yes | Khung | Bội `SLOT_MINUTES`, trong giờ hoạt động |
| `blockedCount` | `integer` | Yes | Số chỗ khoá **mới** (đặt tuyệt đối, không cộng dồn) | `0 ≤ n ≤ maxBlock`; `0` = gỡ khoá |
| `reason` | `string` | Khi `n > 0` | `PHONE_BOOKING` / `WALK_IN` / `MAINTENANCE` / `OTHER` | |
| `note` | `string` | Khi `reason = OTHER` | | Max 255 |

## 8.2 Processing (nguyên tử cùng đặt lịch — FF BR-809, EF-806)

```text
1. Validate ngày, khung, giờ hoạt động          → 422 BLOCK_DATE_OUT_OF_RANGE / SLOT_OUT_OF_HOURS
2. Redis SET NX booking:hold:{ws}:{d}:{t}         (cùng khoá us-029 BR-001) → bận ⇒ retry ngắn, rồi 503
3. BEGIN; đếm occupied FOR UPDATE; maxBlock = total − emergency − occupied
4. n > maxBlock                                   → ROLLBACK, 409 BLOCK_EXCEEDS_FREE_CAPACITY {maxBlock}
5. n = 0 → DELETE; n > 0 → UPSERT (BR-ENT-494)
6. COMMIT; release lock
```

## 8.3 Success Response `200 OK`

```json
{ "data": { "date": "2026-10-04", "timeSlot": "09:00", "blocked": 2, "occupied": 4, "remaining": 1, "maxBlock": 3 } }
```

---

# 9. API-WB-07 / WB-08 — `booking-settings`

## 9.1 `GET` Response `200 OK`

```json
{ "data": { "confirmationMode": "AUTO", "wsConfirmDeadlineHours": 12, "pendingCount": 0 } }
```

## 9.2 `PUT` Request

```json
{ "confirmationMode": "MANUAL" }
```

| Field | Type | Required | Constraints |
|---|---|---:|---|
| `confirmationMode` | `string` | Yes | `AUTO` / `MANUAL` |

**Processing** — `UPDATE workshop SET booking_confirmation_mode = :mode`. Không đụng booking `pending` hiện có (FF BR-811). Trả `200` + giá trị mới; `pendingCount` để FE nhắc "Còn N yêu cầu đang chờ bạn xử lý".

---

# 10. Error Handling

## 10.1 Standard Error Format

```json
{ "error": { "code": "INVALID_STATUS_TRANSITION", "message": "Không thể chuyển từ Đã xác nhận sang Hoàn tất.", "details": { "currentStatus": "CONFIRMED", "allowedActions": ["CHECK_IN", "CANCEL"] }, "traceId": "abc-123" } }
```

## 10.2 Error Cases

| Case | Error Code | HTTP | Áp dụng | Ref |
|---|---|---:|---|---|
| Tham số / body sai | `INVALID_REQUEST` | `400` | tất cả | |
| Thiếu lý do / ghi chú | `REASON_REQUIRED` | `400` | WB-04 | BR-804, BR-806 |
| Token sai | `UNAUTHORIZED` | `401` | tất cả | |
| Phiên đã thu hồi | `SESSION_REVOKED` | `401` | tất cả | FEAT-AUTH-004 |
| Chưa đăng ký chủ xưởng | `WORKSHOP_OWNER_NOT_REGISTERED` | `404` | tất cả | FEAT-AUTH-003 |
| Chưa hoàn tất onboarding / chưa gắn xưởng | `ONBOARDING_REQUIRED` | `403` | tất cả | |
| Xưởng không `active` (ghi) | `WORKSHOP_INACTIVE` | `403` | WB-04/06/08 | EDGE-812 |
| Booking không có / xưởng khác | `BOOKING_NOT_FOUND` | `404` | WB-02/03/04 | BR-801, EDGE-803 |
| Sai state machine / `expectedStatus` lệch | `INVALID_STATUS_TRANSITION` | `409` | WB-04 | BR-802, EF-801, EF-802 |
| Check-in khác ngày | `CHECK_IN_NOT_TODAY` | `409` | WB-04 | BR-805, EDGE-804 |
| Chấp nhận quá hạn chót | `CONFIRM_DEADLINE_PASSED` | `409` | WB-04 | EF-804 |
| No-show quá sớm | `NO_SHOW_TOO_EARLY` | `409` | WB-04 | BR-806, AC-810 |
| Khoá vượt chỗ trống | `BLOCK_EXCEEDS_FREE_CAPACITY` | `409` | WB-06 | BR-809, EF-805 |
| Ngày khoá ngoài phạm vi | `BLOCK_DATE_OUT_OF_RANGE` | `422` | WB-06 | BR-809 |
| Khung ngoài giờ hoạt động | `SLOT_OUT_OF_HOURS` | `422` | WB-06 | us-029 BR-006 |
| Redis/DB tạm lỗi | `SERVICE_UNAVAILABLE` | `503` | WB-04/06 | |
| Lỗi hệ thống | `INTERNAL_SERVER_ERROR` | `500` | tất cả | |

---

# 11. HTTP Status Codes

| HTTP | When |
|---|---|
| `200 OK` | Đọc; chuyển trạng thái (kể cả idempotent); khoá chỗ; đổi cài đặt |
| `400 Bad Request` | Tham số/body sai, thiếu lý do |
| `401 Unauthorized` | Token sai / phiên thu hồi |
| `403 Forbidden` | Chưa onboarding / xưởng inactive |
| `404 Not Found` | Booking không thuộc xưởng; chủ xưởng chưa đăng ký |
| `409 Conflict` | Sai trạng thái, sai ngày, quá hạn, no-show sớm, khoá vượt |
| `422 Unprocessable Entity` | Khung/ngày khoá không hợp lệ |
| `503 Service Unavailable` | Lock/DB tạm lỗi |

---

# 12. Business Logic (tham chiếu FF)

| Rule | Nội dung | FF |
|---|---|---|
| Phạm vi xưởng | Lọc `workshop_id` | BR-801 |
| State machine | Bảng §6.2 | BR-802 |
| Chấp nhận / từ chối | Hạn chót; lý do | BR-803, BR-804 |
| Check-in | Đúng ngày, theo mã trong xưởng | BR-805 |
| Huỷ / no-show | Lý do; no-show sau 30' | BR-806 |
| Hoàn tất | Nguyên tử + lịch sử `ev_care` + hỏi thăm | BR-807 |
| Lịch sử | Mọi chuyển trạng thái | BR-808 |
| Khoá chỗ | ≤ chỗ trống, cùng lock | BR-809 |
| Thông báo | Sau commit, best effort | BR-810 |
| Chế độ xác nhận | Áp dụng cho lần sau | BR-811 |
| Dữ liệu khách | Tên, SĐT, biển số; không VIN/CCCD/email | BR-813 |

---

# 13. Database / Entity Interaction

| Entity / Table | Operation | Purpose |
|---|---|---|
| `workshop_owner`, `workshop` | Read / Update (`booking_confirmation_mode`) | Phạm vi, cài đặt |
| `booking` | Read / Update | Board, state machine |
| `booking_status_event` | Insert / Read | Lịch sử |
| `vehicle_user`, `user_vehicle` | Read | Tên, SĐT, model, biển số |
| `workshop_operating_hour` | Read | Khung hợp lệ |
| `workshop_slot_block` | Read / Upsert / Delete | Khoá chỗ |
| `vehicle_odometer_reading` | Read | ODO hiện tại khi hoàn tất |
| `vehicle_service_record` | Insert | Lịch sử `ev_care` |
| `follow_up` | Insert | Hỏi thăm |
| `booking_reminder` | Insert / Update | Nhắc 24h |
| `quote` | Read / Update | Hiển thị; gỡ liên kết khi huỷ |

---

# 14. Concurrency / Race Condition

| Tình huống | Xử lý |
|---|---|
| Hai tab cùng bấm Hoàn tất | Cập nhật có điều kiện `status = :from`; tab sau nhận idempotent `200` (cùng chủ xưởng, đã ở đích) |
| Chủ xe huỷ (F7) vs xưởng check-in | Cập nhật có điều kiện; bên commit trước thắng, bên sau `409 INVALID_STATUS_TRANSITION` (FF EDGE-802) |
| Xưởng chấp nhận vs job quá hạn BR-015 | Như trên; job chạy trước ⇒ `409 CONFIRM_DEADLINE_PASSED` |
| Khoá chỗ vs chủ xe đặt lịch cùng khung | Cùng Redis lock `booking:hold:{ws}:{d}:{t}` + đếm `FOR UPDATE` (FF EF-806) — không bao giờ `occupied + blocked > capacityBase` |
| `expectedStatus` cũ trên màn | `409` kèm `currentStatus` để FE tải lại |

---

# 15. Idempotency

```text
Required: WB-04 — theo trạng thái (+ expectedStatus); WB-06 — PUT giá trị tuyệt đối; WB-08 — PUT
```

- WB-06 và WB-08 là `PUT` giá trị tuyệt đối ⇒ gửi lại nhiều lần cho cùng kết quả.
- WB-04 không cần `Idempotency-Key`: lặp lại cùng action sau khi thành công ⇒ `200` idempotent; action khác ⇒ `409`.

---

# 16. External Dependencies

| Service | Purpose | Required |
|---|---|---:|
| Firebase Auth | Xác thực chủ xưởng | Yes |
| PostgreSQL | Dữ liệu | Yes |
| Redis | Lock sức chứa (khoá chỗ) | Yes |
| `NotificationService` (Discord) | Báo chủ xe | No (best effort) |

---

# 17. Observability

**Log:** `traceId`, `workshopOwnerId`, `workshopId`, `bookingId`, `action`, `from → to`, `reasonCode`, kết quả; khoá chỗ: `date`, `timeSlot`, `blockedCount`, `maxBlock`. **Không log:** SĐT, tên khách, biển số, `note`.

**Metrics:** số chuyển trạng thái theo action; tỉ lệ `INVALID_STATUS_TRANSITION`; tỉ lệ no-show (`CANCEL/NO_SHOW` ÷ booking `confirmed` đến hạn); thời gian `pending → confirmed` (xưởng `manual`); số lần `BLOCK_EXCEEDS_FREE_CAPACITY`.

---

# 18. Performance Requirements

| Metric | Target |
|---|---|
| WB-01 / WB-05 (p90, ≤ 7 ngày) | `< 500 ms` |
| WB-04 / WB-06 (p90) | `< 500 ms` |
| Vượt sức chứa do khoá chỗ | `0` |

---

# 19. Retry & Timeout

| Dependency | Retry | Max Attempts | Backoff |
|---|---:|---:|---|
| Redis lock (WB-06) | Yes | 3 | 50–200 ms |
| Notification (sau commit) | Theo adapter us-021 | 3 | Exponential; lỗi không ảnh hưởng response |

---

# 20. Example — Một ngày trên Board

```http
GET /api/v1/workshop-owner/bookings?from=2026-10-04
```
→ `200` 12 lịch; 1 `PENDING` (hạn 14:10).

```http
POST /api/v1/workshop-owner/bookings/aa01.../transitions
{ "action": "ACCEPT", "expectedStatus": "PENDING" }
```
→ `200` `CONFIRMED`, `bookingCode = EVC-9QXZ`; chủ xe nhận thông báo; nhắc 24h được lên lịch.

```http
GET /api/v1/workshop-owner/bookings/by-code/EVC-7K2M
```
→ `200` `checkInEligibility = ELIGIBLE`.

```http
POST /api/v1/workshop-owner/bookings/8d2e.../transitions
{ "action": "CHECK_IN", "expectedStatus": "CONFIRMED", "source": "QR_SCAN" }
```
→ `200` `CHECKED_IN`.

```http
PUT /api/v1/workshop-owner/slot-blocks
{ "date": "2026-10-04", "timeSlot": "14:00", "blockedCount": 3, "reason": "WALK_IN" }
```
→ `409 BLOCK_EXCEEDS_FREE_CAPACITY` `{ "maxBlock": 1 }`.

---

# 21. Open Questions

- [ ] Q-801 → Q-806 (FF §24).
- [ ] Board có cần realtime (SSE/WebSocket) thay vì làm mới 60s? — phase sau.
- [ ] Tìm theo biển số đang chuẩn hoá tại chỗ trên `user_vehicle.license_plate` (§3.3); đủ cho ≤ 50 booking/ngày. Nếu chậm, thêm cột/Index chuẩn hoá sau.

---

# 22. References

- Functional Spec: [us-037-sprint-3-spec.ff.md](../feature-functional/us-037-sprint-3-spec.ff.md)
- Entity Spec: [us-037-sprint-3-spec.entity.md](../entity/us-037-sprint-3-spec.entity.md)
- us-029 API (sức chứa, lock, hạn chót): [us-029-sprint-3-spec.api.md](us-029-sprint-3-spec.api.md)
- us-033 API (nhắc 24h, huỷ bởi chủ xe): [us-033-sprint-3-spec.api.md](us-033-sprint-3-spec.api.md)
- us-041 API (hỏi thăm, phiếu hỗ trợ): [us-041-sprint-4-spec.api.md](../../sprint-4/api/us-041-sprint-4-spec.api.md)
- us-017 Entity (lịch sử `ev_care`): [us-017-sprint-2-spec.entity.md](../../sprint-2/entity/us-017-sprint-2-spec.entity.md)

---

# 23. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Team 4 Người | Initial version: API-WB-01 → API-WB-08 |
