# Entity Specification — Chuyển sang người thật

> Entity cho Feature `FEAT-P2-PL02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](pl-02-phase2-spec.ff.md). **API:** [API Spec](pl-02-phase2-spec.api.md).
>
> **Nguyên tắc (BR-PL02-03, FF §21):** `handoff_request` là **nhãn xử lý gọn nhẹ** — không phân loại nhiều cấp, không SLA nhiều tầng, không gán nhân viên hỗ trợ, không bình luận qua lại. Không tạo lại bảng `support_ticket` đã bỏ (AC-PL02-03).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-PL02` — PL-02 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [pl-02-phase2-spec.ff.md](pl-02-phase2-spec.ff.md) |
| Related API | [pl-02-phase2-spec.api.md](pl-02-phase2-spec.api.md) |
| Related FE | [pl-02-phase2-spec.fe.md](pl-02-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-PL02-01` | `HandoffRequest` | `handoff_request` | **Mới** |
| `ENT-417` | `FollowUp` | `follow_up` | Có sẵn — không đổi (đọc `has_issue`, `rating`) |

---

# 2. `handoff_request` (ENT-PL02-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `user_vehicle_id` | `uuid` | Yes | `NULL` | FK `user_vehicle.id` `ON DELETE SET NULL` |
| `workshop_id` | `uuid` | No | — | FK `workshop.id`; xưởng nhận (§3) |
| `reason` | `varchar(24)` | No | — | `OWNER_REQUEST`, `NO_SOURCE`, `WARRANTY_DISPUTE`, `FRUSTRATION`, `LOW_RATING`, `FOLLOW_UP_ISSUE` (BR-PL02-01) |
| `urgency` | `varchar(8)` | No | `'NORMAL'` | `NORMAL`, `URGENT` (dấu hiệu an toàn, EF-PL02-02) |
| `status` | `varchar(10)` | No | `'open'` | `open`, `seen`, `contacted`, `resolved`, `cancelled` (FF §13) |
| `summary` | `jsonb` | No | — | 4 thành phần §2.1 (AC-PL02-02) |
| `conversation_id` | `uuid` | Yes | `NULL` | FK `conversation.id` `ON DELETE SET NULL` |
| `follow_up_id` | `uuid` | Yes | `NULL` | FK `follow_up.id` `ON DELETE SET NULL` |
| `booking_id` | `uuid` | Yes | `NULL` | FK `booking.id` `ON DELETE SET NULL` — lịch liên quan |
| `seen_at` / `contacted_at` / `resolved_at` / `cancelled_at` | `timestamptz` | Yes | `NULL` | |
| `handled_by_owner_id` | `uuid` | Yes | `NULL` | FK `workshop_owner.id` — người cập nhật cuối |
| `resolution_note` | `varchar(300)` | Yes | `NULL` | Ghi chú ngắn của xưởng, chủ xe **không** thấy |
| `reminded_at` / `escalated_at` | `timestamptz` | Yes | `NULL` | EF-PL02-01 |
| `created_at` / `updated_at` | `timestamptz` | No | `now()` | |

```sql
-- BR-PL02-05: một yêu cầu đang mở mỗi hội thoại.
CREATE UNIQUE INDEX ux_handoff_open_conversation ON handoff_request (conversation_id)
  WHERE conversation_id IS NOT NULL AND status IN ('open', 'seen', 'contacted');
-- Một yêu cầu cho mỗi follow-up.
CREATE UNIQUE INDEX ux_handoff_follow_up ON handoff_request (follow_up_id) WHERE follow_up_id IS NOT NULL;
CREATE INDEX ix_handoff_workshop_open ON handoff_request (workshop_id, status, created_at) WHERE status IN ('open', 'seen', 'contacted');
ALTER TABLE handoff_request ADD CONSTRAINT ck_handoff_status CHECK (status IN ('open','seen','contacted','resolved','cancelled'));
ALTER TABLE handoff_request ADD CONSTRAINT ck_handoff_reason CHECK (reason IN
  ('OWNER_REQUEST','NO_SOURCE','WARRANTY_DISPUTE','FRUSTRATION','LOW_RATING','FOLLOW_UP_ISSUE'));
```

## 2.1 `summary`

```json
{ "issue": "Sau bảo dưỡng 24.000 km, phanh trước kêu khi dừng; khách đánh giá 2 sao.",
  "vehicle": { "modelName": "VF 8", "licensePlateMasked": "30A-***.45", "odoKm": 24100 },
  "booking": { "bookingCode": "EVC-…", "date": "2026-10-08", "items": ["Bảo dưỡng 24.000 km"] },
  "agentAnswered": [ "Đã khuyên khách không phanh gấp khi xe kêu (theo sổ tay, trích nguồn)" ],
  "customerQuote": "Về nhà thấy phanh trước kêu",
  "generatedBy": "TEMPLATE+LLM" }
```

Bốn thành phần bắt buộc: `issue`, `vehicle`, `booking` (có thể `null` khi không có lịch, ghi rõ "Không có lịch liên quan"), `agentAnswered` (có thể `[]` với "Trợ lý chưa trả lời gì"). Validate trước khi lưu.

---

# 3. Chọn xưởng nhận (BR-PL02-02, EDGE-PL02-01)

1. Có `booking_id` (follow-up, hội thoại có `refs.bookingId`, lịch mở / gần nhất ≤ 30 ngày) ⇒ xưởng của lịch.
2. Không ⇒ xưởng yêu thích (BK-01 hồ sơ / PS-01 `preferred_workshop`).
3. Không ⇒ xưởng gần nhất theo điểm neo (BK-01 / us-061).

---

# 4. Retention

Giữ 365 ngày sau `resolved` / `cancelled`; xoá tài khoản ⇒ cascade.

---

# 5. Migration

Một revision: bảng + index + CHECK. Không backfill (follow-up cũ có `has_issue` không tự tạo yêu cầu).

---

# 6. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
