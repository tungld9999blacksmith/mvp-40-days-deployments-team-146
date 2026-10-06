# API Technical Specification — Báo giá có chủ xưởng duyệt (HITL)

> **Đã loại khỏi phạm vi (02/10/2026).** Chức năng báo giá có chủ xưởng duyệt (F5b, us-049, AI-005) đã bị bỏ khỏi sản phẩm: code backend/frontend đã gỡ, bảng `quote`, `quote_item` được xoá bởi migration `backend/alembic/versions/a3c7e9f1b2d4_drop_quote_support_ticket_discord.py`. Tài liệu giữ lại để tham khảo lịch sử, **không dùng để triển khai**.

> Backend cho Feature `FEAT-QUOTE-001` — PRD F5b (US-049 → US-052).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-049-sprint-3-spec.ff.md) là chuẩn; API chỉ trỏ `BR-11xx` / `EF-11xx` / `EDGE-11xx`.
>
> **Entity:** [Entity Spec](../entity/us-049-sprint-3-spec.entity.md) — `quote` (ENT-410, thêm `submitted_at`), `quote_item` (ENT-411, thêm `is_covered_by_warranty`, `price_source`, `reviewer_note`); `quote.source_message_id` theo [us-025 entity](../../sprint-2/entity/us-025-sprint-2-spec.entity.md).
>
> **Dùng chung:** `QuoteService` là service duy nhất; API dưới đây và tool AI-005 (`create_draft_quote`, `submit_quote`, `get_quote_status`) đều gọi nó.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-QUOTE-001` |
| Feature | `FEAT-QUOTE-001` — F5b |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Author | Team 4 Người |
| Base URL | `/api/v1` |
| Auth | Firebase ID token (Bearer) |
| Created Date | `2026-09-30` |
| Updated Date | `2026-09-30` |
| Related Functional Spec | [us-049-sprint-3-spec.ff.md](../feature-functional/us-049-sprint-3-spec.ff.md) |
| Related Frontend Spec | [us-049-sprint-3-spec.fe.md](../frontend/us-049-sprint-3-spec.fe.md) |

---

# 1. Overview

## 1.1 API Group

| API ID | Method | Endpoint / Trigger | Actor | Mục đích | FF |
|---|---|---|---|---|---|
| `API-QT-01` | `POST` | `/api/v1/quotes` | Chủ xe | Tạo nháp từ (xe, xưởng, mốc) — backend tự tính dự toán | UC-1101, BR-1101, BR-1102 |
| `API-QT-02` | `GET` | `/api/v1/quotes` | Chủ xe | Danh sách báo giá của xe | SCR-1103 |
| `API-QT-03` | `GET` | `/api/v1/quotes/{quoteId}` | Chủ xe | Chi tiết + trạng thái suy ra | SCR-1101, SCR-1102 |
| `API-QT-04` | `POST` | `/api/v1/quotes/{quoteId}/submit` | Chủ xe | `draft → pending_approval` | BR-1103, BR-1104 |
| `API-QT-05` | `DELETE` | `/api/v1/quotes/{quoteId}` | Chủ xe | Xoá nháp | BR-1112 |
| `API-QT-11` | `GET` | `/api/v1/workshop-owner/quotes` | Chủ xưởng | Danh sách báo giá của xưởng (không gồm `draft`) | SCR-1111, BR-1110 |
| `API-QT-12` | `GET` | `/api/v1/workshop-owner/quotes/{quoteId}` | Chủ xưởng | Chi tiết để duyệt | SCR-1112 |
| `API-QT-13` | `POST` | `/api/v1/workshop-owner/quotes/{quoteId}/approve` | Chủ xưởng | Duyệt (sửa giá dòng, thời hạn) | BR-1105, BR-1106 |
| `API-QT-14` | `POST` | `/api/v1/workshop-owner/quotes/{quoteId}/reject` | Chủ xưởng | Từ chối + lý do | BR-1107 |
| `JOB-QT-01` | Celery beat | `quote.purge_stale_drafts` (hằng ngày 03:00 VN) | Hệ thống | Xoá nháp quá `QUOTE_DRAFT_TTL_DAYS` | BR-1112 |
| `HOOK-QT-01` | Internal | `QuoteService.attach_to_booking(quote_id, booking)` | F6 | Gắn báo giá trong transaction tạo booking | BR-1108 |
| `HOOK-QT-02` | Internal | `QuoteService.detach_from_booking(booking_id)` | F6b/F7/F8 | Gỡ liên kết khi booking huỷ | BR-1108 |

## 1.2 Configuration

| Env | Default | Ý nghĩa |
|---|---|---|
| `QUOTE_DEFAULT_VALIDITY_DAYS` | `7` | Thời hạn mặc định khi duyệt |
| `QUOTE_MAX_VALIDITY_DAYS` | `30` | Thời hạn tối đa |
| `QUOTE_DRAFT_TTL_DAYS` | `7` | Dọn nháp |
| `QUOTE_DRAFT_REFRESH_HOURS` | `24` | Nháp cũ hơn ⇒ lập lại snapshot khi gửi (Q-1104) |

---

# 2. Authentication & Authorization

| Group | Dependency | Rule |
|---|---|---|
| `API-QT-01` → `05` | `require_active_user` + `get_owned_active_vehicle` | `quote.user_vehicle_id` thuộc user; sai ⇒ `404 QUOTE_NOT_FOUND` |
| `API-QT-11` → `14` | `require_active_workshop_owner` | `quote.workshop_id = workshop của chủ xưởng` ∧ `status ≠ draft`; sai ⇒ `404 QUOTE_NOT_FOUND` (BR-1110) |

Tool AI-005 gọi `QuoteService` dưới danh nghĩa chủ xe của phiên chat (cùng kiểm tra quyền).

---

# 3. API-QT-01 — `POST /api/v1/quotes`

## 3.1 Request Body

```json
{ "userVehicleId": "b2c3d4e5-…", "workshopId": "3f1e2d3c-…", "odoMilestone": 12000 }
```

| Field | Type | Required | Constraints |
|---|---|---:|---|
| `userVehicleId` | `uuid` | Yes | Thuộc user, active |
| `workshopId` | `uuid` | Yes | `active` |
| `odoMilestone` | `integer` | Yes | Có trong định mức của model |

> Mọi field khác (`items`, `price`, `total`…) bị **bỏ qua** (FF BR-1101, AC-1104). Không có `sourceMessageId` từ client — Orchestrator truyền nội bộ khi tạo từ chat.

## 3.2 Internal Processing

```text
1. Auth; load vehicle (owned, active); load workshop (active) → 422 WORKSHOP_INACTIVE.
2. est = CostEstimationService.estimate(vehicle, odoMilestone, workshop, today)   -- us-045
   est.status = NO_RULE → 422 NO_MAINTENANCE_RULE (EDGE-1101).
3. BEGIN
   INSERT quote(status='draft', user_vehicle_id, workshop_id, odo_milestone,
                estimated_total = est.chargeable_total, source_message_id = :ctx_msg_id)
   INSERT quote_item × N (maintenance_rule_id, item_code, item_name,
                is_covered_by_warranty = item.covered, price_source = item.price_source,
                estimated_price = item.price)
   COMMIT
4. Trả 201 + chi tiết (như API-QT-03).
```

## 3.3 Response `201 Created`

```json
{
  "data": {
    "quoteId": "7c1a…",
    "status": "DRAFT",
    "displayStatus": "DRAFT",
    "workshop": { "workshopId": "3f1e…", "name": "VinFast Smart City" },
    "odoMilestone": 12000,
    "items": [
      { "quoteItemId": "…a1", "itemCode": "BATTERY_CHECK", "itemName": "Kiểm tra pin cao áp", "covered": true, "priceSource": null, "estimatedPrice": 0, "approvedPrice": null, "reviewerNote": null },
      { "quoteItemId": "…a5", "itemCode": "BRAKE_FLUID_REPLACE", "itemName": "Thay dầu phanh", "covered": false, "priceSource": "REFERENCE_PRICE", "estimatedPrice": 350000, "approvedPrice": null, "reviewerNote": null }
    ],
    "estimatedTotal": 1300000,
    "approvedTotal": null,
    "priceLabel": "Chi phí ước tính",
    "createdAt": "2026-09-30T04:00:00Z",
    "submittedAt": null, "reviewedAt": null, "expiresAt": null, "reviewerNote": null,
    "bookingId": null
  }
}
```

---

# 4. API-QT-02 / API-QT-03 — đọc (chủ xe)

`GET /api/v1/quotes?userVehicleId=…&status=DRAFT&status=PENDING_APPROVAL…&limit=20&cursor=…` — sắp `created_at DESC`, keyset theo (`created_at`, `id`).

**`displayStatus` (suy ra ở backend, FF §13.1):**

| `status` | Điều kiện | `displayStatus` | `priceLabel` |
|---|---|---|---|
| `draft` | | `DRAFT` | "Chi phí ước tính" |
| `pending_approval` | | `PENDING_APPROVAL` | "Chi phí ước tính" |
| `approved` | `now < expires_at`, không dòng nào sửa | `APPROVED` | "Báo giá đã duyệt" |
| `approved` | `now < expires_at`, có dòng `approved_price ≠ estimated_price` | `MODIFIED` | "Báo giá đã duyệt" |
| `approved` | `now ≥ expires_at` | `EXPIRED` | "Đã hết hiệu lực" |
| `rejected` | | `REJECTED` | "Chi phí ước tính" |

`canAttachToBooking = displayStatus ∈ {APPROVED, MODIFIED} ∧ (bookingId IS NULL ∨ booking.status = cancelled)` — F6 dùng để hiện lựa chọn "Dùng báo giá đã duyệt".

---

# 5. API-QT-04 — `POST /api/v1/quotes/{quoteId}/submit`

## 5.1 Request

```json
{ "confirm": true }
```

Header `Idempotency-Key` khuyến nghị. Tool AI-005 gọi `QuoteService.submit(quote_id, confirmation_token)` — token cấp khi hiển thị `CARD-QUOTE`, dùng một lần (FF BR-1103).

## 5.2 Processing

```text
1. Load quote (owned) FOR UPDATE; status ≠ draft →
     pending_approval/approved/rejected: 200 trả trạng thái hiện tại (idempotent) nếu cùng Idempotency-Key, ngược lại 409 QUOTE_NOT_DRAFT.
2. workshop.status ≠ active → 422 WORKSHOP_INACTIVE.
3. now − created_at > QUOTE_DRAFT_REFRESH_HOURS →
     tính lại dự toán; nếu khác snapshot: thay dòng + estimated_total, trả 409 QUOTE_DRAFT_REFRESHED (client hiển thị lại, bấm gửi lần nữa) [Q-1104].
4. UPDATE quote SET status='pending_approval', submitted_at=now()
    WHERE id=:id AND status='draft';
   -- unique partial index uq_quote_pending (user_vehicle_id, workshop_id, odo_milestone) WHERE status='pending_approval'
   vi phạm unique → 409 QUOTE_ALREADY_PENDING + details.pendingQuoteId (EF-1101, BR-1104).
5. 200 + chi tiết.
```

---

# 6. API-QT-05 — `DELETE /api/v1/quotes/{quoteId}`

Chỉ `status = draft` ⇒ xoá cứng quote + items (`ON DELETE CASCADE`), `204`. Khác `draft` ⇒ `409 QUOTE_NOT_DRAFT` (EDGE-1109).

---

# 7. API-QT-11 / API-QT-12 — đọc (chủ xưởng)

`GET /api/v1/workshop-owner/quotes?status=PENDING_APPROVAL&from=&to=&limit=&cursor=` — mặc định `PENDING_APPROVAL`, sắp `submitted_at ASC` (chờ lâu nhất lên đầu). Mỗi dòng: `quoteId`, khách (`fullName`, `phone` — us-037 BR-813), `modelName`, `plateNumber`, `odoMilestone`, `estimatedTotal`, `submittedAt`, `waitingHours`, `isWaitingLong` (`waitingHours ≥ 24` — Q-1105), `hasConversation` (`source_message_id IS NOT NULL`).

`GET …/{quoteId}` — như API-QT-03 + khối `customer` + `conversationExcerptUrl` (`/api/v1/workshop/quotes/{quoteId}/conversation-excerpt` — API-CHAT-008) khi có. **Không** trả VIN, CCCD, email.

---

# 8. API-QT-13 — `POST /api/v1/workshop-owner/quotes/{quoteId}/approve`

## 8.1 Request Body

```json
{
  "validityDays": 7,
  "reviewerNote": "Giá dầu phanh theo bảng giá mới của xưởng.",
  "items": [
    { "quoteItemId": "…a5", "approvedPrice": 320000, "note": "Giá xưởng" }
  ]
}
```

| Field | Type | Required | Constraints |
|---|---|---:|---|
| `validityDays` | `integer` | No | `1..QUOTE_MAX_VALIDITY_DAYS`, default `QUOTE_DEFAULT_VALIDITY_DAYS` |
| `reviewerNote` | `string` | No | ≤ 500 |
| `items[]` | array | No | Chỉ các dòng muốn sửa; dòng không nêu ⇒ `approved_price = estimated_price` |
| `items[].quoteItemId` | `uuid` | Yes | Thuộc quote |
| `items[].approvedPrice` | `number` | Yes | `≥ 0`, tối đa 2 chữ số thập phân; dòng `covered = true` phải = 0 (Q-1103) |
| `items[].note` | `string` | No | ≤ 255 |

## 8.2 Processing (một transaction)

```text
1. Load quote FOR UPDATE; kiểm quyền (BR-1110); status ≠ pending_approval → 409 QUOTE_ALREADY_REVIEWED + details.status (EF-1102).
2. Validate items: thuộc quote, không trùng id; covered ⇒ approvedPrice = 0 else 422 COVERED_ITEM_LOCKED.
3. UPDATE quote_item SET approved_price = COALESCE(:given, estimated_price), reviewer_note = :note.
4. approved_total = Σ approved_price (BR-ENT-414).
5. UPDATE quote SET status='approved', approved_total, reviewed_by=:owner_id, reviewed_at=now(),
                   expires_at = now() + validityDays, reviewer_note
    WHERE id=:id AND status='pending_approval'.
6. COMMIT → phát sự kiện `quote.reviewed` (in-app notification, BR-1109).
```

## 8.3 Response `200 OK` — chi tiết như API-QT-12 với `displayStatus = APPROVED | MODIFIED`.

---

# 9. API-QT-14 — `POST /api/v1/workshop-owner/quotes/{quoteId}/reject`

```json
{ "reviewerNote": "Xe cần kiểm tra pin trước khi báo giá." }
```

`reviewerNote` bắt buộc, 10–500 ký tự (BR-1107) ⇒ thiếu: `422 REVIEWER_NOTE_REQUIRED`. Cập nhật `status='rejected'`, `reviewed_by`, `reviewed_at`, `reviewer_note` với điều kiện `status='pending_approval'` (EF-1102). Phát `quote.reviewed`.

---

# 10. HOOK-QT-01 — gắn vào booking (gọi từ F6 `POST /bookings`)

```sql
UPDATE quote
   SET booking_id = :booking_id, updated_at = now()
 WHERE id = :quote_id
   AND user_vehicle_id = :vehicle AND workshop_id = :workshop
   AND status = 'approved' AND now() < expires_at
   AND (booking_id IS NULL OR booking_id IN (SELECT id FROM booking WHERE status = 'cancelled'))
RETURNING approved_total;
```

0 dòng ⇒ F6 trả `409 QUOTE_EXPIRED` / `QUOTE_NOT_ATTACHABLE` và **không** tạo booking kèm báo giá (chủ xe có thể đặt không kèm). Thành công ⇒ `booking.estimated_cost = approved_total` trong **cùng transaction** tạo booking (BR-1108, BR-ENT-404).

**HOOK-QT-02:** `UPDATE quote SET booking_id = NULL WHERE booking_id = :booking_id` — gọi trong transaction huỷ booking (us-033 BR-709, us-037 BR-804/806, F6b đổi xưởng).

---

# 11. Thông báo trong app (BR-1109)

MVP **không** tạo bảng thông báo in-app riêng. Badge "Báo giá có kết quả" trên Home suy ra từ `quote.result_seen_at`:

- `GET /api/v1/quotes?unseenResult=true` ⇒ các quote `approved`/`rejected` có `result_seen_at IS NULL`.
- Chủ xe mở `API-QT-03` của quote đã có kết quả ⇒ backend ghi `result_seen_at = now()` (idempotent).
- AI-005 đọc cùng trường để báo kết quả khi chủ xe quay lại chat.

Không gửi Discord (Q-1101).

---

# 12. Error Handling

```json
{ "error": { "code": "QUOTE_ALREADY_PENDING", "message": "Bạn đã gửi báo giá này cho xưởng.", "details": { "pendingQuoteId": "…" }, "traceId": "…" } }
```

| Case | Error Code | HTTP | Ref |
|---|---|---:|---|
| Body sai | `INVALID_REQUEST` | `400` | |
| Chưa xác thực | `UNAUTHORIZED` | `401` | |
| Không có quyền vai trò | `FORBIDDEN` | `403` | |
| Không thấy / không thuộc | `QUOTE_NOT_FOUND` | `404` | BR-1110, AC-1106 |
| Xe không thuộc user | `VEHICLE_NOT_FOUND` | `404` | |
| Xưởng không active | `WORKSHOP_INACTIVE` | `422` | BR-1102, EF-1103 |
| Không có định mức | `NO_MAINTENANCE_RULE` | `422` | EDGE-1101 |
| Không còn là nháp | `QUOTE_NOT_DRAFT` | `409` | EDGE-1109 |
| Nháp được lập lại snapshot | `QUOTE_DRAFT_REFRESHED` | `409` | EF-1104 |
| Trùng chờ duyệt | `QUOTE_ALREADY_PENDING` | `409` | BR-1104 |
| Đã được xử lý | `QUOTE_ALREADY_REVIEWED` | `409` | EF-1102 |
| Sửa dòng bảo hành | `COVERED_ITEM_LOCKED` | `422` | Q-1103 |
| Thiếu lý do từ chối | `REVIEWER_NOTE_REQUIRED` | `422` | BR-1107 |
| Lỗi hệ thống | `INTERNAL_SERVER_ERROR` | `500` | |

---

# 13. Database / Entity Interaction

| Entity | Operation | Purpose |
|---|---|---|
| `quote` | Insert / Read / Update / Delete (draft) | Báo giá |
| `quote_item` | Insert / Read / Update | Dòng snapshot, giá duyệt |
| `maintenance_rule`, `service_price`, `vehicle_warranty` | Read (qua F5) | Snapshot |
| `workshop`, `workshop_owner` | Read | Quyền duyệt |
| `booking` | Read / Update (qua hook F6) | Gắn báo giá |
| `chat_message` | Read | Excerpt |

---

# 14. Concurrency

- Gửi: unique partial index chặn hai `pending_approval` cùng khoá dù gửi đồng thời.
- Duyệt/từ chối: `UPDATE … WHERE status='pending_approval'` + `SELECT … FOR UPDATE` ⇒ chỉ một thao tác thắng.
- Gắn booking: câu `UPDATE … WHERE booking_id IS NULL …` nằm trong transaction tạo booking; hai booking đồng thời dùng cùng báo giá ⇒ chỉ một gắn được.

---

# 15. Observability

- Log `quote.created|submitted|approved|rejected|attached|detached` với `trace_id`, `quote_id`, `workshop_id`, `actor`, `duration_ms`.
- Metric `quote_review_latency_hours` (submitted → reviewed) — số liệu cho PRD §10 "Thời gian duyệt báo giá (median)".

# 16. Performance

Mọi API `< 500 ms` (p90). Index: `quote(workshop_id, status, submitted_at)`, `quote(user_vehicle_id, created_at)`, partial unique pending.

---

# 17. Test Checklist

- [ ] Tạo nháp bỏ qua giá client (AC-1104); `estimated_total` = `chargeable_total` F5.
- [ ] Gửi trùng ⇒ `409 QUOTE_ALREADY_PENDING` (AC-1107), kể cả 2 request song song.
- [ ] Duyệt sửa giá ⇒ `approved_total` đúng (AC-1105); dòng covered ≠ 0 ⇒ `422`.
- [ ] Từ chối không lý do ⇒ `422`; có lý do ⇒ chủ xe thấy nguyên văn (AC-1102).
- [ ] Gắn booking: hết hạn / khác xưởng ⇒ không gắn (AC-1101); huỷ booking ⇒ gỡ liên kết.
- [ ] Chủ xưởng X đọc quote xưởng Y ⇒ `404` (AC-1106); không thấy `draft`.
- [ ] Job dọn nháp chỉ xoá `draft` quá hạn.

---

# 18. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu |

# 19. References

- [FF us-049](../feature-functional/us-049-sprint-3-spec.ff.md) · [Entity us-049](../entity/us-049-sprint-3-spec.entity.md) · [FE us-049](../frontend/us-049-sprint-3-spec.fe.md)
- [AI-005](../../ai-agent/ai-005-sprint-3-spec.agent.md) · [us-045 API](../../sprint-2/api/us-045-sprint-2-spec.api.md) · [us-029 API](us-029-sprint-3-spec.api.md) · [us-025 API](../../sprint-2/api/us-025-sprint-2-spec.api.md)
