# Frontend Technical Specification — Danh sách chờ

> Frontend cho Feature `FEAT-P2-BK07` (SCR-BK07-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-07-phase2-spec.ff.md). **API:** [API Spec](bk-07-phase2-spec.api.md) (`API-BK07-01..06`).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-BK07` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-BK07-01 (sheet đăng ký), SCR-BK07-02 (trang), SCR-BK07-03 (trang lời mời) |
| Routes | `/bookings/waitlist` (mới), `/bookings/waitlist/offers/:offerId` (mới) |
| Feature folder | `frontend/src/features/scheduler/waitlist/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Đăng ký chờ (SCR-BK07-01)

Điểm vào: nút "Vào danh sách chờ" của `RelaxationPanel` (BK-01, khi `waitlistAvailable`), ô khung "Hết chỗ" trong `SlotGrid` (nhấn giữ / nút phụ "Chờ khung này"), và `DaySlotsSheet` (BK-04).

`WaitlistSheet`: xưởng (cố định theo ngữ cảnh), ngày, lựa chọn "Đúng khung {HH:mm}" hoặc "Bất kỳ khung {buổi}" (khoảng theo `dayParts`), câu "Khi có chỗ, mình giữ cho bạn {WAITLIST_OFFER_MIN} phút để xác nhận. Không gửi lời mời từ 22:00 đến 07:00." Nút "Vào danh sách chờ".
- `SLOT_AVAILABLE` ⇒ đóng sheet, hiện `ScheduleOptionsList` từ `details.run` + toast "Khung này vừa có chỗ".
- `WAITLIST_LIMIT` ⇒ "Bạn đang chờ {WAITLIST_MAX} khung. Rời bớt để thêm." + link trang danh sách.

## 2.2 Danh sách chờ của tôi (SCR-BK07-02)

Route `/bookings/waitlist`; link từ `MyBookings` (khi có mục). Mỗi mục: xưởng, ngày, khung / khoảng, trạng thái ("Đang chờ · bạn đứng thứ {position}", "Đang được mời" → nút mở lời mời, "Đã từ chối, vẫn chờ lần khác"), nút "Rời danh sách".

## 2.3 Lời mời (SCR-BK07-03)

Route `/bookings/waitlist/offers/:offerId` (mở từ thông báo):
- Thẻ khung trống: xưởng, ngày giờ (`font-mono`), đếm ngược `useCountdown(expiresAt)` cỡ lớn (cảnh báo khi < 3 phút).
- "Nhận" (primary) ⇒ `API-BK07-04` ⇒ vé `/bookings/{id}`.
- "Từ chối" ⇒ hộp nhỏ: checkbox "Vẫn chờ lần khác" (mặc định chọn) ⇒ `API-BK07-05`.
- Hết giờ / `OFFER_EXPIRED` ⇒ "Lời mời đã hết hạn" + "Xem danh sách chờ".

Workshop Portal: ô sức chứa (`Capacity`) và lịch tuần (BK-04) hiện "· {n} chờ" khi `waitingCount > 0` (`API-BK07-06`).

---

# 3. API Integration & Errors

`features/scheduler/waitlist/api.ts`: `joinWaitlist`, `listWaitlist`, `leaveWaitlist`, `acceptOffer`, `declineOffer`; `features/workshop-board/api.ts` `getWaitlistCounts`.

| Lỗi | Xử lý |
|---|---|
| `OFFER_EXPIRED` / `OFFER_INACTIVE` | Trạng thái hết hạn §2.3 |
| `OPEN_BOOKING_EXISTS` | "Xe đã có lịch hẹn" + link vé |

---

# 4. Acceptance Criteria (FE)

1. Đếm ngược khớp `expiresAt` của server (không tự cộng thời gian).
2. Từ chối mặc định giữ chỗ trong danh sách.
3. Chủ xưởng không thấy danh tính người chờ.
4. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `waitlist/entryView.test.ts` | Nhãn trạng thái + vị trí | +4 |
| `waitlist/offerView.test.ts` | Hết hạn theo `now`; cảnh báo < 3 phút | +2 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-BK07-01, UC-BK07-01, BR-BK07-01, EDGE-BK07-01 | §2.1 |
| SCR-BK07-02, Q-BK07-01 | §2.2 |
| SCR-BK07-03, UC-BK07-03, 04 | §2.3 |
| FF §16 | §2.3 (Workshop Portal) |

---

# 7. Analytics

`waitlist_joined` (`kind`: `SLOT` / `RANGE`), `waitlist_left`, `waitlist_offer_opened` (`secondsLeft`), `waitlist_offer_accepted`, `waitlist_offer_declined` (`keepWaiting`).

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
