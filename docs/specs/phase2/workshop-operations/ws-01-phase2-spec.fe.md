# Frontend Technical Specification — Tự nhận lịch hẹn có điều kiện

> Frontend cho Feature `FEAT-P2-WS01` (SCR-WS01-01, SCR-WS01-02) trên Workshop Portal.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ws-01-phase2-spec.ff.md). **API:** [API Spec](ws-01-phase2-spec.api.md) (`API-WS01-01..05`).
>
> **Nguyên tắc:** frontend không đánh giá luật; chỉ sửa tham số và hiện lý do do backend trả (`manualReviewReasons[].text`).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-WS01` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-WS01-01 (thay khối "Chế độ xác nhận" trong `/technician/settings/booking`), SCR-WS01-02 (chip lý do trên Board) |
| Routes | Không thêm route; khối nằm trong `BookingSettingsPage` |
| Feature folder | `frontend/src/features/workshop-board/` |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `BookingRulesSection` (SCR-WS01-01)

File `features/workshop-board/components/BookingRulesSection.tsx`, đặt trong `BookingSettingsPage.tsx` thay khối chọn "Tự xác nhận / Duyệt tay" của us-029.

| Phần | Nội dung |
|---|---|
| Đầu khối | "Luật nhận lịch" + một câu "Lịch thoả mọi luật được nhận ngay. Lịch chạm một luật sẽ chờ bạn duyệt, kèm lý do." |
| Trạng thái chưa lưu (`saved = false`) | Dòng "Xưởng đang dùng chế độ {Tự xác nhận / Duyệt tay}. Lưu luật để chuyển sang nhận theo luật." |
| 5 hàng luật | Công tắc + tên + mô tả một câu + tham số (bảng dưới). `available = false` ⇒ hàng disabled, dòng "Cần bật tính năng phụ tùng (BK-09)" |
| Xem trước | Khối `RulesPreview`: "Tuần trước, {manualRatePct}% lịch ({manualCount}/{sampleSize}) sẽ phải duyệt tay" + chi tiết theo luật; tính lại 600 ms sau lần sửa cuối (debounce) bằng `API-WS01-03`; `INSUFFICIENT_DATA` ⇒ "Chưa đủ dữ liệu tuần trước" |
| Chỉ số | Dòng nhỏ từ `API-WS01-05`: "7 ngày qua: {ratePct}% duyệt tay (mục tiêu ≤ 20%)" |
| Lưu | Nút "Lưu luật" (primary); câu "Áp dụng cho lịch mới. Lịch đang chờ giữ nguyên." Tắt hết luật ⇒ `DecisionSheet` "Tắt mọi luật sẽ quay về chế độ {fallbackMode}." |

| Luật | Tên | Mô tả | Tham số |
|---|---|---|---|
| `R-CAPACITY` | Còn chỗ | "Nhận ngay nếu sau lịch này trong ngày vẫn còn ít nhất N chỗ trống. Lịch lấy chỗ cuối cùng sẽ chờ duyệt." (EDGE-WS01-01) | Ô số N (1–20) |
| `R-RELIABILITY` | Khách tin cậy thấp | "Khách ở mức Giới hạn (lỡ hẹn / huỷ muộn nhiều) sẽ chờ duyệt." | Checkbox bậc: Cần xác nhận, Giới hạn |
| `R-PARTS` | Phụ tùng đặc biệt | "Phụ tùng chưa rõ hoặc đang về sẽ chờ duyệt." | Checkbox "Chưa rõ", "Về trong N ngày" + ô N |
| `R-SLOT` | Khung chỉ duyệt tay | "Các khung bạn chọn luôn chờ duyệt." | Danh sách khoảng (thứ + giờ bắt đầu–kết thúc), nút thêm / xoá |
| `R-EXTRA` | Báo giá kèm lớn | "Lịch kèm báo giá trên X ₫ sẽ chờ duyệt." | Ô tiền (`font-mono`, định dạng `formatVnd`) |

## 2.2 Chip lý do trên Board (SCR-WS01-02)

| Chỗ | Hành vi |
|---|---|
| Thẻ lịch `pending` trong `WorkshopBoard` | Tối đa 2 chip `manualReviewReasons[].text` (rút gọn 40 ký tự) + "+N"; `EVAL_ERROR` chip "Cần xem lại" màu cảnh báo |
| `BoardBookingDetail` | Khối "Vì sao cần duyệt" liệt kê đủ lý do (AC-WS01-01), cạnh nút Chấp nhận / Từ chối MVP |
| Bộ lọc | Tab / chip lọc "Cần duyệt" ⇒ `?needsReview=true` |
| `MVP_MANUAL` | Một chip "Xưởng đang duyệt tay mọi lịch" |

---

# 3. API Integration & Errors

`features/workshop-board/api.ts`: `getBookingRules`, `saveBookingRules`, `previewBookingRules`, `getBookingRuleStats`; kiểu `BookingRule`, `ReviewReason` ở `types.ts`.

| API | Lỗi | Xử lý |
|---|---|---|
| WS01-02 | `INVALID_RULE_PARAMS` | Lỗi dưới tham số của luật `details.code` |
| WS01-02 | `RULE_UNAVAILABLE` | Tải lại; hàng disabled |
| WS01-03 | Bất kỳ | Ẩn số xem trước, dòng "Không tính được xem trước"; vẫn cho lưu |
| Mọi API | `403` | KTV: ẩn khối, chỉ hiện "Chỉ chủ xưởng sửa được luật" |

---

# 4. States

| State | UI |
|---|---|
| Đang tải | Skeleton 5 hàng |
| Có thay đổi chưa lưu | Nút Lưu bật; rời trang hỏi xác nhận |
| 390 px | Tham số xuống dòng dưới mô tả; danh sách khoảng `R-SLOT` dạng thẻ |

---

# 5. Acceptance Criteria (FE)

1. Mọi lịch `pending` có `MANUAL_RULES` / `EVAL_ERROR` hiện ít nhất một chip lý do.
2. Xem trước gọi lại sau khi ngừng sửa 600 ms, không gọi mỗi phím.
3. KTV không thấy công tắc luật.
4. Tắt hết luật luôn hỏi xác nhận trước khi lưu.
5. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `workshop-board/bookingRules.test.ts` | `validateRuleParams(rule)` khớp schema backend; `allRulesOff(rules)` | +6 |
| `workshop-board/reviewChips.test.ts` | `reviewChips(reasons, max=2)` → chip + "+N"; `EVAL_ERROR` | +3 |
| `workshop-board/BookingRulesSection.test.tsx` | `renderToStaticMarkup` với `available = false` ⇒ hàng disabled | +1 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-WS01-01, BR-WS01-01, BR-WS01-04, Q-WS01-02 | §2.1 |
| UC-WS01-02/03, AC-WS01-01, SCR-WS01-02 | §2.2 |
| AC-WS01-03 | §2.1 dòng chỉ số |

---

# 8. Analytics

`ws_rules_viewed`, `ws_rules_saved` (`enabledCodes`), `ws_rules_preview_shown` (`manualRatePct`), `ws_review_reason_opened` (`codes`).

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
