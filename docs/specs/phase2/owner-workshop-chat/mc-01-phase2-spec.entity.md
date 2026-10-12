# Entity Specification — Chat theo từng lịch hẹn giữa xưởng và chủ xe

> Entity cho Feature `FEAT-P2-MC01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](mc-01-phase2-spec.ff.md). **API:** [API Spec](mc-01-phase2-spec.api.md).
>
> **Hạ tầng (BR-MC01-06, P2Q-12 — PO chốt 2026-10-12):** **giữ nguyên công nghệ chat MVP** (Supabase Postgres + Redis pub/sub + WebSocket). Spec dùng **phương án giữ Postgres** (tái dùng mô hình `chat_message` + WebSocket `API-MSG-001` của MVP); nếu ADR-02 chọn khác, phần lưu trữ đổi nhưng các trường nghiệp vụ dưới đây giữ nguyên.
>
> **Nguyên tắc:** luồng chat người–người **tách** khỏi hội thoại chủ xe ↔ trợ lý (`conversation` / `chat_message`): khác người tham gia, khác quyền, khác vòng đời. Tin nhắn lưu toàn bộ, không sửa / xoá (PQ-09, BR-MC01-05).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-MC01` — MC-01 |
| Version | `v0.2` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [mc-01-phase2-spec.ff.md](mc-01-phase2-spec.ff.md) |
| Related API | [mc-01-phase2-spec.api.md](mc-01-phase2-spec.api.md) |
| Related FE | [mc-01-phase2-spec.fe.md](mc-01-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-MC01-01` | `BookingThread` | `booking_thread` | **Mới** |
| `ENT-MC01-02` | `BookingThreadParticipant` | `booking_thread_participant` | **Mới** |
| `ENT-MC01-03` | `BookingThreadMessage` | `booking_thread_message` | **Mới** |
| `ENT-MC01-04` | `BookingThreadAttachment` | `booking_thread_attachment` | **Mới** |
| `ENT-MC01-05` | `BookingThreadReport` | `booking_thread_report` | **Mới** — báo cáo nội dung (EF-MC01-02) |
| `ENT-MC01-06` | `BookingThreadAccessLog` | `booking_thread_access_log` | **Mới** — vận hành truy cập khi tranh chấp |

---

# 2. `booking_thread` (ENT-MC01-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `booking_id` | `uuid` | No | — | FK `booking.id` `ON DELETE CASCADE`; **unique** (một lịch một luồng, BR-MC01-01) |
| `workshop_id` | `uuid` | No | — | |
| `user_id` | `bigint` | No | — | Chủ xe |
| `status` | `varchar(8)` | No | `'open'` | `open`, `closed` |
| `opened_at` | `timestamptz` | No | `now()` | |
| `close_at` | `timestamptz` | Yes | `NULL` | `booking kết thúc + THREAD_CLOSE_DAYS`; đặt khi lịch `completed` / `cancelled` |
| `closed_at` | `timestamptz` | Yes | `NULL` | |
| `agent_enabled` | `boolean` | No | `false` | MC-02 |
| `last_message_at` | `timestamptz` | Yes | `NULL` | |
| `awaiting_workshop_since` | `timestamptz` | Yes | `NULL` | Tin chủ xe đầu tiên chưa được xưởng trả lời (SLA, BR-MC01-04) |
| `sla_reminded_at` | `timestamptz` | Yes | `NULL` | |

```sql
CREATE UNIQUE INDEX ux_booking_thread_booking ON booking_thread (booking_id);
CREATE INDEX ix_booking_thread_workshop ON booking_thread (workshop_id, status, last_message_at DESC);
CREATE INDEX ix_booking_thread_user ON booking_thread (user_id, last_message_at DESC);
CREATE INDEX ix_booking_thread_sla ON booking_thread (awaiting_workshop_since) WHERE awaiting_workshop_since IS NOT NULL AND status = 'open';
```

AF-MC01-02 (đổi xưởng): lịch cũ `cancelled` ⇒ luồng cũ đặt `close_at` như thường; lịch mới có luồng mới khi `confirmed`.

---

# 3. `booking_thread_participant` (ENT-MC01-02)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `thread_id` | `uuid` | No | FK `booking_thread.id` `ON DELETE CASCADE` |
| `role` | `varchar(16)` | No | `vehicle_owner`, `workshop_owner`, `technician`, `agent` (MC-02) |
| `user_id` / `workshop_owner_id` / `technician_id` | | Yes | Đúng một cột theo `role` (`agent` không cột nào) |
| `display_name` | `varchar(80)` | No | Tên hiển thị: chủ xe "Khách {tên cuối}" (như TA-01) phía xưởng, "Bạn" phía chủ xe; xưởng "{tên xưởng}"; KTV "KTV {tên}"; agent "Trợ lý EV Care" |
| `can_send` | `boolean` | No | KTV bị đổi phân công ⇒ `false` (EDGE-MC01-01) |
| `last_read_message_id` | `uuid` | Yes | Đánh dấu đã đọc |
| `joined_at` / `left_at` | `timestamptz` | | |

```sql
CREATE INDEX ix_btp_thread ON booking_thread_participant (thread_id);
CREATE INDEX ix_btp_technician ON booking_thread_participant (technician_id) WHERE technician_id IS NOT NULL;
```

Không cột số điện thoại / email (BR-MC01-02).

---

# 4. `booking_thread_message` (ENT-MC01-03)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `thread_id` | `uuid` | No | — | FK `booking_thread.id` `ON DELETE CASCADE` |
| `seq` | `bigint` | No | identity | Thứ tự |
| `participant_id` | `uuid` | Yes | `NULL` | `NULL` = tin hệ thống |
| `kind` | `varchar(12)` | No | — | `TEXT`, `IMAGE`, `CARD`, `SYSTEM` |
| `content` | `text` | Yes | `NULL` | Văn bản **đã che** SĐT / email (BR-MC01-07) |
| `redactions` | `jsonb` | No | `'[]'` | `[{ "type": "PHONE" | "EMAIL", "count": 1 }]` — không lưu bản gốc |
| `card` | `jsonb` | Yes | `NULL` | Phong bì thẻ CH-02 (`EXTRA_QUOTE`, `PROGRESS_UPDATE`, `BOOKING_TICKET`) |
| `client_message_id` | `uuid` | Yes | `NULL` | Chống gửi trùng |
| `created_at` | `timestamptz` | No | `now()` | |

```sql
CREATE UNIQUE INDEX ux_btm_client ON booking_thread_message (thread_id, client_message_id) WHERE client_message_id IS NOT NULL;
CREATE INDEX ix_btm_thread_seq ON booking_thread_message (thread_id, seq);
ALTER TABLE booking_thread_message ADD CONSTRAINT ck_btm_kind CHECK (kind IN ('TEXT','IMAGE','CARD','SYSTEM'));
```

Không UPDATE / DELETE (trigger chặn), trừ cascade khi xoá booking / tài khoản.

---

# 5. `booking_thread_attachment` (ENT-MC01-04)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `message_id` | `uuid` | No | FK `booking_thread_message.id` `ON DELETE CASCADE` |
| `storage_key` | `varchar(300)` | No | Unique; bucket Phase 2 (như `booking_line_photo`) |
| `content_type` | `varchar(50)` | No | `image/jpeg`, `image/png`, `image/webp` |
| `size_bytes` | `integer` | No | ≤ 8 MB |
| `width` / `height` | `smallint` | Yes | |

Ảnh bị xoá EXIF (vị trí) khi tải lên.

---

# 6. `booking_thread_report` (ENT-MC01-05) & `booking_thread_access_log` (ENT-MC01-06)

`booking_thread_report`: `id`, `thread_id`, `message_id`, `reporter_participant_id`, `reason` (`ABUSIVE`, `SPAM`, `OTHER`), `note`, `status` (`open`, `reviewed`), `created_at`, `reviewed_at`, `reviewed_by` (chủ xưởng hoặc vận hành).

`booking_thread_access_log`: `id`, `thread_id`, `accessor` (vận hành, email đã băm), `reason` (id báo cáo / tranh chấp), `created_at` — mọi lần vận hành mở luồng (FF §16). Chỉ thêm.

---

# 7. Retention

Theo PQ-09 (lưu hội thoại); luồng giữ cùng booking. Xoá tài khoản chủ xe ⇒ cascade theo booking (đã có chính sách MVP); ảnh xoá khỏi bucket bằng job.

---

# 8. Migration

Một revision: 6 bảng, index, CHECK, trigger chặn sửa tin.

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
| `v0.2` | `2026-10-12` | PO chốt hạ tầng chat: giữ công nghệ MVP |
