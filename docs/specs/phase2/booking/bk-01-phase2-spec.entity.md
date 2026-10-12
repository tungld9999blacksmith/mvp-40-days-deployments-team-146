# Entity Specification — Tự động lập lịch theo ràng buộc của chủ xe

> Entity cho Feature `FEAT-P2-BK01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-01-phase2-spec.ff.md). **API:** [API Spec](bk-01-phase2-spec.api.md).
>
> **Nguyên tắc:** hồ sơ thói quen là dữ liệu của chủ xe (sửa được, có nguồn từng ràng buộc). Mỗi lần chạy bộ lập lịch là một bản ghi bất biến kèm các phương án có hạn, để chọn phương án theo `optionId` và để đo M-01 / M-03. `booking` không thêm trạng thái (README §8); giữ chủ động là `pending` + cờ.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-BK01` — BK-01 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [bk-01-phase2-spec.ff.md](bk-01-phase2-spec.ff.md) |
| Related API | [bk-01-phase2-spec.api.md](bk-01-phase2-spec.api.md) |
| Related FE | [bk-01-phase2-spec.fe.md](bk-01-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-BK01-01` | `OwnerSchedulingProfile` | `owner_scheduling_profile` | **Mới** | Một dòng mỗi chủ xe |
| `ENT-BK01-02` | `OwnerSchedulingConstraint` | `owner_scheduling_constraint` | **Mới** | Ràng buộc theo dòng, có nguồn |
| `ENT-BK01-03` | `SchedulingRun` | `scheduling_run` | **Mới** | Một lần chạy bộ lập lịch |
| `ENT-BK01-04` | `SchedulingOption` | `scheduling_option` | **Mới** | Phương án của một lần chạy |
| `ENT-402` | `Booking` | `booking` | Có sẵn — **thêm cột** | `proactive`, `proactive_confirmed_at`, `auto_booked`, `free_cancel_until`, `scheduling_option_id`, `replaced_booking_id` |
| `ENT-426` | `BookingStatusEvent` | `booking_status_event` | Có sẵn — thêm giá trị `reason_code` | `PROACTIVE_HOLD_EXPIRED`, `PROACTIVE_HOLD_DISMISSED`, `RESCHEDULED_TO_OTHER_WORKSHOP`, `WORKSHOP_UNABLE_*` |
| — | `UserLocation` | `user_location` | Có sẵn — không đổi | Điểm neo Nhà / Chỗ làm |

---

# 2. `owner_scheduling_profile` (ENT-BK01-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `user_id` | `bigint` | No | — | PK, FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `automation_level` | `varchar(12)` | No | `'HOLD'` | `SUGGEST` (mức 1), `HOLD` (mức 2, mặc định), `AUTO_BOOK` (mức 3) |
| `anchor_type` | `varchar(12)` | Yes | `NULL` | `HOME`, `WORK`, `DEVICE`, `PROVINCE` |
| `anchor_location_id` | `uuid` | Yes | `NULL` | FK `user_location.id` `ON DELETE SET NULL`; khi `HOME` / `WORK` |
| `anchor_province` | `varchar(100)` | Yes | `NULL` | Khi `PROVINCE` hoặc dự phòng khi không có toạ độ |
| `radius_km` | `numeric(5,1)` | No | `SCHEDULER_DEFAULT_RADIUS_KM` | `> 0`, `≤ 100` |
| `preferred_workshop_id` | `uuid` | Yes | `NULL` | FK `workshop.id` `ON DELETE SET NULL`; ràng buộc mềm |
| `preferred_workshop_source` | `varchar(12)` | Yes | `NULL` | `USER`, `INFERRED` |
| `min_rating` | `smallint` | Yes | `NULL` | 1–5; ràng buộc mềm (PS-02) |
| `needs_review` | `boolean` | No | `false` | `true` khi xưởng yêu thích `inactive` (EDGE-BK01-02) |
| `version` | `integer` | No | `1` | Khoá lạc quan |
| `created_at` / `updated_at` | `timestamptz` | No | `now()` | |

```sql
ALTER TABLE owner_scheduling_profile ADD CONSTRAINT ck_osp_automation
  CHECK (automation_level IN ('SUGGEST', 'HOLD', 'AUTO_BOOK'));
ALTER TABLE owner_scheduling_profile ADD CONSTRAINT ck_osp_anchor
  CHECK (anchor_type IS NULL OR anchor_type IN ('HOME', 'WORK', 'DEVICE', 'PROVINCE'));
ALTER TABLE owner_scheduling_profile ADD CONSTRAINT ck_osp_radius CHECK (radius_km > 0 AND radius_km <= 100);
ALTER TABLE owner_scheduling_profile ADD CONSTRAINT ck_osp_rating CHECK (min_rating IS NULL OR min_rating BETWEEN 1 AND 5);
```

- `DEVICE`: không lưu toạ độ thiết bị ở hồ sơ; toạ độ đi theo từng yêu cầu (PL-01 `CONSENT_LOCATION`).
- `AUTO_BOOK` chỉ ghi được khi `CONSENT_AUTO_BOOKING` hiệu lực (BR-BK01-05); thu hồi đồng ý thì PL-01 hạ về `HOLD`.

---

# 3. `owner_scheduling_constraint` (ENT-BK01-02)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `kind` | `varchar(24)` | No | — | `AVAILABILITY` (cứng), `PREFERRED_TIME` (mềm), `EXCLUDED_WORKSHOP` (cứng, BR-BK01-13) |
| `weekday` | `smallint` | Yes | `NULL` | ISO 1 (Thứ Hai) … 7 (Chủ nhật); `NULL` = mọi ngày |
| `start_time` / `end_time` | `time` | Yes | `NULL` | Giờ địa phương Asia/Ho_Chi_Minh; `start < end` |
| `workshop_id` | `uuid` | Yes | `NULL` | FK `workshop.id` `ON DELETE CASCADE`; chỉ khi `EXCLUDED_WORKSHOP` |
| `exclusion_source` | `varchar(16)` | Yes | `NULL` | `LOW_RATING` (PS-02), `NOT_SUITABLE` (PS-03), `USER` |
| `source` | `varchar(12)` | No | — | `USER` (khai ở màn / chat), `INFERRED` (PS-01) |
| `status` | `varchar(12)` | No | `'active'` | `active`, `pending_review` (suy ra, chưa xác nhận), `rejected` |
| `memory_item_id` | `uuid` | Yes | `NULL` | FK `agent_user_memory.id` `ON DELETE CASCADE` (PS-01) khi `INFERRED` |
| `created_at` / `updated_at` | `timestamptz` | No | `now()` | |

```sql
CREATE INDEX ix_osc_user_kind ON owner_scheduling_constraint (user_id, kind) WHERE status = 'active';
CREATE UNIQUE INDEX ux_osc_excluded ON owner_scheduling_constraint (user_id, workshop_id)
  WHERE kind = 'EXCLUDED_WORKSHOP' AND status = 'active';
ALTER TABLE owner_scheduling_constraint ADD CONSTRAINT ck_osc_time
  CHECK ((start_time IS NULL AND end_time IS NULL) OR start_time < end_time);
ALTER TABLE owner_scheduling_constraint ADD CONSTRAINT ck_osc_workshop
  CHECK ((kind = 'EXCLUDED_WORKSHOP') = (workshop_id IS NOT NULL));
ALTER TABLE owner_scheduling_constraint ADD CONSTRAINT ck_osc_inferred
  CHECK (source <> 'INFERRED' OR memory_item_id IS NOT NULL);
```

**Khung rảnh theo buổi** (SCR-BK01-01): sáng `08:00–12:00`, chiều `12:00–17:00`, tối `17:00–20:00` (config `SCHEDULER_DAY_PARTS`); UI lưu thành `start_time` / `end_time`.

---

# 4. `scheduling_run` (ENT-BK01-03)

Chỉ thêm. Ràng buộc lưu dạng ẩn danh (không địa chỉ, không toạ độ; chỉ bán kính, số khung, có/không xưởng yêu thích) theo NFR-09.

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `user_vehicle_id` | `uuid` | No | — | FK `user_vehicle.id` `ON DELETE CASCADE` |
| `trigger` | `varchar(24)` | No | — | `OWNER_REQUEST`, `CHAT`, `CHIP`, `WIDGET` (BK-04), `MAP` (BK-05), `DUE_JOB`, `SERIES` (BK-06), `WORKSHOP_UNABLE`, `WS_CONFIRM_TIMEOUT` (WS-02), `RESCHEDULE`, `WAITLIST` (BK-07) |
| `entry_channel` | `varchar(16)` | Yes | `NULL` | `APP`, `CHAT`, `NOTIFICATION` — để đo M-01 |
| `constraints_digest` | `jsonb` | No | — | Ẩn danh §4.1 |
| `relaxations_applied` | `jsonb` | No | `'[]'` | Các cách nới chủ xe đã chọn |
| `outcome` | `varchar(16)` | No | — | `OPTIONS`, `NO_OPTION`, `CONFLICT`, `TIMEOUT_PARTIAL`, `ERROR` |
| `candidate_count` | `integer` | No | `0` | Số (xưởng, khung) sau lọc cứng |
| `rejected_by` | `jsonb` | No | `'{}'` | `{ "RADIUS": 12, "AVAILABILITY": 40, "DEADLINE": 3, "FULL": 18, "EXCLUDED": 1, "PROACTIVE_CAP": 2 }` |
| `duration_ms` | `integer` | No | — | |
| `scorer_version` | `varchar(16)` | No | `'rule-v1'` | BK-10 thay bộ chấm thì đổi giá trị |
| `held_option_id` | `uuid` | Yes | `NULL` | Phương án được giữ ở mức 2/3 |
| `created_at` | `timestamptz` | No | `now()` | |

```sql
CREATE INDEX ix_scheduling_run_user ON scheduling_run (user_id, created_at DESC);
CREATE INDEX ix_scheduling_run_trigger ON scheduling_run (trigger, created_at);
```

## 4.1 `constraints_digest`

```json
{ "windows": 3, "radiusKm": 5, "hasPreferredWorkshop": true, "deadline": "2026-10-20",
  "anchorType": "HOME", "requestOverrides": ["windows"], "automationLevel": "HOLD", "usedInferred": false, "usedCalendarBusy": true }
```

---

# 5. `scheduling_option` (ENT-BK01-04)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK, là `optionId` ở API |
| `run_id` | `uuid` | No | — | FK `scheduling_run.id` `ON DELETE CASCADE` |
| `rank` | `smallint` | No | — | 1..`SCHEDULER_MAX_OPTIONS` |
| `workshop_id` | `uuid` | No | — | FK `workshop.id` |
| `booking_date` | `date` | No | — | |
| `time_slot` | `time` | No | — | |
| `search_tier` | `smallint` | No | — | 1–3 theo BR-BK01-02 |
| `score` | `numeric(6,2)` | No | — | 0–100 |
| `score_breakdown` | `jsonb` | No | — | `{ "PREFERRED": 40, "DISTANCE": 18.2, "USUAL_TIME": 15, "RATING": 6, "RELIABILITY": 4 }` |
| `reasons` | `jsonb` | No | — | 1–3 `{ "code": "PREFERRED_WORKSHOP", "text": "Đúng xưởng bạn thích" }` |
| `distance_km` | `numeric(6,2)` | Yes | `NULL` | |
| `travel_minutes` | `smallint` | Yes | `NULL` | Khi có BK-05 |
| `remaining_capacity` | `smallint` | Yes | `NULL` | Chỗ còn lúc chạy |
| `status` | `varchar(12)` | No | `'offered'` | `offered`, `held`, `selected`, `released`, `stale`, `rejected` (PS-03) |
| `booking_id` | `uuid` | Yes | `NULL` | FK `booking.id` `ON DELETE SET NULL` |
| `expires_at` | `timestamptz` | No | — | `created_at + SCHEDULER_OPTION_TTL_MIN` (5 phút, EDGE-BK01-07); khi `held` thì bằng `booking.hold_expires_at` |
| `created_at` | `timestamptz` | No | `now()` | |

```sql
CREATE UNIQUE INDEX ux_scheduling_option_rank ON scheduling_option (run_id, rank);
CREATE UNIQUE INDEX ux_scheduling_option_booking ON scheduling_option (booking_id) WHERE booking_id IS NOT NULL;
ALTER TABLE scheduling_option ADD CONSTRAINT ck_so_status
  CHECK (status IN ('offered', 'held', 'selected', 'released', 'stale', 'rejected'));  -- rejected: PS-03
ALTER TABLE scheduling_option ADD CONSTRAINT ck_so_reasons CHECK (jsonb_array_length(reasons) BETWEEN 1 AND 3);
```

Mã lý do (`reasons[].code`) cố định: `PREFERRED_WORKSHOP`, `PREFERRED_WORKSHOP_OTHER_TIME`, `NEAREST`, `IN_FREE_WINDOW`, `USUAL_TIME`, `HIGH_RATING`, `RELIABLE_WORKSHOP`, `PREVIOUSLY_SATISFIED` (PS-02), `EARLIEST`, `BEFORE_DEADLINE`, `PARTS_IN_STOCK` (BK-09). Chỉ lý do có yếu tố chấm điểm > 0 mới được gắn (BR-BK01-03).

---

# 6. `booking` — cột mới (ENT-402)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `proactive` | `boolean` | No | `false` | Lịch hệ thống tự giữ, chờ chủ xe xác nhận (BR-BK01-06) |
| `auto_booked` | `boolean` | No | `false` | Mức 3 đã xác nhận thay chủ xe |
| `proactive_confirmed_at` | `timestamptz` | Yes | `NULL` | Lúc chủ xe xác nhận lịch giữ chủ động (hoặc hệ thống xác nhận ở mức 3). Hạn chót duyệt của xưởng (us-029 BR-015) tính từ mốc này thay cho `created_at` |
| `free_cancel_until` | `timestamptz` | Yes | `NULL` | `auto_booked` ⇒ `proactive_confirmed_at + AUTO_BOOK_FREE_CANCEL_HOURS`; BK-02 đọc |
| `scheduling_option_id` | `uuid` | Yes | `NULL` | FK `scheduling_option.id` `ON DELETE SET NULL` |
| `replaced_booking_id` | `uuid` | Yes | `NULL` | FK `booking.id` `ON DELETE SET NULL`; lịch cũ bị thay khi đổi xưởng / xưởng báo bận |

```sql
ALTER TABLE booking ADD CONSTRAINT ck_booking_proactive_pending
  CHECK (NOT proactive OR status IN ('pending', 'cancelled'));
ALTER TABLE booking ADD CONSTRAINT ck_booking_proactive_hold
  CHECK (NOT proactive OR status <> 'pending' OR hold_expires_at IS NOT NULL);
-- BR-BK01-14: đếm nhanh chỗ đang giữ chủ động theo xưởng / ngày.
CREATE INDEX ix_booking_proactive_open ON booking (workshop_id, booking_date)
  WHERE proactive AND status = 'pending';
```

- `proactive` được đặt về `false` ngay khi chủ xe xác nhận (lịch đi vào luồng xác nhận MVP). Lịch `cancelled` vì hết hạn giữ vẫn giữ `proactive = true` để báo cáo.
- `hold_expires_at` (có sẵn) mang hạn giữ chủ động = `now + PROACTIVE_HOLD_HOURS`.

## 6.1 `booking_status_event.reason_code` — giá trị mới

| Mã | Khi | Actor |
|---|---|---|
| `PROACTIVE_HOLD_EXPIRED` | Hết hạn giữ chủ động (EF-BK01-02) | `system` |
| `PROACTIVE_HOLD_DISMISSED` | Chủ xe bấm "Bỏ qua lần này" | `vehicle_owner` |
| `RESCHEDULED_TO_OTHER_WORKSHOP` | Lịch cũ khi đổi xưởng (AF-BK01-06) | `vehicle_owner` |
| `WORKSHOP_UNABLE_STAFF` / `WORKSHOP_UNABLE_PARTS` / `WORKSHOP_UNABLE_INCIDENT` / `WORKSHOP_UNABLE_CLOSED` | Xưởng báo không phục vụ được (AF-BK01-08) | `workshop_owner` |

BK-02 không tính điểm chủ xe cho mọi mã ở bảng này.

---

# 7. Business Rules (bổ sung)

## BR-ENT-BK01-01 — Phương án bất biến

Dòng `scheduling_option` không đổi `workshop_id`, `booking_date`, `time_slot`, `score`, `reasons` sau khi chèn. Chạy lại luôn tạo `scheduling_run` mới.

## BR-ENT-BK01-02 — Một phương án đang giữ mỗi xe

Ở mức 2/3, mỗi `user_vehicle` có tối đa một booking `proactive = true AND status = 'pending'`; đảm bảo bằng us-029 BR-013 (một lịch mở mỗi xe) — không cần index riêng.

## BR-ENT-BK01-03 — Ràng buộc suy ra phụ thuộc đồng ý

Bộ lập lịch chỉ đọc dòng `source = INFERRED` khi `CONSENT_LONG_TERM_MEMORY` hiệu lực và `status = 'active'`. Dòng `pending_review` không bao giờ được dùng. Xoá mục nhớ PS-01 xoá luôn ràng buộc suy ra (cascade).

## BR-ENT-BK01-04 — Hồ sơ chưa có

Không có dòng `owner_scheduling_profile` ⇒ bộ lập lịch dùng mặc định (`HOLD`, `SCHEDULER_DEFAULT_RADIUS_KM`, không khung rảnh) và agent hỏi theo AF-BK01-03. Dòng được tạo ở lần lưu đầu tiên.

---

# 8. Migration

- Một revision: 4 bảng mới, 6 cột `booking` (mặc định `false` / `NULL`, không backfill), index + CHECK.
- `booking_status_event.reason_code` là `varchar` có sẵn; thêm giá trị vào enum Python `CancelReasonCode`, không đổi DB.
- `downgrade`: drop cột booking rồi drop bảng theo thứ tự `scheduling_option` → `scheduling_run` → `owner_scheduling_constraint` → `owner_scheduling_profile`.

---

# 9. Retention

| Bảng | Giữ | Ghi chú |
|---|---|---|
| `scheduling_run` / `scheduling_option` | 180 ngày | Job dọn hằng ngày; BK-10 cần ≥ `OPT_MIN_DATA_WEEKS` tuần dữ liệu nên không dọn sớm hơn |
| `owner_scheduling_*` | Đến khi chủ xe xoá / xoá tài khoản | Ràng buộc suy ra xoá theo PL-01 `CONSENT_LONG_TERM_MEMORY` |

---

# 10. Open Questions

| ID | Câu hỏi | Đề xuất |
|---|---|---|
| `Q-ENT-BK01-01` | Lưu toạ độ Nhà / Chỗ làm ở `user_location` hay bảng riêng? | `user_location` có sẵn, thêm `label` nếu chưa có |
| `Q-ENT-BK01-02` | TTL phương án | 5 phút (`SCHEDULER_OPTION_TTL_MIN`) theo EDGE-BK01-07 |

---

# 11. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
