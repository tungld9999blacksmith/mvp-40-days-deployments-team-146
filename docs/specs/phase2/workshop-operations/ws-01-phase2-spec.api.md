# API Technical Specification — Tự nhận lịch hẹn có điều kiện

> Backend cho Feature `FEAT-P2-WS01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ws-01-phase2-spec.ff.md). **Entity:** [Entity Spec](ws-01-phase2-spec.entity.md).
>
> **Tái dùng:** chỗ quyết định `pending` / `confirmed` hiện nằm trong `BookingService._create_booking_locked` (đọc `workshop.booking_confirmation_mode`, us-029 BR-014). WS-01 thay đúng chỗ này bằng `ConfirmationPolicy.decide(...)`; mọi đường tạo / xác nhận lịch (app, chat us-061, bộ lập lịch BK-01 khi chủ xe xác nhận giữ chủ động) đều đi qua nó. Hạn chót duyệt: WS-02 `JOB-WS02-01`. Bậc khách: BK-02 `ReliabilityService.tier`. Phụ tùng: BK-09 `PartsAvailabilityService`.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-WS01` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/workshop_board/rules.py` (mới: schema luật + `ConfirmationPolicy`), route trong `workshop_board/route.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-WS01-01` | `GET` | `/workshop-owner/booking-rules` | Đọc 5 luật (kể cả chưa lưu ⇒ mặc định đề xuất) | UC-WS01-01 |
| `API-WS01-02` | `PUT` | `/workshop-owner/booking-rules` | Lưu bộ luật | UC-WS01-01, BR-WS01-04 |
| `API-WS01-03` | `POST` | `/workshop-owner/booking-rules/preview` | Xem trước "tuần trước X% phải duyệt tay" với bộ luật đang sửa | SCR-WS01-01, Q-WS01-02 |
| `SVC-WS01-01` | Internal | `ConfirmationPolicy.decide(booking, workshop, owner_user)` | Quyết định + lý do | UC-WS01-02, BR-WS01-02, 03, 05, 06 |
| `API-WS01-04` | `GET` | `/workshop-owner/bookings` (sửa) | Thêm `manualReviewReasons`, `confirmationDecision` | SCR-WS01-02, AC-WS01-01 |
| `API-WS01-05` | `GET` | `/workshop-owner/booking-rules/stats` | Tỉ lệ duyệt tay 7 / 30 ngày | AC-WS01-03 |

Duyệt / từ chối dùng endpoint MVP `POST /workshop-owner/bookings/{bookingId}/transitions` (UC-WS01-03), không đổi.

---

# 2. Authorization & Guards

Chủ xưởng của xưởng; KTV (WS-03) đọc được lý do trên Board nhưng không gọi được `API-WS01-02/03` (`403 FORBIDDEN`, FF §16).

---

# 3. SVC-WS01-01 — `ConfirmationPolicy.decide`

```python
@dataclass(frozen=True)
class Decision:
    status: BookingStatus           # CONFIRMED | PENDING
    decision: str                   # AUTO_RULES | MANUAL_RULES | MVP_AUTO | MVP_MANUAL | EVAL_ERROR
    reasons: list[ReviewReason]
```

1. Lịch đang là giữ chủ động chưa xác nhận (BK-01 `proactive = true`) ⇒ **không gọi** (BR-WS01-05). Gọi khi chủ xe xác nhận (`API-BK01-07`) hoặc khi tạo lịch thường.
2. Không có dòng luật `enabled` nào ⇒ hành vi MVP: `AUTO` ⇒ `MVP_AUTO` / `CONFIRMED`; `MANUAL` ⇒ `MVP_MANUAL` / `PENDING` (BR-WS01-03, AC-WS01-02).
3. Có luật bật ⇒ bỏ qua `booking_confirmation_mode` (EDGE-WS01-02); đánh giá **tất cả** luật bật (không dừng ở luật đầu, BR-WS01-02):

| Luật | Duyệt tay khi | Đầu vào |
|---|---|---|
| `R-CAPACITY` | `remaining_day_after_this < minRemaining`. `remaining_day_after_this` = tổng chỗ còn của **ngày** sau khi trừ lịch này (Q-WS01-01: theo ngày). Xưởng bật WS-02: tổng `remaining` các đơn vị / số đơn vị của một lịch chuẩn (`LEGACY_BOOKING_MIN`), làm tròn xuống | `CapacityService.occupancy` (WS-02) hoặc `_capacity` MVP |
| `R-RELIABILITY` | `ReliabilityService.tier(user) ∈ tiers` | BK-02 |
| `R-PARTS` | Hạng mục của lịch có phụ tùng `UNKNOWN`, hoặc `ARRIVING` trong ≤ `arrivingWithinDays` | BK-09; BK-09 chưa bật ⇒ luật bỏ qua (coi như thoả) |
| `R-SLOT` | `starts_at` nằm trong một khoảng `slots` | Lịch |
| `R-EXTRA` | Lịch có báo giá kèm (`quote_id` us-049 hoặc tổng `booking_line` đã báo) `> quoteAboveVnd` | Lịch |

4. Không lý do ⇒ `AUTO_RULES` / `CONFIRMED`; có ⇒ `MANUAL_RULES` / `PENDING` + mọi lý do.
5. **Lỗi bất kỳ** khi đánh giá (đọc bậc, phụ tùng, sức chứa) ⇒ `EVAL_ERROR` / `PENDING` với lý do `EVALUATION_ERROR` "Cần xem lại" (BR-WS01-06, EF-WS01-01); log `ws_rules.eval_error` (`rule_code`, tên lớp lỗi).
6. Chạy trong transaction tạo lịch, sau khi đã giữ chỗ (sức chứa đã khoá); mục tiêu ≤ 100 ms (FF §18): 1 truy vấn luật (đệm Redis theo xưởng, xoá khi `PUT`), 1 truy vấn sức chứa ngày, bậc từ `owner_reliability_state`.
7. Ghi `confirmation_decision`, `manual_review_reasons`, `confirmation_evaluated_at` (entity §3). `booking_status_event` của lần tạo có `source` như cũ; tự nhận theo luật ghi `actor = system`, `reason_code = AUTO_RULES` cho chuyển `pending → confirmed` (khi lịch đi qua `pending` trước, ví dụ xác nhận giữ chủ động).

Lịch `MANUAL_RULES` có hạn chót duyệt như MVP (WS-02 xử lý khi quá hạn, EF-WS01-02).

---

# 4. API-WS01-01 / 02 — Bộ luật

## 4.1 `GET /workshop-owner/booking-rules`

```json
{
  "data": {
    "saved": false,
    "fallbackMode": "MANUAL",
    "rules": [
      { "code": "R-CAPACITY", "enabled": true, "params": { "minRemaining": 1 }, "available": true },
      { "code": "R-RELIABILITY", "enabled": true, "params": { "tiers": ["RESTRICTED"] }, "available": true },
      { "code": "R-PARTS", "enabled": false, "params": { "statuses": ["UNKNOWN","ARRIVING"], "arrivingWithinDays": 3 }, "available": false, "unavailableReason": "PARTS_FEATURE_OFF" },
      { "code": "R-SLOT", "enabled": false, "params": { "slots": [] }, "available": true },
      { "code": "R-EXTRA", "enabled": false, "params": { "quoteAboveVnd": 5000000 }, "available": true }
    ]
  }
}
```

`saved = false` ⇒ xưởng chưa lưu, đang chạy MVP theo `fallbackMode`; `rules` là mặc định đề xuất (entity §2.1).

## 4.2 `PUT /workshop-owner/booking-rules`

Body: `{ "rules": [ { "code", "enabled", "params" } ] }` — đủ 5 phần tử. Kiểm schema §2.1 entity ⇒ `400 INVALID_RULE_PARAMS` (`details.code`, `details.field`). Bật `R-PARTS` khi BK-09 tắt ⇒ `422 RULE_UNAVAILABLE`. Khoảng `R-SLOT` ngoài giờ mở cửa ⇒ `400`.

Upsert 5 dòng trong một transaction; xoá đệm; log `ws_rules.updated` (`enabled_codes`). Tắt cả 5 ⇒ vẫn lưu dòng (`enabled = false`) ⇒ hành vi MVP. Áp cho lịch mới (BR-WS01-04).

## 4.3 `POST /workshop-owner/booking-rules/preview`

Body như `PUT`. Chạy `ConfirmationPolicy` (chế độ mô phỏng, không ghi) trên các lịch của xưởng tạo trong 7 ngày qua, với bậc khách và sức chứa **tại thời điểm tạo** (tái dựng từ `booking_status_event` và lịch cùng ngày đã có lúc đó; phụ tùng dùng trạng thái hiện tại).

```json
{ "data": { "sampleSize": 46, "manualCount": 7, "manualRatePct": 15.2,
            "byRule": { "R-CAPACITY": 4, "R-RELIABILITY": 2, "R-SLOT": 2 }, "basis": "LAST_7_DAYS" } }
```

`sampleSize < 10` ⇒ `manualRatePct = null`, `basis = "INSUFFICIENT_DATA"`.

---

# 5. API-WS01-04 — Board

`GET /workshop-owner/bookings` và `…/{bookingId}` thêm:

```json
{ "confirmationDecision": "MANUAL_RULES",
  "manualReviewReasons": [ { "ruleCode": "R-RELIABILITY", "code": "CUSTOMER_TIER_RESTRICTED", "text": "Khách lỡ hẹn nhiều lần (90 ngày)" } ] }
```

Lọc mới: `?needsReview=true` ⇒ `status = pending AND confirmation_decision IN ('MANUAL_RULES','EVAL_ERROR','MVP_MANUAL')`.

---

# 6. API-WS01-05 — `GET /workshop-owner/booking-rules/stats`

`{ "data": { "last7Days": { "total": 46, "manual": 7, "ratePct": 15.2 }, "last30Days": { … }, "target": 20 } }` theo BR-ENT-WS01-02.

---

# 7. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 400 | `INVALID_RULE_PARAMS` | Tham số sai schema | WS01-02, 03 |
| 403 | `FORBIDDEN` | KTV / chủ xe | WS01-01..05 |
| 422 | `RULE_UNAVAILABLE` | Bật `R-PARTS` khi chưa có BK-09 | WS01-02 |

`ConfirmationPolicy` không bao giờ trả lỗi cho chủ xe: lỗi ⇒ duyệt tay.

---

# 8. Observability

- Log `ws_rules.decided` (`workshop_id`, `decision`, `reason_codes`, `ms`), `ws_rules.eval_error`, `ws_rules.updated`.
- Metric M-06: `booking_confirmation_decision_total{workshop_id,decision}`; histogram `ws_rules_decide_seconds`.

---

# 9. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Từng luật: thoả / không thoả + lý do đúng `code`, `text` | +10 |
| Unit | Nhiều luật cùng chạm ⇒ liệt kê **mọi** lý do (BR-WS01-02) | +1 |
| Unit | EDGE-WS01-01: lịch cuối ngày, `minRemaining = 1` ⇒ duyệt tay | +1 |
| Unit | Lỗi đọc bậc ⇒ `EVAL_ERROR` + `PENDING` (BR-WS01-06) | +1 |
| Service | Không bật luật ⇒ chạy lại bộ test us-029 BR-014/015 không đổi (AC-WS01-02) | bộ có sẵn |
| Service | Luật bật bỏ qua `booking_confirmation_mode = MANUAL` (EDGE-WS01-02) | +1 |
| Service | Giữ chủ động không đánh giá; xác nhận giữ chủ động thì đánh giá (BR-WS01-05) | +2 |
| Service | Đổi luật không đổi lý do của lịch đang chờ (AF-WS01-01) | +1 |
| API | Lịch `MANUAL_RULES` luôn có ≥ 1 lý do trên Board (AC-WS01-01) | +1 |
| API | Preview không ghi DB; `sampleSize < 10` ⇒ `null` | +2 |
| Perf | `decide` ≤ 100 ms với 200 lịch / ngày | +1 |

---

# 10. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
