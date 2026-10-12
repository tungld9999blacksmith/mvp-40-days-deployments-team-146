# API Technical Specification — Chính sách huỷ lịch và lỡ hẹn

> Backend cho Feature `FEAT-P2-BK02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-02-phase2-spec.ff.md). **Entity:** [Entity Spec](bk-02-phase2-spec.entity.md).
>
> **Tái dùng:** điểm vào huỷ MVP `POST /bookings/{bookingId}/cancel` (us-053) và `POST /workshop-owner/bookings/{bookingId}/transitions` (us-037) — **không** thêm endpoint huỷ mới; `BookingStateMachine.transition` (ghi `booking_status_event`); `POST /bookings/{bookingId}/attendance-confirmation` (us-033); thông báo trong app (NOTI). BK-02 chỉ thêm phân loại, sổ cái và các màn đọc.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-BK02` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/reliability/` (mới): `policy.py` (hàm thuần: phân loại, điểm, bậc), `service.py`, `route.py`, `jobs.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-BK02-01` | `GET` | `/bookings/{bookingId}/cancel-preview` | Nói trước lần huỷ có bị tính không (SCR-BK02-01) | BR-BK02-07, AC-BK02-05 |
| `API-BK02-02` | `POST` | `/bookings/{bookingId}/cancel` (sửa) | Huỷ + phân loại + sự kiện | UC-BK02-01 |
| `API-BK02-03` | `POST` | `/bookings/{bookingId}/arrival-response` | Trả lời "Bạn có đang tới không?" | AF-BK02-02 |
| `API-BK02-04` | `GET` | `/reliability` | Điểm, bậc, sự kiện của chủ xe (SCR-BK02-02) | AC-BK02-03 |
| `API-BK02-05` | `POST` | `/reliability/events/{eventId}/appeal` | Khiếu nại | UC-BK02-03 |
| `API-BK02-06` | `POST` | `/workshop-owner/bookings/{bookingId}/no-show` | Xưởng đánh dấu "Khách không đến" | UC-BK02-02 |
| `API-BK02-07` | `POST` | `/workshop-owner/bookings/{bookingId}/no-show/undo` | Hoàn tác (24 giờ) / khôi phục khi xe đến muộn | EDGE-BK02-06, EF-BK02-02 |
| `API-BK02-08` | `GET` | `/workshop-owner/reliability-appeals` | Hàng đợi khiếu nại của xưởng | SCR-BK02-03 |
| `API-BK02-09` | `POST` | `/workshop-owner/reliability-appeals/{appealId}/decision` | Chấp nhận / từ chối | BR-BK02-09 |
| `HOOK-BK02-01` | Internal | `ReliabilityService.on_booking_cancelled(...)` | Mọi đường huỷ đi qua đây | BR-BK02-04, BR-BK02-06 |
| `SVC-BK02-01` | Internal | `ReliabilityService.tier(user_id)`, `workshop_factor(workshop_id)` | BK-01, WS-01 đọc | BR-BK02-03, 06 |
| `JOB-BK02-01` | Celery | `reliability.no_show_watch` (mỗi phút) | Hỏi ở mốc ân hạn; tự đánh dấu | EF-BK02-01 |
| `JOB-BK02-02` | Celery | `reliability.daily_recompute` | Hết hạn sự kiện, hạ bậc, thông báo | AC-BK02-04 |
| `JOB-BK02-03` | Celery | `reliability.appeal_timeout` (mỗi 15 phút) | Tự chấp nhận sau 72 giờ | AC-BK02-06 |
| `JOB-BK02-04` | Celery | `reliability.must_confirm_release` (mỗi 15 phút) | Bậc Cần xác nhận: trả chỗ khi chưa xác nhận 12 giờ trước | BR-BK02-03 |

---

# 2. Authorization & Guards

1. `API-BK02-01..05`: chủ xe, chỉ booking / sự kiện của mình ⇒ không thì `404`.
2. `API-BK02-06..09`: chủ xưởng, booking thuộc xưởng mình. KTV (WS-03) **được** đánh dấu lỡ hẹn khi có quyền check-in (WS-03 permission `CHECK_IN`), không được quyết định khiếu nại.
3. Chủ xưởng không bao giờ nhận `score` hay danh sách sự kiện của khách ngoài xưởng mình; chỉ nhận `tier` (BR §16, Q-BK02-03).

---

# 3. SVC / HOOK — `ReliabilityService`

## 3.1 `classify(booking, actor, now, context) → CancelReason` (hàm thuần, `policy.py`)

Thứ tự (BR-ENT-BK02-02):

1. `actor = workshop_owner` hoặc reason phía xưởng ⇒ `workshop_cancel`.
2. `context.source ∈ {PROACTIVE_EXPIRE, RESCHEDULE_OTHER_WORKSHOP, WS_CONFIRM_TIMEOUT, ATTENDANCE_RELEASE}` ⇒ giá trị tương ứng.
3. `booking.status = pending` và `now < hold_expires_at` (giữ chỗ us-029) ⇒ `hold_released`.
4. `booking.auto_booked` và `now < free_cancel_until` ⇒ `auto_book_free_cancel`.
5. `starts_at − now ≥ LATE_CANCEL_HOURS` ⇒ `early_cancel`; còn lại ⇒ `late_cancel`.

## 3.2 `on_booking_cancelled(booking, reason, actor, now)` — HOOK-BK02-01

Gọi **bên trong** transaction của mọi đường chuyển sang `cancelled` (`BookingService.cancel`, `workshop_board` transitions, jobs BK-01 / WS-02, `replace_booking`). Một chỗ duy nhất: thêm vào `BookingStateMachine.transition` khi `to = cancelled` (tham số mới `cancel_reason` bắt buộc).

- `late_cancel` ⇒ chèn `owner_reliability_event (LATE_CANCEL, LATE_CANCEL_WEIGHT)`, `reason` = "Huỷ lúc HH:mm dd/MM, còn X giờ Y phút tới giờ hẹn". Unique index chặn sự kiện thứ hai cho cùng lịch (BR-BK02-10).
- `workshop_cancel` và lịch đang `confirmed` và `starts_at − now < LATE_CANCEL_HOURS` ⇒ `workshop_reliability_event (LATE_WORKSHOP_CANCEL)` (BR-BK02-06). Chủ xe được BK-01 AF-BK01-08 (nếu đi qua `unable-to-serve`) hoặc thông báo huỷ MVP.
- `ws_confirm_timeout` ⇒ `workshop_reliability_event (CONFIRM_TIMEOUT)`.
- Cập nhật `owner_reliability_state` (§3.3); bậc tăng ⇒ thông báo (BR-BK02-07) **trước** lần đặt lịch kế tiếp có hiệu lực của bậc mới (thông báo gửi ngay, bậc áp dụng từ lúc ghi).
- Mời danh sách chờ (BK-07) cho chỗ vừa trả — sau commit.

## 3.3 Điểm và bậc

`score = Σ points` (entity §3), làm tròn 0,1; `tier` theo `RELIABILITY_TIERS`. `tier(user_id)` đọc `owner_reliability_state` (không có dòng ⇒ `NORMAL`). Lỗi đọc ⇒ `NORMAL` + log (không chặn chủ xe vì lỗi hệ thống).

## 3.4 Áp bậc

| Bậc | Nơi áp | Cách |
|---|---|---|
| `SOFT_REMINDER` | Màn xác nhận đặt lịch, thẻ chat | `BookingOut.policyNotice = "SOFT_REMINDER"` |
| `MUST_CONFIRM` | Mọi lịch `confirmed` của chủ xe | Không thêm cột: `BookingOut.attendanceRequired = (tier == MUST_CONFIRM)`; nút "Xác nhận sẽ đến" dùng `attendance_confirmed_at` có sẵn (us-033); JOB-BK02-04 trả chỗ khi chưa xác nhận |
| `RESTRICTED` | BK-01 lọc (BK-01 API §4.2 bước 6), WS-01 chuyển duyệt tay kèm lý do `RELIABILITY_TIER` | `SVC-BK02-01` |

---

# 4. API-BK02-01 — `GET /bookings/{bookingId}/cancel-preview`

```json
{ "data": { "classification": "LATE_CANCEL", "counted": true, "points": 0.5,
            "remainingMinutes": 150, "lateCancelHours": 24,
            "message": "Còn 2 giờ 30 phút tới giờ hẹn. Huỷ bây giờ được tính là huỷ muộn (0,5 điểm).",
            "suggestReschedule": true, "scoreAfter": 0.5, "tierAfter": "NORMAL" } }
```

`classification` = kết quả `classify` với `now` máy chủ. `counted = false` ⇒ `message` = "Huỷ trước 24 giờ không bị tính" hoặc lý do miễn ("Huỷ trong 2 giờ sau khi hệ thống tự đặt không bị tính"). Booking không huỷ được (trạng thái) ⇒ `409 INVALID_BOOKING_STATE`.

Preview có thể lệch nếu chủ xe để hộp mở qua mốc 24 giờ; `API-BK02-02` luôn phân loại lại. Response huỷ trả phân loại thực tế.

---

# 5. API-BK02-02 — `POST /bookings/{bookingId}/cancel` (sửa)

Request MVP giữ nguyên, thêm tuỳ chọn:

```json
{ "reason": "...", "forceMajeure": { "note": "Xe bị tai nạn trên đường" } }
```

Xử lý: luồng huỷ us-053 + `classify` + HOOK-BK02-01 trong cùng transaction. `forceMajeure` có và phân loại `late_cancel` ⇒ tạo sự kiện **và** `reliability_appeal (FORCE_MAJEURE, pending)` ngay (BR-BK02-04: chủ xưởng chấp nhận mới miễn).

Response MVP thêm:

```json
{ "cancellation": { "classification": "LATE_CANCEL", "counted": true, "points": 0.5, "eventId": "…", "appealId": null, "tier": "NORMAL" } }
```

---

# 6. API-BK02-03 — `POST /bookings/{bookingId}/arrival-response`

`{ "answer": "ON_THE_WAY" | "NOT_COMING" }`

- Chỉ hợp lệ khi đã gửi câu hỏi (`no_show_prompted_at` có) và lịch chưa check-in, chưa `cancelled` ⇒ không thì `409 ARRIVAL_PROMPT_INACTIVE`.
- `ON_THE_WAY` ⇒ `grace_extended_until = starts_at + NO_SHOW_GRACE_MIN + 15'` nếu chưa gia hạn (một lần, AF-BK02-02); thông báo xưởng "Khách {mã} báo đang tới". Đã gia hạn ⇒ `200` không đổi.
- `NOT_COMING` ⇒ coi như chủ xe huỷ ngay: `late_cancel` (không phải `no_show`, vì chủ xe đã báo).

---

# 7. Lỡ hẹn

## 7.1 API-BK02-06 — `POST /workshop-owner/bookings/{bookingId}/no-show`

1. Lịch `confirmed` (chưa check-in) và `now ≥ coalesce(grace_extended_until, starts_at + NO_SHOW_GRACE_MIN)` ⇒ không thì `409 NO_SHOW_TOO_EARLY` (`details.allowedAt`) / `409 INVALID_BOOKING_STATE`.
2. Một transaction: `cancelled`, `cancel_reason = no_show`, `reason_code = NO_SHOW`, `no_show_marked_at = now`; sự kiện `NO_SHOW (+1)` actor `workshop_owner`.
3. Thông báo chủ xe kèm nút "Khiếu nại" (hạn `NO_SHOW_APPEAL_HOURS`).

## 7.2 API-BK02-07 — `POST …/no-show/undo`

`{ "mode": "UNDO" | "VEHICLE_ARRIVED" }`

- Trong 24 giờ sau `no_show_marked_at` ⇒ không thì `409 UNDO_WINDOW_PASSED`.
- `UNDO` (đánh dấu nhầm): sự kiện ⇒ `waived` + `WAIVER`; lịch giữ `cancelled`, `cancel_reason` đổi thành `workshop_cancel`.
- `VEHICLE_ARRIVED` (EF-BK02-02, chỉ cùng ngày hẹn): sự kiện ⇒ `waived` + `WAIVER`; lịch khôi phục `cancelled → checked_in` bằng chuyển trạng thái đặc biệt `restore_no_show` (thêm vào `state_machine.py`, chỉ cho phép khi `cancel_reason = no_show`, actor xưởng) + kiểm tra sức chứa (WS-02 `fits` với giờ hiện tại); không đủ chỗ ⇒ `409 SLOT_FULL` và chủ xưởng xử lý như khách vãng lai.

## 7.3 JOB-BK02-01 — `reliability.no_show_watch`

| Mốc | Việc |
|---|---|
| `now ≥ starts_at + NO_SHOW_GRACE_MIN` (hoặc `grace_extended_until`), chưa check-in, chưa hỏi | Gửi "Bạn có đang tới không?" (push trong app + kênh ưu tiên) với 2 nút → `API-BK02-03`; ghi `no_show_prompted_at` (≤ 1 phút sau mốc, FF §18) |
| `now ≥ starts_at + NO_SHOW_AUTO_MARK_MIN` (dời theo gia hạn), chưa check-in, chưa đánh dấu | Tự đánh dấu như §7.1 với actor `system` (EF-BK02-01) |
| BK-08 báo trễ còn hiệu lực | Mốc tính từ giờ đến mới (`grace_extended_until` do BK-08 ghi) |

`SELECT … FOR UPDATE SKIP LOCKED`, idempotent theo cột mốc.

---

# 8. Sổ cái & khiếu nại

## 8.1 API-BK02-04 — `GET /reliability`

```json
{
  "data": {
    "score": 1.5, "tier": "SOFT_REMINDER", "nextExpiryAt": "2026-12-01T00:00:00Z",
    "tiers": [ { "code": "NORMAL", "min": 0 }, { "code": "SOFT_REMINDER", "min": 1 }, { "code": "MUST_CONFIRM", "min": 2 }, { "code": "RESTRICTED", "min": 3 } ],
    "events": [
      { "eventId": "…", "kind": "NO_SHOW", "points": 1.0, "status": "APPEALED", "occurredAt": "…", "expiresAt": "…",
        "reason": "Không đến lịch 09:30 06/10 tại VinFast Cầu Giấy", "booking": { "bookingId": "…", "bookingCode": "EVC-…" },
        "appeal": { "appealId": "…", "status": "PENDING", "decideBy": "…" }, "canAppeal": false }
    ]
  }
}
```

`events`: 2 × cửa sổ gần nhất, mới trước, gồm cả `expired` (để minh bạch). `canAppeal` = `NO_SHOW`/`LATE_CANCEL`, `counted`, chưa có khiếu nại, `now < occurred_at + NO_SHOW_APPEAL_HOURS` (EF-BK02-04).

## 8.2 API-BK02-05 — `POST /reliability/events/{eventId}/appeal`

`{ "note": "Tôi đã đến lúc 09:40 nhưng xưởng đóng cửa" }` (10–500 ký tự). `canAppeal = false` ⇒ `409 APPEAL_NOT_ALLOWED` (`details.reason`: `WINDOW_PASSED`, `ALREADY_APPEALED`, `NOT_APPEALABLE`). Tạo `reliability_appeal` (`NO_SHOW_DISPUTE` hoặc `FORCE_MAJEURE`), sự kiện ⇒ `appealed`, thông báo xưởng.

## 8.3 API-BK02-08 / 09 — phía xưởng

- `GET /workshop-owner/reliability-appeals?status=PENDING` ⇒ `[ { appealId, kind, ownerNote, submittedAt, decideBy, booking: { code, date, time }, customerTier } ]` (không có `score`).
- `POST …/{appealId}/decision` `{ "decision": "ACCEPT" | "REJECT", "note": "…" }` — `note` bắt buộc khi `REJECT`. `ACCEPT` ⇒ `accepted`, sự kiện `waived` + `WAIVER` (AF-BK02-03). `REJECT` ⇒ `rejected`, sự kiện về `counted`. Đã quyết định ⇒ `409 APPEAL_ALREADY_DECIDED`. Thông báo chủ xe.

## 8.4 JOB-BK02-03 — `reliability.appeal_timeout`

`pending` và `now ≥ decide_by` ⇒ `auto_accepted` + `WAIVER` (BR-BK02-09, AC-BK02-06).

## 8.5 JOB-BK02-02 — `reliability.daily_recompute`

00:30 Asia/Ho_Chi_Minh: sự kiện `counted` có `expires_at ≤ now` ⇒ `expired`; tính lại `owner_reliability_state` của chủ xe bị ảnh hưởng; bậc giảm ⇒ thông báo "Bạn đã trở lại mức {bậc}" (AF-BK02-04).

## 8.6 JOB-BK02-04 — `reliability.must_confirm_release`

Lịch của chủ xe bậc `MUST_CONFIRM`, `confirmed`, chưa `attendance_confirmed_at`, `starts_at − now ≤ 12h` ⇒ huỷ `cancel_reason = attendance_unconfirmed` (không tính điểm), thông báo. Nhắc trước 24 giờ dùng us-033 có sẵn.

---

# 9. Workshop board — hiển thị bậc

`GET /workshop-owner/bookings` và `…/{bookingId}` thêm `customerTier` (`NORMAL` / `SOFT_REMINDER` / `MUST_CONFIRM` / `RESTRICTED`) và `noShowAllowedAt`. Không có trường điểm.

---

# 10. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 404 | `BOOKING_NOT_FOUND` / `EVENT_NOT_FOUND` / `APPEAL_NOT_FOUND` | Không thuộc người gọi | |
| 409 | `INVALID_BOOKING_STATE` | Huỷ / đánh dấu sai trạng thái | BK02-01, 02, 06 |
| 409 | `NO_SHOW_TOO_EARLY` | Chưa qua ân hạn (`details.allowedAt`) | BK02-06 |
| 409 | `UNDO_WINDOW_PASSED` | Quá 24 giờ | BK02-07 |
| 409 | `ARRIVAL_PROMPT_INACTIVE` | | BK02-03 |
| 409 | `APPEAL_NOT_ALLOWED` / `APPEAL_ALREADY_DECIDED` | | BK02-05, 09 |
| 422 | `REJECT_NOTE_REQUIRED` | Từ chối không ghi lý do | BK02-09 |

---

# 11. Observability

- Log `reliability.event_created` (`kind`, `points`, `actor_type`), `reliability.tier_changed` (`from`, `to`), `reliability.no_show_prompted` (`delay_s` sau mốc), `reliability.no_show_auto_marked`, `reliability.appeal_decided` (`decision`, `hours_to_decide`).
- Metric M-05: `booking_cancel_total{reason}`, `no_show_total{actor}`; PL-03 đọc từ `booking.cancel_reason`.

---

# 12. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `classify`: đúng mốc 24 giờ = huỷ sớm (AC-BK02-01); 08:00 huỷ 08:00 = muộn (EDGE-BK02-04) | +3 |
| Unit | Mọi trường hợp miễn BR-BK02-04 ⇒ không sự kiện (AC-BK02-02) | +6 |
| Unit | Điểm + bậc theo ngưỡng; `WAIVER` triệt tiêu | +4 |
| Service | Một lịch tối đa một sự kiện (huỷ muộn rồi đánh dấu lỡ hẹn bị chặn) | +1 |
| Service | Mọi sự kiện có loại, điểm, thời điểm, lịch, lý do (AC-BK02-03) | +1 |
| Service | Đổi giờ trong 24 giờ không tạo sự kiện (EDGE-BK02-02) | +1 |
| Service | Xưởng huỷ `confirmed` sát giờ ⇒ sự kiện xưởng, điểm chủ xe không đổi | +1 |
| Job | Hỏi ở mốc ân hạn; "Đang tới" gia hạn một lần; tự đánh dấu sau 90 phút | +3 |
| Job | Sự kiện quá 90 ngày ⇒ hạ bậc, thông báo (AC-BK02-04) | +1 |
| Job | Khiếu nại không phản hồi 72 giờ ⇒ tự chấp nhận (AC-BK02-06) | +1 |
| API | Hoàn tác trong 24 giờ; khôi phục khi xe đến muộn | +2 |
| API | Chủ xưởng không nhận `score`; chỉ `customerTier` | +1 |

---

# 13. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
