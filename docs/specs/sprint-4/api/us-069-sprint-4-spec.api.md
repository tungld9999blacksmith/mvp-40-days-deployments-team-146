# API Technical Specification — Hộp thư Thông báo trong app

> Backend cho Feature `FEAT-NOTI-003` — PRD F7 kênh trong app (US-069 → US-072).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-069-sprint-4-spec.ff.md) là chuẩn; API chỉ trỏ `BR-xxx` / `EF-xxx` / `EDGE-xxx`. **Entity:** [Entity Spec](../entity/us-069-sprint-4-spec.entity.md) — không có bảng thông báo; hộp thư được dựng khi đọc.
>
> **Bối cảnh:** `API-NOTI-003` và endpoint chi tiết lời nhắc đã chạy (`backend/src/modules/notification/route.py`, `feed_service.py`, `context_service.py`) trước khi có đặc tả. Tài liệu ghi lại hợp đồng hiện tại, đặt mã `API-NOTI-004` cho chi tiết lời nhắc (nối dải `API-NOTI-001/002` của [us-021 API](../../sprint-2/api/us-021-sprint-2-spec.api.md)), và loại `BOOKING_REMINDER` thêm ngày 07/10/2026 (§3.4, FF BR-1707).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-NOTI-003` |
| Version | `v1.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/notification` |
| Created Date | `2026-10-07` |

---

# 1. API Group

| API ID | Method | Endpoint | Actor | Mục đích | FF |
|---|---|---|---|---|---|
| `API-NOTI-003` | `GET` | `/api/v1/notifications` | Chủ xe | Hộp thư 90 ngày, tối đa 50 mục | UC-1701, BR-1701…1703, BR-1711 |
| `API-NOTI-004` | `GET` | `/api/v1/notifications/reminders/{reminderId}` | Chủ xe | Chi tiết một lời nhắc bảo dưỡng | UC-1702, BR-1705, BR-1706 |

Hộp thư chủ xưởng (UC-1703) **không có API riêng**: FE gọi 2 API đã có rồi gộp (FF BR-1710, Q-1705):

| API | Gọi với | Spec |
|---|---|---|
| `API-QT-11` `GET /workshop-owner/quotes?status=PENDING_APPROVAL` | — | [us-049 API](../../sprint-3/api/us-049-sprint-3-spec.api.md) |
| `API-WB-01` `GET /workshop-owner/bookings` | `from = hôm nay`, `to = hôm nay + 6`, `status = PENDING` | [us-037 API](../../sprint-3/api/us-037-sprint-3-spec.api.md) |

Ngoài phạm vi (công cụ demo email): `GET /notifications/email-outbox`, `POST /notifications/email/webhook`.

---

# 2. Authentication & Authorization

| API | Rule | Lỗi |
|---|---|---|
| Cả hai | `Authorization: Bearer <Firebase ID token>` | `401` (`{"detail": …}` của FastAPI) |
| Cả hai | `require_active_vehicle_owner` | `404 USER_NOT_REGISTERED`, `403 ONBOARDING_REQUIRED`, `403 ACCOUNT_SUSPENDED`, `403 ACCOUNT_INACTIVE` |
| `API-NOTI-003` | Mọi nguồn lọc theo `user_vehicle.user_id = uid` hoặc `booking.user_id = uid` (FF BR-1708) | — |
| `API-NOTI-004` | Lời nhắc tồn tại; xe của lời nhắc thuộc chủ xe và đang hoạt động (`get_owned_active_vehicle`) | §4.3 |

---

# 3. API-NOTI-003 — `GET /notifications`

## 3.1 Request

```http
GET /api/v1/notifications
Authorization: Bearer <token>
```

Không có tham số. Không phân trang (FF EDGE-1701).

## 3.2 Processing

1. `since = now − 90 ngày` (`FEED_WINDOW_DAYS`).
2. Đọc 5 nguồn (FF BR-1701):

| Nguồn | Điều kiện | `occurredAt` | `unread` |
|---|---|---|---|
| `reminder` | `user_vehicle_id ∈ xe của chủ xe`, `scheduled_at ≥ since` | `scheduled_at` | `false` |
| `quote` | xe của chủ xe, `status ∈ {approved, rejected}`, `reviewed_at ≥ since` | `reviewed_at` | `result_seen_at IS NULL` |
| `booking_status_event` ⨝ `booking` | `booking.user_id = uid`, `actor_type ≠ vehicle_owner` (BR-1703), `to_status ∈ {confirmed, cancelled, completed}`, `created_at ≥ since` | `created_at` | `false` |
| `booking_reminder` ⨝ `booking` | `booking.user_id = uid`, `status ∈ {sent, failed}`, `scheduled_at ≥ since` | `sent_at`, không có thì `scheduled_at` | §3.4 |
| `follow_up` ⨝ `booking` | `booking.user_id = uid`, `status = sent`, `sent_at ≥ since` | `sent_at` | `true` |

3. Ghép tên xưởng (1 truy vấn `IN` mỗi nguồn cần tên).
4. Gộp, sắp `occurredAt` giảm dần, cắt 50 mục (`FEED_LIMIT`).
5. `unreadCount = số mục unread trong 50 mục` (FF BR-1702).

Không ghi dữ liệu.

## 3.3 Response — `200 OK`

```json
{
  "data": {
    "items": [
      {
        "id": "follow-up:2c1e…",
        "kind": "FOLLOW_UP",
        "occurredAt": "2026-10-06T03:00:00Z",
        "unread": true,
        "reminder": null, "quote": null, "booking": null,
        "followUp": { "followUpId": "2c1e…", "bookingId": "8d2e…", "workshopName": "VinFast Smart City" }
      },
      {
        "id": "booking:7a90…",
        "kind": "BOOKING_UPDATE",
        "occurredAt": "2026-10-05T02:00:00Z",
        "unread": false,
        "booking": {
          "bookingId": "8d2e…", "bookingCode": "EVC-7K2M", "status": "CONFIRMED",
          "reasonCode": null, "bookingDate": "2026-10-04", "timeSlot": "14:00:00",
          "workshopName": "VinFast Smart City"
        }
      },
      {
        "id": "quote:51b3…",
        "kind": "QUOTE_RESULT",
        "occurredAt": "2026-10-04T02:00:00Z",
        "unread": true,
        "quote": { "quoteId": "51b3…", "status": "APPROVED", "approvedTotal": "1400000.00", "workshopName": "VinFast Smart City" }
      },
      {
        "id": "reminder:e0d4…",
        "kind": "MAINTENANCE_REMINDER",
        "occurredAt": "2026-10-02T01:00:00Z",
        "unread": false,
        "reminder": { "userVehicleId": "3f5a…", "level": "WARNING", "odoMilestoneKm": 12000, "resolved": false, "resolutionReason": null }
      }
    ],
    "unreadCount": 2
  }
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `string` | `{reminder\|quote\|booking\|booking-reminder\|follow-up}:{uuid nguồn}` — ổn định, dùng làm key |
| `kind` | `MAINTENANCE_REMINDER \| QUOTE_RESULT \| BOOKING_UPDATE \| BOOKING_REMINDER \| FOLLOW_UP` | Đúng một khối `*Ref` khác `null` tương ứng |
| `occurredAt` | `datetime` (UTC) | §3.2 |
| `unread` | `boolean` | FF BR-1702 |
| `reminder` | `{ userVehicleId, level: EARLY\|WARNING\|URGENT\|EXPIRED, odoMilestoneKm, resolved, resolutionReason }` | `resolutionReason`: `HAS_BOOKING`, `MAINTENANCE_COMPLETED`, `MILESTONE_CHANGED`, `SUPERSEDED`, `BEFORE_WINDOW`, `STATUS_CHANGED` hoặc `null` |
| `quote` | `{ quoteId, status: APPROVED\|REJECTED, approvedTotal: decimal\|null, workshopName }` | — |
| `booking` | `{ bookingId, bookingCode, status: CONFIRMED\|CANCELLED\|COMPLETED, reasonCode, bookingDate, timeSlot, workshopName }` | `reasonCode` theo us-037 |
| `bookingReminder` | `{ bookingId, bookingCode, bookingDate, timeSlot, workshopName }` | §3.4 |
| `followUp` | `{ followUpId, bookingId, workshopName }` | — |
| `unreadCount` | `integer` | — |

Client phải bỏ qua `kind` không biết (FF BR-1711).

## 3.4 Loại `BOOKING_REMINDER` (FF BR-1707)

| Mục | Giá trị |
|---|---|
| Nguồn | `booking_reminder` (ENT-424) ⨝ `booking`, `booking.user_id = uid`, `status ∈ {sent, failed}`, `scheduled_at ≥ since` |
| Vì sao gồm `failed` | Chủ xe không bật kênh ngoài (mặc định MVP) ⇒ job us-033 không có lần gửi nào và `_settle` đặt `failed`, `sent_at = NULL`. Hộp thư là kênh mặc định nên lời nhắc vẫn đến chủ xe ở đây. `skipped` (huỷ, đổi giờ, `TOO_LATE`…) không hiện |
| `id` | `booking-reminder:{booking_reminder.id}` |
| `occurredAt` | `sent_at`, không có thì `scheduled_at` |
| `unread` | `booking.status = confirmed AND booking.attendance_confirmed_at IS NULL AND giờ hẹn > now` (còn việc để làm) |
| Khối | `bookingReminder: { bookingId, bookingCode, bookingDate, timeSlot, workshopName }` |
| Code | `NotificationFeedService._booking_reminders()`, schema `BookingReminderRefOut` |

Thêm `kind` mới không phá client cũ (BR-1711).

## 3.5 Errors

| HTTP | Code | Khi nào |
|---|---|---|
| `401` | — | Token thiếu/sai |
| `403` / `404` | như §2 | Tài khoản chưa sẵn sàng |
| `5xx` | — | FF EF-1701 |

---

# 4. API-NOTI-004 — `GET /notifications/reminders/{reminderId}`

## 4.1 Request

| Param | In | Type | Required | Rule |
|---|---|---|---:|---|
| `reminderId` | path | `uuid` | Yes | Sai định dạng ⇒ `422` mặc định của FastAPI (`{"detail": [...]}`; prefix `/notifications` không dùng envelope lỗi chung) |

## 4.2 Processing

1. `reminder = SELECT reminder WHERE id = :reminderId`; không có ⇒ `404 REMINDER_NOT_FOUND`.
2. `vehicle = get_owned_active_vehicle(user, reminder.user_vehicle_id)` (FF BR-1708) — §4.3.
3. `currentStatus = UserVehicleService.get_maintenance_status(vehicle)` (us-017 API-VEH-003).
4. `hasCurrentBooking` = mốc tiếp theo hiện tại có booking `pending | confirmed | checked_in | in_progress` của xe (`has_milestone_booking`) (FF BR-1705).
5. `deliveries` = mọi `reminder_delivery` của lời nhắc, kèm `email_outbox` cùng `id` nếu có.
6. `details` = `reminder.details` (ảnh chụp lúc tạo). `NULL` ⇒ trả khung rỗng và `snapshotAvailable = false` (FF BR-1706).

Không ghi dữ liệu.

## 4.3 Errors

| HTTP | Code | Khi nào | FF |
|---|---|---|---|
| `404` | `REMINDER_NOT_FOUND` | Không có lời nhắc với id này, **hoặc** xe của lời nhắc không thuộc chủ xe (không phân biệt được hai trường hợp) | EF-1702, AC-1707 |
| `409` | `VEHICLE_NOT_ACTIVE` | Xe của chủ xe nhưng đã gỡ liên kết | EDGE-1708 |
| `422` | — | `reminderId` không phải UUID | — |

Q-1707 (đã chốt 07/10/2026): `ReminderContextService.get` bắt `VehicleNotFoundError` và trả `404 REMINDER_NOT_FOUND`, nên mã lỗi không để lộ lời nhắc của người khác có tồn tại. Tool AI `get_reminder_context` dùng chung service nên trả cùng mã.

## 4.4 Response — `200 OK`

```json
{
  "data": {
    "reminderId": "e0d4…",
    "userVehicleId": "3f5a…",
    "level": "EARLY",
    "odoMilestoneKm": 12000,
    "resolved": false,
    "resolutionReason": null,
    "snapshotAvailable": true,
    "details": {
      "templateVersion": "maintenance-v1",
      "dueStatus": "DUE_SOON",
      "reason": "KM",
      "dueDate": "2026-12-01",
      "remainingKm": 400,
      "remainingDays": 55,
      "monthMilestone": 12,
      "odometerKm": 11600,
      "odometerRecordedAt": "2026-10-01T09:00:00+00:00",
      "odometerStale": false,
      "leadDays": 2,
      "dueSoonKm": 500,
      "items": [{ "itemCode": "BRAKE_FLUID", "itemName": "Thay dầu phanh" }]
    },
    "currentStatus": { "dueStatus": "DUE_SOON", "nextMilestone": { "odoMilestoneKm": 12000, "dueDate": "2026-12-01", "…": "…" }, "…": "…" },
    "hasCurrentBooking": false,
    "deliveries": [
      { "id": "9b77…", "channel": "EMAIL", "status": "SENT", "deliveryState": "delivered", "attempts": 1, "errorCode": null, "sentAt": "2026-10-02T01:00:05+00:00", "mode": "resend" }
    ]
  }
}
```

| Field | Description | FF |
|---|---|---|
| `level`, `odoMilestoneKm`, `resolved`, `resolutionReason` | Như §3.3 | AF-1702 |
| `snapshotAvailable` | `false` ⇒ `details` là khung rỗng (`reason: "TIME"`, `dueDate: ""`, số liệu `null`, `items: []`), FE không được hiện như số liệu thật | BR-1706 |
| `details.reason` | `KM` / `TIME` / `BOTH` — điều kiện nào kích hoạt lời nhắc | BR-1705 |
| `details.odometerStale` | ODO lúc nhắc đã cũ | EDGE-1707 |
| `currentStatus` | Nguyên `MaintenanceStatus` của us-017 API-VEH-003 (camelCase) | EDGE-1706 |
| `hasCurrentBooking` | Mốc **hiện tại** đã có lịch đang mở | BR-1705, AC-1706 |
| `deliveries[].status` | `PENDING` / `SENT` / `FAILED` … (enum `reminder_delivery`) | BR-1705 |
| `deliveries[].deliveryState` | Trạng thái nhà cung cấp email: `accepted`, `delivered`, `delayed`, `bounced`, `complained`, `suppressed`, `failed`, `pending`, `cancelled`, `needs_reconciliation`, `mock`, hoặc `null` | BR-1705 |
| `deliveries[].mode` | `mock` / `resend` / `resend_test` / `null` | — |

> **Ghi chú kỹ thuật:** endpoint đang trả `dict` (không có `response_model`) nên không có trong schema OpenAPI. `[Đề xuất]` thêm schema `ReminderContextOut` để Swagger và test hợp đồng bắt được thay đổi.

---

# 5. Database / Entity Interaction

| Entity | Bảng | API | Read |
|---|---|---|---|
| `ENT-003` | `user_vehicle` | 003, 004 | Xe của chủ xe |
| `ENT-405` | `reminder` | 003, 004 | `scheduled_at`, `reminder_level`, `target_odo_milestone`, `is_resolved`, `resolution_reason`, `details` |
| `ENT-410` | `quote` | 003 | `status`, `reviewed_at`, `result_seen_at`, `approved_total`, `workshop_id` |
| `ENT-426` + `ENT-402` | `booking_status_event`, `booking` | 003 | `to_status`, `actor_type`, `reason_code`, `created_at`; `booking_code`, ngày giờ |
| `ENT-412` | `follow_up` | 003 | `status`, `sent_at` |
| `ENT-420` | `reminder_delivery` | 004 | `channel`, `status`, `attempts`, `error_code`, `sent_at` |
| — | `email_outbox` | 004 | `delivery_state`, `mode` |
| `ENT-008` | `workshop` | 003 | `name` |

Chi tiết index ở [Entity Spec](../entity/us-069-sprint-4-spec.entity.md) §4.

---

# 6. Idempotency, Concurrency, Caching

- Cả hai `GET` an toàn, idempotent.
- `unread` của `QUOTE_RESULT` đổi khi us-049 `API-QT-03` ghi `result_seen_at`; hộp thư không ghi gì (FF BR-1704).
- Không cache phía máy chủ. FE cache 60 giây (FE §6).

---

# 7. Observability & Performance

| Mục | Yêu cầu |
|---|---|
| Log | Access log kèm `traceId`; không log nội dung `details.items` hay `followUp` |
| Hiệu năng | `API-NOTI-003` ≤ 500 ms p90 (PRD §8): 4 truy vấn nguồn + tối đa 3 truy vấn tên xưởng, không N+1 |
| `API-NOTI-004` | Gọi `get_maintenance_status` (có thể kích hoạt tự đồng bộ ODO demo — us-017) ⇒ chấp nhận ≤ 800 ms p90 `[Đề xuất]` |

---

# 8. Test Coverage

| Test | File |
|---|---|
| Gộp 4 nguồn, thứ tự, `unreadCount` | `backend/tests/test_api/test_notification_feed_api.py::test_feed_merges_sources_newest_first_with_unread_count` |
| Bỏ thay đổi do chủ xe làm, mục cũ hơn 90 ngày, dữ liệu chủ xe khác | `test_feed_skips_own_actions_old_entries_and_other_owners` |
| `BOOKING_REMINDER`: `failed` không kênh ngoài vẫn hiện, `skipped` không hiện, `unread` theo xác nhận đến | `test_feed_lists_processed_appointment_reminders` |
| `API-NOTI-004`: có ảnh chụp, id lạ ⇒ 404, lời nhắc của người khác ⇒ `404 REMINDER_NOT_FOUND` | `backend/tests/test_api/test_main_email_api.py` |

---

# 9. Open Questions

| ID | Question | Status |
|---|---|---|
| `Q-1701` | Làm `BOOKING_REMINDER` (§3.4) | **Resolved** 07/10/2026 |
| `Q-1707` | Thống nhất mã lỗi `API-NOTI-004` (§4.3) | **Resolved** 07/10/2026 — `REMINDER_NOT_FOUND` |
| `Q-API-1701` | Thêm `response_model` cho `API-NOTI-004` (§4.4) | Open — `[Đề xuất]` có |
| `Q-1705` | API hộp thư chủ xưởng phía máy chủ | Open — `[Đề xuất]` chưa cần MVP |

---

# 10. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-10-07` | Team 4 Người | Bản đầu, theo endpoint đã triển khai; đề xuất `BOOKING_REMINDER` |
| `v1.1` | `2026-10-07` | Team 4 Người | Triển khai `BOOKING_REMINDER` (gồm lời nhắc `failed` chỉ đến được trong app); `API-NOTI-004` trả `REMINDER_NOT_FOUND` cho lời nhắc của người khác |

---

# 11. References

- [us-069 FF](../feature-functional/us-069-sprint-4-spec.ff.md) · [us-069 FE](../frontend/us-069-sprint-4-spec.fe.md) · [us-069 Entity](../entity/us-069-sprint-4-spec.entity.md)
- [us-021 API](../../sprint-2/api/us-021-sprint-2-spec.api.md) — `API-NOTI-001/002`
- [us-017 API](../../sprint-2/api/us-017-sprint-2-spec.api.md) — `API-VEH-003`
- [us-049 API](../../sprint-3/api/us-049-sprint-3-spec.api.md) — `API-QT-03`, `API-QT-11`
- [us-037 API](../../sprint-3/api/us-037-sprint-3-spec.api.md) — `API-WB-01`
