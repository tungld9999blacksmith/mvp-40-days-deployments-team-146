# Frontend Technical Specification — Giá bảo dưỡng theo mốc, tách phần bảo hành

> Frontend cho Feature `FEAT-P2-AD01` (SCR-AD01-01).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-01-phase2-spec.ff.md). **API:** [API Spec](ad-01-phase2-spec.api.md) (`API-AD01-01/02`, thẻ `ESTIMATE` biến thể `COMPARE`).
>
> **Nguyên tắc:** frontend không cộng tiền, không sắp lại cột theo giá; hiển thị đúng `columns` theo thứ tự backend. Mọi tổng tiền có nhãn "Chi phí ước tính".

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-AD01` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-AD01-01: (1) trang `/estimate/compare` có sẵn (sửa), (2) thẻ so sánh trong chat |
| Feature folder | `frontend/src/features/estimate/` (sửa), `features/assistant/cards/EstimateCompareCard.tsx` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `EstimateCompareTable` (dùng chung)

File `features/estimate/components/EstimateCompareTable.tsx`; dùng ở trang `EstimateCompare` và thẻ chat.

| Hàng (≥ `md`: bảng cột = xưởng; < `md`: thẻ dọc mỗi xưởng, vuốt ngang) | Nội dung |
|---|---|
| Xưởng | Tên + "Xưởng yêu thích" + km |
| Chủ xe trả | `ownerTotal` `font-mono` cỡ lớn + nhãn "ước tính"; `isLowest` ⇒ badge "Thấp nhất" (không dùng màu riêng — badge chữ) |
| Bảo hành chi trả | `warrantyTotal` `font-mono`; 0 ⇒ "—" |
| Tổng giá trị | `itemsTotal` (nhỏ, muted) |
| Bảng giá | "Cập nhật {dd/MM/yyyy}"; `stale` ⇒ badge cảnh báo `AlertTriangle` "Giá cập nhật {staleDays} ngày trước, có thể đã thay đổi" (AC-AD01-02); `priceUpdatedAt = null` ⇒ "Chưa có bảng giá, dùng giá tham khảo" |
| Giá tham khảo | `hasReferencePrice` ⇒ dòng "Một số hạng mục dùng giá tham khảo" |
| Chi tiết | Mở rộng / thu gọn: danh sách `lines` với tag "Bảo hành" (`COVERED`), "Chưa xác định bảo hành" (`UNDETERMINED`) |
| Hành động | "Đặt ở xưởng này" (primary) mỗi cột ⇒ `runScheduler({ trigger: 'OWNER_REQUEST', overrides: { workshopId } })` (BK-01) ⇒ `ScheduleOptionsList` |

Chân bảng: "Chi phí ước tính. Xưởng sẽ báo giá chính thức khi kiểm tra xe."

## 2.2 Trang `/estimate/compare` (sửa `features/estimate/pages/EstimateCompare.tsx`)

- Vào từ `Estimate` ("So sánh xưởng") không còn bắt buộc chọn xưởng trước: không có `workshopIds` trong URL ⇒ gọi API không tham số (backend tự chọn theo BK-01); có ⇒ giữ hành vi cũ.
- Nút "Đổi xưởng so sánh" mở bộ chọn tối đa 3 xưởng (`WorkshopSelect` có sẵn) ⇒ cập nhật query `workshopIds`.
- `mode = SINGLE` ⇒ hiện một cột + dòng "Chỉ một xưởng phù hợp với thói quen đặt lịch của bạn" + link sửa thói quen (BK-01).
- `mode = NONE` ⇒ trạng thái rỗng + link "Mở rộng khu vực" (`/settings/scheduling`).

## 2.3 Thẻ chat `ESTIMATE` biến thể `COMPARE`

`CARD_RENDERERS.ESTIMATE` (CH-02): `card.variant === 'COMPARE'` ⇒ `EstimateCompareCard` render `EstimateCompareTable` chế độ gọn (chỉ hàng Xưởng, Chủ xe trả, Bảo hành, cảnh báo giá cũ) + nút từ `card.actions` ("Đặt ở {xưởng}" là `CHIP`), link "Xem chi tiết" → `/estimate/compare?…`. Thẻ `ESTIMATE` cũ giữ nguyên.

---

# 3. API Integration & Errors

`features/estimate/api.ts`: `compareEstimates({ userVehicleId, odoMilestone?, workshopIds? })` — tham số tuỳ chọn; kiểu `CompareColumn` theo API §3.3.

| Lỗi | Xử lý |
|---|---|
| Mã lỗi us-045 | Giữ xử lý hiện có |
| `ESTIMATE_INVARIANT_BROKEN` / 5xx | "Không tính được dự toán lúc này" + "Thử lại"; không hiện số nào |

---

# 4. Acceptance Criteria (FE)

1. Thứ tự cột = thứ tự `columns` từ API (test so sánh).
2. Cột giá cũ có badge cảnh báo (AC-AD01-02).
3. Mọi tổng tiền có nhãn "ước tính".
4. Không có phép cộng tiền nào ở frontend (tổng lấy từ API).
5. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `estimate/compareView.test.ts` | `compareColumnView(col)` → nhãn giá cũ, "Thấp nhất", giá tham khảo, `UNDETERMINED` | +5 |
| `estimate/EstimateCompareTable.test.tsx` | `renderToStaticMarkup`: thứ tự cột giữ nguyên; có "Chi phí ước tính" | +2 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-AD01-01, BR-AD01-01, 04 | §2.1, §2.2 |
| BR-AD01-02, AC-AD01-02 | §2.1 hàng Bảng giá |
| BR-AD01-03, AC-AD01-03 | §2.1 (số từ API) |
| UC-AD01-02 | §2.1 hành động |
| AF-AD01-01 | §2.2 `SINGLE` |

---

# 7. Analytics

`estimate_compare_viewed` (`mode`, `columns`, `staleCount`), `estimate_compare_book_clicked` (`rank`, `isLowest`), `estimate_compare_details_toggled`.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
