# Entity Specification — Sức chứa theo thời lượng và hạn phản hồi

> Entity cho Feature `FEAT-P2-WS02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ws-02-phase2-spec.ff.md). **API:** [API Spec](ws-02-phase2-spec.api.md).
>
> **Nguyên tắc:** khoảng chiếm của lịch (`starts_at`, `ends_at`) được tính một lần lúc giữ chỗ và lưu trên `booking`, để mọi truy vấn sức chứa chỉ là phép chồng lấn khoảng. Xưởng chưa bật mô hình thời lượng vẫn dùng đúng công thức MVP (BR-WS02-08).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-WS02` — WS-02 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [ws-02-phase2-spec.ff.md](ws-02-phase2-spec.ff.md) |
| Related API | [ws-02-phase2-spec.api.md](ws-02-phase2-spec.api.md) |
| Related FE | [ws-02-phase2-spec.fe.md](ws-02-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-WS02-01` | `ServiceItemDuration` | `service_item_duration` | **Mới** | Thời lượng chuẩn theo hạng mục (mặc định + theo xưởng) |
| `ENT-WS02-02` | `BookingDurationSample` | `booking_duration_sample` | **Mới** | Thời lượng thực tế của lịch đã xong |
| `ENT-WS02-03` | `DurationAdjustmentSuggestion` | `duration_adjustment_suggestion` | **Mới** | Đề xuất chỉnh thời lượng (job tuần) |
| `ENT-402` | `Booking` | `booking` | Có sẵn — **thêm cột** | `duration_min`, `duration_source`, `starts_at`, `ends_at` |
| `ENT-008` | `Workshop` | `workshop` | Có sẵn — **thêm cột** | `duration_model_enabled` |
| — | `WorkshopSlotBlock` | `workshop_slot_block` | Có sẵn — **thêm cột** | `end_time` (khoá theo khoảng) |
| — | `BookingReminder` | `booking_reminder` | Có sẵn — thêm loại | `WS_CONFIRM_REMIND` (nhắc chủ xưởng duyệt) |

---

# 2. `service_item_duration` (ENT-WS02-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `item_code` | `varchar(50)` | No | — | Khớp `maintenance_rule.item_code` / `booking_line.item_code` |
| `workshop_id` | `uuid` | Yes | `NULL` | FK `workshop.id` `ON DELETE CASCADE`; `NULL` = mặc định toàn hệ thống |
| `duration_min` | `smallint` | No | — | `5..600`, bội số của 5 |
| `source` | `varchar(16)` | No | — | `OEM_DOC` (tài liệu hãng), `ADMIN`, `WORKSHOP`, `ACTUAL_MEDIAN` (chủ xưởng bấm "Dùng số thực tế") |
| `updated_by_owner_id` | `uuid` | Yes | `NULL` | FK `workshop_owner.id` `ON DELETE SET NULL` |
| `created_at` / `updated_at` | `timestamptz` | No | `now()` | |

```sql
CREATE UNIQUE INDEX ux_sid_default ON service_item_duration (item_code) WHERE workshop_id IS NULL;
CREATE UNIQUE INDEX ux_sid_workshop ON service_item_duration (workshop_id, item_code) WHERE workshop_id IS NOT NULL;
ALTER TABLE service_item_duration ADD CONSTRAINT ck_sid_duration
  CHECK (duration_min BETWEEN 5 AND 600 AND duration_min % 5 = 0);
ALTER TABLE service_item_duration ADD CONSTRAINT ck_sid_source
  CHECK (source IN ('OEM_DOC', 'ADMIN', 'WORKSHOP', 'ACTUAL_MEDIAN'));
```

**Tra cứu (BR-WS02-01):** dòng của xưởng → dòng mặc định → `LEGACY_BOOKING_MIN` (EF-WS02-02, log `capacity.duration_missing`).

---

# 3. `booking` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `duration_min` | `smallint` | No | `60` | Σ thời lượng chuẩn, làm tròn lên `SLOT_UNIT_MIN` (BR-WS02-01). Lịch cũ = `LEGACY_BOOKING_MIN` |
| `duration_source` | `varchar(12)` | No | `'LEGACY'` | `ITEMS` (tính từ hạng mục), `LEGACY` (không rõ hạng mục, AF-WS02-01), `MVP_SLOT` (xưởng chưa bật) |
| `starts_at` | `timestamptz` | No | — | `booking_date + time_slot` theo Asia/Ho_Chi_Minh, lưu UTC |
| `ends_at` | `timestamptz` | No | — | `starts_at + duration_min` |

```sql
ALTER TABLE booking ADD CONSTRAINT ck_booking_interval CHECK (ends_at > starts_at);
ALTER TABLE booking ADD CONSTRAINT ck_booking_duration CHECK (duration_min > 0 AND duration_min <= 600);
-- Truy vấn chồng lấn theo xưởng.
CREATE INDEX ix_booking_workshop_interval ON booking (workshop_id, starts_at, ends_at)
  WHERE status IN ('pending', 'confirmed', 'checked_in', 'in_progress');
```

- `starts_at` luôn đồng bộ với `booking_date` + `time_slot`; mọi chỗ đổi giờ (đổi lịch us-053, BK-01) tính lại cả hai cột. Giữ `booking_date` / `time_slot` vì code MVP và frontend đọc chúng.
- Gộp việc (HS-02) đổi hạng mục ⇒ tính lại `duration_min`, `ends_at` sau khi kiểm tra sức chứa (EDGE-WS02-02).

---

# 4. `workshop` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `duration_model_enabled` | `boolean` | No | `false` | BR-WS02-08. `false` ⇒ sức chứa như MVP (AC-WS02-04) |

Chỗ dự phòng dùng cột có sẵn `emergency_slots_reserved` (SCR-WS02-03 chỉ đề xuất, chủ xưởng ghi vào cột này).

---

# 5. `workshop_slot_block` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `end_time` | `time` | Yes | `NULL` | `NULL` = khoá một khung `SLOT_UNIT_MIN` bắt đầu ở `time_slot` (như MVP). Có giá trị ⇒ khoá `[time_slot, end_time)` (BR-WS02-07) |

```sql
ALTER TABLE workshop_slot_block ADD CONSTRAINT ck_wsb_end CHECK (end_time IS NULL OR end_time > time_slot);
```

---

# 6. `booking_duration_sample` (ENT-WS02-02)

Ghi khi lịch có tiến độ `ready_for_pickup` (hook service_progress).

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `booking_id` | `uuid` | No | — | PK, FK `booking.id` `ON DELETE CASCADE` |
| `workshop_id` | `uuid` | No | — | FK `workshop.id` |
| `item_codes` | `jsonb` | No | — | Mảng mã hạng mục đã sắp, từ `booking_line` (`kind = PACKAGE` + `EXTRA` đã duyệt) |
| `planned_min` | `smallint` | No | — | `booking.duration_min` lúc làm |
| `actual_min` | `smallint` | No | — | `ready_for_pickup.created_at − servicing.created_at` (bước `servicing` đầu tiên); không có `servicing` ⇒ từ `inspecting`; trừ thời gian ở `waiting_parts` |
| `excluded` | `boolean` | No | `false` | `true` khi `actual_min` < 10 hoặc > 3 × `planned_min` (dữ liệu bất thường, không tính trung vị) |
| `recorded_at` | `timestamptz` | No | `now()` | |

```sql
CREATE INDEX ix_bds_workshop_time ON booking_duration_sample (workshop_id, recorded_at);
```

Phân bổ cho từng hạng mục khi tính trung vị: mẫu một hạng mục dùng thẳng; mẫu nhiều hạng mục phân bổ `actual_min` theo tỉ lệ thời lượng chuẩn.

---

# 7. `duration_adjustment_suggestion` (ENT-WS02-03)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `workshop_id` | `uuid` | No | — | FK `workshop.id` `ON DELETE CASCADE` |
| `item_code` | `varchar(50)` | No | — | |
| `current_min` | `smallint` | No | — | |
| `median_min` | `smallint` | No | — | Trung vị 30 ngày, làm tròn 5 phút |
| `sample_count` | `smallint` | No | — | ≥ 10 (BR-WS02-06) |
| `status` | `varchar(12)` | No | `'open'` | `open`, `applied`, `dismissed`, `superseded` |
| `created_at` / `resolved_at` | `timestamptz` | — | | |

```sql
CREATE UNIQUE INDEX ux_das_open ON duration_adjustment_suggestion (workshop_id, item_code) WHERE status = 'open';
```

Chỉ tạo khi `|median − current| / current > 20 %` và `sample_count ≥ 10`.

---

# 8. Business Rules (bổ sung)

## BR-ENT-WS02-01 — Chồng lấn là nửa mở

Hai lịch chồng nhau khi `a.starts_at < b.ends_at AND b.starts_at < a.ends_at`. Lịch kết thúc 10:30 và lịch bắt đầu 10:30 không chồng.

## BR-ENT-WS02-02 — Sức chứa từng đơn vị

Với mỗi đơn vị `u` (dài `SLOT_UNIT_MIN`) trong `[starts_at, ends_at)`: `available(u) = total_technicians − emergency_slots_reserved − blocked(u) − occupied(u)`; giữ chỗ chỉ khi `available(u) ≥ 1` với **mọi** `u` (BR-WS02-02, BR-WS02-07). `occupied(u)` đếm lịch có trạng thái chiếm chỗ (`_OCCUPYING` của MVP) chồng lên `u`, trừ lịch đang đổi (EDGE-WS02-03).

## BR-ENT-WS02-03 — Không vượt giờ đóng cửa

`ends_at` ≤ giờ đóng cửa của ngày đó (AF-WS02-02). Không có lịch qua đêm.

## BR-ENT-WS02-04 — Bật / tắt mô hình

Bật `duration_model_enabled` không đổi lịch đã có (giữ `duration_min` đã lưu). Tắt ⇒ sức chứa quay về đếm theo `time_slot` của MVP cho lịch mới; lịch dài đã có vẫn chiếm theo khoảng cho tới khi kết thúc (tránh vượt chỗ).

---

# 9. Migration

- Một revision: 3 bảng, 4 cột `booking`, 1 cột `workshop`, 1 cột `workshop_slot_block`, index + CHECK.
- **Backfill `booking`** (theo lô 1.000 dòng): `duration_min = LEGACY_BOOKING_MIN`, `duration_source = 'LEGACY'`, `starts_at = (booking_date + time_slot) AT TIME ZONE 'Asia/Ho_Chi_Minh'`, `ends_at = starts_at + 60 phút`. Sau backfill mới đặt `NOT NULL`.
- Seed `service_item_duration` mặc định từ danh sách `item_code` của `maintenance_rule` (Q-WS02-02: tài liệu hãng; thiếu thì 60).
- `downgrade`: drop cột / bảng; dữ liệu thời lượng mất (chấp nhận).

---

# 10. Open Questions

| ID | Câu hỏi | Đề xuất |
|---|---|---|
| `Q-ENT-WS02-01` | Có cần lưu `actual_min` theo từng hạng mục (KTV bấm từng việc, WS-03)? | Phase sau, khi WS-03 có trạng thái từng việc |
| `Q-ENT-WS02-02` | `SLOT_UNIT_MIN` khác `slot_minutes` MVP (60)? | Xưởng bật thời lượng ⇒ khung bắt đầu theo `SLOT_UNIT_MIN` (30) |

---

# 11. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
