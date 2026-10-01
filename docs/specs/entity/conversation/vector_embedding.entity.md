# Entity Specification — `vector_embedding` (Kho vector chung)

> **Domain:** Conversation / Infrastructure · **Code:** `backend/src/infrastructure/vectorstore/models.py`, `pgvector_store.py`
>
> Bảng **vector dùng chung** phía sau interface `VectorStore`. Không chứa entity nghiệp vụ có ràng buộc riêng: `document_chunk` ([ENT-407](../knowledge/document_chunk.entity.md)) giữ bảng riêng và vẫn là **nguồn duy nhất cho RAG tài liệu chính hãng** (PRD §9). Bảng này hiện dùng cho lập chỉ mục ngữ nghĩa của tin nhắn (collection `conversation_messages`) và cho các collection tương lai.

## 1. Entity Information

| Field | Value |
| --- | --- |
| Entity ID | `ENT-423` |
| Entity Name | `VectorEmbedding` |
| Business Name | Vector nhúng dùng chung |
| Table | `vector_embedding` |
| Domain | Conversation / Infrastructure |
| Version | `v1.0` |
| Status | `Draft` (đã có trong migration `b7e1c2f34d58`, chưa commit) |
| Owner | Backend Team + AI Team |
| Created Date | `2026-09-29` |
| Updated Date | `2026-09-29` |

---

# 2. Entity Overview

## 2.1 Description

Một dòng cho mỗi mục được lập chỉ mục: nội dung, metadata, vector và mô hình embedding đã sinh vector. `collection` là không gian tên logic (tương đương collection của Chroma).

## 2.2 Business Purpose

Cho phép tìm kiếm ngữ nghĩa (cosine) trong một collection, có lọc theo metadata, qua interface chuẩn `VectorStore` — không phụ thuộc backend (`pgvector` hay `chroma`).

## 2.3 Scope

**In Scope:** nội dung, metadata JSON, vector, mô hình embedding, không gian tên.

**Out of Scope:** chunk tài liệu hãng (`document_chunk`); nội dung gốc của tin nhắn (`chat_message`).

---

# 3. Business Meaning

**Example:** collection `conversation_messages`, `id` = id của một tin nhắn, `metadata` theo hợp đồng ở §6:

```json
{
  "source": "conversation_message",
  "sourceCreatedAt": "2026-09-28T02:14:06Z",
  "conversationId": "5b0f6f3e-…",
  "role": "assistant",
  "sourceMeta": {}
}
```

---

# 4. Identity & Keys

| Field / Composite | Unique | Description |
| --- | ---: | --- |
| `id` (`varchar(255)`) | Yes | PK toàn cục (không chỉ trong collection); ghi lại cùng `id` = ghi đè (idempotent) |

> `id` là **duy nhất toàn bảng**. Mỗi collection phải dùng `id` không đụng nhau — quy ước: `id` của collection `conversation_messages` là `chat_message.id`.

---

# 5. Attributes

| Field | Type | Required | Nullable | Default | Constraints | Description |
| --- | --- | ---: | ---: | --- | --- | --- |
| `id` | `varchar(255)` | Yes | No | - | PK | ID mục |
| `collection` | `varchar(255)` | Yes | No | - | | Không gian tên logic |
| `content` | `text` | Yes | No | - | | Nội dung đã embed |
| `metadata` | `jsonb` | Yes | No | `'{}'` | Đối tượng JSON | Metadata lọc được (`where`) |
| `embedding` | `vector(1024)` | Yes | No | - | pgvector; số chiều = `EMBEDDING_DIMENSIONS` | Vector |
| `embedding_model` | `varchar(128)` | No | Yes | - | Dạng `<provider>:<model>` | Mô hình đã sinh vector |
| `created_at` | `timestamptz` | Yes | No | `now()` | | Thời điểm tạo |

> Trong code thuộc tính là `meta` (SQLModel giữ tên `metadata`); cột DB vẫn là `metadata`.

---

# 6. Metadata Contract, Policy & Builder

`metadata` **không** được ghép tuỳ tiện từ nguồn (tránh lỗi ghi đè khoá lọc và rò dữ liệu — xem BR-ENT-474). Mọi `VectorRecord` đi qua **một builder duy nhất** áp **một policy theo collection**.

## 6.1 Khoá hệ thống (top-level, do builder đặt)

| Key | Type | Bắt buộc | Ý nghĩa |
| --- | --- | ---: | --- |
| `source` | `string` | Yes | Loại nguồn sinh ra vector: `conversation_message`, `document_chunk`, … Dùng để truy nguồn, chọn policy, xoá theo nguồn |
| `sourceCreatedAt` | `string` (ISO-8601) | Yes | Thời điểm **bản ghi nguồn** được tạo (không phải thời điểm embed). Phục vụ retention/anonymize |
| `sourceMeta` | `object` | Yes (có thể `{}`) | Metadata của nguồn **sau khi policy lọc/mask**. Là **một field lồng**, không trải phẳng |

Các khoá lọc riêng theo collection (ví dụ `conversationId`, `role`) cũng do builder đặt ở top-level từ chính bản ghi nguồn, **không** lấy từ `sourceMeta`. Vì khoá hệ thống luôn được đặt tách khỏi `sourceMeta`, dữ liệu nguồn không thể đè `conversationId`/`role`/`source` (BR-ENT-474).

## 6.2 `VectorMetadataPolicy` (theo collection)

Một policy cho mỗi `collection`, định nghĩa **thứ được phép lưu** và cách khử nhạy cảm:

- `filter_keys`: whitelist khoá của `sourceMeta` được giữ. **Mặc định của `conversation_messages`: rỗng** — không giữ `citations`, `tool_calls`, `refs`, `intent`… vì không cần cho semantic recall và mang rủi ro rò cao nhất. `sourceMeta = {}`.
- `mask`: che theo mẫu trên `content` và trên các giá trị `sourceMeta` còn lại — VIN, SĐT, email, CCCD, biển số (thống nhất với FF BR-616/BR-617).
- `anonymize`: với collection dùng cho eval, băm một chiều các định danh trước khi lưu.

Đổi policy (thêm/bớt khoá) không đổi schema DB, nhưng để nhất quán nên **re-index** collection liên quan.

## 6.3 Builder / Factory

`VectorRecordBuilder` là nơi **duy nhất** dựng `VectorRecord`:

```text
VectorRecordBuilder.from_message(message, policy)      -> VectorRecord   # source = conversation_message
VectorRecordBuilder.from_document_chunk(chunk, policy) -> VectorRecord   # nếu sau này dùng chung bảng
```

Builder chịu trách nhiệm: đặt `id`, `content`; đặt khoá hệ thống (`source`, `sourceCreatedAt`) và khoá lọc của collection; áp policy để dựng `sourceMeta`; **không** để nguồn ghi đè khoá hệ thống. `TASK-MSG-001` và mọi nơi khác gọi builder, không tự tạo dict metadata.

---

# 7. Relationships

Không có FK. Liên kết với thực thể nguồn là **mềm** qua `id`, `source` và `metadata`:

| Collection | `id` tham chiếu | Khoá lọc top-level | `sourceMeta` mặc định |
| --- | --- | --- | --- |
| `conversation_messages` | `chat_message.id` | `conversationId`, `role` | `{}` (policy rỗng — §6.2) |

---

# 8. Entity Lifecycle / State

Không có trạng thái. Ghi lại cùng `id` → cập nhật (upsert). Xoá theo `id` hoặc theo cả collection.

---

# 9. Business Rules & Constraints

## BR-ENT-470 — Một mô hình embedding cho mỗi collection

**Rule:** Mọi vector trong cùng collection phải do **cùng một mô hình** sinh ra (cùng số chiều chưa đủ để so sánh cosine). Đổi mô hình ⇒ embed lại toàn bộ collection.

**Expected Behavior:** `embedding_model` luôn được ghi (lấy từ `identity` của engine khi `VectorRecord` không nêu).

## BR-ENT-471 — Số chiều cố định theo cấu hình

**Rule:** `vector(1024)` khớp `EMBEDDING_DIMENSIONS`. Đổi số chiều ⇒ migration dựng lại cột và chỉ mục (như BR-ENT-410 của `document_chunk`).

## BR-ENT-472 — Ghi idempotent

**Rule:** Upsert theo `id` (`ON CONFLICT (id) DO UPDATE`), nên retry của worker không tạo trùng.

## BR-ENT-473 — Xoá đồng bộ với nguồn

**Rule:** Khi thực thể nguồn bị xoá (ví dụ xoá hội thoại), các dòng vector tương ứng phải bị xoá (`delete(collection, ids)`), vì bảng này không có FK cascade.

## BR-ENT-474 — Metadata qua builder + policy, không trải phẳng nguồn

**Rule:** `metadata` chỉ được dựng bởi `VectorRecordBuilder` (§6.3). Khoá hệ thống (`source`, `sourceCreatedAt`) và khoá lọc theo collection (`conversationId`, `role`) do builder đặt ở top-level từ bản ghi nguồn; metadata của nguồn nằm gọn trong `sourceMeta` sau khi `VectorMetadataPolicy` lọc/mask.

**Condition:** mọi lần tạo `VectorRecord`.

**Expected Behavior:** cấm mẫu `{**source_meta}` trải phẳng vào top-level. Nhờ đó nguồn không thể ghi đè khoá lọc phân quyền, và dữ liệu ngoài whitelist (trích dẫn, tool args, PII) không lọt vào vector store.

---

# 10. Data Integrity

```sql
CREATE INDEX ix_vector_embedding_collection ON vector_embedding (collection);
CREATE INDEX ix_vector_embedding_hnsw ON vector_embedding
    USING hnsw (embedding vector_cosine_ops);
-- extension: CREATE EXTENSION IF NOT EXISTS vector;
```

Lọc metadata dùng toán tử `metadata @> :where::jsonb`.

---

# 11. Index & Query Requirements

| Query | Fields | Frequency | Required Index |
| --- | --- | --- | --- |
| Tìm ngữ nghĩa trong collection | `collection`, `embedding` (cosine) | Thấp (tuỳ chọn) | HNSW `vector_cosine_ops` |
| Lọc theo metadata (vd `conversation_id`) | `metadata @>` | Thấp | Cân nhắc GIN trên `metadata` khi dữ liệu lớn `[Đề xuất]` |
| Đếm / xoá theo collection | `collection` | Rất thấp | `ix_vector_embedding_collection` |

`score = 1 − cosine_distance`, trong `[0, 1]`, càng cao càng giống.

---

# 12. Ownership & Authorization

Chỉ backend/worker đọc và ghi; **không** expose trực tiếp qua API. Mọi API tìm kiếm phải ép điều kiện sở hữu (ví dụ `conversation_id` thuộc chủ xe) **trước** khi truy vấn vector, vì bảng không tự kiểm quyền.

---

# 15. Data Sensitivity & Security

`content` có thể chứa nội dung tin nhắn của chủ xe (Personal Data): không log, xoá theo BR-ENT-473, chặn anon key (không có policy — PRD §9.1).

---

# 16. Retention & Deletion

Theo dữ liệu nguồn. Hội thoại quá hạn 180 ngày (PQ-09) bị xoá thì vector của hội thoại đó cũng bị xoá.

---

# 21. Open Questions

| ID | Question | Owner | Status |
| --- | --- | --- | --- |
| `Q-616` | Gộp `document_chunk` vào bảng này hay giữ riêng? | AI Team | `[Đề xuất]` giữ riêng — có FK và ràng buộc riêng (ENT-407) |
| `Q-617` | Thêm GIN trên `metadata` khi có nhiều collection? | Backend | `[Đề xuất]` chỉ khi đo chậm |

---

# 22. Change Log

| Version | Date | Author | Changes |
| --- | --- | --- | --- |
| `v1.0` | `2026-09-29` | Team 4 Người | Đặc tả theo code hiện tại (`VectorEmbedding`) |
