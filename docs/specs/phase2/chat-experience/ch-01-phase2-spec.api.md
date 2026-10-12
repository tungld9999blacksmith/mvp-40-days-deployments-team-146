# API Technical Specification — Gợi ý một chạm

> Backend cho Feature `FEAT-P2-CH01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ch-01-phase2-spec.ff.md). **Entity:** [Entity Spec](ch-01-phase2-spec.entity.md).
>
> **Tái dùng:** `ChatService` + `MessageService.append` (lưu, phát SSE), khoá `conversation-run:{id}` và giới hạn tần suất chat (us-025), `booking_proposal` + `API-QB-02` xác nhận (us-061), `SchedulerService.run` / `select` (BK-01), `MemoryService.recall_for_intent` (PS-01), router ý định AI-001. Chip **ACTION** chạy handler xác định — không gọi LLM (BR-CH01-02); chỉ câu gõ tự do mới đi qua agent.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-CH01` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/chips/` (mới): `catalog.py` (danh mục), `selector.py` (chọn 3–5 chip), `handlers/booking_flow.py`, `handlers/info.py`, `route.py`, `jobs.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-CH01-01` | `GET` | `/conversations/{conversationId}/opening-chips` | Chip mở đầu + theo trạng thái cho màn chat trống | UC-CH01-01, 04 |
| `API-CH01-02` | `POST` | `/conversations/{conversationId}/chip-actions` | Bấm một chip | UC-CH01-02, 03, BR-CH01-02 |
| `API-CH01-03` | `GET` | `/chips/home?userVehicleId` | 3 chip theo trạng thái cho Trang chủ | Q-CH01-02 |
| `HOOK-CH01-01` | Internal | `ChipSelector.attach(message, ctx)` | Gắn chip ngữ cảnh / trạng thái vào mọi tin trợ lý (kể cả trả lời từ LLM) | UC-CH01-03, BR-CH01-01, 07 |
| `HOOK-CH01-02` | Internal | Lượt gõ tự do giữa luồng đọc / ghi `conversation_flow_state` | | UC-CH01-05, AF-CH01-02 |
| `JOB-CH01-01` | Celery | `chips.weekly_intent_stats` | Top ý định 30 ngày | BR-CH01-04 |

`MessageDto` (us-025) thêm `chips: Chip[]` và `chipState: "ACTIVE" | "STALE"` (tính khi trả).

---

# 2. Authorization & Guards

1. Như API hội thoại: chủ xe, hội thoại thuộc chủ xe (`404 CONVERSATION_NOT_FOUND`), xe `VERIFIED` + `ACTIVE`.
2. `API-CH01-02` lấy khoá `conversation-run:{conversationId}` (`blocking=False`) ⇒ bận ⇒ `409 CONVERSATION_BUSY`; áp giới hạn tần suất chat ⇒ `429 RATE_LIMITED`.
3. Chip hợp lệ khi: `chipId` có trong `chips` của **tin trợ lý mới nhất** (hoặc tập chip mở đầu vừa phát, §4) **và** chưa dùng ⇒ ngược lại `409 CHIP_STALE` (EF-CH01-01, AC-CH01-03). Kiểm trong khoá; unique index `ux_chat_message_chip_used` là chốt cuối.

---

# 3. Danh mục chip (`catalog.py`)

| Intent | Params | Handler | Tác dụng phụ |
|---|---|---|---|
| `book_maintenance` | — | `booking_flow.start` | Không |
| `booking.confirm_habit` | `{ answer: YES \| NO }` | `booking_flow.habit` | Không |
| `booking.where` | `{ anchor: DEVICE \| WORK \| USUAL_WORKSHOP }` | `booking_flow.where` | Không |
| `booking.pick_workshop` | `{ workshopId }` | `booking_flow.workshop` | Không |
| `booking.when` | `{ date?, part?, range? }` (sinh động từ khung rảnh + chỗ trống) | `booking_flow.when` | Không |
| `booking.pick_slot` | `{ optionId }` | `booking_flow.slot` ⇒ tạo `booking_proposal` (`CHAT_CHIP`) + thẻ `BOOKING_PROPOSAL` | Không (đề xuất, chưa giữ chỗ) |
| `booking.change_time` / `booking.change_workshop` | — | quay lại bước `WHEN` / `WHERE` | Không |
| `ask_due_status`, `ask_cost_estimate`, `view_history`, `ask_warranty`, `ask_parts_quote` | — | `info.*` gọi tool tương ứng (F3, cost_estimate, HS-01, AD-03, AD-02) và dựng câu trả lời mẫu + thẻ | Không |
| `proactive.confirm` / `proactive.other_options` | `{ bookingId }` | BK-01 `API-BK01-07` / chạy lại | **Có** ⇒ chỉ mở thẻ lịch giữ sẵn có nút Xác nhận (BR-CH01-05) |
| `booking.reschedule`, `booking.running_late` | `{ bookingId }` | Thẻ đổi giờ (us-053) / BK-08 | Thẻ có nút xác nhận |
| `quote.view_extra` | `{ bookingId }` | AD-04 thẻ | Không |
| `book_now` | — | như `book_maintenance` | Không |
| `retry` | `{ chipId }` | chạy lại chip lỗi | — |
| `LINK`: `open_map`, `open_calendar`, `directions` | `{ … }` | Frontend mở màn; không gọi API-CH01-02 | — |
| `TYPE`: `type_question` | — | Frontend focus ô nhập | — |

Kiểm tra tự động (AC-CH01-02): test duyệt mọi intent `ACTION` trong danh mục, khẳng định có handler và handler trả `ChipResult` hợp lệ với tham số mẫu.

Nhãn sinh từ mẫu tiếng Việt trong `catalog.py` (≤ 40 ký tự; vượt ⇒ cắt kèm "…" và test cảnh báo).

---

# 4. API-CH01-01 — `GET /conversations/{conversationId}/opening-chips`

Hội thoại chưa có tin ⇒ tập chip mở đầu; đã có tin ⇒ `409 CONVERSATION_NOT_EMPTY` (frontend dùng chip của tin mới nhất). Response:

```json
{ "data": { "chipSetId": "s_…", "chips": [ { "chipId": "c_…", "intent": "booking.start_due", "label": "Đặt lịch mốc 24.000 km", "primary": true, "source": "STATUS", "kind": "ACTION", "params": {} } ] } }
```

`ChipSelector.opening(ctx)` (§6) với `CHIP_MIN`..`CHIP_MAX`. Tập này lưu Redis `chips:opening:{conversationId}` (TTL 24 giờ) để `API-CH01-02` kiểm hợp lệ trước khi có tin nào.

---

# 5. API-CH01-02 — `POST /conversations/{conversationId}/chip-actions`

## 5.1 Request

```json
{ "chipId": "c_…", "clientMessageId": "1f7e…" }
```

`clientMessageId`: idempotency như gửi tin (BR-ENT-465). Gửi lại ⇒ trả cặp tin đã có (`replayed: true`).

## 5.2 Processing

1. Guards §2. Lấy chip (intent, params) từ **bản đã lưu** — không tin `intent` từ client.
2. Lưu tin `user`: `content = label`, `chip_action = { chipId, intent, params, sourceMessageId }`.
3. Handler theo intent (không LLM). Luồng đặt lịch (`booking_flow`), cập nhật `conversation_flow_state` (khoá lạc quan `version`):

| Bước | Handler | Câu trợ lý (mẫu) | Chip trả về |
|---|---|---|---|
| start | Có hồ sơ BK-01 + `CONSENT_LONG_TERM_MEMORY` + mục nhớ `preferred_*` dùng được ⇒ `CONFIRM_HABIT`; ngược lại ⇒ `WHERE` (EDGE-CH01-03) | "Lần trước {xưng hô} đặt {buổi} {thứ} ở {xưởng}, đặt như vậy nhé?" (nêu nguồn bộ nhớ, PS-01 BR-PS01-04) | Đúng vậy · Chọn khác |
| habit YES | Chạy BK-01 (`trigger = CHIP`, ràng buộc hồ sơ) ⇒ `SLOT` | "Mình tìm được các giờ sau" | Tối đa 4 chip giờ (`booking.pick_slot`) + "Đổi ngày" |
| where | `USUAL_WORKSHOP` ⇒ `WHEN`; `DEVICE` / `WORK` ⇒ BK-01 không ràng buộc thời gian, lấy 3 xưởng ⇒ thẻ `SCHEDULE_OPTIONS` dạng chọn xưởng (CH-02) ⇒ `WORKSHOP` | "Bạn muốn làm ở đâu?" | Gần vị trí hiện tại · Gần nơi làm việc (khi có `WORK`) · Xưởng quen (khi có) · Chọn trên bản đồ (`LINK`) |
| workshop | Ghi `workshopId` ⇒ `WHEN` | "Khi nào bạn rảnh?" | Chip thời gian §5.3 + "Mở lịch chọn ngày" (`LINK`) |
| when | BK-01 với `overrides.workshopId` + `availability` ⇒ `SLOT`; kín ⇒ phương án thay thế dạng chip (AF-CH01-01) | "Còn các giờ sau" / "Xưởng {tên} kín, có các lựa chọn khác" | Chip giờ / phương án |
| slot | Tạo `booking_proposal` (`source = CHAT_CHIP`, `primary` = phương án, `alternatives` = 2 phương án kế, chi phí như us-061) ⇒ `SUMMARY` | Câu tóm tắt + thẻ `BOOKING_PROPOSAL` (Xác nhận · Đổi giờ · Đổi xưởng trên thẻ) | Đổi giờ · Đổi xưởng |
| (xác nhận qua `API-QB-02`) | `step = DONE` (hook sau xác nhận) | Tin kết quả us-061 | Thêm vào lịch (`LINK`, BK-04) · Chỉ đường (`LINK`) |

4. Lưu tin `assistant` với `content`, `card`, `chips` (HOOK-CH01-01 có thể thêm chip trạng thái), `refs.inReplyTo`.
5. Handler lỗi ⇒ tin trợ lý "Xin lỗi, mình chưa làm được bước này." + chip `retry` + `type_question` (EF-CH01-03); log `chips.handler_error`.
6. Sự kiện PL-03 `chip_clicked` (`intent`, `source`, `position`, `flowStep`).

## 5.3 Chip thời gian (bước `WHEN`)

Sinh từ khung rảnh (hồ sơ BK-01, lịch bận BK-04 nếu có đồng ý) giao với ngày còn chỗ của xưởng (`open_slots` 14 ngày): chọn tối đa 3 cửa sổ sớm nhất có chỗ, nhãn tự nhiên "Sáng thứ Bảy này", "Chiều mai", "Cuối tuần sau". Không có khung rảnh ⇒ 3 cửa sổ sớm nhất có chỗ.

## 5.4 Response `201`

```json
{ "data": { "userMessage": { "…MessageDto" }, "assistantMessage": { "…MessageDto, chips, card" }, "flow": { "step": "SLOT" }, "replayed": false } }
```

Đồng thời phát qua SSE như tin thường để tab khác cập nhật.

---

# 6. HOOK-CH01-01 — `ChipSelector`

Chạy khi dựng mọi tin trợ lý (handler chip **và** lượt LLM), không gọi LLM, ≤ 20 ms:

1. **Ứng viên trạng thái** (ưu tiên cao nhất, BR-CH01-07): theo bảng FF §8 — hẹn trong 24 giờ (đổi giờ, chỉ đường, tôi đến trễ) > lịch giữ chủ động > báo giá phát sinh chờ > xe `DUE_SOON` / `OVERDUE` chưa có lịch. EDGE-CH01-01: có hẹn thì bỏ chip "Đặt lịch mốc".
2. **Ứng viên ngữ cảnh:** theo `intent` của lượt (AI-001) và `flow.step`: ví dụ sau trả lời dự toán ⇒ "Đặt lịch luôn" (AF-CH01-05); sau trả lời đến hạn ⇒ "Mốc tới hết bao nhiêu?", "Đặt lịch".
3. **Ứng viên mở đầu:** `chip_intent_stat` tuần gần nhất, hoặc danh sách mặc định.
4. Gộp theo ưu tiên trạng thái > ngữ cảnh > mở đầu, bỏ trùng intent, lấy `CHIP_MAX`; < `CHIP_MIN` ⇒ bổ sung từ mở đầu (EDGE-CH01-02). `primary` = ứng viên đầu nếu là bước tiếp theo của luồng.
5. Ghi `chips` vào tin; PL-03 `chip_shown` cho từng chip.

Lượt LLM trả lời câu gõ tự do giữa luồng (HOOK-CH01-02): agent nhận `conversation_flow_state` trong `RunnableConfig`; tool `update_booking_flow(slots_patch)` cho phép LLM cập nhật ràng buộc ("thôi để chiều" ⇒ `window.part = AFTERNOON`), rồi handler bước tương ứng chạy lại để dựng chip (AF-CH01-02). LLM không tạo chip.

---

# 7. API-CH01-03 — `GET /chips/home`

3 chip trạng thái (bước 1 của §6) cho Trang chủ; mỗi chip kèm `deepLink` `/ai?chip={intent}&params=…`. Mở chat từ link ⇒ frontend tạo hội thoại rồi gọi `API-CH01-02` với chip mở đầu tương ứng (backend phát tập mở đầu chứa đúng chip đó).

---

# 8. JOB-CH01-01 — `chips.weekly_intent_stats`

Thứ Hai 01:00: đếm `product_event` (`chip_clicked` + `chat_intent_detected`) 30 ngày theo intent mở đầu được ⇒ ghi `chip_intent_stat`.

---

# 9. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 404 | `CONVERSATION_NOT_FOUND` | | tất cả |
| 409 | `CHIP_STALE` | Chip của bước cũ / đã dùng / không tồn tại | CH01-02 |
| 409 | `CONVERSATION_BUSY` | Lượt khác đang chạy | CH01-02 |
| 409 | `CONVERSATION_NOT_EMPTY` | Xin chip mở đầu cho hội thoại đã có tin | CH01-01 |
| 409 | `FLOW_VERSION_CONFLICT` | Chip và câu gõ cùng ghi luồng (hiếm) — client gọi lại | CH01-02 |
| 409 | `VEHICLE_NOT_ACTIVE` | | tất cả |
| 429 | `RATE_LIMITED` | | CH01-02 |

---

# 10. Observability

- PL-03: `chip_shown`, `chip_clicked` (M-04), `booking_intent_started` (bước start), `booking_confirmed` (`taps`, `typedChars` = 0 khi chỉ chip — M-02, phát khi `API-QB-02` xác nhận đề xuất của luồng).
- Log `chips.handler_error` (`intent`, lớp lỗi), `chips.stale_click`.

---

# 11. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Mọi intent `ACTION` có handler hợp lệ (AC-CH01-02) | +1 (tham số hoá) |
| Unit | Selector: ưu tiên trạng thái > ngữ cảnh > mở đầu; 3–5 chip; có hẹn ⇒ không chip đặt lịch mốc | +5 |
| Unit | Nhãn ≤ 40 ký tự cho mọi mẫu | +1 |
| Service | Luồng chuẩn chỉ bằng chip từ start → thẻ → `API-QB-02` ⇒ booking; 0 ký tự (AC-CH01-01) | +1 |
| Service | Có thói quen ⇒ Đúng vậy → giờ → Xác nhận = 3 chạm (AC-CH01-04) | +1 |
| Service | Chip cũ ⇒ `409 CHIP_STALE`, không tác dụng phụ (AC-CH01-03); dùng lại cùng chip ⇒ `409` | +2 |
| Service | Xưởng quen kín ⇒ chip phương án thay thế (AF-CH01-01) | +1 |
| Service | Gõ "thôi để chiều" giữa luồng ⇒ luồng tiếp ở `SLOT` với khung chiều (AF-CH01-02) | +1 |
| Service | Tắt bộ nhớ ⇒ bỏ bước `CONFIRM_HABIT` (EDGE-CH01-03) | +1 |
| Service | Mở lại hội thoại trong 24 giờ ⇒ tiếp từ bước cuối (EF-CH01-04) | +1 |
| Analytics | `chip_shown` + `chip_clicked` đủ để tính M-04 (AC-CH01-05) | +1 |

---

# 12. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
