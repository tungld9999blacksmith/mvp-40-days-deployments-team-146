# Frontend Technical Specification — Tiến độ dịch vụ chi tiết 6 bước

> Đặc tả frontend cho Feature `FEAT-PROG-001` (PRD F8b, US-057 → US-059).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-057-sprint-4-spec.ff.md) · **API:** [API Spec](../api/us-057-sprint-4-spec.api.md)
>
> **Phạm vi FE:** thêm khối "Tiến độ" vào hai màn đã có — chi tiết lịch hẹn trên Board (`/technician/board/:bookingId`, us-037 SCR-802) và Booking Ticket (`/bookings/:bookingId`, us-053 SCR-1201). Không có route mới.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-PROG-001` |
| Screen | `SCR-1301` ProgressPanel (Portal) · `SCR-1302` ProgressTimeline (App) |
| Route | `/technician/board/:bookingId` · `/bookings/:bookingId` |
| Version | `v1.0` |
| Status | `Draft` |
| Feature flag | Ẩn toàn bộ khi `FEATURE_SERVICE_PROGRESS_ENABLED = false` (API trả `404 FEATURE_DISABLED`) |
| Last Updated | `2026-09-30` |

---

# 2. Components

## 2.1 StageStepper (dùng chung)

- 6 bước ngang (desktop) / dọc (mobile): Đã tiếp nhận · Đang kiểm tra · Đang bảo dưỡng · Chờ phụ tùng · Kiểm tra chất lượng · Sẵn sàng giao xe.
- Bước hiện tại nổi bật; "Chờ phụ tùng" chỉ hiện khi đã từng xảy ra (tránh gây hiểu nhầm là bước bắt buộc).
- Dưới stepper: danh sách `entries` (giờ VN + nhãn + ghi chú).

## 2.2 ProgressPanel (SCR-1301 — Portal)

- Chỉ hiển thị khi `bookingStatus ∈ {CHECKED_IN, IN_PROGRESS, COMPLETED}`.
- Nút cho từng `nextStages` (ví dụ "Chờ phụ tùng", "Kiểm tra chất lượng"); `nextStages = []` ⇒ không có nút.
- Chọn `WAITING_PARTS` ⇒ hộp thoại ghi chú bắt buộc (10–500) + dòng nhắc "Khách hàng sẽ thấy ghi chú này".
- Mọi request gửi `expectedCurrentStage = currentStage` đang hiển thị.
- Khi bấm Hoàn tất (us-037) mà `currentStage ≠ READY_FOR_PICKUP`: thêm dòng cảnh báo vào hộp thoại hoàn tất (FF AF-1301).

## 2.3 ProgressTimeline (SCR-1302 — App chủ xe)

- Nằm trong ticket khi booking `CHECKED_IN` / `IN_PROGRESS` / `COMPLETED`, thay vị trí QR.
- Tự làm mới `API-PG-03` mỗi 60 s khi tab đang hiển thị (`document.visibilityState === 'visible'`) và chưa `isFrozen`.
- `READY_FOR_PICKUP` ⇒ banner "Xe đã sẵn sàng, bạn có thể đến nhận" + địa chỉ/SĐT xưởng.

---

# 3. API Integration & Errors

| Action | API | Error → FE |
|---|---|---|
| Tải (Portal) | `GET /workshop-owner/bookings/:id/progress` | `404 FEATURE_DISABLED` ⇒ ẩn panel |
| Thêm mốc | `POST …/progress` | `409 PROGRESS_CHANGED` ⇒ toast "Tiến độ vừa được cập nhật", tải lại · `422 INVALID_STAGE_TRANSITION` ⇒ tải lại nút theo `details.nextStages` · `422 NOTE_REQUIRED` ⇒ lỗi tại ô ghi chú · `409 BOOKING_NOT_IN_PROGRESS` ⇒ tải lại chi tiết booking |
| Tải (App) | `GET /bookings/:id/progress` | `404` ⇒ ẩn khối |

Sau khi `API-WB-04` `CHECK_IN`/`START` thành công, Portal invalidate cả `booking` và `progress`.

---

# 4. States

- Loading: skeleton stepper.
- Empty (chưa check-in): App không hiển thị khối; Portal hiển thị "Tiến độ bắt đầu khi xe được check-in".

---

# 5. Acceptance Criteria (FE)

- **AC-FE-1301** — Portal chỉ hiện nút cho các mốc trong `nextStages`.
- **AC-FE-1302** — `WAITING_PARTS` không gửi được khi ghi chú < 10 ký tự.
- **AC-FE-1303** — App tự làm mới mỗi 60 s khi đang xem và dừng khi `isFrozen = true`.

---

# 6. Analytics

| Event | Properties |
|---|---|
| `progress_stage_added` | `stage`, `fromStage` |
| `progress_viewed_by_owner` | `currentStage` |

# 7. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu |
