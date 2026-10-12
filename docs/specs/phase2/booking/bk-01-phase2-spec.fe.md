# Frontend Technical Specification — Tự động lập lịch theo ràng buộc của chủ xe

> Frontend cho Feature `FEAT-P2-BK01` (SCR-BK01-01..04) và nút "Không phục vụ được" ở Workshop Portal.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-01-phase2-spec.ff.md). **API:** [API Spec](bk-01-phase2-spec.api.md) (`API-BK01-01..09`, thẻ `SCHEDULE_OPTIONS`).
>
> **Nguyên tắc (BR-BK01-15):** frontend không lọc, không chấm điểm, không sắp xếp lại phương án; hiển thị đúng thứ tự `rank` và lý do backend trả. Frontend không tự nới ràng buộc; chỉ gửi mã nới chủ xe bấm.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-BK01` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-BK01-01 (trang mới), SCR-BK01-02 (component dùng chung), SCR-BK01-03 (trong SCR-BK01-02), SCR-BK01-04 (trang mới) |
| Routes | `/settings/scheduling` (mới), `/booking/options` (bước mới của wizard), `/bookings/:bookingId/proactive` (mới) |
| Feature folder | `frontend/src/features/scheduler/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `SchedulingProfilePage` (SCR-BK01-01)

Route `/settings/scheduling`; vào từ hàng "Thói quen đặt lịch" ở `/notifications/settings` (cạnh "Quyền riêng tư", PL-01) và link "Sửa thói quen" trong SCR-BK01-02. Không thêm mục sidebar.

| Khối | Component | Hành vi |
|---|---|---|
| Khung giờ rảnh | `AvailabilityGrid` | Lưới 7 ngày × 3 buổi (sáng / chiều / tối theo `dayParts` của `API-BK01-04`); chạm ô bật/tắt. Link "Nhập giờ cụ thể" mở dòng `TimeRangeInput` cho một ngày. Không ô nào ⇒ dòng cảnh báo "Chưa chọn giờ rảnh: hệ thống sẽ tìm trong mọi giờ xưởng mở" |
| Địa điểm | `AnchorPicker` (tái dùng `features/bookings/components/LocationAnchorPicker.tsx`) | Nhà / Chỗ làm (địa chỉ đã lưu) / Vị trí hiện tại / Khu vực. Chọn "Vị trí hiện tại" gọi `useConsentGate('CONSENT_LOCATION','BK-01')` (PL-01); từ chối ⇒ quay về Khu vực |
| Bán kính | `Slider` 1–30 km, bước 1, `font-mono` | |
| Xưởng yêu thích | `WorkshopSelect` (tìm theo tên, dữ liệu `GET /workshops/nearby`) + link "Chọn trên bản đồ" (BK-05) | `inactive` ⇒ badge cảnh báo "Xưởng đã ngừng nhận lịch, chọn xưởng khác" (EDGE-BK01-02) |
| Giờ hay chọn, đánh giá tối thiểu | `TimeRangeInput`, `RatingSelect` (tuỳ chọn, gập trong "Tuỳ chọn thêm") | |
| Mức tự động hoá | `AutomationLevelRadio` | 3 lựa chọn, mỗi lựa chọn một câu: Gợi ý — "Chỉ gợi ý, bạn tự chọn"; Giữ chỗ sẵn — "Giữ sẵn chỗ tốt nhất {proactiveHoldHours} giờ, bạn bấm xác nhận"; Tự đặt — "Tự đặt lịch, huỷ miễn phí trong {autoBookFreeCancelHours} giờ". Chọn Tự đặt khi `autoBookAllowed = false` ⇒ mở `ConsentPromptDialog` của `CONSENT_AUTO_BOOKING` (PL-01); từ chối ⇒ giữ mức cũ |
| Mục "Hệ thống suy ra" | `InferredConstraintRow` | Badge "Hệ thống suy ra" + nút "Xác nhận" / "Xoá" (`API-BK01-03`). Chỉ hiện khi backend trả |
| Xưởng đã loại | `ExcludedWorkshopRow` | Tên + lý do + nút "Cho phép lại" (xoá dòng loại trừ qua PS-03 API) |

**Lưu:** nút "Lưu" (primary) dính đáy trên mobile; gửi `PUT /scheduling/profile` với `expectedVersion`. `PROFILE_VERSION_CONFLICT` ⇒ tải lại, toast "Thói quen vừa được cập nhật ở nơi khác". Rời trang khi có thay đổi chưa lưu ⇒ hỏi xác nhận.

## 2.2 `ScheduleOptionsList` (SCR-BK01-02, dùng chung)

File `features/scheduler/components/ScheduleOptionsList.tsx`. Props: `run: RunDto`, `onSelected(result)`, `variant: 'page' | 'chat'`.

| Vùng | Nội dung |
|---|---|
| Câu dẫn | `run.headline` khi có |
| Chế độ đổi lịch | `mode = RESCHEDULE` ⇒ dòng "Xe đang có lịch {giờ} tại {xưởng}. Chọn phương án để đổi." và nhãn nút "Đổi sang" thay "Chọn" |
| Thẻ phương án (≤ 3) | Tên xưởng (+ "Xưởng yêu thích" khi `isPreferred`), ngày giờ `Thứ Bảy, 10/10 · 08:00`, `distanceKm` + `travelMinutes` khi có (`font-mono`), "Còn {remainingCapacity} chỗ", tối đa 3 lý do dạng pill, nhãn "Đã giữ chỗ đến HH:mm" khi `held`. Nút "Chọn" / "Đổi sang" |
| Chân | Link "Sửa thói quen đặt lịch" → `/settings/scheduling`; link "Tự chọn xưởng và giờ" → wizard MVP `/booking/workshops` |
| Cảnh báo | `warnings` ⇒ dòng phụ; `automationDowngrade = RELIABILITY_TIER` ⇒ "Lần này mình chỉ giữ chỗ, chưa tự đặt, vì có lịch bị lỡ gần đây" |

**Chọn:** gọi `API-BK01-06`; nút loading, các nút khác disabled; cờ in-flight theo `optionId` (chống bấm hai lần, EDGE-BK01-06).
- `200` ⇒ `NEW` (mức Gợi ý) đi tiếp màn tóm tắt MVP `/booking/confirm` với booking giữ ngắn; `SWITCH_HOLD` ⇒ cập nhật nhãn giữ; `RESCHEDULE_*` ⇒ toast "Đã đổi lịch" + điều hướng vé `/bookings/{id}`.
- `OPTION_SLOT_FULL` ⇒ thay danh sách bằng `details.run`, toast "Khung này vừa hết, đây là phương án khác" (EF-BK01-01). Lịch cũ không đổi.
- `OPTION_INACTIVE` ⇒ gọi lại `API-BK01-05` cùng tham số.

**Trạng thái kết quả khác:**

| `outcome` | UI |
|---|---|
| `NO_OPTION` | `RelaxationPanel` (§2.3) |
| `CONFLICT` | Câu hỏi "Xưởng {tên} không mở vào giờ bạn rảnh. Bạn muốn giữ xưởng hay giữ giờ?" + 2 nút ⇒ chạy lại với `conflictPreference` |
| `NEED_LOCATION` | Tái dùng `RegionPickerCard` (us-061) ⇒ chạy lại với khu vực |
| `NO_OPTION` + `reason = DUE_UNKNOWN` | Mở chọn hạng mục MVP (`/booking/proposal`) |
| `TIMEOUT_PARTIAL` | Như `OPTIONS` + dòng phụ "Kết quả rút gọn, bấm Tìm lại để xem đầy đủ" |

## 2.3 `RelaxationPanel` (SCR-BK01-03)

Câu giải thích (`run.headline` hoặc `reason`). Tối đa 3 nút từ `relaxationOffers`: `{label} · {optionCount} phương án`. Bấm ⇒ `API-BK01-05` với `relaxations = [...relaxations trước, code]`. Nút "Vào danh sách chờ" chỉ khi `waitlistAvailable` (BK-07). Nút "Để sau" đóng panel. **Không** tự gửi nới khi mở panel (AC-BK01-04).

## 2.4 Điểm vào bộ lập lịch

| Nơi | Cách gọi | Ghi chú |
|---|---|---|
| Wizard Đặt lịch | Route mới `/booking/options` là bước đầu của `BookingLayout` khi `features.scheduler` bật; `BookingStart` điều hướng tới đây thay cho `/booking/proposal`. Gọi `API-BK01-05` `{ trigger: 'OWNER_REQUEST', applyAutomation: true }` khi vào trang | Link "Tự chọn" vẫn mở luồng MVP |
| Chat | Thẻ `SCHEDULE_OPTIONS` trong `MessageCard.tsx` → `<ScheduleOptionsCard runId>` render `ScheduleOptionsList variant="chat"`; dữ liệu đọc từ `card` đã làm giàu | Không gửi câu chat khi bấm chọn |
| Chip (CH-01), widget (BK-04), bản đồ (BK-05) | Gọi `runScheduler({ trigger, overrides })` của `features/scheduler/api.ts` | Mỗi spec quy định `overrides` riêng |
| Đổi lịch | `/bookings/:bookingId/reschedule` thêm tab "Gợi ý phương án" gọi `trigger: 'RESCHEDULE'` | Tab "Chọn giờ" MVP giữ nguyên |

Trạng thái đang chạy: "Đang tìm lịch phù hợp với bạn…" + skeleton 3 thẻ; nút huỷ không cần (≤ 2 s).

## 2.5 `ProactiveHoldPage` (SCR-BK01-04)

Route `/bookings/:bookingId/proactive`; vào từ thông báo "Lịch giữ sẵn" và từ banner Trang chủ.

| Vùng | Nội dung |
|---|---|
| Thẻ lịch | Xưởng, ngày giờ, mốc, lý do (lấy từ `scheduling_option` qua `GET /bookings/{id}` — trường `schedulingOption` mới) |
| Đếm ngược | `useCountdown(holdExpiresAt)`; < 2 giờ ⇒ màu cảnh báo; = 0 ⇒ chuyển trạng thái hết hạn |
| Nút | "Xác nhận" (primary, `API-BK01-07`), "Xem phương án khác" (gọi `API-BK01-05` `trigger: 'RESCHEDULE'`, hiện `ScheduleOptionsList`), "Bỏ qua lần này" (secondary, `API-BK01-08`, không hộp xác nhận) |
| Hết hạn | "Lịch giữ sẵn đã hết hạn" + "Tìm lại" (`API-BK01-05`) |
| Đã xác nhận | Điều hướng vé `/bookings/{id}` |

Banner Trang chủ (`features/dashboard`): khi có booking `proactive` đang giữ, slide "Lịch giữ sẵn chờ bạn xác nhận" trong `HomeCarousel` (dữ liệu thật, có hành động — DESIGN.md).

## 2.6 Lịch tự đặt (mức 3)

Vé `/bookings/:bookingId` khi `autoBooked = true` và `now < freeCancelUntil`: `BookingStatusBanner` thêm dòng "EV Care đã tự đặt lịch này. Huỷ miễn phí đến HH:mm" + nút "Huỷ" (luồng huỷ MVP) và "Đổi giờ".

## 2.7 Workshop Portal — "Không phục vụ được"

`features/workshop-board/components/BoardBookingDetail.tsx`: lịch `pending` / `confirmed` thêm nút secondary "Không phục vụ được". Mở `UnableToServeDialog` (trong `BoardDialogs.tsx`): radio lý do (Thiếu KTV / Thiếu phụ tùng / Sự cố / Nghỉ đột xuất), ô ghi chú (bắt buộc khi Sự cố, ≤ 300 ký tự), câu "Hệ thống sẽ tự tìm và giữ lịch khác cho khách". Xác nhận (danger) ⇒ `API-BK01-09` ⇒ toast "Đã báo khách" ⇒ lịch biến khỏi cột đang chờ.

Lịch `proactive` trên bảng: badge "Hệ thống đang giữ cho khách", ẩn nút "Duyệt" / "Từ chối" (API §6.3).

---

# 3. API Integration & Errors

`features/scheduler/api.ts`: `getProfile`, `saveProfile`, `reviewConstraint`, `getConfig`, `runScheduler`, `selectOption`, `confirmProactive`, `dismissProactive`; `features/workshop-board/api.ts` thêm `reportUnableToServe`. Kiểu ở `features/scheduler/types.ts` theo API §3–7.

| API | Lỗi | Xử lý |
|---|---|---|
| BK01-05 | `SCHEDULER_BUSY` | Chờ 1 s, gọi lại một lần; vẫn bận ⇒ toast "Đang tìm, vui lòng đợi" |
| BK01-05 | `SCHEDULER_TIMEOUT` / `503` | Lỗi trong khối + "Thử lại" |
| BK01-06 | `OPTION_SLOT_FULL` | §2.2 |
| BK01-06 | `OPTION_IN_PROGRESS` | Giữ loading, gọi lại sau 1,5 s (tối đa 3 lần) |
| BK01-06 | `VEHICLE_NOT_ACTIVE` | Như các màn đặt lịch MVP |
| BK01-07 | `PROACTIVE_HOLD_EXPIRED` | Trạng thái hết hạn §2.5 |
| BK01-07/08 | `NOT_PROACTIVE_HOLD` | Điều hướng vé |
| BK01-02 | `AUTO_BOOK_CONSENT_REQUIRED` | Mở hộp đồng ý PL-01 |
| BK01-09 | `INVALID_BOOKING_STATE` | Toast + tải lại bảng |

---

# 4. States

| State | UI |
|---|---|
| Đang chạy bộ lập lịch | Skeleton 3 thẻ + câu "Đang tìm lịch phù hợp với bạn…" |
| Đang chọn | Nút của thẻ loading, thẻ khác disabled |
| Mobile 390 px | Thẻ phương án full width, lý do xuống dòng, nút dưới cùng thẻ; `AvailabilityGrid` cuộn ngang trong khung, không cuộn trang |
| Desktop xl | Wizard: `BookingSummaryRail` bên phải giữ như MVP |

---

# 5. Acceptance Criteria (FE)

1. `ScheduleOptionsList` render đúng thứ tự `rank`, không sắp lại (test so sánh thứ tự).
2. Mở `RelaxationPanel` không gửi request nới; chỉ bấm nút mới gửi đúng một `code`.
3. Bấm "Chọn" hai lần nhanh chỉ gửi một `selectOption`.
4. `OPTION_SLOT_FULL` thay danh sách bằng `details.run` và không điều hướng.
5. Chọn "Tự đặt" khi chưa đồng ý mở hộp PL-01; từ chối giữ mức cũ.
6. Lịch giữ sẵn hiện đếm ngược đúng tới `holdExpiresAt` theo giờ Asia/Ho_Chi_Minh.
7. Workshop Portal không hiện nút Duyệt với lịch `proactive`.
8. Kiểm tra hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `scheduler/runView.test.ts` | `runView(run)` → khối hiển thị cho 5 `outcome`; nhãn "Đổi sang" khi `RESCHEDULE` | +6 |
| `scheduler/optionCard.test.ts` | `optionCardView(option)` → khoảng cách chỉ khi có, nhãn giữ chỗ, tối đa 3 lý do | +3 |
| `scheduler/availabilityGrid.test.ts` | `toggleCell`, `gridToConstraints` / `constraintsToGrid` khứ hồi; phát hiện chồng lấn | +4 |
| `scheduler/selectOption.test.ts` | `handleSelectResult(result)` → hành động điều hướng theo `mode` / lỗi | +4 |
| `scheduler/ScheduleOptionsList.test.tsx` | `renderToStaticMarkup`: thứ tự thẻ = `rank`; không có nút khi `outcome = CONFLICT` | +2 |
| `workshop-board/unableToServe.test.ts` | Ghi chú bắt buộc khi `INCIDENT` | +1 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-BK01-01, BR-BK01-10 | §2.1 |
| UC-BK01-02, BR-BK01-03 | §2.2, §2.4 |
| AF-BK01-04, AC-BK01-04 | §2.3 |
| UC-BK01-03, BR-BK01-06, EF-BK01-02 | §2.5 |
| UC-BK01-04, AC-BK01-05 | §2.2 (đổi sang) |
| UC-BK01-05 | §2.7 |
| AF-BK01-07 | §2.6 |
| EF-BK01-03 / 04 | §2.2 bảng outcome |

---

# 8. Analytics

`scheduler_run_started` (`trigger`), `scheduler_run_result` (`outcome`, `optionCount`, `durationMs`), `scheduler_option_selected` (`rank`, `mode`), `scheduler_relaxation_clicked` (`code`), `proactive_hold_viewed`, `proactive_hold_confirmed` (`secondsLeft`), `proactive_hold_dismissed`, `scheduling_profile_saved` (`automationLevel`, `windowCount`). Không gửi toạ độ, địa chỉ. M-01 đo phía backend (PL-03); frontend chỉ gửi `scheduler_run_started` để có mốc bắt đầu ý định.

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
