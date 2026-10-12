# API Technical Specification — Tối ưu hoá lập lịch

> Backend cho Feature `FEAT-P2-BK10`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-10-phase2-spec.ff.md). **Entity:** [Entity Spec](bk-10-phase2-spec.entity.md).
>
> **Tái dùng:** BK-01 `engine.filter_hard` + `scorer_version` (thay bộ chấm điểm khi xưởng `on`), WS-02 `CapacityService.fits` (kiểm lại lời giải), WS-03 phân công + kỹ năng + lịch làm, BK-08 `estimate_day` (đầu vào tiến độ), BK-02 tỉ lệ lỡ hẹn theo khung, BK-09 phụ tùng, PL-03 (sự kiện, xuất dữ liệu), đổi lịch us-053. Solver: OR-Tools CP-SAT (Q-BK10-04, quyết định cuối ở tài liệu kiến trúc).
>
> **Điều kiện bắt đầu làm (BR-BK10-04, FF §20):** ≥ `OPT_MIN_DATA_WEEKS` tuần dữ liệu thật của P2-A/P2-B. Trước đó chỉ làm khung `shadow`.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-BK10` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/optimizer/` (mới): `model.py` (dựng bài toán), `solve.py` (CP-SAT, giới hạn thời gian), `validate.py` (kiểm lại cứng), `service.py`, `jobs.py`, `route.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `SVC-BK10-01` | Internal | `Optimizer.rank(run_context, candidates)` | Xếp hạng phương án khi BK-01 gọi | UC-BK10-03 |
| `SVC-BK10-02` | Internal | `Optimizer.plan_day(workshop, date, kind, trigger?)` | Gán khoang / KTV, thứ tự; đề xuất dời | UC-BK10-01, 02 |
| `JOB-BK10-01` | Celery | `optimizer.nightly` (22:00) | Theo lô cho ngày mai | UC-BK10-01 |
| `HOOK-BK10-01` | Internal | Sự kiện huỷ / trễ / vãng lai / KTV nghỉ / phát sinh duyệt | Theo sự kiện | UC-BK10-02 |
| `JOB-BK10-02` | Celery | `optimizer.evaluate` (Thứ Hai) | A/B, tự tắt | UC-BK10-04, EF-BK10-03 |
| `API-BK10-01` | `GET` / `PUT` | `/workshop-owner/optimizer` | Cài đặt (SCR-BK10-01) | BR-BK10-03 |
| `API-BK10-02` | `GET` | `/workshop-owner/optimizer/report?weeks` | Báo cáo hiệu quả (SCR-BK10-02) | UC-BK10-04 |
| `API-BK10-03` | `GET` | `/bookings/{bookingId}/reschedule-proposal` | Đề xuất dời (SCR-BK10-03) | BR-BK10-02 |
| `API-BK10-04` | `POST` | `/bookings/{bookingId}/reschedule-proposal/{proposalId}/response` | Đồng ý / Giữ nguyên | AF-BK10-02 |
| `API-BK10-05` | `GET` / `PUT` | `/internal/optimizer/workshops/{workshopId}` | Vận hành: chế độ `shadow`, xem đánh giá | FF §16 |

---

# 2. Authorization & Guards

- Chủ xưởng: `API-BK10-01/02` xưởng mình; chuyển `on` chỉ khi `eligible` (`409 OPTIMIZER_NOT_ELIGIBLE`).
- Chủ xe: `API-BK10-03/04` lịch của mình.
- Vận hành (claim `ops`, PL-03): `API-BK10-05`.

---

# 3. Mô hình (BR-BK10-05, BR-BK10-06)

**Biến:** `x(b, k, r, t) ∈ {0,1}` — lịch `b` bắt đầu tại đơn vị `t` (WS-02 `SLOT_UNIT_MIN`), do KTV `k`, ở khoang `r` (nếu có khoang). Với `RANK`, `b` là lịch mới đang cân nhắc, các lịch khác cố định.

**Ràng buộc cứng** (đều kiểm lại bằng `validate.py` dùng chính hàm của BK-01 / WS-02 / WS-03 sau khi giải):
1. Mỗi lịch đúng một bộ (k, r, t).
2. `t` trong khung rảnh chủ xe (ràng buộc BK-01 lưu trên `scheduling_run`), trước hạn chót.
3. Xưởng trong vùng chấp nhận (đã lọc ở BK-01).
4. NoOverlap mỗi KTV / khoang; Σ chiếm chỗ ≤ `capacity_base − reserved − blocked` mỗi đơn vị.
5. Trong giờ mở cửa và ngày làm của KTV (WS-03).
6. KTV đủ kỹ năng.
7. Phụ tùng có trước `t` khi `require_parts_in_stock` (BK-09).
8. Lịch `confirmed`: `t` cố định ở giờ hiện tại (chỉ được đổi `k`, `r`) — dời giờ chỉ qua `reschedule_proposal` (BR-BK10-02).
9. Phân công `MANUAL` của chủ xưởng giữ nguyên.

**Mục tiêu:** `min w₁T₁ + w₂T₂ + w₃T₃ + w₄T₄ + w₅T₅ + w₆·Phạt_sở_thích`:

| T | Ước lượng trong mô hình (đơn vị phút) |
|---|---|
| T₁ | (`RANK`) khoảng từ yêu cầu đến khung được chọn bị phạt khi > hạn chót mềm; T₁ "lead time" đo riêng (Q-BK10-01) |
| T₂ | Σ `duration_min` (khác nhau theo kỹ năng KTV khi có dữ liệu thực tế WS-02 theo KTV; không có thì hằng số) |
| T₃ | Σ phút KTV / khoang trống giữa ca, không tính chỗ dự phòng (Q-BK10-03) |
| T₄ | Σ (`start` − giờ khách tới dự kiến: `owner_eta_at` hoặc `starts_at` ± tỉ lệ đến trễ lịch sử) |
| T₅ | Σ (`end` + thời gian bàn giao trung vị − giờ khách tới) |
| Phạt | Lệch giờ quen, không phải xưởng yêu thích (theo yếu tố BK-01) |

Trọng số = `OPTIMIZER_DEFAULT_WEIGHTS × weight_overrides` (kẹp `[0.5, 1.5]`, BR-BK10-03, EDGE-BK10-03).

**Giới hạn thời gian (BR-BK10-07, AC-BK10-03):** `BATCH` 30 s / xưởng / ngày; `EVENT` và `RANK` 3 s (`max_time_in_seconds`). Hết giờ có lời giải khả thi ⇒ dùng (đánh dấu `TIMEOUT` nhưng `SOLVED_FEASIBLE`), không có ⇒ lời giải theo luật (AF-BK10-01). Thiếu thời lượng ⇒ `LEGACY_BOOKING_MIN`, giảm độ tin cậy (`input_digest.lowConfidence = true`, EF-BK10-02).

---

# 4. Áp dụng

| Kiểu | `mode = shadow` | `mode = on` |
|---|---|---|
| `RANK` (BK-01 gọi khi `run` có xưởng bật) | Chạy song song luật, ghi `optimizer_run`, BK-01 vẫn dùng thứ hạng luật | BK-01 dùng thứ hạng của bộ tối ưu (`scorer_version = opt-cpsat-v1`), lý do = mô tả lợi ích ngắn ("Giảm 20 phút chờ") bổ sung cho lý do BK-01 |
| `BATCH` / `EVENT` | Chỉ ghi | Ghi `booking_assignment` (`source = OPTIMIZER`, `bay_id`, `planned_start_at`) cho lịch chưa `MANUAL`; lịch giữ chủ động có thể đổi khung trong khung rảnh (BR-BK10-02); lịch `confirmed` có lợi khi dời ≥ 20 phút ⇒ tạo `reschedule_proposal` + thông báo chủ xe |

Trước khi ghi: `validate.py` kiểm mọi ràng buộc cứng; vi phạm ⇒ `status = INVALID`, không áp dụng, dùng luật, cảnh báo kỹ thuật (log `optimizer.invalid` mức `ERROR`, EF-BK10-01, AC-BK10-01); hai lần `INVALID` trong 7 ngày ⇒ `auto_off_reason = HARD_CONSTRAINT_VIOLATION`, `mode = off`.

Thay đổi gán thông báo KTV liên quan (WS-03) kèm lý do ngắn (BR-BK10-08).

---

# 5. Đề xuất dời lịch — API-BK10-03/04

- `GET` ⇒ `{ proposalId, currentStartAt, proposedStartAt, gainSummary, expiresAt }` hoặc `404`.
- `POST …/response { "accept": true }`: đề xuất `pending`, chưa hết hạn ⇒ kiểm lại khung (WS-02 `fits`) ⇒ đổi lịch qua us-053 (`reason_context = OPTIMIZER_ACCEPTED`, không tính BK-02, không tăng `reschedule_count` của chủ xe) ⇒ `accepted`. Khung không còn ⇒ `void` + `409 PROPOSAL_NO_LONGER_VALID`.
- `accept = false` ⇒ `declined`; chạy `plan_day(EVENT)` lại với lịch này cố định (AF-BK10-02).
- Hết hạn ⇒ `expired` (job), giữ nguyên lịch (AC-BK10-04).

---

# 6. Đánh giá — JOB-BK10-02

Mỗi tuần, với xưởng `shadow` / `on`: `median(gain_pct)` của các `optimizer_run` có cả hai lời giải; M-09 / M-10 trước–sau (PL-03). `shadow` + ≥ `OPT_MIN_DATA_WEEKS` tuần + `median_gain ≥ OPT_MIN_GAIN` ⇒ `eligible = true`, thông báo chủ xưởng có thể bật (AC-BK10-02). `on` + `median_gain < OPT_MIN_GAIN` 2 tuần liên tiếp ⇒ `mode = off`, `auto_off_reason = GAIN_BELOW_THRESHOLD`, báo PO + chủ xưởng (EF-BK10-03). Ghi `optimizer_evaluation`.

---

# 7. API-BK10-01/02 — chủ xưởng

- `GET` ⇒ `{ mode, eligible, autoOffReason, slider, weights: { effective, default }, lastEvaluation }`.
- `PUT { mode?: "off" | "on", slider?: -100..100 }`: `on` khi chưa `eligible` ⇒ `409 OPTIMIZER_NOT_ELIGIBLE`; `shadow` chỉ vận hành đặt. `slider` ⇒ `weight_overrides`: âm tăng `T4`, `T5` (tới ×1,5) và giảm `T3`; dương ngược lại.
- `report` ⇒ T₃, T₄, T₅ theo tuần + "trước khi bật" (từ `optimizer_evaluation`, PL-03).

---

# 8. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 400 | `INVALID_REQUEST` | `slider` ngoài khoảng |
| 404 | `RESCHEDULE_PROPOSAL_NOT_FOUND` | |
| 409 | `OPTIMIZER_NOT_ELIGIBLE` | Bật khi chưa đủ điều kiện |
| 409 | `PROPOSAL_NO_LONGER_VALID` | Khung dời không còn |

---

# 9. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `validate.py` phát hiện từng loại vi phạm cứng (9 loại) | +9 |
| Property | Mọi lời giải trên 200 bài ngẫu nhiên qua `validate` (AC-BK10-01) | +1 |
| Unit | Lịch `confirmed` không đổi `t` (AC-BK10-04); `MANUAL` giữ nguyên | +2 |
| Perf | Bài 18 lịch / 4 KTV / 3 khoang ≤ 30 s batch, ≤ 3 s event (AC-BK10-03) | +2 |
| Service | Hết giờ không lời giải ⇒ dùng luật | +1 |
| Service | Bật khi chưa `eligible` ⇒ `409` (AC-BK10-02) | +1 |
| Job | Gain thấp 2 tuần ⇒ tự tắt | +1 |
| Service | Đồng ý dời ⇒ đổi lịch không tính điểm; từ chối ⇒ giữ | +2 |

---

# 10. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
