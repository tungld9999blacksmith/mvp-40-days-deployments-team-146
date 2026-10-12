# Frontend Technical Specification — Chính sách huỷ lịch và lỡ hẹn

> Frontend cho Feature `FEAT-P2-BK02` (SCR-BK02-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-02-phase2-spec.ff.md). **API:** [API Spec](bk-02-phase2-spec.api.md) (`API-BK02-01..09`).
>
> **Nguyên tắc:** frontend không tự phân loại huỷ sớm / muộn (giờ thiết bị có thể lệch, EF-BK02-03); luôn hiện thông điệp của `cancel-preview`. Không có từ "phạt" trên giao diện (BR-BK02-08).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-BK02` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-BK02-01 (sửa `CancelBookingDialog`), SCR-BK02-02 (trang mới), SCR-BK02-03 (Workshop Board) |
| Routes | `/bookings/reliability` (mới) |
| Feature folder | `frontend/src/features/reliability/` (mới), sửa `features/bookings`, `features/workshop-board` |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `CancelBookingDialog` (SCR-BK02-01, sửa `features/bookings/components/CancelBookingDialog.tsx`)

1. Mở hộp ⇒ gọi `API-BK02-01`; trong lúc tải, nút "Huỷ lịch" disabled + skeleton một dòng.
2. Hiện `message`:
   - `counted = false`: dòng phụ màu muted, ví dụ "Huỷ trước 24 giờ không bị tính".
   - `counted = true`: khối cảnh báo (icon `AlertTriangle` + chữ, không chỉ màu) với `message`; nếu `tierAfter` khác bậc hiện tại thêm "Sau lần này bạn sẽ ở mức {tên bậc}".
3. `suggestReschedule` ⇒ nút secondary "Đổi giờ thay vì huỷ" → `/bookings/{id}/reschedule` (EDGE-BK02-02).
4. Huỷ muộn: checkbox "Tôi gặp sự cố bất khả kháng" mở ô ghi chú (10–500 ký tự) ⇒ gửi `forceMajeure.note`; câu "Xưởng sẽ xem xét để miễn tính".
5. Nút "Huỷ lịch" (danger) ⇒ `POST /cancel`. Hiển thị kết quả theo `cancellation` của response (có thể khác preview nếu vượt mốc khi hộp đang mở): toast "Đã huỷ lịch" hoặc "Đã huỷ lịch · tính 0,5 điểm" + link "Xem độ tin cậy".
6. Hộp mở > 60 s ⇒ gọi lại preview trước khi cho bấm huỷ.

Hộp này dùng ở vé, Lịch của tôi (`BookingPreview`), và thẻ chat có hành động huỷ.

## 2.2 `ReliabilityPage` (SCR-BK02-02)

Route `/bookings/reliability`; vào từ `MyBookings` (link "Độ tin cậy đặt lịch" ở đầu danh sách, có badge bậc khi ≠ `NORMAL`) và từ thông báo đổi bậc.

| Khối | Nội dung |
|---|---|
| Tóm tắt | Điểm (`font-mono`), tên bậc, một câu xử lý của bậc (bảng §2.4); "Điểm sớm nhất hết tính vào {nextExpiryAt}" |
| Thanh bậc | 4 đoạn: Bình thường, Nhắc nhẹ, Cần xác nhận, Giới hạn; đoạn hiện tại đậm + nhãn chữ (không chỉ màu); marker vị trí điểm |
| Chính sách | Gập/mở: định nghĩa huỷ sớm / huỷ muộn / lỡ hẹn bằng tham số thật (`lateCancelHours`…), danh sách trường hợp không tính (BR-BK02-04), "Không thu phí" |
| Sự kiện | Danh sách: ngày, loại ("Huỷ muộn", "Lỡ hẹn", "Miễn"), điểm (`+0,5` / `+1` / `−1`), lý do, mã lịch (link vé), trạng thái ("Đang tính", "Đang khiếu nại", "Đã miễn", "Hết tính"). Nút "Khiếu nại" khi `canAppeal` |
| Trống | "Bạn chưa có lần huỷ muộn hay lỡ hẹn nào." |

**Khiếu nại:** `AppealDialog` ô ghi chú (10–500 ký tự), câu "Xưởng phản hồi trong 72 giờ; không phản hồi thì khiếu nại được chấp nhận". Gửi `API-BK02-05`; thành công ⇒ trạng thái "Đang khiếu nại".

## 2.3 "Bạn có đang tới không?"

Thông báo loại `ARRIVAL_CHECK` (push + mục Thông báo + banner trên vé đang mở): hai nút "Đang tới" / "Không đến được". Gọi `API-BK02-03`. "Không đến được" mở `CancelBookingDialog` ở chế độ rút gọn (không cần preview vì đã muộn; vẫn hiện thông điệp từ response). `ARRIVAL_PROMPT_INACTIVE` ⇒ ẩn banner.

## 2.4 Áp bậc trên luồng đặt lịch

| Bậc | Nơi | UI |
|---|---|---|
| `SOFT_REMINDER` | `BookingConfirm`, thẻ chat xác nhận | Dòng nhắc "Huỷ trong 24 giờ trước giờ hẹn sẽ được tính. Xem chính sách" |
| `MUST_CONFIRM` | Vé lịch `confirmed` | `BookingStatusBanner` "Bạn cần bấm Xác nhận sẽ đến trước {giờ hẹn − 12 giờ}, nếu không lịch sẽ được trả" + nút us-033 |
| `RESTRICTED` | `ScheduleOptionsList` (BK-01) | Dòng giải thích khi `reason = RELIABILITY_RESTRICTED` hoặc khi danh sách chỉ có xưởng duyệt tay |

Bậc lấy từ `GET /reliability` (cache 5 phút trong `features/reliability/api.ts`).

## 2.5 Workshop Board (SCR-BK02-03)

`features/workshop-board`:

| Chỗ | Thay đổi |
|---|---|
| `BoardBookingDetail` | Badge bậc khách (`customerTier` ≠ `NORMAL`): "Khách cần xác nhận sẽ đến" / "Khách hay lỡ hẹn". Không hiển thị điểm |
| Lịch quá giờ chưa check-in | Nút "Khách không đến" hiện khi `now ≥ noShowAllowedAt` (trước đó disabled + tooltip "Chờ đến {giờ}"). Xác nhận bằng `alertdialog` ⇒ `API-BK02-06` |
| Lịch vừa đánh dấu lỡ hẹn | Trong 24 giờ: nút "Hoàn tác" (`UNDO`) và "Xe đã đến" (`VEHICLE_ARRIVED`, chỉ cùng ngày) ⇒ `API-BK02-07` |
| Khiếu nại | Trang `/technician/reliability-appeals` (mới; link từ `TechnicianDashboard` thẻ "Khiếu nại chờ xử lý" khi có): danh sách ghi chú khách, mã lịch, hạn quyết định (đếm ngược), nút "Chấp nhận" / "Từ chối" (bắt buộc lý do) |
| Thông báo xưởng | "Khách {mã} báo đang tới" (từ `ON_THE_WAY`) |

---

# 3. API Integration & Errors

`features/reliability/api.ts`: `getCancelPreview`, `getReliability`, `appeal`, `respondArrival`; `features/bookings/api.ts` `cancelBooking` thêm `forceMajeure` và kiểu `cancellation`; `features/workshop-board/api.ts`: `markNoShow`, `undoNoShow`, `listAppeals`, `decideAppeal`.

| API | Lỗi | Xử lý |
|---|---|---|
| BK02-01 | Mạng / 5xx | Vẫn cho huỷ, hiện dòng "Không tải được thông tin chính sách"; kết quả thực tế hiện sau khi huỷ |
| BK02-02 | `INVALID_BOOKING_STATE` | Đóng hộp, tải lại vé |
| BK02-05 | `APPEAL_NOT_ALLOWED` | Toast theo `details.reason` + tải lại |
| BK02-06 | `NO_SHOW_TOO_EARLY` | Toast "Chưa hết thời gian chờ, thử lại sau {allowedAt}" |
| BK02-07 | `UNDO_WINDOW_PASSED` / `SLOT_FULL` | Toast giải thích; ẩn nút |
| BK02-09 | `REJECT_NOTE_REQUIRED` / `APPEAL_ALREADY_DECIDED` | Lỗi dưới ô / tải lại danh sách |

---

# 4. States

| State | UI |
|---|---|
| Đang tải preview | Nút huỷ disabled |
| Trang độ tin cậy đang tải | Skeleton tóm tắt + 3 hàng |
| Mobile 390 px | Thanh bậc full width, nhãn dưới thanh; sự kiện dạng thẻ dọc |

---

# 5. Acceptance Criteria (FE)

1. Hộp huỷ luôn hiện câu từ `cancel-preview` trước khi nút "Huỷ lịch" bấm được (AC-BK02-05).
2. Toast sau huỷ dùng phân loại của response, không của preview.
3. Trang độ tin cậy hiện đủ loại, điểm, thời điểm, lịch, lý do mỗi sự kiện (AC-BK02-03).
4. Nút "Khiếu nại" chỉ khi `canAppeal`.
5. Workshop Board không render bất kỳ con số điểm nào của khách.
6. Không có chữ "phạt" trong copy của feature (test chuỗi).
7. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `reliability/cancelPreviewView.test.ts` | `cancelNotice(preview)` → kiểu khối, câu, nút đổi giờ, cảnh báo đổi bậc | +4 |
| `reliability/reliabilityView.test.ts` | `tierBar(score, tiers)`; nhãn sự kiện + dấu điểm; trạng thái | +5 |
| `reliability/copy.test.ts` | Không chứa "phạt" | +1 |
| `workshop-board/noShow.test.ts` | `noShowActions(booking, now)` → hiện / disabled / hoàn tác / xe đã đến | +4 |
| `bookings/CancelBookingDialog.test.tsx` | `renderToStaticMarkup` với preview huỷ muộn: có số điểm và nút đổi giờ | +1 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-BK02-01, BR-BK02-07, AC-BK02-05 | §2.1 |
| SCR-BK02-02, AC-BK02-03, UC-BK02-03 | §2.2 |
| AF-BK02-02 | §2.3 |
| BR-BK02-03 | §2.4 |
| SCR-BK02-03, UC-BK02-02, EDGE-BK02-06, EF-BK02-02 | §2.5 |

---

# 8. Analytics

`cancel_preview_shown` (`classification`, `counted`), `cancel_reschedule_suggested_clicked`, `booking_cancelled` (`classification`), `reliability_page_viewed` (`tier`), `reliability_appeal_submitted` (`kind`), `arrival_response` (`answer`), `ws_no_show_marked`, `ws_no_show_undone` (`mode`), `ws_appeal_decided` (`decision`).

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
