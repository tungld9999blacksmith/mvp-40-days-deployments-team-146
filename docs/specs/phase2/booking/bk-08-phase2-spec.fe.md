# Frontend Technical Specification — Báo trễ chủ động hai chiều

> Frontend cho Feature `FEAT-P2-BK08` (SCR-BK08-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-08-phase2-spec.ff.md). **API:** [API Spec](bk-08-phase2-spec.api.md) (`API-BK08-01..03`).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-BK08` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-BK08-01 (thông báo + khối trên vé), SCR-BK08-02 (nút "Tôi đến trễ" trên vé), SCR-BK08-03 (nhãn Board) |
| Feature folder | `frontend/src/features/bookings/delay/` (mới), sửa `features/workshop-board` |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Xưởng trễ (SCR-BK08-01)

- Thông báo loại `WORKSHOP_DELAY`: "Xe trước làm lâu hơn dự kiến. Dự kiến bắt đầu {giờ mới} (chậm {n} phút)." Bấm mở vé.
- Vé `/bookings/:id` (`BookingStatusBanner`): khối cảnh báo với giờ mới (`font-mono`) + hai nút "Đến muộn hơn" (primary) / "Đổi giờ" (secondary) ⇒ `API-BK08-02`.
  - "Đổi giờ" ⇒ hiện `ScheduleOptionsList` từ `run` trả về (BK-01) với câu "Đổi giờ vì xưởng chậm không bị tính".
- Báo "đến sớm hơn" (khi chủ xe bật): khối thông tin trung tính, không nút.
- Cài đặt: `/notifications/settings` thêm công tắc "Báo khi tôi có thể đến sớm hơn" (mặc định tắt).

## 2.2 "Tôi đến trễ" (SCR-BK08-02)

Vé lịch `confirmed` chưa check-in, từ 2 giờ trước giờ hẹn tới hết ân hạn: nút secondary "Tôi đến trễ" ⇒ 3 nút chọn "10 phút", "20 phút", "30 phút" (bottom sheet, nút 44 px) ⇒ `API-BK08-01`. Thành công ⇒ "Đã báo xưởng. Giờ đến dự kiến {ownerEtaAt}" + "Còn {reportsLeft} lần báo". `suggestReschedule` ⇒ thêm nút "Đổi giờ hẹn". Cũng có chip "Tôi đến trễ" trong chat (CH-01, hẹn trong 24 giờ) dẫn tới sheet này.

## 2.3 Board (SCR-BK08-03)

`WorkshopBoard` / `BoardBookingDetail`: nhãn "Khách báo trễ {n}' · dự kiến {HH:mm}" (`ownerDelayMin`, `ownerEtaAt`); `expectedStartAt` lệch ⇒ dòng phụ "Dự kiến bắt đầu {HH:mm}"; `overlapWarning` ⇒ badge cảnh báo "Có thể chồng với xe {giờ}".

---

# 3. API Integration & Errors

`features/bookings/delay/api.ts`: `reportRunningLate`, `respondDelay`, `getDelay`.

| Lỗi | Xử lý |
|---|---|
| `LATE_REPORT_WINDOW_CLOSED` | Ẩn nút; toast "Đã quá thời gian báo trễ" |
| `DELAY_REPORT_LIMIT` | "Bạn đã báo trễ {n} lần. Hãy gọi xưởng." + hotline |
| `ALREADY_RESPONDED` | Tải lại vé |

---

# 4. Acceptance Criteria (FE)

1. Nút "Tôi đến trễ" chỉ hiện trong cửa sổ cho phép.
2. Đổi giờ từ báo trễ có câu "không bị tính".
3. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `bookings/delay/delayView.test.ts` | `runningLateAvailable(booking, now)`; khối báo trễ xưởng theo dữ liệu | +4 |
| `workshop-board/delayLabels.test.ts` | Nhãn báo trễ / dự kiến / chồng lịch | +3 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-BK08-01, UC-BK08-01..03, AF-BK08-02 | §2.1 |
| SCR-BK08-02, UC-BK08-04, AF-BK08-01 | §2.2 |
| SCR-BK08-03, EDGE-BK08-02 | §2.3 |

---

# 7. Analytics

`running_late_reported` (`minutes`), `workshop_delay_shown` (`delayMin`), `workshop_delay_response` (`choice`).

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
