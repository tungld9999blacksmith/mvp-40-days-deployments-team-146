# Entity Specification — Hỗ trợ tại khoang làm việc

> Entity cho Feature `FEAT-P2-TA02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ta-02-phase2-spec.ff.md). **API:** [API Spec](ta-02-phase2-spec.api.md).
>
> **Nguyên tắc:** mẫu checklist là dữ liệu tham chiếu có nguồn (tài liệu hãng); checklist của một lịch là **bản chụp** mẫu lúc mở để thay đổi mẫu sau đó không làm đổi việc đang làm. Không lưu âm thanh (giọng nói chỉ thành văn bản sau khi KTV xác nhận).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-TA02` — TA-02 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [ta-02-phase2-spec.ff.md](ta-02-phase2-spec.ff.md) |
| Related API | [ta-02-phase2-spec.api.md](ta-02-phase2-spec.api.md) |
| Related FE | [ta-02-phase2-spec.fe.md](ta-02-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-TA02-01` | `ServiceChecklistTemplate` | `service_checklist_template` | **Mới** |
| `ENT-TA02-02` | `ServiceChecklistTemplateItem` | `service_checklist_template_item` | **Mới** |
| `ENT-TA02-03` | `ServiceChecklistItem` | `service_checklist_item` | **Mới** — trạng thái theo booking |
| `ENT-TA02-04` | `ShiftHandoverNote` | `shift_handover_note` | **Mới** — ghi chú giao ca (văn bản đã xác nhận) |
| `ENT-008` | `Workshop` | `workshop` — **thêm cột** `handover_times` | Có sẵn |

---

# 2. Mẫu checklist (ENT-TA02-01, 02)

`service_checklist_template`:

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `model_id` | `varchar(64)` | No | |
| `odo_milestone` | `integer` | No | |
| `version` | `smallint` | No | Tăng khi nhóm dữ liệu cập nhật |
| `source_document_id` | `uuid` | Yes | FK `official_document.id` — nguồn (BR-TA02-01) |
| `active` | `boolean` | No | Một mẫu `active` mỗi (model, mốc) |

`service_checklist_template_item`:

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `template_id` | `uuid` | No | FK `service_checklist_template.id` `ON DELETE CASCADE` |
| `position` | `smallint` | No | Thứ tự |
| `item_code` | `varchar(50)` | Yes | Khớp `maintenance_rule.item_code` khi có |
| `label` | `varchar(200)` | No | |
| `required` | `boolean` | No | |
| `source_chunk_id` | `uuid` | Yes | FK `document_chunk.id` — trích đoạn |

```sql
CREATE UNIQUE INDEX ux_checklist_template_active ON service_checklist_template (model_id, odo_milestone) WHERE active;
```

Không có mẫu (EF-TA02-01) ⇒ sinh bản chụp từ `maintenance_rule` của mốc (mọi mục `required = true`, `source = MAINTENANCE_RULE`).

---

# 3. `service_checklist_item` (ENT-TA02-03)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `booking_id` | `uuid` | No | — | FK `booking.id` `ON DELETE CASCADE` |
| `template_item_id` | `uuid` | Yes | `NULL` | FK mẫu; `NULL` khi sinh từ `maintenance_rule` hoặc dòng gộp / phát sinh |
| `source` | `varchar(16)` | No | — | `TEMPLATE`, `MAINTENANCE_RULE`, `BOOKING_LINE` (dòng gộp HS-02 / phát sinh đã duyệt AD-04) |
| `position` | `smallint` | No | — | |
| `label` | `varchar(200)` | No | — | Chụp từ mẫu |
| `required` | `boolean` | No | — | |
| `status` | `varchar(8)` | No | `'pending'` | `pending`, `done`, `skipped` (FF §13) |
| `skip_reason` | `varchar(200)` | Yes | `NULL` | Bắt buộc khi `skipped` (AF-TA02-01) |
| `marked_by_technician_id` / `marked_by_owner_id` | `uuid` | Yes | | Người đánh dấu (EDGE-TA02-01) |
| `marked_at` | `timestamptz` | Yes | `NULL` | BR-TA02-04 (thời lượng thực tế từng mục) |
| `template_version` | `smallint` | Yes | `NULL` | |

```sql
CREATE INDEX ix_checklist_item_booking ON service_checklist_item (booking_id, position);
ALTER TABLE service_checklist_item ADD CONSTRAINT ck_checklist_skip CHECK (status <> 'skipped' OR skip_reason IS NOT NULL);
ALTER TABLE service_checklist_item ADD CONSTRAINT ck_checklist_marked CHECK (status = 'pending' OR marked_at IS NOT NULL);
```

---

# 4. `shift_handover_note` (ENT-TA02-04)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `booking_id` | `uuid` | No | FK `booking.id` `ON DELETE CASCADE` |
| `author_technician_id` / `author_owner_id` | `uuid` | Yes | |
| `text` | `varchar(1000)` | No | Văn bản đã xác nhận (gõ hoặc từ giọng nói, BR-TA02-03) |
| `input_method` | `varchar(8)` | No | `TYPED`, `VOICE` |
| `created_at` | `timestamptz` | No | |

---

# 5. `workshop` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `handover_times` | `jsonb` | No | `'[]'` | Giờ giao ca cố định, ví dụ `["12:00","17:00"]`; rỗng = không tự gửi (Q-TA02-01) |

---

# 6. Migration

Một revision: 4 bảng, 1 cột; seed mẫu checklist từ tài liệu (nhóm dữ liệu, sau khi hãng xác nhận quyền dùng — FF §23).

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
