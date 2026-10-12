# Entity Specification — Tài khoản kỹ thuật viên và tự phân công

> Entity cho Feature `FEAT-P2-WS03`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ws-03-phase2-spec.ff.md). **API:** [API Spec](ws-03-phase2-spec.api.md).
>
> **Tên vai trò:** bảng mới dùng `technician` cho **KTV thật** (vai trò mới). `workshop_owner` (có sẵn) vẫn là chủ xưởng dù giao diện MVP gọi là "Kỹ thuật viên". Không đổi tên bảng hay cột cũ (P2Q-01 chỉ ảnh hưởng route / nhãn giao diện).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-WS03` — WS-03 |
| Version | `v0.2` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [ws-03-phase2-spec.ff.md](ws-03-phase2-spec.ff.md) |
| Related API | [ws-03-phase2-spec.api.md](ws-03-phase2-spec.api.md) |
| Related FE | [ws-03-phase2-spec.fe.md](ws-03-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-WS03-01` | `Technician` | `technician` | **Mới** |
| `ENT-WS03-02` | `TechnicianSkill` | `technician_skill` | **Mới** |
| `ENT-WS03-03` | `TechnicianWeeklySchedule` | `technician_weekly_schedule` | **Mới** (FF: `technician_schedule`, tách làm hai) |
| `ENT-WS03-04` | `TechnicianAbsence` | `technician_absence` | **Mới** |
| `ENT-WS03-05` | `BookingAssignment` | `booking_assignment` | **Mới** |
| `ENT-WS03-06` | `TechnicianAuditLog` | `technician_audit_log` | **Mới** |
| `ENT-008` | `Workshop` | `workshop` — **thêm cột** `technician_capacity_enabled` | Có sẵn |
| `ENT-426` / `ENT-403` | `booking_status_event`, `service_progress` | **thêm** `actor_technician_id`; enum `booking_actor_type_enum` + `technician` | Có sẵn |

---

# 2. `technician` (ENT-WS03-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `workshop_id` | `uuid` | No | — | FK `workshop.id` `ON DELETE CASCADE`; đúng một xưởng (BR-WS03-01) |
| `username` | `varchar(30)` | No | — | Tên đăng nhập, chữ thường `^[a-z0-9._]{3,30}$`, duy nhất toàn hệ thống (gợi ý tiền tố theo xưởng, ví dụ `xuongminhphat.an`) |
| `firebase_uid` | `varchar(128)` | No | — | Tài khoản Firebase email/mật khẩu tạo bằng Admin SDK lúc chủ xưởng tạo KTV; email nội bộ `{username}@ktv.evcare.internal` (không gửi thư, chỉ để Firebase đăng nhập) |
| `display_name` | `varchar(80)` | No | — | Tên gọi (chủ xe chỉ thấy tên này, BR-WS03-07) |
| `status` | `varchar(20)` | No | `'pending_activation'` | `pending_activation`, `active`, `disabled` (FF §13) |
| `must_change_password` | `boolean` | No | `true` | `true` khi tạo / đặt lại mật khẩu; `false` sau khi KTV đổi (BR-WS03-08) |
| `temp_password_expires_at` | `timestamptz` | Yes | — | `now + 7 ngày` khi tạo / đặt lại; quá hạn mà chưa đổi ⇒ không cấp phiên (EF-WS03-01) |
| `password_changed_at` | `timestamptz` | Yes | `NULL` | Lần KTV tự đổi gần nhất |
| `created_by_owner_id` | `uuid` | No | — | FK `workshop_owner.id` (quản trị viên tài khoản = xưởng, BR-WS03-01) |
| `permissions` | `jsonb` | No | `'["VIEW_ASSIGNED","UPDATE_PROGRESS","DRAFT_EXTRA","USE_ASSISTANT"]'` | §2.1 |
| `created_at` / `activated_at` / `disabled_at` | `timestamptz` | | | |
| `updated_at` | `timestamptz` | No | `now()` | |

```sql
CREATE UNIQUE INDEX ux_technician_username ON technician (username);
CREATE UNIQUE INDEX ux_technician_uid ON technician (firebase_uid);
CREATE INDEX ix_technician_workshop ON technician (workshop_id, status);
ALTER TABLE technician ADD CONSTRAINT ck_technician_status CHECK (status IN ('pending_activation','active','disabled'));
ALTER TABLE technician ADD CONSTRAINT ck_technician_pending CHECK (status <> 'pending_activation' OR must_change_password);
```

**Mật khẩu (BR-WS03-08):** backend **không lưu** mật khẩu hay mã băm — Firebase Auth giữ. Mật khẩu tạm chỉ trả về một lần trong response tạo / đặt lại. **Một tài khoản một vai trò (FF §21):** tài khoản Firebase của KTV có custom claim `role = technician`; luồng chủ xe (onboarding) và chủ xưởng từ chối token có claim này, nên tài khoản KTV không thể tự thành chủ xe / chủ xưởng.

## 2.1 `permissions`

| Quyền | Mặc định | Ý nghĩa |
|---|---|---|
| `VIEW_ASSIGNED` | ✅ (luôn) | Xem lịch được giao |
| `VIEW_ALL_BOOKINGS` | ❌ | Xem mọi lịch của xưởng (Q-WS03-02, chủ xưởng bật) |
| `UPDATE_PROGRESS` | ✅ | Cập nhật tiến độ 6 bước (us-057) cho lịch được giao |
| `CHECK_IN` | ❌ | Check-in, đánh dấu lỡ hẹn (BK-02) |
| `DRAFT_EXTRA` | ✅ | Tạo nháp báo giá phát sinh (AD-04) |
| `USE_ASSISTANT` | ✅ | Trợ lý TA-01 |

Không bao giờ cấp được (BR-WS03-03): duyệt báo giá, đổi luật nhận lịch (WS-01), xem doanh thu / bảng giá chỉnh sửa, quản lý KTV, thời lượng (WS-02).

---

# 3. `technician_skill` (ENT-WS03-02)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `technician_id` | `uuid` | No | PK (1/2), FK `technician.id` `ON DELETE CASCADE` |
| `skill` | `varchar(24)` | No | PK (2/2): `PERIODIC_MAINTENANCE` + các nhóm `service_item_category.category` của HS-01 (`BRAKE`, `TIRE`, `BATTERY`, `AC`, …) |

**Kỹ năng cần của lịch:** `PERIODIC_MAINTENANCE` nếu `service_kind = MAINTENANCE` (BK-03) + nhóm của từng hạng mục phát sinh / sửa chữa (`booking_line.item_code` → `service_item_category`). `QUICK_CHECK` cần `GENERAL_CHECK`. KTV đủ kỹ năng ⇔ tập kỹ năng ⊇ tập cần (AC-WS03-03).

---

# 4. `technician_weekly_schedule` (ENT-WS03-03) & `technician_absence` (ENT-WS03-04)

`technician_weekly_schedule`:

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `technician_id` | `uuid` | No | PK (1/2) |
| `weekday` | `smallint` | No | PK (2/2), 1–7 |
| `is_working` | `boolean` | No | Ca = giờ mở cửa của xưởng ngày đó (không ca phức tạp, FF §3.2) |

`technician_absence`:

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `technician_id` | `uuid` | No | FK `technician.id` `ON DELETE CASCADE` |
| `absence_date` | `date` | No | Cả ngày |
| `kind` | `varchar(8)` | No | `PLANNED`, `SUDDEN` |
| `note` | `varchar(200)` | Yes | Không lưu lý do sức khoẻ chi tiết |
| `created_by_owner_id` | `uuid` | No | |
| `created_at` | `timestamptz` | No | |

```sql
CREATE UNIQUE INDEX ux_technician_absence_day ON technician_absence (technician_id, absence_date);
```

**KTV làm ngày D** ⇔ `status = active` ∧ `weekly_schedule(weekday(D)).is_working` ∧ không có `absence` ngày D.

---

# 5. `booking_assignment` (ENT-WS03-05)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `booking_id` | `uuid` | No | — | FK `booking.id` `ON DELETE CASCADE` |
| `technician_id` | `uuid` | No | — | FK `technician.id` |
| `source` | `varchar(8)` | No | — | `AUTO`, `MANUAL` |
| `status` | `varchar(10)` | No | `'active'` | `active`, `released` (đổi KTV / KTV nghỉ / huỷ lịch) |
| `assigned_by_owner_id` | `uuid` | Yes | `NULL` | Khi `MANUAL` |
| `assigned_at` / `released_at` | `timestamptz` | | | |
| `release_reason` | `varchar(24)` | Yes | `NULL` | `REASSIGNED`, `ABSENCE`, `DISABLED`, `BOOKING_CANCELLED` |

```sql
CREATE UNIQUE INDEX ux_booking_assignment_active ON booking_assignment (booking_id) WHERE status = 'active';
CREATE INDEX ix_booking_assignment_tech ON booking_assignment (technician_id, status);
```

- Một lịch có tối đa một KTV đang giao (Phase 2 không chia việc một xe cho nhiều KTV).
- `MANUAL` không bị bộ phân công tự đổi lại (AF-WS03-02), trừ khi KTV đó nghỉ / bị vô hiệu.
- Không có dòng `active` ⇒ "Chưa phân công" (EF-WS03-02).

---

# 6. `technician_audit_log` (ENT-WS03-06)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `technician_id` | `uuid` | No | FK `technician.id` `ON DELETE CASCADE` |
| `workshop_id` | `uuid` | No | |
| `action` | `varchar(40)` | No | `PROGRESS_UPDATED`, `EXTRA_DRAFTED`, `CHECKED_IN`, `NO_SHOW_MARKED`, `ASSISTANT_USED`, `LOGIN`, `PASSWORD_CHANGED`, `MESSAGE_SENT` (MC-01)… Việc chủ xưởng làm với tài khoản (`ACCOUNT_CREATED`, `PASSWORD_RESET`, `DISABLED`, `ENABLED`) ghi cùng bảng với `meta.ownerId` |
| `object_type` / `object_id` | `varchar(24)` / `uuid` | Yes | Ví dụ `BOOKING` / id |
| `meta` | `jsonb` | No | Không chứa nội dung cá nhân của chủ xe |
| `created_at` | `timestamptz` | No | `now()` |

Chỉ thêm (BR-WS03-06). Index `(workshop_id, created_at DESC)`. Giữ 365 ngày.

---

# 7. Cột mới ở bảng có sẵn

| Bảng | Cột | Ghi chú |
|---|---|---|
| `workshop` | `technician_capacity_enabled boolean NOT NULL DEFAULT false` | BR-WS03-02. Chỉ có hiệu lực khi có ≥ 1 KTV `active` (EDGE-WS03-01) |
| `booking_status_event`, `service_progress` | `actor_technician_id uuid NULL` FK `technician.id` | Actor mới `technician` trong `booking_actor_type_enum`; CHECK: `actor_type = 'technician'` ⇔ `actor_technician_id IS NOT NULL` |

**Sức chứa khi bật (BR-WS03-02):** `capacity_base(workshop, D) = số KTV làm ngày D` thay cho `total_technicians` trong công thức MVP / WS-02 (`available_from(base, emergency_slots_reserved, blocked, occupied)`).

---

# 8. Migration

- Một revision: 6 bảng, cột `workshop`, cột actor + giá trị enum (`ALTER TYPE booking_actor_type_enum ADD VALUE 'technician'` — ngoài transaction theo yêu cầu Postgres).
- Không backfill.

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
| `v0.2` | `2026-10-12` | PO chốt: tài khoản tên đăng nhập + mật khẩu do xưởng tạo (bỏ email mời, token mời); cờ đổi mật khẩu lần đầu |
