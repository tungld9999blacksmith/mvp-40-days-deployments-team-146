# Frontend Technical Specification — Báo giá có chủ xưởng duyệt (HITL)

> Đặc tả frontend cho Feature `FEAT-QUOTE-001` (PRD F5b, US-049 → US-052).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-049-sprint-3-spec.ff.md) · **API:** [API Spec](../api/us-049-sprint-3-spec.api.md)
>
> **Phạm vi FE:** (1) App chủ xe — nháp, chi tiết, danh sách báo giá, thẻ `CARD-QUOTE` trong chat; (2) Workshop Portal — thay dữ liệu mock của `/technician/quotes` (`PendingQuotes.tsx`) và `/technician/quote-review` (`QuoteReview.tsx`).

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-QUOTE-001` — Báo giá HITL |
| Screen | `SCR-1101` Nháp · `SCR-1102` Chi tiết · `SCR-1103` Báo giá của tôi · `SCR-1111` Chờ duyệt · `SCR-1112` Duyệt · `SCR-1113` Từ chối · `CARD-QUOTE` |
| Route | App: `/quotes` · `/quotes/new` · `/quotes/:quoteId` · Portal: `/technician/quotes` · `/technician/quote-review?quoteId=…` |
| Version | `v1.0` |
| Author | Team 4 Người |
| Status | `Draft` |
| Related PRD | [PRD §F5b](../../../product/PRD_EV_Care_MVP.md) |
| Related API | [API-QT-01 → 14](../api/us-049-sprint-3-spec.api.md) |
| Last Updated | `2026-09-30` |

---

# 2. Screen Overview

## 2.1 Purpose

- Chủ xe: biến dự toán thành báo giá có xưởng xác nhận; theo dõi kết quả; dùng báo giá khi đặt lịch.
- Chủ xưởng: duyệt/sửa giá/từ chối báo giá của xưởng mình trên một màn hình.

## 2.2 Entry Points

| Entry Point | Actor | Action |
|---|---|---|
| SCR-1001 Dự toán — "Gửi xưởng báo giá" | Chủ xe | `/quotes/new?userVehicleId&workshopId&odoMilestone` → gọi `API-QT-01` → thay route bằng `/quotes/:id` |
| Chat — `CARD-QUOTE` | Chủ xe | Nút "Gửi xưởng duyệt" (gọi qua Agent) / "Xem chi tiết" |
| Home — badge "Báo giá có kết quả" | Chủ xe | `/quotes?unseenResult=true` |
| Portal sidebar "Báo giá" | Chủ xưởng | `/technician/quotes` |
| Board (F8) chi tiết booking — link báo giá gắn kèm | Chủ xưởng | `/technician/quote-review?quoteId=…` |

## 2.3 Exit Points

| Condition | Destination |
|---|---|
| Chủ xe "Đặt lịch với báo giá này" | `/booking?workshopId&odoMilestone&quoteId` (us-029 FE) |
| Chủ xe "Lập báo giá mới" (sau từ chối/hết hạn) | `/estimate?odoMilestone` |
| Chủ xưởng duyệt/từ chối xong | `/technician/quotes` + toast |

---

# 3. UI Structure

## 3.1 SCR-1101 / SCR-1102 (mobile)

```text
┌─────────────────────────────────────┐
│ ← Báo giá · VinFast Smart City      │
│ [DRAFT | Chờ xưởng duyệt | Đã duyệt │
│  | Đã duyệt (có điều chỉnh) | Hết   │
│  hiệu lực | Bị từ chối]             │
│ Mốc 12.000 km · VF 6                │
├─────────────────────────────────────┤
│ Trong bảo hành: Kiểm tra pin   0 ₫  │
│ Thay dầu phanh *   ~~350.000~~ 320.000│
│ …                                   │
├─────────────────────────────────────┤
│ Tổng: 1.270.000 ₫                   │
│ [Báo giá đã duyệt — hiệu lực đến 07/10]│
│ Ghi chú xưởng: "…"                  │
├─────────────────────────────────────┤
│ DRAFT:    [Xoá nháp] [Gửi xưởng duyệt]│
│ APPROVED: [Đặt lịch với báo giá này] │
│ REJECTED/EXPIRED: [Lập báo giá mới]  │
└─────────────────────────────────────┘
```

## 3.2 SCR-1112 Duyệt (desktop, dựa trên `QuoteReview.tsx`)

- Trái: bảng dòng — tên | badge "Bảo hành" | giá ước tính + nguồn | ô **Giá duyệt** | ghi chú dòng.
- Dưới bảng: Tổng ước tính · Tổng duyệt (tạm tính phía FE, nhãn "tạm tính") · chọn thời hạn (1–30 ngày, mặc định 7) · "Ghi chú của chủ xưởng".
- Phải: thông tin khách (tên, SĐT, model, biển số), thời điểm gửi, "Chờ > 24h" nếu `isWaitingLong`, link "Xem hội thoại" khi `hasConversation`.
- Nút: **Từ chối** (mở SCR-1113) · **Duyệt**.

**Thay đổi so với mock hiện có:**

| Mock | Spec | Lý do |
|---|---|---|
| Nút thêm/xoá dịch vụ, `aiSuggested`, `included` | Bỏ | Không thêm/xoá dòng trong MVP (FF BR-1105, Q-1102) |
| "Ghi chú kỹ thuật viên" | "Ghi chú của chủ xưởng" | Người duyệt là chủ xưởng (FF TERM, Q-411) |
| Nút "Save draft" (nếu có) | Bỏ | Không có trạng thái nháp phía xưởng |
| Trạng thái `pending/approved/rejected` hard-code | Dùng `displayStatus` từ API | Có `MODIFIED`, `EXPIRED` suy ra ở backend |

---

# 4. Component Specification

## 4.1 QuoteStatusBadge

| `displayStatus` | Label | Màu |
|---|---|---|
| `DRAFT` | Nháp | muted |
| `PENDING_APPROVAL` | Chờ xưởng duyệt | warning |
| `APPROVED` | Đã duyệt | emerald |
| `MODIFIED` | Đã duyệt (có điều chỉnh) | emerald |
| `EXPIRED` | Hết hiệu lực | muted |
| `REJECTED` | Bị từ chối | error |

## 4.2 QuoteItemTable

- Dòng `covered`: badge "Bảo hành", giá "0 ₫", không có ô sửa (Portal) — FF Q-1103.
- `priceSource = REFERENCE_PRICE`: dấu `*` + chú thích "giá tham khảo của hãng".
- Chủ xe, khi `approvedPrice ≠ estimatedPrice`: hiển thị giá ước tính gạch ngang + giá duyệt + `reviewerNote` dòng (nếu có).

## 4.3 PriceInput (Portal)

- Chỉ số nguyên VNĐ ≥ 0 (định dạng nghìn khi blur); rỗng = giữ giá ước tính.
- Chỉ gửi dòng có thay đổi trong `items[]` của `API-QT-13`.

## 4.4 RejectDialog (SCR-1113)

- Textarea bắt buộc 10–500 ký tự, đếm ký tự; nút "Từ chối" disabled khi chưa hợp lệ.

## 4.5 CARD-QUOTE (chat)

- Trạng thái nháp: tóm tắt tổng + nút **Gửi xưởng duyệt** (phát sự kiện xác nhận cho AI-005 kèm `confirmation_token` của thẻ) + "Xem chi tiết".
- Trạng thái khác: badge §4.1 + tổng + "Xem chi tiết".

## 4.6 PendingQuoteList (SCR-1111)

- Cột: khách, model/biển số, mốc, tổng ước tính, gửi lúc, thời gian chờ (nhãn đỏ "Chờ > 24h"), trạng thái.
- Tab lọc: Chờ duyệt (mặc định) · Đã duyệt · Bị từ chối. Sắp chờ lâu nhất trước.

---

# 5. User Interaction

| # | Actor | Action | FE Behavior | API |
|---|---|---|---|---|
| 1 | Chủ xe | Mở `/quotes/new?...` | Spinner "Đang lập báo giá" → `POST /quotes` → `replace` sang `/quotes/:id` | QT-01 |
| 2 | Chủ xe | "Gửi xưởng duyệt" | Hộp xác nhận "Gửi báo giá cho {xưởng}?" → `POST /submit` | QT-04 |
| 3 | Chủ xe | "Xoá nháp" | Hộp xác nhận → `DELETE` → `/quotes` | QT-05 |
| 4 | Chủ xe | Mở chi tiết đã có kết quả | `GET` (backend ghi `result_seen_at`); làm mới badge Home | QT-03 |
| 5 | Chủ xưởng | Mở `/technician/quotes` | `GET` danh sách chờ duyệt | QT-11 |
| 6 | Chủ xưởng | Sửa giá, chọn thời hạn, "Duyệt" | Hộp xác nhận hiển thị tổng duyệt tạm tính → `POST /approve` | QT-12, QT-13 |
| 7 | Chủ xưởng | "Từ chối" | RejectDialog → `POST /reject` | QT-14 |

---

# 6. State Management

```ts
type QuoteDisplayStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'MODIFIED' | 'EXPIRED' | 'REJECTED';

interface QuoteReviewForm {
  prices: Record<string /* quoteItemId */, number | null>;  // null = giữ giá ước tính
  itemNotes: Record<string, string>;
  validityDays: number;          // default 7
  reviewerNote: string;
}
```

- Server state (React Query hoặc tương đương): `quotes`, `quote(id)`, `workshopQuotes(status)`; invalidate sau mọi mutation.
- Form duyệt giữ local; rời trang khi form bẩn ⇒ hỏi xác nhận.

---

# 7. API Integration & Error Mapping

| Code | Màn | FE |
|---|---|---|
| `QUOTE_ALREADY_PENDING` | SCR-1101 | Toast "Bạn đã gửi báo giá này" + điều hướng `details.pendingQuoteId` |
| `QUOTE_DRAFT_REFRESHED` | SCR-1101 | Tải lại chi tiết, banner "Giá đã được cập nhật theo bảng giá mới, vui lòng xem lại trước khi gửi" |
| `QUOTE_NOT_DRAFT` | SCR-1101 | Tải lại chi tiết |
| `NO_MAINTENANCE_RULE` | `/quotes/new` | Quay về `/estimate` với thông báo `NO_RULE` |
| `WORKSHOP_INACTIVE` | SCR-1101 | "Xưởng hiện không nhận khách" + nút chọn xưởng khác |
| `QUOTE_ALREADY_REVIEWED` | SCR-1112 | Toast "Báo giá đã được xử lý" + tải lại |
| `COVERED_ITEM_LOCKED` / `REVIEWER_NOTE_REQUIRED` | SCR-1112/1113 | Lỗi tại trường |
| `QUOTE_NOT_FOUND` | mọi màn | Trang "Không tìm thấy báo giá" |
| `401` | mọi màn | Về login tương ứng (`/` hoặc `/workshop/login`) |

---

# 8. Client-side Validation

| Field | Rule |
|---|---|
| Giá duyệt | Số nguyên ≥ 0; ≤ 1.000.000.000 |
| Thời hạn | 1–30 |
| Lý do từ chối | 10–500 ký tự |
| Ghi chú dòng | ≤ 255 |

---

# 9. Loading / Empty / Error States

- Loading: skeleton bảng dòng; nút mutation hiển thị spinner và disabled (chống bấm hai lần).
- Empty `/quotes`: "Bạn chưa có báo giá nào. Xem chi phí dự kiến để bắt đầu." + nút `/estimate`.
- Empty `/technician/quotes`: "Không có báo giá chờ duyệt."

---

# 10. Navigation & Permission

| Route | Guard |
|---|---|
| `/quotes`, `/quotes/new`, `/quotes/:quoteId` | Chủ xe active |
| `/technician/quotes`, `/technician/quote-review` | Chủ xưởng đã onboarding |

`/technician/quote-review` không có `quoteId` ⇒ redirect `/technician/quotes`.

---

# 11. Analytics

| Event | Properties |
|---|---|
| `quote_draft_created` | `source = UI / CHAT`, `hasReferencePrice` |
| `quote_submitted` | `draftAgeHours` |
| `quote_reviewed` | `decision`, `modifiedLines`, `validityDays`, `waitingHours` (Portal) |
| `quote_used_for_booking` | — |

---

# 12. Acceptance Criteria (FE)

## AC-FE-1101 — Nhãn giá đúng trạng thái

**Given** báo giá `APPROVED` còn hạn **Then** nhãn "Báo giá đã duyệt — hiệu lực đến {dd/MM}", không có nhãn "Chi phí ước tính"; `DRAFT`/`PENDING_APPROVAL` luôn có "Chi phí ước tính".

## AC-FE-1102 — Portal không cho sửa dòng bảo hành

**Given** dòng `covered = true` **Then** không render ô nhập giá cho dòng đó.

## AC-FE-1103 — Lý do từ chối hiển thị nguyên văn

**Given** `REJECTED` với `reviewerNote` **Then** SCR-1102 hiển thị nguyên văn trong khối "Lý do từ chối".

## AC-FE-1104 — Không gửi hai lần

**Given** chủ xe bấm "Gửi xưởng duyệt" hai lần nhanh **Then** chỉ một request được gửi (nút disabled khi đang gửi, có `Idempotency-Key`).

---

# 13. Technical Notes

- Tách `features/quotes/` thành `api/`, `hooks/`, `components/`; xoá kiểu mock `ServiceItem` khi nối API.
- Tiền tệ: `Intl.NumberFormat('vi-VN')`; ngày: hiển thị theo `Asia/Ho_Chi_Minh`.
- Tổng duyệt phía FE chỉ là "tạm tính"; sau khi duyệt, hiển thị `approvedTotal` từ response.

# 14. Open Questions

| ID | Question |
|---|---|
| `Q-1102` | Có giữ nút thêm/xoá dịch vụ của mock ở Portal không? `[Đề xuất]` không trong MVP |
| `Q-FE-1101` | Chủ xe có cần màn so sánh báo giá của nhiều xưởng không? `[Đề xuất]` phase sau |

# 15. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu |
