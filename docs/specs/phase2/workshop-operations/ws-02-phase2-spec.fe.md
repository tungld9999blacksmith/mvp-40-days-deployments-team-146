# Frontend Technical Specification — Sức chứa theo thời lượng và hạn phản hồi

> Frontend cho Feature `FEAT-P2-WS02` (SCR-WS02-01..04).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ws-02-phase2-spec.ff.md). **API:** [API Spec](ws-02-phase2-spec.api.md) (`API-WS02-01..07`).
>
> **Nguyên tắc:** frontend không tính sức chứa; mọi con số "còn bao nhiêu chỗ" và khung nào chọn được đều lấy từ API. Xưởng chưa bật mô hình thời lượng thấy màn Sức chứa như MVP.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-WS02` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-WS02-01 (trang mới), SCR-WS02-02 (sửa `/technician/capacity`), SCR-WS02-03 (khối trong `/technician/settings/booking`), SCR-WS02-04 (thông báo chủ xe) |
| Routes | `/technician/settings/durations` (mới) |
| Feature folder | `frontend/src/features/workshop-board/` (bổ sung), `frontend/src/features/notifications/` (loại thông báo mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `ServiceDurationsPage` (SCR-WS02-01)

Route `/technician/settings/durations`; vào từ `BookingSettingsPage` (link "Thời lượng hạng mục") và từ thông báo đề xuất tuần. Không thêm mục sidebar.

| Cột (bảng; dưới `md` thành danh sách thẻ) | Nguồn |
|---|---|
| Hạng mục | `itemName` |
| Mặc định | `defaultMin` (`font-mono`) |
| Của xưởng | Ô số `workshopMin` (bước 5, 5–600), trống = theo mặc định; lưu khi blur bằng `PUT` |
| Thực tế (trung vị 30 ngày) | `actualMedianMin` + "{sampleCount} lần"; `null` ⇒ "Chưa đủ dữ liệu" |
| Đề xuất | Khi có `suggestion`: badge "Nên đổi thành {suggestedMin} phút" + nút "Dùng số thực tế" (`API-WS02-03`) |

- Đầu trang: "Thời lượng dùng để tính sức chứa. Thay đổi chỉ áp dụng cho lịch mới."
- Xưởng chưa bật mô hình (`durationModelEnabled = false`): banner "Xưởng đang tính sức chứa theo khung {slot} phút như cũ. Bật ở Cài đặt đặt lịch." — bảng vẫn chỉnh được để chuẩn bị.
- Lọc: ô tìm theo tên hạng mục; nút "Chỉ hiện đề xuất".

## 2.2 Màn Sức chứa (SCR-WS02-02, sửa `features/workshop-board/pages/Capacity.tsx`)

Chỉ khi response có `units` (xưởng đã bật):

| Phần | Hành vi |
|---|---|
| Lưới | Cột = ngày, hàng = đơn vị `unitMin` (30 phút). Ô hiển thị `remaining / total−reserved` (`font-mono`); `remaining = 0` ⇒ nền cảnh báo nhạt + chữ "Kín" (không dùng màu đơn thuần) |
| Lịch dài | Khối `bookings` vẽ chồng theo cột ngày, cao bằng số đơn vị (`durationMin / unitMin`), nhãn mã + giờ bắt đầu–kết thúc; `proactive` ⇒ viền nét đứt + "Hệ thống đang giữ" |
| Khoá chỗ | Hộp khoá MVP thêm "Đến" (`endTime`, chọn theo đơn vị). Lưu ⇒ `PUT slot-blocks` |
| Cảnh báo quá tải | Response có `warnings.OVERBOOKED_UNITS` ⇒ hộp cảnh báo liệt kê lịch bị ảnh hưởng + nút "Báo không phục vụ được" mở `UnableToServeDialog` (BK-01 FE §2.7) cho từng lịch (EF-WS02-03) |

Xưởng chưa bật: giữ nguyên UI MVP (AC-WS02-04). Logic dựng lưới tách ra `capacityGrid.ts` (hàm thuần), cạnh `capacitySlotState.ts` có sẵn.

## 2.3 Cài đặt đặt lịch (SCR-WS02-03, sửa `BookingSettingsPage.tsx`)

| Khối | Hành vi |
|---|---|
| "Tính sức chứa theo thời lượng" | `Switch` + một câu "Bảo dưỡng lớn chiếm nhiều thời gian hơn kiểm tra nhanh". Bật ⇒ `DecisionSheet` "Lịch mới sẽ chiếm thời gian theo hạng mục. Lịch đã có giữ nguyên." ⇒ `PUT` |
| "Chỗ dự phòng cho khách vãng lai" | Ô số `emergencySlotsReserved` (0 … `totalTechnicians − 1`). Khi có `reserveSuggestion`: "Đề xuất {suggested} chỗ (khách vãng lai chiếm {walkInRatePct}% trong {basisDays} ngày)" + nút "Dùng đề xuất" (điền ô, chưa lưu). Chủ xưởng bấm "Lưu" mới ghi (BR-WS02-05) |
| Link | "Thời lượng hạng mục" → `/technician/settings/durations` |

## 2.4 Nhắc duyệt (Workshop Portal)

Thông báo loại `WS_CONFIRM_REMIND` trong `/technician/notifications` và badge ở `TechnicianDashboard`: "Lịch {mã} còn {phút} phút để duyệt" + nút "Mở lịch" → `/technician/board/{bookingId}`. Trong `BoardBookingDetail`, lịch `pending` hiện đếm ngược tới hạn chót (`confirmDeadlineAt` — trường mới trả từ `GET /workshop-owner/bookings/{id}`).

## 2.5 Thông báo hết hạn cho chủ xe (SCR-WS02-04)

`features/notifications`: loại mới `BOOKING_WS_TIMEOUT_REPLACED` và `BOOKING_WS_TIMEOUT_NO_OPTION`.

| Loại | Nội dung | Hành động |
|---|---|---|
| `…_REPLACED` | "Xưởng {tên} chưa kịp xác nhận lịch {giờ}. Mình đã giữ sẵn: {xưởng mới} · {giờ mới}, đến {hạn}." | "Xem và xác nhận" → `/bookings/{newBookingId}/proactive` (BK-01 SCR-BK01-04) |
| `…_NO_OPTION` | "Xưởng {tên} chưa kịp xác nhận lịch {giờ} nên lịch đã huỷ. Chưa có lịch khác phù hợp." | "Xem gợi ý" → `/booking/options` với `relaxations` gợi ý (BK-01 SCR-BK01-03) |

Vé lịch cũ (`/bookings/{oldId}`) `cancelled` với lý do `WS_CONFIRM_TIMEOUT` hiện link "Lịch thay thế" khi có `replacedBy`.

## 2.6 Chủ xe chọn khung

`features/bookings/pages/BookingSlots.tsx` gọi availability kèm `userVehicleId` + `odoMilestone` (hoặc `itemCodes` của gói đã chọn). Khung `available = false` với `reason = INSUFFICIENT_DURATION` hiện disabled kèm tooltip "Không đủ thời gian cho các hạng mục". Thẻ tóm tắt hiện "Dự kiến {durationMin} phút" khi `durationMin` có.

---

# 3. API Integration & Errors

`features/workshop-board/api.ts` thêm `getServiceDurations`, `setServiceDuration`, `applyDurationSuggestion`; `getCapacity`, `putSlotBlocks`, `getBookingSettings`, `putBookingSettings` mở rộng kiểu. `features/bookings/api.ts` `getAvailability` thêm tham số.

| API | Lỗi | Xử lý |
|---|---|---|
| WS02-02 | `INVALID_REQUEST` | Lỗi dưới ô: "Thời lượng 5–600 phút, bước 5" |
| WS02-03 | `SUGGESTION_NOT_FOUND` | Tải lại bảng |
| WS02-05 | `200` + `warnings` | §2.2 cảnh báo quá tải |
| WS02-06 | `INVALID_REQUEST` | "Chỗ dự phòng phải nhỏ hơn số thợ" |
| Mọi API | `403` | Như Workshop Portal hiện có |

---

# 4. States

| State | UI |
|---|---|
| Đang tải bảng thời lượng | Skeleton 8 hàng |
| Đang lưu một ô | Spinner trong ô; lỗi ⇒ trả giá trị cũ |
| Lưới sức chứa 390 px | Một ngày mỗi màn, vuốt / nút ngày trước–sau; khối lịch dài vẫn theo đơn vị |

---

# 5. Acceptance Criteria (FE)

1. Xưởng chưa bật: `Capacity` render giống MVP (snapshot `renderToStaticMarkup` với dữ liệu MVP không đổi).
2. Lịch 150 phút vẽ cao đúng 5 đơn vị 30 phút.
3. "Dùng đề xuất" chỉ điền ô, không gọi API cho tới khi bấm "Lưu".
4. Thông báo `…_REPLACED` mở đúng trang lịch giữ sẵn của lịch mới.
5. Khung không đủ thời lượng bị disabled ở bước chọn giờ của chủ xe.
6. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `workshop-board/capacityGrid.test.ts` | `buildGrid(units, bookings)` → hàng/cột, khối lịch dài trải đúng số ô; ô `remaining = 0` có nhãn "Kín" | +4 |
| `workshop-board/durations.test.ts` | `durationRowView(item)`; kiểm tra bước 5 / khoảng 5–600 | +3 |
| `workshop-board/reserveSuggestion.test.ts` | Hiển thị đề xuất / ẩn khi `null`; kẹp giá trị | +2 |
| `notifications/feed.test.ts` (mở rộng) | Hai loại thông báo mới → tiêu đề, CTA, route | +2 |
| `workshop-board/Capacity.test.tsx` | Snapshot xưởng chưa bật không đổi | +1 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-WS02-01, UC-WS02-05 | §2.1 |
| SCR-WS02-02, BR-WS02-07, EF-WS02-03 | §2.2 |
| BR-WS02-05, BR-WS02-08 | §2.3 |
| UC-WS02-03 | §2.4 |
| UC-WS02-04, AC-WS02-03 | §2.5 |
| UC-WS02-02 | §2.6 |

---

# 8. Analytics

`ws_duration_edited` (`itemCode`, `from`, `to`), `ws_duration_suggestion_applied`, `ws_duration_model_toggled` (`enabled`), `ws_reserve_suggestion_used`, `ws_confirm_remind_opened`, `owner_ws_timeout_notice_opened` (`replaced`).

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
