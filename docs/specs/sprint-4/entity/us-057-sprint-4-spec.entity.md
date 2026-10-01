# Entity Specification — Tiến độ dịch vụ chi tiết 6 bước

> Entity cho Feature `FEAT-PROG-001` — PRD F8b (US-057 → US-059).
>
> **Nguyên tắc:** tái dùng `service_progress` (ENT-403). Sửa khoảng trống "người cập nhật" (`updated_by integer` không lưu được `workshop_owner.id` kiểu `uuid`) bằng các cột người ghi giống `booking_status_event` (ENT-426).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-PROG-001` — F8b |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-09-30` |
| Related FF | [us-057-sprint-4-spec.ff.md](../feature-functional/us-057-sprint-4-spec.ff.md) |
| Related API | [us-057-sprint-4-spec.api.md](../api/us-057-sprint-4-spec.api.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-403` | `ServiceProgress` | `service_progress` | Có sẵn — **mở rộng** | + `actor_type`, + `actor_workshop_owner_id`, + `source`; `updated_by` **deprecated** |
| `ENT-402` | `Booking` | `booking` | Có sẵn — không đổi | Điều kiện ghi theo `status` |

---

# 2. Vấn đề với `updated_by`

[service_progress.entity.md](../../entity/maintenance/service_progress.entity.md) khai `updated_by integer`, Q-403 chốt "giữ nguyên `integer`, không FK". Nhưng người cập nhật trong MVP là **chủ xưởng** (`workshop_owner.id` là `uuid` — ENT-007) hoặc **hệ thống** ⇒ không có giá trị `integer` hợp lệ để lưu, mất truy vết (FF BR-1304). Đề xuất mở lại Q-403 và dùng các cột dưới đây; giữ `updated_by` (luôn `NULL`) để không phá migration cũ, xoá ở phase sau.

---

# 3. Cột bổ sung trên `service_progress`

| Field | Type | Required | Nullable | Default | Constraints | Description |
|---|---|---:|---:|---|---|---|
| `actor_type` | `booking_actor_type_enum` | Yes | No | `'system'` | `workshop_owner` / `system` | Loại người ghi (dùng lại enum ENT-426) |
| `actor_workshop_owner_id` | `uuid` | No | Yes | - | FK → `workshop_owner.id` `ON DELETE SET NULL`; bắt buộc khi `actor_type = workshop_owner` | Chủ xưởng ghi |
| `source` | `varchar(32)` | Yes | No | `'BOARD'` | `CHECK_IN` / `START` / `BOARD` | Nguồn phát sinh |

`CHECK (actor_type <> 'workshop_owner' OR actor_workshop_owner_id IS NOT NULL)`.

---

# 4. Business Rules (bổ sung)

## BR-ENT-1301 — Thứ tự mốc kiểm ở service

Bảng chuyển tiếp FF BR-1302 kiểm ở `ServiceProgressService` (không dùng trigger) trong transaction có `SELECT booking … FOR UPDATE` để tuần tự hoá các lần ghi của cùng booking.

## BR-ENT-1302 — Ghi chú chờ phụ tùng

`CHECK (stage <> 'waiting_parts' OR char_length(note) BETWEEN 10 AND 500)`.

## BR-ENT-405 (nhắc lại)

Chỉ thêm dòng khi `booking.status IN ('checked_in','in_progress')`; append-only.

---

# 5. Migration

1. `ALTER TABLE service_progress ADD COLUMN actor_type booking_actor_type_enum NOT NULL DEFAULT 'system', ADD COLUMN actor_workshop_owner_id uuid NULL REFERENCES workshop_owner(id) ON DELETE SET NULL, ADD COLUMN source varchar(32) NOT NULL DEFAULT 'BOARD';`
2. Thêm 2 CHECK ở §3, §4.
3. Enum `booking_actor_type_enum` phải được tạo trước (migration của us-037 ENT-426) — sắp thứ tự revision.
4. Cập nhật [service_progress.entity.md](../../entity/maintenance/service_progress.entity.md) (v1.2) và đóng lại Q-403 theo quyết định mới.

---

# 6. Open Questions

| ID | Question | Status |
|---|---|---|
| `Q-ENT-1301` | Mở lại Q-403: bỏ hẳn `updated_by` ở phase sau? | Open — `[Đề xuất]` có |
| `Q-ENT-1302` | Kết quả gửi thông báo tiến độ lưu ở bảng delivery chung hay chỉ log? | Open — `[Đề xuất]` chỉ log trong MVP (Could) |

---

# 7. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu |
