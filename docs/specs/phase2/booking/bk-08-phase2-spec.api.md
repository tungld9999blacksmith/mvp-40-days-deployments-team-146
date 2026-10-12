# API Technical Specification — Báo trễ chủ động hai chiều

> Backend cho Feature `FEAT-P2-BK08`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-08-phase2-spec.ff.md). **Entity:** [Entity Spec](bk-08-phase2-spec.entity.md).
>
> **Tái dùng:** tiến độ 6 bước (us-057, `service_progress`), thời lượng chuẩn + khoảng `starts_at`/`ends_at` (WS-02), phân công KTV (WS-03, khi có), `capacity_base` (WS-02/WS-03), BK-01 đổi lịch (`trigger = RESCHEDULE`) và us-053, BK-02 (`grace_extended_until`, sự kiện tin cậy xưởng `WORKSHOP_LATE`), thông báo trong app. Không theo dõi vị trí (FF §21).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-BK08` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/booking/delay.py` (mới: `estimate_day()` hàm thuần + service), route trong `booking/route.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `SVC-BK08-01` | Internal | `DelayEstimator.recompute(workshop_id, date)` | Ước tính giờ bắt đầu các lịch còn lại | BR-BK08-01 |
| `API-BK08-01` | `POST` | `/bookings/{bookingId}/running-late` | Chủ xe báo trễ 10/20/30 | UC-BK08-04, BR-BK08-02, 05 |
| `API-BK08-02` | `POST` | `/bookings/{bookingId}/delay-reports/{reportId}/response` | Chủ xe chọn "Đến muộn hơn" / "Đổi giờ" | UC-BK08-02, 03 |
| `API-BK08-03` | `GET` | `/bookings/{bookingId}/delay` | Trạng thái trễ hiện tại (vé) | — |
| `HOOK-BK08-01` | Internal | Tiến độ / phát sinh / check-in đổi ⇒ `recompute` | | UC-BK08-01 |
| `JOB-BK08-01` | Celery | `delay.tick` (mỗi 2 phút trong giờ mở cửa) | Bắt trường hợp quá thời lượng mà không ai cập nhật | FF §18 |

Board (`GET /workshop-owner/bookings`) thêm `expectedStartAt`, `ownerEtaAt`, `ownerDelayMin`, `overlapWarning` (SCR-BK08-03, EDGE-BK08-02).

---

# 2. Authorization & Guards

Chủ xe cho `API-BK08-01..03` (booking của mình). Khoá Redis `delay:{bookingId}` cho báo / phản hồi (đếm giới hạn đúng). Khoá `delay:day:{workshopId}:{date}` cho `recompute`.

---

# 3. SVC-BK08-01 — ước tính (hàm thuần `estimate_day`)

Đầu vào cho một xưởng / ngày: các lịch chưa xong (`confirmed`, `checked_in`, `in_progress`) với `starts_at`, `duration_min` (WS-02 + phút của dòng `EXTRA` đã duyệt AD-04 theo `service_item_duration` / `repair_price`), bước tiến độ hiện tại + thời điểm vào bước, `owner_eta_at`, KTV được giao (WS-03); số làn = `capacity_base` (KTV làm ngày đó hoặc `total_technicians − emergency_slots_reserved`).

Thuật toán (list scheduling theo làn):
1. Lịch đang làm: `predicted_end = max(now, stage_started_at) + remaining`, `remaining` = `duration_min` − thời gian đã làm (ước theo bước: `checked_in`/`inspecting` 0 %, `servicing` theo thời gian trôi, `waiting_parts` + 15 phút mỗi lần cập nhật, `quality_check` 85 %, `ready_for_pickup` 100 %); không âm.
2. Có WS-03: mỗi KTV là một làn với lịch được giao; lịch chưa giao vào làn rảnh sớm nhất. Không có: làn giả theo `capacity_base`.
3. Lịch chưa bắt đầu, theo `starts_at`: `expected_start = max(starts_at, owner_eta_at?, lane_free_at)`; `lane_free_at += duration_min`.
4. Không có tiến độ của bất kỳ lịch đang làm nào trong ngày ⇒ không ước tính (giữ `NULL`, EF-BK08-01).

`recompute` ghi `expected_start_at` cho lịch thay đổi; với mỗi lịch chưa check-in:
- `delay = expected_start − starts_at`.
- Báo khi `delay ≥ DELAY_NOTIFY_MIN` **và** (`last_notified_delay_min` null hoặc `delay − last_notified ≥ DELAY_NOTIFY_MIN`, EDGE-BK08-01) **và** số báo phía `WORKSHOP` < `DELAY_MAX_REPORTS` (EF-BK08-02) **và** `starts_at` còn ≥ 10 phút ở tương lai.
- Báo = chèn `booking_delay_report (WORKSHOP)`, cập nhật `last_notified_delay_min`, thông báo SCR-BK08-01 ≤ 2 phút sau khi ước tính đổi (FF §18).
- AF-BK08-02: `delay ≤ −DELAY_NOTIFY_MIN` và chủ xe bật `notify_early_start` ⇒ thông báo "Bạn có thể đến sớm hơn, dự kiến {giờ}" (không tính vào giới hạn báo trễ).
- `overlapWarning` khi `owner_eta_at + duration` chồng lịch kế tiếp cùng làn (EDGE-BK08-02).

**Xưởng trễ thật** (`service_started` thực tế − `starts_at` > `WS_LATE_MIN` và chủ xe đã có mặt đúng giờ) ⇒ BK-02 `workshop_reliability_event (WORKSHOP_LATE)`.

---

# 4. API-BK08-01 — chủ xe báo trễ

`{ "minutes": 20 }` (10 / 20 / 30).

1. Booking `confirmed`, chưa check-in, `now ≤ starts_at + NO_SHOW_GRACE_MIN` (BR-BK08-05) ⇒ không thì `409 LATE_REPORT_WINDOW_CLOSED`.
2. Số báo phía `OWNER` < `DELAY_MAX_REPORTS` ⇒ không thì `409 DELAY_REPORT_LIMIT`.
3. `owner_eta_at = max(starts_at, now) + minutes`; BK-02 `grace_extended_until = owner_eta_at + NO_SHOW_GRACE_MIN` (AC-BK08-01); chèn report; `recompute`; thông báo xưởng + KTV được giao "Khách báo trễ {n}' · dự kiến {giờ}" (SCR-BK08-03).
4. AF-BK08-01: lần báo thứ hai trở đi ⇒ response kèm `suggestReschedule: true`.

Response `200`: `{ ownerEtaAt, reportsLeft, suggestReschedule }`.

---

# 5. API-BK08-02 — phản hồi báo trễ của xưởng

`{ "choice": "ARRIVE_LATER" | "RESCHEDULE" }`.

- `ARRIVE_LATER` ⇒ `owner_eta_at = new_time` của report (cùng xử lý BK-02 như §4); xưởng thấy giờ đến mới.
- `RESCHEDULE` ⇒ ghi phản hồi; trả `{ "run": RunDto }` từ `SchedulerService.run(trigger = RESCHEDULE, …)` để chủ xe chọn; khi chủ xe chọn phương án, đổi lịch qua BK-01 / us-053 với `reason_context = WORKSHOP_DELAY` ⇒ BK-02 không tạo sự kiện (BR-BK08-04, AC-BK08-03). Nếu chủ xe sau đó huỷ hẳn thay vì đổi, BK-02 phân loại `workshop_cancel` khi huỷ trong 2 giờ sau báo trễ của xưởng (miễn tính).
- Report đã có phản hồi ⇒ `409 ALREADY_RESPONDED`.

---

# 6. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 400 | `INVALID_REQUEST` | `minutes` ngoài 10/20/30 |
| 404 | `BOOKING_NOT_FOUND` / `DELAY_REPORT_NOT_FOUND` | |
| 409 | `LATE_REPORT_WINDOW_CLOSED` | Quá giờ hẹn + ân hạn hoặc đã check-in |
| 409 | `DELAY_REPORT_LIMIT` | Quá `DELAY_MAX_REPORTS` |
| 409 | `ALREADY_RESPONDED` | |

---

# 7. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `estimate_day`: ví dụ Main Flow (phát sinh 25' ⇒ lịch 09:30 thành 09:55) | +1 |
| Unit | Nhiều làn; lịch có KTV giao; `owner_eta_at` đẩy giờ | +3 |
| Unit | Không có tiến độ ⇒ không ước tính | +1 |
| Service | Chỉ báo lại khi lệch thêm ≥ ngưỡng; tối đa `DELAY_MAX_REPORTS` (AC-BK08-02) | +2 |
| Service | Báo trễ ⇒ không bị đánh dấu lỡ hẹn trong khoảng (AC-BK08-01) | +1 |
| Service | Đổi giờ từ báo trễ xưởng ⇒ không sự kiện tin cậy (AC-BK08-03) | +1 |
| Service | Báo sau giờ hẹn + ân hạn ⇒ `409` | +1 |

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
