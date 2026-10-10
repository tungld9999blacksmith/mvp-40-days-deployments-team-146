# Entity Specification — `quote` (Báo giá bảo dưỡng — HITL)

> **Đưa lại vào phạm vi (07/10/2026, PRD v3.8).** Báo giá có chủ xưởng duyệt (F5b, us-049, AI-005) là chức năng MVP trở lại: bảng `quote`, `quote_item` được tạo lại bởi migration `backend/alembic/versions/b4e6f8a1c3d5_restore_quote_hitl.py`; code backend/frontend đã khôi phục. Tài liệu này là đặc tả để triển khai.

> **Domain:** Maintenance · **Tổng quan lược đồ:** [core.entity.md](../core.entity.md)
>
> **Nguồn:** entity `quotes` (ENT-010) trong bản ERD sinh tự động ([archive/core.entity.generated.md](../archive/core.entity.generated.md)), đã **chỉnh theo quy ước core v1.1** và các entity đã có. Các điểm thay đổi so với bản sinh tự động: xem §21. Đánh dấu `[Đề xuất]` là phần bổ sung chưa có trong nguồn nào, cần review.

## 1. Entity Information

| Field | Value |
| --- | --- |
| Entity ID | `ENT-410` |
| Entity Name | `Quote` |
| Business Name | Báo giá |
| Table | `quote` |
| Domain | Maintenance |
| Version | `v1.2` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-09-27` |
| Updated Date | `2026-10-07` |

---

# 2. Entity Overview

## 2.1 Description

Báo giá bảo dưỡng cho một xe tại một xưởng. AI Agent lập bản nháp từ `maintenance_rule` và `service_price`; chủ xưởng duyệt hoặc từ chối (Human-in-the-loop — HITL).

## 2.2 Business Purpose

Đảm bảo chi phí báo cho chủ xe đã được con người xác nhận trước khi đặt lịch.

## 2.3 Scope

**In Scope**

* Xe, xưởng, mốc bảo dưỡng liên quan, trạng thái HITL, tổng ước tính, tổng được duyệt, người duyệt, ghi chú.

**Out of Scope**

* Từng dòng hạng mục — `quote_item`.
* Thanh toán.

---

# 3. Business Meaning

## Definition

Một `quote` = một đề xuất chi phí cho một lần bảo dưỡng của một xe tại một xưởng, đi qua `draft → pending_approval → approved | rejected`.

## Example

Xe VF6 mốc 12.000 km tại VinFast Cầu Giấy: AI ước tính 1.250.000 VNĐ, chủ xưởng duyệt 1.100.000 VNĐ.

## Terminology

* HITL — Human-in-the-loop: AI đề xuất, con người duyệt.

---

# 4. Identity & Keys

| Field | Type | Description |
| --- | --- | --- |
| `id` | `uuid` | PK, sinh bằng `uuid4` |

---

# 5. Attributes

| Tên trường (Field) | Kiểu dữ liệu (Data Type) | Required | Nullable | Default | Ràng buộc (Constraints) | Mô tả (Description) |
| --- | --- | ---: | ---: | --- | --- | --- |
| `id` | `uuid` | Yes | No | `uuid4` | PK | ID báo giá |
| `user_vehicle_id` | `uuid` | Yes | No | - | FK → `user_vehicle.id` `ON DELETE CASCADE` | Xe được báo giá |
| `workshop_id` | `uuid` | Yes | No | - | FK → `workshop.id` | Xưởng báo giá và duyệt `[Đề xuất]` |
| `odo_milestone` | `integer` | No | Yes | - | `> 0` | Mốc bảo dưỡng liên quan (khớp `maintenance_rule.odo_milestone`); `NULL` = báo giá ngoài mốc |
| `booking_id` | `uuid` | No | Yes | - | FK → `booking.id` `ON DELETE SET NULL` | Lịch hẹn thực hiện báo giá này |
| `source_message_id` | `uuid` | No | Yes | - | FK → `chat_message.id` `ON DELETE SET NULL` | Tin nhắn chat yêu cầu lập báo giá, khi nháp được tạo từ trợ lý AI (BR-ENT-460) |
| `status` | `quote_status_enum` | Yes | No | `draft` | `draft / pending_approval / approved / rejected` | Trạng thái HITL |
| `estimated_total` | `numeric(12,2)` | Yes | No | - | `>= 0` | Tổng giá ước tính (AI) |
| `approved_total` | `numeric(12,2)` | No | Yes | - | `>= 0` | Tổng sau khi chủ xưởng duyệt |
| `reviewed_by` | `uuid` | No | Yes | - | FK → `workshop_owner.id` `ON DELETE SET NULL` | Người duyệt / từ chối |
| `reviewer_note` | `text` | No | Yes | - | | Ghi chú của người duyệt |
| `reviewed_at` | `timestamptz` | No | Yes | - | | Thời điểm duyệt / từ chối |
| `expires_at` | `timestamptz` | No | Yes | - | Bắt buộc khi `approved`; `> reviewed_at` | Hạn hiệu lực của báo giá đã duyệt (Q-410) |
| `submitted_at` | `timestamptz` | No | Yes | - | Bắt buộc khi `status ≠ draft`; `<= reviewed_at` | Thời điểm chủ xe gửi duyệt (us-049 BR-1103); dùng sắp danh sách chờ và đo thời gian duyệt |
| `result_seen_at` | `timestamptz` | No | Yes | - | Chỉ có nghĩa khi `approved` / `rejected` | Lúc chủ xe mở báo giá đã có kết quả; `NULL` ⇒ hiện badge kết quả trên Home (us-049 BR-1109) |
| `created_at` | `timestamptz` | Yes | No | `now()` | | |
| `updated_at` | `timestamptz` | Yes | No | `now()` | | |

---

# 6. Attribute Details

## `workshop_id` `[Đề xuất]`

Bản sinh tự động không có cột này. Cần vì (1) giá lấy từ `service_price` theo từng xưởng, (2) người duyệt là chủ của xưởng đó.

## `reviewed_by`

Thay cho `technician_id → users.id`. **Người duyệt là chủ xưởng** (`workshop_owner`, ENT-007) — đã chốt ở Q-411, phù hợp W-11 (chưa có tài khoản kỹ thuật viên / nhân viên xưởng).

## `expires_at`

Gán khi chủ xưởng duyệt: `expires_at = reviewed_at + thời hạn hiệu lực`. Chủ xưởng chọn thời hạn khi duyệt; mặc định 7 ngày `[Đề xuất]`. Báo giá quá hạn vẫn giữ `status = approved` nhưng không dùng để đặt lịch được (BR-ENT-426).

## `odo_milestone`

Thay cho `maintenance_rule_id`: `maintenance_rule` là bảng phẳng (mỗi dòng một hạng mục), nên một mốc gồm nhiều dòng. Liên kết từng hạng mục nằm ở `quote_item.maintenance_rule_id`.

## `estimated_total` và các dòng `quote_item`

Backend tự tính khi tạo nháp: Quote Service gọi Cost Estimation Service (F5) với (xe, xưởng, mốc) rồi snapshot từng dòng vào `quote_item` (us-049 BR-1101). API và AI Agent **không** gửi giá hay danh sách dòng. `estimated_total = Σ quote_item.estimated_price`. Nếu bảng giá thay đổi trước khi gửi duyệt, nháp được tính lại và API trả `QUOTE_DRAFT_REFRESHED` để chủ xe xem lại.

## `submitted_at`, `result_seen_at`

`submitted_at` ghi khi `draft → pending_approval`. `result_seen_at` ghi lần đầu chủ xe mở chi tiết báo giá sau khi xưởng duyệt hoặc từ chối; mở lại không đổi giá trị.

## `booking_id`

Thay cho `appointments.quote_id` để **không thay đổi** bảng core `booking`. Chỉ gán khi `status = approved`.

---

# 7. Relationships

## 7.1 Relationship Overview

```mermaid
erDiagram
    user_vehicle   ||--o{ quote      : "quoted"
    workshop       ||--o{ quote      : "quotes"
    workshop_owner |o--o{ quote      : "reviews"
    booking        |o--o{ quote      : "fulfils"
    quote          ||--|{ quote_item : "contains"
```

## 7.2 Relationship Details

| Related Entity | Relationship | Cardinality | Description |
| --- | --- | --- | --- |
| [`user_vehicle`](../vehicle/user_vehicle.entity.md) | for | N:1 | Xe |
| [`workshop`](../workshop/workshop.entity.md) | at | N:1 | Xưởng |
| `workshop_owner` (ENT-007) | reviewed by | N:0..1 | Người duyệt |
| [`booking`](./booking.entity.md) | fulfilled by | N:0..1 | Lịch hẹn |
| [`quote_item`](./quote_item.entity.md) | contains | 1:N (≥1 khi gửi duyệt) | Dòng hạng mục |

---

# 8. Entity Lifecycle / State

## 8.1 States

| State (DB) | API | Meaning |
| --- | --- | --- |
| `draft` | `DRAFT` | AI đang lập, chủ xe chưa gửi |
| `pending_approval` | `PENDING_APPROVAL` | Chờ chủ xưởng duyệt |
| `approved` | `APPROVED` | Đã duyệt, có thể đặt lịch |
| `rejected` | `REJECTED` | Bị từ chối |

## 8.2 State Transition

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> pending_approval: Gửi duyệt (có ≥ 1 quote_item)
    pending_approval --> approved: Chủ xưởng duyệt
    pending_approval --> rejected: Chủ xưởng từ chối
    approved --> [*]
    rejected --> [*]
```

## 8.3 Transition Rules

* `approved`, `rejected` là trạng thái cuối. Muốn báo giá lại ⇒ tạo `quote` mới.
* Sửa bản sinh tự động: bỏ `APPROVED → REJECTED`, thay bằng `PENDING_APPROVAL → REJECTED`.

---

# 9. Business Rules & Constraints

## BR-ENT-413 — Chỉ chủ của xưởng được duyệt

**Rule:** `reviewed_by` phải là `workshop.owner_id` của `quote.workshop_id` tại thời điểm duyệt.

## BR-ENT-414 — Tổng tiền khớp chi tiết

**Rule:** `estimated_total = SUM(quote_item.estimated_price)`; khi `approved`: `approved_total = SUM(COALESCE(quote_item.approved_price, quote_item.estimated_price))`. Tính ở service trong cùng transaction.

## BR-ENT-415 — Khoá sau khi duyệt

**Rule:** Quote `approved` / `rejected` không được sửa tiền hoặc thêm/xoá `quote_item`.

## BR-ENT-416 — Điều kiện tạo

**Rule:** Xe phải `verified` + `link_status = active`; xưởng phải `status = active`.

## BR-ENT-426 — Hạn hiệu lực báo giá (Q-410)

**Rule:** Chỉ báo giá `approved` còn hạn (`now() < expires_at`) mới được dùng để đặt lịch (gán `booking_id`).

**Condition:** Chủ xe đặt lịch từ báo giá.

**Expected Behavior:** Quá hạn ⇒ từ chối, AI Agent đề nghị lập báo giá mới.

---

# 10. Data Integrity

* `CHECK (estimated_total >= 0)`, `CHECK (approved_total IS NULL OR approved_total >= 0)`.
* `CHECK (status NOT IN ('approved','rejected') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))`.
* `CHECK (status <> 'approved' OR (approved_total IS NOT NULL AND expires_at IS NOT NULL))`.
* `CHECK (expires_at IS NULL OR (reviewed_at IS NOT NULL AND expires_at > reviewed_at))`.
* `CHECK (booking_id IS NULL OR status = 'approved')`.
* `CHECK (odo_milestone IS NULL OR odo_milestone > 0)` (`ck_quote_odo_milestone`).
* `CHECK (status = 'draft' OR submitted_at IS NOT NULL)` (`ck_quote_submitted_at`), `CHECK (reviewed_at IS NULL OR submitted_at IS NULL OR reviewed_at >= submitted_at)` (`ck_quote_reviewed_after_submit`).
* Unique partial index `uq_quote_pending_per_milestone (user_vehicle_id, workshop_id, odo_milestone) WHERE status = 'pending_approval'`: mỗi (xe, xưởng, mốc) chỉ có một báo giá chờ duyệt (us-049 BR-1104). Vi phạm ⇒ `QUOTE_ALREADY_PENDING`.

---

# 11. Index & Query Requirements

| Query | Fields | Frequency | Required Index |
| --- | --- | --- | --- |
| Báo giá chờ duyệt của xưởng | `workshop_id`, `status` | Cao | `ix_quote_workshop_status` |
| Báo giá của một xe | `user_vehicle_id`, `created_at` | Cao | `ix_quote_user_vehicle_created` |
| Chặn trùng chờ duyệt | `user_vehicle_id`, `workshop_id`, `odo_milestone` | Mỗi lần gửi duyệt | `uq_quote_pending_per_milestone` (partial unique) |

---

# 12. Ownership & Authorization

| Actor / Role | Read | Create | Update | Delete |
| --- | ---: | ---: | ---: | ---: |
| Chủ xe | ✅ (xe của mình) | ✅ (UI hoặc qua AI Agent) | ✅ (gửi duyệt khi `draft`; ghi `result_seen_at`) | ✅ (chỉ `draft`) |
| Chủ xưởng | ✅ (xưởng mình) | ❌ | ✅ (duyệt / từ chối) | ❌ |
| AI Agent | ✅ | ✅ | ✅ (khi `draft`) | ❌ |

---

# 13–16. Audit, Data Source, Security, Retention

* Audit: `created_at`, `updated_at`, `reviewed_by`, `reviewed_at`.
* Source of truth: App DB. Giá lấy từ `service_price` (ưu tiên) hoặc `maintenance_rule.estimated_cost`.
* Không xoá cứng quote đã gửi duyệt.

---

# 21. Open Questions

| ID | Question | Owner | Status |
| --- | --- | --- | --- |
| Q-410 | Có cần hạn hiệu lực báo giá (`expires_at`) không? | Product | **Resolved** — Có, thêm `expires_at`, BR-ENT-426 |
| Q-411 | Xác nhận người duyệt là chủ xưởng (W-11) cho MVP. | Product | **Resolved** — Người duyệt là chủ xưởng |

**Thay đổi so với bản sinh tự động (`quotes`):** đổi tên bảng số ít; `vehicle_id` → `user_vehicle_id`; bỏ `maintenance_rule_id`, thêm `odo_milestone`; thêm `workshop_id` `[Đề xuất]`, `booking_id`; `technician_id` → `reviewed_by` (FK `workshop_owner`); `technician_note` → `reviewer_note`; `approved_at` → `reviewed_at`; thêm `expires_at`; `VARCHAR` status → enum lowercase; `TIMESTAMP` → `timestamptz`; `updated_at` NOT NULL; sửa state transition.

---

# 22. Change Log

| Version | Date | Author | Changes |
| --- | --- | --- | --- |
| `v1.0` | `2026-09-27` | Team 4 Người | Tạo mới từ bản ERD sinh tự động, chỉnh theo quy ước core v1.1 |
| `v1.1` | `2026-09-27` | Team 4 Người | Thêm `expires_at`, BR-ENT-426 (Q-410); chốt người duyệt là chủ xưởng (Q-411) |
| `v1.2` | `2026-10-07` | Team 4 Người | Gộp phần mở rộng của us-049 entity spec và đồng bộ với code (báo cáo 03/10, C-07): thêm `source_message_id`, `submitted_at`, `result_seen_at`; ghi rõ backend tự tính dòng và tổng (BR-1101); thêm CHECK `ck_quote_odo_milestone`, `ck_quote_submitted_at`, `ck_quote_reviewed_after_submit` và unique partial index chờ duyệt |
