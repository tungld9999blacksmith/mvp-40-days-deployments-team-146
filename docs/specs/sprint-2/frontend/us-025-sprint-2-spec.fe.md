# Frontend Technical Specification — Chat RAG có trích nguồn & lưu trữ hội thoại

> **Cập nhật phạm vi (02/10/2026):** các phần dưới đây trong tài liệu này không còn áp dụng.
>
> - Báo giá / duyệt báo giá (`quote`, `quote_item`, us-049): **đã bỏ**. Đặt lịch không gắn báo giá; mọi con số chi phí là ước tính (F5), chi phí cuối cùng do xưởng xác nhận khi kiểm tra xe.

> Đặc tả frontend cho Feature `FEAT-CHAT-001` (PRD F4, US-025 → US-029).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-025-sprint-2-spec.ff.md) · **API:** [API Spec F4](../api/us-025-sprint-2-spec.api.md) · [Nền tảng Conversation & Messaging](../../platform/conversation-messaging.api.md) · **Entity:** [Entity Spec](../entity/us-025-sprint-2-spec.entity.md)
>
> **Phạm vi FE:** màn chat của chủ xe (hỏi đáp streaming, trích dẫn, lịch sử, tìm kiếm, xoá) và panel "Đoạn hội thoại liên quan" chỉ đọc cho chủ xưởng. **Không** gồm nội dung thẻ dự toán (F5) và đặt lịch (F6) — spec này chỉ chừa chỗ hiển thị `card`. US-030 (xuất ẩn danh) là script nội bộ, không có UI.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-CHAT-001` — Chat RAG có trích nguồn & lưu trữ hội thoại |
| Screen | `SCR-601` Chat · `SCR-602` Lịch sử hội thoại · `SCR-603` Kết quả tìm kiếm · `SCR-604` Chi tiết nguồn · `SCR-605` Đoạn hội thoại liên quan (chủ xưởng) |
| Route | `/ai` · `/ai/:conversationId` · panel trong `/technician/quote-review` và chi tiết booking của xưởng |
| Version | `v1.0` |
| Author | Mai Văn Trung |
| FE Owner | Đinh Kim Thái |
| Status | `Draft` |
| Related PRD | [PRD_EV_Care_MVP.md §F4](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-025-sprint-2-spec.ff.md#7-user-flow) |
| Related API | [API-CHAT-001 → 008](../api/us-025-sprint-2-spec.api.md) · [API-CONV-001 → 005, API-MSG-001](../../platform/conversation-messaging.api.md) |
| Last Updated | `2026-09-29` |

---

# 2. Screen Overview

## 2.1 Purpose

- Chủ xe hỏi bằng tiếng Việt về bảo dưỡng, bảo hành, cách dùng xe; câu trả lời **hiện dần** (streaming) và luôn kèm **trích dẫn** tài liệu chính hãng khi có khẳng định kỹ thuật.
- Hệ thống đã biết xe của chủ xe → không hỏi lại model/ODO (FE không gửi thông tin xe).
- Đóng app mở lại vẫn thấy đủ lịch sử, tiếp tục đúng ngữ cảnh.
- Chủ xe xem danh sách, tìm và xoá hội thoại của mình.
- Chủ xưởng xem (chỉ đọc) đoạn hội thoại dẫn tới booking/báo giá của xưởng mình.

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Sidebar "AI Trợ lý" | Chủ xe `ACTIVE` | `/ai` → mở hội thoại gần nhất của xe |
| Quick action "Hỏi AI" / CTA "Hỏi AI về mốc này" trên Home | — | `/ai` (tuỳ chọn điền sẵn câu hỏi — mục 4.4) |
| Chọn hội thoại trong Lịch sử / kết quả tìm kiếm | — | `/ai/:conversationId` (cuộn tới tin nhắn nếu có `?messageSeq=`) |
| Chủ xưởng mở chi tiết báo giá / booking tạo từ chat | Có `source_message_id` | Panel SCR-605 |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| Nhấn trích dẫn | Drawer SCR-604 (không rời màn) |
| Nhấn "Lịch sử" | Drawer/panel SCR-602 |
| Thẻ F5/F6 trong tin nhắn (`card`) | Theo spec F5/F6 (`/estimate`, `/booking`) |
| `401` | Login |
| `403 ONBOARDING_REQUIRED` | Onboarding |
| `404 CONVERSATION_NOT_FOUND` | `/ai` (hội thoại gần nhất) + toast |

## 2.4 Preconditions

- Chủ xe `ACTIVE`, có xe `verified` + `active` (BR-601).
- Chủ xưởng (SCR-605): `ACTIVE`, booking/báo giá thuộc xưởng mình.

---

# 3. UI Structure

## 3.1 Layout

```text
SCR-601 Chat (/ai, /ai/:conversationId)            — trong AppLayout chủ xe
├── Chat Header
│   ├── Tiêu đề hội thoại (title hoặc "Cuộc trò chuyện mới")
│   ├── Button "Lịch sử" (mở SCR-602)
│   ├── Button "Cuộc trò chuyện mới"
│   └── Menu (⋯): "Xoá cuộc trò chuyện"
├── Message List (cuộn; cũ trên, mới dưới)
│   ├── Load-older sentinel (spinner khi tải tin cũ)
│   ├── UserBubble (phải)
│   │   └── Trạng thái: đang gửi · lỗi + "Gửi lại"
│   ├── AssistantBubble (trái)
│   │   ├── Nội dung (markdown an toàn: đoạn, danh sách, in đậm)
│   │   ├── StreamingCursor (khi đang stream)
│   │   ├── StageIndicator ("Đang tra cứu tài liệu...")
│   │   ├── CitationChips: [Sổ tay bảo dưỡng VF6 · v2.1 · tr.42] ...
│   │   ├── Card F5/F6 (nếu message.card) — placeholder
│   │   └── Thời gian
│   └── Empty State + Suggested Questions (khi chưa có tin)
├── Composer
│   ├── Textarea (auto-grow, tối đa 6 dòng)
│   ├── Bộ đếm ký tự (hiện khi > 1.800)
│   ├── Button "Gửi" / "Đang trả lời..." (disabled)
│   └── Helper lỗi (rate limit, busy)
└── Context Panel (phải, desktop)
    ├── Thông tin xe: model, biển số
    ├── Trạng thái bảo dưỡng: badge + còn km/ngày (từ API-VEH-003)
    └── Câu hỏi gợi ý

SCR-602 Lịch sử hội thoại (drawer trái trên desktop / full-screen trên mobile)
├── Search Input "Tìm trong lịch sử..."
├── Conversation List (title, lastMessagePreview, lastMessageAt)
│   └── Item actions: Mở · Xoá
└── Load more

SCR-603 Kết quả tìm kiếm (thay nội dung SCR-602 khi có từ khoá)
└── Result Item: conversationTitle · snippet (có <mark>) · thời gian

SCR-604 Chi tiết nguồn (drawer phải / bottom sheet)
├── Tên tài liệu
├── Loại tài liệu · Phiên bản · Trang
├── Đoạn trích (snippet)
└── Ghi chú: "Trích từ tài liệu chính hãng tại thời điểm trả lời."

SCR-605 Đoạn hội thoại liên quan (panel trong trang báo giá/booking của chủ xưởng)
├── Title "Hội thoại dẫn tới yêu cầu"
├── Message list chỉ đọc (user / assistant), highlight tin "xác nhận"
└── Ghi chú "Chỉ hiển thị tối đa 20 tin nhắn gần nhất trước khi khách xác nhận."
```

## 3.2 Screen Layout Notes

- Theo [wireframe.md §8](../../../design/wireframe.md): chat ở giữa, panel "Thông tin xe" bên phải.
- Tin user: bong bóng `bg-emerald/10`, căn phải. Tin assistant: `bg-card border border-border`, căn trái.
- Trích dẫn luôn nằm **ngay dưới** câu trả lời tương ứng, style chip `font-mono text-xs`, icon `FileText`, nhãn "Nguồn chính hãng" (wireframe §18: "AI recommendations phải luôn hiển thị nguồn tài liệu chính hãng").
- Tự cuộn xuống cuối khi có tin mới **chỉ khi** người dùng đang ở gần cuối (≤ 120 px); nếu đang đọc tin cũ, hiện nút `↓ Tin mới`.

---

# 4. Component Specification

## 4.1 Message List

| Property | Value |
|---|---|
| Component | `MessageList` |
| Data Source | `API-CONV-003` (lịch sử), SSE `API-CHAT-004` (lượt hiện tại), WebSocket `API-MSG-001` (thiết bị khác — tuỳ chọn) |
| Order | Theo `seq` tăng dần; loại trùng theo `id` |

### Behavior

- Mở hội thoại: tải 50 tin mới nhất (`limit=50`), đảo lại để hiển thị cũ → mới, cuộn xuống cuối (BR-604).
- Cuộn lên đỉnh (sentinel `IntersectionObserver`) và `hasMore = true` → tải `before = page.nextCursor`; **giữ nguyên vị trí cuộn** sau khi chèn tin cũ (AC-609).
- Tin nhận được từ bất kỳ nguồn nào đều qua hàm `mergeMessages()` — sắp theo `seq`, bỏ trùng theo `id` (platform §API-MSG-001.5).
- Tin `role` khác `user`/`assistant` → bỏ qua (API không trả `tool`).

---

## 4.2 Assistant Bubble

| Property | Value |
|---|---|
| Component | `AssistantMessage` |
| Props | `message: MessageDto \| StreamingDraft` |

### Nội dung

- Render markdown **an toàn** (không cho HTML thô): đoạn, danh sách, in đậm, xuống dòng. Không render link ngoài `[Đề xuất]`.
- Khi đang stream: nối `delta` vào `draft.text`, hiện con trỏ nhấp nháy.
- Khi nhận `message.completed`: **thay** draft bằng `message` chuẩn từ server (nội dung, `citations`, `refs`, `card`) — không dùng text ghép từ `token` làm bản cuối (API §4).

### StageIndicator (từ SSE `status`)

| `stage` | Hiển thị |
|---|---|
| `retrieving` | `Đang tra cứu tài liệu chính hãng...` |
| `calling_tool` | `Đang kiểm tra thông tin xe...` |
| `generating` | `Đang soạn câu trả lời...` |
| Chưa có `token` nào sau `message.accepted` | `Đang suy nghĩ...` |

Ẩn khi `token` đầu tiên tới.

### Citations

| Property | Value |
|---|---|
| Component | `CitationChip` |
| Hiển thị | `{title} · v{version}{pageNumber ? ' · tr.' + pageNumber : ''}` |
| Click | Mở SCR-604 với `CitationDto` |
| Rỗng | Không hiển thị khối trích dẫn (câu từ chối/xã giao — AC-602) |

### Card (F5/F6)

- `message.card != null` → render `MessageCard` theo `card.type` do spec F5/F6 định nghĩa. Loại chưa hỗ trợ → không render (không lỗi).
- Mọi con số chi phí trong chat luôn kèm nhãn `Chi phí ước tính` (FF §22) — thuộc spec F5.

---

## 4.3 User Bubble

| Trạng thái local | Hiển thị |
|---|---|
| `sending` (chưa có `message.accepted`) | Bong bóng mờ + spinner nhỏ |
| `sent` | Bình thường + thời gian |
| `failed` (lỗi trước khi luồng mở, hoặc mạng rớt) | Viền đỏ + `Chưa gửi được.` + nút `Gửi lại` |
| `unanswered` (đã lưu nhưng không có câu trả lời — EF-601/EF-602) | Bình thường + dòng `Trợ lý chưa trả lời.` + nút `Gửi lại` |

`Gửi lại` dùng **cùng `clientMessageId`** (BR-611, AC-611).

Phát hiện `unanswered` khi tải lịch sử: tin `user` cuối cùng của hội thoại không có tin `assistant` nào có `seq` lớn hơn, và không có lượt nào đang chạy ở client.

---

## 4.4 Composer

| Property | Value |
|---|---|
| Component | `ChatComposer` |
| Placeholder | `Hỏi về bảo dưỡng, bảo hành, cách dùng xe...` |
| Max Length | `2000` ký tự (`CHAT_MESSAGE_MAX_CHARS` — BR-614) |
| Submit | `Enter` gửi · `Shift+Enter` xuống dòng · nút `Gửi` |
| Disabled When | Đang có lượt chạy (`isStreaming`), xe không `active`, đang chờ rate limit |

### Behavior

1. Trim; rỗng → không gửi.
2. Vượt 2000 ký tự → không cho gửi, hiện lỗi (mục 8).
3. Chưa có hội thoại (AF-604): gọi `API-CONV-001` tạo trước, rồi gửi (API §14: giữ hai bước).
4. Sinh `clientMessageId = crypto.randomUUID()`, thêm tin user tạm (`sending`), xoá ô nhập.
5. Gọi `API-CHAT-004` (mục 7.4).

Điền sẵn: `/ai?q=...` (từ CTA Home) → đặt vào ô nhập, **không** tự gửi.

---

## 4.5 Context Panel

| Property | Value |
|---|---|
| Component | `ChatContextPanel` |
| Data Source | `API-VEH-001`, `API-VEH-003` ([US-017 FE](./us-017-sprint-2-spec.fe.md)) |
| Visibility | Desktop (≥ 1280px); mobile ẩn, mở bằng nút `Xe của tôi` ở header |

- Hiển thị model, biển số, `DueStatusBadge`, khoảng cách còn lại, ODO + thời điểm hãng cập nhật (dùng lại component của US-017).
- `UNKNOWN + OEM_DATA_NOT_SYNCED` → `Đang lấy dữ liệu từ hãng...` (EF-603).
- **Chỉ hiển thị** — không gửi dữ liệu này kèm tin nhắn (AC-603).

### Suggested Questions

Chip câu hỏi gợi ý (tĩnh ở FE `[Đề xuất]`): `Mốc bảo dưỡng tới của xe tôi cần làm gì?` · `Hạng mục nào được bảo hành miễn phí?` · `Chính sách bảo hành pin thế nào?` · `Bao lâu cần kiểm tra lốp?`. Nhấn chip → gửi ngay như tin nhắn.

---

## 4.6 Conversation History (SCR-602)

| Property | Value |
|---|---|
| Component | `ConversationHistoryDrawer` |
| Data Source | `API-CONV-002` (`userVehicleId`, `limit=20`, `cursor`) |

### Item

- `title ?? 'Cuộc trò chuyện'`, `lastMessagePreview` (1 dòng, cắt), `lastMessageAt` dạng tương đối (`Hôm nay 09:14`, `Hôm qua`, `28/09`).
- Hội thoại đang mở được highlight.
- Cuối danh sách: `Tải thêm` khi `page.hasMore`.

### Xoá hội thoại

1. Nhấn `Xoá` → dialog xác nhận:
   - Title: `Xoá cuộc trò chuyện này?`
   - Description: `Toàn bộ tin nhắn sẽ bị xoá vĩnh viễn và không thể khôi phục. Lịch hẹn hoặc báo giá đã tạo từ cuộc trò chuyện vẫn được giữ.` (BR-608)
   - Buttons: `Huỷ` · `Xoá` (danger)
2. Gọi `API-CONV-005`.
3. `204` → bỏ khỏi danh sách; nếu đang mở hội thoại đó → chuyển sang hội thoại gần nhất còn lại, hoặc trạng thái "Cuộc trò chuyện mới".
4. Đang stream mà xoá → huỷ `AbortController` của SSE trước khi gọi xoá (EDGE-605).

---

## 4.7 Search (SCR-603)

| Property | Value |
|---|---|
| Component | `ConversationSearch` |
| Data Source | `API-CONV-004` (`q`, `userVehicleId`, `limit=20`, `cursor`) |
| Min / Max | 2 / 100 ký tự sau trim |
| Debounce | 400 ms |

### Behavior

- `q` < 2 ký tự → hiện danh sách hội thoại (SCR-602) thay vì kết quả.
- Mỗi kết quả: `conversationTitle`, `snippet`, thời gian, nhãn vai trò (`Bạn` / `Trợ lý`).
- `snippet` có `<mark>`: backend đã escape HTML khác; FE vẫn **chỉ cho phép thẻ `<mark>`** khi render (sanitize whitelist).
- Nhấn kết quả → `/ai/{conversationId}?messageSeq={seq}` → tải tin quanh `seq` (`before = seq + 1`, `limit = 50`), cuộn tới và highlight tin đó 2 giây.
- Không phân biệt hoa thường, không dấu do backend xử lý (BR-615) — FE gửi nguyên chuỗi người dùng gõ.

---

## 4.8 Citation Detail (SCR-604)

| Field | Nguồn | Format |
|---|---|---|
| Tên tài liệu | `title` | Tiêu đề |
| Loại | `documentType` | `owner_manual` → Sách hướng dẫn sử dụng · `maintenance_manual` → Sổ tay bảo dưỡng · `warranty_policy` → Chính sách bảo hành · `service_bulletin` → Thông báo kỹ thuật |
| Phiên bản | `version` | `v{version}` |
| Trang | `pageNumber` | `Trang {n}`; null → ẩn |
| Đoạn trích | `snippet` | Trích dẫn dạng blockquote, text thuần |

Ghi chú cuối: `Trích từ tài liệu chính hãng tại thời điểm trả lời.` (BR-603, EDGE-609). Không có link tải tài liệu gốc (chưa có API).

---

## 4.9 Conversation Excerpt — chủ xưởng (SCR-605)

| Property | Value |
|---|---|
| Component | `ConversationExcerptPanel` |
| Props | `source: { type: 'booking' \| 'quote', id: string }` |
| Data Source | `API-CHAT-007` (booking) / `API-CHAT-008` (quote) |
| Nơi dùng | Trang duyệt báo giá `/technician/quote-review`; trang chi tiết booking của xưởng (khi có — F6/F8) |

### Behavior

- Hiển thị `messages[]` theo thứ tự trả về (cũ → mới), chỉ đọc, **không** có composer.
- Tin có `id = source.confirmedMessageId` được highlight với nhãn `Khách xác nhận`.
- Không có trích dẫn chi tiết, không có tin tool (backend đã lọc).
- `404 CONVERSATION_EXCERPT_NOT_AVAILABLE` → `Yêu cầu này không được tạo từ trò chuyện, hoặc khách đã xoá cuộc trò chuyện.` (EDGE-607, BR-608).
- `404 BOOKING_NOT_FOUND` / `QUOTE_NOT_FOUND` → ẩn panel.
- Panel mặc định thu gọn (`Xem hội thoại liên quan ▾`), mở ra mới gọi API.

---

# 5. User Interaction

## 5.1 Interaction Flow

```text
Mở /ai
   ↓
GET /user-vehicles → userVehicleId
   ↓
GET /conversations?userVehicleId=…&limit=1
   ├── có → GET /conversations/{id}/messages?limit=50 → hiển thị
   └── không → Empty state + câu hỏi gợi ý
   ↓
Gõ câu hỏi → Gửi
   ↓
(chưa có hội thoại) POST /conversations {userVehicleId}
   ↓
POST /conversations/{id}/messages  (Accept: text/event-stream)
   ├── 4xx JSON (trước khi mở luồng) → lỗi nghiệp vụ, tin không lưu
   └── 200 SSE
         message.accepted → tin user "sent"
         status           → StageIndicator
         token*           → câu trả lời hiện dần
         message.completed→ thay bằng bản chuẩn + trích dẫn
         error            → tin user "unanswered" + "Gửi lại"
```

## 5.2 Interaction Table

| User Action | Frontend Behavior | Result |
|---|---|---|
| Mở `/ai` | Tải hội thoại gần nhất | Thấy lịch sử (AC-604) |
| Gửi câu hỏi | SSE `API-CHAT-004` | Trả lời streaming + trích dẫn (AC-601) |
| Gửi khi đang trả lời | Không cho (composer disabled) | — (BR-612) |
| Nhấn chip trích dẫn | Mở SCR-604 | Thấy nguồn |
| Cuộn lên đầu | `before = nextCursor` | Tin cũ hơn, không trùng/sót (AC-609) |
| Nhấn `Cuộc trò chuyện mới` | Xoá trạng thái màn, chưa gọi API; tạo hội thoại khi gửi tin đầu | Hội thoại mới (AF-605) |
| Nhấn `Gửi lại` | Gửi lại cùng `clientMessageId` | Một tin user, một câu trả lời (AC-611) |
| Mở Lịch sử, gõ "phanh" | `API-CONV-004` | Kết quả có đánh dấu (AC-610) |
| Xoá hội thoại | Dialog → `API-CONV-005` | Hội thoại biến mất (AC-608) |
| Rời màn khi đang stream | Huỷ SSE (`AbortController`) | Backend không lưu câu trả lời dang dở (EF-601) |

---

# 6. State Management

## 6.1 State Model

```text
ChatState (theo conversationId)
├── vehicle              { userVehicleId, isActive }
├── conversation         ConversationDto | null
├── messages             MessageDto[]                 (đã lưu, sort theo seq)
├── pagination           { olderCursor, hasOlder, isLoadingOlder }
├── pendingUser          Map<clientMessageId, { content, status: sending|failed|unanswered }>
├── streaming            { clientMessageId, draftText, stage, abort: AbortController } | null
├── composer             { text, error }
├── rateLimit            { retryAt: number | null }
└── request              { isLoading, error }

HistoryState
├── conversations        ConversationDto[]
├── page                 { nextCursor, hasMore }
├── search               { q, results[], page, isLoading }
```

## 6.2 State Fields

| State | Type | Default | Description |
|---|---|---|---|
| `conversation` | `ConversationDto \| null` | `null` | `null` = "Cuộc trò chuyện mới" chưa tạo |
| `messages` | `MessageDto[]` | `[]` | Chỉ tin đã lưu ở server |
| `pagination.olderCursor` | `string \| null` | từ `page.nextCursor` | Dùng làm `before` |
| `pendingUser` | `Map` | trống | Tin user chưa có `message.accepted`, hoặc đã lưu nhưng chưa được trả lời |
| `streaming` | object \| `null` | `null` | Lượt đang chạy; `!= null` ⇒ composer disabled |
| `streaming.draftText` | `string` | `""` | Ghép từ `token`, chỉ để hiển thị |
| `rateLimit.retryAt` | `number \| null` | `null` | Epoch ms = now + `Retry-After` |
| `lastSeq` | `number` | max `seq` | Dùng cho bắt kịp WebSocket (`after`) |

- Cache `messages` theo `conversationId` trong bộ nhớ khi chuyển qua lại giữa các hội thoại trong phiên.
- Không lưu nội dung chat vào `localStorage` (FF §18 Riêng tư). Chỉ `draft` ô nhập của hội thoại hiện tại có thể lưu `sessionStorage` `[Đề xuất]`.
- Xoá toàn bộ khi đăng xuất.

---

# 7. API Integration

> Hợp đồng chi tiết: [API Spec F4](../api/us-025-sprint-2-spec.api.md), [Nền tảng](../../platform/conversation-messaging.api.md). Quy ước chung theo [US-001 FE §7.0](../../sprint-1/frontend/us-001-sprint-1-spec.fe.md#70-quy-ước-chung). Header trace của API này là `X-Trace-Id`.

## 7.1 Hội thoại gần nhất — `API-CONV-002`

```http
GET /api/v1/conversations?userVehicleId={id}&limit=1
```

**Trigger:** mở `/ai` không có `conversationId`. `data[0]` → mở; rỗng → Empty State.

Danh sách đầy đủ (SCR-602): `limit=20`, `cursor=page.nextCursor`.

---

## 7.2 Tạo hội thoại — `API-CONV-001`

```http
POST /api/v1/conversations
{ "userVehicleId": "{userVehicleId}" }
```

**Trigger:** gửi tin đầu khi `conversation = null`. `201` → `conversation = data`, cập nhật URL `/ai/{id}` (replace). Lỗi → mục 11.2.

---

## 7.3 Tải tin nhắn — `API-CONV-003`

```http
GET /api/v1/conversations/{conversationId}/messages?limit=50[&before={seq}|&after={seq}]
```

| Mục đích | Tham số |
|---|---|
| Mở hội thoại | `limit=50` |
| Tải tin cũ | `before={olderCursor}` |
| Bắt kịp sau WebSocket reconnect / tab focus lại | `after={lastSeq}` |
| Mở từ kết quả tìm kiếm | `before={seq+1}&limit=50` |

**Mapping:** `data` (mới nhất trước) → đảo lại → `mergeMessages()`; `page.nextCursor` → `olderCursor` (khi `before`) hoặc `lastSeq` (khi `after`).

Đọc được cả khi xe không còn `active` (EDGE-608) — chỉ composer bị khoá.

---

## 7.4 Gửi tin nhắn (SSE) — `API-CHAT-004`

```http
POST /api/v1/conversations/{conversationId}/messages
Content-Type: application/json
Accept: text/event-stream
Authorization: Bearer <token>

{ "clientMessageId": "{uuid}", "content": "{text}" }
```

> Không dùng `EventSource` (chỉ GET, không gửi được `Authorization`). Dùng `fetch` + `response.body.getReader()` + `TextDecoder`, tự tách sự kiện theo `\n\n`, bỏ qua dòng comment `: ping` (API §4).

### Xử lý response

| Tình huống | Nhận biết | Frontend |
|---|---|---|
| Lỗi trước khi mở luồng | `response.ok = false`, `Content-Type: application/json` | Map `error.code` (mục 11.2); tin user → `failed` (tin **không** được lưu) |
| `message.accepted` | Event | Xoá khỏi `pendingUser`, thêm `userMessage` vào `messages`; nếu `replayed = true` thì đợi `message.completed` phát lại |
| `status` | Event | Cập nhật `streaming.stage` |
| `token` | Event | `streaming.draftText += delta` |
| `message.completed` | Event | Thêm `message` vào `messages`, `streaming = null`, cập nhật `conversation.lastMessageAt`, `title` (nếu trống thì gọi lại `API-CONV-002` để lấy title) |
| `error` | Event (`AGENT_FAILED`, `AGENT_TIMEOUT`, `LLM_UNAVAILABLE`) | `streaming = null`, tin user → `unanswered` + `Gửi lại`; thông báo `Trợ lý tạm thời không trả lời được.` (EF-602) |
| Luồng đóng không có `message.completed` / `error` | Reader `done` | Như `error` (coi là mất kết nối — EF-601) |
| Mạng rớt khi đang stream | `fetch` ném lỗi | Như trên; tin user có thể đã lưu → `unanswered` |

### Timeout phía client

- Không nhận được byte nào (kể cả `: ping`) trong **45 giây** → huỷ (`AbortController`), xử lý như mất kết nối.
- Rời màn / đổi hội thoại / xoá hội thoại → `abort()`.

### Gửi lại

Gọi lại endpoint với **cùng** `clientMessageId` + `content`. Server trả `replayed: true` nếu đã có câu trả lời (không chạy lại Agent), hoặc chạy lại lượt nếu chưa (BR-611).

---

## 7.5 Tìm kiếm — `API-CONV-004`

```http
GET /api/v1/conversations/search?q={q}&userVehicleId={id}&limit=20[&cursor=…]
```

Mapping: `data[]` → kết quả; `page` → `Tải thêm`. `data = []` → Empty State 10.3.

---

## 7.6 Xoá hội thoại — `API-CONV-005`

```http
DELETE /api/v1/conversations/{conversationId}
```

`204` → mục 4.6. `404` → coi như đã xoá, bỏ khỏi danh sách.

---

## 7.7 WebSocket đồng bộ đa thiết bị — `API-MSG-001` `[Đề xuất: tuỳ chọn]`

```text
GET /api/v1/conversations/{conversationId}/stream   (Upgrade: websocket)
```

MVP một thiết bị có thể chỉ dùng SSE (platform §0.4). Nếu bật (`VITE_CHAT_WS_ENABLED=true`):

1. Mở khi vào hội thoại; gửi khung đầu `{ "type": "auth", "token": "<idToken>" }` trong 5 giây.
2. Nhận `ready.lastSeq` → nếu lớn hơn `lastSeq` ở client, gọi `API-CONV-003?after={lastSeq}` để bắt kịp.
3. `message` → `mergeMessages()` (bỏ trùng với tin nhận qua SSE theo `id`).
4. `ping` → trả `{ "type": "pong" }`.
5. Đóng `4401` → làm mới token, kết nối lại một lần; `4404` → về `/ai`; `4429` → không kết nối lại, chỉ dùng REST; khác → kết nối lại với backoff 1s → 30s.
6. Nhận `conversation.deleted` → đóng, về `/ai` + toast `Cuộc trò chuyện đã bị xoá.`

Không bật WebSocket: khi tab focus lại, gọi `API-CONV-003?after={lastSeq}` để lấy tin từ thiết bị khác.

---

## 7.8 Đoạn hội thoại cho chủ xưởng — `API-CHAT-007` / `API-CHAT-008`

```http
GET /api/v1/workshop/bookings/{bookingId}/conversation-excerpt
GET /api/v1/workshop/quotes/{quoteId}/conversation-excerpt
```

Mapping: `data.messages[]` → danh sách; `data.source.confirmedMessageId` → highlight. Lỗi → mục 4.9.

---

# 8. Client-side Validation

## 8.1 Validation Rules

| Field | Rule | Error Message |
|---|---|---|
| Tin nhắn | Không rỗng sau trim | (nút `Gửi` disabled, không báo lỗi) |
| Tin nhắn | ≤ 2000 ký tự (BR-614) | `Tin nhắn tối đa 2.000 ký tự.` |
| Từ khoá tìm kiếm | 2–100 ký tự sau trim | `Nhập ít nhất 2 ký tự để tìm.` (chỉ hiện khi người dùng nhấn Enter với < 2 ký tự) |

## 8.2 Validation Timing

- Đếm ký tự khi gõ; hiện bộ đếm từ 1.800 ký tự; vượt thì bộ đếm đỏ và chặn gửi.
- Không gọi API khi validate thất bại.

---

# 9. Loading States

| Tình huống | UI |
|---|---|
| Mở `/ai` lần đầu | Skeleton 3–4 bong bóng xen kẽ; composer disabled |
| Tải tin cũ | Spinner nhỏ ở đầu danh sách; giữ vị trí cuộn |
| Đã gửi, chưa `message.accepted` | Tin user mờ + spinner |
| Đã accepted, chưa có `token` | Bong bóng assistant với `StageIndicator` / 3 chấm nhấp nháy |
| Đang stream | Chữ hiện dần + con trỏ; nút `Gửi` → `Đang trả lời...` (disabled) |
| Tải Lịch sử / Tìm kiếm | Skeleton danh sách |
| Xoá | Nút `Xoá` trong dialog spinner |
| Excerpt (chủ xưởng) | Skeleton trong panel |

---

# 10. Empty States

## 10.1 Chưa có hội thoại

- **UI:** Icon Bot + `Xin chào! Tôi có thể giúp bạn tra cứu lịch bảo dưỡng, hạng mục, bảo hành và cách dùng xe theo tài liệu chính hãng.` + chip câu hỏi gợi ý.

## 10.2 Lịch sử trống

- **UI:** `Bạn chưa có cuộc trò chuyện nào.` + nút `Bắt đầu trò chuyện`.

## 10.3 Tìm không có kết quả (EDGE-610)

- **UI:** `Không tìm thấy tin nhắn nào chứa "{q}".`

## 10.4 Câu trả lời không có nguồn (AC-602)

- Không phải empty state lỗi: bong bóng assistant bình thường, **không** có khối trích dẫn. Nội dung từ chối do Agent soạn (AI-002).

---

# 11. Error States

## 11.1 General Error

Khi tải hội thoại lỗi (thay danh sách tin nhắn):

```text
Không tải được cuộc trò chuyện.
Vui lòng thử lại.

[Thử lại]
Mã lỗi: {traceId}
```

## 11.2 Error Mapping

| HTTP Status / Error Code | API | Frontend Behavior |
|---|---|---|
| `400 INVALID_REQUEST` | All | Toast `Yêu cầu không hợp lệ.` (lỗi lập trình — log) |
| `401 UNAUTHORIZED` | All | Interceptor → Login ([US-005 FE](../../sprint-1/frontend/us-005-sprint-1-spec.fe.md)) |
| `403 FORBIDDEN` / `ONBOARDING_REQUIRED` | 001–006 | Onboarding / về trang đúng vai trò |
| `404 VEHICLE_NOT_FOUND` | CONV-001 | Tải lại danh sách xe ([US-017 FE](./us-017-sprint-2-spec.fe.md)) |
| `404 CONVERSATION_NOT_FOUND` | 003, 004, 005, 006 | Toast `Không tìm thấy cuộc trò chuyện.` → `/ai` (AC-605 — không phân biệt "không tồn tại" và "của người khác") |
| `409 VEHICLE_NOT_ACTIVE` | CONV-001, CHAT-004 | Composer khoá: `Xe chưa được xác thực hoặc đã gỡ liên kết — bạn vẫn xem được lịch sử nhưng không gửi tin mới.` (EDGE-608) |
| `409 CONVERSATION_BUSY` | CHAT-004 | Tin user → `failed`; helper `Trợ lý đang trả lời tin trước, vui lòng đợi.` Tự thử lại sau 3 giây, tối đa 1 lần (EDGE-602) |
| `429 RATE_LIMITED` | CHAT-004 | Tin user → `failed`; composer khoá tới `retryAt` (từ `Retry-After`); helper `Bạn đã gửi quá nhiều tin. Vui lòng thử lại sau {mm:ss}.` có đếm ngược (AC-612) |
| SSE `error: AGENT_FAILED` / `AGENT_TIMEOUT` / `LLM_UNAVAILABLE` | CHAT-004 | Tin user → `unanswered` + `Gửi lại`; `Trợ lý tạm thời không trả lời được.` |
| `404 BOOKING_NOT_FOUND` / `QUOTE_NOT_FOUND` | 007, 008 | Ẩn panel |
| `404 CONVERSATION_EXCERPT_NOT_AVAILABLE` | 007, 008 | Thông báo trong panel (mục 4.9) |
| `500 DATABASE_ERROR` / `INTERNAL_SERVER_ERROR` | All | General Error / toast + `Thử lại` |
| Lỗi mạng | All | `Không có kết nối mạng.`; tin đang gửi → `failed` |

---

# 12. Error Handling

## 12.1 Field-level Error

Lỗi của composer hiển thị ngay trên ô nhập (helper text), không dùng toast.

## 12.2 Screen-level Error

Chỉ khi không tải được hội thoại. Lỗi của một lượt chat hiển thị **tại tin nhắn** đó, không che cả màn.

## 12.3 Retry Behavior

1. `Gửi lại` luôn dùng lại `clientMessageId` cũ.
2. Tải tin lỗi → `Thử lại` chỉ gọi lại trang lỗi, giữ tin đã có.
3. Không tự gửi lại khi `429` (chỉ mở khoá composer khi hết thời gian chờ).

---

# 13. Navigation

## 13.1 Routes

| Route | Purpose |
|---|---|
| `/ai` | Mở hội thoại gần nhất của xe (hoặc màn trống) |
| `/ai/:conversationId` | Mở hội thoại cụ thể; `?messageSeq=` để cuộn tới tin |
| `/ai?q=...` | Điền sẵn câu hỏi |
| `/technician/quote-review` | Có panel SCR-605 (chủ xưởng) |

## 13.2 Navigation Rules

- Tạo hội thoại mới → `navigate('/ai/{id}', { replace: true })` để Back không về trạng thái "chưa tạo".
- Rời màn khi đang stream → không hỏi xác nhận; huỷ luồng. Khi quay lại, tin user hiển thị `Trợ lý chưa trả lời` + `Gửi lại` (EF-601).
- Mở hội thoại không thuộc mình qua URL → `404` → `/ai` (AC-605).

---

# 14. Permission / Visibility

| UI Element | Condition |
|---|---|
| SCR-601 → 604 | Chủ xe `ACTIVE` |
| Composer | Xe `active`, không `streaming`, không bị rate limit |
| `Xoá cuộc trò chuyện` | Chủ hội thoại (mọi hội thoại hiển thị đều của chủ xe) |
| SCR-605 | Chủ xưởng `ACTIVE`, booking/báo giá của xưởng mình, có `source_message_id` |
| Composer ở SCR-605 | **Không có** (chủ xưởng không chat với Agent — FF §3.2) |
| Tin `tool`, `traceId`, điểm truy hồi | **Không hiển thị** |

## 14.1 Role-based Behavior

| Role | Access |
|---|---|
| Chủ xe | Đọc/gửi/tìm/xoá hội thoại của mình |
| Chủ xưởng | Chỉ đọc đoạn liên quan booking/báo giá xưởng mình |

> Kiểm tra ở FE chỉ phục vụ UX; backend quyết định quyền (BR-605, BR-606).

---

# 15. Responsive / Device Behavior

## Mobile (mobile-first — FF §20)

- Chat full-screen; composer dính đáy, tránh bàn phím ảo (`visualViewport`).
- Context Panel ẩn; nút `Xe của tôi` ở header mở bottom sheet.
- SCR-602 full-screen; SCR-604 bottom sheet.

## Tablet

- Chat + History drawer có thể mở song song.

## Desktop

- 3 vùng: (History drawer — tuỳ chọn) | Chat (rộng tối đa `max-w-3xl`) | Context Panel (320px).

---

# 16. Accessibility

- `MessageList`: `role="log"`, `aria-live="polite"`, `aria-relevant="additions"`; **không** đọc từng `token` — chỉ thông báo khi `message.completed` (dùng vùng `aria-live` riêng chứa nội dung cuối).
- Mỗi bong bóng có nhãn ẩn `Bạn:` / `Trợ lý:`.
- Chip trích dẫn là `<button>` có `aria-label="Nguồn: {title}, phiên bản {version}, trang {page}"`.
- Composer: `<textarea aria-label="Nhập câu hỏi">`; `Enter` gửi, `Shift+Enter` xuống dòng — ghi rõ trong helper.
- Dialog xoá: `role="alertdialog"`, focus mặc định `Huỷ`.
- Đếm ngược rate limit cập nhật `aria-live="polite"` mỗi 10 giây, không mỗi giây.

---

# 17. Analytics / Tracking

| Event | Trigger | Properties |
|---|---|---|
| `chat_opened` | Mở `/ai` | `hasConversation` |
| `chat_message_sent` | Gửi tin | `length`, `fromSuggestion` |
| `chat_first_token` | Token đầu tới | `latencyMs` (đo AC-613: p50 ≤ 1,5s) |
| `chat_answer_completed` | `message.completed` | `totalMs`, `citationCount` |
| `chat_answer_failed` | SSE `error` / mất kết nối | `code` |
| `chat_citation_opened` | Mở SCR-604 | `documentType` |
| `chat_rate_limited` | `429` | `retryAfterSeconds` |
| `chat_conversation_deleted` | Xoá thành công | — |
| `chat_history_searched` | Gọi tìm kiếm | `resultCount` |

> **Không** gửi nội dung tin nhắn, từ khoá tìm kiếm, id hội thoại vào analytics (FF §18, BR-617).

---

# 18. Acceptance Criteria

## AC-FE-601 — Trả lời có trích dẫn (FF AC-601)

**Given** câu hỏi có trong tài liệu đã ingest
**When** chủ xe gửi
**Then** câu trả lời hiện dần, và sau `message.completed` có ít nhất 1 chip trích dẫn `{title} · v{version} · tr.{page}`; nhấn chip mở chi tiết nguồn.

## AC-FE-602 — Không có nguồn (FF AC-602)

**Given** `message.completed.message.citations = []`
**Then** bong bóng hiển thị bình thường, không có khối trích dẫn, không hiển thị lỗi.

## AC-FE-603 — Không hỏi lại thông tin xe (FF AC-603)

**Given** chủ xe gửi "mốc tới cần làm gì?"
**Then** body request chỉ có `clientMessageId` và `content` — FE không gửi model, ODO hay `userVehicleId`.

## AC-FE-604 — Mở lại app (FF AC-604)

**Given** hội thoại có tin hoàn tất
**When** đóng rồi mở lại `/ai`
**Then** FE tải hội thoại gần nhất và 50 tin mới nhất, không hiển thị câu trả lời dang dở; tin user cuối chưa có trả lời hiện `Gửi lại`.

## AC-FE-605 — Hội thoại người khác (FF AC-605)

**Given** chủ xe mở `/ai/{id}` của người khác
**Then** nhận `404 CONVERSATION_NOT_FOUND`, FE báo `Không tìm thấy cuộc trò chuyện.` và về `/ai`, không hiển thị nội dung nào.

## AC-FE-606 — Chủ xưởng xem đoạn liên quan (FF AC-607)

**Given** chủ xưởng mở trang báo giá tạo từ chat
**When** mở panel `Hội thoại dẫn tới yêu cầu`
**Then** thấy tối đa 20 tin user/assistant, chỉ đọc, tin xác nhận được đánh dấu; không có ô nhập.

## AC-FE-607 — Xoá hội thoại (FF AC-608)

**Given** chủ xe xác nhận xoá
**Then** FE gọi `DELETE /conversations/{id}`, hội thoại biến mất khỏi danh sách; nếu đang mở thì chuyển sang hội thoại khác hoặc màn trống.

## AC-FE-608 — Phân trang (FF AC-609)

**Given** hội thoại 200 tin
**When** mở và cuộn lên liên tục
**Then** FE tải 50 tin mỗi lần bằng `before`, không trùng, không sót, giữ vị trí cuộn.

## AC-FE-609 — Tìm kiếm (FF AC-610)

**Given** chủ xe gõ "Phanh" trong ô tìm
**Then** sau 400ms FE gọi `GET /conversations/search?q=Phanh`, hiển thị kết quả với từ khớp được đánh dấu; nhấn kết quả mở đúng hội thoại và cuộn tới tin.

## AC-FE-610 — Gửi lại không trùng (FF AC-611)

**Given** mất mạng khi đang chờ trả lời
**When** nhấn `Gửi lại`
**Then** FE gửi lại cùng `clientMessageId`; lịch sử chỉ có một tin user và một câu trả lời.

## AC-FE-611 — Rate limit (FF AC-612)

**Given** `API-CHAT-004` trả `429` với `Retry-After: 40`
**Then** tin chưa gửi hiện lỗi, composer khoá và đếm ngược 40 giây, sau đó mở lại.

## AC-FE-612 — Một lượt mỗi lần (FF BR-612)

**Given** câu trả lời đang stream
**Then** nút `Gửi` disabled; nếu thiết bị khác gửi và backend trả `409 CONVERSATION_BUSY`, FE hiển thị thông báo chờ.

## AC-FE-613 — Hiệu năng hiển thị (FF AC-613)

**Given** điều kiện mạng bình thường
**Then** token đầu hiển thị ngay khi nhận (không buffer), và 50 tin lịch sử render không giật (danh sách > 200 tin dùng ảo hoá `[Đề xuất]`).

---

# 19. Technical Notes

## Frontend Stack

```text
Framework: React 19 + Vite
Language: TypeScript
State Management: useReducer (ChatState) + context cho History
Networking: fetch (REST, SSE qua ReadableStream), WebSocket native (tuỳ chọn)
Navigation: React Router 7
UI Library: Tailwind CSS 4 + lucide-react
Markdown: renderer tối giản an toàn (vd react-markdown không bật raw HTML) [Đề xuất]
```

## Component Structure

```text
frontend/src/features/assistant/
├── api.ts                      # conversations CRUD, getMessages, searchMessages, deleteConversation
├── sse.ts                      # streamChatTurn(): fetch + parse SSE, AbortController
├── ws.ts                       # (tuỳ chọn) ConversationSocket: auth frame, ping/pong, reconnect
├── types.ts                    # MessageDto, CitationDto, ConversationDto, SseEvent
├── state/chatReducer.ts        # mergeMessages, pendingUser, streaming
├── pages/AIAssistant.tsx       # SCR-601
└── components/
    ├── MessageList.tsx
    ├── AssistantMessage.tsx
    ├── UserMessage.tsx
    ├── CitationChip.tsx
    ├── CitationDrawer.tsx      # SCR-604
    ├── ChatComposer.tsx
    ├── ChatContextPanel.tsx
    ├── ConversationHistoryDrawer.tsx   # SCR-602 + SCR-603
    └── ConversationExcerptPanel.tsx    # SCR-605 (dùng ở features/quotes)
```

## Implementation Notes — thay đổi so với code hiện tại

| File | Hiện trạng | Việc cần làm |
|---|---|---|
| [assistant/api.ts](../../../../frontend/src/features/assistant/api.ts) | `sendChat()` gọi `POST /api/v1/chat` — **endpoint không tồn tại** ở backend | Bỏ; thay bằng `API-CONV-*` + `API-CHAT-004` |
| [assistant/types.ts](../../../../frontend/src/features/assistant/types.ts) | `Message { role: 'user' \| 'ai', source, actions }` | Đổi sang `MessageDto` (`role: 'user' \| 'assistant'`, `citations[]`, `refs`, `card`, `seq`) |
| [AIAssistant.tsx](../../../../frontend/src/features/assistant/pages/AIAssistant.tsx) | Dùng `mocks/assistant.ts`, trả lời theo từ khoá cứng | Nối API thật theo spec này |
| Backend route PROVISIONAL | `POST /conversations/{id}/messages` nhận `role` bất kỳ, không auth (pending Q-620, Q-621) | FE chỉ dùng hợp đồng mới; chờ backend chuyển đổi (platform §12) |

- SSE parser phải xử lý: nhiều dòng `data:` trong một sự kiện, chunk cắt giữa sự kiện, dòng comment `:`.
- `mergeMessages()` là hàm thuần, có unit test cho: trùng `id`, sai thứ tự `seq`, trộn trang cũ + tin mới.
- `crypto.randomUUID()` cho `clientMessageId`; lưu trong `pendingUser` để `Gửi lại`.

---

# 20. Open Questions

- [ ] **Q-FE-CHAT-01** — MVP có bật WebSocket (`API-MSG-001`) không, hay chỉ SSE + bắt kịp bằng `after` khi focus lại tab?
- [ ] **Q-FE-CHAT-02** — Câu hỏi gợi ý lấy tĩnh ở FE hay backend trả theo model/trạng thái xe?
- [ ] **Q-FE-CHAT-03** — Hợp đồng `card` cho F5/F6 (`card.type`, field) — cần spec F5/F6 chốt trước khi render.
- [ ] **Q-FE-CHAT-04** — Có cho mở tài liệu gốc (PDF, đúng trang) từ SCR-604 không? Hiện API không trả `documentId`/URL.
- [ ] **Q-FE-CHAT-05** — Trang chi tiết booking của xưởng (nơi đặt SCR-605 cho `API-CHAT-007`) chưa tồn tại; thuộc F6/F8.
- [ ] Còn mở ở backend: [pending-questions.md](../pending-questions.md) Q-620 (siết ghi tin), Q-621 (auth route/WS — bắt buộc trước khi đo AC-605), Q-622.

---

# 21. Related Documents

- PRD: [PRD_EV_Care_MVP.md §F4](../../../product/PRD_EV_Care_MVP.md)
- Functional Spec: [us-025-sprint-2-spec.ff.md](../feature-functional/us-025-sprint-2-spec.ff.md)
- API Specification: [us-025-sprint-2-spec.api.md](../api/us-025-sprint-2-spec.api.md) · [conversation-messaging.api.md](../../platform/conversation-messaging.api.md)
- Entity Spec: [us-025-sprint-2-spec.entity.md](../entity/us-025-sprint-2-spec.entity.md)
- Agent: [AI-001](../../ai-agent/ai-001-sprint-2-spec.agent.md) · [AI-002](../../ai-agent/ai-002-sprint-2-spec.agent.md)
- Design: [wireframe.md §5, §8](../../../design/wireframe.md) · [design-guidelines.md](../../../design/design-guidelines.md)
- FE liên quan: [US-017 Hồ sơ xe & trạng thái đến hạn](./us-017-sprint-2-spec.fe.md)

---

# 22. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Mai Văn Trung | Bản nháp đầu tiên, dựng từ FF v1.1, API Spec F4 v1.1 và API nền tảng |
