# Entity Specification — Chính sách huỷ lịch và lỡ hẹn

> Entity cho Feature `FEAT-P2-BK02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-02-phase2-spec.ff.md). **API:** [API Spec](bk-02-phase2-spec.api.md).
>
> **Nguyên tắc:** sự kiện tin cậy là sổ cái chỉ thêm (không xoá cứng, chỉ đổi trạng thái — FF §18 Audit). Điểm và bậc là giá trị suy ra từ sổ cái, được lưu đệm trong một bảng trạng thái để đọc nhanh. `booking_status_event.reason_code` (có sẵn) vẫn là lịch sử chuyển trạng thái; `booking.cancel_reason` là **phân loại** của BK-02.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-BK02` — BK-02 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [bk-02-phase2-spec.ff.md](bk-02-phase2-spec.ff.md) |
| Related API | [bk-02-phase2-spec.api.md](bk-02-phase2-spec.api.md) |
| Related FE | [bk-02-phase2-spec.fe.md](bk-02-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-BK02-01` | `OwnerReliabilityEvent` | `owner_reliability_event` | **Mới** | Sổ cái sự kiện của chủ xe |
| `ENT-BK02-02` | `ReliabilityAppeal` | `reliability_appeal` | **Mới** | Khiếu nại một sự kiện |
| `ENT-BK02-03` | `OwnerReliabilityState` | `owner_reliability_state` | **Mới** | Điểm + bậc hiện tại (đệm) |
| `ENT-BK02-04` | `WorkshopReliabilityEvent` | `workshop_reliability_event` | **Mới** | Sự kiện tin cậy của xưởng |
| `ENT-402` | `Booking` | `booking` | Có sẵn — **thêm cột** | `cancel_reason`, `no_show_prompted_at`, `grace_extended_until`, `no_show_marked_at` |

---

# 2. `booking` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `cancel_reason` | `varchar(40)` | Yes | `NULL` | Chỉ khi `cancelled`. Giá trị §2.1 |
| `no_show_prompted_at` | `timestamptz` | Yes | `NULL` | Lúc gửi "Bạn có đang tới không?" |
| `grace_extended_until` | `timestamptz` | Yes | `NULL` | AF-BK02-02 (một lần) hoặc BK-08 báo trễ; mốc ân hạn mới |
| `no_show_marked_at` | `timestamptz` | Yes | `NULL` | Lúc đánh dấu lỡ hẹn; dùng cho hoàn tác 24 giờ (EDGE-BK02-06) |

## 2.1 `cancel_reason`

| Giá trị | Ai | Tính điểm chủ xe |
|---|---|---|
| `early_cancel` | Chủ xe huỷ, còn ≥ `LATE_CANCEL_HOURS` | Không |
| `late_cancel` | Chủ xe huỷ, còn < `LATE_CANCEL_HOURS` (kể cả đúng / sau giờ hẹn, EDGE-BK02-04) | **+`LATE_CANCEL_WEIGHT`** |
| `no_show` | Xưởng đánh dấu / hệ thống tự đánh dấu | **+1** |
| `hold_released` | Chủ xe huỷ `pending` trong thời gian giữ chỗ (us-029 BR-010, EDGE-BK02-01) | Không |
| `auto_book_free_cancel` | Chủ xe huỷ lịch tự đặt trước `free_cancel_until` (BK-01) | Không |
| `attendance_unconfirmed` | Bậc Cần xác nhận, chưa "Xác nhận sẽ đến" 12 giờ trước giờ hẹn | Không (BR-BK02-03) |
| `workshop_cancel` | Xưởng huỷ / từ chối / báo không phục vụ được | Không (tính cho xưởng nếu sát giờ) |
| `ws_confirm_timeout` | Xưởng chậm duyệt (WS-02) | Không |
| `proactive_hold_expired` | Hết hạn giữ chủ động (BK-01) | Không |
| `rescheduled_to_other_workshop` | Đổi xưởng (BK-01) | Không |

```sql
ALTER TABLE booking ADD CONSTRAINT ck_booking_cancel_reason
  CHECK ((status = 'cancelled') = (cancel_reason IS NOT NULL));
```

Lịch đã `cancelled` trước khi có BK-02: backfill `cancel_reason` từ `booking_status_event.reason_code` cuối cùng theo bảng ánh xạ trong migration; không tạo sự kiện tin cậy cho dữ liệu cũ.

---

# 3. `owner_reliability_event` (ENT-BK02-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `booking_id` | `uuid` | No | — | FK `booking.id` `ON DELETE CASCADE` |
| `workshop_id` | `uuid` | No | — | FK `workshop.id`; để chủ xưởng lọc sự kiện của xưởng mình |
| `kind` | `varchar(16)` | No | — | `LATE_CANCEL`, `NO_SHOW`, `WAIVER` |
| `points` | `numeric(3,1)` | No | — | `LATE_CANCEL_WEIGHT` / `1.0` / số âm bằng điểm sự kiện gốc |
| `status` | `varchar(10)` | No | `'counted'` | `counted`, `appealed`, `waived`, `expired` (WAIVER luôn `counted` tới khi `expired`) |
| `waives_event_id` | `uuid` | Yes | `NULL` | FK tự tham chiếu; bắt buộc khi `WAIVER` |
| `reason` | `varchar(300)` | No | — | Câu đọc được (BR-BK02-07), ví dụ "Huỷ lúc 07:00, còn 2 giờ 30 phút tới giờ hẹn 09:30" |
| `actor_type` | `booking_actor_type_enum` | No | — | `vehicle_owner`, `workshop_owner`, `system` |
| `actor_workshop_owner_id` | `uuid` | Yes | `NULL` | Khi xưởng đánh dấu / miễn |
| `occurred_at` | `timestamptz` | No | — | Giờ máy chủ (EF-BK02-03) |
| `expires_at` | `timestamptz` | No | — | `occurred_at + RELIABILITY_WINDOW_DAYS` |
| `created_at` | `timestamptz` | No | `now()` | |

```sql
-- BR-BK02-10: mỗi lịch tối đa một sự kiện tính điểm.
CREATE UNIQUE INDEX ux_ore_booking_scoring ON owner_reliability_event (booking_id)
  WHERE kind IN ('LATE_CANCEL', 'NO_SHOW');
CREATE UNIQUE INDEX ux_ore_waiver ON owner_reliability_event (waives_event_id) WHERE kind = 'WAIVER';
CREATE INDEX ix_ore_user_window ON owner_reliability_event (user_id, expires_at) WHERE status IN ('counted', 'appealed');
CREATE INDEX ix_ore_workshop ON owner_reliability_event (workshop_id, occurred_at DESC);
ALTER TABLE owner_reliability_event ADD CONSTRAINT ck_ore_kind_points CHECK (
  (kind = 'NO_SHOW' AND points = 1.0) OR (kind = 'LATE_CANCEL' AND points > 0) OR (kind = 'WAIVER' AND points < 0));
ALTER TABLE owner_reliability_event ADD CONSTRAINT ck_ore_waiver_ref
  CHECK ((kind = 'WAIVER') = (waives_event_id IS NOT NULL));
```

**Không xoá, không sửa `points`.** Miễn = đổi sự kiện gốc sang `waived` **và** chèn một `WAIVER` âm (sổ cái cân bằng, BR-BK02-02). Điểm tính bằng tổng `points` của các dòng `status IN ('counted','appealed','waived')` có `expires_at > now` — dòng gốc `waived` + `WAIVER` âm triệt tiêu nhau. Sự kiện đang `appealed` **vẫn tính** cho tới khi có quyết định.

---

# 4. `reliability_appeal` (ENT-BK02-02)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `event_id` | `uuid` | No | — | FK `owner_reliability_event.id` `ON DELETE CASCADE`, **unique** (một khiếu nại mỗi sự kiện) |
| `kind` | `varchar(16)` | No | — | `NO_SHOW_DISPUTE` (BR-BK02-09) hoặc `FORCE_MAJEURE` (huỷ muộn do bất khả kháng, BR-BK02-04) |
| `owner_note` | `varchar(500)` | No | — | |
| `status` | `varchar(16)` | No | `'pending'` | `pending`, `accepted`, `rejected`, `auto_accepted` |
| `workshop_note` | `varchar(300)` | Yes | `NULL` | Bắt buộc khi `rejected` |
| `decided_by_owner_id` | `uuid` | Yes | `NULL` | FK `workshop_owner.id` |
| `submitted_at` | `timestamptz` | No | `now()` | |
| `decide_by` | `timestamptz` | No | — | `submitted_at + 72h` (BR-BK02-09) |
| `decided_at` | `timestamptz` | Yes | `NULL` | |

```sql
CREATE INDEX ix_appeal_pending ON reliability_appeal (status, decide_by) WHERE status = 'pending';
```

---

# 5. `owner_reliability_state` (ENT-BK02-03)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `user_id` | `bigint` | No | — | PK, FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `score` | `numeric(4,1)` | No | `0` | |
| `tier` | `varchar(16)` | No | `'NORMAL'` | `NORMAL` (< 1), `SOFT_REMINDER` (1 – < 2), `MUST_CONFIRM` (2 – < 3), `RESTRICTED` (≥ 3) — BR-BK02-03 |
| `tier_changed_at` | `timestamptz` | Yes | `NULL` | |
| `next_expiry_at` | `timestamptz` | Yes | `NULL` | `min(expires_at)` của sự kiện còn tính; "ngày điểm sớm nhất rơi khỏi cửa sổ" (SCR-BK02-02) |
| `recomputed_at` | `timestamptz` | No | `now()` | |

Ghi lại trong **cùng transaction** với mọi sự kiện mới / đổi trạng thái; job hằng ngày tính lại toàn bộ để xử lý hết hạn (AC-BK02-04). Ngưỡng bậc là config `RELIABILITY_TIERS`.

---

# 6. `workshop_reliability_event` (ENT-BK02-04)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `workshop_id` | `uuid` | No | — | FK `workshop.id` `ON DELETE CASCADE` |
| `booking_id` | `uuid` | No | — | FK `booking.id` `ON DELETE CASCADE`; unique theo (`booking_id`, `kind`) |
| `kind` | `varchar(24)` | No | — | `LATE_WORKSHOP_CANCEL` (huỷ / báo bận lịch `confirmed` trong `LATE_CANCEL_HOURS`), `WORKSHOP_LATE` (trễ quá `WS_LATE_MIN`, BK-08), `CONFIRM_TIMEOUT` (WS-02) |
| `points` | `numeric(3,1)` | No | `1.0` | |
| `occurred_at` | `timestamptz` | No | — | |
| `expires_at` | `timestamptz` | No | — | `occurred_at + RELIABILITY_WINDOW_DAYS` |

```sql
CREATE UNIQUE INDEX ux_wre_booking_kind ON workshop_reliability_event (booking_id, kind);
CREATE INDEX ix_wre_workshop_window ON workshop_reliability_event (workshop_id, expires_at);
```

**Chỉ số cho BK-01:** `workshop_unreliability = min(1, Σ points trong cửa sổ / max(10, số lịch confirmed của xưởng trong cửa sổ))`. Tính trong `ReliabilityService.workshop_factor(workshop_id)`, đệm Redis 1 giờ.

---

# 7. Business Rules (bổ sung)

## BR-ENT-BK02-01 — Phân loại lúc huỷ, theo giờ máy chủ

`remaining = starts_at − now()` (giờ máy chủ, EF-BK02-03). `remaining ≥ LATE_CANCEL_HOURS` ⇒ `early_cancel` (đúng mốc là huỷ sớm, BR-BK02-01); ngược lại `late_cancel`. Ghi `cancel_reason` và sự kiện (nếu có) cùng transaction với chuyển trạng thái.

## BR-ENT-BK02-02 — Miễn trước phân loại

Thứ tự kiểm tra: miễn (bảng §2.1 cột "Không") ⇒ phân loại. Đổi giờ (`booking_reschedule`) không phải huỷ, không tạo sự kiện (EDGE-BK02-02).

## BR-ENT-BK02-03 — Hoàn tác lỡ hẹn

Trong 24 giờ sau `no_show_marked_at`, chủ xưởng hoàn tác ⇒ sự kiện `NO_SHOW` sang `waived` + chèn `WAIVER` (actor `workshop_owner`, lý do "Xưởng hoàn tác"). Xe đến muộn sau khi tự đánh dấu (EF-BK02-02) ⇒ cùng cách, kèm khôi phục lịch (API §7.2).

---

# 8. Migration

- Một revision: 4 bảng, 4 cột `booking`, index, CHECK.
- Backfill `cancel_reason` cho lịch `cancelled` cũ theo `reason_code`: `WS_CONFIRM_TIMEOUT` → `ws_confirm_timeout`; mã phía xưởng → `workshop_cancel`; mã phía chủ xe → `early_cancel` (không truy ngược huỷ muộn cho dữ liệu cũ); không có ⇒ `early_cancel`.
- Không tạo `owner_reliability_event` cho quá khứ (mọi chủ xe bắt đầu điểm 0).

---

# 9. Retention

| Bảng | Giữ |
|---|---|
| `owner_reliability_event`, `reliability_appeal` | 2 × `RELIABILITY_WINDOW_DAYS` sau `expires_at`, rồi job xoá (không còn ảnh hưởng điểm). Xoá tài khoản ⇒ cascade |
| `owner_reliability_state` | Theo tài khoản |
| `workshop_reliability_event` | 365 ngày |

---

# 10. Open Questions

| ID | Câu hỏi | Đề xuất |
|---|---|---|
| `Q-ENT-BK02-01` | Ngưỡng cố định hay theo xưởng (P2Q-04)? | Cố định toàn hệ thống ở P2-A (config) |
| `Q-ENT-BK02-02` | Trọng số sự kiện xưởng có khác nhau theo `kind`? | Cùng 1,0 ở P2-A |

---

# 11. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
