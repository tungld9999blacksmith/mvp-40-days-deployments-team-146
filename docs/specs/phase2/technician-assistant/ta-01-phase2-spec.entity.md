# Entity Specification — Trợ lý tra cứu và nhắc việc cho kỹ thuật viên

> Entity cho Feature `FEAT-P2-TA01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ta-01-phase2-spec.ff.md). **API:** [API Spec](ta-01-phase2-spec.api.md).
>
> **Nguyên tắc:** trợ lý xưởng tách biệt agent chủ xe (FF §21): hội thoại lưu ở bảng riêng, không dùng `conversation` / `chat_message` của chủ xe, không đọc / ghi bộ nhớ dài hạn PS-01. Trợ lý chỉ đọc dữ liệu nghiệp vụ; không có bảng nghiệp vụ mới ngoài hội thoại và nhắc việc.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-TA01` — TA-01 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend + AI Team |
| Created Date | `2026-10-12` |
| Related FF | [ta-01-phase2-spec.ff.md](ta-01-phase2-spec.ff.md) |
| Related API | [ta-01-phase2-spec.api.md](ta-01-phase2-spec.api.md) |
| Related FE | [ta-01-phase2-spec.fe.md](ta-01-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-TA01-01` | `WorkshopAssistantThread` | `workshop_assistant_thread` | **Mới** |
| `ENT-TA01-02` | `WorkshopAssistantMessage` | `workshop_assistant_message` | **Mới** |
| `ENT-TA01-03` | `TechnicianReminder` | `technician_reminder` | **Mới** |
| `ENT-402` | `Booking` | `booking.reported_symptom` | Do AD-02 thêm; TA-01 chỉ đọc |

---

# 2. `workshop_assistant_thread` (ENT-TA01-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `workshop_id` | `uuid` | No | — | FK `workshop.id` `ON DELETE CASCADE` |
| `actor_type` | `varchar(16)` | No | — | `workshop_owner`, `technician` |
| `owner_id` | `uuid` | Yes | `NULL` | FK `workshop_owner.id` `ON DELETE CASCADE` |
| `technician_id` | `uuid` | Yes | `NULL` | FK `technician.id` `ON DELETE CASCADE` |
| `title` | `varchar(80)` | Yes | `NULL` | Tự đặt từ câu hỏi đầu |
| `created_at` / `last_message_at` | `timestamptz` | No | `now()` | |

```sql
ALTER TABLE workshop_assistant_thread ADD CONSTRAINT ck_wat_actor CHECK (
  (actor_type = 'workshop_owner' AND owner_id IS NOT NULL AND technician_id IS NULL) OR
  (actor_type = 'technician' AND technician_id IS NOT NULL AND owner_id IS NULL));
CREATE INDEX ix_wat_actor ON workshop_assistant_thread (workshop_id, technician_id, owner_id, last_message_at DESC);
```

Mỗi người có thể có nhiều thread; mặc định frontend dùng thread gần nhất trong ngày.

---

# 3. `workshop_assistant_message` (ENT-TA01-02)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `thread_id` | `uuid` | No | — | FK `workshop_assistant_thread.id` `ON DELETE CASCADE` |
| `seq` | `bigint` | No | identity | Thứ tự |
| `role` | `varchar(10)` | No | — | `user`, `assistant`, `tool` |
| `content` | `text` | No | — | |
| `client_message_id` | `uuid` | Yes | `NULL` | Chống gửi trùng (unique theo thread) |
| `card` | `jsonb` | Yes | `NULL` | Phong bì thẻ CH-02 (`VEHICLE_BRIEF`, `JOB_LIST`, `SERVICE_HISTORY_LIST`) |
| `chips` | `jsonb` | No | `'[]'` | Chip cho KTV (FF §3.1) |
| `tool_calls` / `tool_name` / `tool_call_id` | như `chat_message` | | | Phát lại ngữ cảnh |
| `trace_id` | `varchar(64)` | Yes | `NULL` | LangSmith |
| `created_at` | `timestamptz` | No | `now()` | |

```sql
CREATE UNIQUE INDEX ux_wam_client ON workshop_assistant_message (thread_id, client_message_id) WHERE client_message_id IS NOT NULL;
CREATE INDEX ix_wam_thread_seq ON workshop_assistant_message (thread_id, seq);
```

**Không lưu** SĐT đầy đủ, email chủ xe trong `content` / `card` (AC-TA01-04): tool trả dữ liệu đã che, guard đầu ra kiểm lại trước khi lưu.

Retention: 180 ngày (dữ liệu vận hành của xưởng); KTV bị vô hiệu ⇒ giữ để chủ xưởng kiểm tra, không hiển thị cho KTV.

---

# 4. `technician_reminder` (ENT-TA01-03)

Chống nhắc trùng (AC-TA01-03).

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `booking_id` | `uuid` | No | FK `booking.id` `ON DELETE CASCADE` |
| `technician_id` | `uuid` | No | FK `technician.id` `ON DELETE CASCADE` |
| `kind` | `varchar(16)` | No | `ARRIVAL`, `STAGE_OVERDUE` |
| `stage` | `varchar(20)` | Yes | Bước tiến độ khi `STAGE_OVERDUE` |
| `due_at` | `timestamptz` | No | Thời điểm phải nhắc |
| `sent_at` | `timestamptz` | Yes | |

```sql
CREATE UNIQUE INDEX ux_tr_once ON technician_reminder (booking_id, technician_id, kind, coalesce(stage, ''));
```

Đổi giờ lịch / đổi KTV ⇒ xoá dòng chưa gửi để job tạo lại theo giờ mới.

---

# 5. Che thông tin (BR-TA01-01)

| Dữ liệu | Hiển thị cho trợ lý xưởng |
|---|---|
| Tên chủ xe | Rút gọn: "Anh/Chị" không đoán giới tính ⇒ "Khách {Tên cuối}" (ví dụ "Khách Tùng") |
| Số điện thoại, email | Không bao giờ |
| Biển số | Đầy đủ (xưởng cần nhận xe; đã có trên Board) |
| VIN | 6 ký tự cuối |
| Triệu chứng khách kể | Nguyên văn, nhãn "Khách mô tả" (BR-TA01-05) |

---

# 6. Migration

Một revision: 3 bảng, index, CHECK.

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
