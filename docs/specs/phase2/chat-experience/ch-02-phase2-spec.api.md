# API Technical Specification — Thẻ tương tác trong chat

> Backend cho Feature `FEAT-P2-CH02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ch-02-phase2-spec.ff.md). **Entity:** [Entity Spec](ch-02-phase2-spec.entity.md).
>
> **Tái dùng và tổng quát hoá:** `HOOK-QB-01` của us-061 (làm giàu `BOOKING_PROPOSAL` khi trả `MessageDto`) trở thành **registry làm giàu** cho mọi loại thẻ. Nút thẻ dùng lại `chip-actions` (CH-01) hoặc API nghiệp vụ có sẵn; CH-02 không thêm endpoint hành động mới.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-CH02` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/conversation/cards/` (mới): `registry.py`, `schemas.py` (Pydantic từng loại thẻ), `enrichers/*.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `SVC-CH02-01` | Internal | `CardFactory.build(type, tool_result, ctx)` | Dựng thẻ từ kết quả tool (không LLM) | UC-CH02-01, BR-CH02-01, 02 |
| `HOOK-CH02-01` | Internal | `CardEnricher.enrich(messages)` | Gắn `status` + dữ liệu động + ẩn nút khi trả tin | UC-CH02-03, BR-CH02-03, EF-CH02-01, EDGE-CH02-01 |
| `API-CH02-01` | `GET` | `/conversations/{conversationId}/messages` (có sẵn) | Trả `card` đã làm giàu | AC-CH02-02 |
| `API-CH02-02` | `POST` | `/conversations/{conversationId}/chip-actions` (CH-01) | Nút `kind = CHIP` | UC-CH02-02 |

---

# 2. SVC-CH02-01 — `CardFactory`

1. Chỉ dựng từ **kết quả tool** của lượt hiện tại (tool `end` event trong `ChatService._run_turn`, như us-061 gắn thẻ `propose_booking`). LLM không truyền số liệu vào thẻ (BR-CH02-02).
2. Ánh xạ tool → thẻ:

| Tool / handler | Thẻ |
|---|---|
| `find_schedule_options` (BK-01), chip `booking.where` / `when` | `SCHEDULE_OPTIONS` / `SLOT_PICKER` |
| `propose_booking`, chip `booking.pick_slot` | `BOOKING_PROPOSAL` |
| Xác nhận đề xuất (us-061 tin kết quả) | `BOOKING_TICKET` |
| `estimate_cost` (F5) | `ESTIMATE` |
| AD-04 báo giá phát sinh | `EXTRA_QUOTE` |
| `search_service_history` (HS-01) | `SERVICE_HISTORY_ITEM` |
| BK-01 giữ chủ động, chip `proactive.*` | `PROACTIVE_HOLD` |
| `check_early_service` (BK-03) | `EARLY_SERVICE` |

3. Nhiều tool cùng lượt ⇒ một tin có **một** thẻ chính (thẻ của tool cuối); thẻ phụ không lưu (giữ ràng buộc một `card` mỗi tin của ENT-422). Ngoại lệ: `SCHEDULE_OPTIONS` chứa tới 3 phương án trong một thẻ.
4. Validate bằng schema Pydantic của loại thẻ (BR-ENT-CH02-02). Lỗi validate ⇒ không gắn thẻ, tin vẫn có chữ + chip (AF-CH02-01), log `cards.invalid`.
5. Sinh `actions` theo loại thẻ (§4); nút `CHIP` đăng ký `chipId` trong `chat_message.chips` của **cùng tin** (để `chip-actions` kiểm hợp lệ), đánh dấu `origin = CARD`.
6. Số tiền chưa được xưởng duyệt có `amountKind = ESTIMATE` ⇒ frontend gắn nhãn "ước tính" (BR-CH02-04).

---

# 3. HOOK-CH02-01 — `CardEnricher`

Chạy ở mọi chỗ dựng `MessageDto` cho client (danh sách tin, SSE `message.completed`, replay, phản hồi `chip-actions` và `API-QB-*`) — thay `HOOK-QB-01` bằng registry.

1. Gom thẻ trong trang tin theo `entity.type`; mỗi enricher đọc **một lần theo lô**:

| `entity.type` | Đọc | `card.status` | Dữ liệu động gắn thêm |
|---|---|---|---|
| `BOOKING_PROPOSAL` | `booking_proposal` + `booking` | `PROPOSED` ⇒ `ACTIVE`; `CONFIRMED` ⇒ `COMPLETED`; `SUPERSEDED` / `CANCELLED` ⇒ `SUPERSEDED`; quá hạn ⇒ `EXPIRED` | `booking` (us-061) |
| `BOOKING` (vé) | `booking` | `pending/confirmed` ⇒ `ACTIVE`; `completed` ⇒ `COMPLETED`; `cancelled` ⇒ `SUPERSEDED` | `status`, `bookingCode`, giờ hiện tại (sau đổi lịch) |
| `BOOKING` (giữ sẵn) | `booking` | `proactive` + `pending` + chưa hết hạn ⇒ `ACTIVE`; đã xác nhận ⇒ `COMPLETED`; hết hạn / bỏ ⇒ `EXPIRED` | `holdExpiresAt` |
| `SCHEDULING_RUN` | `scheduling_option` | Có phương án `offered` chưa hết hạn ⇒ `ACTIVE`; đã chọn ⇒ `COMPLETED`; hết hạn ⇒ `EXPIRED` | trạng thái từng phương án |
| `EXTRA_QUOTE` | `extra_quote` + `booking_line` (AD-04) | `sent_to_owner` / `awaiting_owner` ⇒ `ACTIVE`; đã quyết định ⇒ `COMPLETED` | quyết định từng dòng, `version` |
| `SERVICE_RECORD` | — | luôn `ACTIVE` | — |

2. **EDGE-CH02-01:** với mỗi `entity`, chỉ thẻ có `seq` lớn nhất trong hội thoại giữ `actions`; thẻ cũ hơn trả `actions = []` và `status` như trên (dùng index `ix_chat_message_card_entity`).
3. `status ≠ ACTIVE` ⇒ `actions = []`, trừ hành động "Tìm lại" hợp lệ cho `EXPIRED` (`kind = CHIP`, intent `book_now` / `proactive.other_options`) (EF-CH02-01, AC-CH02-02).
4. Không ghi DB. Đối tượng không còn (xoá) ⇒ giữ ảnh chụp, `status = EXPIRED`.
5. Ngân sách: ≤ 1 truy vấn mỗi `entity.type` mỗi trang; mục tiêu thêm ≤ 30 ms cho trang 50 tin.

Sự kiện realtime (pub/sub) vẫn mang ảnh chụp (như us-061); client gọi lại danh sách khi cần.

---

# 4. Nút theo loại thẻ (UC-CH02-02)

| Thẻ | Nút | `kind` | Đích |
|---|---|---|---|
| `SCHEDULE_OPTIONS` | Chọn | `API` | `POST /scheduling/options/{optionId}/select` (BK-01) |
| | Chỉ đường | `LINK` | Google Maps |
| `SLOT_PICKER` | Chọn khung | `CHIP` | `booking.pick_slot` |
| `BOOKING_PROPOSAL` | Xác nhận / Đổi giờ / Đổi xưởng / Huỷ | `API` | `API-QB-02..04` (us-061) |
| `BOOKING_TICKET` | Thêm vào lịch / Chỉ đường / Đổi / Huỷ | `API` / `LINK` | BK-04 `calendar-event` / Maps / `/bookings/{id}/reschedule` / hộp huỷ BK-02 |
| `ESTIMATE` | Đặt lịch luôn / So sánh xưởng | `CHIP` / `LINK` | `book_now` / `/estimate/compare` |
| `EXTRA_QUOTE` | Đồng ý thay / Không thay lần này / Gọi cho xưởng | `API` | `POST /bookings/{bookingId}/extra-quotes/{quoteId}/decision` (AD-04) |
| `SERVICE_HISTORY_ITEM` | Xem chi tiết | `LINK` | `/history/{recordId}` |
| `PROACTIVE_HOLD` | Xác nhận / Xem phương án khác | `API` / `CHIP` | `API-BK01-07` / `proactive.other_options` |

**EF-CH02-02:** mọi API đích tự kiểm lại dữ liệu khi bấm (hết chỗ, giá đổi, hết hạn) và trả thẻ / tin mới theo spec của API đó (ví dụ `PROPOSAL_SLOT_FULL` của us-061, `OPTION_SLOT_FULL` của BK-01).

---

# 5. `MessageDto.card` khi trả về

```json
{ "type": "PROACTIVE_HOLD", "version": 1, "entity": { "type": "BOOKING", "id": "b7…" },
  "data": { "workshopName": "VinFast Cầu Giấy", "date": "2026-10-17", "timeSlot": "08:00", "holdExpiresAt": "…" },
  "status": "EXPIRED", "dynamic": { "holdExpiresAt": "…" },
  "actions": [ { "actionId": "a_…", "label": "Tìm lại", "style": "PRIMARY", "kind": "CHIP", "chipId": "c_…" } ],
  "fallbackText": "Lịch giữ sẵn tại VinFast Cầu Giấy 08:00 17/10 đã hết hạn." }
```

`fallbackText` dựng từ `data` theo mẫu (không LLM) cho client không dựng được thẻ (AF-CH02-01) và cho trình đọc màn hình.

---

# 6. Error Cases

Không có mã lỗi mới; lỗi thuộc API đích (us-061, BK-01, BK-04, AD-04) và `chip-actions` (CH-01).

---

# 7. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Mỗi loại thẻ: schema chặn VIN đầy đủ / SĐT (BR-CH02-05) | +1 (tham số hoá) |
| Unit | `CardFactory` chỉ dùng dữ liệu tool; số trên thẻ = kết quả tool đã lưu (AC-CH02-01) | +3 |
| Service | Giữ chỗ hết hạn ⇒ mở lại thẻ `EXPIRED`, không nút Xác nhận, có "Tìm lại" (AC-CH02-02) | +1 |
| Service | Hai thẻ cùng booking ⇒ chỉ thẻ mới có nút (EDGE-CH02-01) | +1 |
| Service | Thẻ cũ us-061 vẫn làm giàu đúng (hồi quy `HOOK-QB-01`) | +2 |
| Perf | Làm giàu 50 tin ≤ 30 ms thêm, ≤ 1 truy vấn / loại | +1 |

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
