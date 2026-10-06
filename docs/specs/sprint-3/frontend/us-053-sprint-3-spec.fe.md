# Frontend Technical Specification — Booking Ticket, QR check-in, huỷ & đổi lịch

> **Cập nhật phạm vi (02/10/2026):** các phần dưới đây trong tài liệu này không còn áp dụng.
>
> - Báo giá / duyệt báo giá (`quote`, `quote_item`, us-049): **đã bỏ**. Đặt lịch không gắn báo giá; mọi con số chi phí là ước tính (F5), chi phí cuối cùng do xưởng xác nhận khi kiểm tra xe.
> - Kết nối Discord (`user_discord_link`, ENT-417): **đã bỏ**. Nhắc bảo dưỡng, nhắc lịch hẹn và hỏi thăm hiện trong mục **Thông báo** của app; danh sách kênh ngoài (Zalo / Telegram / SMS / Email) vẫn có nhưng đều "Sắp có", bật nhắc không bắt buộc chọn kênh.

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
| Version | `v1.1` |
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

### Nội dung các khối (FF BR-1202, BR-1208)

| Khối | Nguồn | Hiển thị |
|---|---|---|
| Xe | `vehicle` | Model + biển số che (`30A-***.45`). **Không** hiển thị VIN, CCCD, email, SĐT ở bất kỳ trạng thái nào |
| Hạng mục | `items[]` (`itemName`, `covered`) | Có báo giá ⇒ các dòng báo giá; không ⇒ hạng mục của `odoMilestone`; `items = []` ⇒ "Bảo dưỡng theo yêu cầu, xưởng sẽ tư vấn tại chỗ". `covered = true` ⇒ nhãn "Bảo hành" |
| Chi phí | `quote` / `estimatedCost` | Có báo giá ⇒ "Theo báo giá đã duyệt: {approvedTotal}"; không ⇒ "Chi phí ước tính: {estimatedCost}" hoặc "Chưa có ước tính". Luôn có chữ "ước tính" khi không phải báo giá |
| Giấy tờ cần mang | `documentsToBring[]` (cấu hình backend) | Danh sách gạch đầu dòng; mảng rỗng ⇒ ẩn khối. FE không tự viết cứng danh sách |

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

- Tab **Sắp tới** (`scope=UPCOMING`, giờ hẹn tăng dần) / **Đã qua** (`scope=PAST`, giảm dần, chỉ `MY_BOOKINGS_PAST_DAYS` = 90 ngày gần nhất — ghi chú cuối danh sách "Chỉ hiển thị 90 ngày gần nhất") (FF BR-1213); thẻ: ngày giờ, xưởng, badge trạng thái, chi phí, mũi tên.
- Hành động nhanh trên thẻ (nếu có) cũng theo `allowedActions` của từng dòng.
- Trống: "Bạn chưa có lịch hẹn nào" + nút "Đặt lịch" (`/booking`).
- Phân trang vô hạn theo `nextCursor`.

## 4.6 RescheduleSlotPicker (SCR-1203)

- Tiêu đề "Đổi lịch tại {xưởng}" + giờ hiện tại.
- Chọn ngày trong `[hôm nay, +7]`; tải khung bằng `API-BK-02?rescheduleBookingId=…` (không `timeSlot` ⇒ danh sách khung còn chỗ).
- Khung hiện tại hiển thị "Giờ hiện tại" và không chọn được.
- Chọn khung ⇒ gọi lại `API-BK-02` có `timeSlot` để lấy `confirmationToken` ⇒ SCR-1204.
- Ghi chú: "Muốn đổi sang xưởng khác? Bạn cần huỷ lịch này và đặt mới." + link (FF AF-1202).
- Khung mới hết chỗ ⇒ gợi ý phương án **chỉ trong cùng xưởng** (khung gần nhất cùng ngày → ngày kế tiếp còn chỗ) từ `alternatives[]`; lịch cũ giữ nguyên (FF AF-1203).

## 4.7 RescheduleConfirm (SCR-1204)

- Hai cột "Hiện tại" → "Mới"; câu "Lịch cũ chỉ được huỷ khi lịch mới được giữ thành công."
- Nút "Xác nhận đổi" (disabled khi đang gửi) ⇒ `API-BT-04` kèm header `Idempotency-Key` sinh một lần cho mỗi token; gửi lại sau lỗi mạng dùng lại key (FF EF-1204).
- Lỗi mạng / timeout: **không** báo "đã đổi"; tải lại ticket để hiển thị giờ thực tế (FF EF-1204).
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
| `BOOKING_CHANGED` / `BOOKING_NOT_CONFIRMED` | Tải lại ticket, toast "Lịch hẹn vừa thay đổi" và hiển thị trạng thái hiện tại (xưởng vừa huỷ hoặc check-in — FF EF-1203) |
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
- Hiện trạng code (2026-10-01): `BookingTicket.tsx` là SCR-701/SCR-1201 đầy đủ đọc `GET /bookings/:id`; thêm `MyBookings`, `Reschedule`, `/c/:bookingCode`. Backend chưa có `API-BR-01/02/03`, `API-BT-01 → 04` nên FE dùng mock API (`VITE_API_MOCKS`); booking tạo bằng `API-BK-03` thật được mock ghi lại để mở được ticket.
- Thẻ lịch hẹn trong chat (FF AF-1201, AF-1204) chỉ hiển thị dữ liệu từ backend và link tới SCR-1201; chat không tự dựng mã/QR, đổi lịch qua chat vẫn cần chủ xe bấm Xác nhận.

# 13. Truy vết FF → FE

| FF | Nội dung | FE |
|---|---|---|
| UC-1201, BR-1201, BR-1202, AC-1201 | Ticket đầy đủ khi `confirmed` | §3.1, nội dung các khối, §4.1–4.2 |
| AC-1202 | Không QR khi `pending` | §3.2, AC-FE-1203 |
| BR-1203, AC-1208, UC-1205 | QR chỉ chứa `{APP_BASE_URL}/c/{code}`; check-in thuộc us-037 | §4.1 (vẽ từ `qrPayload`), §8 `/c/:bookingCode` |
| BR-1208 | Giấy tờ cần mang | Nội dung các khối (`documentsToBring`) |
| UC-1202, BR-1213 | Lịch của tôi | §4.5 |
| UC-1203, BR-1204, BR-1205, AC-1203, AC-1204 | Đổi lịch cùng xưởng, nguyên tử | §4.6, §4.7, AC-FE-1202 (giữ nguyên lịch cũ khi lỗi) |
| BR-1206, BR-1207, AC-1207 | Hạn đổi 60', tối đa 2 lần | §4.3 (`rescheduleBlockedReason`), AC-FE-1201 |
| BR-1209, AC-1205 | Giữ `confirmed`, mã/QR không đổi | §5 #4 (về ticket cũ, cùng mã) |
| BR-1210, AC-1206 | Nhắc 24h theo giờ mới | Backend |
| BR-1211 | Lịch sử đổi lịch | §4.4 |
| UC-1204, BR-1212 | Huỷ qua xác nhận lần hai | §2.2, §5 #5 (SCR-702) |
| AF-1201, AF-1204 | Đổi lịch / xem ticket qua chat | §12 |
| AF-1203, EF-1201 | Khung mới hết chỗ | §4.6, §7 `SLOT_FULL` |
| EF-1202 | Token đổi lịch hết hạn | §4.7, §7 |
| EF-1203 | Booking đổi trạng thái giữa chừng | §7 `BOOKING_CHANGED` |
| EF-1204 | Lỗi khoá/DB | §4.7 (Idempotency-Key, không báo đã đổi), §7 `503` |

# 14. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu |
| `v1.1` | `2026-10-01` | Team 4 Người | Đối chiếu FF: nội dung từng khối ticket (không PII, hạng mục khi không có mốc, giấy tờ từ `documentsToBring`), sắp xếp + giới hạn 90 ngày của "Lịch của tôi", phương án chỉ cùng xưởng khi đổi lịch, Idempotency-Key, hiện trạng code, bảng truy vết FF → FE |
