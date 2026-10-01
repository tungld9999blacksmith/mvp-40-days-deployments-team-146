# Frontend Technical Specification — Booking Ticket, QR check-in, huỷ & đổi lịch

> Đặc tả frontend cho Feature `FEAT-BOOK-002` (PRD F6b, US-053 → US-056).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-053-sprint-3-spec.ff.md) · **API:** [API Spec](../api/us-053-sprint-3-spec.api.md)
>
> **Phạm vi FE:** App chủ xe — mở rộng màn chi tiết lịch hẹn `/bookings/:bookingId` của [us-033 FE](us-033-sprint-3-spec.fe.md) thành **Booking Ticket** (SCR-1201), thêm "Lịch của tôi" (SCR-1202), luồng đổi lịch (SCR-1203/1204), route QR `/c/:bookingCode`. Thay dữ liệu mock của `/booking-success` (`BookingSuccess.tsx`) bằng ticket thật.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-BOOK-002` |
| Screen | `SCR-1201` Ticket · `SCR-1202` Lịch của tôi · `SCR-1203` Chọn khung mới · `SCR-1204` Xác nhận đổi |
| Route | `/bookings` · `/bookings/:bookingId` · `/bookings/:bookingId/reschedule` · `/c/:bookingCode` · (`/booking-success?bookingId=` → redirect `/bookings/:bookingId`) |
| Version | `v1.0` |
| Author | Team 4 Người |
| Status | `Draft` |
| Related API | `API-BT-01 → 04`, `API-BR-01/03`, `API-BK-02/04` |
| Last Updated | `2026-09-30` |

---

# 2. Screen Overview

## 2.1 Entry Points

| Entry | Action |
|---|---|
| Sau đặt lịch thành công (us-029 SCR-405) | `/bookings/:id` (thay `/booking-success`) |
| Menu "Lịch hẹn" / Home "Lịch sắp tới" | `/bookings` |
| Link nhắc 24h (Discord) | `/bookings/:id?src=REMINDER_24H` (us-033) |
| Quét QR bằng camera điện thoại | `/c/:bookingCode` |
| Chat — thẻ lịch hẹn | `/bookings/:id` |

## 2.2 Exit Points

| Action | Destination |
|---|---|
| Đổi lịch | `/bookings/:id/reschedule` |
| Huỷ | Hộp thoại SCR-702 (us-033) |
| "Đặt lịch" khi danh sách trống | `/booking` (us-029) |

---

# 3. UI Structure

## 3.1 SCR-1201 Ticket (`CONFIRMED`)

```text
┌──────────────────────────────────┐
│ ← Lịch hẹn            [ĐÃ XÁC NHẬN]│
│        ┌──────────┐              │
│        │   QR     │              │
│        └──────────┘              │
│      EVC-7F3A9C21  (chữ lớn, mono) │
├──────────────────────────────────┤
│ 🕘 Thứ 7, 04/10/2026 · 09:00      │
│ 📍 VinFast Smart City             │
│    Đại lộ Thăng Long… [Chỉ đường] │
│ 🚗 VF 6 · 30A-***.45              │
├──────────────────────────────────┤
│ Hạng mục: …                       │
│ Theo báo giá đã duyệt: 1.270.000 ₫│
│  (hoặc) Chi phí ước tính: …       │
├──────────────────────────────────┤
│ Giấy tờ cần mang: • … • … • …     │
├──────────────────────────────────┤
│ [Xác nhận sẽ đến]                 │
│ [Đổi lịch]  [Huỷ lịch]            │
│ (lý do nếu không đổi được)        │
│ Lịch sử ▸                         │
└──────────────────────────────────┘
```

## 3.2 Biến thể theo trạng thái

| `status` | Khác biệt |
|---|---|
| `PENDING` | Không QR/mã; banner "Đang giữ chỗ — chờ xưởng xác nhận"; nút "Huỷ giữ chỗ" nếu `CANCEL_HOLD` ∈ `allowedActions` (đếm ngược tới `holdExpiresAt`) |
| `CHECKED_IN` / `IN_PROGRESS` | Ẩn QR; khối tiến độ (F8b nếu bật) |
| `COMPLETED` / `CANCELLED` | Ẩn QR và hành động; ghi trạng thái + thời điểm |

---

# 4. Component Specification

## 4.1 TicketQr

- Vẽ phía client từ `qrPayload` (thư viện QR nhẹ, ví dụ `qrcode`), kích thước ≥ 220 px, nền trắng kể cả dark mode (để máy quét đọc).
- Nút "Tải QR" ⇒ `API-BT-02` (blob kèm Bearer) → lưu PNG.
- Tăng độ sáng màn hình: không bắt buộc (web).

## 4.2 BookingCode

- Font monospace, cỡ lớn, nút "Sao chép".

## 4.3 ActionBar

- Render theo `allowedActions`; **không** tự suy luận từ thời gian ở FE.
- Nút "Đổi lịch" ẩn khi không có `RESCHEDULE`; hiển thị dòng lý do từ `rescheduleBlockedReason`:
  - `TOO_CLOSE_TO_APPOINTMENT` → "Đã quá hạn đổi lịch (trước giờ hẹn 60 phút). Vui lòng liên hệ xưởng."
  - `MAX_RESCHEDULES_REACHED` → "Bạn đã đổi lịch tối đa 2 lần cho lịch hẹn này."

## 4.4 HistoryTimeline

- Từ `history[]`: "Đổi giờ 04/10 09:00 → 05/10 14:00 (từ lời nhắc)", "Xưởng chấp nhận", …

## 4.5 MyBookingsList (SCR-1202)

- Tab **Sắp tới** / **Đã qua**; thẻ: ngày giờ, xưởng, badge trạng thái, chi phí, mũi tên.
- Phân trang vô hạn theo `nextCursor`.

## 4.6 RescheduleSlotPicker (SCR-1203)

- Tiêu đề "Đổi lịch tại {xưởng}" + giờ hiện tại.
- Chọn ngày trong `[hôm nay, +7]`; tải khung bằng `API-BK-02?rescheduleBookingId=…` (không `timeSlot` ⇒ danh sách khung còn chỗ).
- Khung hiện tại hiển thị "Giờ hiện tại" và không chọn được.
- Chọn khung ⇒ gọi lại `API-BK-02` có `timeSlot` để lấy `confirmationToken` ⇒ SCR-1204.
- Ghi chú: "Muốn đổi sang xưởng khác? Bạn cần huỷ lịch này và đặt mới." + link (FF AF-1202).

## 4.7 RescheduleConfirm (SCR-1204)

- Hai cột "Hiện tại" → "Mới"; câu "Lịch cũ chỉ được huỷ khi lịch mới được giữ thành công."
- Nút "Xác nhận đổi" (disabled khi đang gửi) ⇒ `API-BT-04`.
- Đếm ngược TTL token; hết hạn ⇒ quay lại SCR-1203 và tải lại.

---

# 5. User Interaction

| # | Action | FE Behavior | API |
|---|---|---|---|
| 1 | Mở ticket | `GET /bookings/:id` | BR-01 |
| 2 | Mở `/c/:code` | `GET /bookings/by-code/:code` → `replace('/bookings/:id')`; `404` ⇒ "Không tìm thấy lịch hẹn của bạn" | BT-03 |
| 3 | Mở "Lịch của tôi" | `GET /bookings?scope=UPCOMING` | BT-01 |
| 4 | Đổi lịch | SCR-1203 → SCR-1204 → `POST /reschedule` → về ticket, toast "Đã đổi lịch" | BK-02, BT-04 |
| 5 | Huỷ | SCR-702 (us-033) → `API-BR-03` hoặc `API-BK-04` theo action | BR-03 / BK-04 |

---

# 6. State Management

```ts
interface RescheduleDraft {
  bookingId: string;
  date: string;               // YYYY-MM-DD
  timeSlot: string | null;    // HH:mm
  confirmationToken: string | null;
  tokenExpiresAt: string | null;
}
```

- Ticket đã mở được lưu cache cục bộ (mã + `qrPayload` + ngày giờ + xưởng, **không** PII khác) để hiển thị khi mất mạng `[Đề xuất]`; hiển thị nhãn "Dữ liệu lúc {giờ}".
- Sau mọi mutation: invalidate `booking(id)` và `myBookings`.

---

# 7. Error Mapping

| Code | FE |
|---|---|
| `SLOT_FULL` | "Khung này vừa hết chỗ. Lịch cũ của bạn vẫn giữ nguyên." + gợi ý `details.alternatives` |
| `CONFIRMATION_TOKEN_EXPIRED` / `INVALID_CONFIRMATION_TOKEN` | Quay lại SCR-1203, tải lại khung |
| `BOOKING_CHANGED` / `BOOKING_NOT_CONFIRMED` | Tải lại ticket, toast "Lịch hẹn vừa thay đổi" |
| `RESCHEDULE_TOO_LATE` / `RESCHEDULE_LIMIT_REACHED` | Hiện lý do như §4.3 |
| `RESCHEDULE_SAME_SLOT` | Lỗi tại khung đã chọn |
| `QR_NOT_AVAILABLE` | Ẩn nút tải QR |
| `BOOKING_NOT_FOUND` | Trang "Không tìm thấy lịch hẹn" |
| `503` | "Tạm thời chưa đổi được, lịch cũ vẫn giữ nguyên. Thử lại sau." |

---

# 8. Navigation

| Route | Screen | Guard |
|---|---|---|
| `/bookings` | SCR-1202 | Chủ xe |
| `/bookings/:bookingId` | SCR-1201 (= us-033 SCR-701) | Chủ xe |
| `/bookings/:bookingId/reschedule` | SCR-1203/1204 | Chủ xe; không có `RESCHEDULE` ⇒ redirect ticket |
| `/c/:bookingCode` | Resolver | Chưa đăng nhập ⇒ login rồi quay lại; chủ xưởng đăng nhập ⇒ `/technician/check-in?code=…` (us-037 SCR-803) |
| `/booking-success` | Redirect | Có `bookingId` ⇒ `/bookings/:id`, không ⇒ `/bookings` |

---

# 9. Accessibility & Responsive

- QR có `alt="Mã QR check-in cho lịch hẹn {code}"`; mã chữ luôn hiển thị cạnh QR (người không quét được vẫn đọc mã).
- Mobile-first; desktop hiển thị ticket dạng thẻ giữa màn.

# 10. Analytics

| Event | Properties |
|---|---|
| `ticket_viewed` | `status`, `src` |
| `qr_downloaded` | — |
| `reschedule_started` / `reschedule_succeeded` / `reschedule_failed` | `code`, `source` |

---

# 11. Acceptance Criteria (FE)

## AC-FE-1201 — Hành động theo `allowedActions`

**Given** response không có `RESCHEDULE` với `rescheduleBlockedReason = TOO_CLOSE_TO_APPOINTMENT` **Then** không có nút Đổi lịch và hiển thị câu lý do.

## AC-FE-1202 — Lịch cũ giữ nguyên khi lỗi

**Given** `API-BT-04` trả `SLOT_FULL` **Then** ticket vẫn hiển thị giờ cũ và thông báo "Lịch cũ của bạn vẫn giữ nguyên".

## AC-FE-1203 — QR chỉ khi `CONFIRMED`

**Given** `status = PENDING` **Then** không render QR/mã.

## AC-FE-1204 — Route QR

**Given** chủ xe đã đăng nhập mở `/c/EVC-7F3A9C21` của chính mình **Then** chuyển tới `/bookings/{id}`; mã của người khác ⇒ trang không tìm thấy.

---

# 12. Technical Notes

- Tái dùng `features/bookings/`; tách `TicketView` dùng chung cho `/bookings/:id` (us-033) và màn sau đặt lịch (us-029).
- Giờ hiển thị theo `Asia/Ho_Chi_Minh` từ `appointmentAt` (UTC).

# 13. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu |
