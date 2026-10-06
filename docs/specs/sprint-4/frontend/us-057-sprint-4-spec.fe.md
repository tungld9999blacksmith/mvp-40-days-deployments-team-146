# Frontend Technical Specification — Tiến độ dịch vụ chi tiết 6 bước

> **Cập nhật phạm vi (02/10/2026):** các phần dưới đây trong tài liệu này không còn áp dụng.
>
> - Kết nối Discord (`user_discord_link`, ENT-417): **đã bỏ**. Nhắc bảo dưỡng, nhắc lịch hẹn và hỏi thăm hiện trong mục **Thông báo** của app; danh sách kênh ngoài (Zalo / Telegram / SMS / Email) vẫn có nhưng đều "Sắp có", bật nhắc không bắt buộc chọn kênh.

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
| Version | `v1.1` |
| Status | `Draft` |
| Feature flag | Ẩn toàn bộ khi `FEATURE_SERVICE_PROGRESS_ENABLED = false` (API trả `404 FEATURE_DISABLED`) |
| Last Updated | `2026-09-30` |

---

# 2. Components

## 2.0 Mã mốc và nhãn (FF BR-1302)

| `stage` | Nhãn | Ai ghi | Mốc kế tiếp hợp lệ (để đối chiếu; FE luôn dùng `nextStages` từ API) |
|---|---|---|---|
| `CHECKED_IN` | Đã tiếp nhận | Hệ thống — khi check-in (us-037) | `INSPECTING` (hệ thống) |
| `INSPECTING` | Đang kiểm tra | Hệ thống — khi bắt đầu | `SERVICING` |
| `SERVICING` | Đang bảo dưỡng | Chủ xưởng | `WAITING_PARTS`, `QUALITY_CHECK` |
| `WAITING_PARTS` | Chờ phụ tùng | Chủ xưởng | `SERVICING` |
| `QUALITY_CHECK` | Kiểm tra chất lượng | Chủ xưởng | `READY_FOR_PICKUP`, `SERVICING` |
| `READY_FOR_PICKUP` | Sẵn sàng giao xe | Chủ xưởng | — (chờ Hoàn tất ở us-037) |

Không có nút "hoàn tác"; FE không tự suy luận bước kế tiếp từ bảng này.

## 2.1 StageStepper (dùng chung)

- 6 bước ngang (desktop) / dọc (mobile): Đã tiếp nhận · Đang kiểm tra · Đang bảo dưỡng · Chờ phụ tùng · Kiểm tra chất lượng · Sẵn sàng giao xe.
- Bước hiện tại nổi bật; "Chờ phụ tùng" chỉ hiện khi đã từng xảy ra (tránh gây hiểu nhầm là bước bắt buộc).
- Dưới stepper: danh sách `entries` (giờ VN + nhãn + ghi chú), mới nhất trên cùng. Portal hiện thêm người ghi ("Hệ thống" / tên chủ xưởng); App chủ xe chỉ hiện giờ, nhãn, ghi chú.
- Booking đã check-in trước khi bật tính năng (chưa có dòng `CHECKED_IN`): hiển thị mốc hiện tại theo `currentStage` backend suy ra, không báo lỗi (FF EDGE-1304).

## 2.2 ProgressPanel (SCR-1301 — Portal)

- Chỉ hiển thị khi `bookingStatus ∈ {CHECKED_IN, IN_PROGRESS, COMPLETED}`.
- Nút cho từng `nextStages` (ví dụ "Chờ phụ tùng", "Kiểm tra chất lượng"); `nextStages = []` ⇒ không có nút (gồm cả khi booking `COMPLETED` / `CANCELLED` — tiến độ đóng băng, FF BR-1301, AC-1305).
- Từ `QUALITY_CHECK` về `SERVICING`: nút ghi "Làm lại (về Đang bảo dưỡng)", hộp ghi chú khuyến nghị nhập lý do (FF AF-1302).
- Mốc khác `WAITING_PARTS`: ghi chú tuỳ chọn ≤ 500 ký tự.
- Mọi ô ghi chú có dòng nhắc "Khách hàng sẽ thấy ghi chú này. Không nhập số điện thoại, VIN hay thông tin cá nhân" (FF BR-1303).
- Chọn `WAITING_PARTS` ⇒ hộp thoại ghi chú bắt buộc (10–500) + dòng nhắc "Khách hàng sẽ thấy ghi chú này".
- Mọi request gửi `expectedCurrentStage = currentStage` đang hiển thị.
- Khi bấm Hoàn tất (us-037) mà `currentStage ≠ READY_FOR_PICKUP`: thêm dòng cảnh báo vào hộp thoại hoàn tất (FF AF-1301).

## 2.3 ProgressTimeline (SCR-1302 — App chủ xe)

- Nằm trong ticket khi booking `CHECKED_IN` / `IN_PROGRESS` / `COMPLETED`, thay vị trí QR.
- Tự làm mới `API-PG-03` mỗi 60 s khi tab đang hiển thị (`document.visibilityState === 'visible'`) và chưa `isFrozen`.
- `READY_FOR_PICKUP` ⇒ banner "Xe đã sẵn sàng, bạn có thể đến nhận" + địa chỉ/SĐT xưởng.
- `WAITING_PARTS` ⇒ hiển thị nổi bật ghi chú của xưởng (phụ tùng chờ, dự kiến).
- Thông báo Discord khi vào `WAITING_PARTS` / `READY_FOR_PICKUP` do backend gửi (FF BR-1305); FE không gửi gì, chỉ làm mới dữ liệu.

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
- **AC-FE-1304** — Booking `COMPLETED` ⇒ Portal không còn nút cập nhật mốc.

# 6. Truy vết FF → FE

| FF | Nội dung | FE |
|---|---|---|
| UC-1301, AC-1301 | Hệ thống ghi `CHECKED_IN`, `INSPECTING` khi check-in / bắt đầu | §2.0, §3 (invalidate `progress` sau `API-WB-04`) |
| UC-1302, BR-1302, EF-1301, AC-1302 | Chủ xưởng cập nhật theo thứ tự hợp lệ | §2.0, §2.2 (nút theo `nextStages`), §3 `INVALID_STAGE_TRANSITION` |
| BR-1303, AC-1303, EDGE-1302 | Ghi chú bắt buộc khi chờ phụ tùng, hiển thị cho khách, không PII | §2.2, AC-FE-1302 |
| AF-1301 | Hoàn tất khi chưa "Sẵn sàng giao xe" | §2.2 (cảnh báo trong hộp hoàn tất) |
| AF-1302 | Làm lại sau kiểm tra chất lượng | §2.2 |
| EF-1302 | Hai tab cập nhật cùng lúc | §2.2 (`expectedCurrentStage`), §3 `PROGRESS_CHANGED` |
| UC-1303, AC-1304 | Chủ xe xem tiến độ booking của mình | §2.3, §3 (`404` ⇒ ẩn khối) |
| BR-1301, AC-1305, EDGE-1301/1303 | Chỉ ghi khi đang làm; đóng băng sau hoàn tất | §2.2, §4, AC-FE-1304 |
| BR-1304 | Append-only, có người ghi | §2.1 (danh sách `entries`, Portal hiện người ghi) |
| BR-1305, EF-1303, EDGE-1305/1306 | Thông báo cho chủ xe | Backend — §2.3 ghi chú |
| BR-1306 | Chủ xưởng chỉ cập nhật xưởng mình | Backend (`404` ⇒ ẩn panel) |
| EDGE-1304 | Check-in trước khi bật tính năng | §2.1 |

---

# 7. Analytics

| Event | Properties |
|---|---|
| `progress_stage_added` | `stage`, `fromStage` |
| `progress_viewed_by_owner` | `currentStage` |

# 8. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu |
| `v1.1` | `2026-10-01` | Team 4 Người | Đối chiếu FF: bảng mã mốc ↔ nhãn, nút làm lại sau kiểm tra chất lượng, quy tắc ghi chú (tuỳ chọn ≤ 500, không PII), người ghi trên Portal, đóng băng sau hoàn tất, EDGE-1304, bảng truy vết FF → FE |
