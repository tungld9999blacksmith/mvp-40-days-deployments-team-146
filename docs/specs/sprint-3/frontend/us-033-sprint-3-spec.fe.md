# Frontend Technical Specification — Nhắc lịch hẹn 24h & xử lý từ lời nhắc

> Đặc tả frontend cho Feature `FEAT-NOTI-002` (PRD F7 phần nhắc lịch hẹn, US-033 → US-036).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-033-sprint-3-spec.ff.md) · **API:** [API Spec](../api/us-033-sprint-3-spec.api.md) · **Entity:** [Entity Spec](../entity/us-033-sprint-3-spec.entity.md)
>
> **Phạm vi FE:** màn **Chi tiết lịch hẹn** (SCR-701) — nơi link trong lời nhắc Discord dẫn tới — và **hộp thoại xác nhận huỷ** (SCR-702). Việc lên lịch và gửi nhắc chạy hoàn toàn ở backend (JOB-BR-001), không có UI. Luồng đổi lịch chi tiết thuộc F6b.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-NOTI-002` — Nhắc lịch hẹn 24h & xử lý từ lời nhắc |
| Screen | `SCR-701` Chi tiết lịch hẹn · `SCR-702` Hộp thoại xác nhận huỷ |
| Route | `/bookings/:bookingId` (query tuỳ chọn `src=REMINDER_24H`) |
| Version | `v1.0` |
| Author | Team 4 Người |
| FE Owner | Nguyễn Lê Phước Tiến `[Đề xuất — cùng mảng Đặt lịch]` |
| Status | `Draft` |
| Related PRD | [PRD_EV_Care_MVP.md §F7](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-033-sprint-3-spec.ff.md#7-user-flow) |
| Related API | [API-BR-01, API-BR-02, API-BR-03](../api/us-033-sprint-3-spec.api.md) · us-029 `API-BK-04` (huỷ giữ chỗ) |
| Last Updated | `2026-09-29` |

---

# 2. Screen Overview

## 2.1 Purpose

Cho chủ xe xem một lịch hẹn và phản hồi lời nhắc 24h bằng một chạm:

- **Xác nhận sẽ đến** (FF BR-708).
- **Huỷ lịch** — qua hộp thoại xác nhận, chỗ được trả lại ngay (FF BR-709).
- **Đổi lịch** — sang luồng F6b, hoặc hướng dẫn khi F6b chưa có (FF AF-702).

Đây cũng là màn "chi tiết lịch hẹn" chung khi chủ xe mở lịch từ Home hoặc sau khi đặt lịch.

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Link trong lời nhắc Discord | Chủ xe bấm link `{FRONTEND_URL}/bookings/{id}?src=REMINDER_24H` | Mở SCR-701 (đăng nhập trước nếu chưa có phiên) |
| Home — thẻ "Lịch hẹn sắp tới" `[Đề xuất]` | Có booking đang mở | `/bookings/{id}?src=APP` |
| Đặt lịch thành công (`/booking-success`) | Nhấn `Xem lịch hẹn` | `/bookings/{id}?src=APP` |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| Nhấn Back | Màn trước; nếu mở từ link ngoài (không có history) ⇒ `/dashboard` |
| Nhấn `Đổi lịch` (`rescheduleMode = F6B`) | Luồng đổi lịch F6b `[route F6b]` |
| Nhấn `Đặt lịch mới` (`rescheduleMode = GUIDE`) | `/booking` |
| `401` | Login, sau đó quay lại đúng `/bookings/:id?src=…` |
| `403 ONBOARDING_REQUIRED` | Onboarding |

## 2.4 Preconditions

- Chủ xe đã đăng nhập, tài khoản `ACTIVE`.
- Booking thuộc chủ xe (backend kiểm tra — FF BR-713).

---

# 3. UI Structure

## 3.1 Layout

```text
Chi tiết lịch hẹn (SCR-701)
├── Header: "Lịch hẹn" + Back
├── StatusBanner            (trạng thái + lý do khi không còn hành động)
├── AppointmentCard
│   ├── Thời gian (Thứ, dd/mm/yyyy · HH:mm)
│   ├── Xưởng + địa chỉ
│   ├── Mã lịch hẹn + QR check-in (khi CONFIRMED)
│   ├── Xe (model · biển số che)
│   └── Chi phí ước tính (nhãn "Chi phí ước tính")
├── AttendanceBadge         ("Bạn đã xác nhận sẽ đến lúc HH:mm dd/mm")
├── ActionBar
│   ├── [Xác nhận sẽ đến]   (primary)
│   ├── [Đổi lịch]          (secondary)
│   └── [Huỷ lịch]          (destructive, text button)
└── CancelDialog (SCR-702)
```

## 3.2 Screen Layout Notes

- Mobile-first; một cột; `ActionBar` dính đáy màn hình khi có ít nhất một hành động.
- Chỉ render nút có trong `allowedActions` (API tính — không tự suy luận ở FE).
- Khi `src=REMINDER_24H`, nút **Xác nhận sẽ đến** được nhấn mạnh (primary) và cuộn tới `ActionBar`.

---

# 4. Component Specification

## 4.1 StatusBanner

| Property | Value |
|---|---|
| Component | `BookingStatusBanner` |
| Data Source | `status`, `allowedActions`, `appointmentAt` |
| Visibility | Luôn hiện |

### Behavior

| Điều kiện | Nội dung |
|---|---|
| `CONFIRMED` và có hành động | `Đã xác nhận` (xanh) |
| `CONFIRMED` và `now ≥ appointmentAt` | `Đã tới giờ hẹn — nếu cần thay đổi, vui lòng liên hệ xưởng.` |
| `PENDING` | `Đang giữ chỗ — chờ xưởng xác nhận` (us-029); có `CANCEL_HOLD` ⇒ nút `Huỷ giữ chỗ` dùng `API-BK-04` |
| `CANCELLED` | `Lịch hẹn đã huỷ` |
| `CHECKED_IN` / `IN_PROGRESS` | `Xe đã check-in tại xưởng` / `Xe đang được bảo dưỡng` |
| `COMPLETED` | `Đã hoàn tất` |

Không dùng màu làm tín hiệu duy nhất — luôn kèm chữ và icon (lucide).

## 4.2 AppointmentCard

| Property | Value |
|---|---|
| Component | `AppointmentCard` |
| Data Source | `API-BR-01` |

### Behavior

- Hiển thị thời gian theo giờ Việt Nam từ `appointmentAt` (định dạng `Thứ 7, 04/10/2026 · 14:00`).
- `qrUrl` chỉ render khi `status = CONFIRMED`.
- Biển số dùng `plateMasked` từ API; FE không tự che/không nhận biển số đầy đủ.
- Chi phí luôn kèm nhãn `estimateLabel`.

## 4.3 Confirm Attendance Button

| Property | Value |
|---|---|
| Component | `PrimaryButton` |
| Label | `Xác nhận sẽ đến` |
| Visible When | `allowedActions` chứa `CONFIRM_ATTENDANCE` |
| Loading State | Disabled + spinner |

### Behavior

1. Gọi `API-BR-02` (không cần hộp thoại — không phải side effect phá huỷ).
2. Thành công ⇒ ẩn nút, hiện `AttendanceBadge`, toast `Cảm ơn bạn! Xưởng đã nhận được xác nhận.`

## 4.4 Reschedule Button

| Property | Value |
|---|---|
| Component | `SecondaryButton` |
| Label | `Đổi lịch` |
| Visible When | `allowedActions` chứa `RESCHEDULE` |

### Behavior

- `rescheduleMode = F6B` ⇒ điều hướng luồng đổi lịch F6b, truyền `bookingId`.
- `rescheduleMode = GUIDE` ⇒ mở bottom sheet:
  ```text
  Đổi lịch
  Để đổi giờ, bạn hãy đặt lịch mới rồi quay lại huỷ lịch này.
  Lịch hiện tại vẫn được giữ cho đến khi bạn huỷ.
  [Đặt lịch mới]   [Đóng]
  ```
  **Không** tự huỷ lịch hiện tại (FF AF-702).

## 4.5 Cancel Button + CancelDialog (SCR-702)

| Property | Value |
|---|---|
| Component | `DestructiveTextButton` + `ConfirmDialog` |
| Label | `Huỷ lịch` |
| Visible When | `allowedActions` chứa `CANCEL` |

### Dialog Content

```text
Huỷ lịch hẹn?
14:00 Thứ 7, 04/10 tại VinFast Smart City.
Chỗ của bạn sẽ được trả lại cho người khác.

Lý do (không bắt buộc)
[______________________________]  0/255

[Giữ lịch]            [Huỷ lịch]
```

### Behavior

1. Nhấn `Huỷ lịch` trên màn ⇒ chỉ mở dialog, **không** gọi API (FF AC-705).
2. Trong dialog nhấn `Huỷ lịch` ⇒ gọi `API-BR-03` với `source = src ?? "APP"`, `reason` (trim, bỏ trống ⇒ không gửi), header `Idempotency-Key` = UUID sinh khi mở dialog.
3. Đang gửi: disable cả hai nút, spinner trên nút huỷ.
4. Thành công ⇒ đóng dialog, cập nhật màn sang `CANCELLED`, toast `Đã huỷ lịch hẹn.`
5. `Giữ lịch` / bấm ngoài / Esc ⇒ đóng, không gọi API.

### Validation

`reason.length ≤ 255` — bộ đếm ký tự; vượt ⇒ chặn nhập thêm.

---

# 5. User Interaction

## 5.1 Interaction Flow

```text
Mở link nhắc
   ↓
(Chưa có phiên → Login → quay lại)
   ↓
GET /bookings/{id}
   ↓
Hiển thị trạng thái + nút theo allowedActions
   ├── Xác nhận sẽ đến → POST attendance-confirmation → badge
   ├── Đổi lịch → F6b | bottom sheet hướng dẫn
   └── Huỷ lịch → Dialog → POST cancel → CANCELLED
```

## 5.2 Interaction Table

| User Action | Frontend Behavior | Result |
|---|---|---|
| Mở link khi chưa đăng nhập | Lưu `returnTo`, sang Login | Quay lại đúng màn |
| Nhấn `Xác nhận sẽ đến` | `API-BR-02` | Badge xác nhận |
| Nhấn `Đổi lịch` | Theo `rescheduleMode` | F6b / hướng dẫn |
| Nhấn `Huỷ lịch` | Mở dialog | Chưa gọi API |
| Xác nhận trong dialog | `API-BR-03` | Booking `CANCELLED` |
| API `409` | Tải lại `API-BR-01`, hiện lý do | Nút cập nhật theo trạng thái mới |

---

# 6. State Management

## 6.1 State Model

```text
BookingDetailState
├── booking            (từ API-BR-01)
├── source             ("REMINDER_24H" | "APP")
├── request
│   ├── isLoading
│   ├── isConfirming
│   ├── isCancelling
│   └── error
└── cancelDialog
    ├── isOpen
    ├── reason
    └── idempotencyKey
```

## 6.2 State Fields

| State | Type | Default | Description |
|---|---|---|---|
| `booking` | `BookingDetail?` | `null` | Dữ liệu API-BR-01 |
| `source` | `"REMINDER_24H" \| "APP"` | `"APP"` | Từ query `src` |
| `isLoading` | `boolean` | `true` | Tải lần đầu |
| `isConfirming` | `boolean` | `false` | Đang gọi API-BR-02 |
| `isCancelling` | `boolean` | `false` | Đang gọi API-BR-03 |
| `error` | `ApiError?` | `null` | Lỗi màn / lỗi hành động |
| `cancelDialog.isOpen` | `boolean` | `false` | |
| `cancelDialog.reason` | `string` | `""` | |
| `cancelDialog.idempotencyKey` | `string?` | `null` | Sinh khi mở dialog |

Dùng `useReducer` cục bộ trong trang (như các màn khác của dự án).

---

# 7. API Integration

> Contract chi tiết ở [API Spec](../api/us-033-sprint-3-spec.api.md).

## 7.1 Load Booking — `API-BR-01`

```http
GET /api/v1/bookings/{bookingId}?src={source}
```

**Trigger** — Mở màn; sau mỗi lỗi `409`; khi người dùng kéo để làm mới.

| Frontend State | API Response |
|---|---|
| `booking` | `data` |
| Nút hiển thị | `data.allowedActions` |
| Kiểu đổi lịch | `data.rescheduleMode` |

## 7.2 Confirm Attendance — `API-BR-02`

```http
POST /api/v1/bookings/{bookingId}/attendance-confirmation
```

**Success** — cập nhật `booking.attendanceConfirmedAt`, bỏ `CONFIRM_ATTENDANCE` khỏi `allowedActions`.

## 7.3 Cancel — `API-BR-03`

```http
POST /api/v1/bookings/{bookingId}/cancel
Idempotency-Key: {cancelDialog.idempotencyKey}
```

```json
{ "source": "{source}", "reason": "{reason | omitted}" }
```

**Success** — `booking.status = CANCELLED`, `allowedActions = []`.

## 7.4 Cancel Hold — us-029 `API-BK-04`

Chỉ khi `allowedActions` chứa `CANCEL_HOLD` (booking `PENDING` trong 10'). Hành vi theo spec us-029.

---

# 8. Client-side Validation

## 8.1 Validation Rules

| Field | Rule | Error Message |
|---|---|---|
| Lý do huỷ | ≤ 255 ký tự | Chặn nhập, bộ đếm `255/255` |

## 8.2 Validation Timing

- Kiểm tra độ dài khi gõ.
- FE **không** kiểm tra giờ hẹn/trạng thái để quyết định hành động — dựa vào `allowedActions`; backend vẫn kiểm tra lại.

---

# 9. Loading States

## 9.1 Initial Loading

Skeleton cho `AppointmentCard`; `ActionBar` ẩn.

## 9.2 Action Loading

- `isConfirming` ⇒ nút `Xác nhận sẽ đến` disabled + spinner.
- `isCancelling` ⇒ hai nút dialog disabled; không cho đóng dialog.
- Chống bấm hai lần: bỏ qua click khi đang gửi.

---

# 10. Empty States

Không có empty state — màn luôn gắn với một booking. Booking không tồn tại xử lý như lỗi `404` (mục 11).

---

# 11. Error States

## 11.1 General Error

```text
Không thể tải lịch hẹn.
Vui lòng thử lại.

[Thử lại]
```

## 11.2 Error Mapping

| HTTP Status / Error Code | Frontend Behavior |
|---|---|
| `401 UNAUTHORIZED` | Login, `returnTo` = URL hiện tại |
| `403 ONBOARDING_REQUIRED` | Onboarding |
| `404 BOOKING_NOT_FOUND` | Màn "Không tìm thấy lịch hẹn" + nút `Về trang chủ` (không nêu lịch có tồn tại hay không — FF AC-709) |
| `409 BOOKING_NOT_CONFIRMED` | Toast theo `details.currentStatus` (vd. `Lịch hẹn đã huỷ trước đó.`, `Xe đã check-in tại xưởng.`) + tải lại API-BR-01 |
| `409 APPOINTMENT_STARTED` | Toast `Đã tới giờ hẹn — vui lòng liên hệ xưởng.` + tải lại |
| `400 INVALID_REQUEST` | Lỗi dưới ô lý do |
| `500` / `503` | Toast `Tạm thời chưa thực hiện được, bạn thử lại nhé.`; giữ dialog mở với lý do đã nhập |

---

# 12. Error Handling

## 12.1 Field-level Error

Chỉ ô lý do huỷ.

## 12.2 Screen-level Error

Tải API-BR-01 lỗi ⇒ General Error (11.1).

## 12.3 Retry Behavior

- Thử lại huỷ **dùng lại cùng `idempotencyKey`** để không tạo hai yêu cầu khác nhau.
- Giữ `reason` đã nhập khi thử lại.

---

# 13. Navigation

## 13.1 Routes

| Route | Purpose |
|---|---|
| `/bookings/:bookingId` | Chi tiết lịch hẹn (mới) |
| `/booking` | Đặt lịch (us-029) |
| `/dashboard` | Home |
| `/` | Login |

Thêm route vào `frontend/src/app/App.tsx` trong layout đã đăng nhập.

## 13.2 Navigation Rules

### Deep link khi chưa đăng nhập

```text
/bookings/:id?src=REMINDER_24H
  ↓ (không có phiên)
Login (lưu returnTo)
  ↓
/bookings/:id?src=REMINDER_24H
```

### Back

Không có history (mở từ Discord) ⇒ về `/dashboard`.

---

# 14. Permission / Visibility

| UI Element | Condition |
|---|---|
| Toàn màn | Chủ xe đăng nhập, sở hữu booking |
| `Xác nhận sẽ đến` | `CONFIRM_ATTENDANCE` ∈ `allowedActions` |
| `Đổi lịch` | `RESCHEDULE` ∈ `allowedActions` |
| `Huỷ lịch` | `CANCEL` ∈ `allowedActions` |
| `Huỷ giữ chỗ` | `CANCEL_HOLD` ∈ `allowedActions` |
| QR | `status = CONFIRMED` |

## 14.1 Role-based Behavior

| Role | Access |
|---|---|
| Chủ xe | Xem và thao tác booking của mình |
| Chủ xưởng | Không dùng màn này (Board — us-037) |

> Kiểm tra ở FE chỉ để hiển thị; backend là nơi quyết định.

---

# 15. Responsive / Device Behavior

## Mobile

- Một cột; `ActionBar` dính đáy; dialog dạng bottom sheet.
- Link từ Discord mở trên trình duyệt điện thoại — màn phải dùng được không cần cài app.

## Tablet / Desktop

- Nội dung giới hạn độ rộng ~560px, căn giữa; dialog dạng modal.

---

# 16. Accessibility

- Nút có nhãn rõ; nút huỷ có `aria-describedby` trỏ tới câu "Chỗ của bạn sẽ được trả lại…".
- Dialog: focus vào nút `Giữ lịch` khi mở (lựa chọn an toàn); Esc đóng; trả focus về nút `Huỷ lịch` khi đóng.
- Trạng thái không chỉ dựa vào màu.

---

# 17. Analytics / Tracking

| Event | Trigger | Properties |
|---|---|---|
| `booking_detail_viewed` | Mở màn | `source`, `status` |
| `attendance_confirmed` | API-BR-02 thành công | `source` |
| `booking_cancel_dialog_opened` | Mở dialog | `source` |
| `booking_cancelled` | API-BR-03 thành công | `source`, `hasReason` |
| `booking_cancel_failed` | API-BR-03 lỗi | `errorCode` |
| `booking_reschedule_clicked` | Nhấn `Đổi lịch` | `rescheduleMode` |

Không gửi `reason`, `bookingCode`, biển số vào analytics.

---

# 18. Acceptance Criteria

## AC-FE-701 — Mở từ lời nhắc (FF UC-702)

**Given** chủ xe chưa đăng nhập bấm link nhắc

**When** đăng nhập thành công

**Then** quay lại đúng `/bookings/:id?src=REMINDER_24H` và thấy lịch hẹn + nút theo `allowedActions`.

## AC-FE-702 — Xác nhận sẽ đến (FF AC-703)

**Given** `allowedActions` chứa `CONFIRM_ATTENDANCE`

**When** nhấn `Xác nhận sẽ đến`

**Then** gọi API-BR-02 một lần; nút biến mất; hiện badge thời điểm xác nhận.

## AC-FE-703 — Huỷ cần xác nhận lần hai (FF AC-705)

**Given** màn chi tiết lịch `CONFIRMED`

**When** nhấn `Huỷ lịch` rồi `Giữ lịch`

**Then** không có request huỷ nào được gửi.

## AC-FE-704 — Huỷ thành công (FF AC-704)

**Given** dialog huỷ đang mở

**When** nhấn `Huỷ lịch` trong dialog

**Then** gọi API-BR-03 với `source` đúng và `Idempotency-Key`; màn chuyển `Lịch hẹn đã huỷ`, không còn nút hành động.

## AC-FE-705 — Không còn hợp lệ (FF AC-708, EF-704)

**Given** booking đã qua giờ hẹn hoặc đã check-in

**When** mở màn

**Then** không hiện nút hành động; `StatusBanner` nêu lý do.

## AC-FE-706 — Đổi lịch khi F6b chưa có (FF AF-702)

**Given** `rescheduleMode = GUIDE`

**When** nhấn `Đổi lịch`

**Then** hiện hướng dẫn và nút `Đặt lịch mới`; lịch hiện tại không bị huỷ.

## AC-FE-707 — Booking của người khác (FF AC-709)

**Given** API trả `404 BOOKING_NOT_FOUND`

**When** màn tải xong

**Then** hiện "Không tìm thấy lịch hẹn", không lộ thông tin nào.

---

# 19. Technical Notes

## Frontend Stack

```text
Framework: React 19 + Vite
Language: TypeScript
State Management: useReducer cục bộ trong trang
Networking: fetch qua shared/api/client.ts
Navigation: React Router 7
UI Library: Tailwind CSS 4 + lucide-react
```

## Component Structure

```text
frontend/src/features/bookings/
├── pages/
│   └── BookingDetail.tsx           (SCR-701)
├── components/
│   ├── BookingStatusBanner.tsx
│   ├── AppointmentCard.tsx
│   ├── BookingActionBar.tsx
│   └── CancelBookingDialog.tsx     (SCR-702)
├── api.ts                          (getBooking, confirmAttendance, cancelBooking)
└── types.ts                        (BookingDetail, BookingAction, RescheduleMode)
```

## Implementation Notes

- Không tự tính "còn huỷ được không" từ giờ hẹn — luôn dựa `allowedActions`.
- Thời gian: parse `appointmentAt` (UTC) và format bằng `Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })`.
- Mock trong `frontend/src/mocks/` cho tới khi backend sẵn sàng; giữ đúng shape API-BR-01.

---

# 20. Open Questions

- [ ] Home có thẻ "Lịch hẹn sắp tới" dẫn vào SCR-701 không? (`[Đề xuất]` có — cần API danh sách booking của tôi, thuộc F6b)
- [ ] Route luồng đổi lịch F6b.
- [ ] Q-703 — nội dung hướng dẫn khi `rescheduleMode = GUIDE`.

---

# 21. Related Documents

- Functional Spec: [us-033-sprint-3-spec.ff.md](../feature-functional/us-033-sprint-3-spec.ff.md)
- API Spec: [us-033-sprint-3-spec.api.md](../api/us-033-sprint-3-spec.api.md)
- us-029 (đặt lịch, huỷ giữ chỗ): [FF](../feature-functional/us-029-sprint-3-spec.ff.md) · [API](../api/us-029-sprint-3-spec.api.md)
- us-021 FE (cài đặt thông báo): [us-021-sprint-2-spec.fe.md](../../sprint-2/frontend/us-021-sprint-2-spec.fe.md)
- Design / Figma: `[Chưa có]`

---

# 22. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Team 4 Người | Initial version: SCR-701, SCR-702 |
