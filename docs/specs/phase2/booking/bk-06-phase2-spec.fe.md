# Frontend Technical Specification — Lịch bảo dưỡng định kỳ tại xưởng quen

> Frontend cho Feature `FEAT-P2-BK06` (SCR-BK06-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-06-phase2-spec.ff.md). **API:** [API Spec](bk-06-phase2-spec.api.md) (`API-BK06-01..07`).
>
> **Tái dùng:** `ProactiveHoldPage` (BK-01 SCR-BK01-04), `ScheduleOptionsList`, `AvailabilityGrid` (BK-01), `CancelBookingDialog` (BK-02).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-BK06` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-BK06-01 (trang mới), SCR-BK06-02 (lời mời trong hỏi thăm / vé), SCR-BK06-03 (mở rộng SCR-BK01-04) |
| Routes | `/bookings/series` (mới) |
| Feature folder | `frontend/src/features/scheduler/series/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `SeriesPage` (SCR-BK06-01)

Route `/bookings/series`; vào từ `MyBookings` (thẻ "Lịch định kỳ" đầu trang khi có chuỗi, hoặc link "Đặt định kỳ") và thông báo.

| Vùng | Nội dung |
|---|---|
| Không có chuỗi | Giải thích một câu + nút "Tạo lịch định kỳ" ⇒ `SeriesCreateSheet` |
| Thẻ chuỗi | Xưởng (badge "Đã ngừng nhận lịch" khi không `active`), ràng buộc (tóm tắt "Sáng thứ Bảy" hoặc "Theo thói quen đặt lịch"), trạng thái ("Đang chạy" / "Tạm dừng: {lý do}"), lần kế tiếp: "Mốc {km} · dự kiến {dueDate} · hệ thống tìm lịch từ {triggerDate}" |
| Lần hiện tại | Khi occurrence `HELD`: thẻ lịch giữ + "Xác nhận" (→ `/bookings/{id}/proactive`) và "Bỏ qua lần này"; `ALTERNATIVES_OFFERED`: "Xưởng kín, xem phương án cho lần này" (→ `ScheduleOptionsList` của `schedulingRunId`) |
| Lịch sử | Danh sách mốc + trạng thái ("Đã làm", "Đã bỏ qua", "Hết hạn giữ", "Làm ở nơi khác") |
| Hành động | "Sửa" (xưởng, ràng buộc — câu "Áp dụng từ lần sau"), "Tạm dừng" / "Tiếp tục", "Huỷ chuỗi" (danger) |

**Huỷ chuỗi:** `alertdialog`: "Huỷ lịch định kỳ?" + checkbox "Huỷ luôn lịch {ngày} đang có" (chỉ khi có lịch mở; mặc định **bỏ chọn**, AC-BK06-03). Khi chọn và lịch đã xác nhận ⇒ hiện câu của `cancel-preview` BK-02 trước khi xác nhận.

## 2.2 `SeriesCreateSheet`

- Chọn xưởng (mặc định xưởng của lịch vừa xong / xưởng yêu thích), ràng buộc: "Theo thói quen đặt lịch" (mặc định) hoặc "Riêng cho lịch định kỳ" (`AvailabilityGrid`).
- `422 SERIES_REQUIRES_HOLD_LEVEL` ⇒ `DecisionSheet` "Lịch định kỳ cần bật Giữ chỗ sẵn. Bật ngay?" ⇒ `PUT /scheduling/profile` (`automationLevel = HOLD`) rồi tạo lại.
- `warnings: DUE_UNKNOWN` ⇒ dòng "Chưa xác định được mốc, hệ thống sẽ tạo lịch khi có dữ liệu".

## 2.3 Lời mời (SCR-BK06-02)

Ở `FollowUp` (`/follow-ups/:id`) sau khi chủ xe gửi hỏi thăm và ở vé lịch `completed`: gọi `API-BK06-07`; `invite = true` ⇒ khối "Đặt định kỳ ở {xưởng} cho các mốc sau?" + "Đặt định kỳ" (mở `SeriesCreateSheet` điền sẵn) + "Không, cảm ơn" (dismiss).

## 2.4 Xác nhận lần kế tiếp (SCR-BK06-03)

`ProactiveHoldPage` (BK-01) khi booking có `seriesId`: tiêu đề "Lịch định kỳ", thêm nút "Bỏ qua lần này" (gọi `API-BK06-06` thay cho `dismiss` BK-01, để occurrence ghi `skipped`) và dòng "Chuỗi vẫn tiếp tục cho mốc sau".

---

# 3. API Integration & Errors

`features/scheduler/series/api.ts`: `createSeries`, `getSeries`, `updateSeries`, `pauseSeries`, `resumeSeries`, `cancelSeries`, `skipOccurrence`, `getInvitation`, `dismissInvitation`.

| Lỗi | Xử lý |
|---|---|
| `SERIES_EXISTS` | Điều hướng tới chuỗi hiện có |
| `SERIES_REQUIRES_HOLD_LEVEL` | §2.2 |
| `WORKSHOP_INACTIVE` | "Xưởng đã ngừng nhận lịch, hãy chọn xưởng khác" + mở "Sửa" |
| `SERIES_INVALID_STATE` | Tải lại |

---

# 4. Acceptance Criteria (FE)

1. Hộp huỷ chuỗi mặc định không huỷ lịch đang có (AC-BK06-03).
2. "Bỏ qua lần này" có câu xác nhận chuỗi vẫn tiếp tục.
3. Mọi ngày hiển thị theo Asia/Ho_Chi_Minh.
4. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `series/seriesView.test.ts` | `seriesCardView(dto)` → trạng thái, dòng lần kế tiếp, hành động theo occurrence | +5 |
| `series/cancelSeries.test.ts` | Checkbox mặc định `false`; chỉ hiện khi có lịch mở | +2 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-BK06-01, UC-BK06-04, 05, AF-BK06-05 | §2.1 |
| UC-BK06-01, BR-BK06-08 | §2.2, §2.3 |
| SCR-BK06-03, UC-BK06-03 | §2.4 |
| AF-BK06-01 | §2.1 (phương án cho lần này) |

---

# 7. Analytics

`series_invite_shown`, `series_created` (`source`), `series_paused` (`reason`), `series_cancelled` (`cancelOpenBooking`), `series_occurrence_skipped`.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
