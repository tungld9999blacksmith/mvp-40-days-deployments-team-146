# Frontend Technical Specification — Chat theo từng lịch hẹn giữa xưởng và chủ xe

> Frontend cho Feature `FEAT-P2-MC01` (SCR-MC01-01, SCR-MC01-02).
>
> **Nguồn nghiệp vụ:** [Functional Spec](mc-01-phase2-spec.ff.md). **API:** [API Spec](mc-01-phase2-spec.api.md) (`API-MC01-01..07`, `WS-MC01-01`).
>
> **Tái dùng:** `shared/chat` (tách ở TA-01: danh sách tin, composer, `CardShell`), parser WebSocket của chat MVP, `PhotoUploadTile`. Bong bóng theo DESIGN.md Chat (người gửi là mình: `bg-brand text-on-brand`; người khác: `bg-card elevation-sm`). Không dùng mascot trợ lý cho tin của người.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-MC01` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-MC01-01 (chủ xe), SCR-MC01-02 (Workshop Portal + app KTV) |
| Routes | `/bookings/:bookingId/messages` (chủ xe), `/technician/messages`, `/technician/messages/:threadId` (chủ xưởng), `/ktv/messages/:threadId` (KTV) |
| Feature folder | `frontend/src/features/booking-thread/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `BookingThreadView` (dùng chung)

| Vùng | Nội dung |
|---|---|
| Đầu | Chủ xe: "{Tên xưởng} · KTV {tên}" + mã lịch, ngày giờ; xưởng / KTV: "Khách {tên} · {biển số}" + mã lịch |
| Danh sách tin | Bong bóng có tên người gửi (trừ của mình), giờ; tin hệ thống canh giữa chữ nhỏ muted; tin ảnh lưới thumbnail (chạm mở lớn); tin thẻ render qua `CARD_RENDERERS` (CH-02: `EXTRA_QUOTE`, `PROGRESS_UPDATE`, `BOOKING_TICKET`) |
| Tin bị che | Dòng nhỏ dưới bong bóng "Đã ẩn số điện thoại / email" |
| Composer | Ô chữ (≤ 2.000 ký tự), nút ảnh (`PhotoAddTile`, camera trên điện thoại, ≤ 5 ảnh, ảnh đang tải có vòng tiến độ), nút gửi |
| Luồng đóng | Composer thay bằng "Cuộc trò chuyện đã đóng" (AC-MC01-02) |
| `CANNOT_SEND` | Composer khoá: "Bạn không còn được giao lịch này" |
| Menu tin | "Báo cáo" (tin của người khác) ⇒ sheet lý do |

**Gửi:** hiện ngay bong bóng chờ (`clientMessageId`), thay bằng tin từ server; `notice = CONTACT_REDACTED` ⇒ toast "Để an toàn, hãy trao đổi số điện thoại / email trong app không cần thiết — xưởng liên hệ bạn qua đây".
**Realtime:** mở WS khi màn hiện; mất kết nối ⇒ thử lại có backoff và gọi `messages?after=lastSeq` để bù; đánh dấu đã đọc (`API-MC01-06`) khi tin cuối vào viewport.

## 2.2 Chủ xe (SCR-MC01-01)

Vé lịch `/bookings/:bookingId` thêm nút "Nhắn xưởng" (badge số chưa đọc) khi có luồng; mở `/bookings/:bookingId/messages`. Thông báo tin mới loại `THREAD_MESSAGE` mở thẳng luồng.

## 2.3 Workshop Portal / KTV (SCR-MC01-02)

`/technician/messages`: danh sách luồng (mới nhất trước) với tên khách, biển số, tin cuối, badge chưa đọc, nhãn "Quá hạn phản hồi" (`overdue`), lọc "Chưa trả lời". `xl`: danh sách 1/3 + luồng 2/3; nhỏ hơn: hai màn. Badge tổng chưa đọc trên mục "Tin nhắn khách" (thêm mục điều hướng Workshop Portal — thay đổi điều hướng cần duyệt theo DESIGN.md; trước đó vào từ `TechnicianDashboard` và `BoardBookingDetail` nút "Nhắn khách"). App KTV: `/ktv/messages/:threadId` mở từ chi tiết việc (WS-03).

---

# 3. API Integration & Errors

`features/booking-thread/api.ts` + `ws.ts`: `listThreads`, `getThreadByBooking`, `listMessages`, `sendMessage`, `uploadAttachment`, `markRead`, `reportMessage`, `connectThread(threadId)`.

| Lỗi | Xử lý |
|---|---|
| `THREAD_CLOSED` | Chuyển sang trạng thái đóng |
| `CANNOT_SEND` | Khoá composer |
| `FILE_TOO_LARGE` / `INVALID_REQUEST` | Lỗi dưới ô / ảnh ("Tải lại") |
| `RATE_LIMITED` | Đếm ngược ngắn |

---

# 4. Acceptance Criteria (FE)

1. UI không hiển thị trường liên hệ nào của bên kia.
2. Luồng đóng không có composer.
3. Tin mới hiện ≤ 2 s khi cả hai đang mở (dựa trên WS; test thủ công + test `ws.ts` với socket giả).
4. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `booking-thread/threadReducer.test.ts` | Gửi chờ → xác nhận; trùng `clientMessageId`; bù sau mất kết nối theo `seq` | +4 |
| `booking-thread/headerView.test.ts` | Tiêu đề theo vai trò người xem | +3 |
| `booking-thread/ws.test.ts` | Gửi khung `auth` đầu tiên; backoff | +2 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-MC01-01, UC-MC01-02, BR-MC01-02/03/07, EF-MC01-01/02 | §2.1, §2.2 |
| SCR-MC01-02, UC-MC01-03 | §2.3 |
| UC-MC01-04, AC-MC01-02, EDGE-MC01-01 | §2.1 |

---

# 7. Analytics

`thread_opened` (`role`), `thread_message_sent` (`kind`, `redacted`), `thread_report_sent`, `ws_overdue_thread_opened`.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
