# API Technical Specification — Đặt lịch bảo dưỡng nhanh

> Backend cho Feature `FEAT-QBOOK-001` (US-061).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-061-sprint-4-spec.ff.md). **Entity:** [Entity Spec](../entity/us-061-sprint-4-spec.entity.md) — `booking_proposal` (ENT-475).
>
> **Tái dùng, không viết lại:** `UserVehicleService.get_maintenance_status` (mốc, BR-1502), `CostEstimationService.estimate` (chi phí), `BookingService.check_availability` + `create_hold` (sức chứa, khoá xe + khoá khung giờ, BR-013, tự xác nhận `AUTO`), `MessageService.append` (lưu + phát tin nhắn), khoá chạy hội thoại `conversation-run:{id}`. Composition giống endpoint HTTP hiện có (BR-011, BR-1006).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-QBOOK-001` |
| Version | `v1.1` |
| Status | `Approved` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/quick_booking/` (mới) |
| Created Date | `2026-10-03` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-QB-01` | `POST` | `/conversations/{conversationId}/quick-booking` | Ô nhanh: dựng đề xuất, lưu tin chủ xe + tin trợ lý có thẻ | UC-1501, BR-1501..1508 |
| `API-QB-02` | `POST` | `/conversations/{conversationId}/booking-proposals/{proposalId}/confirm` | Xác nhận → tạo booking | UC-1502, BR-1509..1513 |
| `API-QB-03` | `POST` | `/conversations/{conversationId}/booking-proposals/{proposalId}/revise` | Đổi xưởng / thời gian → đề xuất mới | UC-1503, AF-1504 |
| `API-QB-04` | `POST` | `/conversations/{conversationId}/booking-proposals/{proposalId}/cancel` | Huỷ đề xuất | UC-1504 |
| `HOOK-QB-01` | Internal | Làm giàu `card` khi trả tin nhắn | Thẻ hiện trạng thái hiện tại | BR-1512, AC-1510 |
| `TOOL-QB-01` | Agent tool | `propose_booking` (thay `create_booking_draft`) | LLM chỉ tạo đề xuất | BR-1514 |

Không có endpoint nào của LLM hay tool nào tạo booking ngoài `API-QB-02`.

---

# 2. Authorization & Guards (mọi `API-QB-*`)

1. Xác thực như các endpoint conversation hiện có (`get_current_user_id`, tài khoản `ACTIVE`).
2. `ChatService.get_owned_conversation(user_id, conversationId)`: không phải của chủ xe ⇒ `404 CONVERSATION_NOT_FOUND`.
3. Xe của hội thoại (`conversation.user_vehicle_id`) phải `VERIFIED` + `ACTIVE` và thuộc chủ xe ⇒ không thì `409 VEHICLE_NOT_ACTIVE`.
4. `API-QB-02..04`: đề xuất phải có `proposal.user_id = user_id` **và** `proposal.conversation_id = conversationId` **và** `proposal.user_vehicle_id = conversation.user_vehicle_id`; sai bất kỳ điều kiện nào ⇒ `404 PROPOSAL_NOT_FOUND` (không lộ đề xuất của người khác).
5. `API-QB-01` và `API-QB-03` lấy khoá `conversation-run:{conversationId}` (cùng khoá với lượt chat SSE, `blocking=False`); đang bận ⇒ `409 CONVERSATION_BUSY`, và áp dụng giới hạn tần suất chat (`429 RATE_LIMITED`). `API-QB-02` **không** lấy khoá này (xác nhận không chạy LLM, không bị lượt chat chặn).
6. `API-QB-02..04` cùng lấy khoá Redis `booking-proposal:{proposalId}` (`ttl = BOOKING_LOCK_TTL_SECONDS`, `wait_timeout = 2s`) rồi đọc lại đề xuất trong khoá: thao tác nào lấy khoá trước thì quyết định; thao tác sau thấy trạng thái mới (`PROPOSAL_ALREADY_CONFIRMED`, `PROPOSAL_INACTIVE`, …). Không lấy được ⇒ `409 PROPOSAL_IN_PROGRESS`; Redis lỗi ⇒ `503 SERVICE_UNAVAILABLE`.
7. **Hết hạn:** đề xuất `proposed` hết hạn khi `now ≥ expires_at` (giờ UTC của server). Mọi thao tác chạm vào đề xuất đã hết hạn đều ghi `expired` trước rồi trả `409 PROPOSAL_EXPIRED` (kể cả huỷ).

---

# 3. Response chung

## 3.1 `MessageDto` (có sẵn, us-025)

`{ id, seq, role, content, citations, refs, card, createdAt }`.

## 3.2 `card` — `BOOKING_PROPOSAL`

Lưu trong `chat_message.card` (ảnh chụp lúc tạo) **cộng** các trường động do `HOOK-QB-01` gắn khi trả về:

```json
{
  "type": "BOOKING_PROPOSAL",
  "version": 1,
  "proposalId": "7d0c…",
  "vehicle": { "userVehicleId": "a751…", "modelName": "VF6", "trim": "Plus", "licensePlateMasked": "30A-***45" },
  "milestone": {
    "odoMilestoneKm": 12000, "monthMilestone": 12, "label": "12,000 km / 12 months",
    "dueDate": "2026-10-15", "dueStatus": "DUE_SOON", "dueReason": "BOTH",
    "remainingKm": 500, "remainingDays": 12,
    "items": [{ "itemCode": "BATTERY_CHECK", "itemName": "High-voltage battery check", "isCoveredByWarranty": true }]
  },
  "reason": "Xe còn 500 km / 12 ngày tới mốc 12.000 km (hạn 15/10/2026). Đề xuất lịch trước hạn.",
  "locationBasis": "DEVICE",
  "locationLabel": null,
  "primary": { "optionId": "opt-1", "workshopId": "…", "workshopName": "VinFast Thanh Xuân", "address": "…", "region": "Hà Nội",
               "distanceKm": 1.84, "isPreferred": false, "date": "2026-10-05", "timeSlot": "10:00",
               "estimate": { "chargeableTotal": "350000", "hasReferencePrice": false, "coveredCount": 1 } },
  "alternatives": [],
  "expiresAt": "2026-10-03T03:30:00Z",

  "status": "PROPOSED",
  "booking": null
}
```

- `locationLabel`: `"Xưởng trong khu vực Hà Nội"` khi `locationBasis = PROVINCE`; khi đó mọi `distanceKm = null`.
- `milestone` = `null` khi đề xuất đến từ `TOOL-QB-01` mà LLM không kèm mốc.
- Trường động: `status` (`PROPOSED` / `CONFIRMED` / `CANCELLED` / `SUPERSEDED` / `EXPIRED`), `booking` = `{ bookingId, bookingCode, status, ownerCancelableUntil }` (trạng thái booking **hiện tại**: `PENDING` / `CONFIRMED` / …; `bookingCode` chỉ có khi `CONFIRMED`).

## 3.3 `card` — `QUICK_BOOKING_NEED_LOCATION`

```json
{ "type": "QUICK_BOOKING_NEED_LOCATION", "version": 1, "regions": ["Hà Nội", "TP. Hồ Chí Minh"] }
```

`regions` = các `workshop.region` khác nhau của xưởng `ACTIVE`, sắp theo tên.

---

# 4. API-QB-01 — `POST /conversations/{conversationId}/quick-booking`

## 4.1 Request

```json
{ "clientMessageId": "1f7e…", "location": { "lat": 21.0035, "lng": 105.8042 }, "province": null }
```

| Field | Type | Required | Validation |
|---|---|---|---|
| `clientMessageId` | `uuid` | Yes | Idempotency như gửi tin (BR-ENT-465) |
| `location.lat` / `location.lng` | `float` | No | `[-90, 90]` / `[-180, 180]`; cả hai hoặc không có |
| `province` | `string` | No | ≤ 100 ký tự; khi chủ xe chọn ở thẻ hỏi khu vực |

## 4.2 Processing

1. Guards §2. Lưu tin `user` nội dung cố định `"Đặt lịch bảo dưỡng nhanh"` với `clientMessageId`. Nếu là gửi lại (tin đã có) và có tin trợ lý với `refs.inReplyTo = <id tin user>` ⇒ trả lại đúng cặp tin đó (`replayed: true`), không dựng lại. Không tìm theo "tin trợ lý kế tiếp" vì tin kết quả xác nhận có thể chen vào.
2. **BR-013:** xe có booking `pending | confirmed | checked_in | in_progress` ⇒ tin trợ lý EF-1501, `refs.bookingId`, không thẻ.
3. **Mốc:** `UserVehicleService.get_maintenance_status(vehicle)`. `due_status = UNKNOWN` ⇒ tin EF-1502 theo `unknown_reason`.
4. **Điểm neo (BR-1505):** `location` → `DEVICE`; không có thì `user_location` chính có toạ độ → `PROFILE`; không có thì `province` (request) hoặc `user_location.province` → `PROVINCE`; không có gì ⇒ tin + thẻ `QUICK_BOOKING_NEED_LOCATION`.
5. **Xếp xưởng (BR-1506):** `WorkshopLocationFinder.rank(anchor, workshops, preferred_workshop_id=user.preferred_workshop_id, limit=5, ranking=RankingMode.DISTANCE)`.
   - Thêm tham số `ranking: RankingMode = RankingMode.DEFAULT` vào `WorkshopLocationFinder.rank` / `SimpleTextLocationFinder.rank` (`backend/src/modules/booking/location.py`). `DEFAULT` giữ nguyên hành vi us-029 (yêu thích trước). `DISTANCE`: có toạ độ thì sắp `(distance_km is None, distance_km)`, không đẩy yêu thích; không toạ độ thì như hiện tại theo khu vực nhưng cũng không đẩy yêu thích.
6. **Cửa sổ (BR-1504)** từ `due_status`, `next_milestone.due_date`, `now_vn()`; config: `QUICK_BOOKING_MIN_LEAD_MINUTES=120`, `QUICK_BOOKING_HORIZON_DAYS=14`, `QUICK_BOOKING_NOT_DUE_LEAD_DAYS=7`, `QUICK_BOOKING_MAX_LOOKAHEAD_DAYS=60`. Vượt `MAX_LOOKAHEAD` ⇒ tin EF-1504.
7. **Tìm khung (BR-1507):** với từng xưởng theo thứ tự xếp hạng, `BookingService.open_slots(workshop, first_day, last_day)` (mới: 3 truy vấn cho cả cửa sổ, cùng công thức BR-005/006 với `check_availability`), lấy khung đầu tiên có `available = true` và bắt đầu ≥ `now + MIN_LEAD`. Dừng toàn bộ khi đủ 1 chính + 2 thay thế; nếu < 2 xưởng có khung thì lấy thêm khung kế tiếp tại xưởng chính. Các cửa sổ của BR-1504 được thử **lần lượt cho cả danh sách xưởng**: cửa sổ dự phòng (`DUE_SOON` sau ngày hạn) chỉ dùng khi **không xưởng nào** có khung trong cửa sổ trước hạn. Không có khung ⇒ tin EF-1503.
8. **Chi phí:** `CostEstimationService.estimate(vehicle, (odo_milestone, month_milestone), workshop)` cho từng phương án; `status ≠ READY` ⇒ `estimate = null`.
9. **Lưu đề xuất (một transaction):** BR-ENT-1502 (thay thế các `proposed` của chủ xe bằng `NEW_PROPOSAL`), chèn `booking_proposal` (`source = QUICK_BOOKING`, `expires_at = now + 30'`).
10. Lưu tin `assistant`: `content` = câu mẫu (lý do + phương án chính), `card` = §3.2 (ảnh chụp), `refs.inReplyTo` = id tin user, rồi gán `booking_proposal.message_id`.
11. Không gọi LLM ở bất kỳ bước nào.

## 4.3 Response `201`

```json
{ "data": { "userMessage": { "…MessageDto" }, "assistantMessage": { "…MessageDto, card đã làm giàu" }, "replayed": false } }
```

Mọi kết quả nghiệp vụ (có thẻ, cần vị trí, EF-1501..1504) đều là `201` với tin trợ lý tương ứng; chỉ lỗi §8 mới là mã lỗi.

---

# 5. API-QB-02 — `POST …/booking-proposals/{proposalId}/confirm`

## 5.1 Request

Không body. Idempotent theo `proposalId`.

## 5.2 Processing

1. Guards §2 (khoá đề xuất §2.6; không lấy khoá `conversation-run`).
2. Liên kết bền vững thẻ ↔ booking: `booking.source_message_id = proposal.message_id` (mỗi thẻ một tin nhắn).
3. Đọc lại đề xuất trong khoá:
   - `confirmed` ⇒ `200` với booking đã có (`replayed: true`).
   - Đã có booking (bất kỳ trạng thái nào, kể cả đã huỷ) có `source_message_id = proposal.message_id` ⇒ lần trước đã tạo booking nhưng chưa kịp ghi đề xuất: ghi `confirmed` với booking đó, `200 replayed: true`. Thẻ này không bao giờ đặt lần thứ hai.
   - `cancelled` / `superseded` ⇒ `409 PROPOSAL_INACTIVE` (`details.status`).
   - `proposed` đã hết hạn ⇒ §2.7.
4. Khung giờ đã bắt đầu (`appointment_at ≤ now`) ⇒ xử lý như hết chỗ (bước 7).
5. `BookingService.check_availability(user, workshop_id, booking_date, time_slot, with_alternatives=True)`.
6. Còn chỗ ⇒ `BookingService.create_hold(user, HoldRequest(confirmation_token, user_vehicle_id, milestone_ref=str(odo_milestone)), source="CHAT", source_message_id=proposal.message_id)`.
   - **Thay đổi nhỏ trong `booking/service.py`:** thêm tham số tuỳ chọn `source_message_id: UUID | None = None` cho `create_hold` → `_create_for_vehicle` → `_create_booking_locked` (gán `Booking.source_message_id`; `booking_status_event` không có cột này nên sự kiện tạo chỉ ghi `source = CHAT`). Mặc định `None`, luồng app không đổi.
   - Thành công: cập nhật đề xuất `confirmed`, `booking_id`, `confirmed_at` (commit). Lưu tin `assistant` kết quả (BR-1512) với `refs.bookingId`. Trả `200`.
   - `OpenBookingExistsError` ⇒ `409 OPEN_BOOKING_EXISTS` (`details.bookingId` = booking đang mở của xe).
   - Ô nhanh chạy xen giữa (đề xuất vừa bị `superseded` trong lúc tạo booking): booking đã có thì đề xuất vẫn ghi `confirmed` (xoá `superseded_reason`, `closed_at`).
   - Mất kết nối sau khi tạo booking nhưng trước khi lưu tin kết quả: lần xác nhận sau trả `replayed: true` với `message = null`; frontend chỉ cập nhật thẻ.
7. Hết chỗ (`available = false`, `SlotFullError`, xưởng `INACTIVE`, khung đã qua):
   - Ứng viên: `options.alternatives` của đề xuất cũ (kiểm lại bằng `check_availability`, khung ≥ `now + MIN_LEAD`) rồi `alternatives` BR-008 từ bước 5 (lọc khung ≥ `now + MIN_LEAD`).
   - Có ứng viên ⇒ một transaction: đề xuất cũ `superseded (SLOT_FULL)`, đề xuất mới (`primary` = ứng viên đầu, `alternatives` = tối đa 2 kế tiếp, chi phí tính lại, `distanceKm` chép từ phương án cũ cùng xưởng, xưởng mới thì `null`). Lưu tin trợ lý có thẻ mới. Trả `409 PROPOSAL_SLOT_FULL`, `details = { "proposalId": "<mới>", "message": MessageDto }`.
   - Không có ⇒ đề xuất cũ `superseded (SLOT_FULL)`, tin trợ lý EF-1503, `409 PROPOSAL_SLOT_FULL`, `details = { "proposalId": null, "message": MessageDto }`.

## 5.3 Response `200`

```json
{
  "data": {
    "proposalId": "7d0c…",
    "status": "CONFIRMED",
    "booking": { "bookingId": "9e62…", "bookingCode": "EVC-3289E0B2", "status": "CONFIRMED", "confirmationMode": "AUTO",
                 "workshopName": "VinFast Thanh Xuân", "bookingDate": "2026-10-05", "timeSlot": "10:00:00", "ownerCancelableUntil": null },
    "message": { "…MessageDto tin kết quả" },
    "replayed": false
  }
}
```

Xưởng `MANUAL`: `booking.status = "PENDING"`, `bookingCode = null`, `ownerCancelableUntil` có giá trị. Khi `replayed: true`, `message` là tin kết quả đã lưu lần đầu.

---

# 6. API-QB-03 — `POST …/booking-proposals/{proposalId}/revise`

## 6.1 Request

```json
{ "workshopId": "c0ca…", "date": "2026-10-06", "timeSlot": "14:00" }
```

## 6.2 Processing

1. Guards §2, khoá `conversation-run`. Đề xuất phải `proposed` và chưa hết hạn (không thì `409 PROPOSAL_INACTIVE` / `409 PROPOSAL_EXPIRED`).
2. `workshopId` phải là xưởng của một phương án trong `options` của đề xuất (chính hoặc thay thế) ⇒ không thì `422 REVISE_WORKSHOP_NOT_OFFERED`. Đổi sang xưởng ngoài danh sách thì dùng chat tự do.
3. Khung phải bắt đầu ≥ `now + MIN_LEAD` ⇒ không thì `422 SLOT_TOO_SOON`. `check_availability(..., time_slot, with_alternatives=True)`: ngoài giờ ⇒ `422 SLOT_OUT_OF_HOURS`; hết chỗ ⇒ `409 SLOT_FULL` (`details.alternatives`), **không** đổi đề xuất.
4. Một transaction: đề xuất cũ `superseded (REVISED)`; đề xuất mới với `primary` = lựa chọn (chi phí tính lại, `distanceKm` chép từ phương án cùng xưởng), `alternatives` = các phương án còn lại của đề xuất cũ (tối đa 2, khác lựa chọn). Lưu tin trợ lý có thẻ mới.

## 6.3 Response `201`

`{ "data": { "proposalId": "<mới>", "message": MessageDto } }`

---

# 7. API-QB-04 — `POST …/booking-proposals/{proposalId}/cancel`

1. Guards §2, khoá đề xuất §2.6.
2. `cancelled` ⇒ `200` (idempotent). `confirmed` ⇒ `409 PROPOSAL_ALREADY_CONFIRMED` (huỷ lịch ở màn vé, us-053). `superseded` / `expired` ⇒ `409 PROPOSAL_INACTIVE`. `proposed` đã hết hạn ⇒ §2.7 (`409 PROPOSAL_EXPIRED`). `proposed` còn hạn ⇒ `cancelled`, `closed_at = now`.
3. Không lưu tin nhắn mới.

Response `200`: `{ "data": { "proposalId": "…", "status": "CANCELLED" } }`

---

# 8. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | Body sai (toạ độ thiếu một nửa, `timeSlot` sai định dạng) | QB-01, QB-03 |
| 404 | `CONVERSATION_NOT_FOUND` | Hội thoại không thuộc chủ xe | tất cả |
| 404 | `PROPOSAL_NOT_FOUND` | Đề xuất không tồn tại / khác chủ xe / khác hội thoại / khác xe | QB-02..04 |
| 409 | `VEHICLE_NOT_ACTIVE` | Xe không còn `VERIFIED` + `ACTIVE` | tất cả |
| 409 | `CONVERSATION_BUSY` | Lượt chat khác đang chạy | QB-01, QB-03 |
| 409 | `PROPOSAL_IN_PROGRESS` | Một xác nhận khác của cùng đề xuất đang chạy | QB-02 |
| 409 | `PROPOSAL_INACTIVE` | `cancelled` / `superseded` (`details.status`) | QB-02..04 |
| 409 | `PROPOSAL_EXPIRED` | Quá 30 phút | QB-02, QB-03 |
| 409 | `PROPOSAL_SLOT_FULL` | Hết chỗ lúc xác nhận; `details.message` có thẻ mới hoặc EF-1503 | QB-02 |
| 409 | `PROPOSAL_ALREADY_CONFIRMED` | Huỷ đề xuất đã đặt | QB-04 |
| 409 | `OPEN_BOOKING_EXISTS` | Xe đã có lịch mở khác (BR-013) | QB-02 |
| 409 | `SLOT_FULL` | Khung chọn khi đổi đã hết | QB-03 |
| 422 | `SLOT_OUT_OF_HOURS` / `SLOT_TOO_SOON` / `REVISE_WORKSHOP_NOT_OFFERED` | Lựa chọn khi đổi không hợp lệ | QB-03 |
| 429 | `RATE_LIMITED` | Vượt giới hạn chat | QB-01, QB-03 |
| 503 | `SERVICE_UNAVAILABLE` | Redis / khoá không sẵn sàng | QB-02 |

Lỗi của module là `QuickBookingError(code, message, details)` (module `quick_booking/errors.py`), đăng ký trong `main.py` qua `_domain_error_response` để giữ `details` trong envelope chung `{ error: { code, message, details, traceId } }`. Lỗi `booking` được ánh xạ sang mã cùng tên.

---

# 9. HOOK-QB-01 — Làm giàu `card` khi trả tin nhắn

- Chỗ gọi: mọi nơi dựng `MessageDto` cho client trong module conversation: `GET /conversations/{id}/messages`, SSE `message.accepted` / `message.completed` / replay, phản hồi `API-QB-*`.
- Cách làm: gom `proposalId` của các `card.type = BOOKING_PROPOSAL` trong trang tin nhắn, đọc một lần `booking_proposal` (+ `booking` theo `booking_id`), gắn `status` (đổi `proposed` quá hạn thành `EXPIRED` khi đọc, BR-ENT-1501) và `booking`. Không ghi DB.
- Đề xuất không còn (hội thoại đã xoá thì tin cũng mất) ⇒ giữ ảnh chụp, `status = "EXPIRED"`.
- Sự kiện realtime (`MessageEventDto`, pub/sub) giữ ảnh chụp; client tự gọi lại danh sách khi cần trạng thái mới.

---

# 10. TOOL-QB-01 — `propose_booking` (thay `create_booking_draft`)

| | |
|---|---|
| File | `backend/src/agents/tools/booking_tools.py` |
| Args (LLM thấy) | `workshop_id`, `booking_date` (YYYY-MM-DD), `time_slot` (HH:MM), `odo_milestone?` |
| Danh tính | `user_id`, `user_vehicle_id`, **`conversation_id`** từ `RunnableConfig["configurable"]` (thêm `conversation_id` vào `run_agent_turn`) |
| Xử lý | Kiểm tra như QB-03 bước 3 (khung ≥ `now + MIN_LEAD`, `check_availability` còn chỗ); mốc từ `get_maintenance_status` nếu `odo_milestone` khớp `next_milestone` (không khớp thì `milestone = null`); chi phí như QB-01 bước 8; lưu đề xuất `source = CHAT_AGENT`, `alternatives = []`, `location_basis = NONE`, `distanceKm = null` |
| Trả về LLM | `{ "status": "PROPOSED", "proposal_id", "summary": "…", "next_step": "Chủ xe bấm Xác nhận đặt lịch trên thẻ" }` hoặc lỗi `SLOT_FULL` kèm `alternatives` |
| Gắn thẻ | `ChatService._run_turn` nhận `tool_end` của `propose_booking`, giữ card của lần gọi **cuối**, truyền `card=` khi lưu tin trợ lý, rồi gán `booking_proposal.message_id`. Đề xuất của các lần gọi trước trong cùng lượt đã bị thay (BR-1508) |
| Prompt | Mục 6 của `EV_CARE_BASE_PROMPT`: "Tool này chỉ tạo đề xuất. Chủ xe gõ đồng ý thì nhắc bấm Xác nhận đặt lịch trên thẻ; không có tool nào tạo lịch" |

`CUSTOMER_AGENT_TOOLS` không còn tool ghi booking nào.

---

# 11. Performance & Observability

- QB-01 không gọi LLM. Số truy vấn: 3 truy vấn `open_slots` mỗi xưởng cho cả cửa sổ. Trường hợp xấu nhất (5 xưởng × 14 ngày, mọi khung kín) đo được **33 câu SQL** cho cả lượt, so với 3.530 nếu gọi `check_availability` từng ngày (test `test_scan_of_fully_booked_workshops_stays_a_few_queries` giữ ngưỡng < 60).
- Mục tiêu p95 `duration_ms` của log `quick_booking.proposed` < 1,5 s, đo trên backend local nối Supabase dev (khu vực `ap-southeast-1`), 5 xưởng có toạ độ, cửa sổ 14 ngày, ≥ 20 lượt bấm.
- Log: `quick_booking.proposed` (`proposal_id`, `due_status`, `location_basis`, `options_count`), `quick_booking.confirmed` (`proposal_id`, `booking_id`, `booking_status`, `latency_ms` = `confirmed_at − created_at`), `quick_booking.slot_full`, `quick_booking.cancelled`, `quick_booking.revised`. Không log toạ độ thiết bị (PII).

---

# 12. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Cửa sổ BR-1504 cho `OVERDUE` / `DUE_SOON` (có và không có khung trước hạn) / `NORMAL` / quá `MAX_LOOKAHEAD` | +5 |
| Unit | `SimpleTextLocationFinder.rank(ranking=DISTANCE)`: yêu thích không lên đầu; xưởng không toạ độ xếp cuối; `DEFAULT` không đổi | +3 |
| Service | QB-01: không tạo booking, không khoá Redis nào còn lại (AC-1502) | +1 |
| Service | QB-01: `milestone` bằng `get_maintenance_status` (AC-1503) | +1 |
| Service | QB-01: chọn xưởng theo khoảng cách, bỏ xưởng gần nhất không có khung (AC-1504) | +1 |
| Service | QB-01: chỉ khu vực ⇒ `distanceKm = null`, `locationLabel` (AC-1505) | +1 |
| Service | QB-01: EF-1501 / EF-1502 (2 lý do) / AF-1501 / EF-1503 / EF-1504 | +6 |
| Service | QB-01: đề xuất thứ hai thay đề xuất thứ nhất (BR-1508) | +1 |
| Service | QB-02: xác nhận `AUTO` ⇒ `CONFIRMED` + mã; `MANUAL` ⇒ `PENDING`, không mã (AC-1509) | +2 |
| Service | QB-02: gọi 2 lần tuần tự + 2 lần song song ⇒ 1 booking, cùng `bookingId`, `source = CHAT`, `source_message_id` (AC-1507) | +2 |
| Service | QB-02: `superseded` / `cancelled` / `expired` / hội thoại khác / chủ xe khác ⇒ không booking (AC-1506) | +5 |
| Service | QB-02: hết chỗ ⇒ đề xuất mới, xác nhận đề xuất mới tạo booking (AC-1508) | +1 |
| Service | QB-02: phục hồi khi booking đã tạo nhưng đề xuất chưa cập nhật | +1 |
| Service | QB-03: đổi hợp lệ; xưởng ngoài danh sách; khung quá sớm; khung hết | +4 |
| Service | QB-04: huỷ ⇒ không booking; huỷ lại idempotent; huỷ đề xuất đã đặt bị từ chối | +3 |
| Service | HOOK-QB-01: thẻ đọc lại mang `status` + `booking` hiện tại, `EXPIRED` khi quá hạn (AC-1510) | +2 |
| Agent | `CUSTOMER_AGENT_TOOLS` không có tool tạo booking; `propose_booking` tạo đề xuất, không booking (AC-1506) | +2 |
| API | Envelope lỗi có `details` cho `PROPOSAL_SLOT_FULL`; `404` không lộ đề xuất người khác | +2 |

Hạ tầng test: SQLite trong bộ nhớ + fakeredis như `tests/test_modules/test_booking_service.py`; thêm `BookingProposal.__table__` vào `tests/_maintenance.TABLES`.

---

# 13. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-03` | Bản nháp đầu |
| `v1.0` | `2026-10-03` | Chủ sản phẩm duyệt bản nháp; triển khai cùng PR (backend `modules/quick_booking`, frontend `features/assistant/quickBooking`) |
| `v1.1` | `2026-10-03` | Sau review Codex (7/10): khoá theo đề xuất cho xác nhận / đổi / huỷ; liên kết booking ↔ thẻ bền vững; trả lời gửi lại theo `refs.inReplyTo`; hết hạn thắng huỷ; khớp khu vực bỏ dấu; quét khung giờ theo lô; chỉ số đo được |
