# API Technical Specification — Hỏi thăm sau dịch vụ & phiếu hỗ trợ

> Backend cho Feature `FEAT-CRM-001` — F9 (US-041 → US-044).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-041-sprint-4-spec.ff.md) là chuẩn; API chỉ trỏ `BR-9xx` / `EF-9xx` / `EDGE-9xx`.
>
> **Entity:** [Entity Spec](../entity/us-041-sprint-4-spec.entity.md) — mở rộng `follow_up`, `support_ticket`; mới `follow_up_delivery` (ENT-427).
>
> **Agent:** phân loại + tóm tắt do [AI-007](../../ai-agent/ai-007-sprint-4-spec.agent.md) (`classify_feedback`, structured output) — API gọi đồng bộ có timeout và fallback quy tắc.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-CRM-001` |
| Feature | `FEAT-CRM-001` — F9 |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Author | Team 4 Người |
| Base URL | `/api/v1` (chủ xe) · `/api/v1/workshop-owner` (chủ xưởng) |
| Auth | Firebase ID token (Bearer) |
| Created Date | `2026-09-29` |
| Updated Date | `2026-09-29` |
| Related Functional Spec | [us-041-sprint-4-spec.ff.md](../feature-functional/us-041-sprint-4-spec.ff.md) |
| Related Entity Spec | [us-041-sprint-4-spec.entity.md](../entity/us-041-sprint-4-spec.entity.md) |
| Related Frontend Spec | [us-041-sprint-4-spec.fe.md](../frontend/us-041-sprint-4-spec.fe.md) |

---

# 1. Overview

## 1.1 API Group

| API ID | Method | Endpoint / Trigger | Actor | Mục đích | FF |
|---|---|---|---|---|---|
| `API-FU-01` | `GET` | `/api/v1/follow-ups/{followUpId}` | Chủ xe | Xem hỏi thăm (form) + trạng thái | UC-902 |
| `API-FU-02` | `POST` | `/api/v1/follow-ups/{followUpId}/response` | Chủ xe | Gửi điểm + nhận xét ⇒ phân loại ⇒ (phiếu) | UC-902, UC-903 |
| `API-FU-03` | `GET` | `/api/v1/support-tickets` | Chủ xe | Danh sách phiếu của tôi | BR-911 |
| `API-FU-04` | `GET` | `/api/v1/support-tickets/{ticketId}` | Chủ xe | Chi tiết phiếu | BR-911 |
| `API-FU-05` | `GET` | `/api/v1/workshop-owner/support-tickets` | Chủ xưởng | Danh sách phiếu của xưởng | UC-904 |
| `API-FU-06` | `GET` | `/api/v1/workshop-owner/support-tickets/{ticketId}` | Chủ xưởng | Chi tiết phiếu | UC-904 |
| `API-FU-07` | `POST` | `/api/v1/workshop-owner/support-tickets/{ticketId}/transitions` | Chủ xưởng | `START` / `RESOLVE` | BR-910 |
| `JOB-FU-001` | Celery beat | `follow_up.send_due` (15') | System | Gửi hỏi thăm đến hạn + thử lại | UC-901 |
| `JOB-FU-002` | Celery beat | `follow_up.close_expired` (1h) | System | Tự đóng sau 72h | UC-905 |
| `HOOK-FU-001` | Internal | `FollowUpScheduler.on_completed(booking)` | System | Tạo hỏi thăm khi hoàn tất (gọi từ us-037) | BR-901 |

## 1.2 Scope

**In Scope** — các endpoint/job trên. **Out of Scope** — chat hai chiều trong phiếu; mở lại phiếu; khảo sát nhiều câu.

---

# 2. Authentication & Authorization

## 2.1 Authentication

```http
Authorization: Bearer <firebase_id_token>
```

## 2.2 Allowed Roles

| Endpoint | `VEHICLE_USER` | `WORKSHOP_OWNER` | `ANONYMOUS` |
|---|---|---|---|
| FU-01 → FU-04 | ✅ (của mình) | ❌ | ❌ |
| FU-05 → FU-07 | ❌ | ✅ (xưởng mình) | ❌ |

## 2.3 Authorization Rules

- Chủ xe: `follow_up → booking.user_id = uid`; `support_ticket → user_vehicle.user_id = uid`. Sai ⇒ `404` (FF AC-910).
- Chủ xưởng: phiếu có `assigned_to = owner_id` **hoặc** (`assigned_to IS NULL` và booking thuộc xưởng của chủ xưởng — Entity BR-ENT-506). Sai ⇒ `404`.
- Phiên chủ xưởng bị thu hồi ⇒ `401 SESSION_REVOKED` (như us-037).

---

# 3. API-FU-01 — `GET /api/v1/follow-ups/{followUpId}`

## 3.1 Processing

```text
1. Load follow_up JOIN booking JOIN workshop JOIN user_vehicle WHERE follow_up.id=:id AND booking.user_id=:uid → 404 FOLLOW_UP_NOT_FOUND
2. canRespond = status='sent' AND now <= sent_at + RESPONSE_WINDOW
3. Nếu status='pending' → trả như "chưa mở" (FE hiển thị "Chưa tới lúc đánh giá")
4. Nếu đã closed/PROCESSED → trả kèm kết quả (rating, comment, hasIssue, ticket summary)
```

## 3.2 Success Response `200 OK`

```json
{
  "data": {
    "followUpId": "f1a2b3c4-d5e6-4f70-8192-a3b4c5d6e7f8",
    "status": "SENT",
    "canRespond": true,
    "respondBefore": "2026-10-08T01:03:10Z",
    "question": "Xe VF 6 (30A-***.45) đã bảo dưỡng xong tại VinFast Smart City ngày 04/10. Xe của bạn chạy thế nào?",
    "booking": { "bookingId": "8d2e...", "bookingCode": "EVC-7K2M", "bookingDate": "2026-10-04" },
    "workshop": { "name": "VinFast Smart City", "hotline": "024 3999 8888" },
    "response": null,
    "outcome": null
  }
}
```

Sau khi đã trả lời:

```json
{
  "data": {
    "followUpId": "f1a2...",
    "status": "CLOSED",
    "closedReason": "PROCESSED",
    "canRespond": false,
    "response": { "rating": 2, "comment": "Về nhà thấy phanh trước kêu khi dừng", "respondedAt": "2026-10-05T05:15:44Z" },
    "outcome": { "hasIssue": true, "safetyAdvice": true, "ticket": { "ticketId": "0a1b...", "status": "OPEN" } }
  }
}
```

`outcome` **không** chứa `feedbackIntent`, `classificationConfidence`, `priority` (FF BR-911).

---

# 4. API-FU-02 — `POST /api/v1/follow-ups/{followUpId}/response`

## 4.1 Request Body

```json
{ "rating": 2, "comment": "Về nhà thấy phanh trước kêu khi dừng" }
```

| Field | Type | Required | Nullable | Description | Constraints |
|---|---|---:|---:|---|---|
| `rating` | `integer` | Yes | No | Điểm hài lòng | `1..5` |
| `comment` | `string` | No | Yes | Nhận xét | Trim; ≤ 1000 ký tự; rỗng ⇒ `null` |

## 4.2 Validation

| Validation | Rule | Error |
|---|---|---|
| Body | `rating ∈ 1..5`, `comment ≤ 1000` | `400 INVALID_REQUEST` |
| Sở hữu | booking của user | `404 FOLLOW_UP_NOT_FOUND` |
| Chưa mở | `status = pending` | `409 FOLLOW_UP_NOT_OPEN` |
| Đã trả lời | `status ∈ {responded, closed/PROCESSED}` | `409 FOLLOW_UP_ALREADY_RESPONDED` (FF EF-903) |
| Hết hạn | `closed/NO_RESPONSE` hoặc `now > sent_at + 72h` | `409 FOLLOW_UP_CLOSED` (FF EF-902) |

## 4.3 Internal Processing

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant FUS as FollowUpService
    participant AI as AI-007 classify_feedback
    participant DB

    Client->>API: POST /follow-ups/{id}/response
    API->>FUS: respond(uid, id, rating, comment)
    FUS->>FUS: validate (§4.2)
    alt rating ≥ 4 và comment rỗng
        FUS->>FUS: SATISFIED, has_issue=false, classified_by=RULES
    else
        FUS->>AI: classify(rating, comment) [timeout 5s]
        alt AI OK
            AI-->>FUS: intent, has_issue, confidence, summary, safety
            FUS->>FUS: áp BR-906 (rating ≤ 2 ⇒ issue; confidence < 0.7 ⇒ issue)
        else timeout / lỗi / output không hợp lệ
            FUS->>FUS: fallback quy tắc từ khoá + điểm (classified_by=LLM_FALLBACK)
        end
    end
    FUS->>DB: BEGIN
    FUS->>DB: UPDATE follow_up → responded (WHERE status='sent' AND trong 72h)
    opt has_issue
        FUS->>DB: INSERT support_ticket(open, assigned_to=workshop.owner_id, priority, issue_summary)
    end
    FUS->>DB: UPDATE follow_up → closed/PROCESSED (+ intent, confidence, classified_by, has_issue)
    FUS->>DB: COMMIT
    API-->>Client: 200 outcome
```

**Quy tắc fallback (FF BR-906, BR-908)** — so khớp không dấu, không phân biệt hoa thường:

| Nhóm | Từ khoá (ví dụ) | Kết quả |
|---|---|---|
| An toàn | `phanh`, `pin`, `khoi`, `chay`, `mui khet`, `mat lai`, `den do`, `ro ri`, `canh bao` | `has_issue`, `priority = high`, `safetyAdvice` |
| Vấn đề kỹ thuật | `loi`, `keu`, `tieng la`, `rung`, `den bao`, `khong chay`, `sai` | `has_issue` |
| Phàn nàn dịch vụ | `lau`, `cho`, `dat`, `tinh tien`, `thai do`, `ban`, `khong sach` | `has_issue` |
| Không khớp | — | `has_issue = (rating ≤ 2) OR (rating = 3 AND comment không rỗng)` `[Đề xuất]` |

`issue_summary` = tóm tắt AI (≤ 500) nếu AI OK và **kiểm tra không thêm thông tin ngoài lời chủ xe** (AI-007 §14.5); ngược lại = `comment` cắt 500, hoặc `"Khách chấm {rating}/5, không để lại nhận xét."`.

Nhận xét được đưa vào prompt **như dữ liệu** trong khối có đánh dấu, không ghép vào system instruction (FF EF-906).

## 4.4 Success Response `200 OK`

```json
{
  "data": {
    "followUpId": "f1a2...",
    "status": "CLOSED",
    "outcome": {
      "hasIssue": true,
      "safetyAdvice": true,
      "message": "Cảm ơn bạn đã phản hồi. Chúng mình đã chuyển thông tin tới xưởng VinFast Smart City. Xưởng sẽ liên hệ lại với bạn.",
      "safetyMessage": "Nếu xe có dấu hiệu bất thường khi vận hành, bạn nên dừng xe và liên hệ xưởng ngay: 024 3999 8888.",
      "ticket": { "ticketId": "0a1b...", "status": "OPEN" }
    }
  }
}
```

---

# 5. API-FU-03 / FU-04 — Phiếu của chủ xe

## 5.1 `GET /api/v1/support-tickets`

| Query | Type | Required | Description |
|---|---|---:|---|
| `status` | `string` | No | `OPEN` / `IN_PROGRESS` / `RESOLVED` |
| `limit` / `cursor` | `integer` / `string` | No | Phân trang (mặc định 20, mới nhất trước) |

```json
{
  "data": {
    "items": [
      { "ticketId": "0a1b...", "status": "IN_PROGRESS", "issueSummary": "Phanh trước kêu khi dừng sau bảo dưỡng.",
        "workshopName": "VinFast Smart City", "bookingDate": "2026-10-04", "createdAt": "2026-10-05T05:15:46Z", "updatedAt": "2026-10-05T06:00:00Z" }
    ],
    "nextCursor": null
  }
}
```

## 5.2 `GET /api/v1/support-tickets/{ticketId}`

```json
{
  "data": {
    "ticketId": "0a1b...", "status": "RESOLVED",
    "issueSummary": "Phanh trước kêu khi dừng sau bảo dưỡng.",
    "yourFeedback": { "rating": 2, "comment": "Về nhà thấy phanh trước kêu khi dừng" },
    "booking": { "bookingId": "8d2e...", "bookingCode": "EVC-7K2M", "bookingDate": "2026-10-04" },
    "workshop": { "name": "VinFast Smart City", "hotline": "024 3999 8888" },
    "startedAt": "2026-10-05T06:00:00Z",
    "resolvedAt": "2026-10-05T09:30:00Z",
    "resolutionNote": "Đã gọi khách, hẹn kiểm tra lại má phanh miễn phí 06/10."
  }
}
```

Không trả `priority`, `assignedTo`, `classificationConfidence` (FF BR-911).

---

# 6. API-FU-05 / FU-06 — Phiếu trên Portal

## 6.1 `GET /api/v1/workshop-owner/support-tickets`

| Query | Type | Required | Description |
|---|---|---:|---|
| `status` | `string[]` | No | Mặc định `OPEN`, `IN_PROGRESS` |
| `priority` | `string` | No | `HIGH` / `NORMAL` |
| `limit` / `cursor` | | No | Mặc định 20 |

Sắp xếp: `priority = high` trước, rồi `created_at` cũ trước (phiếu chờ lâu lên đầu).

```json
{
  "data": {
    "summary": { "OPEN": 2, "IN_PROGRESS": 1, "RESOLVED": 14, "highOpen": 1 },
    "items": [
      { "ticketId": "0a1b...", "status": "OPEN", "priority": "HIGH",
        "issueSummary": "Phanh trước kêu khi dừng sau bảo dưỡng.",
        "rating": 2, "customer": { "fullName": "Nguyễn Văn A" },
        "vehicle": { "modelName": "VF 6", "licensePlate": "30A-123.45" },
        "bookingCode": "EVC-7K2M", "createdAt": "2026-10-05T05:15:46Z" }
    ],
    "nextCursor": null
  }
}
```

## 6.2 `GET /api/v1/workshop-owner/support-tickets/{ticketId}`

Như item + `customer.phone`, `feedback { rating, comment, respondedAt }`, `classification { intent, confidence, classifiedBy }`, `booking { bookingId, bookingDate, timeSlot, actualCost }`, `startedAt`, `resolvedAt`, `resolutionNote`, `allowedActions`.

`allowedActions`: `OPEN` ⇒ `["START","RESOLVE"]`; `IN_PROGRESS` ⇒ `["RESOLVE"]`; `RESOLVED` ⇒ `[]`.

---

# 7. API-FU-07 — `POST /api/v1/workshop-owner/support-tickets/{ticketId}/transitions`

## 7.1 Request Body

```json
{ "action": "RESOLVE", "expectedStatus": "IN_PROGRESS", "resolutionNote": "Đã gọi khách, hẹn kiểm tra lại má phanh miễn phí 06/10." }
```

| Field | Type | Required | Description | Constraints |
|---|---|---:|---|---|
| `action` | `string` | Yes | `START` / `RESOLVE` | |
| `expectedStatus` | `string` | Yes | Trạng thái FE đang thấy | Khớp "từ" |
| `resolutionNote` | `string` | Khi `RESOLVE` | Ghi chú xử lý — chủ xe đọc được | Trim, 1..1000 |

## 7.2 Processing

```text
START:   UPDATE support_ticket SET status='in_progress', started_at=now()
          WHERE id=:id AND status='open' AND (assigned_to=:owner OR <gán lại — BR-ENT-506>)
RESOLVE: UPDATE support_ticket SET status='resolved', resolved_at=now(), resolution_note=:note
          WHERE id=:id AND status IN ('open','in_progress') AND status=:expected AND assigned_to=:owner
0 dòng ⇒ re-read ⇒ đã ở đích (cùng người) ⇒ 200 idempotent; ngược lại 409 INVALID_STATUS_TRANSITION
RESOLVE thành công ⇒ sau commit: NotificationService báo chủ xe (best effort):
  "✅ Xưởng {workshop_name} đã xử lý phản hồi của bạn. Xem chi tiết: {FRONTEND_URL}/support-tickets/{id}"
```

## 7.3 Success Response `200 OK`

```json
{ "data": { "ticketId": "0a1b...", "status": "RESOLVED", "resolvedAt": "2026-10-05T09:30:00Z", "allowedActions": [] } }
```

---

# 8. JOB-FU-001 — `follow_up.send_due` (mỗi 15')

```text
FOR f IN SELECT ... FROM follow_up WHERE status='pending' AND scheduled_at <= now()
         ORDER BY scheduled_at FOR UPDATE SKIP LOCKED LIMIT :batch:
  b = booking(f.booking_id)
  IF b.status <> 'completed' OR xe/tài khoản không hợp lệ (BR-903):
      closed / NOT_ELIGIBLE; continue
  UPDATE f SET status='sent', sent_at=now()                    -- BR-904: mở phản hồi dù gửi lỗi
  channels = effective_channels(b.user_id) ∩ adapters_available -- us-021; không đọc reminders_enabled (Q-903)
  INSERT follow_up_delivery (pending) per channel ON CONFLICT DO NOTHING
  text = f.message + "\nChia sẻ với chúng mình: {FRONTEND_URL}/follow-ups/{f.id}"
  deliver từng kênh; cập nhật delivery
  COMMIT per follow_up
Retry: delivery failed tạm thời, attempts < MAX, follow_up vẫn 'sent' (BR-ENT-508)
```

# 9. JOB-FU-002 — `follow_up.close_expired` (mỗi giờ)

`UPDATE follow_up SET status='closed', closed_reason='NO_RESPONSE', closed_at=now() WHERE status='sent' AND sent_at < now() - interval '72 hours'` (BR-ENT-502). Log số dòng.

# 10. HOOK-FU-001 — `FollowUpScheduler.on_completed(booking)`

Gọi trong transaction hoàn tất của us-037 (API-WB-04 `COMPLETE`):

```text
scheduled_at = quiet_hours_adjust(now() + FOLLOW_UP_DELAY_HOURS)       -- BR-ENT-503
message      = template AI-007 (model, biển số che, tên xưởng, ngày hẹn)
INSERT follow_up(booking_id, message, status='pending', scheduled_at) ON CONFLICT (booking_id) DO NOTHING
```

Lỗi ⇒ transaction hoàn tất rollback (us-037 BR-807, AC-808).

---

# 11. Error Handling

## 11.1 Standard Error Format

```json
{ "error": { "code": "FOLLOW_UP_CLOSED", "message": "Khảo sát đã đóng.", "details": { "workshopHotline": "024 3999 8888" }, "traceId": "abc-123" } }
```

## 11.2 Error Cases

| Case | Error Code | HTTP | Áp dụng | Ref |
|---|---|---:|---|---|
| Body sai | `INVALID_REQUEST` | `400` | FU-02, FU-07 | |
| Thiếu ghi chú xử lý | `RESOLUTION_NOTE_REQUIRED` | `400` | FU-07 | BR-910, AC-909 |
| Chưa xác thực / phiên thu hồi | `UNAUTHORIZED` / `SESSION_REVOKED` | `401` | tất cả | |
| Chưa onboarding | `ONBOARDING_REQUIRED` | `403` | tất cả | |
| Hỏi thăm không có / không thuộc user | `FOLLOW_UP_NOT_FOUND` | `404` | FU-01, FU-02 | AC-910 |
| Phiếu không có / không thuộc user/xưởng | `SUPPORT_TICKET_NOT_FOUND` | `404` | FU-04, FU-06, FU-07 | AC-910 |
| Hỏi thăm chưa mở | `FOLLOW_UP_NOT_OPEN` | `409` | FU-02 | |
| Đã trả lời | `FOLLOW_UP_ALREADY_RESPONDED` | `409` | FU-02 | EF-903, AC-906 |
| Đã đóng / quá 72h | `FOLLOW_UP_CLOSED` | `409` | FU-02 | EF-902, AC-905 |
| Sai chuyển trạng thái phiếu | `INVALID_STATUS_TRANSITION` | `409` | FU-07 | EF-905 |
| DB lỗi | `SERVICE_UNAVAILABLE` | `503` | FU-02, FU-07 | EF-904 |
| Lỗi hệ thống | `INTERNAL_SERVER_ERROR` | `500` | tất cả | |

> AI lỗi **không** trả lỗi cho client — luôn fallback (AF-904).

---

# 12. HTTP Status Codes

| HTTP | When |
|---|---|
| `200 OK` | Đọc; phản hồi thành công; chuyển trạng thái phiếu (kể cả idempotent) |
| `400 Bad Request` | Body sai; thiếu ghi chú |
| `401 Unauthorized` | Token sai / phiên thu hồi |
| `403 Forbidden` | Chưa onboarding |
| `404 Not Found` | Không tồn tại / không có quyền |
| `409 Conflict` | Chưa mở / đã trả lời / đã đóng / sai trạng thái phiếu |
| `503 Service Unavailable` | DB tạm lỗi |

---

# 13. Business Logic (tham chiếu FF)

| Rule | Nội dung | FF |
|---|---|---|
| Tạo | 1 / booking khi completed | BR-901 |
| Thời điểm | +12h, dời khỏi 21:00–08:00 | BR-902 |
| Mở phản hồi | `sent` dù gửi lỗi; 72h | BR-904, BR-905 |
| Phân loại | ≤ 2 sao / phàn nàn / không chắc ⇒ có vấn đề | BR-906 |
| Phiếu | 1 / hỏi thăm; gán chủ xưởng; tóm tắt từ lời khách | BR-907 |
| An toàn | `priority = high` + khuyến cáo | BR-908 |
| Tự đóng | 72h | BR-909 |
| Xử lý phiếu | START / RESOLVE (ghi chú bắt buộc) | BR-910 |
| Quyền xem | Chủ xe / chủ xưởng | BR-911 |

---

# 14. Database / Entity Interaction

| Entity / Table | Operation | Purpose |
|---|---|---|
| `follow_up` | Insert / Read / Update | Vòng đời |
| `follow_up_delivery` | Insert / Update | Kết quả gửi |
| `support_ticket` | Insert / Read / Update | Phiếu |
| `booking`, `workshop`, `user_vehicle`, `vehicle_user` | Read | Ngữ cảnh, quyền, hotline |
| `user_notification_channel`, `user_discord_link` | Read | Kênh |

---

# 15. Concurrency / Race Condition

| Tình huống | Xử lý |
|---|---|
| Hai lần gửi phản hồi | `UPDATE ... WHERE status='sent'`; lần sau `409 FOLLOW_UP_ALREADY_RESPONDED`; unique `support_ticket.follow_up_id` |
| Phản hồi đúng lúc job tự đóng | Cùng điều kiện `status='sent'` — bên commit trước thắng |
| Hai tab chủ xưởng xử lý phiếu | Cập nhật có điều kiện + `expectedStatus` |
| Hai worker job gửi | `FOR UPDATE SKIP LOCKED` + unique delivery |

---

# 16. Idempotency

- FU-02: idempotent theo trạng thái (chỉ một phản hồi). FE nên giữ nút disable khi đang gửi.
- FU-07: lặp lại cùng action sau khi thành công ⇒ `200`.
- Hook/job: unique `follow_up.booking_id`, `(follow_up_id, channel)`.

---

# 17. External Dependencies

| Service | Purpose | Required |
|---|---|---:|
| Firebase Auth | Xác thực | Yes |
| PostgreSQL | Dữ liệu | Yes |
| Celery beat | JOB-FU-001/002 | Yes |
| LLM (AI-007) | Phân loại, tóm tắt | No (fallback) |
| Discord (adapter us-021) | Gửi | Yes (MVP) |

---

# 18. Observability

**Log:** `traceId`, `followUpId`, `ticketId`, `workshopId`, `rating`, `hasIssue`, `classifiedBy`, `latency_ms` (AI), `priority`. **Không log:** `comment`, `resolutionNote`, SĐT, biển số.

**Metrics:** tỉ lệ phản hồi (responded ÷ sent); điểm trung bình theo xưởng; tỉ lệ có vấn đề; tỉ lệ fallback AI; thời gian `open → resolved`; số phiếu `high` đang mở.

---

# 19. Performance Requirements

| Metric | Target |
|---|---|
| FU-02 (p90, gồm AI) | `< 6 s` |
| Các API khác (p90) | `< 500 ms` |
| Độ trễ gửi so với `scheduled_at` (p95) | `≤ 15 phút` |

---

# 20. Retry & Timeout

| Dependency | Retry | Max Attempts | Backoff / Timeout |
|---|---:|---:|---|
| LLM classify | No | 1 | Timeout 5 s ⇒ fallback |
| Discord | Yes | `REMINDER_MAX_ATTEMPTS` (3) | Theo us-021; dừng khi hỏi thăm không còn `sent` |

---

# 21. Example — Luồng đủ

```http
GET /api/v1/follow-ups/f1a2...
```
→ `200` `canRespond = true`.

```http
POST /api/v1/follow-ups/f1a2.../response
{ "rating": 2, "comment": "Về nhà thấy phanh trước kêu khi dừng" }
```
→ `200` `hasIssue = true`, `safetyAdvice = true`, `ticket.status = OPEN`.

```http
POST /api/v1/workshop-owner/support-tickets/0a1b.../transitions
{ "action": "START", "expectedStatus": "OPEN" }
```
→ `200` `IN_PROGRESS`.

```http
POST /api/v1/workshop-owner/support-tickets/0a1b.../transitions
{ "action": "RESOLVE", "expectedStatus": "IN_PROGRESS" }
```
→ `400 RESOLUTION_NOTE_REQUIRED`.

---

# 22. Open Questions

- [ ] AI-Q-701 → AI-Q-704, Q-901 → Q-905 (FF §24).
- [ ] Phân loại đồng bộ (≤ 5 s) hay đẩy nền rồi FE poll? — `[Đề xuất]` đồng bộ cho MVP.
- [ ] Danh sách từ khoá fallback do AI Team duy trì ở đâu (file cấu hình)?

---

# 23. References

- Functional Spec: [us-041-sprint-4-spec.ff.md](../feature-functional/us-041-sprint-4-spec.ff.md)
- Entity Spec: [us-041-sprint-4-spec.entity.md](../entity/us-041-sprint-4-spec.entity.md)
- AI-007: [ai-007-sprint-4-spec.agent.md](../../ai-agent/ai-007-sprint-4-spec.agent.md)
- us-037 API (hoàn tất gọi HOOK-FU-001): [us-037-sprint-3-spec.api.md](../../sprint-3/api/us-037-sprint-3-spec.api.md)
- us-021 API (NotificationService): [us-021-sprint-2-spec.api.md](../../sprint-2/api/us-021-sprint-2-spec.api.md)

---

# 24. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Team 4 Người | Initial version: API-FU-01 → FU-07, JOB-FU-001/002, HOOK-FU-001 |
