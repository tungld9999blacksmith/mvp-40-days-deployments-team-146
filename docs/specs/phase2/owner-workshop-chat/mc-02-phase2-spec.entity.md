# Entity Specification — Agent cùng tham gia luồng chat

> Entity cho Feature `FEAT-P2-MC02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](mc-02-phase2-spec.ff.md). **API:** [API Spec](mc-02-phase2-spec.api.md).
>
> **Nguyên tắc:** agent là một **người tham gia** của luồng MC-01 (`booking_thread_participant.role = agent`), tin của agent là `booking_thread_message` bình thường có nhãn. Thêm: cấu hình bật theo xưởng, trạng thái gắn cờ trên tin, và tóm tắt chỉ cho xưởng (không phải tin trong luồng — BR-MC02-05).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-MC02` — MC-02 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend + AI Team |
| Created Date | `2026-10-12` |
| Related FF | [mc-02-phase2-spec.ff.md](mc-02-phase2-spec.ff.md) |
| Related API | [mc-02-phase2-spec.api.md](mc-02-phase2-spec.api.md) |
| Related FE | [mc-02-phase2-spec.fe.md](mc-02-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Thay đổi |
|---|---|---|---|
| `ENT-008` | `Workshop` | `workshop` — **thêm cột** `thread_agent_enabled` | Có sẵn |
| `ENT-MC01-01` | `BookingThread` | `booking_thread.agent_enabled` | MC-01 (đã có cột) — chụp từ xưởng khi mở luồng, chủ xưởng đổi được |
| `ENT-MC01-03` | `BookingThreadMessage` | **thêm cột** `flag_status`, `flag_urgency`, `answered_by_message_id`, `agent_citations` | MC-01 |
| `ENT-MC02-01` | `BookingThreadSummary` | `booking_thread_summary` | **Mới** |

---

# 2. Cột mới

| Bảng | Cột | Type | Ghi chú |
|---|---|---|---|
| `workshop` | `thread_agent_enabled` | `boolean NOT NULL DEFAULT false` | Xưởng bật / tắt (FF §3.1) |
| `booking_thread_message` | `flag_status` | `varchar(10) NULL` | `flagged` → `answered` (FF §13); trên **tin của chủ xe** cần xưởng trả lời |
| | `flag_urgency` | `varchar(8) NULL` | `NORMAL`, `URGENT` (an toàn, EF-MC02-01) |
| | `answered_by_message_id` | `uuid NULL` | Tin của xưởng / KTV trả lời câu gắn cờ (trả lời đầu tiên sau đó, hoặc trả lời có trích dẫn tin) |
| | `agent_citations` | `jsonb NULL` | Nguồn của tin agent (như `chat_message.citations`) |

```sql
CREATE INDEX ix_btm_flagged ON booking_thread_message (thread_id) WHERE flag_status = 'flagged';
```

---

# 3. `booking_thread_summary` (ENT-MC02-01)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `thread_id` | `uuid` | No | FK `booking_thread.id` `ON DELETE CASCADE` |
| `up_to_seq` | `bigint` | No | Tóm tắt tới tin này |
| `summary` | `text` | No | ≤ 1.000 ký tự |
| `requested_by_owner_id` / `requested_by_technician_id` | `uuid` | Yes | |
| `created_at` | `timestamptz` | No | |

Chỉ phía xưởng đọc được (BR-MC02-05). Tóm tắt cũ giữ lại; lần hỏi kế tiếp tạo bản mới nếu có tin mới.

---

# 4. Migration

Một revision: 1 cột `workshop`, 4 cột `booking_thread_message`, 1 bảng.

---

# 5. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
