# Entity Specification — Thẻ tương tác trong chat

> Entity cho Feature `FEAT-P2-CH02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ch-02-phase2-spec.ff.md). **API:** [API Spec](ch-02-phase2-spec.api.md).
>
> **Nguyên tắc (giữ từ us-061):** `chat_message.card` (có sẵn, ENT-422) giữ **ảnh chụp** dữ liệu hiển thị lúc gửi + id đối tượng nghiệp vụ; trạng thái hiện tại luôn đọc từ bảng nghiệp vụ khi trả tin nhắn (làm giàu), không ghi ngược vào `card`. CH-02 chỉ chuẩn hoá phong bì thẻ và thêm hai cột chỉ mục để tìm "thẻ mới nhất của một đối tượng" (EDGE-CH02-01).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-CH02` — CH-02 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend + Frontend Team |
| Created Date | `2026-10-12` |
| Related FF | [ch-02-phase2-spec.ff.md](ch-02-phase2-spec.ff.md) |
| Related API | [ch-02-phase2-spec.api.md](ch-02-phase2-spec.api.md) |
| Related FE | [ch-02-phase2-spec.fe.md](ch-02-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-422` | `ChatMessage` | `chat_message` | Có sẵn — **thêm cột** | `card_entity_type`, `card_entity_id` |

Không có bảng mới.

---

# 2. Phong bì thẻ (`chat_message.card`)

```json
{
  "type": "PROACTIVE_HOLD",
  "version": 1,
  "entity": { "type": "BOOKING", "id": "b7…" },
  "data": { "…ảnh chụp lúc gửi, từ kết quả tool…" },
  "actions": [
    { "actionId": "a_…", "label": "Xác nhận", "style": "PRIMARY", "kind": "API", "api": "PROACTIVE_CONFIRM" },
    { "actionId": "a_…", "label": "Xem phương án khác", "style": "SECONDARY", "kind": "CHIP", "chipId": "c_…" }
  ]
}
```

| Trường | Ý nghĩa |
|---|---|
| `type` | Mã trong danh mục §3 (BR-CH02-01) |
| `version` | Phiên bản schema của loại thẻ; frontend không biết `version` ⇒ hiện bản chữ (AF-CH02-01) |
| `entity` | Đối tượng nghiệp vụ để làm mới trạng thái; `null` cho thẻ thuần thông tin |
| `data` | Ảnh chụp số liệu **từ kết quả tool** (BR-CH02-02) |
| `actions` | Nút. `kind`: `CHIP` (gọi `chip-actions` CH-01 với `chipId` sinh cùng thẻ), `API` (frontend gọi API nghiệp vụ cụ thể), `LINK` (điều hướng / mở ngoài) |

Thẻ cũ (us-061, trước CH-02) không có `entity` / `actions`: giữ nguyên định dạng cũ, frontend router xử lý theo `type` như hiện tại. Thẻ mới luôn theo phong bì này.

---

# 3. Danh mục thẻ

| `type` | Thẻ (FF §3.1) | `entity.type` | Trạng thái động | Spec dữ liệu |
|---|---|---|---|---|
| `SCHEDULE_OPTIONS` | Thẻ xưởng (1–3 phương án) | `SCHEDULING_RUN` | `ACTIVE` / `SUPERSEDED` (đã chọn / chạy lại) / `EXPIRED` | BK-01, BK-05 |
| `SLOT_PICKER` | Thẻ khung giờ | `SCHEDULING_RUN` | như trên | BK-01 |
| `BOOKING_PROPOSAL` | Thẻ tóm tắt lịch hẹn | `BOOKING_PROPOSAL` | `PROPOSED` / `CONFIRMED` / `CANCELLED` / `SUPERSEDED` / `EXPIRED` (us-061) | us-061, HS-02 (`mergedItems`) |
| `BOOKING_TICKET` | Vé lịch hẹn | `BOOKING` | Trạng thái booking hiện tại | us-053 |
| `ESTIMATE` | Thẻ dự toán | `null` | — (thông tin; nhãn "ước tính") | F5, AD-01 |
| `EXTRA_QUOTE` | Thẻ báo giá phát sinh | `EXTRA_QUOTE` | `sent_to_owner` / `awaiting_owner` ⇒ `ACTIVE`; `accepted` / `declined` / `partially_accepted` ⇒ `COMPLETED` | AD-04 |
| `SERVICE_HISTORY_ITEM` | Thẻ mục lịch sử | `SERVICE_RECORD` | — | HS-01 |
| `PROACTIVE_HOLD` | Thẻ lịch giữ sẵn | `BOOKING` | `ACTIVE` (đang giữ) / `CONFIRMED` / `EXPIRED` / `CANCELLED` | BK-01 |
| `EARLY_SERVICE` | (BK-03) | `null` | — | BK-03 |
| `QUICK_BOOKING_NEED_LOCATION` | (us-061) | `null` | — | us-061 |
| `REPAIR_ADVICE` | Thẻ tư vấn sửa chữa | `null` | — (thông tin; nhãn "ước tính") | AD-02 |
| `SAFETY_ADVICE` | Thẻ an toàn | `null` | — | AD-02 |
| `WARRANTY_STATUS` | Thẻ bảo hành | `null` | — | AD-03 |

Trạng thái chuẩn hoá cho frontend (`card.status`, FF §13): `ACTIVE`, `EXPIRED`, `SUPERSEDED`, `COMPLETED` — ánh xạ từ trạng thái nghiệp vụ ở API §3.

---

# 4. `chat_message` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `card_entity_type` | `varchar(24)` | Yes | `NULL` | = `card.entity.type` |
| `card_entity_id` | `uuid` | Yes | `NULL` | = `card.entity.id` |

```sql
CREATE INDEX ix_chat_message_card_entity ON chat_message (card_entity_type, card_entity_id, seq DESC)
  WHERE card_entity_id IS NOT NULL;
ALTER TABLE chat_message ADD CONSTRAINT ck_chat_message_card_entity
  CHECK ((card_entity_type IS NULL) = (card_entity_id IS NULL));
```

Ghi cùng lúc với `card` trong `MessageService.append`. EDGE-CH02-01: thẻ có `seq` lớn nhất cho cùng (`card_entity_type`, `card_entity_id`) trong hội thoại là thẻ duy nhất có nút.

---

# 5. Business Rules (bổ sung)

## BR-ENT-CH02-01 — Ảnh chụp bất biến

`card.data` không bao giờ bị sửa sau khi lưu (AC-CH02-01 so sánh với kết quả tool đã lưu ở tin `tool` cùng lượt). Trạng thái mới chỉ đi trong phản hồi (làm giàu).

## BR-ENT-CH02-02 — Không dữ liệu nhạy cảm

`card.data` không chứa VIN đầy đủ, số điện thoại, email; biển số dạng che (`licensePlateMasked`) theo quy tắc hiện có (BR-CH02-05). Kiểm bằng validator Pydantic của từng loại thẻ trước khi lưu.

---

# 6. Migration

Một revision: 2 cột + index + CHECK. Backfill `card_entity_*` cho thẻ `BOOKING_PROPOSAL` cũ (`card.proposalId` ⇒ `BOOKING_PROPOSAL`).

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
