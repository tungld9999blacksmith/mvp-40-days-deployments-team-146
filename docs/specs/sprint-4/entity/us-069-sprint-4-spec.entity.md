# Entity Specification — Hộp thư Thông báo trong app

> Entity cho Feature `FEAT-NOTI-003` (US-069 → US-072).
>
> **Nguyên tắc:** **không có bảng thông báo.** Hộp thư được dựng khi đọc từ dữ liệu các tính năng đã giữ (FF BR-1702). Tài liệu này ghi các bảng nguồn, cột được đọc, truy vấn và index, các cột đã thêm sau spec gốc nhưng chưa được ghi vào entity spec, và đề xuất cho BR-1707.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-NOTI-003` — F7 kênh trong app |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-07` |
| Related FF | [us-069-sprint-4-spec.ff.md](../feature-functional/us-069-sprint-4-spec.ff.md) |
| Related API | [us-069-sprint-4-spec.api.md](../api/us-069-sprint-4-spec.api.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Vai trò ở feature này |
|---|---|---|---|---|
| `ENT-405` | `Reminder` | `reminder` | Có sẵn — cột mới chưa ghi spec (§3) | Nhắc bảo dưỡng + ảnh chụp dữ liệu |
| `ENT-420` | `ReminderDelivery` | `reminder_delivery` | Có sẵn — không đổi | Từng lần gửi theo kênh |
| — | `EmailOutbox` | `email_outbox` | Có sẵn — **chưa có entity spec** (§3) | Trạng thái nhà cung cấp email |
| `ENT-410` | `Quote` | `quote` | Có sẵn — không đổi | Kết quả báo giá, `result_seen_at` |
| `ENT-426` | `BookingStatusEvent` | `booking_status_event` | Có sẵn — không đổi | Cập nhật lịch hẹn |
| `ENT-402` | `Booking` | `booking` | Có sẵn — không đổi | Mã, ngày giờ, chủ |
| `ENT-412` | `FollowUp` | `follow_up` | Có sẵn — không đổi | Lời mời đánh giá |
| `ENT-424` | `BookingReminder` | `booking_reminder` | Có sẵn — không đổi | Nhắc 24h — FF BR-1707 |
| `ENT-003` | `UserVehicle` | `user_vehicle` | Có sẵn — không đổi | Xe của chủ xe |
| `ENT-008` | `Workshop` | `workshop` | Có sẵn — không đổi | Tên xưởng |

---

# 2. Cột được đọc theo loại mục

| Loại | Bảng | Cột |
|---|---|---|
| `MAINTENANCE_REMINDER` | `reminder` | `id`, `user_vehicle_id`, `reminder_level`, `target_odo_milestone`, `is_resolved`, `resolution_reason`, `scheduled_at` |
| `QUOTE_RESULT` | `quote` | `id`, `user_vehicle_id`, `workshop_id`, `status`, `approved_total`, `reviewed_at`, `result_seen_at` |
| `BOOKING_UPDATE` | `booking_status_event` ⨝ `booking` | `id`, `to_status`, `actor_type`, `reason_code`, `created_at`; `booking.id`, `booking_code`, `booking_date`, `time_slot`, `workshop_id`, `user_id` |
| `BOOKING_REMINDER` | `booking_reminder` ⨝ `booking` | `id`, `status`, `scheduled_at`, `sent_at`, `appointment_at`; `booking.id`, `booking_code`, `booking_date`, `time_slot`, `status`, `attendance_confirmed_at`, `workshop_id`, `user_id` |
| `FOLLOW_UP` | `follow_up` ⨝ `booking` | `id`, `status`, `sent_at`, `booking_id`; `booking.user_id`, `workshop_id` |
| Chi tiết lời nhắc | `reminder`, `reminder_delivery`, `email_outbox` | `reminder.details`; `reminder_delivery.channel`, `status`, `attempts`, `error_code`, `sent_at`; `email_outbox.delivery_state`, `mode` |

Không có cột nào được ghi bởi hộp thư. `quote.result_seen_at` do us-049 API-QT-03 ghi (FF BR-1704).

---

# 3. Cột đã có trong DB nhưng chưa có entity spec

Migration `e7a9c2b4d6f8_email_outbox.py` (email nhắc bảo dưỡng) thêm các cột/bảng dưới đây. Entity spec của us-021 chưa ghi. `[Đề xuất]` cập nhật [reminder.entity.md](../../entity/maintenance/reminder.entity.md) và thêm entity spec cho `email_outbox` (mã ENT mới, dải `ENT-49x`).

| Bảng | Cột | Type | Nullable | Ý nghĩa |
|---|---|---|---:|---|
| `reminder` | `details` | `json` | Yes | Ảnh chụp lúc tạo: `templateVersion`, `dueStatus`, `reason` (`KM`/`TIME`/`BOTH`), `dueDate`, `remainingKm`, `remainingDays`, `monthMilestone`, `odometerKm`, `odometerRecordedAt`, `odometerStale`, `leadDays`, `dueSoonKm`, `items[]`. `NULL` ở lời nhắc cũ (FF BR-1706) |
| `reminder` | `resolution_reason` | `varchar(32)` | Yes | `HAS_BOOKING`, `MAINTENANCE_COMPLETED`, `MILESTONE_CHANGED`, `SUPERSEDED`, `BEFORE_WINDOW`, `STATUS_CHANGED` |
| `email_outbox` | `delivery_id` (PK, FK → `reminder_delivery.id` `ON DELETE CASCADE`), `user_id`, `user_vehicle_id`, `mode`, `recipient`, `recipient_hash`, `payload`, `delivery_state`, `provider_message_id`, các mốc thời gian thử lại … | — | — | Hàng đợi và kết quả gửi email; `payload` xoá sau `email_payload_retention_days` (mặc định 30) |

---

# 4. Index & Query

| Truy vấn (API-NOTI-003) | Index dùng | Ghi chú |
|---|---|---|
| `reminder WHERE user_vehicle_id IN (…) AND scheduled_at ≥ since` | `ix_reminder_user_vehicle_id` | Mỗi xe có vài lời nhắc (BR-502 us-021) ⇒ đủ |
| `quote WHERE user_vehicle_id IN (…) AND status IN (approved, rejected) AND reviewed_at ≥ since` | `ix_quote_user_vehicle_created` (lọc tiếp trong bộ nhớ DB) | Ít báo giá/xe |
| `booking_status_event ⨝ booking WHERE booking.user_id = uid AND …` | `ix_booking_user_id`, `ix_bse_booking_created` | — |
| `follow_up ⨝ booking WHERE booking.user_id = uid AND status = 'sent' AND sent_at ≥ since` | `ix_booking_user_id`; `ix_follow_up_sent_sent_at` (partial) | — |
| `workshop WHERE id IN (…)` | PK | 1 truy vấn mỗi nguồn |
| (API-NOTI-004) `reminder_delivery WHERE reminder_id = :id`, `email_outbox` theo PK | `ux_reminder_delivery_reminder_channel (reminder_id, channel)`, PK | — |

Không cần index mới với lượng dữ liệu MVP (FF §20).

---

# 5. FF BR-1707 — nhắc lịch hẹn 24h

Không cần bảng mới: đọc `booking_reminder` (ENT-424) `WHERE status IN ('sent','failed') AND scheduled_at ≥ since` ⨝ `booking` theo `booking.user_id` (index `ix_booking_user_id`). Gồm `failed` vì lời nhắc không có kênh ngoài nào bị job đặt `failed` mà không có `sent_at` (API §3.4). Mỗi lịch hẹn có tối đa vài lời nhắc nên không cần index mới.

---

# 6. Vì sao không có bảng `in_app_notification`

| Phương án | Ưu | Nhược |
|---|---|---|
| **Dựng khi đọc (đang dùng)** | Không job ghi, không lệch dữ liệu giữa thông báo và nguồn; thêm loại chỉ cần thêm một nguồn | Không có "đã đọc" chung; cửa sổ 90 ngày/50 mục cố định |
| Bảng `in_app_notification` | Đã đọc, xoá, phân trang, đẩy realtime | Mỗi tính năng phải ghi thêm; cần migration + backfill |

Giữ phương án hiện tại cho MVP; xem lại khi chốt us-049 Q-ENT-1103 / FF Q-1702.

---

# 7. Ownership, Sensitivity & Retention

| Mục | Quy tắc |
|---|---|
| Ownership | Mọi nguồn lọc theo xe hoặc booking của chủ xe (FF BR-1708) |
| Sensitivity | Không trả VIN, SĐT, email, CCCD (FF BR-1709). `email_outbox.recipient` (địa chỉ email) và `payload` (nội dung email) ⇒ không trả qua API-NOTI-004 |
| Retention | Hộp thư chỉ đọc 90 ngày gần nhất; dữ liệu nguồn giữ theo spec của từng bảng |

---

# 8. Open Questions

| ID | Question | Status |
|---|---|---|
| `Q-ENT-1701` | Cập nhật `reminder.entity.md` (cột `details`, `resolution_reason`) và viết entity spec cho `email_outbox` | Open — `[Đề xuất]` làm cùng đợt cập nhật us-021 |
| `Q-1702` / `Q-ENT-1103` | Bảng `in_app_notification` | Open — `[Đề xuất]` chưa cần MVP |

---

# 9. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-10-07` | Team 4 Người | Bản đầu |
