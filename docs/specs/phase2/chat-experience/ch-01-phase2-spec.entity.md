# Entity Specification — Gợi ý một chạm

> Entity cho Feature `FEAT-P2-CH01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ch-01-phase2-spec.ff.md). **API:** [API Spec](ch-01-phase2-spec.api.md).
>
> **Nguyên tắc:** danh mục chip (ý định, tham số, nhãn) là **code**, không phải dữ liệu do LLM sinh (FF §21). Chip đã phát cho một tin nhắn được chụp vào tin nhắn đó để xác định chip nào còn hiệu lực. Trạng thái luồng đặt lịch nhiều bước nằm ở một bảng nhỏ theo hội thoại để cả chip lẫn câu gõ tự do cùng cập nhật (BR-CH01-03).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-CH01` — CH-01 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend + AI Team |
| Created Date | `2026-10-12` |
| Related FF | [ch-01-phase2-spec.ff.md](ch-01-phase2-spec.ff.md) |
| Related API | [ch-01-phase2-spec.api.md](ch-01-phase2-spec.api.md) |
| Related FE | [ch-01-phase2-spec.fe.md](ch-01-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-422` | `ChatMessage` | `chat_message` | Có sẵn — **thêm cột** | `chips` (jsonb), `chip_action` (jsonb) |
| `ENT-CH01-01` | `ConversationFlowState` | `conversation_flow_state` | **Mới** | Bước hiện tại của luồng đặt lịch một chạm |
| `ENT-CH01-02` | `ChipIntentStat` | `chip_intent_stat` | **Mới** | Top ý định 30 ngày, cập nhật hằng tuần (BR-CH01-04) |
| `ENT-475` | `BookingProposal` | `booking_proposal` | Có sẵn (us-061) — thêm giá trị `source` | `CHAT_CHIP` |
| `ENT-PL03-01` | `ProductEvent` | `product_event` | PL-03 | Sự kiện `chip_shown`, `chip_clicked` (M-04) |

---

# 2. `chat_message` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `chips` | `jsonb` | No | `'[]'` | Chip phát kèm tin **trợ lý** này (§2.1). Tin `user` / `tool` luôn `[]` |
| `chip_action` | `jsonb` | Yes | `NULL` | Trên tin **user** sinh ra do bấm chip: `{ "chipId", "intent", "params", "sourceMessageId" }`. `NULL` khi gõ tự do |

```sql
ALTER TABLE chat_message ADD CONSTRAINT ck_chat_message_chips_assistant
  CHECK (role = 'assistant' OR chips = '[]'::jsonb);
ALTER TABLE chat_message ADD CONSTRAINT ck_chat_message_chip_action_user
  CHECK (chip_action IS NULL OR role = 'user');
-- Một chip chỉ được dùng một lần (AC-CH01-03).
CREATE UNIQUE INDEX ux_chat_message_chip_used ON chat_message ((chip_action->>'chipId'))
  WHERE chip_action IS NOT NULL;
```

## 2.1 Phần tử `chips[]`

```json
{ "chipId": "c_9f1e…", "intent": "booking.pick_slot", "params": { "optionId": "o1…" },
  "label": "08:00 · còn 1 chỗ", "primary": true, "source": "CONTEXT", "kind": "ACTION" }
```

| Trường | Ý nghĩa |
|---|---|
| `chipId` | `c_` + 12 ký tự ngẫu nhiên; duy nhất toàn hệ thống |
| `intent` | Mã trong danh mục `chips/catalog.py` (API §3) |
| `params` | Theo schema của ý định; chỉ id / mã, không dữ liệu cá nhân |
| `label` | ≤ 40 ký tự, tiếng Việt (BR-CH01-09) |
| `primary` | Đúng một chip `true` mỗi tin khi có bước tiếp theo rõ (BR-CH01-01) |
| `source` | `OPENING`, `CONTEXT`, `STATUS` |
| `kind` | `ACTION` (gửi ý định), `LINK` (mở màn: bản đồ, widget lịch, chỉ đường), `TYPE` ("Gõ câu hỏi": chỉ đưa con trỏ vào ô nhập) |

**Hiệu lực (BR-CH01 §13):** chip `active` khi thuộc tin trợ lý **mới nhất** của hội thoại và chưa được dùng; mọi chip khác là `stale`. Không lưu trạng thái — suy ra khi đọc.

---

# 3. `conversation_flow_state` (ENT-CH01-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `conversation_id` | `uuid` | No | — | PK, FK `conversation.id` `ON DELETE CASCADE` |
| `flow` | `varchar(16)` | No | — | `BOOKING` (Phase 2 chỉ có luồng này) |
| `step` | `varchar(16)` | No | — | `CONFIRM_HABIT`, `WHERE`, `WORKSHOP`, `WHEN`, `SLOT`, `SUMMARY`, `DONE`, `ABANDONED` |
| `slots` | `jsonb` | No | `'{}'` | Ràng buộc đã thu thập: `{ "anchor": "USUAL_WORKSHOP", "workshopId": "…", "window": { "date": "2026-10-17", "part": "MORNING" }, "runId": "…", "proposalId": "…" }` |
| `version` | `integer` | No | `1` | Khoá lạc quan (chip và lượt gõ tự do cùng ghi) |
| `started_at` | `timestamptz` | No | `now()` | Mốc bắt đầu ý định — dùng đo M-01 cùng PL-03 |
| `updated_at` | `timestamptz` | No | `now()` | |

- `ABANDONED` sau 24 giờ không cập nhật (đọc lười). Mở lại hội thoại trong 24 giờ ⇒ tiếp tục từ `step` (EF-CH01-04).
- Không lưu toạ độ (chỉ `anchor` loại); địa chỉ không vào bảng này.

---

# 4. `chip_intent_stat` (ENT-CH01-02)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `week_start` | `date` | No | PK (1/2) |
| `intent` | `varchar(40)` | No | PK (2/2) |
| `count_30d` | `integer` | No | Số lượt ý định (bấm chip + gõ tự do nhận diện cùng ý định) trong 30 ngày tới `week_start` |
| `rank` | `smallint` | No | 1 = phổ biến nhất |

Chỉ lưu ý định thuộc nhóm "mở đầu được" (danh mục đánh dấu `openingEligible`). Dưới 200 lượt / 30 ngày ⇒ dùng danh sách mặc định FF §8.

---

# 5. `booking_proposal` — giá trị mới

`source`: thêm `CHAT_CHIP` (bước chọn giờ tạo đề xuất). Sửa CHECK `ck_booking_proposal_source` của us-061. Xác nhận vẫn qua `API-QB-02` (chỉ nút Xác nhận trên thẻ tạo booking, BR-CH01-05).

---

# 6. Migration

- Một revision: 2 cột `chat_message` (mặc định `[]` / `NULL`, không backfill), 2 bảng mới, sửa CHECK `booking_proposal.source`.
- SQLite test: index biểu thức `((chip_action->>'chipId'))` bỏ qua; test chống dùng lại kiểm ở service.

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
