# Frontend Technical Specification — Workshop Board

> Đặc tả frontend cho Feature `FEAT-BOARD-001` (PRD F8, US-037 → US-040).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-037-sprint-3-spec.ff.md) · **API:** [API Spec](../api/us-037-sprint-3-spec.api.md) · **Entity:** [Entity Spec](../entity/us-037-sprint-3-spec.entity.md)
>
> **Phạm vi FE:** Workshop Portal (desktop-first) — Board lịch hẹn (SCR-801), chi tiết + hành động (SCR-802), check-in QR (SCR-803, dùng được trên điện thoại), sức chứa & khoá chỗ (SCR-804), cài đặt đặt lịch (SCR-805). Trang `/technician` hiện có (Dashboard kỹ thuật viên, dữ liệu mock) lấy tóm tắt từ `API-WB-01` và dẫn vào Board.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-BOARD-001` — Workshop Board |
| Screen | `SCR-801` Board · `SCR-802` Chi tiết lịch hẹn · `SCR-803` Check-in QR · `SCR-804` Sức chứa & khoá chỗ · `SCR-805` Cài đặt đặt lịch |
| Route | `/technician/board` · `/technician/board/:bookingId` · `/technician/check-in` · `/technician/capacity` · `/technician/settings/booking` |
| Version | `v1.0` |
| Author | Team 4 Người |
| FE Owner | Lê Đức Tùng (mảng Dashboard kỹ thuật viên) |
| Status | `Draft` |
| Related PRD | [PRD_EV_Care_MVP.md §F8](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-037-sprint-3-spec.ff.md#7-user-flow) |
| Related API | [API-WB-01 → API-WB-08](../api/us-037-sprint-3-spec.api.md) |
| Last Updated | `2026-09-29` |

---

# 2. Screen Overview

## 2.1 Purpose

Một nơi để chủ xưởng: xem lịch hẹn hôm nay / 7 ngày tới, xử lý yêu cầu giữ chỗ, tiếp nhận xe bằng QR, cập nhật bắt đầu / hoàn tất, huỷ có lý do, khoá chỗ và đổi chế độ xác nhận — mà không vi phạm state machine (FF BR-802) hay sức chứa (FF BR-809).

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Sidebar Portal — mục `Lịch hẹn` | Đăng nhập chủ xưởng | `/technician/board` |
| Dashboard `/technician` — khối "Lịch hẹn hôm nay" | Nhấn `Xem tất cả` / một dòng | `/technician/board` / `/technician/board/:id` |
| Sidebar — `Check-in` | | `/technician/check-in` |
| Sidebar — `Sức chứa` | | `/technician/capacity` |
| Sidebar — `Cài đặt đặt lịch` | | `/technician/settings/booking` |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| Nhấn báo giá gắn kèm | `/technician/quote-review?quoteId=…` (F5b) |
| `401 UNAUTHORIZED` / `SESSION_REVOKED` | `/` (Login), thông báo phiên hết hạn |
| `403 ONBOARDING_REQUIRED` | Onboarding chủ xưởng |

## 2.4 Preconditions

- Chủ xưởng đăng nhập, phiên hợp lệ, onboarding xong, gắn một xưởng.
- Vai trò trong `AuthContext` = chủ xưởng; chủ xe không thấy các route này.

---

# 3. UI Structure

## 3.1 Layout

```text
SCR-801 Board (/technician/board)
├── Toolbar
│   ├── DateRangeSwitch  [Hôm nay] [7 ngày tới] [Chọn ngày]
│   ├── StatusFilter     (chip đa chọn)
│   ├── SearchBox        (mã lịch hẹn / biển số)
│   ├── ConfirmationModeBadge (Tự động | Thủ công → SCR-805)
│   └── [Check-in QR]    (→ SCR-803)
├── SummaryCards         (Chờ xưởng · Đã xác nhận · Đã check-in · Đang làm · Hoàn tất · Đã huỷ)
├── PendingBanner        ("Có N yêu cầu chờ bạn xác nhận" — chỉ khi N > 0)
└── BookingTable (nhóm theo ngày → khung giờ)
    └── BookingRow: giờ · mã · khách · xe · trạng thái · nhãn · [hành động nhanh]

SCR-802 Chi tiết (drawer bên phải trên desktop, trang riêng trên mobile)
├── Header: mã + trạng thái
├── CustomerVehicleCard (tên, SĐT, model, biển số)
├── AppointmentCard (ngày, khung, hạng mục, chi phí ước tính, báo giá)
├── AttendanceBadge / ConfirmDeadlineBadge
├── ActionPanel (theo allowedActions)
├── StatusTimeline (statusHistory)
└── Dialogs: ReasonDialog (Từ chối/Huỷ) · CompleteDialog (chi phí thực tế)

SCR-803 Check-in (/technician/check-in)
├── QrScanner (camera)
├── ManualCodeInput + [Tìm]
└── LookupResultCard + [Xác nhận check-in]

SCR-804 Sức chứa (/technician/capacity)
├── WeekHeader (7 ngày)
├── CapacityGrid (ngày × khung): Đã đặt / Đã khoá / Còn nhận
└── BlockEditorPopover (số chỗ khoá, lý do, ghi chú, [Lưu] [Gỡ khoá])

SCR-805 Cài đặt đặt lịch (/technician/settings/booking)
├── RadioGroup: Tự động xác nhận / Tôi xác nhận thủ công
├── Mô tả + hạn chót xác nhận (12 giờ)
└── [Lưu]
```

## 3.2 Screen Layout Notes

- Desktop-first (≥ 1280px): Board dạng bảng, chi tiết mở **drawer** để không mất vị trí danh sách.
- SCR-803 tối ưu cho điện thoại: camera toàn chiều ngang, nút to.
- Chỉ render nút có trong `allowedActions` từ API.

---

# 4. Component Specification

## 4.1 DateRangeSwitch

| Property | Value |
|---|---|
| Component | `DateRangeSwitch` |
| Default | `Hôm nay` |
| Options | `Hôm nay` (`from=to=today`) · `7 ngày tới` (`from=today`, `to=today+6`) · `Chọn ngày` (1 ngày, tối đa 30 ngày trước — FF BR-812) |

Đổi lựa chọn ⇒ gọi lại `API-WB-01`, giữ bộ lọc trạng thái và từ khoá; đồng bộ vào query string (`?from=&to=&status=&q=`).

## 4.2 StatusFilter & SummaryCards

- Chip đa chọn 6 trạng thái; nhấn một `SummaryCard` ⇒ lọc đúng trạng thái đó.
- `SummaryCards` lấy từ `data.summary` (không bị ảnh hưởng bởi bộ lọc).

## 4.3 SearchBox

- Debounce 300 ms; ≥ 2 ký tự mới gọi API (`q`).
- Placeholder `Mã lịch hẹn hoặc biển số`.

## 4.4 BookingRow

| Cột | Nguồn | Ghi chú |
|---|---|---|
| Giờ | `timeSlot` | |
| Mã | `bookingCode` | `—` khi `PENDING` chưa có mã |
| Khách | `customer.fullName` | SĐT hiện trong chi tiết |
| Xe | `vehicle.modelName` + `vehicle.licensePlate` | |
| Trạng thái | `status` | Badge chữ + icon |
| Nhãn | `attendanceConfirmedAt` ⇒ `✓ Khách đã xác nhận đến`; `confirmDeadline` ⇒ `Hạn xác nhận HH:mm` (đỏ khi < 1 giờ) | |
| Hành động nhanh | `allowedActions` ∩ {`ACCEPT`, `CHECK_IN`, `START`} | `REJECT`, `CANCEL`, `COMPLETE` chỉ trong SCR-802 (cần nhập thêm) |

Nhấn dòng ⇒ mở SCR-802.

## 4.5 ActionPanel (SCR-802)

| Action | Nút | Xác nhận | API |
|---|---|---|---|
| `ACCEPT` | `Chấp nhận` (primary) | Không | WB-04 |
| `REJECT` | `Từ chối` | `ReasonDialog` (bắt buộc lý do) | WB-04 |
| `CHECK_IN` | `Check-in` | Không | WB-04 (`source=BOARD`) |
| `START` | `Bắt đầu làm` | Không | WB-04 |
| `COMPLETE` | `Hoàn tất` (primary) | `CompleteDialog` | WB-04 |
| `CANCEL` | `Huỷ lịch` (destructive) | `ReasonDialog` | WB-04 |

Mọi request gửi `expectedStatus = booking.status` hiện có trên màn.

## 4.6 ReasonDialog

| Mode | Lựa chọn lý do |
|---|---|
| Từ chối (`REJECT`) | `Đã kín lịch` (`FULLY_BOOKED`) · `Không hỗ trợ hạng mục` (`NOT_SUPPORTED_SERVICE`) · `Xưởng bận đột xuất` (`WORKSHOP_UNAVAILABLE`) · `Khác` (`OTHER`) |
| Huỷ (`CANCEL`) | `Khách không đến` (`NO_SHOW`) · `Xưởng bận đột xuất` · `Khách yêu cầu huỷ` (`CUSTOMER_REQUEST`) · `Khác` |

- `Khác` ⇒ ô ghi chú bắt buộc (≤ 255).
- `Khách không đến` bị **disable** kèm chú thích `Có thể chọn sau HH:mm` khi `now < appointmentAt + 30'` (tính từ `bookingDate`/`timeSlot`; backend vẫn kiểm tra — `NO_SHOW_TOO_EARLY`).
- Dòng nhắc: `Khách sẽ nhận được thông báo.` (ẩn với `NO_SHOW`).

## 4.7 CompleteDialog

```text
Hoàn tất dịch vụ cho 30A-123.45?
Chi phí thực tế (không bắt buộc)  [ 1.850.000 ] đ
Sau khi hoàn tất: lịch sử bảo dưỡng của xe được cập nhật và khách sẽ nhận
lời hỏi thăm sau khoảng 12 giờ.
[Để sau]   [Hoàn tất]
```

- Input tiền tệ VND, chỉ số, ≥ 0, định dạng `1.850.000`; gửi số nguyên (`actualCost`).

## 4.8 StatusTimeline

Hiển thị `statusHistory` theo thời gian: `HH:mm dd/mm · Đã xác nhận · Hệ thống (tự động)`, `· Đã huỷ · Khách · qua lời nhắc 24h · "Bận việc"` (nguồn/lý do dịch sang tiếng Việt).

## 4.9 QrScanner & ManualCodeInput (SCR-803)

| Property | Value |
|---|---|
| Component | `QrScanner` |
| Tech | `BarcodeDetector` API khi trình duyệt hỗ trợ; fallback `@zxing/browser` `[Đề xuất]` |
| Camera | `facingMode: environment`; xin quyền khi mở màn |

### Behavior

1. Đọc được QR ⇒ tách **mã lịch hẹn** (QR có thể là URL chứa mã hoặc chính mã) ⇒ tạm dừng quét ⇒ gọi `API-WB-03`.
2. Hiện `LookupResultCard` theo `checkInEligibility`:

   | Giá trị | UI |
   |---|---|
   | `ELIGIBLE` | Tên khách, xe, giờ hẹn + nút **Xác nhận check-in** |
   | `NOT_TODAY` | `Lịch hẹn của khách là ngày dd/mm.` — không có nút |
   | `ALREADY_CHECKED_IN` | `Đã check-in lúc HH:mm.` + `Xem chi tiết` |
   | `NOT_CONFIRMED` | `Lịch hẹn không ở trạng thái có thể check-in.` |
3. **Xác nhận check-in** ⇒ `API-WB-04 {action: CHECK_IN, expectedStatus: CONFIRMED, source: QR_SCAN}` ⇒ toast `Đã check-in` ⇒ tiếp tục quét.
4. `404` ⇒ `Không tìm thấy lịch hẹn tại xưởng của bạn.`
5. Không có camera / từ chối quyền ⇒ chỉ hiện `ManualCodeInput`.

## 4.10 CapacityGrid & BlockEditorPopover (SCR-804)

- Dữ liệu `API-WB-05` (7 ngày). Ô: `Đã đặt n` · `Khoá m` · `Còn nhận r`; ngày `isClosed` hiển thị xám.
- Nhấn ô ⇒ popover: stepper `Số chỗ khoá` (0..`maxBlock`), lý do (`Khách gọi điện` / `Khách vãng lai` / `Bảo trì` / `Khác`), ghi chú (bắt buộc khi `Khác`).
- `Lưu` ⇒ `API-WB-06` với giá trị tuyệt đối; `Gỡ khoá` ⇒ `blockedCount = 0`.
- Thành công ⇒ cập nhật ô từ response (không tải lại cả lưới).

## 4.11 Booking Settings (SCR-805)

- Radio `AUTO` / `MANUAL`, mô tả:
  - Tự động: `Khách giữ chỗ là lịch hẹn được xác nhận ngay.`
  - Thủ công: `Bạn cần chấp nhận trong 12 giờ, nếu không yêu cầu sẽ tự huỷ.`
- `Lưu` ⇒ `API-WB-08`. Nếu `pendingCount > 0` khi chuyển sang `AUTO`: toast `Còn N yêu cầu đang chờ — vẫn cần bạn xử lý trên Board.` (FF BR-811).

---

# 5. User Interaction

## 5.1 Interaction Flow

```text
Mở Board → GET bookings (hôm nay)
  ├── Chấp nhận nhanh (PENDING) → POST transitions ACCEPT → cập nhật dòng
  ├── Mở chi tiết → hành động có dialog (Từ chối / Huỷ / Hoàn tất)
  ├── Check-in QR → quét → GET by-code → Xác nhận → POST CHECK_IN
  └── Sức chứa → chọn ô → PUT slot-blocks
Tự làm mới Board mỗi 60s (khi tab đang hiển thị)
```

## 5.2 Interaction Table

| User Action | Frontend Behavior | Result |
|---|---|---|
| Đổi khoảng ngày / lọc / tìm | Gọi WB-01, cập nhật query string | Danh sách mới |
| Hành động nhanh trên dòng | WB-04, spinner trên nút của dòng đó | Dòng cập nhật từ response |
| Hành động cần dialog | Mở dialog, validate, WB-04 | Dòng + drawer cập nhật |
| `409 INVALID_STATUS_TRANSITION` | Toast theo `currentStatus`, tải lại booking | Nút cập nhật đúng |
| Quét QR | Tạm dừng camera, WB-03 | Thẻ kết quả |
| Lưu khoá chỗ | WB-06 | Ô cập nhật |
| Tab ẩn | Dừng tự làm mới | Tiết kiệm request |

---

# 6. State Management

## 6.1 State Model

```text
BoardState (SCR-801/802)
├── query: { from, to, statuses[], q }
├── data: { summary, items[], confirmationMode }
├── selectedBookingId
├── detail: BookingDetail | null
├── pendingAction: { bookingId, action } | null
├── dialog: { kind: 'reason'|'complete'|null, mode, reasonCode, note, actualCost }
└── request: { isLoading, isRefreshing, error }

CheckInState (SCR-803)
├── scannerStatus: 'idle'|'scanning'|'paused'|'unavailable'
├── code
├── lookup: LookupResult | null
└── request: { isLooking, isCheckingIn, error }

CapacityState (SCR-804)
├── from
├── days[]
├── editing: { date, timeSlot, blockedCount, reason, note } | null
└── request: { isLoading, isSaving, error }
```

## 6.2 State Fields (chính)

| State | Type | Default | Description |
|---|---|---|---|
| `query.from` / `query.to` | `string (YYYY-MM-DD)` | hôm nay | Khoảng ngày |
| `query.statuses` | `BookingStatus[]` | `[]` (tất cả) | Bộ lọc |
| `query.q` | `string` | `""` | Từ khoá |
| `pendingAction` | object? | `null` | Chặn bấm lặp trên cùng dòng |
| `dialog.actualCost` | `number?` | `null` | CompleteDialog |
| `scannerStatus` | enum | `idle` | Trạng thái camera |
| `editing.blockedCount` | `number` | giá trị hiện tại | Popover khoá |

`useReducer` cục bộ từng trang; không cần store toàn cục.

---

# 7. API Integration

> Contract ở [API Spec](../api/us-037-sprint-3-spec.api.md).

## 7.1 Board — `API-WB-01`

```http
GET /api/v1/workshop-owner/bookings?from={from}&to={to}&status={s1}&status={s2}&q={q}
```

Trigger: mở màn, đổi query, tự làm mới 60s, sau khi quay lại từ SCR-803/804.

## 7.2 Chi tiết — `API-WB-02`

```http
GET /api/v1/workshop-owner/bookings/{bookingId}
```

Trigger: mở drawer / trang chi tiết; sau lỗi `409`.

## 7.3 Tra mã — `API-WB-03`

```http
GET /api/v1/workshop-owner/bookings/by-code/{bookingCode}
```

## 7.4 Chuyển trạng thái — `API-WB-04`

```http
POST /api/v1/workshop-owner/bookings/{bookingId}/transitions
```

```json
{ "action": "{action}", "expectedStatus": "{booking.status}", "reasonCode": "{…}", "note": "{…}", "actualCost": 1850000, "source": "BOARD|QR_SCAN" }
```

Success ⇒ thay item trong `data.items` và `detail` bằng response; cập nhật `summary` cục bộ (giảm trạng thái cũ, tăng trạng thái mới).

## 7.5 Sức chứa — `API-WB-05` / Khoá — `API-WB-06`

```http
GET /api/v1/workshop-owner/capacity?from={from}&days=7
PUT /api/v1/workshop-owner/slot-blocks
```

## 7.6 Cài đặt — `API-WB-07` / `API-WB-08`

```http
GET /api/v1/workshop-owner/booking-settings
PUT /api/v1/workshop-owner/booking-settings
```

---

# 8. Client-side Validation

## 8.1 Validation Rules

| Field | Rule | Error Message |
|---|---|---|
| Lý do (Từ chối/Huỷ) | Bắt buộc chọn | `Vui lòng chọn lý do.` |
| Ghi chú khi `Khác` | Bắt buộc, ≤ 255 | `Vui lòng ghi rõ lý do.` |
| Chi phí thực tế | Số ≥ 0, ≤ 999.999.999 | `Chi phí không hợp lệ.` |
| Số chỗ khoá | 0..`maxBlock` (stepper chặn) | `Chỉ còn {maxBlock} chỗ trống để khoá.` |
| Ghi chú khoá khi `Khác` | Bắt buộc | `Vui lòng ghi chú lý do khoá.` |
| Mã lịch hẹn nhập tay | `^[A-Z0-9-]{4,20}$` sau khi upper-case | `Mã lịch hẹn không hợp lệ.` |

## 8.2 Validation Timing

- Validate khi bấm nút xác nhận trong dialog/popover; không gọi API khi lỗi.
- Không tự kiểm tra state machine ở FE — dựa `allowedActions`.

---

# 9. Loading States

- **Board lần đầu:** skeleton 6 thẻ tóm tắt + 5 dòng bảng.
- **Tự làm mới:** không skeleton; chỉ chấm tròn nhỏ "Đang cập nhật" ở toolbar.
- **Hành động trên dòng:** spinner trên nút; các nút khác của dòng disable (`pendingAction`).
- **Dialog gửi:** disable hai nút, không cho đóng.
- **SCR-803:** `Đang tìm…` trên thẻ kết quả; camera tạm dừng.
- **SCR-804:** skeleton lưới; ô đang lưu hiển thị spinner.

---

# 10. Empty States

| Điều kiện | Nội dung |
|---|---|
| Không có lịch hẹn trong khoảng | `Chưa có lịch hẹn nào {hôm nay / trong 7 ngày tới}.` |
| Có bộ lọc nhưng không khớp | `Không có lịch hẹn phù hợp bộ lọc.` + `Xoá bộ lọc` |
| SCR-804 xưởng đóng cửa cả 7 ngày | `Xưởng không mở cửa trong 7 ngày tới. Kiểm tra giờ hoạt động.` |

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
| `401 UNAUTHORIZED` / `SESSION_REVOKED` | Về Login, toast `Phiên đăng nhập đã hết, vui lòng đăng nhập lại.` |
| `403 ONBOARDING_REQUIRED` | Onboarding chủ xưởng |
| `403 WORKSHOP_INACTIVE` | Banner `Xưởng đang tạm ngưng — chỉ xem, không thao tác được.`; ẩn mọi nút ghi |
| `404 BOOKING_NOT_FOUND` | Đóng drawer, toast `Không tìm thấy lịch hẹn.`, tải lại Board |
| `409 INVALID_STATUS_TRANSITION` | Toast `Lịch hẹn vừa được cập nhật ({trạng thái mới}).` + tải lại chi tiết |
| `409 CHECK_IN_NOT_TODAY` | Thẻ kết quả `Lịch hẹn của khách là ngày dd/mm.` |
| `409 CONFIRM_DEADLINE_PASSED` | Toast `Yêu cầu đã quá hạn xác nhận và bị huỷ tự động.` + tải lại |
| `409 NO_SHOW_TOO_EARLY` | Lỗi trong dialog `Có thể đánh dấu khách không đến sau HH:mm.` |
| `409 BLOCK_EXCEEDS_FREE_CAPACITY` | Lỗi trong popover với `details.maxBlock`; cập nhật trần stepper |
| `422 BLOCK_DATE_OUT_OF_RANGE` / `SLOT_OUT_OF_HOURS` | Lỗi trong popover |
| `400 REASON_REQUIRED` / `INVALID_REQUEST` | Lỗi tại field |
| `500` / `503` | Toast `Tạm thời chưa thực hiện được, thử lại nhé.`; giữ dialog và dữ liệu đã nhập |

---

# 12. Error Handling

## 12.1 Field-level Error

Dưới ô lý do / ghi chú / chi phí / số chỗ khoá.

## 12.2 Screen-level Error

Tải Board / Sức chứa lỗi ⇒ General Error; tự làm mới lỗi ⇒ giữ dữ liệu cũ + banner nhỏ `Không cập nhật được — dữ liệu có thể chưa mới nhất.`

## 12.3 Retry Behavior

- Thử lại chỉ request lỗi; giữ query, dialog, giá trị đã nhập.
- Không tự retry `POST transitions` (tránh thao tác trùng ngoài ý muốn) — để chủ xưởng bấm lại; backend idempotent theo trạng thái.

---

# 13. Navigation

## 13.1 Routes

| Route | Purpose |
|---|---|
| `/technician` | Dashboard (hiện có) — khối lịch hẹn hôm nay dùng WB-01 |
| `/technician/board` | SCR-801 |
| `/technician/board/:bookingId` | SCR-802 (drawer trên desktop, trang trên mobile) |
| `/technician/check-in` | SCR-803 |
| `/technician/capacity` | SCR-804 |
| `/technician/settings/booking` | SCR-805 |
| `/technician/quote-review` | Duyệt báo giá (F5b) |

Thêm route vào `frontend/src/app/App.tsx` trong layout Portal; thêm mục sidebar theo vai trò chủ xưởng.

## 13.2 Navigation Rules

- Mở/đóng drawer đổi URL (`/technician/board/:id` ↔ `/technician/board`) để chia sẻ/quay lại được; giữ query string.
- Back từ SCR-803 ⇒ Board, Board tự tải lại.

---

# 14. Permission / Visibility

| UI Element | Condition |
|---|---|
| Toàn bộ route `/technician/*` | Vai trò chủ xưởng |
| Nút hành động | Theo `allowedActions` |
| Nút ghi (hành động, khoá, lưu cài đặt) | Ẩn khi `WORKSHOP_INACTIVE` |
| SĐT khách | Chỉ trong SCR-802 |
| Báo giá | Có `quote` ⇒ link sang Duyệt báo giá |

## 14.1 Role-based Behavior

| Role | Access |
|---|---|
| Chủ xưởng | Toàn bộ Board của xưởng mình |
| Chủ xe | Không truy cập |

> Chỉ kiểm tra hiển thị; backend quyết định.

---

# 15. Responsive / Device Behavior

## Desktop (chính)

- Bảng đầy đủ cột; drawer chi tiết 480px; lưới sức chứa 7 cột ngày.

## Tablet

- Ẩn cột `Nhãn` vào badge nhỏ cạnh trạng thái; drawer full-height 60% chiều ngang.

## Mobile

- Board dạng thẻ theo khung giờ; chi tiết là trang riêng.
- SCR-803 camera full-width, nút cao ≥ 48px.
- SCR-804 hiển thị 1 ngày/lần với vuốt ngang đổi ngày.

---

# 16. Accessibility

- Bảng dùng `<table>` với tiêu đề cột; dòng có thể focus, Enter mở chi tiết.
- Trạng thái = chữ + icon, không chỉ màu; nhãn "Hạn xác nhận" đỏ kèm icon đồng hồ.
- Dialog: focus vào lựa chọn an toàn (`Để sau` / đóng); Esc đóng khi không đang gửi.
- Camera: có nút bật/tắt; thông báo `aria-live` khi quét thành công.

---

# 17. Analytics / Tracking

| Event | Trigger | Properties |
|---|---|---|
| `board_viewed` | Mở Board | `range`, `statusFilterCount` |
| `booking_transition` | WB-04 thành công | `action`, `reasonCode`, `source` |
| `booking_transition_failed` | WB-04 lỗi | `action`, `errorCode` |
| `checkin_scan_result` | Nhận kết quả WB-03 | `eligibility`, `method` (`qr`/`manual`) |
| `slot_block_saved` | WB-06 thành công | `blockedCount`, `reason` |
| `confirmation_mode_changed` | WB-08 thành công | `mode` |

Không gửi tên, SĐT, biển số, mã lịch hẹn, ghi chú.

---

# 18. Acceptance Criteria

## AC-FE-801 — Board mặc định hôm nay (FF UC-801)

**Given** chủ xưởng đăng nhập

**When** mở `/technician/board`

**Then** thấy tóm tắt 6 trạng thái và danh sách lịch hôm nay nhóm theo khung giờ.

## AC-FE-802 — Chỉ nút hợp lệ (FF AC-802)

**Given** booking `CONFIRMED`

**When** mở chi tiết

**Then** chỉ có `Check-in` và `Huỷ lịch`; không có `Hoàn tất`.

## AC-FE-803 — Chấp nhận nhanh (FF AC-805)

**Given** dòng `PENDING` có `ACCEPT`

**When** nhấn `Chấp nhận`

**Then** gọi WB-04 một lần; dòng chuyển `Đã xác nhận` có mã lịch hẹn; thẻ tóm tắt cập nhật.

## AC-FE-804 — Check-in QR (FF AC-806)

**Given** QR hợp lệ hôm nay

**When** quét và nhấn `Xác nhận check-in`

**Then** gọi WB-04 với `source = QR_SCAN`; toast `Đã check-in`; quét lại cùng QR hiện `Đã check-in lúc HH:mm`.

## AC-FE-805 — Hoàn tất có chi phí (FF AC-807)

**Given** booking `IN_PROGRESS`

**When** mở `Hoàn tất`, nhập 1.850.000, xác nhận

**Then** gửi `actualCost = 1850000`; trạng thái `Hoàn tất`; timeline có sự kiện mới.

## AC-FE-806 — No-show sớm bị chặn (FF AC-810)

**Given** giờ hẹn 09:00, hiện 09:20

**When** mở `Huỷ lịch`

**Then** lựa chọn `Khách không đến` bị disable với chú thích `Có thể chọn sau 09:30`.

## AC-FE-807 — Khoá vượt chỗ (FF AC-804)

**Given** ô có `maxBlock = 1`

**When** chủ xưởng cố tăng stepper lên 2

**Then** stepper dừng ở 1; nếu backend vẫn trả `409` (dữ liệu cũ) thì hiện lỗi với `maxBlock` mới.

## AC-FE-808 — Xung đột trạng thái (FF EF-802)

**Given** khách vừa huỷ booking trong lúc chi tiết đang mở

**When** chủ xưởng nhấn `Check-in`

**Then** toast `Lịch hẹn vừa được cập nhật (Đã huỷ).`, chi tiết tải lại, không còn nút hành động.

---

# 19. Technical Notes

## Frontend Stack

```text
Framework: React 19 + Vite
Language: TypeScript
State Management: useReducer cục bộ trong trang
Networking: fetch qua shared/api/client.ts
Navigation: React Router 7 (search params cho bộ lọc Board)
UI Library: Tailwind CSS 4 + lucide-react
QR: BarcodeDetector API; fallback @zxing/browser [Đề xuất]
```

## Component Structure

```text
frontend/src/features/workshop-board/
├── pages/
│   ├── WorkshopBoard.tsx          (SCR-801 + drawer SCR-802)
│   ├── BookingDetailPage.tsx      (SCR-802 trên mobile)
│   ├── CheckIn.tsx                (SCR-803)
│   ├── Capacity.tsx               (SCR-804)
│   └── BookingSettings.tsx        (SCR-805)
├── components/
│   ├── BoardToolbar.tsx · SummaryCards.tsx · BookingTable.tsx · BookingRow.tsx
│   ├── BookingDrawer.tsx · ActionPanel.tsx · StatusTimeline.tsx
│   ├── ReasonDialog.tsx · CompleteDialog.tsx
│   ├── QrScanner.tsx · LookupResultCard.tsx
│   └── CapacityGrid.tsx · BlockEditorPopover.tsx
├── api.ts
├── labels.ts                      (map status / reason / source → tiếng Việt)
└── types.ts
```

## Implementation Notes

- `TechnicianDashboard.tsx` hiện dùng mock ⇒ chuyển khối "Lịch hẹn hôm nay" sang WB-01 (`from=to=today`, 5 dòng đầu).
- Tự làm mới dùng `document.visibilityState`; huỷ request cũ bằng `AbortController` khi query đổi.
- Giờ hiển thị theo `Asia/Ho_Chi_Minh`; `bookingDate` + `timeSlot` là giờ địa phương, không chuyển múi.

---

# 20. Open Questions

- [ ] Thư viện quét QR (BarcodeDetector chưa có trên Safari/Firefox) — chốt `@zxing/browser`?
- [ ] Board cần realtime thay vì làm mới 60s?
- [ ] Q-805 — hiển thị SĐT khách.
- [ ] Dashboard `/technician` và Board có gộp làm một không?

---

# 21. Related Documents

- Functional Spec: [us-037-sprint-3-spec.ff.md](../feature-functional/us-037-sprint-3-spec.ff.md)
- API Spec: [us-037-sprint-3-spec.api.md](../api/us-037-sprint-3-spec.api.md)
- Entity Spec: [us-037-sprint-3-spec.entity.md](../entity/us-037-sprint-3-spec.entity.md)
- us-033 FE (chi tiết lịch hẹn phía chủ xe): [us-033-sprint-3-spec.fe.md](us-033-sprint-3-spec.fe.md)
- us-041 FE (phiếu hỗ trợ trên Portal): [us-041-sprint-4-spec.fe.md](../../sprint-4/frontend/us-041-sprint-4-spec.fe.md)
- Design / Figma: `[Chưa có]`

---

# 22. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Team 4 Người | Initial version: SCR-801 → SCR-805 |
