# Frontend Technical Specification — Hộp thư Thông báo trong app

> Đặc tả frontend cho Feature `FEAT-NOTI-003` (PRD F7 kênh trong app, US-069 → US-072).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-069-sprint-4-spec.ff.md) · **API:** [API Spec](../api/us-069-sprint-4-spec.api.md)
>
> **Bối cảnh:** các màn đã chạy (`frontend/src/features/notifications/`). Tài liệu ghi lại hành vi hiện tại làm chuẩn kiểm thử. Màn **Cài đặt thông báo** (`/notifications/settings`) thuộc [us-021 FE](../../sprint-2/frontend/us-021-sprint-2-spec.fe.md) SCR-501, không lặp lại ở đây.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-NOTI-003` |
| Screen | `SCR-1701` Thông báo (chủ xe) · `SCR-1702` Lời nhắc bảo dưỡng · `SCR-1703` Thông báo (chủ xưởng) |
| Route | `/notifications` · `/notifications/reminders/:reminderId[?action=chat\|booking]` · `/technician/notifications` |
| Version | `v1.1` |
| Status | `Draft` |
| Owner | Mai Văn Trung |
| Last Updated | `2026-10-07` |

---

# 2. Screen Overview

| | SCR-1701 | SCR-1702 | SCR-1703 |
|---|---|---|---|
| Component | `Notifications variant="owner"` | `ReminderDetail` | `Notifications variant="portal"` |
| Guard | `RequireActiveUser` (`OwnerLayout`) | `RequireActiveUser` | `RequireActiveWorkshopOwner` (`TechnicianLayout`) |
| Entry | Chuông ở thanh trên (`AppLayout`, `notificationsPath`), menu "Thông báo" | "Xem lời nhắc" ở SCR-1701, link email | Chuông, menu "Thông báo" của Portal |
| Exit | `entry.action.to` (§4.2), "Cài đặt" ⇒ `/notifications/settings` | §4.4 | `entry.action.to` |

---

# 3. UI Structure

```text
SCR-1701 / SCR-1703
┌──────────────────────────────────────────────┐
│ Thông báo                          [⚙ Cài đặt]│  ← nút Cài đặt chỉ ở SCR-1701
│ 2 việc cần bạn xem                            │
├──────────────────────────────────────────────┤
│ (icon) Tiêu đề  •               hôm qua       │
│        Nội dung                               │
│        Hành động ›                            │
├──────────────────────────────────────────────┤
│ …                                             │
└──────────────────────────────────────────────┘

SCR-1702
← Thông báo
Lời nhắc bảo dưỡng
[Ghi chú: lời nhắc cũ / đã đóng]
┌ Dữ liệu dùng cho lời nhắc ┐ ┌ Trạng thái gửi lời nhắc ┐ ┌ Tình trạng hiện tại ┐
Quản lý / tắt nhận email
```

---

# 4. Component Specification

## 4.1 FeedCard

| Phần | Quy tắc |
|---|---|
| Biểu tượng | `warning` ⇒ tam giác cảnh báo · `success` ⇒ dấu tích · `error` ⇒ dấu X · `info` ⇒ chuông |
| Viền | `unread` ⇒ viền nhấn màu thương hiệu |
| Chấm "mới" | Khi `unread` (`aria-label="Mới"`) |
| Thời điểm | `formatRelativeDay(at)`; ẩn khi `at` rỗng (lịch hẹn chờ xác nhận ở SCR-1703) |
| Hành động | Nút text + mũi tên; `navigate(action.to)` |

## 4.2 Ánh xạ mục chủ xe ⇒ thẻ (`toFeedEntry`, `feed.ts`)

| `kind` | Sắc thái | Tiêu đề | Nội dung | Hành động | FF |
|---|---|---|---|---|---|
| `MAINTENANCE_REMINDER` | `EXPIRED`/`URGENT` ⇒ warning; còn lại info | `EARLY` "Sắp đến mốc bảo dưỡng" · `WARNING` "Sắp đến hạn bảo dưỡng" · `URGENT` "Gần tới hạn bảo dưỡng" · `EXPIRED` "Đã quá hạn bảo dưỡng" | Mở: "Xe sắp tới / đã quá mốc bảo dưỡng {km}." · Đóng: "Mốc {km} — {lý do}" | "Xem lời nhắc" ⇒ `/notifications/reminders/{id}` | BR-1705, AF-1702 |
| `QUOTE_RESULT` | `APPROVED` ⇒ success; `REJECTED` ⇒ error | "Báo giá đã được duyệt" / "Báo giá chưa được duyệt" | "Xưởng tại {xưởng} đã duyệt báo giá: {VNĐ}." / "… đã phản hồi báo giá. Xem lý do trong chi tiết." | "Xem báo giá" ⇒ `/quotes/{quoteId}` | BR-1704 |
| `BOOKING_UPDATE` | `CONFIRMED`/`COMPLETED` ⇒ success; `CANCELLED` ⇒ error | "Lịch hẹn đã được xác nhận" / "Lịch hẹn đã bị huỷ" / "Đã hoàn tất dịch vụ" | "{mã} · {HH:mm dd/mm/yyyy} tại {xưởng}." (+ "Bạn có thể đặt lịch khác." khi huỷ) | "Xem lịch hẹn" ⇒ `/bookings/{bookingId}` | BR-1703 |
| `FOLLOW_UP` | info | "Mời bạn đánh giá lần dịch vụ" | "Lần dịch vụ tại {xưởng} thế nào? …" | "Đánh giá" ⇒ `/follow-ups/{followUpId}` | — |
| `BOOKING_REMINDER` | `unread` ⇒ warning; còn lại info | "Nhắc lịch hẹn sắp tới" | "{mã} · {HH:mm dd/mm/yyyy} tại {xưởng}." (+ "Xác nhận bạn sẽ đến, hoặc đổi / huỷ nếu cần." khi `unread`) | "Xem lịch hẹn" ⇒ `/bookings/{bookingId}?src=REMINDER_24H` | BR-1707 |
| khác / thiếu khối | — | Bỏ qua mục | | | BR-1711 |

- Lý do đóng lời nhắc (`RESOLUTION_TEXT`, `reminderActions.ts`): `HAS_BOOKING` "Đã có lịch hẹn cho mốc này." · `MAINTENANCE_COMPLETED` "Đã hoàn tất bảo dưỡng; mốc tiếp theo được tính lại." · `MILESTONE_CHANGED` "Xe đã chuyển sang mốc bảo dưỡng khác." · `SUPERSEDED` "Lời nhắc sớm đã được thay bằng lời nhắc quá hạn." · `BEFORE_WINDOW` "Xe hiện chưa nằm trong khoảng nhắc đã cấu hình." · `STATUS_CHANGED` "Tình trạng xe đã thay đổi; lời nhắc này không còn áp dụng." · không rõ ⇒ "lời nhắc đã đóng."
- "tại {xưởng}" bị bỏ khi không có tên xưởng (FF EDGE-1704).
- Tiền: `formatVnd`; `approvedTotal` dạng chuỗi được chuyển sang số, không hợp lệ ⇒ bỏ phần tiền.

## 4.3 Ánh xạ mục chủ xưởng ⇒ thẻ (`portalEntries`, `feed.ts`)

| Nguồn | Sắc thái | Tiêu đề | Nội dung | Cần xem | Hành động |
|---|---|---|---|---|---|
| Báo giá `PENDING_APPROVAL` (`API-QT-11`) | `isWaitingLong` ⇒ warning, còn lại info | "Báo giá chờ duyệt quá 24 giờ" / "Báo giá chờ duyệt" | "{khách} · {dòng xe} · mốc {km}" | `isWaitingLong` | "Duyệt báo giá" ⇒ `/technician/quote-review?quoteId=…` |
| Lịch hẹn `PENDING` 7 ngày tới (`API-WB-01`) | warning | "Lịch hẹn chờ xác nhận" | "{khách} · {dòng xe} · {HH:mm} {dd/mm/yyyy}" | luôn | "Xem lịch hẹn" ⇒ `/technician/board/{bookingId}` |

Báo giá đứng trước lịch hẹn (FF BR-1710).

## 4.4 ReminderDetail (SCR-1702)

| Khối | Nội dung | FF |
|---|---|---|
| Ghi chú đầu trang | `snapshotAvailable = false` ⇒ "Lời nhắc cũ chưa lưu dữ liệu tại thời điểm tạo. Tình trạng hiện tại được hiển thị bên dưới." · `resolved` ⇒ câu lý do (§4.2) | BR-1706, AF-1702 |
| Dữ liệu dùng cho lời nhắc | "Mốc {km}[ / {tháng} tháng] · {Theo số km / Theo thời gian / Theo số km và thời gian}"; "Hạn theo thời gian: {dd/mm/yyyy}"; ODO + ngày cập nhật, hoặc "Chưa có ODO; nhắc theo thời gian."; cảnh báo "Dữ liệu ODO đã cũ…" khi `odometerStale`; danh sách hạng mục. Khi `snapshotAvailable = false`: chỉ hiện mốc, câu "Chưa có dữ liệu ODO tại thời điểm tạo lời nhắc." | BR-1705, BR-1706, EDGE-1707 |
| Trạng thái gửi lời nhắc | Chỉ khi `deliveries.length > 0`. Mỗi dòng: kênh ("Thư mô phỏng" / "Email thử thật [DEMO]" / tên kênh) · trạng thái theo bảng §4.5 · "{n} lần thử" | BR-1705 |
| Tình trạng hiện tại | "Mốc tiếp theo: {km} · hạn {dd/mm/yyyy}." hoặc "Chưa đủ dữ liệu để xác định mốc hiện tại." · nút §4.6 | BR-1705, EDGE-1706 |
| Chân trang | "Quản lý / tắt nhận email" ⇒ `/notifications/settings#channel-EMAIL` | — |

## 4.5 Nhãn trạng thái gửi email

`accepted` "Nhà cung cấp đã tiếp nhận" · `delivered` "Đã giao thư" · `delayed` "Giao thư chậm" · `bounced` "Không giao được thư" · `complained` "Người nhận báo spam" · `suppressed` "Địa chỉ bị chặn" · `failed` "Gửi không thành công" · `pending` "Đang chờ gửi" · `cancelled` "Đã dừng" · `needs_reconciliation` "Cần kiểm tra lại kết quả gửi" · chế độ mô phỏng + `SENT` ⇒ "Đã mô phỏng" · khác ⇒ `SENT` "Đã tiếp nhận", còn lại "Chưa hoàn tất".

## 4.6 Hành động của lời nhắc (`reminderActions`)

| Nút | Hiện khi | Đích |
|---|---|---|
| "Đặt lịch theo mốc hiện tại" | Có `currentStatus.nextMilestone` **và** mốc đó chưa có lịch (`hasCurrentBooking = false`; backend cũ thiếu cờ ⇒ suy ra từ `resolutionReason = HAS_BOOKING` cùng mốc) | `/booking?userVehicleId=…&odoMilestone={mốc hiện tại}` |
| "Xem lịch hẹn" | Không có nút đặt lịch **và** (`hasCurrentBooking` hoặc `resolutionReason = HAS_BOOKING`) | `/bookings` |
| "Hỏi trợ lý" | Luôn | `/ai/new?userVehicleId=…&q=Hãy giải thích lời nhắc bảo dưỡng {reminderId} và tình trạng hiện tại của xe tôi.` |

## 4.7 Liên kết sâu từ email (FF AF-1703)

Sau khi tải xong (không lỗi, không đang tải lại): `?action=chat` ⇒ `navigate(chat, { replace: true })`; `?action=booking` ⇒ chỉ chuyển khi nút đặt lịch được phép (§4.6), ngược lại ở lại SCR-1702.

---

# 5. State Management

| Query | Khoá cache | Coi là mới trong | Ghi chú |
|---|---|---|---|
| Hộp thư chủ xe | `notifications` (`NOTIFICATION_FEED_KEY`) | 60 s | Trang demo email gọi `invalidateQuery(NOTIFICATION_FEED_KEY)` sau khi chạy nhắc |
| Hộp thư chủ xưởng | `notifications:portal` | 60 s | `Promise.all` 2 API |
| Chi tiết lời nhắc | `reminder:{reminderId}` | 0 (luôn tải lại khi mở) | Tình trạng hiện tại phải mới |

`unreadCount` trên phụ đề tính lại phía client từ các thẻ đã dựng (`entries.filter(e => e.unread)`), nên mục bị bỏ qua theo BR-1711 không bị đếm.

---

# 6. API Integration

| Action | API | Client |
|---|---|---|
| Hộp thư chủ xe | `GET /notifications` (`API-NOTI-003`) | `listNotifications` (`api.ts`), timeout 10 s |
| Chi tiết lời nhắc | `GET /notifications/reminders/{id}` (`API-NOTI-004`) | `getReminderContext`, timeout 10 s |
| Hộp thư chủ xưởng | `GET /workshop-owner/quotes?status=PENDING_APPROVAL` (`API-QT-11`) + `GET /workshop-owner/bookings` (`API-WB-01`, `from = todayVn()`, `to = +6 ngày`, `statuses = ['PENDING']`) | `listWorkshopQuotes`, `getBoard` |

---

# 7. Loading / Empty / Error States

| State | SCR-1701 | SCR-1702 | SCR-1703 |
|---|---|---|---|
| Loading | 2 `SkeletonCard` | `SkeletonCard` 5 dòng | 2 `SkeletonCard` |
| Empty | "Chưa có thông báo" — "Nhắc bảo dưỡng, kết quả báo giá, cập nhật lịch hẹn và khảo sát sau dịch vụ sẽ hiện ở đây." | — | "Không có việc chờ xử lý" — "Báo giá mới và lịch hẹn cần xác nhận sẽ hiện ở đây." |
| Error (chưa có dữ liệu) | "Chưa tải được thông báo." + Thử lại + `traceId` | "Không tải được lời nhắc." + Thử lại + `traceId` | Như SCR-1701; **một** trong 2 API lỗi ⇒ cả màn lỗi (FF EF-1703, Q-1705) |
| Error khi làm mới | Giữ danh sách cũ | — | Giữ danh sách cũ |
| Phụ đề | `unread > 0` ⇒ "{n} việc cần bạn xem"; ngược lại "Hoạt động 90 ngày gần nhất" | — | "Báo giá chờ duyệt và lịch hẹn 7 ngày tới đang chờ xưởng xác nhận" |

## 7.1 Error Mapping

| API | Lỗi | FE |
|---|---|---|
| `API-NOTI-004` | `404 REMINDER_NOT_FOUND`, `404 VEHICLE_NOT_FOUND`, `409 VEHICLE_NOT_ACTIVE` | `ErrorState` SCR-1702 (FF EF-1702, EDGE-1708) |
| Mọi API | `403 ONBOARDING_REQUIRED` | Guard của layout chuyển về onboarding |
| Mọi API | Mạng / `5xx` / timeout | `ErrorState` kèm `traceId` |

---

# 8. Navigation

| Từ | Tới | Ghi chú |
|---|---|---|
| Chuông (`AppLayout`) | `notificationsPath` (`/notifications` hoặc `/technician/notifications`) | Chuông chưa có số đếm (FF Q-1703) |
| SCR-1702 "← Thông báo" | `/notifications` | — |
| Link email | `/notifications/reminders/{id}?action=…` | §4.7; chưa đăng nhập ⇒ guard đưa về đăng nhập rồi quay lại |

---

# 9. Responsive & Accessibility

- Cột đơn, `max-w-3xl`; thẻ co giãn theo chiều ngang, không cuộn ngang.
- Chấm "mới" có `aria-label="Mới"`; nút chuông `aria-label="Thông báo"`.
- `[Đề xuất]` tiêu đề thẻ dùng `h2` thay `h3` để không nhảy cấp từ `h1` (FINDING-019 trong `TODOS.md`).

---

# 10. Acceptance Criteria (FE)

- **AC-FE-1701** — Thứ tự thẻ trùng thứ tự API trả.
- **AC-FE-1702** — Mục `QUOTE_RESULT` `REJECTED` hiện sắc thái lỗi và nút "Xem báo giá" tới `/quotes/{id}` (test `feed.test.ts`).
- **AC-FE-1703** — `kind` không biết hoặc thiếu khối ⇒ thẻ không hiện, các thẻ khác vẫn hiện (test `feed.test.ts`).
- **AC-FE-1704** — Phụ đề đếm đúng số thẻ `unread`.
- **AC-FE-1705** — SCR-1702 với `snapshotAvailable = false` không hiện lý do nhắc, hạn và ODO lúc nhắc.
- **AC-FE-1706** — `hasCurrentBooking = true` ⇒ không có nút đặt lịch, có "Xem lịch hẹn".
- **AC-FE-1707** — `?action=booking` khi mốc đã có lịch ⇒ ở lại SCR-1702.
- **AC-FE-1708** — SCR-1703 đặt báo giá trước lịch hẹn (test `feed.test.ts`).
- **AC-FE-1709** — Mục `BOOKING_REMINDER` mở `/bookings/{id}?src=REMINDER_24H`; chỉ khi `unread` mới có sắc thái cảnh báo và câu nhắc hành động (test `feed.test.ts`).

---

# 11. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-1701, BR-1701, AC-1701 | §4.1, §4.2, AC-FE-1701 |
| BR-1702, AC-1702, AC-1703 | §4.1 (chấm mới), §5 (đếm), §7 (phụ đề) |
| BR-1703, AC-1704 | Backend; FE không lọc thêm |
| BR-1704 | §5 (cache 60 s ⇒ hết "mới" ở lần tải lại) |
| UC-1702, BR-1705, AC-1705, AC-1706 | §4.4, §4.6 |
| BR-1706, AF-1704 | §4.4, AC-FE-1705 |
| BR-1707, AC-1709 | §4.2 dòng `BOOKING_REMINDER`, AC-FE-1709 |
| BR-1708, EF-1702, AC-1707 | §7.1 |
| BR-1710, UC-1703, AC-1708 | §4.3 |
| BR-1711 | §4.2, AC-FE-1703 |
| AF-1703 | §4.7 |
| EF-1701, EF-1703 | §7 |

---

# 12. Analytics

`[Đề xuất]` — chưa có sự kiện nào.

| Event | Properties |
|---|---|
| `notification_opened` | `kind`, `unread` |
| `reminder_action_clicked` | `action` (`booking` / `chat` / `bookings`), `source` (`inbox` / `email`) |

---

# 13. Technical Notes

| Mục | Vị trí |
|---|---|
| Trang hộp thư | `frontend/src/features/notifications/pages/Notifications.tsx` |
| Chi tiết lời nhắc | `frontend/src/features/notifications/pages/ReminderDetail.tsx` |
| Ánh xạ thẻ (có test) | `frontend/src/features/notifications/feed.ts` · `feed.test.ts` |
| Hành động lời nhắc | `frontend/src/features/notifications/reminderActions.ts` |
| Type | `frontend/src/features/notifications/types.ts` (`NotificationItem`, `ReminderContext`) |
| Mock demo | `frontend/src/mocks/server/notifications.ts` — suy ra `BOOKING_REMINDER` từ lịch hẹn của chủ xe đã qua mốc 24h trước giờ hẹn |

---

# 14. Open Questions

| ID | Question | Status |
|---|---|---|
| `Q-1703` | Số đếm trên chuông (dùng `unreadCount`) | Open — `[Đề xuất]` có |
| `Q-1705` | SCR-1703: một nguồn lỗi thì vẫn hiện nguồn kia kèm cảnh báo | Open — `[Đề xuất]` có |
| `Q-FE-1701` | Lấy `unreadCount` từ API thay vì đếm phía client khi có `BOOKING_REMINDER` | Open |

---

# 15. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-10-07` | Team 4 Người | Bản đầu, theo các màn đã triển khai |
| `v1.1` | `2026-10-07` | Team 4 Người | Thẻ `BOOKING_REMINDER` (FF BR-1707), AC-FE-1709 |
