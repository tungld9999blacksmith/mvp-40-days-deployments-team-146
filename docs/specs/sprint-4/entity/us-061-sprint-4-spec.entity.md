# Entity Specification — Đặt lịch bảo dưỡng nhanh

> Entity cho Feature `FEAT-QBOOK-001` (US-061).
>
> **Nguyên tắc:** đề xuất đặt lịch là dữ liệu có trạng thái và ràng buộc (một đề xuất đang chờ mỗi chủ xe, một booking mỗi đề xuất), nên nằm trong bảng riêng. `chat_message.card` chỉ giữ ảnh chụp dữ liệu hiển thị + `proposalId`; trạng thái luôn đọc từ bảng này.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-QBOOK-001` — US-061 |
| Version | `v1.1` |
| Status | `Approved` |
| Owner | Backend Team |
| Created Date | `2026-10-03` |
| Related FF | [us-061-sprint-4-spec.ff.md](../feature-functional/us-061-sprint-4-spec.ff.md) |
| Related API | [us-061-sprint-4-spec.api.md](../api/us-061-sprint-4-spec.api.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-475` | `BookingProposal` | `booking_proposal` | **Mới** | Bảng + enum + 3 index |
| `ENT-402` | `Booking` | `booking` | Có sẵn — không đổi cột | Ghi `source_message_id` cho booking tạo từ đề xuất (cột đã có) |
| — | `ChatMessage` | `chat_message` | Có sẵn — không đổi cột | `card` mang `type = BOOKING_PROPOSAL` / `QUICK_BOOKING_NEED_LOCATION`; `refs.bookingId` ở tin kết quả |

---

# 2. `booking_proposal` (ENT-475)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `integer` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `user_vehicle_id` | `uuid` | No | — | FK `user_vehicle.id` `ON DELETE CASCADE` |
| `conversation_id` | `uuid` | No | — | FK `conversation.id` `ON DELETE CASCADE` |
| `message_id` | `uuid` | Yes | `NULL` | FK `chat_message.id` `ON DELETE SET NULL`; tin nhắn chứa thẻ, gán ngay sau khi tin được lưu |
| `source` | `varchar(16)` | No | — | `QUICK_BOOKING` (ô nhanh, đổi, hết chỗ) / `CHAT_AGENT` (LLM `propose_booking`) |
| `status` | `booking_proposal_status_enum` | No | `'proposed'` | `proposed`, `confirmed`, `cancelled`, `superseded`, `expired` |
| `superseded_reason` | `varchar(16)` | Yes | `NULL` | `NEW_PROPOSAL`, `REVISED`, `SLOT_FULL`; chỉ khi `superseded` |
| `odo_milestone` | `integer` | Yes | `NULL` | Mốc km (BR-1502); NULL khi LLM đề xuất không kèm mốc |
| `workshop_id` | `uuid` | No | — | FK `workshop.id`; xưởng của phương án chính |
| `booking_date` | `date` | No | — | Ngày của phương án chính |
| `time_slot` | `time` | No | — | Giờ bắt đầu của phương án chính |
| `options` | `jsonb` | No | — | Ảnh chụp `{primary, alternatives[]}` (§3) để dựng lại đề xuất khi hết chỗ / đổi |
| `location_basis` | `varchar(16)` | No | — | `DEVICE`, `PROFILE`, `PROVINCE`, `NONE`. Không lưu toạ độ thiết bị |
| `booking_id` | `uuid` | Yes | `NULL` | FK `booking.id` `ON DELETE SET NULL` |
| `expires_at` | `timestamptz` | No | — | `created_at + 30 phút` (config `QUICK_BOOKING_PROPOSAL_TTL_MINUTES`) |
| `confirmed_at` | `timestamptz` | Yes | `NULL` | |
| `closed_at` | `timestamptz` | Yes | `NULL` | Thời điểm sang `cancelled` / `superseded` / `expired` |
| `created_at` | `timestamptz` | No | `now()` | |
| `updated_at` | `timestamptz` | No | `now()` | `onupdate` |

## 2.1 Constraints & Indexes

```sql
CREATE TYPE booking_proposal_status_enum AS ENUM
  ('proposed', 'confirmed', 'cancelled', 'superseded', 'expired');

-- BR-1508: một đề xuất đang chờ mỗi chủ xe.
CREATE UNIQUE INDEX ux_booking_proposal_open_per_user
  ON booking_proposal (user_id) WHERE status = 'proposed';

-- BR-1513: một đề xuất có tối đa một booking, một booking thuộc tối đa một đề xuất.
CREATE UNIQUE INDEX ux_booking_proposal_booking
  ON booking_proposal (booking_id) WHERE booking_id IS NOT NULL;

-- Đọc trạng thái thẻ theo hội thoại.
CREATE INDEX ix_booking_proposal_conversation ON booking_proposal (conversation_id, created_at);

ALTER TABLE booking_proposal ADD CONSTRAINT ck_booking_proposal_confirmed
  CHECK ((status = 'confirmed') = (booking_id IS NOT NULL AND confirmed_at IS NOT NULL));
ALTER TABLE booking_proposal ADD CONSTRAINT ck_booking_proposal_superseded
  CHECK ((status = 'superseded') = (superseded_reason IS NOT NULL));
ALTER TABLE booking_proposal ADD CONSTRAINT ck_booking_proposal_source
  CHECK (source IN ('QUICK_BOOKING', 'CHAT_AGENT'));
ALTER TABLE booking_proposal ADD CONSTRAINT ck_booking_proposal_location_basis
  CHECK (location_basis IN ('DEVICE', 'PROFILE', 'PROVINCE', 'NONE'));
```

---

# 3. `options` (jsonb)

```json
{
  "primary": {
    "optionId": "opt-1",
    "workshopId": "c0ca2f6b-9d18-4af3-8c03-51ea8d203e56",
    "workshopName": "VinFast Thanh Xuân",
    "address": "68 Lê Văn Lương, Thanh Xuân, Hà Nội",
    "region": "Hà Nội",
    "distanceKm": 1.84,
    "isPreferred": false,
    "date": "2026-10-05",
    "timeSlot": "10:00",
    "estimate": { "chargeableTotal": "350000", "hasReferencePrice": false, "coveredCount": 1 }
  },
  "alternatives": [
    { "optionId": "opt-2", "...": "cùng cấu trúc" }
  ]
}
```

- `distanceKm`: `null` khi không có toạ độ neo hoặc xưởng không có toạ độ (BR-1506).
- `estimate`: `null` khi `cost_estimate` không trả `READY`.
- `alternatives`: 0–2 phần tử.

---

# 4. Business Rules (bổ sung)

## BR-ENT-1501 — Trạng thái hết hạn tính lười

Không có job. Dòng `proposed` có `now() ≥ expires_at` được coi là `expired` khi đọc; được ghi `expired` khi có thao tác chạm vào nó (xác nhận, huỷ, đổi, hoặc khi tạo đề xuất mới cho cùng chủ xe). Hết hạn thắng huỷ: huỷ một dòng đã hết hạn ghi `expired`, không ghi `cancelled`.

## BR-ENT-1502 — Thay thế trước khi chèn

Tạo đề xuất mới trong **cùng transaction**: cập nhật mọi dòng `proposed` của `user_id` sang `superseded` (`NEW_PROPOSAL`, `REVISED` hoặc `SLOT_FULL`) hoặc `expired` (nếu đã quá hạn), rồi mới chèn dòng mới. Index `ux_booking_proposal_open_per_user` là chốt chặn cuối.

## BR-ENT-1503 — Không sửa ảnh chụp

`options`, `workshop_id`, `booking_date`, `time_slot` không đổi sau khi chèn. Đổi phương án luôn tạo dòng mới.

---

# 5. Migration

- Một revision Alembic mới: tạo enum, bảng, 3 index, 4 CHECK.
- `downgrade`: drop bảng rồi drop enum. Booking đã tạo không bị ảnh hưởng (FK nằm ở phía `booking_proposal`).
- Không backfill.
- SQLite trong test: `options` dùng `JSON` (helper `_make_sqlite_compatible` đã đổi `JSONB` → `JSON`); partial index `postgresql_where` bị SQLite bỏ qua, nên test của BR-1508 kiểm hành vi service, không dựa vào index.

---

# 6. Open Questions

| ID | Câu hỏi | Đề xuất |
|---|---|---|
| `Q-ENT-1501` | Giữ đề xuất bao lâu? | Xoá theo `conversation` (cascade); không có job dọn riêng ở MVP |

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-03` | Bản nháp đầu |
| `v1.0` | `2026-10-03` | Chủ sản phẩm duyệt bản nháp; triển khai cùng PR (backend `modules/quick_booking`, frontend `features/assistant/quickBooking`) |
| `v1.1` | `2026-10-03` | Sau review Codex (7/10): khoá theo đề xuất cho xác nhận / đổi / huỷ; liên kết booking ↔ thẻ bền vững; trả lời gửi lại theo `refs.inReplyTo`; hết hạn thắng huỷ; khớp khu vực bỏ dấu; quét khung giờ theo lô; chỉ số đo được |
