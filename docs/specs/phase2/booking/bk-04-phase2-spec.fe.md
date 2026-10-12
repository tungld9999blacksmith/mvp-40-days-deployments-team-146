# Frontend Technical Specification — Widget lịch

> Frontend cho Feature `FEAT-P2-BK04` (SCR-BK04-01..03) và trang kết nối lịch.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-04-phase2-spec.ff.md). **API:** [API Spec](bk-04-phase2-spec.api.md) (`API-BK04-01..10`).
>
> **Nguyên tắc:** widget không tự tính cửa sổ đến hạn hay số chỗ; lớp bận/rảnh tải nền và lỗi của nó không bao giờ chặn phần còn lại (AC-BK04-04).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-BK04` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-BK04-01 (component), SCR-BK04-02 (sheet), SCR-BK04-03 (trang xưởng), trang Kết nối lịch |
| Routes | `/settings/calendar` (mới), `/technician/calendar` (mới) |
| Feature folder | `frontend/src/features/calendar/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `CalendarWidget` (SCR-BK04-01)

File `features/calendar/components/CalendarWidget.tsx`. Đặt ở: Trang chủ (`features/dashboard`, dưới banner, cạnh highlight lịch hẹn sắp tới — không đổi layout grid, chiếm một thẻ trong cột chính) và đầu trang `/booking/options` (BK-01). Mặc định tháng (Q-BK04-02), nút chuyển "Tháng / Tuần", nút "Hôm nay", mũi tên tháng trước / sau.

| Trạng thái ô ngày | Hiển thị (không chỉ dựa vào màu) |
|---|---|
| Hôm nay | Viền đậm `border-foreground` |
| Trong cửa sổ đến hạn | Nền `bg-emerald-dim`; `OVERDUE` nền cảnh báo nhạt |
| Có lịch hẹn | Ô đặc `bg-brand text-on-brand` + chấm; giữ chủ động ⇒ viền nét đứt |
| Ngày bận | Sọc chéo (CSS `repeating-linear-gradient` dùng token `--color-border`, không gradient màu) + `aria-label` "bận" |
| Quá khứ | `opacity-50`, `aria-disabled`, không chạm |

- Chú giải bốn lớp dưới lưới.
- `dueWindow = null` ⇒ dòng "Chưa xác định được hạn bảo dưỡng: {lý do}" (EDGE-BK04-04).
- Cửa sổ trải hai tháng tô liền mạch khi chuyển tháng (dữ liệu tải `from–to` rộng hơn tháng hiển thị).
- Chưa kết nối lịch ⇒ dòng mời "Hiện ngày bạn bận? Kết nối Google Calendar" + "Để sau" (ẩn 30 ngày, lưu `localStorage` có try/catch).
- `busy.status = ERROR` ⇒ dòng nhỏ "Không tải được lịch của bạn · Kết nối lại" (EF-BK04-01).

**Bàn phím (NFR-11):** lưới là `role="grid"`; mũi tên di chuyển ngày, `Enter` mở ngày, `PageUp/PageDown` đổi tháng, `Home` về hôm nay.

## 2.2 `DaySlotsSheet` (SCR-BK04-02)

Chạm ngày ⇒ bottom sheet (dialog bên phải ở `xl`): tiêu đề "Thứ Sáu, 24/10"; gọi `API-BK04-03`; render `ScheduleOptionsList` (BK-01) với `run` trả về. `busyWarning` ⇒ khối cảnh báo "Lịch của bạn có sự kiện ngày này" nhưng vẫn cho chọn (AF-BK04-01). Chọn ⇒ luồng BK-01 → vé.

## 2.3 "Thêm vào lịch" trên vé

`features/bookings/pages/BookingTicket.tsx` thêm nút secondary "Thêm vào lịch" (icon `CalendarPlus`):
- Kết nối có quyền ghi ⇒ `API-BK04-08 { target: 'AUTO' }` ⇒ toast "Đã thêm vào Google Calendar"; đã có ⇒ nhãn nút "Đã thêm vào lịch".
- Không ⇒ menu hai lựa chọn: "Tải tệp .ics" (`API-BK04-08 ICS` rồi tải `API-BK04-09` bằng blob) và "Kết nối Google Calendar" (→ `/settings/calendar`).
- Thông báo "Lịch hẹn đã đổi, cập nhật lịch của bạn" (loại `CALENDAR_ICS_UPDATED`) có nút "Tải tệp mới".

## 2.4 `CalendarSettingsPage` (route `/settings/calendar`)

Vào từ hàng "Kết nối lịch" ở `/notifications/settings`, link "Xem dữ liệu" của PL-01, lời mời trên widget.

| Trạng thái | UI |
|---|---|
| Chưa kết nối | Giải thích: "EV Care chỉ đọc giờ bận/rảnh, không đọc tên hay nội dung sự kiện." Checkbox "Cho phép thêm lịch hẹn vào lịch của tôi" (quyền ghi, mặc định bỏ chọn). Nút "Kết nối Google Calendar" ⇒ `useConsentGate('CONSENT_CALENDAR_SYNC','BK-04')` ⇒ `API-BK04-04` ⇒ `window.location.assign(authUrl)` |
| Quay về `?connected=1` | Toast "Đã kết nối" |
| Quay về `?error=` | Thông báo lỗi + "Thử lại" |
| Đã kết nối | Danh sách lịch (checkbox, `API-BK04-06`), công tắc quyền ghi (bật cần cấp quyền thêm ⇒ chuyển `reauthUrl`), "Lần đồng bộ: {lastSyncedAt}", nút "Ngắt kết nối" (danger, xác nhận) |
| `revoked` / `error` | Banner + "Kết nối lại" |

## 2.5 `WorkshopWeekPage` (SCR-BK04-03)

Route `/technician/calendar`; link từ `TechnicianDashboard` và tab trên `Capacity`. Không thêm mục sidebar.
- Lưới hàng = khung giờ, cột = 7 ngày; ô `remaining` `font-mono`; `full` ⇒ "Hết chỗ" (quy ước Board, DESIGN.md).
- Điều hướng tuần trước / sau / "Tuần này". Chạm ô ⇒ mở `/technician/capacity?date=` ở ngày đó.
- Dùng chung hàm dựng ô với `capacityGrid.ts` (WS-02) để nhất quán với Board (BR-BK04-05).

---

# 3. API Integration & Errors

`features/calendar/api.ts`: `getOverview`, `getBusy`, `getDaySlots`, `connectGoogle`, `updateConnection`, `disconnect`, `addToCalendar`, `downloadIcs`; `features/workshop-board/api.ts` `getWeek`.

| API | Lỗi | Xử lý |
|---|---|---|
| BK04-01 | Mạng / 5xx | Thẻ widget lỗi + "Thử lại"; không ảnh hưởng phần khác của Trang chủ |
| BK04-02 | `ERROR` / `NOT_CONNECTED` | §2.1 (không phải lỗi màn) |
| BK04-02/04 | `CONSENT_REQUIRED` | Mở hộp đồng ý PL-01 |
| BK04-03 | `DATE_IN_PAST` | Đóng sheet |
| BK04-08 | `CALENDAR_PROVIDER_ERROR` | Toast + đề xuất tải `.ics` |

---

# 4. States

| State | UI |
|---|---|
| Đang tải overview | Skeleton lưới 6 × 7 |
| Busy đang tải | Lưới hiện đủ, sọc chéo xuất hiện khi xong (không nhảy layout) |
| 390 px | Tháng: ô vuông nhỏ, chỉ chấm chỉ báo, chú giải gập; Tuần: danh sách 7 ngày dọc |

---

# 5. Acceptance Criteria (FE)

1. Busy lỗi ⇒ widget vẫn hiện cửa sổ đến hạn, lịch hẹn và mở được sheet ngày (AC-BK04-04).
2. Ngày quá khứ không mở sheet bằng chuột hay bàn phím.
3. Điều hướng lưới hoàn toàn bằng bàn phím (NFR-11).
4. Chưa đồng ý PL-01 thì không bao giờ gọi `API-BK04-02/04`.
5. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `calendar/monthGrid.test.ts` | `buildMonth(year, month, overview, busy, today)` → 42 ô, cờ lớp đúng, cửa sổ trải tháng | +5 |
| `calendar/gridKeyboard.test.ts` | `nextFocus(date, key)` cho mũi tên / PageUp / Home | +4 |
| `calendar/addToCalendar.test.ts` | `addToCalendarAction(connection, existing)` → `GOOGLE` / menu / đã thêm | +3 |
| `calendar/CalendarWidget.test.tsx` | `renderToStaticMarkup` với busy lỗi: vẫn có lưới + dòng "Không tải được" | +1 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-BK04-01, BR-BK04-01, EDGE-BK04-03/04 | §2.1 |
| UC-BK04-02, AF-BK04-01/03 | §2.2 |
| UC-BK04-04/05, AF-BK04-02 | §2.3 |
| UC-BK04-03, EF-BK04-01/02, EDGE-BK04-02 | §2.4 |
| UC-BK04-06, BR-BK04-05 | §2.5 |

---

# 8. Analytics

`calendar_widget_viewed` (`view`), `calendar_day_opened` (`inDueWindow`, `busy`), `calendar_connect_started` (`write`), `calendar_connected`, `calendar_add_event` (`kind`), `calendar_invite_dismissed`. Không gửi khoảng bận.

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
