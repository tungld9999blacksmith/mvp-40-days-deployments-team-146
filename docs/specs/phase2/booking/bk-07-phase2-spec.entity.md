# Entity Specification — Danh sách chờ

> Entity cho Feature `FEAT-P2-BK07`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-07-phase2-spec.ff.md). **API:** [API Spec](bk-07-phase2-spec.api.md).
>
> **Nguyên tắc:** chỗ giữ tạm cho người được mời là một `booking` **giữ chủ động** của BK-01 (`pending` + `proactive = true` + `hold_expires_at = now + WAITLIST_OFFER_MIN`) — dùng lại toàn bộ cơ chế sức chứa, khoá, hết hạn, xác nhận của BK-01. Danh sách chờ chỉ lưu đăng ký và lời mời.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-BK07` — BK-07 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [bk-07-phase2-spec.ff.md](bk-07-phase2-spec.ff.md) |
| Related API | [bk-07-phase2-spec.api.md](bk-07-phase2-spec.api.md) |
| Related FE | [bk-07-phase2-spec.fe.md](bk-07-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-BK07-01` | `BookingWaitlist` | `booking_waitlist` | **Mới** — một đăng ký chờ |
| `ENT-BK07-02` | `WaitlistOffer` | `waitlist_offer` | **Mới** — một lời mời |
| `ENT-402` | `Booking` | `booking` | Có sẵn — chỗ giữ tạm dùng cột BK-01 |

---

# 2. `booking_waitlist` (ENT-BK07-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `user_vehicle_id` | `uuid` | No | — | FK `user_vehicle.id` `ON DELETE CASCADE` |
| `workshop_id` | `uuid` | No | — | Một xưởng mỗi đăng ký (FF §3.2) |
| `odo_milestone` | `integer` | Yes | `NULL` | Mốc cần làm (để tự rời khi đã có lịch, BR-BK07-04) |
| `service_kind` | `varchar(16)` | No | `'MAINTENANCE'` | BK-03 |
| `window_date` | `date` | No | — | Ngày |
| `window_start` / `window_end` | `time` | No | — | Khung cụ thể: `end = start + SLOT_UNIT_MIN`; khoảng: ví dụ 08:00–12:00 (BR-BK07-01) |
| `status` | `varchar(10)` | No | `'waiting'` | `waiting`, `offered`, `fulfilled`, `declined`, `expired`, `left` (FF §13) |
| `queued_at` | `timestamptz` | No | `now()` | Thứ tự (BR-BK07-03) |
| `priority_tier` | `smallint` | No | `0` | `1` khi chủ xe ở bậc `RESTRICTED` (BK-02) ⇒ xếp sau; tính lúc mời |
| `keep_after_decline` | `boolean` | No | `true` | "Chờ lần khác" khi từ chối |
| `left_reason` | `varchar(20)` | Yes | `NULL` | `OWNER`, `BOOKED_ELSEWHERE`, `WINDOW_PASSED` |
| `created_at` / `updated_at` | `timestamptz` | No | `now()` | |

```sql
CREATE INDEX ix_waitlist_match ON booking_waitlist (workshop_id, window_date, status, priority_tier, queued_at)
  WHERE status IN ('waiting', 'declined');
CREATE INDEX ix_waitlist_user_live ON booking_waitlist (user_id) WHERE status IN ('waiting', 'offered', 'declined');
ALTER TABLE booking_waitlist ADD CONSTRAINT ck_waitlist_window CHECK (window_start < window_end);
ALTER TABLE booking_waitlist ADD CONSTRAINT ck_waitlist_status CHECK (status IN ('waiting','offered','fulfilled','declined','expired','left'));
```

`WAITLIST_MAX` (BR-BK07-04) kiểm ở service: số mục `waiting | offered | declined(keep_after_decline)` của chủ xe.

`declined` + `keep_after_decline = true` vẫn được ghép cho chỗ trống **sau**; không được mời lại cho cùng chỗ đã từ chối.

---

# 3. `waitlist_offer` (ENT-BK07-02)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `waitlist_id` | `uuid` | No | — | FK `booking_waitlist.id` `ON DELETE CASCADE` |
| `workshop_id` | `uuid` | No | — | |
| `slot_date` / `slot_time` | `date` / `time` | No | — | Chỗ trống được mời |
| `slot_key` | `varchar(80)` | No | — | `{workshopId}:{date}:{time}:{seq}` — một chỗ trống cụ thể (seq phân biệt khi cùng khung trống nhiều chỗ) |
| `hold_booking_id` | `uuid` | Yes | `NULL` | FK `booking.id` `ON DELETE SET NULL` — chỗ giữ tạm (BK-01 giữ chủ động) |
| `status` | `varchar(10)` | No | `'open'` | `open`, `accepted`, `declined`, `expired`, `voided` (EF-BK07-02) |
| `expires_at` | `timestamptz` | No | — | `sent_at + WAITLIST_OFFER_MIN` |
| `sent_at` / `responded_at` | `timestamptz` | | | |

```sql
-- BR-BK07-06 / AC-BK07-01: một lời mời đang mở mỗi chỗ trống.
CREATE UNIQUE INDEX ux_waitlist_offer_open_slot ON waitlist_offer (slot_key) WHERE status = 'open';
CREATE UNIQUE INDEX ux_waitlist_offer_open_entry ON waitlist_offer (waitlist_id) WHERE status = 'open';
CREATE INDEX ix_waitlist_offer_expiry ON waitlist_offer (expires_at) WHERE status = 'open';
```

---

# 4. Retention

Mục `fulfilled` / `expired` / `left` xoá sau 90 ngày (job); lời mời theo cascade.

---

# 5. Migration

Một revision: 2 bảng + index + CHECK.

---

# 6. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
