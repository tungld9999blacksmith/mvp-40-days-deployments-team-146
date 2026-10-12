# Entity Specification — Báo trễ chủ động hai chiều

> Entity cho Feature `FEAT-P2-BK08`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-08-phase2-spec.ff.md). **API:** [API Spec](bk-08-phase2-spec.api.md).
>
> **Nguyên tắc:** giờ bắt đầu dự kiến là giá trị **suy ra** (tính lại khi tiến độ đổi), lưu trên `booking` để đọc nhanh và để biết đã báo tới mức lệch nào. Mỗi lần báo (hai phía) là một dòng sự kiện để đếm giới hạn và làm dữ liệu cho BK-10. Không lưu vị trí chủ xe (FF §21).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-BK08` — BK-08 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [bk-08-phase2-spec.ff.md](bk-08-phase2-spec.ff.md) |
| Related API | [bk-08-phase2-spec.api.md](bk-08-phase2-spec.api.md) |
| Related FE | [bk-08-phase2-spec.fe.md](bk-08-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-402` | `Booking` | `booking` — **thêm cột** | Có sẵn |
| `ENT-BK08-01` | `BookingDelayReport` | `booking_delay_report` | **Mới** |
| — | `UserNotificationSetting` | `user_notification_setting` — thêm khoá `notify_early_start` | Có sẵn |

---

# 2. `booking` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `expected_start_at` | `timestamptz` | Yes | `NULL` | Giờ bắt đầu dự kiến (bộ ước tính); `NULL` = không có dữ liệu (EF-BK08-01) |
| `expected_start_computed_at` | `timestamptz` | Yes | `NULL` | |
| `last_notified_delay_min` | `smallint` | Yes | `NULL` | Mức lệch đã báo gần nhất (EDGE-BK08-01) |
| `owner_eta_at` | `timestamptz` | Yes | `NULL` | Giờ đến chủ xe báo hoặc chọn "Đến muộn hơn" |

`owner_eta_at` có giá trị ⇒ BK-02 ghi `grace_extended_until = owner_eta_at + NO_SHOW_GRACE_MIN` (cột của BK-02) để không tính lỡ hẹn trong khoảng đã báo (BR-BK08-02, AC-BK08-01).

---

# 3. `booking_delay_report` (ENT-BK08-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `booking_id` | `uuid` | No | — | FK `booking.id` `ON DELETE CASCADE` |
| `side` | `varchar(10)` | No | — | `WORKSHOP` (hệ thống báo thay xưởng), `OWNER` |
| `delay_min` | `smallint` | No | — | Xưởng: `expected_start − starts_at`; chủ xe: 10 / 20 / 30 |
| `new_time` | `timestamptz` | No | — | Giờ bắt đầu dự kiến mới / giờ đến mới |
| `owner_response` | `varchar(12)` | Yes | `NULL` | Với `WORKSHOP`: `ARRIVE_LATER`, `RESCHEDULE`, `NONE` |
| `responded_at` | `timestamptz` | Yes | `NULL` | |
| `created_at` | `timestamptz` | No | `now()` | |

```sql
CREATE INDEX ix_delay_report_booking ON booking_delay_report (booking_id, side, created_at);
ALTER TABLE booking_delay_report ADD CONSTRAINT ck_delay_side CHECK (side IN ('WORKSHOP','OWNER'));
ALTER TABLE booking_delay_report ADD CONSTRAINT ck_delay_owner_values CHECK (side <> 'OWNER' OR delay_min IN (10, 20, 30));
```

Giới hạn `DELAY_MAX_REPORTS` mỗi phía mỗi lịch (BR-BK08-03, AC-BK08-02) kiểm ở service (đếm theo `booking_id`, `side`) trong khoá theo booking.

---

# 4. Migration

Một revision: 4 cột `booking`, bảng mới. Khoá cài đặt thông báo `notify_early_start` (mặc định `false`, Q-BK08-01) thêm vào schema cài đặt có sẵn, không đổi bảng.

---

# 5. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
