# Frontend Technical Specification — Hỗ trợ tại khoang làm việc

> Frontend cho Feature `FEAT-P2-TA02` (SCR-TA02-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ta-02-phase2-spec.ff.md). **API:** [API Spec](ta-02-phase2-spec.api.md) (`API-TA02-01..04`).
>
> **Nguyên tắc:** dùng một tay trên tablet / điện thoại (vùng chạm ≥ 48 px, FF §18). Văn bản từ giọng nói không bao giờ tự lưu (BR-TA02-03).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-TA02` |
| Version | `v0.2` |
| Status | `Draft` |
| Screens | SCR-TA02-01 (checklist trong `/ktv/jobs/:bookingId` và Board), SCR-TA02-02 (giao ca), SCR-TA02-03 (`VoiceInput` dùng chung) |
| Routes | `/ktv/handover`, `/technician/handover` (mới) |
| Feature folder | `frontend/src/features/technician-app/checklist/`, `features/technician-app/voice/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `ServiceChecklist` (SCR-TA02-01)

Hiện ở chi tiết việc KTV (WS-03 FE §2.4) khi bước tiến độ là "Đang thực hiện" (và ở `BoardBookingDetail` cho chủ xưởng).

| Phần | Nội dung |
|---|---|
| Đầu | "{n}/{m} mục bắt buộc" + thanh tiến độ (có chữ); nguồn "Theo {tài liệu} {phiên bản}" (pill mở `CitationDrawer`); `notice = NO_DETAILED_CHECKLIST` ⇒ dòng "Chưa có checklist chi tiết, dùng danh mục hạng mục của mốc" |
| Mục | Hàng cao ≥ 56 px, toàn hàng là vùng chạm: ô đánh dấu lớn, nhãn, dấu "Bắt buộc"; chạm giữ / menu "…" ⇒ "Bỏ qua" (sheet lý do: chọn nhanh "Khách từ chối" / "Không áp dụng cho xe này" / nhập) và "Bỏ đánh dấu"; người + giờ đánh dấu dạng chữ nhỏ |
| Nút chuyển bước | Stepper tiến độ: nút sang "Kiểm tra chất lượng" disabled khi `requiredRemaining > 0`, kèm "Còn {k} mục bắt buộc" và nút cuộn tới mục đầu tiên còn thiếu |

Cập nhật lạc quan; lỗi ⇒ trả lại. `CHECKLIST_INCOMPLETE` từ API tiến độ ⇒ tô các mục `details.items`.

## 2.2 Giao ca (SCR-TA02-02)

Route `/ktv/handover` (KTV) và `/technician/handover` (chủ xưởng); thông báo "Tóm tắt giao ca" mở trang này. Ba nhóm có tiêu đề + số lượng: "Đang làm dở", "Chờ phụ tùng", "Chờ khách duyệt"; mỗi xe: `PlateTile`, bước, checklist "4/6", KTV, ghi chú gần nhất; nút "Thêm ghi chú giao ca" (`VoiceInput` hoặc gõ) ⇒ `API-TA02-04`.

## 2.3 `VoiceInput` (SCR-TA02-03)

`features/technician-app/voice/VoiceInput.tsx`, dùng cho ghi chú giao ca và ô hỏi trợ lý xưởng (TA-01):
- Dùng Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`, `lang = 'vi-VN'`) — không thêm dependency. Không hỗ trợ hoặc bị chặn micro ⇒ ẩn nút (EF-TA02-02).
- Nút micro lớn (≥ 56 px); khi nghe: chỉ báo + văn bản tạm thời hiện dần.
- Kết thúc ⇒ văn bản vào ô **chỉnh sửa được** với 3 nút "Xác nhận" (primary), "Sửa" (focus ô), "Huỷ". Chỉ "Xác nhận" mới gửi API / gửi câu hỏi (AC-TA02-02); `inputMethod = VOICE`.
- Lần đầu dùng: hộp thông tin "Giọng nói được trình duyệt chuyển thành chữ (có thể gửi âm thanh tới dịch vụ nhận dạng của trình duyệt). EV Care chỉ lưu chữ bạn đã xác nhận." — cần duyệt quyền riêng tư (Q-FE-TA02-01).
- **Pending (PO 2026-10-12, Q-TA02-02):** toàn bộ phần giọng nói ở mục này là phương án đề xuất, PO đang xem xét công nghệ và tính khả thi. Không triển khai cho tới khi chốt; các phần khác của TA-02 làm độc lập (nút micro ẩn sau cờ tính năng).
- Logic trạng thái (`idle → listening → review → sent`) ở hàm thuần `voiceReducer.ts`.

---

# 3. API Integration & Errors

`features/technician-app/checklist/api.ts`: `getChecklist`, `markChecklistItem`, `getHandover`, `addHandoverNote`.

| Lỗi | Xử lý |
|---|---|
| `SKIP_REASON_REQUIRED` | Mở sheet lý do |
| `CHECKLIST_INCOMPLETE` | §2.1 |
| `BOOKING_NOT_IN_SERVICE` | Ẩn checklist |

---

# 4. Acceptance Criteria (FE)

1. Nút chuyển bước bị khoá khi còn mục bắt buộc `pending` (AC-TA02-01).
2. Không có đường nào gửi văn bản giọng nói khi chưa bấm "Xác nhận" (test `voiceReducer`).
3. Vùng chạm ≥ 48 px; dùng được một tay ở 390 px và tablet.
4. Hai theme; `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `checklist/checklistView.test.ts` | Đếm bắt buộc, khoá nút, mục thiếu đầu tiên | +3 |
| `voice/voiceReducer.test.ts` | Chỉ `CONFIRM` tạo hành động gửi; `CANCEL` xoá | +4 |
| `checklist/handoverView.test.ts` | Nhóm 3 loại | +2 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-TA02-01, UC-TA02-01/02, BR-TA02-01, AF-TA02-01, EF-TA02-01 | §2.1 |
| SCR-TA02-02, UC-TA02-03, BR-TA02-02 | §2.2 |
| SCR-TA02-03, UC-TA02-04, BR-TA02-03, EF-TA02-02 | §2.3 |

---

# 7. Analytics

`checklist_opened`, `checklist_item_marked` (`status`), `checklist_blocked_transition`, `voice_input_used` (`confirmed`), `handover_viewed`.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
| `v0.2` | `2026-10-12` | Nhập giọng nói chuyển Pending (Q-TA02-02) |
