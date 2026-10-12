# Frontend Technical Specification — Tối ưu hoá lập lịch

> Frontend cho Feature `FEAT-P2-BK10` (SCR-BK10-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-10-phase2-spec.ff.md). **API:** [API Spec](bk-10-phase2-spec.api.md) (`API-BK10-01..05`).
>
> **Nguyên tắc:** không lộ công thức hay trọng số dạng số cho chủ xưởng (chỉ thanh trượt hai đầu); chủ xe chỉ thấy lợi ích bằng lời ("lấy xe sớm hơn 40 phút").

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-BK10` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-BK10-01 (khối trong `/technician/settings/booking`), SCR-BK10-02 (tab trong `/technician/metrics`), SCR-BK10-03 (trang chủ xe) |
| Routes | `/bookings/:bookingId/reschedule-proposal` (mới) |
| Feature folder | `frontend/src/features/optimizer/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Cài đặt tối ưu (SCR-BK10-01)

Khối "Sắp xếp lịch tự động" trong `BookingSettingsPage`:

| Trạng thái | UI |
|---|---|
| `off`, chưa `eligible` | "Hệ thống đang thu thập dữ liệu để đánh giá. Bạn sẽ được báo khi có thể bật." (không công tắc) |
| `off`, `eligible` | Công tắc "Bật" + kết quả đánh giá gần nhất ("Thử nghiệm cho thấy giảm {x}% thời gian chờ") |
| `off`, `autoOffReason` | Banner "Đã tự tắt vì hiệu quả chưa đạt" / "… vì lỗi kỹ thuật" |
| `on` | Công tắc tắt; thanh trượt hai đầu "Khách chờ ít" ↔ "Thợ ít rảnh" (giữa = mặc định), không số; câu "Thay đổi áp dụng từ lần sắp xếp kế tiếp" |

## 2.2 Báo cáo (SCR-BK10-02)

Tab "Sắp xếp tự động" trong `/technician/metrics` (PL-03 FE §2.3): T₃ ("Thời gian thợ / khoang trống"), T₄ ("Khách chờ trước khi làm"), T₅ ("Thời gian giao nhận xe") theo tuần, đường "trước khi bật" làm mốc (SVG thuần, cùng `lineChart` PL-03). Board: lịch có `planned_start_at` hiện thứ tự trong làn của KTV / khoang (tên khoang khi có).

## 2.3 Đề xuất dời lịch (SCR-BK10-03)

Route `/bookings/:bookingId/reschedule-proposal` (mở từ thông báo):
- "Đến {giờ mới} thay vì {giờ cũ} để {gainSummary}?" (giờ `font-mono`).
- "Đồng ý" (primary) ⇒ `API-BK10-04 { accept: true }` ⇒ vé cập nhật; "Giữ nguyên" (secondary) ⇒ `accept: false`.
- Hết hạn / `PROPOSAL_NO_LONGER_VALID` ⇒ "Đề xuất không còn hiệu lực, lịch của bạn giữ nguyên."
- Vé (`BookingTicket`) có banner nhỏ dẫn tới trang này khi có đề xuất `pending`.

Quản lý khoang (`workshop_bay`): danh sách khoang trong `BookingSettingsPage` (thêm / đổi tên / tắt) — chỉ hiện khi `optimizer` không `off` hoặc có ≥ 1 khoang.

---

# 3. API Integration & Errors

`features/optimizer/api.ts`: `getOptimizerSetting`, `putOptimizerSetting`, `getOptimizerReport`, `getRescheduleProposal`, `respondRescheduleProposal`.

| Lỗi | Xử lý |
|---|---|
| `OPTIMIZER_NOT_ELIGIBLE` | Tải lại; ẩn công tắc |
| `PROPOSAL_NO_LONGER_VALID` | §2.3 |

---

# 4. Acceptance Criteria (FE)

1. Không có số trọng số nào trên UI.
2. Đề xuất dời luôn cần bấm "Đồng ý" — không có hành vi tự chấp nhận.
3. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `optimizer/settingView.test.ts` | 4 trạng thái khối cài đặt | +4 |
| `optimizer/proposalView.test.ts` | Câu đề xuất; hết hạn | +2 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-BK10-01, BR-BK10-03, 04, EF-BK10-03 | §2.1 |
| SCR-BK10-02, UC-BK10-04 | §2.2 |
| SCR-BK10-03, BR-BK10-02, 08, AF-BK10-02 | §2.3 |

---

# 7. Analytics

`optimizer_setting_changed` (`mode`, `sliderBucket`), `reschedule_proposal_viewed`, `reschedule_proposal_response` (`accept`).

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
