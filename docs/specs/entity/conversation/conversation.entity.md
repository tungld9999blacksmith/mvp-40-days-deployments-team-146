# Entity Specification — `conversation` (Hội thoại)

## 1. Entity Information

| Field | Value |
| --- | --- |
| Entity ID | `ENT-421` |
| Entity Name | `Conversation` |
| Business Name | Hội thoại |
| Table | `conversation` |
| Domain | Conversation (nền tảng dùng chung — [platform API](../../platform/conversation-messaging.api.md)) |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-09-28` |
| Updated Date | `2026-09-28` |

## 2. Entity Overview

### 2.1 Description

Một cuộc trò chuyện giữa một chủ xe và Agent, gắn với một xe. Nhóm các `chat_message` theo thứ tự.

### 2.2 Business Purpose

Đơn vị nền tảng để tải lại lịch sử, liệt kê theo xe, kiểm soát quyền đọc, xoá theo yêu cầu và gom tin nhắn theo phiên. Dùng chung cho mọi use case có chat (F4, F5, F5b, F6 — xem bảng use case ở [platform API §0.2](../../platform/conversation-messaging.api.md)); quy tắc nghiệp vụ tham chiếu FF F4 (BR-601, BR-604, BR-605, BR-608).

### 2.3 Scope

**In Scope:** chủ sở hữu, xe, tiêu đề, thời điểm tin cuối.

**Out of Scope:** nội dung tin nhắn (`chat_message`); trạng thái Agent (checkpointer, §0.3); trạng thái lượt đang chạy (Redis).

## 3. Business Meaning

**Definition:** chuỗi tin nhắn liên tục về một xe. Chủ xe có thể có nhiều hội thoại cho cùng một xe (nút "Cuộc trò chuyện mới").

**Example:** "Mốc 12.000 km cần làm gì?" — hội thoại của chủ xe #17 về VF6 `f2c1…`, 14 tin nhắn.

## 4. Identity & Keys

| Field / Composite | Unique | Description |
| --- | ---: | --- |
| `id` (`uuid`) | Yes | PK, sinh ở app bằng `uuid4` |

## 5. Attributes

| Field | Type | Required | Nullable | Default | Constraints | Description |
| --- | --- | ---: | ---: | --- | --- | --- |
| `id` | `uuid` | Yes | No | `uuid4` | PK | ID hội thoại; đồng thời là `thread_id` của checkpointer |
| `user_id` | `integer` | Yes | No | - | FK → `vehicle_user.user_id` `ON DELETE CASCADE` | Chủ xe sở hữu |
| `user_vehicle_id` | `uuid` | Yes | No | - | FK → `user_vehicle.id` `ON DELETE CASCADE` | Xe của hội thoại |
| `title` | `varchar(255)` | No | Yes | - | | Tiêu đề; mặc định cắt 60 ký tự đầu của câu hỏi đầu tiên |
| `last_message_at` | `timestamptz` | Yes | No | `now()` | | Thời điểm tin nhắn cuối; dùng sắp xếp và tính hạn lưu giữ |
| `created_at` | `timestamptz` | Yes | No | `now()` | | |
| `updated_at` | `timestamptz` | Yes | No | `now()` | | |

> `user_id` là `integer` khớp `vehicle_user.user_id`. Bản PROVISIONAL dùng `varchar(64)` không FK — đổi (xem §Migration).

## 7. Relationships

| Related Entity | Relationship | Cardinality | Description |
| --- | --- | --- | --- |
| `vehicle_user` (ENT-001) | belongs to | N:1 | Chủ xe |
| `user_vehicle` (ENT-003) | belongs to | N:1 | Xe |
| `chat_message` (ENT-422) | has | 1:N | Tin nhắn; xoá hội thoại xoá toàn bộ tin nhắn |

## 8. Entity Lifecycle / State

Không có trạng thái. Tồn tại đến khi bị xoá (chủ xe yêu cầu hoặc quá hạn lưu giữ) — **hard delete** (BR-ENT-462).

## 9. Business Rules & Constraints

### BR-ENT-461 — Hội thoại thuộc đúng chủ xe của xe

**Rule:** `conversation.user_id` phải bằng `user_vehicle.user_id` của `user_vehicle_id`.

**Expected Behavior:** kiểm tra ở service khi tạo; không đổi `user_id` và `user_vehicle_id` sau khi tạo.

### BR-ENT-462 — Xoá hoàn toàn

**Rule:** Xoá hội thoại xoá: các `chat_message` (`ON DELETE CASCADE`), các bản ghi checkpointer có `thread_id = id`. Cột `booking.source_message_id` tự về `NULL`.

**Expected Behavior:** thực hiện trong một transaction cho dữ liệu Postgres; bản ghi checkpointer bị xoá cùng transaction (cùng database).

### BR-ENT-463 — Thời hạn lưu giữ

**Rule:** Hội thoại có `last_message_at < now() − CHAT_RETENTION_DAYS` (mặc định 180, PQ-09) bị xoá theo BR-ENT-462 bởi job dọn.

## 10. Data Integrity

```sql
-- Danh sách hội thoại của chủ xe theo xe, mới nhất trước
CREATE INDEX ix_conversation_user_vehicle_last
    ON conversation (user_id, user_vehicle_id, last_message_at DESC);
-- Job dọn quá hạn
CREATE INDEX ix_conversation_last_message_at ON conversation (last_message_at);
```

## 11. Index & Query Requirements

| Query | Fields | Frequency | Required Index |
| --- | --- | --- | --- |
| Hội thoại gần nhất của xe | `user_id`, `user_vehicle_id`, `last_message_at DESC` | Rất cao (mỗi lần mở Chat) | `ix_conversation_user_vehicle_last` |
| Danh sách hội thoại của chủ xe | `user_id`, `last_message_at DESC` | Cao | Cùng chỉ mục (tiền tố `user_id`) |
| Tìm hội thoại quá hạn | `last_message_at` | Thấp (job) | `ix_conversation_last_message_at` |

## 12. Ownership & Authorization

| Actor / Role | Read | Create | Update | Delete |
| --- | ---: | ---: | ---: | ---: |
| Chủ xe (của mình) | ✅ | ✅ | ✅ (đổi `title` — `[Đề xuất]` chưa có API) | ✅ |
| Chủ xưởng | ❌ | ❌ | ❌ | ❌ |
| Job dọn | ✅ | ❌ | ❌ | ✅ |

Chủ xưởng chỉ đọc `chat_message` qua API đoạn hội thoại (BR-ENT-464), không đọc `conversation`.

## 14. Data Source & Ownership

Nguồn duy nhất: backend EV Care. Không đồng bộ từ hãng.

## 15. Data Sensitivity & Security

| Field | Classification | Notes |
| --- | --- | --- |
| `title` | Personal Data (nội dung câu hỏi) | Không log; không đưa vào bản xuất ẩn danh |
| `user_id`, `user_vehicle_id` | Personal / Vehicle Data | Băm một chiều khi xuất ẩn danh |

Bảng chặn truy cập bằng anon key (không có policy); mọi truy cập qua backend (PRD §9.1).

## 16. Retention & Deletion

**Retention:** 180 ngày kể từ `last_message_at` (PQ-09). **Deletion:** Hard delete (BR-ENT-462).

## 17. Example Data

```json
{
  "id": "5b0f6f3e-3d0c-4a0e-9a35-0f6f7a1d2c11",
  "user_id": 17,
  "user_vehicle_id": "f2c1a9e0-8b5d-4a52-a1de-1a2b3c4d5e6f",
  "title": "Mốc 12.000 km cần làm gì, cái nào được miễn phí?",
  "last_message_at": "2026-09-28T02:15:41Z",
  "created_at": "2026-09-28T02:14:02Z",
  "updated_at": "2026-09-28T02:15:41Z"
}
```

---

# 21. Open Questions

| ID | Question | Owner | Status |
| --- | --- | --- | --- |
| `Q-615` | Cho phép hội thoại không gắn xe (`user_vehicle_id` NULL) cho use case sau này (ví dụ chat chung với xưởng)? | PO | `[Đề xuất]` chưa — MVP mọi hội thoại thuộc một xe |
| Tham chiếu | Q-605 (nhiều hội thoại/xe) | PO | Xem [FF §24](../../sprint-2/feature-functional/us-025-sprint-2-spec.ff.md#24-open-questions) |

---

# 22. Change Log

| Version | Date | Author | Changes |
| --- | --- | --- | --- |
| `v1.0` | `2026-09-29` | Team 4 Người | Tách từ `us-025` entity spec thành entity nền tảng; thay bảng PROVISIONAL `conversation` |

