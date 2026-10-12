# Frontend Technical Specification — Báo giá phát sinh khi thay phụ tùng

> Frontend cho Feature `FEAT-P2-AD04` (SCR-AD04-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-04-phase2-spec.ff.md). **API:** [API Spec](ad-04-phase2-spec.api.md) (`API-AD04-01..08`, thẻ `EXTRA_QUOTE`).
>
> **Tái dùng (DESIGN.md):** `PhotoUploadTile` / `PhotoAddTile` (chụp ảnh, mở camera trên điện thoại), `DecisionCard` (dòng quyết định `divide-y`, badge "Hạng mục an toàn"), `DecisionSheet` (xác nhận quyết định tiền), `PhoneDecisionDialog`, `ExtraItemDrawer` của Board. Giá phát sinh là giá xưởng đã duyệt: **không** gắn nhãn "ước tính" (BR-AD04-07).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-AD04` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-AD04-01 (KTV / chủ xưởng tạo), SCR-AD04-02 (chủ xưởng duyệt), SCR-AD04-03 (thẻ chủ xe + trang chi tiết) |
| Routes | `/ktv/jobs/:bookingId/extra` (KTV), `/technician/extra-quotes` (chủ xưởng, hàng đợi), `/bookings/:bookingId/extras/:quoteId` (chủ xe) |
| Feature folder | `frontend/src/features/extra-quote/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `ExtraQuoteForm` (SCR-AD04-01)

Dùng ở app KTV (`/ktv/jobs/:bookingId/extra`, nút "Phát sinh" của WS-03) và Board chủ xưởng (`ExtraItemDrawer` có sẵn chuyển sang form này).

| Bước (một màn, cuộn dọc, mobile-first) | Nội dung |
|---|---|
| Ảnh | Lưới `PhotoUploadTile` + `PhotoAddTile` (camera), tối đa 3 ảnh, bắt buộc ≥ 1 (EF-AD04-01) — tải ngay qua `line-photos` khi chọn |
| Phụ tùng / công | Ô tìm theo tên trong danh mục xưởng (giá hiện bên cạnh, `font-mono`; giá tham khảo có nhãn "Giá tham khảo"); số lượng; tối đa 10 dòng |
| Mức khẩn | 3 lựa chọn: "An toàn" (icon `ShieldAlert`), "Nên làm", "Có thể để sau" |
| Lý do | Ô chữ 5–300 ký tự, placeholder "Ví dụ: Lốp sau trái phồng hông" |
| Gửi | "Gửi chủ xưởng duyệt" (KTV) / "Gửi" (chủ xưởng — vào thẳng màn duyệt §2.2) |

Validate client: ảnh ≥ 1, ≥ 1 dòng, lý do ≥ 5 ký tự; nút disabled đến khi đủ. Ảnh đang tải ⇒ nút disabled.

## 2.2 Duyệt (SCR-AD04-02) — chủ xưởng

Route `/technician/extra-quotes` (link từ `TechnicianDashboard` thẻ "Phát sinh chờ duyệt" + badge đếm) và khối trong `BoardBookingDetail`.

| Vùng | Nội dung |
|---|---|
| Đầu | Mã lịch, xe (`PlateTile`), người tạo ("KTV An"), thời gian |
| Ảnh | Thumbnail 56 px, chạm mở lớn |
| Giải thích | Đoạn agent soạn (badge "Trợ lý soạn") + nguồn; ô sửa (textarea) |
| Dòng | `DecisionCard`-style: tên, số lượng, ô giá sửa được (`font-mono`), badge an toàn |
| Tổng | "Tổng hiện tại {totalBefore} → sau phát sinh {totalAfter}"; "Vượt {EXTRA_CONSENT_PCT}% — chủ xe phải đồng ý" khi `consentRequired` (tính lại ở server khi bấm duyệt; hiển thị gợi ý từ dữ liệu server) |
| Hành động | "Duyệt và gửi khách" (primary, `DecisionSheet` tóm tắt số tiền), "Từ chối" (bắt buộc ghi chú) |

Danh sách phát sinh của một lịch (`API-AD04-02`) hiện trên Board kèm trạng thái: "Chờ duyệt", "Đã gửi khách · còn {phút}", "Chờ khách" (nút "Gọi khách" `tel:` + "Ghi đồng ý qua điện thoại" mở `PhoneDecisionDialog`), "Khách muốn gọi", "Đã đồng ý", "Không thay".

## 2.3 Thẻ chủ xe (SCR-AD04-03)

`EXTRA_QUOTE` trong `CARD_RENDERERS` (CH-02) + trang `/bookings/:bookingId/extras/:quoteId` (mở từ thông báo; cùng component).

| Vùng | Nội dung |
|---|---|
| Đầu | "Xưởng phát hiện cần làm thêm" + badge mức khẩn (An toàn = cảnh báo + `ShieldAlert`) |
| Ảnh | Lưới ảnh, chạm mở lớn |
| Giải thích | `explanation` + pill nguồn (nếu có) |
| Dòng | Tên, số lượng, giá (`font-mono`), không nhãn "ước tính"; khi nhiều dòng: checkbox từng dòng (mặc định chọn hết) |
| Tổng | "Tổng: {totalBefore} → {totalAfter}" (`font-mono`); "Bạn cần xác nhận trước khi xưởng làm" khi `consentRequired`; ngược lại "Xưởng sẽ làm nếu bạn không phản đối trước {respondBy}" |
| Nút | "Đồng ý thay" (primary) · "Không thay lần này" (secondary) · "Gọi cho xưởng" (ghost) |

**Hành vi:**
- "Đồng ý thay" ⇒ `DecisionSheet` "Thêm {hạng mục} · {thisTotal}? Tổng mới {totalAfter}" ⇒ `decision = ACCEPT` (hoặc `PER_LINE` khi bỏ chọn một số dòng).
- "Không thay lần này" ⇒ có dòng an toàn: `DecisionSheet` dạng `alertdialog` nút danger, nội dung cảnh báo từ server ("Không nên lái xe tốc độ cao…"), gửi `confirmSafetyDecline = true`; không có dòng an toàn: xác nhận một bước.
- "Gọi cho xưởng" ⇒ `decision = CALL_WORKSHOP` ⇒ hiện hotline dạng chữ + nút `tel:` (AF-AD04-03).
- Gửi kèm `version`; `EXTRA_QUOTE_CHANGED` ⇒ tải lại thẻ + toast "Xưởng vừa cập nhật giá".
- Sau quyết định thẻ chuyển trạng thái (CH-02 `COMPLETED`) với nhãn "Đã đồng ý" / "Không thay" / "Đã đồng ý một phần".

---

# 3. API Integration & Errors

`features/extra-quote/api.ts`: `createExtraQuote`, `listBookingExtraQuotes`, `listPendingExtraQuotes`, `approveExtraQuote`, `rejectExtraQuote`, `recordPhoneDecision`, `getOwnerExtraQuote`, `decideExtraQuote`.

| Lỗi | Xử lý |
|---|---|
| `BOOKING_NOT_IN_SERVICE` | "Chỉ tạo phát sinh khi xe đang ở xưởng" |
| `PERMISSION_DENIED` | Ẩn nút "Phát sinh" |
| `EXTRA_QUOTE_INVALID_STATE` | Tải lại; thẻ theo trạng thái mới |
| `SAFETY_DECLINE_CONFIRMATION_REQUIRED` | Mở hộp xác nhận lần hai |
| `EXTRA_QUOTE_CHANGED` | Tải lại + toast |

---

# 4. States

| State | UI |
|---|---|
| Ảnh đang tải | Vòng tiến độ trên ảnh (`PhotoUploadTile`) |
| Đang gửi quyết định | Nút loading, các nút khác disabled |
| 390 px | Form KTV một cột, nút đáy dính; thẻ chủ xe nút xếp dọc |

---

# 5. Acceptance Criteria (FE)

1. Không gửi được nháp khi chưa có ảnh.
2. Giá trên thẻ chủ xe không có nhãn "ước tính".
3. Từ chối hạng mục an toàn luôn qua xác nhận lần hai.
4. Thẻ hiện đúng câu theo `consentRequired`.
5. KTV không có nút duyệt ở bất kỳ đâu.
6. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `extra-quote/formValidation.test.ts` | Thiếu ảnh / dòng / lý do ⇒ không gửi | +3 |
| `extra-quote/ownerCardView.test.ts` | Câu tổng theo `consentRequired`; nút theo trạng thái; `PER_LINE` khi bỏ chọn | +4 |
| `extra-quote/safetyDecline.test.ts` | Có dòng an toàn ⇒ cần xác nhận lần hai | +2 |
| `extra-quote/boardStatus.test.ts` | Nhãn trạng thái phía xưởng | +2 |
| `extra-quote/ExtraQuoteCard.test.tsx` | `renderToStaticMarkup`: không có chuỗi "ước tính" | +1 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-AD04-01, BR-AD04-02, EF-AD04-01 | §2.1 |
| SCR-AD04-02, BR-AD04-03, EDGE-AD04-02 | §2.2 |
| SCR-AD04-03, BR-AD04-04, 05, 07, AF-AD04-01, 03 | §2.3 |
| UC-AD04-04 | §2.2 trạng thái "Chờ khách" |

---

# 8. Analytics

`extra_quote_form_opened` (`actor`), `extra_quote_submitted` (`urgency`, `lines`, `photos`), `extra_quote_approved` (`edited`), `extra_quote_owner_decision` (`decision`, `secondsSinceSent`), `extra_quote_phone_recorded`.

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
