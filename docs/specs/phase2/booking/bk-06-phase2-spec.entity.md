# Entity Specification — Lịch bảo dưỡng định kỳ tại xưởng quen

> Entity cho Feature `FEAT-P2-BK06`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-06-phase2-spec.ff.md). **API:** [API Spec](bk-06-phase2-spec.api.md).
>
> **Nguyên tắc:** chuỗi là **cấu hình**, không phải các lịch giữ trước nhiều tháng (FF §2.1, §21). Mỗi lần trong chuỗi là một `booking` bình thường do BK-01 giữ chủ động, gắn `series_id`. Ngày kích hoạt luôn tính lại từ mốc F3 (không lưu cứng).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-BK06` — BK-06 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [bk-06-phase2-spec.ff.md](bk-06-phase2-spec.ff.md) |
| Related API | [bk-06-phase2-spec.api.md](bk-06-phase2-spec.api.md) |
| Related FE | [bk-06-phase2-spec.fe.md](bk-06-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-BK06-01` | `BookingSeries` | `booking_series` | **Mới** |
| `ENT-BK06-02` | `BookingSeriesOccurrence` | `booking_series_occurrence` | **Mới** — mỗi mốc một dòng (chống tạo trùng, ghi bỏ qua) |
| `ENT-402` | `Booking` | `booking` — **thêm cột** `series_id` | Có sẵn |

---

# 2. `booking_series` (ENT-BK06-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `user_vehicle_id` | `uuid` | No | — | FK `user_vehicle.id` `ON DELETE CASCADE` |
| `workshop_id` | `uuid` | No | — | FK `workshop.id`; xưởng của chuỗi |
| `constraints_override` | `jsonb` | No | `'{}'` | Ràng buộc riêng của chuỗi (khung rảnh); rỗng ⇒ dùng hồ sơ BK-01 hiện hành |
| `status` | `varchar(10)` | No | `'active'` | `active`, `paused`, `cancelled` |
| `pause_reason` | `varchar(24)` | Yes | `NULL` | `OWNER`, `WORKSHOP_INACTIVE` |
| `cancel_reason` | `varchar(24)` | Yes | `NULL` | `OWNER`, `OWNERSHIP_CHANGED` |
| `next_milestone_km` | `integer` | Yes | `NULL` | Mốc kế tiếp (đệm, tính lại hằng ngày) |
| `next_due_date` | `date` | Yes | `NULL` | Ngày đến hạn dự kiến (đệm, từ F3) |
| `next_trigger_date` | `date` | Yes | `NULL` | `next_due_date − SERIES_LEAD_DAYS` |
| `created_from_booking_id` | `uuid` | Yes | `NULL` | Lịch hoàn tất sinh lời mời (SCR-BK06-02) |
| `created_at` / `updated_at` | `timestamptz` | No | `now()` | |

```sql
-- BR-BK06-06: tối đa một chuỗi active / paused mỗi xe.
CREATE UNIQUE INDEX ux_booking_series_vehicle_live ON booking_series (user_vehicle_id) WHERE status IN ('active', 'paused');
CREATE INDEX ix_booking_series_trigger ON booking_series (next_trigger_date) WHERE status = 'active';
ALTER TABLE booking_series ADD CONSTRAINT ck_booking_series_status CHECK (status IN ('active','paused','cancelled'));
```

---

# 3. `booking_series_occurrence` (ENT-BK06-02)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `series_id` | `uuid` | No | — | FK `booking_series.id` `ON DELETE CASCADE` |
| `odo_milestone` | `integer` | No | — | Mốc của lần này |
| `status` | `varchar(16)` | No | — | `held` (đã giữ chủ động), `alternatives_offered` (xưởng chuỗi kín, AF-BK06-01), `confirmed`, `skipped`, `expired`, `superseded` (hãng báo đã làm nơi khác, EF-BK06-02), `no_option`, `skipped_due_unknown` |
| `booking_id` | `uuid` | Yes | `NULL` | FK `booking.id` `ON DELETE SET NULL` |
| `scheduling_run_id` | `uuid` | Yes | `NULL` | FK `scheduling_run.id` (BK-01) |
| `triggered_on` | `date` | No | — | Ngày job chạy (AC ngày chạy lại không tạo trùng) |
| `created_at` / `updated_at` | `timestamptz` | No | `now()` | |

```sql
-- Mỗi mốc của chuỗi tối đa một lần xử lý (FF §18).
CREATE UNIQUE INDEX ux_series_occurrence_milestone ON booking_series_occurrence (series_id, odo_milestone);
```

"Bỏ qua lần này" ⇒ `skipped` cho mốc đó; chuỗi tiếp tục với mốc sau (AC-BK06-02).

---

# 4. `booking` — cột mới

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `series_id` | `uuid` | Yes | FK `booking_series.id` `ON DELETE SET NULL`; Board hiện nhãn "Khách định kỳ" (FF §16) |

---

# 5. Business Rules (bổ sung)

## BR-ENT-BK06-01 — Một lịch mở mỗi xe

Job chỉ tạo khi xe không có lịch mở (us-029 BR-013, BR-BK06-04); unique occurrence + khoá Redis theo xe đảm bảo không trùng (AC-BK06-01).

## BR-ENT-BK06-02 — Xe đổi chủ

`user_vehicle` của chủ cũ chuyển `INACTIVE` vì đổi chủ ⇒ chuỗi `cancelled (OWNERSHIP_CHANGED)`, `constraints_override = '{}'` (EF-BK06-03).

---

# 6. Migration

Một revision: 2 bảng, cột `booking.series_id`, index.

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
