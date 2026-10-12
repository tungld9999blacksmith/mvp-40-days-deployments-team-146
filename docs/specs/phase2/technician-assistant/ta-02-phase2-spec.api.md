# API Technical Specification — Hỗ trợ tại khoang làm việc

> Backend cho Feature `FEAT-P2-TA02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ta-02-phase2-spec.ff.md). **Entity:** [Entity Spec](ta-02-phase2-spec.entity.md).
>
> **Tái dùng:** tiến độ 6 bước (us-057: `POST …/progress`), `WorkshopActor` + quyền `UPDATE_PROGRESS` / `USE_ASSISTANT` (WS-03), trợ lý xưởng TA-01 (tool + thread), `booking_line` (dòng gộp / phát sinh), thông báo Workshop Portal, `technician_audit_log` (WS-03). Giọng nói nhận dạng ở trình duyệt (frontend §2.3); backend chỉ nhận văn bản đã xác nhận.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-TA02` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/workshop_assistant/checklist.py`, `handover.py` (mới) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-TA02-01` | `GET` | `/workshop/bookings/{bookingId}/checklist` | Checklist (tạo bản chụp lần đầu) | UC-TA02-01 |
| `API-TA02-02` | `PATCH` | `/workshop/bookings/{bookingId}/checklist/items/{itemId}` | Đánh dấu `done` / `skipped` / về `pending` | UC-TA02-02 |
| `HOOK-TA02-01` | Internal | Chặn chuyển bước tiến độ khi còn mục bắt buộc `pending` | | BR-TA02-01, AC-TA02-01 |
| `API-TA02-03` | `GET` | `/workshop/handover?date` | Tóm tắt giao ca (SCR-TA02-02) | UC-TA02-03 |
| `API-TA02-04` | `POST` | `/workshop/bookings/{bookingId}/handover-notes` | Ghi chú giao ca (văn bản đã xác nhận) | UC-TA02-04 |
| `JOB-TA02-01` | Celery | `handover.scheduled` (theo `handover_times`) | Gửi tóm tắt giao ca | Q-TA02-01 |
| `TOOL-TA02-01` | Agent tool (TA-01) | `ws_checklist_status`, `ws_handover_summary` | Hỏi bằng giọng nói / chữ qua trợ lý xưởng | UC-TA02-04 |

---

# 2. Authorization & Guards

`WorkshopActor`: KTV được giao lịch (cần `UPDATE_PROGRESS`) hoặc chủ xưởng (FF §16). EDGE-TA02-01: nhiều KTV — mọi KTV có phân công `active` cho lịch (Phase 2 chỉ một) **hoặc** có `VIEW_ALL_BOOKINGS` + `UPDATE_PROGRESS` đều đánh dấu được; người đánh dấu được ghi. Khoá lạc quan theo `marked_at` không cần — thao tác idempotent theo trạng thái đích.

---

# 3. API-TA02-01 — checklist

1. Lịch `checked_in` / `in_progress`.
2. Chưa có dòng ⇒ tạo bản chụp (một transaction, khoá `checklist:{bookingId}`): mẫu `active` theo (model xe, `odo_milestone`) ⇒ `TEMPLATE`; không có ⇒ `maintenance_rule` ⇒ `MAINTENANCE_RULE` + `notice = "NO_DETAILED_CHECKLIST"` (EF-TA02-01). Thêm dòng `BOOKING_LINE` cho dòng gộp (HS-02) và phát sinh `APPROVED` (AD-04), `required = true`. Phát sinh được duyệt sau khi đã chụp ⇒ thêm dòng vào cuối khi đọc lại.
3. Response:

```json
{ "data": { "bookingId": "…", "templateVersion": 3, "notice": null,
  "source": { "documentId": "…", "title": "Sổ tay bảo dưỡng VF 8", "version": "2025" },
  "items": [ { "itemId": "…", "label": "Kiểm tra má phanh trước", "required": true, "status": "pending", "sourceChunkId": "…", "markedBy": null, "markedAt": null } ],
  "requiredRemaining": 6 } }
```

---

# 4. API-TA02-02 — đánh dấu

`{ "status": "done" | "skipped" | "pending", "skipReason": "Khách từ chối thay" }`. `skipped` thiếu lý do ⇒ `422 SKIP_REASON_REQUIRED`. Ghi người + thời điểm (BR-TA02-04); log WS-03 (`CHECKLIST_MARKED`). Trả item + `requiredRemaining`.

---

# 5. HOOK-TA02-01 — chặn chuyển bước

Trong `ServiceProgressService` (us-057) khi chuyển **ra khỏi** bước `servicing` (Đang thực hiện) sang `quality_check` / `ready_for_pickup`: nếu checklist tồn tại và còn mục `required` `pending` ⇒ `409 CHECKLIST_INCOMPLETE` với `details.items` = nhãn còn thiếu (AC-TA02-01). Chưa từng mở checklist ⇒ tạo bản chụp rồi kiểm (không cho né bằng cách không mở). `skipped` có lý do tính là đã xử lý (AF-TA02-01). Chủ xưởng có thể ghi đè với `override = true` + lý do (ghi log) — trường hợp ngoại lệ ngoài FF, cần PO xác nhận (Q-API-TA02-01); mặc định tắt.

---

# 6. Giao ca — API-TA02-03/04, JOB-TA02-01

`GET /workshop/handover?date` (phạm vi theo quyền WS-03; KTV mặc định chỉ xe của mình):

```json
{ "data": { "generatedAt": "…", "groups": {
  "inProgress": [ { "bookingId": "…", "plate": "30A-123.45", "stage": "servicing", "checklist": "4/6 bắt buộc", "technician": "An", "lastNote": "…" } ],
  "waitingParts": [ … ],
  "waitingOwnerApproval": [ { "…": "phát sinh AD-04 sent_to_owner / awaiting_owner" } ] } } }
```

Nhóm theo BR-TA02-02: làm dở (`in_progress` / `checked_in` chưa `ready_for_pickup`), chờ phụ tùng (bước `waiting_parts`), chờ khách duyệt (AD-04). Dữ liệu từ DB, không LLM (trợ lý có thể diễn đạt khi được hỏi). `JOB-TA02-01` gửi thông báo "Tóm tắt giao ca" vào giờ trong `handover_times` (rỗng ⇒ không gửi).

`POST …/handover-notes { "text": "…", "inputMethod": "VOICE" }` — chỉ nhận văn bản (≤ 1.000 ký tự); không có endpoint nhận âm thanh (BR-TA02-03, AC-TA02-02).

---

# 7. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 403 | `PERMISSION_DENIED` | Không được giao / thiếu quyền |
| 404 | `CHECKLIST_ITEM_NOT_FOUND` | |
| 409 | `BOOKING_NOT_IN_SERVICE` | Lịch chưa check-in |
| 409 | `CHECKLIST_INCOMPLETE` | Chuyển bước khi còn mục bắt buộc |
| 422 | `SKIP_REASON_REQUIRED` | |

---

# 8. Test Checklist

| Layer | What | Count |
|---|---|---|
| Service | Còn mục bắt buộc ⇒ không chuyển bước (AC-TA02-01); bỏ qua có lý do ⇒ cho | +2 |
| Service | Không có mẫu ⇒ dùng `maintenance_rule` + notice | +1 |
| Service | Phát sinh duyệt sau ⇒ thêm vào checklist | +1 |
| Service | Hai KTV đánh dấu ⇒ ghi đúng người | +1 |
| API | Không endpoint nhận âm thanh; ghi chú chỉ văn bản (AC-TA02-02) | +1 |
| Service | Giao ca nhóm đúng ba loại | +3 |

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
