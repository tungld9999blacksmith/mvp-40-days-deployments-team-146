# API Technical Specification — Báo giá phát sinh khi thay phụ tùng

> Backend cho Feature `FEAT-P2-AD04`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-04-phase2-spec.ff.md). **Entity:** [Entity Spec](ad-04-phase2-spec.entity.md) — xây trên `booking_line` (Q-ENT-AD04-01).
>
> **Tái dùng:** module `booking_line` (báo giá hai tầng: `POST …/line-photos`, `…/lines/{lineId}/decision`, `…/phone-decision`, `…/withdraw`, `settlement.py`, `cards.py`), `CostEstimationService` / `service_price` (giá dòng — tool tính, không LLM), RAG có nguồn (giải thích), `WorkshopActor` + quyền `DRAFT_EXTRA` (WS-03), thẻ `EXTRA_QUOTE` (CH-02), thông báo trong app.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-AD04` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/booking_line/extra_quote.py` (mới), route bổ sung trong `booking_line/route.py`; `agents/tools/extra_quote_tools.py` (soạn giải thích) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-AD04-01` | `POST` | `/workshop/bookings/{bookingId}/extra-quotes` | Tạo nháp (KTV hoặc chủ xưởng) | UC-AD04-01, BR-AD04-02 |
| `API-AD04-02` | `GET` | `/workshop/bookings/{bookingId}/extra-quotes` | Danh sách phát sinh của lịch (phía xưởng) | — |
| `API-AD04-03` | `GET` | `/workshop-owner/extra-quotes?status=PENDING_APPROVAL` | Hàng đợi duyệt (SCR-AD04-02) | UC-AD04-02 |
| `API-AD04-04` | `POST` | `/workshop-owner/extra-quotes/{quoteId}/approve` | Duyệt (có thể sửa giá / giải thích) ⇒ gửi chủ xe | UC-AD04-02, BR-AD04-03 |
| `API-AD04-05` | `POST` | `/workshop-owner/extra-quotes/{quoteId}/reject` | Từ chối nháp | UC-AD04-02 |
| `API-AD04-06` | `POST` | `/workshop-owner/extra-quotes/{quoteId}/phone-decision` | Ghi đồng ý / từ chối qua điện thoại | EDGE-AD04-02 |
| `API-AD04-07` | `GET` | `/bookings/{bookingId}/extra-quotes/{quoteId}` | Chủ xe xem (ảnh, giải thích, giá, tổng cũ → mới) | SCR-AD04-03 |
| `API-AD04-08` | `POST` | `/bookings/{bookingId}/extra-quotes/{quoteId}/decision` | Chủ xe: Đồng ý / Không thay / Gọi cho xưởng | UC-AD04-03, BR-AD04-05 |
| `JOB-AD04-01` | Celery | `extra_quote.timeouts` (mỗi phút) | Hết `EXTRA_TIMEOUT_MIN` ⇒ `awaiting_owner` hoặc chấp nhận vì không phản đối | UC-AD04-04 |
| `TOOL-AD04-01` | Agent (nội bộ) | `draft_extra_explanation` | Soạn giải thích từ lý do + tài liệu | BR-AD04-02 |

`/workshop/…` = endpoint dùng chung chủ xưởng + KTV (`WorkshopActor`, WS-03 §2). Trước khi có WS-03, chỉ chủ xưởng gọi được (Q-AD04-02).

---

# 2. Authorization & Guards

1. `API-AD04-01/02`: `WorkshopActor` của xưởng của lịch; KTV cần `DRAFT_EXTRA` **và** lịch được giao cho mình.
2. `API-AD04-03..06`: chỉ chủ xưởng (KTV không duyệt, FF §16).
3. `API-AD04-07/08`: chủ xe của booking. Phát sinh ở `draft` / `pending_approval` / `rejected` ⇒ `404 EXTRA_QUOTE_NOT_FOUND` với chủ xe (chưa được gửi).
4. Khoá Redis `extra-quote:{quoteId}` cho approve / reject / decision / phone-decision / job (ai đến trước quyết định).

---

# 3. API-AD04-01 — tạo nháp

## 3.1 Request

```json
{ "items": [ { "itemCode": "TIRE_235_55R19", "quantity": 1 }, { "itemCode": "WHEEL_BALANCE", "quantity": 1 } ],
  "urgency": "SAFETY", "reason": "Lốp sau trái phồng hông", "photoIds": ["p1…", "p2…"] }
```

| Field | Validation |
|---|---|
| `items` | 1–10; `itemCode` có trong `service_price` của xưởng cho model xe, hoặc danh mục phụ tùng chuẩn (giá tham khảo, `priceSource = REFERENCE`) |
| `urgency` | `SAFETY`, `RECOMMENDED`, `DEFERRABLE` |
| `reason` | 5–300 ký tự |
| `photoIds` | ≥ 1 (EF-AD04-01) — ảnh đã tải qua `POST /workshop-owner/bookings/{bookingId}/line-photos` (mở cho `WorkshopActor`), cùng booking |

## 3.2 Processing

1. Lịch phải `checked_in` hoặc `in_progress` ⇒ không thì `409 BOOKING_NOT_IN_SERVICE` (EF-AD04-03).
2. Tính giá từng dòng bằng tool giá (cùng nguồn `service_price` / tham khảo như F5) — không LLM.
3. Một transaction: `extra_quote` (`draft`), các `booking_line` `kind = EXTRA`, `line_status = DRAFT`, `extra_quote_id`, `reason`, `is_safety_critical = urgency == SAFETY`, `proposed_by` (actor); gắn ảnh vào dòng đầu (ảnh dùng chung cho nhóm, trả về ở mức nhóm).
4. Chuyển `pending_approval` ngay và đẩy job `extra_quote.explain` (TOOL-AD04-01, ≤ 10 s).
5. **Tự duyệt** (BR-AD04-03, AF-AD04-02): `workshop.auto_approve_extra_vnd` có giá trị và `this_total` < giá trị đó và `urgency ≠ SAFETY` ⇒ chờ giải thích xong (hoặc timeout 10 s ⇒ dùng câu mẫu từ `reason`) rồi chạy §4 với `auto_approved = true`.
6. Thông báo chủ xưởng "Phát sinh mới chờ duyệt" (khi không tự duyệt). Log KTV (`EXTRA_DRAFTED`).

Response `201` `ExtraQuoteDto` (§7).

---

# 4. API-AD04-04 — duyệt ⇒ gửi chủ xe

Body (tuỳ chọn): `{ "lines": [ { "lineId": "…", "unitPrice": "2400000" } ], "explanation": "…", "expectedVersion": 2 }`.

1. Trạng thái phải `pending_approval` ⇒ không thì `409 EXTRA_QUOTE_INVALID_STATE`.
2. Áp sửa giá (giá xưởng duyệt, BR-AD04-07: không nhãn "ước tính") và giải thích (`explanation_source = AGENT_EDITED` / `MANUAL`).
3. Tính `baseline_total`, `extras_before` (Σ dòng `EXTRA` `APPROVED` của lịch), `this_total`, `consent_required` (entity §2–3).
4. Một transaction: `sent_to_owner`, `approved_by_owner_id` (hoặc `auto_approved`), `sent_at`, `respond_by = now + EXTRA_TIMEOUT_MIN`; dòng ⇒ `PROPOSED`, `confirmed_price` = giá duyệt; `version + 1`.
5. Sau commit: lưu tin trợ lý vào hội thoại gần nhất của xe (hoặc tạo hội thoại "Xưởng {tên}") với thẻ `EXTRA_QUOTE` (CH-02, `entity = { type: EXTRA_QUOTE, id }`); thông báo đẩy "Xưởng cần bạn xác nhận hạng mục phát sinh" (≤ 1 phút, FF §18). `consent_required = false` ⇒ thông báo ghi "Xưởng sẽ làm nếu bạn không phản đối trong {EXTRA_TIMEOUT_MIN} phút".

`API-AD04-05` (reject): `pending_approval` ⇒ `rejected`; dòng ⇒ `WITHDRAWN`; báo người tạo. Body `{ "note": "…" }` bắt buộc.

---

# 5. API-AD04-08 — quyết định của chủ xe

## 5.1 Request

```json
{ "decision": "ACCEPT", "lineDecisions": null, "version": 3, "confirmSafetyDecline": false }
```

| `decision` | Ý nghĩa |
|---|---|
| `ACCEPT` | Đồng ý mọi dòng |
| `DECLINE` | Không thay lần này (mọi dòng) |
| `PER_LINE` | Theo `lineDecisions: [{ lineId, approve: bool }]` |
| `CALL_WORKSHOP` | Muốn gọi (AF-AD04-03): không đổi dòng; ghi `owner_wants_call_at`; trả hotline xưởng; Board nhãn "Khách muốn gọi" |

## 5.2 Processing

1. Trạng thái phải `sent_to_owner` hoặc `awaiting_owner` ⇒ không thì `409 EXTRA_QUOTE_INVALID_STATE` (`details.status`). `version` lệch ⇒ `409 EXTRA_QUOTE_CHANGED` (giá đã đổi, thẻ tải lại).
2. Từ chối dòng `SAFETY` mà `confirmSafetyDecline = false` ⇒ `422 SAFETY_DECLINE_CONFIRMATION_REQUIRED` (`details.message` = cảnh báo "không nên lái xe…", AF-AD04-01).
3. Áp quyết định cho từng dòng qua `settlement.py` có sẵn (`decided_by`, `decided_at`, `decided_via = APP`); nhóm ⇒ `accepted` / `declined` / `partially_accepted`.
4. Dòng `APPROVED` ⇒ thêm vào lịch (tổng mới), tiến độ xưởng hiện "Khách đã đồng ý" (us-057 thêm ghi chú hệ thống). Dòng `DECLINED` ⇒ khuyến nghị chưa làm (HS-01 tự đọc, AC-AD04-03); nhắc lại ở lần đặt lịch sau qua PS-01 `vehicle_issue` (`source = FEEDBACK`) khi có đồng ý bộ nhớ.
5. Thông báo xưởng + KTV được giao.

---

# 6. API-AD04-06 — đồng ý qua điện thoại (EDGE-AD04-02)

Body `{ "decision": "ACCEPT" | "DECLINE" | "PER_LINE", "lineDecisions": …, "phoneConfirmedBy": "Nguyễn Văn A (CVDV)", "note": "Khách đồng ý lúc 10:05" }`. `phoneConfirmedBy` bắt buộc (CHECK có sẵn `ck_booking_line_phone_confirmer`). `decided_via = PHONE`, `recorded_by` = chủ xưởng. Hợp lệ ở `sent_to_owner` / `awaiting_owner`. Chủ xe nhận thông báo "Xưởng đã ghi nhận bạn đồng ý qua điện thoại" để phát hiện ghi sai (dùng `dispute` có sẵn của `booking_line`).

---

# 7. `ExtraQuoteDto`

```json
{ "quoteId": "…", "bookingId": "…", "status": "SENT_TO_OWNER", "urgency": "SAFETY",
  "reason": "Lốp sau trái phồng hông", "explanation": "Lốp sau trái bị phồng hông, có nguy cơ nổ lốp khi chạy nhanh. Đề xuất thay 1 lốp.",
  "citations": [], "photos": [ { "photoId": "…", "url": "https://…signed…" } ],
  "lines": [ { "lineId": "…", "itemName": "Lốp 235/55R19", "quantity": 1, "unitPrice": "2400000", "lineStatus": "PROPOSED", "isSafetyCritical": true },
             { "lineId": "…", "itemName": "Cân bằng động", "quantity": 1, "unitPrice": "100000", "lineStatus": "PROPOSED", "isSafetyCritical": true } ],
  "thisTotal": "2500000", "totalBefore": "1400000", "totalAfter": "3900000",
  "consentRequired": true, "respondBy": "…", "workshopHotline": "1900…", "version": 3,
  "createdBy": { "type": "technician", "name": "An" }, "approvedBy": "MANUAL" }
```

`totalBefore` = `baseline_total + extras_before`; `totalAfter` = `totalBefore + thisTotal`. Chủ xe chỉ thấy tên gọi KTV (BR-WS03-07).

---

# 8. JOB-AD04-01 — hết thời gian

| Điều kiện | Việc |
|---|---|
| `sent_to_owner`, `now ≥ respond_by`, `consent_required = true` | `awaiting_owner`; Board nhãn "Chờ khách" + nút gọi; thông báo xưởng "Gọi khách xác nhận"; nhắc chủ xe một lần. **Không** đổi dòng (EF-AD04-02, AC-AD04-01) |
| `sent_to_owner`, `now ≥ respond_by`, `consent_required = false` | Không có phản đối ⇒ dòng `APPROVED`, `decided_via = NO_OBJECTION`; nhóm `accepted`; thông báo chủ xe "Xưởng đã thêm {hạng mục}" (AF-AD04-02) |

---

# 9. TOOL-AD04-01 — `draft_extra_explanation`

| | |
|---|---|
| Vào | `reason`, `urgency`, tên hạng mục, model xe; truy hồi RAG theo hạng mục (tài liệu hãng) |
| Ra | 1–3 câu tiếng Việt dễ hiểu, ≤ 400 ký tự, + `citations` khi dùng tài liệu |
| Ràng buộc | Không nêu giá, không hứa bảo hành, không phóng đại mức nguy hiểm vượt `urgency`; guard đầu ra hiện có kiểm số tiền / cam kết bảo hành ⇒ loại câu vi phạm, dùng câu mẫu từ `reason` |
| Lỗi / timeout 10 s | Câu mẫu: "{reason}. Xưởng đề xuất {danh sách hạng mục}." `explanation_source = MANUAL` |

---

# 10. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 400 | `INVALID_REQUEST` | Thiếu ảnh / lý do / `items` sai |
| 403 | `PERMISSION_DENIED` | KTV không có `DRAFT_EXTRA` hoặc không được giao lịch |
| 404 | `EXTRA_QUOTE_NOT_FOUND` | Ngoài phạm vi / chủ xe xem nháp |
| 409 | `BOOKING_NOT_IN_SERVICE` | Lịch chưa check-in hoặc đã `completed` |
| 409 | `EXTRA_QUOTE_INVALID_STATE` | Sai trạng thái |
| 409 | `EXTRA_QUOTE_CHANGED` | `version` lệch |
| 422 | `SAFETY_DECLINE_CONFIRMATION_REQUIRED` | Từ chối hạng mục an toàn chưa xác nhận lần hai |

---

# 11. Observability

Log `extra_quote.created` (`urgency`, `lines`, `actor`), `extra_quote.sent` (`consent_required`, `auto_approved`, `ms_since_created`), `extra_quote.decided` (`decision`, `via`, `ms_since_sent`), `extra_quote.timeout`. Metric: thời gian chờ khách đồng ý (đóng góp T₅, M-09).

---

# 12. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `consent_required` cộng dồn nhiều phát sinh (EDGE-AD04-01); `baseline_total = 0` ⇒ luôn hỏi | +4 |
| Service | Không ảnh ⇒ `400`; lịch `completed` ⇒ `409` | +2 |
| Service | Vượt ngưỡng: timeout ⇒ `awaiting_owner`, dòng vẫn `PROPOSED` — không bao giờ `APPROVED` khi chưa đồng ý (AC-AD04-01) | +2 |
| Service | Dưới ngưỡng: timeout ⇒ `APPROVED` `NO_OBJECTION` | +1 |
| Service | Mọi phát sinh đã gửi có ảnh và người duyệt hoặc `auto_approved` (AC-AD04-02) | +1 |
| Service | Không thay ⇒ dòng `DECLINED` hiện ở HS-01 `deferred` (AC-AD04-03) | +1 |
| Service | Từ chối hạng mục an toàn cần xác nhận lần hai | +1 |
| Service | Ghi đồng ý qua điện thoại bắt buộc người ghi | +1 |
| Security | KTV không duyệt được; chủ xe không thấy nháp | +2 |
| Agent | Giải thích không chứa số tiền / cam kết bảo hành; lỗi ⇒ câu mẫu | +2 |

---

# 13. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
