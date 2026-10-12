# Frontend Technical Specification — Tư vấn bảo hành và gói bảo hành

> Frontend cho Feature `FEAT-P2-AD03` (SCR-AD03-01, SCR-AD03-02).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-03-phase2-spec.ff.md). **API:** [API Spec](ad-03-phase2-spec.api.md) (`API-AD03-01/02`, thẻ `WARRANTY_STATUS`, `WARRANTY_PLAN_COMPARE`).
>
> **Tái dùng:** khối "warranty tiles" của Xe của tôi (`VehicleHero`, `warrantyTimeline` — DESIGN.md: chỉ hiển thị, `isActive` từ backend quyết định), `CitationDrawer`, `CardShell` (CH-02). Không tính trạng thái bảo hành ở frontend.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-AD03` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-AD03-01 (thẻ chat + khối Xe của tôi), SCR-AD03-02 (thẻ so sánh gói + trang chi tiết) |
| Routes | `/vehicle/warranty-plans/:planId` (mới, chi tiết so sánh) |
| Feature folder | `frontend/src/features/vehicles/warranty/` (mới), `features/assistant/cards/` |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `WarrantyStatusCard` (SCR-AD03-01)

Dùng ở chat (`WARRANTY_STATUS`) và thay dữ liệu cho khối warranty tiles ở `/vehicle` (cùng API).

| Vùng | Nội dung |
|---|---|
| Mỗi thành phần | Tên ("Pin cao áp"), badge "Còn bảo hành" / "Hết bảo hành" (chữ + icon), "Đến {endDate} hoặc {kmLimit} km" (`font-mono`), "Còn {remainingDays} ngày · {remainingKm} km", thanh thời gian đã dùng (`warrantyTimeline` có sẵn) |
| Nguồn | "Theo dữ liệu hãng, cập nhật {lastRefreshedAt}"; pill điều khoản (`termsCitation`) mở `CitationDrawer` |
| Không dữ liệu xe | Dòng "Chưa có dữ liệu bảo hành riêng của xe; thông tin dưới đây theo chính sách chung" |
| Ghi chú mâu thuẫn | `OEM_DATA_DIFFERS_FROM_POLICY` ⇒ "Dữ liệu của xe khác chính sách chung; EV Care dùng dữ liệu của xe" |
| Nút | Từ `card.actions` (ví dụ "Đặt lịch mốc 24.000 km") |

Hết bảo hành: không có câu cảnh báo mất bảo hành (AF-AD03-01).

## 2.2 `WarrantyPlanCompareCard` (SCR-AD03-02)

| Vùng | Nội dung |
|---|---|
| Đầu | Tên gói, giá gói (`font-mono`), thời hạn / km |
| So sánh | Hai cột: "Mua gói: {planPrice}" vs "Trả từng lần (ước tính): {payAsYouGoEstimate}"; dòng "Chênh lệch {difference}" — chữ trung tính, không dùng màu xanh/đỏ để "khuyên" |
| Giả định | Danh sách `assumptions` luôn hiện (không gập): "Bạn chạy khoảng 1.500 km/tháng (theo ODO 6 tháng)", "Giá theo xưởng {tên}" |
| Mốc bao gồm | Danh sách mốc trong thời hạn |
| Không đủ điều kiện | `eligible = false` ⇒ lý do, ẩn phần so sánh |
| Nguồn | Pill điều khoản gói |
| Chân | "Đây là phép tính tham khảo, không phải lời khuyên mua." |

Chat: dạng gọn + "Xem chi tiết" → `/vehicle/warranty-plans/:planId`. Không có nút "Mua" (FF §3.2).

---

# 3. API Integration & Errors

`features/vehicles/warranty/api.ts`: `getVehicleWarranty`, `compareWarrantyPlan`.

| Lỗi | Xử lý |
|---|---|
| `NO_PLAN_CATALOG` | "Chưa có thông tin gói, bạn có thể hỏi xưởng" (EF-AD03-02) |
| `PLAN_NOT_FOUND` | Quay lại, toast |
| 5xx | Khối lỗi + "Thử lại" |

---

# 4. Acceptance Criteria (FE)

1. Trạng thái thành phần lấy từ `status` backend, không so sánh ngày ở client.
2. Thẻ so sánh luôn hiển thị giả định và câu "không phải lời khuyên mua".
3. Không có nút mua gói.
4. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `vehicles/warranty/warrantyView.test.ts` | Dòng hạn, còn lại, không dữ liệu xe, ghi chú mâu thuẫn | +4 |
| `vehicles/warranty/planCompareView.test.ts` | Giả định luôn có; `eligible = false` ẩn so sánh; chênh lệch âm / dương hiển thị trung tính | +3 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-AD03-01, UC-AD03-01, BR-AD03-01, AF-AD03-01, EDGE-AD03-01 | §2.1 |
| SCR-AD03-02, UC-AD03-03, BR-AD03-03, EF-AD03-02 | §2.2 |
| UC-AD03-02, 04 | Chat (thẻ nguồn) + PL-02 FE |

---

# 7. Analytics

`warranty_card_shown` (`components`, `hasVehicleData`), `warranty_plan_compare_viewed` (`eligible`), `warranty_terms_opened`.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
