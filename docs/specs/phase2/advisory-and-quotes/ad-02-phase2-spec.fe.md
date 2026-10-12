# Frontend Technical Specification — Tư vấn phụ tùng và báo giá sửa chữa

> Frontend cho Feature `FEAT-P2-AD02` (SCR-AD02-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-02-phase2-spec.ff.md). **API:** [API Spec](ad-02-phase2-spec.api.md) (thẻ `REPAIR_ADVICE`, `SAFETY_ADVICE`; `API-AD02-01..05`).
>
> **Nguyên tắc:** giá luôn hiển thị dạng khoảng + tiền công riêng + ngày cập nhật + nhãn "ước tính"; thẻ an toàn luôn đứng trước và không có giá.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-AD02` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-AD02-01 (thẻ tư vấn sửa chữa), SCR-AD02-02 (thẻ an toàn), SCR-AD02-03 (bảng giá sửa chữa — tab trong `/technician/price-list`) |
| Feature folder | `frontend/src/features/assistant/cards/` (2 thẻ mới), `frontend/src/features/workshop-pricing/` (tab mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `RepairAdviceCard` (SCR-AD02-01)

| Vùng | Nội dung |
|---|---|
| Đầu | "Hạng mục có thể liên quan" |
| Hạng mục (≤ 3) | Tên + pill nguồn (mở `CitationDrawer` có sẵn) |
| Cảnh báo cố định | "Cần kỹ thuật viên kiểm tra để xác nhận." (luôn hiện, không ẩn được) |
| Bảng xưởng (≤ 3) | Mỗi xưởng: tên, km; mỗi hạng mục: "Phụ tùng {min}–{max}" + "Công {labor}" (`font-mono`), "ước tính", "Giá cập nhật {ngày}" (+ badge cảnh báo khi `stale`), tồn kho (BK-09: "Có sẵn" / "Về trong N ngày" / "Chưa rõ") |
| Thiếu giá | "Xưởng chưa có giá cho hạng mục này" |
| Nút | Từ `card.actions`: "Đặt lịch thay {hạng mục}" (primary), "So sánh xưởng", "Xin xưởng báo giá" (khi thiếu giá) |

Trên 390 px: mỗi xưởng một khối dọc; ≥ `md`: bảng cột theo xưởng (tái dùng bố cục `EstimateCompareTable` AD-01).

## 2.2 `SafetyAdviceCard` (SCR-AD02-02)

- Khối nền cảnh báo nhạt (`--color-warning` token, không thêm màu), icon `AlertTriangle`, tiêu đề theo nhóm ("Dừng xe và kiểm tra phanh ngay").
- Các bước hướng dẫn (danh sách đánh số) từ `card.data.steps`.
- Hotline: tên xưởng + số điện thoại **dạng chữ chọn được** (`user-select: text`, `font-mono`) + nút "Gọi" (`tel:`).
- Nút "Đặt lịch kiểm tra sớm nhất" (primary, chip).
- Không có bất kỳ con số giá nào.
- `role="alert"` để trình đọc màn hình đọc ngay.

## 2.3 Chip hỏi thêm triệu chứng

Khi tool trả `needsClarification`, tin trợ lý kèm chip (CH-01 `TYPE_AND_SEND`): "Tiếng kêu", "Rung", "Đèn cảnh báo", "Khi nào xảy ra". Tối đa 2 lượt (backend quyết định).

## 2.4 Bảng giá sửa chữa (SCR-AD02-03)

`features/workshop-pricing/pages/PriceListPage.tsx` thêm tab "Sửa chữa" (tab "Bảo dưỡng" là bảng giá hiện có):

| Phần | Nội dung |
|---|---|
| Bộ lọc | Model (select), ô tìm hạng mục |
| Bảng | Hạng mục, mã phụ tùng hãng (`font-mono`), Giá phụ tùng từ–đến, Tiền công, Thời lượng (phút), Cập nhật — sửa trực tiếp trong ô, lưu khi blur (`PUT`) |
| Thêm dòng | Tìm trong danh mục (`API-AD02-04`) ⇒ thêm |
| Tải CSV | Nút "Tải CSV" ⇒ chạy thử (`dryRun`) ⇒ hiện lỗi theo dòng ⇒ "Áp dụng"; link "Tải file mẫu" (CSV tĩnh trong `public/`) |
| Gợi ý | Dòng tiến độ "Đã nhập {n}/20 hạng mục phổ biến" (Q-AD02-02) |

Validate client: `min ≤ max`, số không âm, thời lượng 5–600.

---

# 3. API Integration & Errors

`features/workshop-pricing/api.ts` thêm `listRepairPrices`, `putRepairPrice`, `importRepairPrices(file, dryRun)`, `searchRepairItems`; `features/assistant/cards/` render theo CH-02.

| Lỗi | Xử lý |
|---|---|
| `INVALID_REQUEST` | Lỗi dưới ô |
| `FILE_TOO_LARGE` | "File tối đa 1 MB" |
| Import có `errors` | Bảng lỗi theo dòng, không cho "Áp dụng" |

---

# 4. Acceptance Criteria (FE)

1. `RepairAdviceCard` luôn có câu "Cần kỹ thuật viên kiểm tra để xác nhận".
2. Không render giá dạng một con số; luôn khoảng + công riêng.
3. `SafetyAdviceCard` không chứa chuỗi tiền và có `role="alert"`.
4. CSV chỉ áp dụng sau khi chạy thử không lỗi.
5. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `cards/repairAdviceView.test.ts` | Định dạng khoảng giá, công riêng, nhãn cũ, tồn kho | +4 |
| `cards/SafetyAdviceCard.test.tsx` | `renderToStaticMarkup`: không có "₫", có `role="alert"` | +1 |
| `workshop-pricing/repairPriceRow.test.ts` | Validate `min ≤ max`, thời lượng | +3 |
| `workshop-pricing/csvImport.test.ts` | Ánh xạ lỗi theo dòng | +2 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-AD02-01, BR-AD02-01, 03, 07, EF-AD02-03 | §2.1 |
| SCR-AD02-02, BR-AD02-04 | §2.2 |
| AF-AD02-01 | §2.3 |
| SCR-AD02-03, UC-AD02-05 | §2.4 |

---

# 7. Analytics

`repair_advice_shown` (`items`, `workshops`, `missingPrice`), `repair_book_clicked`, `repair_quote_requested`, `safety_advice_shown` (`group`), `safety_call_clicked`, `ws_repair_price_imported` (`rows`).

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
