# Entity Specification — `chat_message` (Tin nhắn chat)

## 1. Entity Information

| Field | Value |
| --- | --- |
| Entity ID | `ENT-422` |
| Entity Name | `ChatMessage` |
| Business Name | Tin nhắn chat |
| Table | `chat_message` |
| Domain | Conversation (nền tảng dùng chung — [platform API](../../platform/conversation-messaging.api.md)) |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-09-28` |
| Updated Date | `2026-09-28` |

## 2. Entity Overview

### 2.1 Description

Một tin nhắn **hoàn chỉnh** trong hội thoại: của chủ xe, của trợ lý, hoặc kết quả một tool call. Bất biến sau khi lưu.

### 2.2 Business Purpose

Lịch sử chat; bằng chứng trả lời (trích dẫn, tool, trace); điểm truy ngược của booking/báo giá; nguồn dữ liệu eval (FF BR-602, BR-603, BR-607).

### 2.3 Scope

**In Scope:** nội dung, vai trò, thứ tự, trích dẫn (bản chụp), tool đã gọi, tham chiếu tới booking/báo giá, trace, mã chống trùng.

**Out of Scope:** tin nhắn dang dở đang stream (không lưu); trạng thái Agent (§0.3); vector của tin nhắn (nằm ở `vector_embedding` — [ENT-423](./vector_embedding.entity.md), tuỳ chọn).

## 3. Business Meaning

**Definition:** một lượt nói. Ba loại (`role`):

| Role | Ý nghĩa |
| --- | --- |
| `user` | Chủ xe gửi |
| `assistant` | Câu trả lời hoàn chỉnh của trợ lý; có thể kèm yêu cầu gọi tool |
| `tool` | Kết quả một tool call, để phát lại đúng ngữ cảnh (không hiển thị cho chủ xưởng, không đưa vào tìm kiếm) |

Không lưu `system` (prompt hệ thống nằm trong code/cấu hình).

## 4. Identity & Keys

| Field / Composite | Unique | Description |
| --- | ---: | --- |
| `id` (`uuid`) | Yes | PK |
| `seq` | Yes | Thứ tự toàn cục, tăng dần (phân trang keyset) |
| `conversation_id`, `client_message_id` (khi `role = user`) | Yes | Chống gửi trùng (BR-ENT-465) — unique một phần |

## 5. Attributes

| Field | Type | Required | Nullable | Default | Constraints | Description |
| --- | --- | ---: | ---: | --- | --- | --- |
| `id` | `uuid` | Yes | No | `uuid4` | PK | ID tin nhắn |
| `conversation_id` | `uuid` | Yes | No | - | FK → `conversation.id` `ON DELETE CASCADE` | Hội thoại |
| `seq` | `bigint` | Yes | No | identity | `GENERATED ALWAYS AS IDENTITY`; unique | Thứ tự; lớn hơn nghĩa là mới hơn |
| `role` | `chat_message_role_enum` | Yes | No | - | `user / assistant / tool` | Vai trò |
| `content` | `text` | Yes | No | - | Không rỗng (trừ `assistant` chỉ gọi tool, xem BR-ENT-466) | Nội dung |
| `client_message_id` | `uuid` | No | Yes | - | Chỉ khi `role = user` | Mã do client sinh, chống gửi trùng |
| `citations` | `jsonb` | Yes | No | `'[]'` | Mảng; xem §6.1 | Trích dẫn — **bản chụp** tại thời điểm trả lời |
| `tool_calls` | `jsonb` | Yes | No | `'[]'` | Mảng; xem §6.2 | Tool assistant đã gọi (khi `assistant`) |
| `tool_call_id` | `varchar(64)` | No | Yes | - | Bắt buộc khi `role = tool` | Khớp `tool_calls[].id` |
| `tool_name` | `varchar(64)` | No | Yes | - | Bắt buộc khi `role = tool` | Tên tool |
| `refs` | `jsonb` | Yes | No | `'{}'` | Xem §6.3 | Id booking/báo giá được tạo bởi tin nhắn này |
| `card` | `jsonb` | No | Yes | - | `[Đề xuất]` | Thẻ UI có cấu trúc (tóm tắt đặt lịch, dự toán); định nghĩa ở AI-003/004/005 |
| `intent` | `varchar(50)` | No | Yes | - | | Ý định đã nhận diện (AI-001 `INT-*`) |
| `agent_run_id` | `uuid` | No | Yes | - | | Lượt chạy của Agent |
| `trace_id` | `varchar(64)` | No | Yes | - | | Trace id của phiên/lượt (PRD §8 Quan sát) |
| `search_vector` | `tsvector` | No | Yes | - | Sinh tự động từ `content` khi `role IN (user, assistant)` | Tìm từ khoá (BR-ENT-467) |
| `embedded` | `boolean` | Yes | No | `false` | | Đã lập chỉ mục vector chưa; chỉ dùng khi bật lập chỉ mục ngữ nghĩa (BR-ENT-469) |
| `created_at` | `timestamptz` | Yes | No | `now()` | | Thời điểm lưu |

> Bảng **append-only**: không có `updated_at`; không UPDATE/DELETE lẻ (chỉ xoá theo hội thoại).

## 6. Attribute Details

### 6.1 `citations` — bản chụp trích dẫn

Mỗi phần tử:

| Key | Type | Required | Description |
| --- | --- | ---: | --- |
| `chunkId` | `uuid` | Yes | `document_chunk.id` **lúc trả lời** (có thể không còn tồn tại sau re-ingest — BR-ENT-409) |
| `documentId` | `uuid` | Yes | `official_document.id` |
| `title` | `string` | Yes | Tên tài liệu |
| `version` | `string` | Yes | Phiên bản tài liệu |
| `documentType` | `string` | Yes | `owner_manual / maintenance_manual / warranty_policy / service_bulletin` |
| `pageNumber` | `integer` | No | Trang nguồn |
| `snippet` | `string` | Yes | Đoạn trích hiển thị (≤ 500 ký tự) |
| `score` | `number` | No | Điểm truy hồi, phục vụ eval |

**Business Meaning:** giữ nguyên bằng chứng ngay cả khi tài liệu được ingest lại; **không có FK** để không chặn re-ingest.

### 6.2 `tool_calls`

Mỗi phần tử: `{ "id": "call_1", "name": "search_official_documents", "args": { ... } }`. `args` **không** chứa VIN, CCCD (FF BR-617). Tên tool theo AI-001/AI-002 (`TOOL-1xx`, `TOOL-2xx`).

### 6.3 `refs`

Ví dụ: `{ "bookingId": "…", "quoteId": "…" }`. Chỉ ghi khi tin nhắn này **tạo** đối tượng (ví dụ tin trợ lý sau khi chủ xe bấm Xác nhận). Khoá không có nghĩa là không tạo.

## 7. Relationships

| Related Entity | Relationship | Cardinality | Description |
| --- | --- | --- | --- |
| `conversation` (ENT-421) | belongs to | N:1 | Hội thoại chứa |
| `booking` (ENT-402) | referenced by | 1:N | `booking.source_message_id` — tin nhắn xác nhận của chủ xe |
| `quote` (ENT-410) | referenced by | 1:N | `quote.source_message_id` |
| `document_chunk` (ENT-407) | cites (mềm) | N:N | Qua `citations`, không FK |

## 8. Entity Lifecycle / State

Không có trạng thái; bất biến.

## 9. Business Rules & Constraints

### BR-ENT-460 — Liên kết booking/báo giá về tin nhắn

**Rule:** `booking.source_message_id` và `quote.source_message_id` trỏ tới tin nhắn `role = user` là **lời xác nhận** dẫn tới việc tạo (AC-F4-06). `NULL` khi tạo từ UI hoặc khi tin nhắn đã bị xoá.

**Expected Behavior:** Service tạo booking/báo giá nhận `source_message_id` từ ngữ cảnh lượt chat; thuộc cùng chủ xe (`conversation.user_id = booking.user_id`).

### BR-ENT-464 — Đoạn hội thoại cho chủ xưởng

**Rule:** Từ `source_message_id` xác định `conversation_id`; đoạn hội thoại = tối đa `CHAT_EXCERPT_MAX_MESSAGES` `[Đề xuất: 20]` tin `role IN (user, assistant)` có `seq ≤ seq của tin nguồn`, đảo về thứ tự thời gian.

### BR-ENT-465 — Chống gửi trùng

**Rule:** Unique một phần `(conversation_id, client_message_id) WHERE role = 'user' AND client_message_id IS NOT NULL`.

### BR-ENT-466 — Ràng buộc theo vai trò

**Rule:**

- `role = user`: `content` không rỗng; `citations = []`, `tool_calls = []`.
- `role = assistant`: `content` không rỗng **hoặc** `tool_calls` không rỗng.
- `role = tool`: có `tool_call_id`, `tool_name`; `content` là kết quả (chuỗi/JSON) đã lược bớt VIN/CCCD.

### BR-ENT-467 — Tìm từ khoá

**Rule:** `search_vector` chỉ có cho `user` và `assistant`. Chuẩn hoá không phân biệt hoa thường và dấu tiếng Việt (FF BR-615). Ví dụ: `to_tsvector('simple', immutable_unaccent(content))` `[Đề xuất — technical design]`.

### BR-ENT-469 — Lập chỉ mục ngữ nghĩa là tuỳ chọn

**Rule:** Khi `CONVERSATION_SEMANTIC_INDEX_ENABLED = true`, sau khi lưu, tin `user`/`assistant` được embed và ghi vào `vector_embedding` (collection `conversation_messages`, `id = chat_message.id`); worker đặt `embedded = true`. Tắt cờ → `embedded` luôn `false` và không có vector. Xoá hội thoại phải xoá cả vector tương ứng (BR-ENT-462).

**Expected Behavior:** lập chỉ mục là hiệu ứng phụ **không** chặn việc lưu và publish; lỗi embedding không làm mất tin nhắn.

### BR-ENT-468 — Thứ tự bằng `seq`

**Rule:** Thứ tự và phân trang dựa trên `seq`, không dựa trên `created_at` (có thể trùng thời điểm).

## 10. Data Integrity

```sql
CREATE TYPE chat_message_role_enum AS ENUM ('user', 'assistant', 'tool');

CHECK (role <> 'user'      OR (length(content) > 0
                               AND jsonb_array_length(citations) = 0
                               AND jsonb_array_length(tool_calls) = 0))
CHECK (role <> 'tool'      OR (tool_call_id IS NOT NULL AND tool_name IS NOT NULL))
CHECK (role <> 'assistant' OR (length(content) > 0 OR jsonb_array_length(tool_calls) > 0))
CHECK (jsonb_typeof(citations) = 'array' AND jsonb_typeof(tool_calls) = 'array' AND jsonb_typeof(refs) = 'object')

CREATE UNIQUE INDEX ux_chat_message_client_id
    ON chat_message (conversation_id, client_message_id)
    WHERE role = 'user' AND client_message_id IS NOT NULL;
```

> `content` luôn `NOT NULL`; tin `assistant` chỉ gọi tool dùng chuỗi rỗng `''`.

## 11. Index & Query Requirements

| Query | Fields | Frequency | Required Index |
| --- | --- | --- | --- |
| Tải 50 tin mới nhất / trang cũ hơn | `conversation_id`, `seq DESC` | Rất cao | `ix_chat_message_conversation_seq` |
| Khôi phục bản gửi trùng | `conversation_id`, `client_message_id` | Cao | `ux_chat_message_client_id` |
| Tìm từ khoá trong lịch sử của chủ xe | `search_vector` (join `conversation.user_id`) | Thấp | GIN trên `search_vector` |
| Đoạn hội thoại của booking | PK theo `source_message_id`, rồi `conversation_id`, `seq` | Thấp | Chỉ mục trên; `ix_booking_source_message`, `ix_quote_source_message` |
| Xuất ẩn danh theo khoảng thời gian | `created_at` | Rất thấp (job) | `ix_chat_message_created_at` |

```sql
CREATE INDEX ix_chat_message_conversation_seq ON chat_message (conversation_id, seq DESC);
CREATE INDEX ix_chat_message_search ON chat_message USING GIN (search_vector);
CREATE INDEX ix_chat_message_created_at ON chat_message (created_at);
```

Mục tiêu hiệu năng: tải 50 tin ≤ 300 ms p90 (PRD §8).

## 12. Ownership & Authorization

| Actor / Role | Read | Create | Update | Delete |
| --- | ---: | ---: | ---: | ---: |
| Chủ xe (hội thoại của mình) | ✅ | ✅ (qua backend, không ghi trực tiếp) | ❌ | ✅ (cả hội thoại) |
| Chủ xưởng | ✅ (đoạn theo BR-ENT-464, xưởng mình) | ❌ | ❌ | ❌ |
| Agent / Backend | ✅ | ✅ | ❌ | ❌ |
| Job dọn / xuất | ✅ / ❌ | ❌ | ❌ | ✅ |

**Ownership Rule:** tin nhắn thuộc chủ xe của hội thoại. Backend là nơi **duy nhất** ghi (FF BR-602); client không ghi trực tiếp.

## 13. Audit Fields

Chỉ `created_at`. Truy vết bằng `trace_id`, `agent_run_id`.

## 14. Data Source & Ownership

Nguồn duy nhất: backend EV Care. Trích dẫn sao chép từ kho tài liệu do AI Team sở hữu.

## 15. Data Sensitivity & Security

| Field | Classification | Notes |
| --- | --- | --- |
| `content` | Personal Data | Có thể chứa dữ liệu nhạy cảm chủ xe tự gõ; không log nội dung |
| `citations.snippet` | Business Data | Trích tài liệu công khai của hãng |
| `tool_calls.args`, tool `content` | Business / Vehicle Data | Không chứa VIN, CCCD (BR-ENT-466) |
| `trace_id`, `agent_run_id` | Technical | Không nhạy cảm |

## 16. Retention & Deletion

**Retention:** theo hội thoại (BR-ENT-463). **Deletion:** cascade khi xoá hội thoại. Bản ẩn danh cho eval nằm ngoài bảng này (kho riêng của AI Team) và giữ lâu hơn (PQ-09).

## 17. Example Data

```json
[
  {
    "id": "a1a1a1a1-0000-4000-8000-000000000001",
    "conversation_id": "5b0f6f3e-3d0c-4a0e-9a35-0f6f7a1d2c11",
    "seq": 1001,
    "role": "user",
    "content": "Mốc 12.000 km cần làm gì, cái nào được miễn phí?",
    "client_message_id": "3f0d9c1e-6d7e-4f8a-9d0b-2a2b3c4d5e6f",
    "citations": [],
    "tool_calls": [],
    "refs": {},
    "created_at": "2026-09-28T02:14:02Z"
  },
  {
    "id": "a1a1a1a1-0000-4000-8000-000000000002",
    "conversation_id": "5b0f6f3e-3d0c-4a0e-9a35-0f6f7a1d2c11",
    "seq": 1004,
    "role": "assistant",
    "content": "Theo sổ tay bảo dưỡng VF6, mốc 12.000 km gồm: kiểm tra phanh, thay lọc gió điều hoà …",
    "citations": [
      {
        "chunkId": "0c7e1d52-5f43-4a53-8f3a-9a1b2c3d4e5f",
        "documentId": "9d2f0c11-7a8b-4c3d-b5e6-1a2b3c4d5e6f",
        "title": "Sổ tay bảo dưỡng VF6",
        "version": "2.1",
        "documentType": "maintenance_manual",
        "pageNumber": 42,
        "snippet": "Mốc 12.000 km: kiểm tra hệ thống phanh, thay lọc gió điều hoà …"
      }
    ],
    "tool_calls": [],
    "refs": {},
    "intent": "MAINTENANCE_ITEMS",
    "agent_run_id": "7c1e2d3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
    "trace_id": "tr-20260928-0214-abc123",
    "created_at": "2026-09-28T02:14:06Z"
  }
]
```

## 18. API References

| API | Vai trò với entity |
| --- | --- |
| `API-CONV-001` … `API-CONV-006` (tạo / liệt kê / tải / tìm từ khoá / xoá hội thoại, tìm ngữ nghĩa) | Đọc/ghi qua [platform API](../../platform/conversation-messaging.api.md) |
| `API-MSG-001` `WS /conversations/{id}/stream` | Phát tin nhắn mới theo thời gian thực |
| `MessageService.append` (nội bộ) | Nơi **duy nhất** ghi `chat_message` |
| `API-CHAT-004` (F4) `POST /conversations/{id}/messages` (SSE) | Use case F4 gọi `MessageService.append` cho tin `user`, `assistant`, `tool` |
| `API-CHAT-007` / `API-CHAT-008` (F4) | Chủ xưởng đọc đoạn liên quan |

## 19. Related Entities

| Entity | Relationship | Reference |
| --- | --- | --- |
| `vehicle_user` (ENT-001) | owns `conversation` | [vehicle_user](../identity/vehicle_user.entity.md) |
| `user_vehicle` (ENT-003) | về xe | [user_vehicle](../vehicle/user_vehicle.entity.md) |
| `booking` (ENT-402) | tham chiếu `chat_message` | [booking](../maintenance/booking.entity.md) |
| `quote` (ENT-410) | tham chiếu `chat_message` | [quote](../maintenance/quote.entity.md) |
| `official_document` (ENT-406), `document_chunk` (ENT-407) | nguồn của `citations` (mềm) | [knowledge](../knowledge/document_chunk.entity.md) |

## 20. Related Functional Specifications

- [us-025 FF — Chat RAG & lưu trữ hội thoại](../../sprint-2/feature-functional/us-025-sprint-2-spec.ff.md)
- [AI-001](../../ai-agent/ai-001-sprint-2-spec.agent.md), [AI-002](../../ai-agent/ai-002-sprint-2-spec.agent.md)

---

# 21. Open Questions

| ID | Question | Owner | Status |
| --- | --- | --- | --- |
| `Q-611` | `booking.source_message_id` / `quote.source_message_id`: cột FK hay bảng liên kết riêng? | Backend | `[Đề xuất]` cột FK — đơn giản, cùng transaction (BR-ENT-460) |
| `Q-612` | Có cần `card` không, hay thẻ UI tính lại từ `refs`? | AI Team | `[Đề xuất]` giữ `card` |
| `Q-613` | Tìm từ khoá tiếng Việt: `simple` + bỏ dấu đủ chưa? | Backend | `[Đề xuất]` đủ cho MVP |
| `Q-614` | Cột `token_usage`? | AI Team | `[Đề xuất]` không, để trace |
| Tham chiếu | Q-604 (lập chỉ mục ngữ nghĩa) | Tech Lead | Xem [FF §24](../../sprint-2/feature-functional/us-025-sprint-2-spec.ff.md#24-open-questions) |

---

# 22. Change Log

| Version | Date | Author | Changes |
| --- | --- | --- | --- |
| `v1.0` | `2026-09-29` | Team 4 Người | Tách từ `us-025` entity spec thành entity nền tảng; thay bảng PROVISIONAL `message`; thêm `embedded` (lập chỉ mục tuỳ chọn) |

