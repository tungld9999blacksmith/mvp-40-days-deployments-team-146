# Frontend Technical Specification — Báo giá có chủ xưởng duyệt (HITL)

> **Đã loại khỏi phạm vi (02/10/2026).** Chức năng báo giá có chủ xưởng duyệt (F5b, us-049, AI-005) đã bị bỏ khỏi sản phẩm: code backend/frontend đã gỡ, bảng `quote`, `quote_item` được xoá bởi migration `backend/alembic/versions/a3c7e9f1b2d4_drop_quote_support_ticket_discord.py`. Tài liệu giữ lại để tham khảo lịch sử, **không dùng để triển khai**.

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
| Version | `v1.1` |
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
| Chủ xe "Đặt lịch với báo giá này" (chỉ khi `canAttachToBooking = true`) | `/booking?workshopId&odoMilestone&quoteId` (us-029 FE) — luôn kèm đúng `workshopId` của báo giá |
| Chủ xe "Đặt lịch không kèm báo giá" (báo giá `EXPIRED`) | `/booking?workshopId&odoMilestone` (FF AF-1104) |
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
│ EXPIRED:  [Đặt lịch không kèm báo giá]│
│           [Lập báo giá mới]          │
│ REJECTED: [Lập báo giá mới]          │
└─────────────────────────────────────┘
```

### Quy tắc hiển thị SCR-1102 (FF BR-1106, BR-1108, BR-1111, BR-1112, EF-1103)

| Điều kiện | Hiển thị |
|---|---|
| `DRAFT` | Dòng phụ "Nháp chưa gửi sẽ tự xoá sau 7 ngày" (`QUOTE_DRAFT_TTL_DAYS`); nhãn "Chi phí ước tính" |
| `PENDING_APPROVAL` | "Chờ xưởng duyệt" + thời điểm gửi; nhãn "Chi phí ước tính" |
| `APPROVED` / `MODIFIED`, `canAttachToBooking = true` | Nút "Đặt lịch với báo giá này"; nhãn "Báo giá đã duyệt — hiệu lực đến {dd/MM}" |
| `APPROVED` / `MODIFIED`, đã gắn booking đang mở (`bookingId` ≠ null, `canAttachToBooking = false`) | Ẩn nút đặt lịch; dòng "Đã dùng cho lịch hẹn" + link `/bookings/:bookingId` |
| `EXPIRED` | "Đã hết hiệu lực"; hai nút §3.1 (đặt lịch không kèm / lập mới). Không có lựa chọn gắn vào booking |
| `REJECTED` | Khối "Lý do từ chối" nguyên văn `reviewerNote` + "Lập báo giá mới" ⇒ `/estimate?odoMilestone` (có thể chọn xưởng khác — FF AF-1103) |
| Xưởng ngừng hoạt động khi đang chờ | Ghi chú "Xưởng hiện không nhận khách" `[Đề xuất — cần API trả trạng thái xưởng, Q-FE-1102]`; hiện tại chỉ biết qua lỗi `WORKSHOP_INACTIVE` khi gửi |

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
- Nháp được lập hoàn toàn ở backend từ dự toán F5: `POST /quotes` chỉ gửi `userVehicleId`, `workshopId`, `odoMilestone` — **không** gửi dòng/giá (FF BR-1101, AC-1104).
- Báo giá chỉ dùng được cho **đúng xưởng** của nó (FF BR-1108, AF-1105): trong luồng đặt lịch us-029, nếu chủ xe "Đổi xưởng" khác `workshopId` của báo giá thì FE bỏ `quoteId` khỏi query và thẻ tóm tắt hiển thị "Chi phí ước tính" của xưởng mới.
- Gửi duyệt qua chat chỉ khi chủ xe bấm nút trên `CARD-QUOTE` (sự kiện xác nhận kèm `confirmation_token`); câu trả lời mơ hồ không gửi (FF BR-1103, AC-1103).

# 14. Truy vết FF → FE

| FF | Nội dung | FE |
|---|---|---|
| UC-1101, BR-1101, BR-1102, AC-1104 | Lập nháp từ dự toán ở backend | §2.2, §5 #1, §13 |
| BR-1103, AF-1101, AC-1103 | Gửi duyệt cần xác nhận rõ (UI / chat) | §5 #2, §4.5, §13 |
| BR-1104, EF-1101, AC-1107 | Không trùng báo giá chờ | §7 `QUOTE_ALREADY_PENDING`, AC-FE-1104 |
| EF-1104 | Giá đổi giữa lúc lập và lúc gửi | §7 `QUOTE_DRAFT_REFRESHED` |
| UC-1102, AF-1102, BR-1105, AC-1105 | Duyệt / sửa giá dòng tính phí, tổng do backend tính | §3.2, §4.2, §4.3, §13 |
| UC-1103, BR-1107, AC-1102 | Từ chối cần lý do, hiển thị nguyên văn | §4.4, §3.1 (quy tắc hiển thị), AC-FE-1103 |
| BR-1106, AF-1104 | Thời hạn hiệu lực, hết hạn | §3.2 (chọn 1–30 ngày), quy tắc hiển thị `EXPIRED` |
| UC-1104, BR-1108, AC-1101, AF-1105 | Gắn báo giá vào booking | §2.3, quy tắc hiển thị (`canAttachToBooking`), §13 |
| AF-1103 | Bị từ chối, lập lại | §2.3, quy tắc hiển thị `REJECTED` |
| BR-1109 | Thông báo kết quả (badge Home, chat) | §2.2 (badge `unseenResult`), §5 #4 |
| BR-1110, AC-1106 | Chủ xưởng chỉ thấy xưởng mình | §7 `QUOTE_NOT_FOUND` |
| BR-1111 | Nhãn chi phí | AC-FE-1101 |
| BR-1112 | Dọn nháp | Quy tắc hiển thị `DRAFT` |
| EF-1102 | Hai tab cùng duyệt | §7 `QUOTE_ALREADY_REVIEWED` |
| EF-1103 | Xưởng ngừng hoạt động | §7 `WORKSHOP_INACTIVE`, quy tắc hiển thị, Q-FE-1102 |

# 15. Open Questions

| ID | Question |
|---|---|
| `Q-1102` | Có giữ nút thêm/xoá dịch vụ của mock ở Portal không? `[Đề xuất]` không trong MVP |
| `Q-FE-1101` | Chủ xe có cần màn so sánh báo giá của nhiều xưởng không? `[Đề xuất]` phase sau |
| `Q-FE-1102` | `API-QT-03` có trả trạng thái xưởng (`workshopActive`) để hiện "Xưởng hiện không nhận khách" trên báo giá đang chờ (FF EF-1103)? |

# 16. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu |
| `v1.1` | `2026-10-01` | Team 4 Người | Đối chiếu FF: quy tắc hiển thị theo trạng thái (đã gắn booking, hết hạn có "Đặt lịch không kèm báo giá", nháp tự xoá, xưởng ngừng hoạt động), chỉ dùng báo giá đúng xưởng, bảng truy vết FF → FE, Q-FE-1102 |
