# Entity Specification — `service_progress` (Tiến độ dịch vụ tại xưởng)

> **Domain:** Maintenance · **Tổng quan lược đồ:** [core.entity.md](../core.entity.md)
>
> **Nguồn sự thật:** `core.entity.md` v1.1 §14.2 bảng 6. Cấu trúc bảng **giữ nguyên**.

## 1. Entity Information

| Field | Value |
| --- | --- |
| Entity ID | `ENT-403` |
| Entity Name | `ServiceProgress` |
| Business Name | Tiến độ dịch vụ tại xưởng |
| Table | `service_progress` |
| Domain | Maintenance |
| Version | `v1.2` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-09-27` |
| Updated Date | `2026-10-07` |

---

# 2. Entity Overview

## 2.1 Description

Theo dõi trạng thái sửa chữa/bảo dưỡng xe theo thời gian thực khi xe đang ở xưởng. **Append-only**: mỗi lần cập nhật là một dòng mới.

## 2.2 Business Purpose

Cho chủ xe xem xe đang ở bước nào; lưu vết các mốc tại xưởng.

## 2.3 Scope

**In Scope:** mốc tiến độ, ghi chú, người cập nhật, thời điểm.

**Out of Scope:** trạng thái tổng của lịch hẹn — `booking.status`.

---

# 3. Business Meaning

Một dòng = "Tại thời điểm T, xe của booking B chuyển sang mốc S".

**Example:** booking `BK-20261003-0012`, `waiting_parts`, "Chờ má phanh trước, dự kiến 2 ngày".

---

# 4. Identity & Keys

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | PK |

---

# 5. Attributes

| Tên trường (Field) | Kiểu dữ liệu (Data Type) | Required | Nullable | Default | Ràng buộc (Constraints) | Mô tả (Description) |
| --- | --- | ---: | ---: | --- | --- | --- |
| `id` | `uuid` | Yes | No | `uuid4` | PK | ID bản ghi tiến độ |
| `booking_id` | `uuid` | Yes | No | - | FK → `booking.id` `ON DELETE CASCADE` | Lịch hẹn tương ứng |
| `stage` | `service_stage_enum` | Yes | No | - | `checked_in / inspecting / servicing / waiting_parts / quality_check / ready_for_pickup` | Mốc trạng thái |
| `note` | `text` | No | Yes | - | Bắt buộc 10–500 ký tự khi `stage = waiting_parts` | Ghi chú của chủ xưởng (VD: phát sinh thêm hạng mục, đang chờ phụ tùng gì) |
| `updated_by` | `integer` | No | Yes | - | **Deprecated** (us-057), luôn `NULL` | Giữ lại để không phá migration cũ; thay bằng `actor_type` + `actor_workshop_owner_id` |
| `actor_type` | `booking_actor_type_enum` | Yes | No | `system` | `workshop_owner` / `system` | Loại người ghi (dùng chung enum với `booking_status_event`) |
| `actor_workshop_owner_id` | `uuid` | No | Yes | - | FK → `workshop_owner.id` `ON DELETE SET NULL`; bắt buộc khi `actor_type = workshop_owner` | Chủ xưởng đã ghi mốc |
| `source` | `varchar(32)` | Yes | No | `BOARD` | `CHECK_IN` / `START` / `BOARD` | Nguồn phát sinh: tự ghi khi check-in hoặc bắt đầu làm, hoặc chủ xưởng ghi trên Workshop Board |
| `created_at` | `timestamptz` | Yes | No | `now()` | | Thời gian cập nhật trạng thái |

---

# 7. Relationships

```mermaid
erDiagram
    booking ||--o{ service_progress : "tracks"
```

| Related Entity | Relationship | Cardinality | Description |
| --- | --- | --- | --- |
| [`booking`](./booking.entity.md) | belongs to | N:1 | Lịch hẹn |

---

# 8. Entity Lifecycle / State

Bản ghi không đổi trạng thái (append-only). Thứ tự mốc tham khảo:

```mermaid
stateDiagram-v2
    [*] --> checked_in
    checked_in --> inspecting
    inspecting --> servicing
    servicing --> waiting_parts
    waiting_parts --> servicing
    servicing --> quality_check
    quality_check --> ready_for_pickup
    ready_for_pickup --> [*]
```

---

# 9. Business Rules & Constraints

## BR-ENT-405 — Append-only, gắn với booking đang ở xưởng

**Rule:** Chỉ thêm dòng khi `booking.status IN ('checked_in', 'in_progress')`; không sửa/xoá dòng đã ghi.

---

# 10. Data Integrity

* `CHECK (actor_type <> 'workshop_owner' OR actor_workshop_owner_id IS NOT NULL)` (`ck_service_progress_owner_actor`).
* `CHECK (stage <> 'waiting_parts' OR length(note) BETWEEN 10 AND 500)` (`ck_service_progress_waiting_parts_note`, BR-ENT-1302).
* Thứ tự mốc hợp lệ (us-057 BR-1302) được kiểm ở `ServiceProgressService` trong transaction có `SELECT booking … FOR UPDATE`, không dùng trigger. Sai thứ tự ⇒ `INVALID_STAGE_TRANSITION`.

---

# 11. Index & Query Requirements

| Query | Fields | Frequency | Required Index |
| --- | --- | --- | --- |
| Tiến độ của một booking | `booking_id`, `created_at` | Cao | `ix_service_progress_booking_created` |

---

# 12. Ownership & Authorization

| Actor / Role | Read | Create | Update | Delete |
| --- | ---: | ---: | ---: | ---: |
| Chủ xe | ✅ (booking của mình) | ❌ | ❌ | ❌ |
| Chủ xưởng | ✅ (xưởng mình) | ✅ | ❌ | ❌ |

---

# 21. Open Questions

| ID | Question | Owner | Status |
| --- | --- | --- | --- |
| Q-403 | `updated_by` là `integer` (core v1.1) trong khi tài khoản xưởng `workshop_owner.id` là `uuid` (ENT-007). Có đổi kiểu và thêm FK không? | Backend Team | **Resolved, mở lại ở us-057** — Không đổi kiểu; `updated_by` deprecated, người ghi lưu ở `actor_type` + `actor_workshop_owner_id`. Bỏ hẳn cột ở phase sau (Q-ENT-1301) |

---

# 22. Change Log

| Version | Date | Author | Changes |
| --- | --- | --- | --- |
| `v1.1` | `2026-09-27` | Team 4 Người | Tách từ `core.entity.md` v1.1 §14.2 bảng 6, cấu trúc giữ nguyên |
| `v1.2` | `2026-10-07` | Team 4 Người | Gộp phần mở rộng của us-057 entity spec và đồng bộ với code (báo cáo 03/10, C-07): thêm `actor_type`, `actor_workshop_owner_id`, `source`; `updated_by` deprecated; thêm §10 với 2 CHECK constraint; cập nhật Q-403 |
