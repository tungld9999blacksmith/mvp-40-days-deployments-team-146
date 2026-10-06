# Frontend Technical Specification — Hỏi thăm sau dịch vụ & phiếu hỗ trợ

> **Cập nhật phạm vi (02/10/2026):** các phần dưới đây trong tài liệu này không còn áp dụng.
>
> - Phiếu hỗ trợ (`support_ticket`): **đã bỏ**. Phản hồi hỏi thăm có vấn đề chỉ được phân loại và ghi trên `follow_up` (`has_issue`); app hiện lời khuyên an toàn và hotline xưởng, không tạo phiếu, không có màn phiếu cho chủ xe hay xưởng.
> - Kết nối Discord (`user_discord_link`, ENT-417): **đã bỏ**. Nhắc bảo dưỡng, nhắc lịch hẹn và hỏi thăm hiện trong mục **Thông báo** của app; danh sách kênh ngoài (Zalo / Telegram / SMS / Email) vẫn có nhưng đều "Sắp có", bật nhắc không bắt buộc chọn kênh.

> Đặc tả frontend cho Feature `FEAT-CRM-001` (PRD F9, US-041 → US-044).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-041-sprint-4-spec.ff.md) · **API:** [API Spec](../api/us-041-sprint-4-spec.api.md) · **Entity:** [Entity Spec](../entity/us-041-sprint-4-spec.entity.md)
>
> **Phạm vi FE:** phía **chủ xe** (mobile-first) — form hỏi thăm (SCR-901), danh sách và chi tiết phiếu hỗ trợ (SCR-902, SCR-903); phía **chủ xưởng** (Portal, desktop-first) — danh sách và chi tiết phiếu (SCR-904, SCR-905). Gửi hỏi thăm, tự đóng, phân loại AI chạy ở backend.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-CRM-001` — Hỏi thăm sau dịch vụ & phiếu hỗ trợ |
| Screen | `SCR-901` Hỏi thăm · `SCR-902` Phiếu của tôi · `SCR-903` Chi tiết phiếu (chủ xe) · `SCR-904` Phiếu hỗ trợ (Portal) · `SCR-905` Chi tiết phiếu (Portal) |
| Route | `/follow-ups/:followUpId` · `/support-tickets` · `/support-tickets/:ticketId` · `/technician/tickets` · `/technician/tickets/:ticketId` |
| Version | `v1.1` |
| Author | Team 4 Người |
| FE Owner | `[Cần phân công]` — F9 chưa có trong bảng phân công (`chucnang.md`) |
| Status | `Draft` |
| Related PRD | [PRD_EV_Care_MVP.md §F9](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-041-sprint-4-spec.ff.md#7-user-flow) |
| Related API | [API-FU-01 → API-FU-07](../api/us-041-sprint-4-spec.api.md) |
| Last Updated | `2026-09-29` |

---

# 2. Screen Overview

## 2.1 Purpose

- **Chủ xe:** trả lời hỏi thăm trong vài giây (chấm sao + nhận xét), biết ngay vấn đề đã được chuyển xưởng, theo dõi phiếu tới khi giải quyết.
- **Chủ xưởng:** thấy phiếu khẩn trước, đọc phản hồi gốc + tóm tắt, nhận xử lý, ghi chú khi giải quyết.

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Link trong tin Discord | Chủ xe bấm `{FRONTEND_URL}/follow-ups/{id}` | SCR-901 (đăng nhập trước nếu cần) |
| Chi tiết lịch hẹn `COMPLETED` (us-033 SCR-701) | Có hỏi thăm `SENT` còn hạn | Nút `Đánh giá dịch vụ` ⇒ SCR-901 |
| SCR-901 sau khi tạo phiếu | | `Xem phiếu hỗ trợ` ⇒ SCR-903 |
| Menu tài khoản chủ xe | | `Phiếu hỗ trợ` ⇒ SCR-902 |
| Sidebar Portal | Chủ xưởng | `Phiếu hỗ trợ` (badge số phiếu `OPEN`) ⇒ SCR-904 |
| Board chi tiết lịch hẹn (us-037 SCR-802) | Booking có phiếu | `Phiếu hỗ trợ` ⇒ SCR-905 |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| Gửi đánh giá xong (không vấn đề) | Ở lại SCR-901 trạng thái cảm ơn; `Về trang chủ` |
| Gửi xong có phiếu | SCR-901 trạng thái "Đã chuyển xưởng" + `Xem phiếu hỗ trợ` |
| `401` | Login (giữ `returnTo`) |

## 2.4 Preconditions

- Chủ xe/chủ xưởng đã đăng nhập, onboarding xong.
- Quyền sở hữu do backend kiểm tra (FF BR-911).

---

# 3. UI Structure

## 3.1 Layout

```text
SCR-901 Hỏi thăm (/follow-ups/:id)           — mobile-first
├── Header "Đánh giá dịch vụ"
├── ServiceSummary (xưởng, ngày, mã lịch hẹn)
├── Question (câu hỏi từ API)
├── StarRating (1–5, bắt buộc)
├── CommentBox (tuỳ chọn, 0/1000)
├── [Gửi đánh giá]
└── ResultPanel (sau khi gửi / khi đã trả lời / khi đã đóng)
    ├── ThankYou | IssueForwarded (+ Xem phiếu hỗ trợ)
    └── SafetyAlert (khi safetyAdvice)

SCR-902 Phiếu của tôi (/support-tickets)
├── StatusTabs [Đang xử lý] [Đã giải quyết]
└── TicketCard[]: tóm tắt · xưởng · ngày dịch vụ · trạng thái · cập nhật lúc

SCR-903 Chi tiết phiếu (/support-tickets/:id)
├── StatusStepper (Đã tiếp nhận → Đang xử lý → Đã giải quyết)
├── IssueSummary + YourFeedback (sao + nhận xét)
├── WorkshopContact (tên, hotline — nút gọi)
└── ResolutionNote (khi RESOLVED)

SCR-904 Phiếu hỗ trợ (/technician/tickets)      — desktop-first
├── SummaryCards (Mới · Đang xử lý · Đã giải quyết · Khẩn đang mở)
├── Filters (trạng thái, ưu tiên)
└── TicketTable: ưu tiên · tóm tắt · sao · khách · xe · mã lịch hẹn · tạo lúc (tuổi phiếu) · trạng thái

SCR-905 Chi tiết phiếu (/technician/tickets/:id) — drawer trên desktop
├── PriorityBadge (Khẩn — an toàn | Bình thường)
├── IssueSummary
├── CustomerFeedback (sao, nhận xét gốc, thời điểm)
├── ClassificationInfo (ý định, độ tin cậy, cách phân loại) — chữ nhỏ
├── BookingInfo (mã, ngày, khung, chi phí thực tế) + link Board
├── CustomerVehicle (tên, SĐT — nút gọi, model, biển số)
├── ActionPanel [Nhận xử lý] [Đã giải quyết]
└── ResolveDialog (ghi chú bắt buộc — "Khách sẽ đọc được ghi chú này")
```

## 3.2 Screen Layout Notes

- SCR-901 phải dùng tốt trên trình duyệt điện thoại mở từ Discord; nút gửi dính đáy.
- SCR-904 sắp xếp theo API (khẩn trước, cũ trước) — FE không tự sắp lại.

---

# 4. Component Specification

## 4.1 StarRating

| Property | Value |
|---|---|
| Component | `StarRating` |
| Required | Yes |
| Values | 1..5 |
| Labels | 1 `Rất tệ` · 2 `Chưa tốt` · 3 `Bình thường` · 4 `Tốt` · 5 `Rất tốt` |

- Chạm để chọn; hỗ trợ bàn phím (mũi tên trái/phải).
- Chọn 1–2 sao ⇒ placeholder ô nhận xét đổi thành `Bạn gặp vấn đề gì? Mô tả giúp xưởng nhé.` (gợi ý, không bắt buộc).

## 4.2 CommentBox

| Property | Value |
|---|---|
| Component | `TextArea` |
| Required | No |
| Max Length | 1000 (bộ đếm) |
| Placeholder | `Chia sẻ thêm về trải nghiệm của bạn (không bắt buộc)` |

## 4.3 Submit Button

| Property | Value |
|---|---|
| Label | `Gửi đánh giá` |
| Enabled When | Đã chọn sao ∧ `canRespond` |
| Loading | Disabled + spinner + `Đang gửi…` (có thể tới ~6 s do phân loại) |

## 4.4 ResultPanel

| Tình huống (từ API) | Nội dung |
|---|---|
| `outcome.hasIssue = false` | `outcome.message` (cảm ơn) + `Về trang chủ` |
| `outcome.hasIssue = true` | `outcome.message` ("Đã chuyển xưởng…") + `Xem phiếu hỗ trợ` (SCR-903) |
| `outcome.safetyAdvice = true` | `SafetyAlert` (nền vàng, icon cảnh báo) với `safetyMessage` + nút `Gọi xưởng` (`tel:` hotline) — hiển thị **trên cùng** |
| `status = PENDING` | `Chưa tới lúc đánh giá. Bạn sẽ nhận lời mời sau khi dịch vụ hoàn tất.` |
| `status = CLOSED`, `NO_RESPONSE` / `409 FOLLOW_UP_CLOSED` | `Khảo sát đã đóng. Nếu xe có vấn đề, vui lòng liên hệ xưởng {tên} — {hotline}.` + nút gọi |
| Đã trả lời trước đó | Hiển thị lại sao + nhận xét đã gửi (chỉ đọc) + kết quả |

Nội dung văn bản lấy từ API (`message`, `safetyMessage`) — FE không tự soạn để giữ đúng BR-912.

## 4.5 TicketCard / TicketTable

- Chủ xe: trạng thái hiển thị `Đã tiếp nhận` (`OPEN`), `Đang xử lý` (`IN_PROGRESS`), `Đã giải quyết` (`RESOLVED`); **không** hiển thị ưu tiên.
- Chủ xưởng: cột ưu tiên với badge `Khẩn` (đỏ + icon) cho `HIGH`; cột "tuổi phiếu" (`2 giờ trước`, `1 ngày trước`).

## 4.6 ActionPanel & ResolveDialog (SCR-905)

| Action | Nút | Xác nhận | API |
|---|---|---|---|
| `START` | `Nhận xử lý` | Không | FU-07 |
| `RESOLVE` | `Đã giải quyết` | `ResolveDialog` | FU-07 |

`ResolveDialog`:

```text
Đánh dấu đã giải quyết
Ghi chú xử lý (bắt buộc) — khách sẽ đọc được
[______________________________________]  0/1000
[Huỷ]   [Xác nhận]
```

Gửi `expectedStatus = ticket.status` hiện tại.

---

# 5. User Interaction

## 5.1 Interaction Flow

```text
Chủ xe:
Mở link → (Login) → GET follow-up
  ├── canRespond → chọn sao (+ nhận xét) → POST response → ResultPanel
  └── !canRespond → ResultPanel tương ứng (chưa mở / đã đóng / đã trả lời)

Chủ xưởng:
Sidebar Phiếu hỗ trợ → GET tickets (mặc định OPEN + IN_PROGRESS)
  → mở phiếu → Nhận xử lý → Đã giải quyết (+ ghi chú)
```

## 5.2 Interaction Table

| User Action | Frontend Behavior | Result |
|---|---|---|
| Chọn sao | Cập nhật state, bật nút gửi | |
| Gửi đánh giá | FU-02; khoá form | ResultPanel |
| `409 FOLLOW_UP_ALREADY_RESPONDED` | Tải lại FU-01 | Hiện kết quả cũ |
| Bấm `Gọi xưởng` | Mở `tel:` | Gọi điện |
| Chủ xưởng `Nhận xử lý` | FU-07 START | Trạng thái `Đang xử lý` |
| Chủ xưởng `Đã giải quyết` | Mở dialog → FU-07 RESOLVE | `Đã giải quyết` |

---

# 6. State Management

## 6.1 State Model

```text
FollowUpState (SCR-901)
├── followUp (FU-01)
├── form: { rating: 1..5 | null, comment }
├── result: outcome | null
└── request: { isLoading, isSubmitting, error }

MyTicketsState (SCR-902/903)
├── tab: 'active' | 'resolved'
├── items[], nextCursor
├── detail
└── request

WorkshopTicketsState (SCR-904/905)
├── filters: { statuses[], priority }
├── summary, items[], nextCursor
├── selectedTicketId, detail
├── resolveDialog: { isOpen, note }
└── request: { isLoading, pendingAction, error }
```

## 6.2 State Fields (chính)

| State | Type | Default | Description |
|---|---|---|---|
| `form.rating` | `number \| null` | `null` | Bắt buộc trước khi gửi |
| `form.comment` | `string` | `""` | ≤ 1000 |
| `isSubmitting` | `boolean` | `false` | Chặn gửi lặp |
| `filters.statuses` | `TicketStatus[]` | `['OPEN','IN_PROGRESS']` | Portal |
| `resolveDialog.note` | `string` | `""` | Bắt buộc 1..1000 |

`useReducer` cục bộ từng trang.

---

# 7. API Integration

## 7.1 Hỏi thăm — `API-FU-01` / `API-FU-02`

```http
GET  /api/v1/follow-ups/{followUpId}
POST /api/v1/follow-ups/{followUpId}/response
```

```json
{ "rating": "{form.rating}", "comment": "{form.comment | null}" }
```

Success FU-02 ⇒ `result = data.outcome`, khoá form.

## 7.2 Phiếu của chủ xe — `API-FU-03` / `API-FU-04`

```http
GET /api/v1/support-tickets?status=OPEN&status=IN_PROGRESS&limit=20
GET /api/v1/support-tickets/{ticketId}
```

Tab `Đang xử lý` = `OPEN` + `IN_PROGRESS`; tab `Đã giải quyết` = `RESOLVED`. Phân trang "Xem thêm" theo `nextCursor`.

## 7.3 Portal — `API-FU-05` / `API-FU-06` / `API-FU-07`

```http
GET  /api/v1/workshop-owner/support-tickets?status=OPEN&status=IN_PROGRESS
GET  /api/v1/workshop-owner/support-tickets/{ticketId}
POST /api/v1/workshop-owner/support-tickets/{ticketId}/transitions
```

```json
{ "action": "RESOLVE", "expectedStatus": "{detail.status}", "resolutionNote": "{note}" }
```

Success ⇒ cập nhật dòng + detail + `summary` cục bộ; badge sidebar giảm.

---

# 8. Client-side Validation

## 8.1 Validation Rules

| Field | Rule | Error Message |
|---|---|---|
| Sao | Bắt buộc | `Vui lòng chọn số sao.` |
| Nhận xét | ≤ 1000 | Chặn nhập, bộ đếm |
| Ghi chú xử lý | Bắt buộc, 1..1000 sau trim | `Vui lòng nhập ghi chú xử lý.` |

## 8.2 Validation Timing

Khi bấm gửi / xác nhận; không gọi API khi lỗi.

---

# 9. Loading States

- SCR-901: skeleton câu hỏi + sao; khi gửi: nút `Đang gửi…` — **không** timeout ở FE dưới 10 s (backend có thể mất ~6 s).
- SCR-902/904: skeleton 3 thẻ / 5 dòng.
- SCR-905: spinner trên nút đang thao tác; nút khác disable.

---

# 10. Empty States

| Điều kiện | Nội dung |
|---|---|
| Chủ xe chưa có phiếu | `Bạn chưa có phiếu hỗ trợ nào. Khi bạn báo vấn đề sau dịch vụ, phiếu sẽ hiện ở đây.` |
| Chủ xưởng không có phiếu đang mở | `Không có phiếu nào cần xử lý.` |

---

# 11. Error States

## 11.1 General Error

```text
Không thể tải dữ liệu.
Vui lòng thử lại.

[Thử lại]
```

## 11.2 Error Mapping

| HTTP Status / Error Code | Frontend Behavior |
|---|---|
| `401` / `SESSION_REVOKED` | Login, `returnTo` |
| `403 ONBOARDING_REQUIRED` | Onboarding |
| `404 FOLLOW_UP_NOT_FOUND` / `SUPPORT_TICKET_NOT_FOUND` | Màn "Không tìm thấy" + `Về trang chủ` |
| `409 FOLLOW_UP_NOT_OPEN` | ResultPanel "Chưa tới lúc đánh giá" |
| `409 FOLLOW_UP_ALREADY_RESPONDED` | Tải lại FU-01, hiện kết quả cũ |
| `409 FOLLOW_UP_CLOSED` | ResultPanel "Khảo sát đã đóng" với `details.workshopHotline` |
| `409 INVALID_STATUS_TRANSITION` | Toast `Phiếu vừa được cập nhật.` + tải lại FU-06 |
| `400 RESOLUTION_NOTE_REQUIRED` | Lỗi dưới ô ghi chú |
| `500` / `503` | Toast `Tạm thời chưa gửi được, bạn thử lại nhé.`; **giữ** sao + nhận xét / ghi chú đã nhập |

---

# 12. Error Handling

## 12.1 Field-level Error

Sao, nhận xét, ghi chú xử lý.

## 12.2 Screen-level Error

Tải FU-01/03/05 lỗi ⇒ General Error.

## 12.3 Retry Behavior

Giữ dữ liệu đã nhập; retry chỉ request lỗi. FU-02 an toàn khi retry (backend chỉ nhận một phản hồi).

---

# 13. Navigation

## 13.1 Routes

| Route | Purpose | Layout |
|---|---|---|
| `/follow-ups/:followUpId` | SCR-901 | Chủ xe |
| `/support-tickets` | SCR-902 | Chủ xe |
| `/support-tickets/:ticketId` | SCR-903 | Chủ xe |
| `/technician/tickets` | SCR-904 | Portal |
| `/technician/tickets/:ticketId` | SCR-905 (drawer) | Portal |

Thêm vào `frontend/src/app/App.tsx`; mục sidebar Portal `Phiếu hỗ trợ` kèm badge `summary.OPEN`.

## 13.2 Navigation Rules

- Deep link chưa đăng nhập ⇒ Login ⇒ quay lại đúng route.
- Back từ SCR-901 mở từ Discord (không history) ⇒ `/dashboard`.
- Mở/đóng drawer SCR-905 đổi URL.

---

# 14. Permission / Visibility

| UI Element | Condition |
|---|---|
| SCR-901 → 903 | Vai trò chủ xe |
| SCR-904 → 905 | Vai trò chủ xưởng |
| Ưu tiên, thông tin phân loại | Chỉ Portal |
| SĐT khách | Chỉ SCR-905 |
| Nút `Nhận xử lý` / `Đã giải quyết` | Theo `allowedActions` |

## 14.1 Role-based Behavior

| Role | Access |
|---|---|
| Chủ xe | Hỏi thăm + phiếu của mình (chỉ đọc phiếu) |
| Chủ xưởng | Phiếu của xưởng mình, chuyển trạng thái |

> Chỉ để hiển thị; backend quyết định.

---

# 15. Responsive / Device Behavior

## Mobile

- SCR-901/902/903: một cột; sao lớn (≥ 44px); nút gửi dính đáy.
- SCR-904/905 trên mobile: danh sách thẻ, chi tiết trang riêng.

## Tablet / Desktop

- SCR-901 giới hạn 560px, căn giữa.
- SCR-904 bảng; SCR-905 drawer 480px.

---

# 16. Accessibility

- `StarRating` là `radiogroup` với nhãn từng mức; không chỉ dùng màu vàng để thể hiện đã chọn.
- `SafetyAlert` có `role="alert"`.
- Badge `Khẩn` có chữ, không chỉ màu đỏ.
- Dialog: focus vào ô ghi chú; Esc đóng khi không đang gửi.

---

# 17. Analytics / Tracking

| Event | Trigger | Properties |
|---|---|---|
| `follow_up_viewed` | Mở SCR-901 | `status`, `canRespond`, `source` (`discord`/`app`) |
| `follow_up_submitted` | FU-02 thành công | `rating`, `hasComment`, `hasIssue`, `safetyAdvice` |
| `follow_up_submit_failed` | FU-02 lỗi | `errorCode` |
| `support_ticket_viewed` | Mở SCR-903 / SCR-905 | `role`, `status` |
| `support_ticket_transition` | FU-07 thành công | `action`, `priority` |

Không gửi nội dung nhận xét / ghi chú / tên / SĐT / biển số.

---

# 18. Acceptance Criteria

## AC-FE-901 — Gửi đánh giá hài lòng (FF AC-903)

**Given** hỏi thăm `SENT` còn hạn

**When** chọn 5 sao, không nhận xét, bấm `Gửi đánh giá`

**Then** gọi FU-02 một lần; hiện lời cảm ơn; form bị khoá.

## AC-FE-902 — Có vấn đề + an toàn (FF AC-904)

**Given** hỏi thăm `SENT`

**When** chọn 2 sao, nhận xét "phanh trước kêu", gửi

**Then** `SafetyAlert` hiện trên cùng với nút `Gọi xưởng`; có nút `Xem phiếu hỗ trợ` dẫn tới SCR-903 trạng thái `Đã tiếp nhận`.

## AC-FE-903 — Bắt buộc chọn sao

**Given** chưa chọn sao

**When** bấm gửi

**Then** không gọi API; hiện `Vui lòng chọn số sao.`

## AC-FE-904 — Khảo sát đã đóng (FF AC-905)

**Given** hỏi thăm `CLOSED` / `NO_RESPONSE`

**When** mở link

**Then** không có form; hiện "Khảo sát đã đóng" + hotline xưởng.

## AC-FE-905 — Chủ xe không thấy ưu tiên (FF BR-911)

**Given** phiếu `priority = HIGH`

**When** chủ xe mở SCR-903

**Then** không có nhãn ưu tiên hay thông tin phân loại.

## AC-FE-906 — Chủ xưởng giải quyết phiếu (FF AC-908, AC-909)

**Given** phiếu `IN_PROGRESS`

**When** bấm `Đã giải quyết` rồi `Xác nhận` với ô ghi chú trống

**Then** không gọi API, hiện lỗi; nhập ghi chú rồi xác nhận ⇒ phiếu `Đã giải quyết`, badge sidebar giảm.

## AC-FE-907 — Khẩn lên đầu

**Given** có phiếu `HIGH` và `NORMAL` cùng mở

**When** mở SCR-904

**Then** phiếu `HIGH` hiển thị trước với badge `Khẩn`.

---

# 19. Technical Notes

## Frontend Stack

```text
Framework: React 19 + Vite
Language: TypeScript
State Management: useReducer cục bộ trong trang
Networking: fetch qua shared/api/client.ts
Navigation: React Router 7
UI Library: Tailwind CSS 4 + lucide-react
```

## Component Structure

```text
frontend/src/features/after-service/
├── pages/
│   ├── FollowUp.tsx               (SCR-901)
│   ├── MySupportTickets.tsx       (SCR-902)
│   ├── MySupportTicketDetail.tsx  (SCR-903)
│   ├── WorkshopTickets.tsx        (SCR-904 + drawer SCR-905)
│   └── WorkshopTicketDetailPage.tsx (SCR-905 mobile)
├── components/
│   ├── StarRating.tsx · CommentBox.tsx · ResultPanel.tsx · SafetyAlert.tsx
│   ├── TicketCard.tsx · TicketStatusStepper.tsx
│   └── TicketTable.tsx · TicketActionPanel.tsx · ResolveDialog.tsx
├── api.ts
├── labels.ts
└── types.ts
```

## Implementation Notes

- Nút `Đánh giá dịch vụ` trên SCR-701 (us-033) cần API-BR-01 trả thêm `followUp { followUpId, canRespond }` khi booking `COMPLETED` — `[Đề xuất]` bổ sung vào us-033 API v1.1.
- Mock trong `frontend/src/mocks/` giữ đúng shape API cho tới khi backend sẵn sàng.
- Nhận xét của chủ xe và tóm tắt AI luôn render dạng **văn bản thuần** (escape HTML, không render markdown/link) trên Portal; tóm tắt có nhãn "Tóm tắt tự động" và luôn hiển thị kèm nhận xét gốc — nội dung chủ xe nhập được coi là dữ liệu, kể cả khi trông như lệnh cho AI (FF EF-906).

---

# 20. Open Questions

- [ ] FE owner cho F9.
- [ ] Bổ sung `followUp` vào response API-BR-01 (us-033) để hiện nút `Đánh giá dịch vụ`.
- [ ] Chủ xe có cần thông báo trong app (ngoài Discord) khi phiếu được giải quyết? — phụ thuộc API danh sách thông báo (`/notifications`, chưa có).

---

# 21. Truy vết FF → FE

Mã trong [FF us-041](../feature-functional/us-041-sprint-4-spec.ff.md). "Backend" = job/nghiệp vụ không có UI riêng.

| FF | Nội dung | FE |
|---|---|---|
| UC-902, BR-905, AC-903 | Chủ xe phản hồi (1–5 sao bắt buộc, nhận xét tuỳ chọn) | §4.1–4.3, AC-FE-901, AC-FE-903 |
| AF-901 | Phản hồi hài lòng | §4.4 ResultPanel |
| AF-902, BR-906, BR-907, AC-904 | Có vấn đề ⇒ phiếu hỗ trợ | §4.4, §2.2 (`Xem phiếu hỗ trợ`) |
| BR-908 | Ưu tiên an toàn, khuyến cáo trên màn cảm ơn | §4.4, AC-FE-902, AC-FE-907 (Portal: khẩn lên đầu) |
| AF-903 | Mở hỏi thăm từ app (không qua Discord) | §2.2 (nút trên chi tiết lịch hẹn `COMPLETED`), §19 |
| EF-902, BR-909, UC-905, AC-905 | Quá 72 giờ / tự đóng | §4.4, §11.2 `FOLLOW_UP_CLOSED`, AC-FE-904 |
| EF-903, AC-906 | Gửi hai lần | §5.2, §11.2 `FOLLOW_UP_ALREADY_RESPONDED` |
| UC-904, BR-910, AC-908, AC-909 | Chủ xưởng xử lý phiếu | §4.5, §4.6, AC-FE-906 |
| EF-905 | Phiếu đã đổi trạng thái | §11.2 `INVALID_STATUS_TRANSITION` |
| BR-911, BR-912, AC-910 | Chủ xe không thấy ưu tiên; phân quyền phiếu | §4.5, AC-FE-905, §11.2 `*_NOT_FOUND` |
| EF-906 | Prompt injection trong nhận xét | §19 (render văn bản thuần, nhãn "Tóm tắt tự động") |
| UC-901, UC-903, BR-901–904, AF-904, EF-901, EF-904, AC-901/902/907 | Tạo, hẹn giờ, gửi hỏi thăm; phân loại AI, lỗi AI không bỏ sót | Backend |

# 22. Related Documents

- Functional Spec: [us-041-sprint-4-spec.ff.md](../feature-functional/us-041-sprint-4-spec.ff.md)
- API Spec: [us-041-sprint-4-spec.api.md](../api/us-041-sprint-4-spec.api.md)
- Entity Spec: [us-041-sprint-4-spec.entity.md](../entity/us-041-sprint-4-spec.entity.md)
- us-033 FE (chi tiết lịch hẹn): [us-033-sprint-3-spec.fe.md](../../sprint-3/frontend/us-033-sprint-3-spec.fe.md)
- us-037 FE (Workshop Board): [us-037-sprint-3-spec.fe.md](../../sprint-3/frontend/us-037-sprint-3-spec.fe.md)
- Design / Figma: `[Chưa có]`

---

# 23. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Team 4 Người | Initial version: SCR-901 → SCR-905 |
| `v1.1` | `2026-10-01` | Team 4 Người | Đối chiếu FF: render nhận xét/tóm tắt dạng văn bản thuần (EF-906), bảng truy vết FF → FE |
