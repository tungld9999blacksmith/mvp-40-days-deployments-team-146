# API Technical Specification — Danh sách chờ

> Backend cho Feature `FEAT-P2-BK07`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-07-phase2-spec.ff.md). **Entity:** [Entity Spec](bk-07-phase2-spec.entity.md).
>
> **Tái dùng:** giữ chủ động BK-01 (`hold_option` với `proactive = true`, `API-BK01-07` xác nhận, `API-BK01-08` bỏ, JOB hết hạn), `CapacityService` (WS-02) để biết chỗ trống, BK-02 `on_booking_cancelled` (nguồn chỗ trống), `ReliabilityService.tier` (xếp hạng), thông báo trong app.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-BK07` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/scheduler/waitlist.py` (mới), route trong `scheduler/route.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-BK07-01` | `POST` | `/waitlist` | Đăng ký chờ (SCR-BK07-01) | UC-BK07-01 |
| `API-BK07-02` | `GET` | `/waitlist` | Danh sách chờ của tôi (SCR-BK07-02) | — |
| `API-BK07-03` | `DELETE` | `/waitlist/{waitlistId}` | Rời danh sách | — |
| `API-BK07-04` | `POST` | `/waitlist/offers/{offerId}/accept` | Nhận lời mời | UC-BK07-03 |
| `API-BK07-05` | `POST` | `/waitlist/offers/{offerId}/decline` | Từ chối | UC-BK07-04 |
| `API-BK07-06` | `GET` | `/workshop-owner/waitlist-counts?from&to` | Số người chờ mỗi khung (không danh tính) | FF §16 |
| `HOOK-BK07-01` | Internal | `on_slot_freed(workshop, date, time)` | Mời khi có chỗ trống | UC-BK07-02 |
| `JOB-BK07-01` | Celery | `waitlist.expire_offers` (30 giây) | Hết hạn ⇒ mời người kế | AC-BK07-02 |
| `JOB-BK07-02` | Celery | `waitlist.sweep` (5 phút) | Quét chỗ trống bị lỡ, dọn mục quá giờ | EF-BK07-03 |

---

# 2. Authorization & Guards

Chủ xe cho `API-BK07-01..05` (xe `VERIFIED` + `ACTIVE`, mục / lời mời của mình). Chủ xưởng cho `API-BK07-06`. Khoá Redis `waitlist:slot:{workshopId}:{date}` khi ghép / mời để hai chỗ trống cùng khung không mời trùng người (AF-BK07-01).

---

# 3. API-BK07-01 — đăng ký chờ

```json
{ "userVehicleId": "…", "workshopId": "…", "date": "2026-10-17", "startTime": "08:00", "endTime": "12:00", "runId": "…" }
```

1. Khung / khoảng nằm trong giờ mở cửa, ngày trong `SCHEDULER_WINDOW_DAYS`, `startTime < endTime` ⇒ không thì `400`.
2. Chủ xe đã có `WAITLIST_MAX` mục ⇒ `409 WAITLIST_LIMIT`.
3. Xe đã có lịch mở cho mốc ⇒ `409 OPEN_BOOKING_EXISTS` (đăng ký vô nghĩa, BR-BK07-04).
4. Khung hiện **đang trống** ⇒ không đăng ký, trả `409 SLOT_AVAILABLE` + `details.run` (BK-01 chạy với khoảng đó) để chủ xe đặt luôn.
5. Chèn `booking_waitlist` (`waiting`, `odo_milestone` theo mốc kế tiếp, `queued_at = now`).

Response `201 WaitlistEntryDto`: `{ waitlistId, workshop, date, startTime, endTime, status, position, offer: null }` — `position` = thứ tự trong hàng của khoảng giao nhau (Q-BK07-01, "bạn đứng thứ 2").

---

# 4. HOOK-BK07-01 — `on_slot_freed`

Gọi sau commit khi một khung có thêm chỗ: huỷ lịch (BK-02 hook — mọi `cancel_reason`), hết hạn giữ chủ động (BK-01), đổi lịch dời khỏi khung, xưởng bớt khoá chỗ / tăng số thợ (EDGE-BK07-02), lời mời trước bị từ chối / hết hạn.

1. `starts_at − now < WAITLIST_MIN_LEAD_MIN` ⇒ dừng (BR-BK07-05).
2. **Giờ yên lặng** (EDGE-BK07-01, Q-BK07-02): `now` trong 22:00–07:00 và giờ hẹn cách > 12 giờ ⇒ hoãn; `JOB-BK07-02` xử lý lúc 07:00 nếu chỗ còn trống.
3. Trong khoá `waitlist:slot`: tính số chỗ trống thật của khung (`CapacityService.fits` với thời lượng chuẩn của mục chờ) trừ lời mời đang mở cho khung ⇒ `k`.
4. Lấy tối đa `k` mục khớp (khung nằm trong khoảng của mục; `status ∈ {waiting, declined + keep_after_decline}`; chưa từng từ chối chính `slot_key` này), sắp `(priority_tier, queued_at)` — `priority_tier = 1` khi chủ xe bậc `RESTRICTED` (BR-BK07-03). Bỏ qua mục có xe đã có lịch mở (EF-BK07-01 ⇒ đánh dấu `left (BOOKED_ELSEWHERE)`).
5. Với mỗi mục (song song khi `k > 1`, AF-BK07-01): `SchedulerService.hold_slot(user, vehicle, workshop, date, time, proactive = True, hold_minutes = WAITLIST_OFFER_MIN, trigger = WAITLIST)` ⇒ booking giữ tạm; thất bại vì hết chỗ ⇒ dừng.
6. Chèn `waitlist_offer` (`open`, `slot_key`, `hold_booking_id`, `expires_at`); mục ⇒ `offered`. Unique index chặn hai lời mời cho cùng chỗ (AC-BK07-01).
7. Thông báo đẩy + trong app: "Có chỗ {giờ} {thứ} tại {xưởng}. Giữ cho bạn {WAITLIST_OFFER_MIN} phút." ≤ 1 phút sau khi có chỗ (FF §18). PL-03 `waitlist_offer_sent`.

`hold_slot` là hàm mới mỏng của BK-01: giữ chủ động một khung cụ thể không qua chấm điểm (cùng đường `create_for_slot` + cột `proactive`).

---

# 5. Nhận / từ chối

## 5.1 API-BK07-04 — accept

1. Lời mời `open` và `now < expires_at` ⇒ không thì `409 OFFER_EXPIRED` / `OFFER_INACTIVE`.
2. Gọi `API-BK01-07` nội bộ trên `hold_booking_id` (xác nhận giữ chủ động ⇒ luồng xác nhận MVP + WS-01).
3. Một transaction: offer `accepted`, mục `fulfilled`; mọi mục khác của chủ xe cho cùng mốc ⇒ `left (BOOKED_ELSEWHERE)` (BR-BK07-04, AC-BK07-03). PL-03 `waitlist_offer_accepted`.
4. Response: `BookingOut` của lịch.

## 5.2 API-BK07-05 — decline

`{ "keepWaiting": true }`. Offer `declined`; huỷ giữ tạm (`API-BK01-08`, `PROACTIVE_HOLD_DISMISSED`, không tính điểm — BR-BK07-07); mục ⇒ `declined` (`keep_after_decline = keepWaiting`) hoặc `left`. Gọi `on_slot_freed` để mời người kế ngay.

---

# 6. Jobs

- `waitlist.expire_offers` (30 s): offer `open` quá `expires_at` ⇒ `expired`; giữ tạm do BK-01 JOB hết hạn huỷ (hoặc huỷ ngay ở đây nếu JOB BK-01 chưa chạy); mục ⇒ `expired` nếu không `keep_after_decline`, ngược lại về `waiting`; gọi `on_slot_freed` (AC-BK07-02: người kế được mời ≤ 1 phút). Không tính điểm.
- `waitlist.sweep` (5 phút): (a) mục có `window_date + window_end` đã qua ⇒ `expired (WINDOW_PASSED)` (EF-BK07-03); (b) mục của xe đã có lịch mở cho mốc ⇒ `left (BOOKED_ELSEWHERE)`; (c) chạy `on_slot_freed` cho các khung có mục chờ mà đang có chỗ (bắt sự kiện bị lỡ, xử lý giờ yên lặng hoãn).
- **EF-BK07-02:** giữ tạm bị mất (booking bị huỷ ngoài ý muốn) ⇒ offer `voided`, mục về `waiting` với `queued_at` giữ nguyên (vẫn đứng đầu), thông báo xin lỗi.

---

# 7. API-BK07-06 — chủ xưởng

`[{ date, time, waitingCount }]` — đếm mục khớp mỗi khung; không danh tính.

---

# 8. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 400 | `INVALID_REQUEST` | Khung / khoảng sai |
| 404 | `WAITLIST_NOT_FOUND` / `OFFER_NOT_FOUND` | |
| 409 | `WAITLIST_LIMIT` | Quá `WAITLIST_MAX` |
| 409 | `SLOT_AVAILABLE` | Khung đang trống (`details.run`) |
| 409 | `OPEN_BOOKING_EXISTS` | Xe đã có lịch mở |
| 409 | `OFFER_EXPIRED` / `OFFER_INACTIVE` | |

---

# 9. Test Checklist

| Layer | What | Count |
|---|---|---|
| Concurrency | 2 chỗ trống cùng lúc ⇒ 2 người khác nhau; 1 chỗ không bao giờ 2 lời mời (AC-BK07-01) | +2 |
| Job | Hết hạn ⇒ người kế được mời ≤ 1 phút (AC-BK07-02) | +1 |
| Service | Nhận ⇒ mọi mục khác cho mốc `left` (AC-BK07-03) | +1 |
| Service | Bậc `RESTRICTED` xếp sau | +1 |
| Service | Còn < 60 phút ⇒ không mời; giờ yên lặng ⇒ hoãn | +2 |
| Service | Từ chối / hết hạn không tính điểm BK-02 | +1 |
| Service | Mục có xe đã đặt nơi khác bị bỏ qua (EF-BK07-01) | +1 |

---

# 10. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
