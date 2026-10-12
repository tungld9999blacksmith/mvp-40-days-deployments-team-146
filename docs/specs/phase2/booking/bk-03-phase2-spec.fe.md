# Frontend Technical Specification — Bảo dưỡng sớm hoặc trễ so với mốc

> Frontend cho Feature `FEAT-P2-BK03` (SCR-BK03-01, SCR-BK03-02).
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-03-phase2-spec.ff.md). **API:** [API Spec](bk-03-phase2-spec.api.md) (`API-BK03-01..03`, thẻ `EARLY_SERVICE`).
>
> **Nguyên tắc:** frontend không so sánh km / ngày với ngưỡng; chỉ hiện `classification`, `summary`, `warrantyNote` của backend. Không có câu nào về bảo hành ngoài `warrantyNote`.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-BK03` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-BK03-01 (thẻ trong chat + khối trong `/booking/options`), SCR-BK03-02 (nhãn trên Trang chủ / Xe của tôi) |
| Feature folder | `frontend/src/features/scheduler/early/` (mới), sửa `features/dashboard`, `features/vehicles` |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `EarlyServiceCard` (SCR-BK03-01)

File `features/scheduler/early/EarlyServiceCard.tsx`; dùng ở hai nơi: (1) `MessageCard` nhánh `EARLY_SERVICE` trong chat, (2) `/booking/options` khi `API-BK01-05` trả `outcome = EARLY_CONFIRMATION_REQUIRED`.

| Vùng | Nội dung |
|---|---|
| Tóm tắt | `summary` (ví dụ "Xe còn 4.200 km hoặc 4 tháng mới tới mốc 24.000 km.") |
| Ngưỡng | "Có thể làm sớm trong {earlyDays} ngày hoặc {earlyKm} km trước mốc." + pill nguồn khi `threshold.citation` (mở `CitationDrawer` có sẵn); `CONFIG` ⇒ không pill |
| Bảo hành | Chỉ khi `warrantyNote`: có nguồn ⇒ trích dẫn + pill nguồn; không nguồn ⇒ câu cố định của backend |
| Nút (`TOO_EARLY`) | "Kiểm tra nhanh" (primary, chỉ khi `quickCheckOffered`), "Vẫn bảo dưỡng đầy đủ" (secondary), "Thôi" (ghost) |
| `OVERDUE` | Không nút lựa chọn; một dòng "Mình sẽ ưu tiên khung sớm nhất" và danh sách phương án BK-01 ngay dưới |

**Hành vi nút:**
- "Kiểm tra nhanh" ⇒ `runScheduler({ trigger, serviceKind: 'QUICK_CHECK' })` (BK-01 FE §2.4) ⇒ `ScheduleOptionsList`.
- "Vẫn bảo dưỡng đầy đủ" ⇒ `DecisionSheet` xác nhận lần hai: "Bảo dưỡng mốc {label} ngay bây giờ? {nextMilestoneNote}" ⇒ đồng ý ⇒ `runScheduler({ serviceKind: 'MAINTENANCE', earlyAcknowledged: true })`.
- "Thôi" ⇒ đóng thẻ (chat: ghi lựa chọn vào trạng thái cục bộ của thẻ, không gửi API).

## 2.2 Luồng đặt lịch MVP

`BookingConfirm` nhận `409 EARLY_CONFIRMATION_REQUIRED` ⇒ mở `DecisionSheet` như §2.1 với `details.early`; đồng ý ⇒ gửi lại kèm `earlyAcknowledged: true` (token giữ nguyên).

## 2.3 Nhãn mốc kế tiếp (SCR-BK03-02)

`features/vehicles/components/VehicleHero.tsx` và thẻ bảo dưỡng ở Trang chủ (`features/dashboard`):

| Dữ liệu | Hiển thị |
|---|---|
| `basis.type = LAST_SERVICE` | Dòng phụ dưới mốc: "Tính từ lần bảo dưỡng ngày {serviceDate} ({serviceOdoKm} km)" (`font-mono` cho số) |
| `pendingOemSync` | Badge "Đang chờ hãng cập nhật lịch sử" + tooltip "Mốc sẽ cập nhật khi hãng gửi lịch sử lần bảo dưỡng {ngày}" (EF-BK03-02) |
| Lịch `QUICK_CHECK` đã xong | Không đổi mốc (BR-BK03-06) |

Trong `HomeCarousel` (banner ink) chỉ dùng nhãn mono uppercase theo DESIGN.md; ngoài banner dùng sentence case.

## 2.4 Vé / Lịch của tôi

Lịch `serviceKind = QUICK_CHECK`: tiêu đề "Kiểm tra nhanh" thay nhãn mốc; dòng phụ "Không thay thế bảo dưỡng định kỳ".

---

# 3. API Integration & Errors

`features/scheduler/api.ts` thêm `getEarlyServiceCheck(userVehicleId, workshopId?)`; `runScheduler` thêm `serviceKind`, `earlyAcknowledged`; `features/vehicles/types.ts` thêm `basis`, `pendingOemSync`.

| API | Lỗi | Xử lý |
|---|---|---|
| BK03-01 | Mạng / 5xx | Thẻ hiện lỗi + "Thử lại"; không cho đặt quá sớm khi chưa có kết quả |
| BK03-01 | `classification = UNKNOWN` | Chuyển sang chọn hạng mục (us-061) |
| BK01-05 | `QUICK_CHECK_NOT_OFFERED` | Ẩn nút Kiểm tra nhanh, toast "Xưởng này chưa có Kiểm tra nhanh" |

---

# 4. Acceptance Criteria (FE)

1. Không có nút "Kiểm tra nhanh" khi `quickCheckOffered = false`.
2. "Vẫn bảo dưỡng đầy đủ" luôn qua hộp xác nhận lần hai trước khi gọi API.
3. Không render câu bảo hành nào khi `warrantyNote = null`.
4. Nhãn "Tính từ lần bảo dưỡng ngày …" hiện đúng `basis`.
5. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `scheduler/early/earlyView.test.ts` | `earlyCardView(check)` → nút theo `classification` + `quickCheckOffered`; khối bảo hành | +5 |
| `vehicles/milestoneBasis.test.ts` | Nhãn `basis`, badge `pendingOemSync` | +2 |
| `scheduler/early/EarlyServiceCard.test.tsx` | `renderToStaticMarkup`: `OVERDUE` không có nút lựa chọn | +1 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-BK03-01, UC-BK03-02, AF-BK03-01/02 | §2.1, §2.2 |
| UC-BK03-04, AF-BK03-03 | §2.1 (`OVERDUE`) |
| SCR-BK03-02, UC-BK03-03, EF-BK03-02 | §2.3 |
| BR-BK03-06 | §2.3, §2.4 |

---

# 7. Analytics

`early_service_card_shown` (`classification`, `quickCheckOffered`), `early_service_choice` (`QUICK_CHECK` / `FULL` / `CANCEL`), `early_service_full_confirmed`.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
