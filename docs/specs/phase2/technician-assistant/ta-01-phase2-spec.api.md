# API Technical Specification — Trợ lý tra cứu và nhắc việc cho kỹ thuật viên

> Backend cho Feature `FEAT-P2-TA01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ta-01-phase2-spec.ff.md). **Entity:** [Entity Spec](ta-01-phase2-spec.entity.md).
>
> **Tái dùng (Q-TA01-01: chung hạ tầng, tách tool và prompt):** orchestrator LangGraph (`agents/orchestrator.py`, `graph.py`), SSE (`assistant/sse` phía FE, `conversation` route pattern), guardrails đầu vào / ra (`agents/conversation_guards`), telemetry (LangSmith + Grafana), `WorkshopActor` + quyền `USE_ASSISTANT` (WS-03), dữ liệu lịch sử HS-01 (`history.py`), tiến độ us-057, thông báo Workshop Portal. Cần thêm AI-Agent Spec riêng `ai-0xx-phase2-spec.agent.md` (FF §23) — ngoài phạm vi tài liệu này.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-TA01` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/workshop_assistant/` (mới: `route.py`, `service.py`, `reminders.py`); `backend/src/agents/workshop/` (mới: `prompt`, `tools.py`, `graph.py` dùng chung node hạ tầng) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-TA01-01` | `POST` | `/workshop/assistant/threads` | Tạo thread | SCR-TA01-01 |
| `API-TA01-02` | `GET` | `/workshop/assistant/threads` | Thread gần đây của người gọi | — |
| `API-TA01-03` | `GET` | `/workshop/assistant/threads/{threadId}/messages` | Tin nhắn (phân trang keyset) | — |
| `API-TA01-04` | `POST` | `/workshop/assistant/threads/{threadId}/messages` | Gửi câu hỏi, trả SSE | UC-TA01-01..04 |
| `API-TA01-05` | `GET` | `/workshop/assistant/chips` | Chip gợi ý mở đầu | FF §3.1 |
| `TOOL-TA01-*` | Agent tools | §4 | Đọc dữ liệu xưởng | BR-TA01-01, 03, 04 |
| `JOB-TA01-01` | Celery | `ta.reminders` (mỗi phút) | Nhắc trước giờ đến, bước quá giờ | UC-TA01-05, BR-TA01-02 |

---

# 2. Authorization & Guards

1. `WorkshopActor` (WS-03): chủ xưởng luôn được; KTV cần `USE_ASSISTANT`. Thread chỉ chủ của nó đọc (`404` với người khác, kể cả chủ xưởng — chủ xưởng không đọc trộm chat của KTV; log hành động KTV đã có ở WS-03).
2. **Phạm vi dữ liệu do tool áp** (không do prompt):
   - `scope = actor.workshop_id`.
   - KTV không có `VIEW_ALL_BOOKINGS` ⇒ chỉ lịch có `booking_assignment` của mình (BR-TA01-04); hỏi về KTV khác ⇒ tool trả `FORBIDDEN_SCOPE` (EDGE-TA01-02).
   - Xe chỉ tra được khi có ≥ 1 `booking` (mọi trạng thái) với xưởng (BR-TA01-01); không có ⇒ `NOT_FOUND_IN_WORKSHOP` (EF-TA01-01) — tool không phân biệt "xe không tồn tại" và "xe không thuộc xưởng".
3. Khoá `workshop-assistant-run:{threadId}` như chat chủ xe; giới hạn tần suất 20 câu / phút / người.

---

# 3. API-TA01-04 — gửi câu hỏi

Request `{ "content": "Tóm tắt xe 10 giờ", "clientMessageId": "…" }` (≤ 1.000 ký tự) hoặc `{ "chipId": "…" }`.

Luồng: guard đầu vào ⇒ lưu tin `user` ⇒ chạy graph trợ lý xưởng (prompt riêng, **chỉ** bộ tool §4, không có tool ghi) ⇒ stream `message.delta` / `message.completed` (cùng giao thức SSE của chat chủ xe) ⇒ guard đầu ra (chặn SĐT / email / VIN đầy đủ, AC-TA01-04) ⇒ lưu tin `assistant` kèm `card` + `chips` ⇒ PL-03 `technician_assistant_used` (`tool`, `channel = TEXT`).

Mục tiêu token đầu ≤ 1,5 s p50 (FF §18): model nhanh mặc định của orchestrator (`LLM_*_MODEL` cấu hình), prompt ngắn, tool đọc DB trực tiếp.

---

# 4. Tools (chỉ đọc)

| Tool | Args (LLM thấy) | Trả về | UC |
|---|---|---|---|
| `ws_find_vehicle` | `plate?`, `vin_suffix?`, `customer_name?`, `booking_code?` | ≤ 3 ứng viên `{ vehicleRef, plate, model, lastBookingAt }` — chỉ xe có lịch với xưởng; biển số thiếu ký tự ⇒ tìm `ILIKE` trong lịch của xưởng, > 3 ⇒ `AMBIGUOUS` (EF-TA01-02) | UC-TA01-01 |
| `ws_vehicle_history` | `vehicleRef`, `limit?` | Danh sách lần bảo dưỡng (HS-01 `history.py`, gồm dữ liệu hãng — nhãn nguồn, AF-TA01-02); không chi phí khi actor là KTV (WS-03: KTV không xem doanh thu) | UC-TA01-01 |
| `ws_my_schedule` | `date?` (mặc định hôm nay), `scope?` (`MINE` / `WORKSHOP` — `WORKSHOP` chỉ cho chủ xưởng hoặc `VIEW_ALL_BOOKINGS`) | Lịch theo giờ: giờ, biển số, model, hạng mục, KTV, bước tiến độ | UC-TA01-02, AF-TA01-01 |
| `ws_vehicle_brief` | `bookingId?` hoặc `time?` ("10:00") | `VehicleBrief` §5; hai xe cùng giờ ⇒ `MULTIPLE` + danh sách (EDGE-TA01-01) | UC-TA01-03 |
| `ws_my_past_jobs` | `from`, `to` (≤ 31 ngày) | Lịch đã làm của KTV (phân công + tiến độ), chủ xưởng thêm `technicianName?` | UC-TA01-04 |
| `ws_pending_progress` | — | Lịch đang làm có bước quá thời lượng chuẩn / chưa cập nhật | FF §3.1 |

Mỗi tool trả `{ "found": false, "reason": "NOT_FOUND_IN_WORKSHOP" | "FORBIDDEN_SCOPE" | "AMBIGUOUS" }` thay vì lỗi; prompt: "Không có dữ liệu thì nói không có, không đoán (BR-TA01-03)". Không tool nào ghi (BR-TA01-06).

---

# 5. `VehicleBrief` (SCR-TA01-02) — thẻ `VEHICLE_BRIEF`

```json
{ "type": "VEHICLE_BRIEF", "version": 1, "entity": { "type": "BOOKING", "id": "…" },
  "data": {
    "booking": { "bookingCode": "EVC-…", "startsAt": "…", "technicianName": "An", "stage": null },
    "vehicle": { "plate": "30A-123.45", "modelName": "VF 8", "vinSuffix": "…1234", "odoKm": 23400, "odoAsOf": "2026-10-10" },
    "customer": { "displayName": "Khách Tùng" },
    "milestone": { "label": "24.000 km / 24 tháng", "items": ["Kiểm tra pin cao áp", "…"] },
    "reportedSymptom": { "text": "phanh trước kêu khi dừng", "label": "Khách mô tả" },
    "approvedLines": [ { "itemName": "…" } ],
    "deferredLastTime": [ { "itemName": "Thay lốp sau trái", "proposedAt": "2026-07-02" } ],
    "recalls": { "status": "NONE" },
    "missing": ["RECALL_DATA"]
  },
  "actions": [ { "label": "Cập nhật tiến độ", "kind": "LINK", "href": "/ktv/jobs/{bookingId}" } ] }
```

- Mọi trường từ dữ liệu nguồn (booking, `get_maintenance_status`, AD-02 `reported_symptom`, `booking_line` đã duyệt, dòng `DECLINED` lần trước = khuyến nghị chưa làm, triệu hồi từ `vehicle_recall` của HS-02 nếu có). Thiếu ⇒ đưa vào `missing` để LLM nói "chưa có dữ liệu …" (BR-TA01-03).
- Giá không có trong `approvedLines` khi actor là KTV.
- Nút trên thẻ chỉ là `LINK` sang màn cập nhật tiến độ (BR-TA01-06).

---

# 6. API-TA01-05 — chip

KTV: "Hôm nay tôi có mấy xe?", "Xe tiếp theo", "Việc chưa cập nhật", "Tuần trước tôi làm xe nào?". Chủ xưởng: "Hôm nay xưởng có mấy xe?", "Xe nào chưa phân công?", "Việc chưa cập nhật". Mỗi chip gửi câu cố định (kind `TYPE_AND_SEND`) — trợ lý xưởng không dùng luồng chip có tác dụng phụ của CH-01.

---

# 7. JOB-TA01-01 — nhắc

| Loại | Điều kiện | Nội dung (SCR-TA01-03) |
|---|---|---|
| `ARRIVAL` | Lịch `confirmed` có KTV được giao; `now ≥ starts_at − TA_ARRIVAL_REMIND_MIN` và `< starts_at`; chưa gửi | "Xe {biển số} đến lúc {HH:mm} · {hạng mục chính}" + link thẻ tóm tắt |
| `STAGE_OVERDUE` | Bước tiến độ hiện tại đã kéo dài > thời lượng chuẩn của bước (`servicing` = `booking.duration_min` WS-02; bước khác theo config `TA_STAGE_MAX_MIN`); chưa gửi cho bước đó | "Xe {biển số} đang ở bước {bước} quá {phút} phút. Cập nhật tiến độ?" |

- Chạy mỗi phút; độ lệch ≤ 1 phút (AC-TA01-03) nhờ `due_at` tính trước và quét `due_at ≤ now AND sent_at IS NULL`.
- Kênh: thông báo Workshop Portal (mục Thông báo của KTV, `/ktv` badge) + Web Push nếu KTV đã cho phép (cùng hạ tầng thông báo hiện có).
- Lịch không có KTV được giao ⇒ nhắc chủ xưởng thay (một lần).

---

# 8. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 401 / 403 | `TECHNICIAN_INACTIVE` / `PERMISSION_DENIED` | Như WS-03 |
| 404 | `THREAD_NOT_FOUND` | Thread không thuộc người gọi |
| 409 | `ASSISTANT_BUSY` | Lượt khác đang chạy |
| 429 | `RATE_LIMITED` | |

Trường hợp dữ liệu (không có xe, ngoài phạm vi) là câu trả lời, không phải mã lỗi.

---

# 9. Eval & Test Checklist

| Layer | What | Count |
|---|---|---|
| Tool | Xe không có lịch với xưởng ⇒ `NOT_FOUND_IN_WORKSHOP` (AC-TA01-01) | +2 |
| Tool | KTV không thấy lịch không được giao; chủ xưởng thấy toàn xưởng | +2 |
| Tool | Biển số thiếu ký tự ⇒ ≤ 3 ứng viên trong lịch của xưởng | +1 |
| Tool | `VehicleBrief` không có giá khi actor KTV; có `missing` khi thiếu dữ liệu | +2 |
| Guard | Đầu ra chứa SĐT ⇒ bị chặn / che (AC-TA01-04) | +2 |
| Job | Nhắc đúng `TA_ARRIVAL_REMIND_MIN ± 1 phút` (đồng hồ giả, AC-TA01-03); không nhắc trùng | +2 |
| Eval | ≥ 30 ca tóm tắt xe so với dữ liệu nguồn (bộ `eval/datasets/workshop_brief`) (AC-TA01-02) | 1 bộ |
| Isolation | Trợ lý xưởng không gọi được tool của agent chủ xe và không đọc PS-01 | +1 |

---

# 10. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
