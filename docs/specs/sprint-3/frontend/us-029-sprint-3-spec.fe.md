# Frontend Technical Specification — Đặt lịch bảo dưỡng theo sức chứa & vị trí

> **Cập nhật phạm vi (02/10/2026):** các phần dưới đây trong tài liệu này không còn áp dụng.
>
> - Báo giá / duyệt báo giá (`quote`, `quote_item`, us-049): **đã bỏ**. Đặt lịch không gắn báo giá; mọi con số chi phí là ước tính (F5), chi phí cuối cùng do xưởng xác nhận khi kiểm tra xe.

> Đặc tả frontend cho Feature `FEAT-BOOK-001` (PRD F6, US-029 → US-032).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-029-sprint-3-spec.ff.md) · **API:** [API Spec](../api/us-029-sprint-3-spec.api.md) (`API-BK-01 → 04`) · **Entity:** [Entity Spec](../entity/us-029-sprint-3-spec.entity.md)
>
> **Phạm vi FE:** App chủ xe (mobile-first) — luồng đặt lịch trên UI (SCR-401 → SCR-404), thay dữ liệu mock của trang `/booking` (`features/bookings/pages/Booking.tsx`). Ticket sau khi đặt (SCR-405) dùng chung màn Booking Ticket của [us-053 FE](us-053-sprint-3-spec.fe.md). Luồng đặt lịch qua chat do [AI-004](../../ai-agent/ai-004-sprint-3-spec.agent.md) + thẻ trong chat đảm nhận; thẻ tóm tắt trong chat dùng chung component `BookingSummaryCard` ở §4.4.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-BOOK-001` — Đặt lịch theo sức chứa & vị trí |
| Screen | `SCR-401` Bắt đầu · `SCR-402` Gợi ý xưởng gần · `SCR-403` Chọn ngày + khung · `SCR-404` Thẻ tóm tắt · `SCR-405` → us-053 SCR-1201 |
| Route | `/booking` (query tuỳ chọn: `workshopId`, `odoMilestone`, `quoteId`, `date`) · `/booking/workshops` · `/booking/slots` · `/booking/confirm` |
| Version | `v1.1` |
| Author | Team 4 Người |
| Status | `Draft` |
| Related PRD | [PRD §F6](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-029-sprint-3-spec.ff.md#8-screen--ui-flow) |
| Related API | [API-BK-01 → 04](../api/us-029-sprint-3-spec.api.md) |
| Last Updated | `2026-09-30` |

---

# 2. Screen Overview

## 2.1 Purpose

Chủ xe tự đặt lịch trên UI: chọn xưởng (gợi ý theo vị trí), chọn khung còn chỗ, xem thẻ tóm tắt và **bấm Xác nhận** để giữ chỗ — không bao giờ tạo booking khi chưa bấm Xác nhận (FF BR-009, AC-005).

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Home — thẻ trạng thái (F3) "Đặt lịch" | `DUE_SOON` / `OVERDUE` | `/booking?odoMilestone={next}` |
| SCR-1001 Dự toán — "Đặt lịch" | | `/booking?workshopId&odoMilestone` |
| SCR-1102 Báo giá đã duyệt — "Đặt lịch với báo giá này" | `canAttachToBooking` | `/booking?workshopId&odoMilestone&quoteId` |
| Menu "Đặt lịch" | | `/booking` |

## 2.3 Exit Points

| Condition | Destination |
|---|---|
| Giữ chỗ thành công (`PENDING` hoặc `CONFIRMED`) | `/bookings/:bookingId` (us-053 SCR-1201; thay `/booking-success`) |
| `409 OPEN_BOOKING_EXISTS` | Hộp thoại "Bạn đang có lịch hẹn …" → `/bookings/:id` hoặc luồng đổi lịch (us-053) |
| Chọn "Đặt qua chat" ở SCR-401 | `/ai` với ý định đặt lịch |

## 2.4 Preconditions

- Chủ xe đăng nhập, onboarding xong, có xe `verified` + `active`.

---

# 3. UI Structure

## 3.1 Stepper

```text
[1 Xưởng] ──> [2 Ngày & giờ] ──> [3 Xác nhận]
```

- Có `workshopId` trong query ⇒ bỏ bước 1 (FF AF-003).
- Header luôn hiển thị xe (model + biển số che) và mốc (nếu có).

## 3.2 SCR-401 Bắt đầu

- Hai lựa chọn: **"Đặt qua trò chuyện"** (→ `/ai`) và **"Tự chọn xưởng & giờ"** (→ SCR-402 hoặc SCR-403).
- Bỏ qua SCR-401 khi vào từ Dự toán/Báo giá (đã có xưởng).

## 3.3 SCR-402 Gợi ý xưởng gần

```text
┌──────────────────────────────────────┐
│ Gần: [Nhà — Cầu Giấy, Hà Nội ▾] [📍]  │
│ Ngày muốn đến: [Thứ 7 04/10 ▾] Giờ: [09:00 ▾] (tuỳ chọn) │
├──────────────────────────────────────┤
│ ★ VinFast Smart City · 3,4 km         │
│   Đại lộ Thăng Long… · Còn 5 chỗ 09:00│
│ VinFast Mỹ Đình · 5,1 km · Hết chỗ    │
│ (Sắp xếp theo khu vực) khi rankedBy=REGION │
└──────────────────────────────────────┘
```

## 3.4 SCR-403 Chọn ngày + khung

- Dải 7 ngày (`BOOKING_SEARCH_HORIZON_DAYS`); ngày xưởng nghỉ ⇒ disabled + "Nghỉ".
- Lưới khung giờ trong giờ hoạt động: khung còn chỗ (hiện `remaining` khi ≤ 3: "Còn 2 chỗ"), khung hết chỗ (disabled).
- Chọn khung ⇒ gọi `API-BK-02` có `timeSlot` để lấy `confirmationToken` ⇒ SCR-404.

## 3.5 SCR-404 Thẻ tóm tắt

- Xưởng + địa chỉ; thời gian (thứ, dd/MM/yyyy, HH:mm); xe (biển số che một phần); hạng mục của mốc; báo giá (mã báo giá hoặc "Không"); chi phí:
  - có `quoteId` hợp lệ ⇒ "Theo báo giá đã duyệt: …"
  - không ⇒ "Chi phí ước tính: …" (từ `API-EST-02` của us-045 với cùng xưởng + mốc) hoặc "Chưa có ước tính".
- Ô ghi chú (≤ 500).
- Đồng hồ hiệu lực của thẻ (TTL token); hết hạn ⇒ disable "Xác nhận", nút "Kiểm tra lại" (FF EF-001).
- Nút **Xác nhận** · **Sửa** (về SCR-403) · **Huỷ** (về trang trước, không gọi API).

---

# 4. Component Specification

## 4.1 LocationAnchorPicker

| Item | Spec |
|---|---|
| Mặc định | Không truyền `anchor` ⇒ backend chọn theo BR-002; hiển thị `data.anchor` trả về ("Gần địa chỉ hồ sơ" / "Gần xưởng ưa thích") |
| Đổi vị trí | (a) nhập text ⇒ `query`; (b) "Dùng vị trí hiện tại" ⇒ `navigator.geolocation` ⇒ `lat/lng` (`anchor=SPECIFIED`); (c) chọn tỉnh ⇒ `province` |
| Quyền vị trí bị từ chối | Toast "Không lấy được vị trí, bạn nhập địa điểm nhé", giữ mốc cũ |

## 4.2 WorkshopCard

- Tên, địa chỉ, `distanceKm` (1 chữ số thập phân) hoặc nhãn "Cùng khu vực" khi `null`, ★ khi `isPreferred`, giờ hoạt động hôm nay.
- `availability` (khi đã chọn ngày/giờ): "Còn {remaining} chỗ" / "Hết chỗ khung này".

## 4.3 SlotGrid

- Nguồn: `API-BK-02` không `timeSlot` ⇒ `slots[]`.
- Khung quá khứ trong hôm nay ⇒ không hiển thị (backend đã lọc; FE lọc thêm theo giờ VN).

## 4.4 BookingSummaryCard (dùng chung chat + UI)

- Props: `workshop`, `date`, `timeSlot`, `vehicle`, `items`, `cost`, `quote`, `tokenExpiresAt`, `onConfirm`, `onEdit`, `onCancel`.
- Trong chat: `onConfirm` gửi sự kiện xác nhận kèm `confirmation_token` cho AI-004 (không gọi `POST /bookings` trực tiếp từ thẻ) — một đường tạo booking duy nhất ở backend (FF BR-011).

## 4.5 AlternativesSheet

- Hiện khi `requested.available = false` hoặc `409 SLOT_FULL`: tối đa 3 phương án từ `alternatives[]` (FF BR-008) — mỗi dòng: xưởng, ngày, giờ, còn chỗ; chọn ⇒ gọi lại `API-BK-02` cho phương án đó.

## 4.6 HoldResult (sau khi Xác nhận)

| `status` trả về | UI |
|---|---|
| `CONFIRMED` (xưởng `auto`) | Điều hướng ticket (us-053) — có mã + QR |
| `PENDING` (xưởng `manual`) | Ticket ở trạng thái "Đã giữ chỗ — chờ xưởng xác nhận"; đồng hồ đếm ngược tới `ownerCancelableUntil` + nút "Huỷ giữ chỗ" (`API-BK-04`). Hết 10' ⇒ ẩn nút, chỉ còn "Đang chờ xưởng xác nhận" (FF BR-010) |
| `CANCELLED` sau khi chờ xưởng (xưởng từ chối, hoặc quá hạn chót xác nhận — FF BR-015, EF-006) | Ticket "Lịch hẹn đã bị huỷ" kèm lý do do backend trả (nếu có) + nút **"Đặt lịch lại"** ⇒ `/booking?workshopId&odoMilestone` (giữ xưởng, mốc). Không hiện QR. Màn đọc trạng thái này thuộc us-053 SCR-1201; thông báo tới chủ xe do backend gửi |

---

# 5. User Interaction

| # | Action | FE Behavior | API |
|---|---|---|---|
| 1 | Mở `/booking` | Nếu có `workshopId` ⇒ SCR-403; ngược lại SCR-401/402 | — |
| 2 | Mở SCR-402 | `GET /workshops/nearby` (+ `date`/`timeSlot` nếu chủ xe chọn) | BK-01 |
| 3 | Chọn xưởng | SCR-403; `GET /workshops/{id}/availability?date` | BK-02 |
| 4 | Chọn khung | `GET …/availability?date&timeSlot` ⇒ lấy token ⇒ SCR-404 | BK-02 |
| 5 | Bấm Xác nhận | `POST /bookings` với `confirmationToken`, `userVehicleId`, `quoteId?`, `milestoneRef?`, `note?`; header `Idempotency-Key` | BK-03 |
| 6 | Huỷ giữ chỗ (≤ 10') | Hộp xác nhận ⇒ `DELETE /bookings/{id}/hold` | BK-04 |

---

# 6. State Management

```ts
interface BookingWizardState {
  userVehicleId: string;
  odoMilestone: number | null;
  quoteId: string | null;
  anchor: { source: 'SPECIFIED' | 'PROFILE' | 'PREFERRED'; query?: string; lat?: number; lng?: number; province?: string } | null;
  workshopId: string | null;
  date: string | null;          // YYYY-MM-DD (Asia/Ho_Chi_Minh)
  timeSlot: string | null;      // HH:mm
  confirmationToken: string | null;
  tokenExpiresAt: string | null;
  note: string;
  submitting: boolean;
}
```

- Nguồn sự thật cho `workshopId`, `date`, `timeSlot`, `odoMilestone`, `quoteId` là query string (back/forward giữ bước).
- `quoteId` chỉ hợp lệ với `workshopId` của báo giá: khi chủ xe "Đổi xưởng" (về SCR-402 chọn xưởng khác) FE bỏ `quoteId` khỏi query, thẻ tóm tắt dùng chi phí ước tính của xưởng mới (us-049 FF BR-1108, AF-1105).
- `confirmationToken` chỉ giữ trong bộ nhớ (không lưu localStorage).
- Sinh `Idempotency-Key` một lần cho mỗi token; retry dùng lại key.

---

# 7. API Integration — Error Mapping

| Code | Màn | FE |
|---|---|---|
| `LOCATION_ANCHOR_REQUIRED` | SCR-402 | Mở LocationAnchorPicker, "Cho mình biết bạn muốn đặt gần đâu" (FF EF-004) |
| `NO_WORKSHOP_AVAILABLE` / `WORKSHOP_NOT_FOUND` (404 — backend hiện trả mã này khi không có xưởng `active`) / danh sách rỗng | SCR-402 | "Chưa có xưởng khả dụng gần vị trí này" + đổi vị trí (FF EF-004) |
| `WORKSHOP_NOT_FOUND` ở SCR-403/404 | SCR-403, SCR-404 | Xưởng vừa ngừng hoạt động: toast "Xưởng không còn nhận đặt lịch" + về SCR-402 |
| `SLOT_OUT_OF_HOURS` | SCR-403 | Hiện giờ hoạt động, chọn lại (FF EF-003) |
| `SLOT_FULL` | SCR-404 | AlternativesSheet (FF EF-002, AC-003) |
| `HOLD_EXPIRED` / `INVALID_CONFIRMATION_TOKEN` | SCR-404 | "Thẻ đặt lịch đã hết hiệu lực, mình kiểm tra lại giúp bạn" ⇒ gọi lại `API-BK-02` (FF EF-001) |
| `QUOTE_EXPIRED` | SCR-404 | "Báo giá đã hết hiệu lực" + lựa chọn "Đặt không kèm báo giá" (bỏ `quoteId`) |
| `OPEN_BOOKING_EXISTS` | SCR-404 | Hộp thoại dẫn tới lịch đang mở / đổi lịch (FF BR-013) |
| `HOLD_WINDOW_CLOSED` | Ticket | Ẩn nút huỷ giữ chỗ, hiển thị "Đang chờ xưởng xác nhận" |
| `FORBIDDEN` / `VEHICLE_NOT_FOUND` / `VEHICLE_NOT_ACTIVE` | mọi màn | Về `/dashboard`; không tiết lộ xe có tồn tại hay không (FF BR-012, AC-009) |
| `ONBOARDING_REQUIRED` | mọi màn | Về `/onboarding` |
| `SERVICE_UNAVAILABLE` | SCR-404 | "Tạm thời chưa đặt được, bạn thử lại giúp mình" + gợi ý kiểm tra "Lịch của tôi" (FF EF-005) |

---

# 8. Client-side Validation

| Field | Rule |
|---|---|
| Ngày | Trong `[hôm nay, hôm nay + 7]` theo giờ VN |
| Khung | Có trong `slots[]` và `available = true` |
| Ghi chú | ≤ 500 ký tự |
| Xác nhận | Disabled khi `submitting` hoặc token hết hạn |

---

# 9. Loading / Empty States

- SCR-402: skeleton 3 thẻ xưởng; SCR-403: skeleton lưới khung.
- Khi đang gửi Xác nhận: overlay "Đang giữ chỗ…" (không cho quay lại).
- Không có khung trống cả 7 ngày ⇒ "Xưởng đã kín lịch 7 ngày tới" + gợi ý xưởng khác (AlternativesSheet).

---

# 10. Navigation

| Route | Screen | Guard |
|---|---|---|
| `/booking` | SCR-401 | Chủ xe active |
| `/booking/workshops` | SCR-402 | Chủ xe active |
| `/booking/slots?workshopId&date` | SCR-403 | Có `workshopId` |
| `/booking/confirm` | SCR-404 | Có token trong state; mất state (reload) ⇒ về `/booking/slots` |
| `/booking-success` | Redirect | → `/bookings/:id` (us-053) |

---

# 11. Permission / Visibility

- Chỉ chủ xe; Workshop Portal không có luồng đặt hộ (FF §2.2 — khoá chỗ thay thế).

# 12. Responsive / Accessibility

- Mobile-first; lưới khung 3 cột trên mobile, 6 cột desktop.
- Khung hết chỗ có văn bản "Hết chỗ", không chỉ đổi màu.
- Đồng hồ TTL có `aria-live="polite"` khi còn ≤ 60 s.

# 13. Analytics

| Event | Properties |
|---|---|
| `booking_started` | `entry = HOME / ESTIMATE / QUOTE / MENU` |
| `booking_workshop_selected` | `rankedBy`, `isPreferred`, `rank` |
| `booking_slot_full_shown` | `alternativesCount` |
| `booking_confirmed` | `status = PENDING / CONFIRMED`, `hasQuote`, `secondsFromStart` (đo "thời gian từ ý định đến xác nhận" — PRD §10) |

---

# 14. Acceptance Criteria (FE)

## AC-FE-401 — Không tạo booking trước Xác nhận

**Given** chủ xe đang ở SCR-404 **When** bấm Sửa/Huỷ hoặc rời trang **Then** không có request `POST /bookings`.

## AC-FE-402 — Hết chỗ hiển thị phương án

**Given** `POST /bookings` trả `409 SLOT_FULL` **Then** AlternativesSheet hiện ≤ 3 phương án; chọn một ⇒ quay lại kiểm tra.

## AC-FE-403 — Hiển thị đúng theo chế độ xưởng

**Given** response `status = PENDING` **Then** ticket hiện "chờ xưởng xác nhận" + đếm ngược huỷ giữ chỗ; `status = CONFIRMED` ⇒ có mã + QR.

## AC-FE-404 — Token hết hạn

**Given** `tokenExpiresAt` đã qua **Then** nút Xác nhận disabled và có nút "Kiểm tra lại".

---

# 15. Technical Notes

- Vite + React 19 + React Router 7 + Tailwind 4.
- Tách `features/bookings/{api,hooks,components}`; `BookingSummaryCard` export cho `features/assistant` dùng trong chat.
- Thời gian gửi API: `date` + `timeSlot` theo giờ VN (đúng hợp đồng us-029); hiển thị từ `appointmentAt` UTC.
- `API-BK-02` không trả thời điểm hết hạn token: FE ước tính `tokenExpiresAt = lúc nhận response + BOOKING_CONFIRMATION_TOKEN_TTL_SECONDS` (mặc định 600 s). Backend tiêu token ngay khi nhận `POST /bookings`, nên sau **mọi** lỗi của BK-03 phải lấy token mới (gọi lại BK-02 cho cùng khung).
- `status` booking backend trả chữ thường (`pending`, `confirmed`, `cancelled`) — so sánh không phân biệt hoa thường.
- BK-02 chậm khi nhiều request song song (mỗi khung một truy vấn sức chứa): dải 7 ngày tải **lần lượt** (ngày đang chọn trước); lấy token gọi `withAlternatives=false`, chỉ gọi lại có `alternatives` khi khung đã hết chỗ.

# 16. Truy vết FF → FE

Mã trong [FF us-029](../feature-functional/us-029-sprint-3-spec.ff.md) và nơi FE xử lý. "Backend" = không có hành vi UI riêng; FE chỉ hiển thị kết quả API.

| FF | Nội dung | FE |
|---|---|---|
| UC-401, AC-001 | Gợi ý xưởng gần theo hồ sơ, ghim xưởng ưa thích | §3.3, §4.1, §4.2 (★) |
| AF-001, AC-002, EDGE-401 | Địa điểm chỉ định thay hồ sơ | §4.1 (nhập text / vị trí hiện tại) |
| AF-002, BR-003, BR-004, EDGE-402/412 | Xếp theo khoảng cách hoặc khu vực, không bịa khoảng cách | §3.3 nhãn "Sắp xếp theo khu vực", §4.2 "Cùng khu vực" |
| UC-402, BR-007, AC-005 | Thẻ tóm tắt chưa tạo booking; Xác nhận mới giữ chỗ | §3.5, §4.4, AC-FE-401 |
| AF-004, EDGE-409 | Đặt không kèm báo giá / báo giá hết hạn | §3.5 (báo giá "Không"), §6 (bỏ `quoteId` khi đổi xưởng), §7 `QUOTE_EXPIRED` |
| AF-005, AC-003, AC-004, BR-008, EDGE-404 | Hết chỗ ⇒ 2–3 phương án | §4.5, AC-FE-402 |
| BR-006, AC-007, EF-003, EDGE-407 | Chỉ khung trong giờ hoạt động | §3.4 (ngày nghỉ disabled), §4.3, §7 `SLOT_OUT_OF_HOURS` |
| BR-010, AC-006 | Huỷ giữ chỗ trong 10' | §4.6, §5 #6, §7 `HOLD_WINDOW_CLOSED` |
| BR-014, AC-010, EDGE-413 | Xác nhận tự động / thủ công | §4.6, AC-FE-403 |
| BR-015, EF-006, AC-011, EDGE-414 | Xưởng thủ công không xác nhận kịp ⇒ huỷ, mời đặt lại | §4.6 dòng `CANCELLED` |
| BR-012, AC-009, EDGE-410 | Chỉ đặt cho xe của mình | §7 `FORBIDDEN` / `VEHICLE_*` |
| BR-013, EDGE-411 | Đang có booking mở | §7 `OPEN_BOOKING_EXISTS` |
| EF-001, EDGE-406 | Token thẻ hết hạn | §3.5, AC-FE-404, §15 |
| EF-004, EDGE-403 | Không có xưởng / không có mốc vị trí | §7 `LOCATION_ANCHOR_REQUIRED`, `WORKSHOP_NOT_FOUND` |
| EF-005 | Service sức chứa lỗi | §7 `SERVICE_UNAVAILABLE` |
| BR-001, BR-005, AC-008, EF-002, EDGE-405/408 | Nguyên tử, công thức sức chứa, chung service Agent/UI | Backend — FE chỉ hiển thị `SLOT_FULL` (§4.5) |
| BR-011 | Một đường tạo booking duy nhất | §4.4 (thẻ trong chat không gọi BK-03) |

# 17. Open Questions

| ID | Question |
|---|---|
| `Q-FE-401` | SCR-401 có cần không, hay vào thẳng SCR-402? `[Đề xuất]` giữ để giới thiệu đặt qua chat |
| `Q-FE-402` | Có hiển thị bản đồ ở SCR-402? `[Đề xuất]` không trong MVP (Q-401 — chưa geocoding) |

# 18. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu — FF us-029 ghi "Related Frontend Spec [Chưa có]" |
| `v1.1` | `2026-10-01` | Team 4 Người | Đối chiếu FF: thêm trạng thái huỷ do xưởng không xác nhận kịp (BR-015, EF-006), dòng báo giá trên thẻ, mã lỗi backend thật (`WORKSHOP_NOT_FOUND`, `VEHICLE_*`, `ONBOARDING_REQUIRED`), ghi chú kỹ thuật token/hiệu năng, bảng truy vết FF → FE |
