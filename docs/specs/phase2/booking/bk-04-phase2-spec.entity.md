# Entity Specification — Widget lịch

> Entity cho Feature `FEAT-P2-BK04`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-04-phase2-spec.ff.md). **API:** [API Spec](bk-04-phase2-spec.api.md).
>
> **Nguyên tắc:** chỉ lưu khoảng bận (bắt đầu, kết thúc) — không tiêu đề, không nội dung, không người tham dự (BR-BK04-02, AC-BK04-02). Token OAuth mã hoá khi lưu. Mọi dữ liệu lịch cá nhân phụ thuộc `CONSENT_CALENDAR_SYNC` (PL-01) và bị xoá theo eraser của PL-01.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-BK04` — BK-04 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [bk-04-phase2-spec.ff.md](bk-04-phase2-spec.ff.md) |
| Related API | [bk-04-phase2-spec.api.md](bk-04-phase2-spec.api.md) |
| Related FE | [bk-04-phase2-spec.fe.md](bk-04-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-BK04-01` | `CalendarConnection` | `calendar_connection` | **Mới** | Một kết nối Google mỗi chủ xe |
| `ENT-BK04-02` | `CalendarBusyCache` | `calendar_busy_cache` | **Mới** | Khoảng bận, sống ≤ 24 giờ |
| `ENT-BK04-03` | `BookingCalendarEvent` | `booking_calendar_event` | **Mới** | Booking ↔ sự kiện Google / `.ics` đã xuất |

---

# 2. `calendar_connection` (ENT-BK04-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `user_id` | `bigint` | No | — | PK, FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `provider` | `varchar(16)` | No | `'GOOGLE'` | Chỉ `GOOGLE` ở Phase 2 |
| `status` | `varchar(16)` | No | — | `connected`, `revoked`, `error` (`not_connected` = không có dòng) |
| `scopes` | `jsonb` | No | — | Tập con của `["freebusy", "events"]`; `events` = có quyền ghi (Q-BK04-01: tuỳ chọn) |
| `calendar_ids` | `jsonb` | No | `'["primary"]'` | Lịch dùng để đọc bận/rảnh (EDGE-BK04-02) |
| `access_token_enc` | `bytea` | Yes | `NULL` | Mã hoá AES-GCM, khoá từ `CALENDAR_TOKEN_KEY` (Secret Manager / env), không log |
| `refresh_token_enc` | `bytea` | Yes | `NULL` | Như trên |
| `token_expires_at` | `timestamptz` | Yes | `NULL` | |
| `last_error_code` | `varchar(40)` | Yes | `NULL` | `invalid_grant`, `rate_limited`, `network` … (không lưu thông điệp) |
| `last_synced_at` | `timestamptz` | Yes | `NULL` | Lần đọc bận/rảnh thành công gần nhất |
| `connected_at` / `updated_at` | `timestamptz` | No | `now()` | |

```sql
ALTER TABLE calendar_connection ADD CONSTRAINT ck_cc_status CHECK (status IN ('connected', 'revoked', 'error'));
ALTER TABLE calendar_connection ADD CONSTRAINT ck_cc_tokens
  CHECK (status <> 'revoked' OR (access_token_enc IS NULL AND refresh_token_enc IS NULL));
```

`revoked` ⇒ token đã xoá (PL-01 HOOK, EF-BK04-02).

---

# 3. `calendar_busy_cache` (ENT-BK04-02)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `busy_start` | `timestamptz` | No | — | |
| `busy_end` | `timestamptz` | No | — | `> busy_start` |
| `all_day` | `boolean` | No | `false` | EDGE-BK04-01: cả ngày bận |
| `range_start` / `range_end` | `date` | No | — | Khoảng đã truy vấn (để biết ngày "rảnh" thật vs "chưa tải") |
| `fetched_at` | `timestamptz` | No | `now()` | |
| `expires_at` | `timestamptz` | No | — | `fetched_at + 24h` (BR-BK04-07) |

```sql
CREATE INDEX ix_cbc_user_range ON calendar_busy_cache (user_id, busy_start);
CREATE INDEX ix_cbc_expires ON calendar_busy_cache (expires_at);
```

**Không có cột** tiêu đề, mô tả, địa điểm, người tham dự, id sự kiện nguồn. API free/busy của Google cũng không trả các trường này.

---

# 4. `booking_calendar_event` (ENT-BK04-03)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `booking_id` | `uuid` | No | — | FK `booking.id` `ON DELETE CASCADE` |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `kind` | `varchar(8)` | No | — | `GOOGLE`, `ICS` |
| `external_event_id` | `varchar(256)` | Yes | `NULL` | Id sự kiện Google; `NULL` khi `ICS` |
| `ics_uid` | `varchar(128)` | No | — | `booking-{bookingId}@evcare` — giữ nguyên qua các lần cập nhật để ứng dụng lịch thay thế đúng sự kiện |
| `ics_sequence` | `integer` | No | `0` | Tăng mỗi lần đổi giờ / huỷ (chuẩn iCalendar `SEQUENCE`) |
| `status` | `varchar(10)` | No | `'created'` | `created`, `updated`, `deleted`, `orphaned` (chủ xe tự xoá trong Calendar, EF-BK04-03) |
| `last_pushed_at` | `timestamptz` | Yes | `NULL` | |
| `created_at` / `updated_at` | `timestamptz` | No | `now()` | |

```sql
CREATE UNIQUE INDEX ux_bce_booking_kind ON booking_calendar_event (booking_id, kind) WHERE status <> 'deleted';
ALTER TABLE booking_calendar_event ADD CONSTRAINT ck_bce_google_id
  CHECK (kind <> 'GOOGLE' OR external_event_id IS NOT NULL);
```

---

# 5. Nội dung sự kiện (BR-BK04-06)

| Trường iCal / Google | Giá trị |
|---|---|
| `summary` | "Bảo dưỡng xe tại {tên xưởng}" |
| `location` | Địa chỉ xưởng |
| `start` / `end` | `booking.starts_at` / `ends_at` (WS-02; không có thì + 60 phút) |
| `description` | "Mã lịch hẹn: {booking_code}\nMở EV Care: {APP_BASE_URL}/bookings/{bookingId}" |

**Không** ghi VIN, biển số, chi phí, hạng mục, tên chủ xe.

---

# 6. Retention

| Bảng | Giữ | Xoá |
|---|---|---|
| `calendar_busy_cache` | ≤ 24 giờ | Job `calendar.purge_busy_cache` mỗi giờ xoá `expires_at ≤ now` |
| `calendar_connection` | Đến khi ngắt / thu hồi đồng ý | PL-01 eraser `CONSENT_CALENDAR_SYNC` |
| `booking_calendar_event` | Theo booking | PL-01 eraser khi `keepCreatedEvents = false` (xoá sự kiện Google trước rồi xoá dòng) |

---

# 7. Migration

Một revision: 3 bảng, index, CHECK. Không backfill.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
