# Frontend Technical Specification — Chọn xưởng theo phụ tùng sẵn có

> Frontend cho Feature `FEAT-P2-BK09` (SCR-BK09-01, SCR-BK09-02).
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-09-phase2-spec.ff.md). **API:** [API Spec](bk-09-phase2-spec.api.md) (`API-BK09-01..06`).
>
> **Nguyên tắc:** chủ xe chỉ thấy trạng thái + ngày (không số lượng). Nhãn luôn kèm thời điểm cập nhật.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-BK09` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-BK09-01 (trang Tồn kho Workshop Portal), SCR-BK09-02 (nhãn phụ tùng — component dùng chung) |
| Routes | `/technician/parts` (mới) |
| Feature folder | `frontend/src/features/parts/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `PartsBadge` (SCR-BK09-02)

`features/parts/PartsBadge.tsx`, dùng ở thẻ phương án (BK-01), thẻ xưởng bản đồ (BK-05), thẻ tư vấn sửa chữa (AD-02), cột so sánh (AD-01):

| `status` | Hiển thị |
|---|---|
| `IN_STOCK` | Badge "Có sẵn phụ tùng" (icon `PackageCheck`) |
| `ARRIVING` | Badge "Phụ tùng về {dd/MM}" (icon `Truck`) |
| `UNKNOWN` | Badge muted "Phụ tùng chưa rõ" |
| `NOT_REQUIRED` | Không hiện |

Tooltip / dòng phụ: "Xưởng cập nhật {updatedAt}". Nhãn có chữ, không chỉ màu.

## 2.2 Lựa chọn của chủ xe

`ScheduleOptionsList` (BK-01) khi ít nhất một phương án có `parts`: công tắc "Chỉ xưởng có sẵn phụ tùng" ⇒ chạy lại `runScheduler({ requirePartsInStock: true })`. `RelaxationPanel` hiện offer `PREORDER_PARTS` ("Đặt trước phụ tùng ở {xưởng}, sớm nhất {ngày}") và `ALLOW_NOT_IN_STOCK`.

Vé lịch `parts_preordered`: dòng "Phụ tùng đã được đặt trước".

## 2.3 Tồn kho (SCR-BK09-01)

Route `/technician/parts`; link từ `TechnicianDashboard` và `PriceListPage` (tab).

| Phần | Nội dung |
|---|---|
| Bảng | Mã phụ tùng (`font-mono`), tên, Tồn (sửa trực tiếp), Đang giữ, Khả dụng, Ngày về + SL về (sửa), Cập nhật (badge "Cũ" khi `stale`) |
| Hành động hàng | "Vẫn đúng" (gửi lại giá trị hiện tại để làm mới `updatedAt`) |
| Thêm dòng | Tìm danh mục (`API-BK09-04`) |
| CSV | Như AD-02: chạy thử ⇒ lỗi theo dòng ⇒ áp dụng; file mẫu |
| Cảnh báo | `BELOW_RESERVED` ⇒ hộp liệt kê lịch bị ảnh hưởng |

Board: lịch `parts_shortage` có badge cảnh báo "Thiếu phụ tùng" + nút "Báo không phục vụ được (thiếu phụ tùng)" ⇒ `API-BK09-06`.

---

# 3. API Integration & Errors

`features/parts/api.ts`: `listStock`, `putStock`, `importStock`, `searchParts`, `reportPartsUnavailable`.

| Lỗi | Xử lý |
|---|---|
| `INVALID_REQUEST` | Lỗi dưới ô |
| `PART_NOT_FOUND` | Lỗi dòng import |

---

# 4. Acceptance Criteria (FE)

1. Không có số lượng phụ tùng trên mọi màn chủ xe.
2. Nhãn luôn có thời điểm cập nhật (tooltip hoặc dòng phụ).
3. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `parts/partsBadge.test.ts` | 4 trạng thái → nhãn | +4 |
| `parts/stockRow.test.ts` | Khả dụng, `stale`, validate số | +3 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-BK09-02, BR-BK09-02, 07 | §2.1 |
| BR-BK09-03, 04, UC-BK09-03 | §2.2 |
| SCR-BK09-01, UC-BK09-01, EF-BK09-02 | §2.3 |

---

# 7. Analytics

`parts_filter_toggled` (`requireInStock`), `parts_preorder_selected`, `ws_stock_updated` (`rows`), `ws_stock_imported`.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
