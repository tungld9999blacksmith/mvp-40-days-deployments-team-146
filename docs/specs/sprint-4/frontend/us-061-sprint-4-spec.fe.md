# Frontend Technical Specification — Đặt lịch bảo dưỡng nhanh

> Frontend cho Feature `FEAT-QBOOK-001` (US-061) trên SCR-601 AI trợ lý.
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-061-sprint-4-spec.ff.md). **API:** [API Spec](../api/us-061-sprint-4-spec.api.md) (`API-QB-01..04`, `card` §3.2–3.3).
>
> **Nguyên tắc:** frontend không tự quyết định mốc, xưởng, giờ hay trạng thái đề xuất; mọi thứ hiển thị đều lấy từ `card` do backend trả. Frontend không bao giờ gọi `POST /bookings` trong luồng này.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-QBOOK-001` |
| Version | `v1.1` |
| Status | `Approved` |
| Screens | SCR-601 (sửa), SCR-1501, SCR-1502 (mới, trong tin nhắn) |
| Created Date | `2026-10-03` |

---

# 2. Components

## 2.1 Ô "Đặt lịch bảo dưỡng nhanh" (AC-1501)

| | |
|---|---|
| File | `frontend/src/features/assistant/components/ChatContextPanel.tsx` |
| Hằng số | `export const QUICK_BOOKING_LABEL = 'Đặt lịch bảo dưỡng nhanh'` |
| Vị trí | Phần tử **đầu tiên** của danh sách gợi ý ở cả hai nơi: (1) màn trống trong `AIAssistant.tsx` (`emptyState`, dạng chip tròn), (2) `ChatContextPanel` mục "Câu hỏi gợi ý" (cột phải `xl`, drawer "Xe của tôi" trên màn nhỏ hơn) |
| Kiểu | Cùng class với các câu gợi ý ở nơi đó; thêm icon `CalendarClock` (lucide) 14 px trước nhãn |
| Hành vi | Gọi `onQuickBooking()` (prop mới), **không** gửi nhãn như một câu chat |
| Disabled | Khi `state.streaming`, `chat.lockedReason`, `retryIn`, hoặc đang có yêu cầu quick booking chạy |
| Không có xe | `ChatContextPanel` với `vehicle = null`: ô bị disabled, có dòng phụ "Liên kết xe để đặt lịch" (màn AI trợ lý thường đã được `VehicleGate` chặn trước) |

## 2.2 `useChatSession.quickBooking({ province? })`

File `frontend/src/features/assistant/hooks/useChatSession.ts`.

1. Nếu chưa có `conversationId` thì `transport.createConversation(userVehicleId)` + `dispatch('conversation-created')` (giống `send`).
2. Lấy vị trí thiết bị (`getDeviceLocation()` trong `features/assistant/quickBooking/location.ts`): có `navigator.geolocation` thì gọi `getCurrentPosition` với `{ timeout: 5000, maximumAge: 600000 }`. Bị từ chối, hết giờ hoặc không hỗ trợ ⇒ `null`, **không** báo lỗi (backend dùng vị trí hồ sơ). Bỏ qua bước này khi đã có `province` (lượt chọn khu vực).
3. `dispatch({ type: 'send', clientMessageId, content: QUICK_BOOKING_LABEL })` để hiện ngay tin của chủ xe; `dispatch({ type: 'stage', stage: 'quick_booking' })` hiện "Đang tìm xưởng gần bạn và khung giờ trống…".
4. `transport.quickBooking(conversationId, { clientMessageId, location, province })` (API-QB-01).
5. Thành công ⇒ `dispatch('accepted', userMessage)` rồi `dispatch('completed', assistantMessage)`. Lỗi ⇒ `dispatch('turn-failed')` với thông điệp theo §3.
6. Analytics: `quick_booking_started` (`hasDeviceLocation`), `quick_booking_result` (`cardType`, `dueStatus`, `locationBasis`).

## 2.3 `ChatTransport` (bổ sung)

`frontend/src/features/assistant/transport/ChatTransport.ts`, `httpTransport.ts`:

```ts
quickBooking(conversationId: string, body: { clientMessageId: string; location: { lat: number; lng: number } | null; province: string | null }):
  Promise<{ userMessage: MessageDto; assistantMessage: MessageDto; replayed: boolean }>
confirmProposal(conversationId: string, proposalId: string): Promise<ConfirmProposalResult>
reviseProposal(conversationId: string, proposalId: string, body: { workshopId: string; date: string; timeSlot: string }):
  Promise<{ proposalId: string; message: MessageDto }>
cancelProposal(conversationId: string, proposalId: string): Promise<{ proposalId: string; status: 'CANCELLED' }>
```

`mockTransport.ts`: bốn hàm ném `ApiError('NOT_SUPPORTED_IN_MOCK')`; ô nhanh hiện toast "Chế độ minh hoạ chưa hỗ trợ đặt lịch nhanh".

## 2.4 Kiểu dữ liệu

`frontend/src/features/assistant/types.ts` thêm `BookingProposalCard`, `ProposalOption`, `QuickBookingNeedLocationCard`, `ConfirmProposalResult` đúng theo API §3.2, §3.3, §5.3. `MessageDto.card` giữ kiểu hiện có; `MessageCard` thu hẹp kiểu theo `card.type`.

## 2.5 `MessageCard` (router)

`frontend/src/features/assistant/components/MessageCard.tsx`: thêm nhánh `BOOKING_PROPOSAL` → `<BookingProposalCard>`, `QUICK_BOOKING_NEED_LOCATION` → `<RegionPickerCard>`; nhánh ước tính giữ nguyên. Hành động của thẻ đi qua React context `QuickBookingProvider` (`quickBooking/QuickBookingContext.tsx`) do `AIAssistant` cung cấp quanh `MessageList`, nên `MessageList` / `AssistantMessage` không đổi props. Logic gọi API và ánh xạ lỗi nằm ở `quickBooking/useProposalActions.ts`.

## 2.6 `BookingProposalCard` (SCR-1501, mới)

File `frontend/src/features/assistant/components/BookingProposalCard.tsx`.

| Vùng | Nội dung | Nguồn |
|---|---|---|
| Đầu thẻ | "Đề xuất đặt lịch" + nhãn trạng thái (§2.7) | `status`, `booking.status` |
| Xe | `vehicleDisplayName(modelName, trim)` · biển số đã che | `vehicle` |
| Mốc | `milestoneLabel` + `DueStatusBadge` + `reason` + danh sách hạng mục (thẻ "Bảo hành" khi `isCoveredByWarranty`) | `milestone`, `reason` |
| Xưởng | Tên, địa chỉ, `formatKm(distanceKm)` khi có; không có km thì hiện `locationLabel` nếu có; nhãn "Xưởng yêu thích" khi `isPreferred` | `primary` |
| Thời gian | `Thứ Hai, 05/10/2026 · 10:00` (`formatDate` + giờ) | `primary.date`, `primary.timeSlot` |
| Chi phí | `formatVnd(chargeableTotal)` + "Giá tham khảo, xưởng có thể báo khác" khi `hasReferencePrice`; ẩn cả dòng khi `estimate = null` | `primary.estimate` |
| Hạn | "Đề xuất giữ trong 30 phút, chưa giữ chỗ" (khi `PROPOSED`) | `expiresAt` |
| Hành động | "Xác nhận đặt lịch" (primary), "Đổi xưởng / thời gian" (secondary), "Hủy đề xuất" (ghost) — chỉ khi `PROPOSED` | |

**Xác nhận:** bấm ⇒ nút loading, mọi nút trên thẻ disabled; giữ cờ in-flight theo `proposalId` để bấm lần hai không gửi thêm yêu cầu. `confirmProposal` thành công ⇒ cập nhật card của tin (`status = CONFIRMED`, `booking`) bằng `dispatch({ type: 'merge', messages: [tin có card đã cập nhật] })` và `dispatch('merge', [result.message])`. Lỗi theo §3.

**Đổi xưởng / thời gian:** mở panel ngay trong thẻ:
- Danh sách radio: phương án chính (đang chọn) + `alternatives` (xưởng · khoảng cách · ngày giờ · chi phí).
- "Chọn ngày khác tại {xưởng đang chọn}": `DayStrip` + `SlotGrid` (`features/bookings/components/SlotPicker.tsx`) với dữ liệu `getAvailability({ workshopId, date, withAlternatives: false })` (API-BK-02, có sẵn); ẩn khung bắt đầu trong vòng 2 giờ tới (chỉ hiển thị; backend vẫn kiểm).
- "Dùng phương án này" ⇒ `reviseProposal` ⇒ `merge(message)` (thẻ mới); thẻ cũ cập nhật `status = SUPERSEDED`.

**Huỷ:** `cancelProposal` ⇒ card `status = CANCELLED`. Không hộp thoại xác nhận (huỷ không mất dữ liệu nào).

## 2.7 Trạng thái thẻ (AC-1509, AC-1510)

| `status` | `booking.status` | Hiển thị | Hành động |
|---|---|---|---|
| `PROPOSED` | — | Nhãn "Chờ bạn xác nhận" | 3 nút |
| `CONFIRMED` | `CONFIRMED` | Nhãn xanh "Đã xác nhận" + "Mã đặt lịch **EVC-…**" | Link "Xem vé lịch hẹn" → `/bookings/{bookingId}` |
| `CONFIRMED` | `PENDING` | Nhãn vàng "Chờ xưởng xác nhận" + "Xưởng xác nhận trong tối đa 12 giờ; mã đặt lịch có sau khi xưởng xác nhận" | Link vé |
| `CONFIRMED` | `CANCELLED` / khác | Nhãn theo trạng thái booking hiện tại (dùng nhãn có sẵn của màn vé) | Link vé |
| `CANCELLED` | — | "Đã hủy đề xuất" (mờ) | Không |
| `SUPERSEDED` | — | "Đã thay bằng đề xuất mới" (mờ) | Không |
| `EXPIRED` | — | "Đề xuất đã hết hạn" | "Tạo đề xuất mới" → `quickBooking()` |

Mã đặt lịch chỉ hiện khi `booking.bookingCode` có giá trị; không bao giờ tự tạo mã.

## 2.8 `RegionPickerCard` (SCR-1502, mới)

Câu "Bạn muốn bảo dưỡng ở khu vực nào?" + danh sách nút theo `regions`. Bấm ⇒ `quickBooking({ province })`. Các nút disabled khi tin này không còn là tin trợ lý mới nhất.

---

# 3. API Integration & Errors

| API | Lỗi | Xử lý |
|---|---|---|
| QB-01 | `CONVERSATION_BUSY` | Toast "Trợ lý đang trả lời, thử lại sau giây lát"; bỏ tin chờ (`drop-pending`) |
| QB-01 | `RATE_LIMITED` | Dùng cơ chế đếm ngược `retryAt` hiện có |
| QB-01 | `VEHICLE_NOT_ACTIVE` / `CONVERSATION_NOT_FOUND` | Như gửi tin hiện có |
| QB-02 | `PROPOSAL_SLOT_FULL` | `merge(details.message)` (thẻ mới hoặc tin EF-1503); thẻ cũ `SUPERSEDED`; toast "Khung giờ vừa hết chỗ, đã đề xuất phương án khác" |
| QB-02 | `PROPOSAL_EXPIRED` | Thẻ `EXPIRED` |
| QB-02/03/04 | `PROPOSAL_INACTIVE` | Thẻ theo `details.status` |
| QB-02 | `PROPOSAL_IN_PROGRESS` | Giữ loading, gọi lại sau 1,5 s (tối đa 3 lần), sau đó tải lại tin nhắn |
| QB-02 | `OPEN_BOOKING_EXISTS` | Lỗi trong thẻ "Xe đã có lịch hẹn đang mở" + link `/bookings/{details.bookingId}` |
| QB-02 | `SERVICE_UNAVAILABLE` / mạng | Lỗi trong thẻ + nút "Thử lại" (gọi lại cùng `proposalId`, an toàn nhờ idempotent) |
| QB-03 | `SLOT_FULL` | Panel đổi hiện "Khung này vừa hết chỗ" + `details.alternatives` |
| QB-03 | `SLOT_TOO_SOON` / `SLOT_OUT_OF_HOURS` / `REVISE_WORKSHOP_NOT_OFFERED` | Thông báo trong panel |
| QB-04 | `PROPOSAL_ALREADY_CONFIRMED` | Tải lại tin nhắn để thẻ hiện `CONFIRMED` |
| Mọi QB | `404 PROPOSAL_NOT_FOUND` | Tải lại tin nhắn |

---

# 4. States

| State | UI |
|---|---|
| Đang dựng đề xuất | Tin chủ xe (pending) + dòng trạng thái "Đang tìm xưởng gần bạn và khung giờ trống…"; composer và ô gợi ý bị khoá |
| Đang xác nhận / đổi / huỷ | Nút tương ứng loading; các nút khác trên thẻ disabled; phần còn lại của chat dùng được |
| Mở lại hội thoại | Thẻ render từ `card` đã làm giàu (`status`, `booking`) của `GET …/messages`; không lưu trạng thái cục bộ |
| Mobile (< `xl`) | Thẻ rộng 100% khung tin; nút xếp dọc dưới 400 px; panel đổi mở trong thẻ, không mở drawer mới |

---

# 5. Acceptance Criteria (FE)

1. Nhãn ô đúng "Đặt lịch bảo dưỡng nhanh", là phần tử đầu ở màn trống, ở cột phải (≥ 1280 px) và ở drawer "Xe của tôi" (< 1280 px).
2. Bấm ô không gọi `POST /bookings` và không gọi `sendMessage` (test với transport giả: chỉ `quickBooking` được gọi).
3. Thẻ `PROPOSED` có đúng 3 nút với nhãn "Xác nhận đặt lịch", "Đổi xưởng / thời gian", "Hủy đề xuất".
4. Bấm "Xác nhận đặt lịch" hai lần nhanh chỉ gửi một `confirmProposal`.
5. `booking.status = PENDING` không hiện mã; `CONFIRMED` hiện đúng `bookingCode`.
6. Dòng khoảng cách tới xưởng chỉ hiện khi `distanceKm` khác `null`; khi `null` dòng xưởng không có số km (mốc bảo dưỡng và lý do vẫn có "km").
7. Thẻ `CANCELLED` / `SUPERSEDED` / `EXPIRED` / `CONFIRMED` không có nút "Xác nhận đặt lịch".
8. `npm run typecheck`, `npm run build` và `npm test` (gồm các test §6) đều qua; không thêm dependency.

---

# 6. Tests (Vitest)

Frontend chỉ có Vitest, không có `@testing-library/react` / `jsdom`; **không thêm dependency**. Logic được tách thành hàm thuần để test, component chỉ render theo kết quả hàm:

- `features/assistant/quickBooking/proposalView.ts`: `proposalView(card, now) → { status, badge, code, note, distanceText, areaText, actions, canRetry, ticketHref }`, và `patchProposalCard(messages, proposalId, patch)` cho `merge`.
- `features/assistant/quickBooking/runQuickBooking.ts`: `runQuickBooking({ transport, dispatch, conversationId, userVehicleId, location, province })` (hook `useChatSession.quickBooking` chỉ gọi hàm này).
- `features/assistant/quickBooking/inFlightGuard.ts`: `createInFlightGuard()` chặn gọi trùng theo `proposalId`.

| File | What | Count |
|---|---|---|
| `quickBooking/proposalView.test.ts` | 7 trạng thái §2.7; 3 hành động chỉ ở `PROPOSED`; `distanceText = null` khi `distanceKm = null`; PENDING `showCode = false`; CONFIRMED đúng `code` | +5 |
| `quickBooking/runQuickBooking.test.ts` | Chưa có hội thoại ⇒ `createConversation` rồi `quickBooking`; không bao giờ gọi `sendMessage`; lỗi ⇒ `turn-failed` | +3 |
| `quickBooking/inFlightGuard.test.ts` | Gọi hai lần cùng `proposalId` khi lần đầu chưa xong ⇒ chỉ một lần chạy | +2 |
| `state/chatReducer.test.ts` | `merge` thay card của tin cùng `id` (`mergeMessages` đã làm vậy; test hồi quy, không sửa reducer) | +1 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| AC-1501 | §2.1, AC-FE 1 |
| AC-1502 | §2.2, AC-FE 2 |
| AC-1505 | §2.6 (khoảng cách), AC-FE 6 |
| AC-1506 / AC-1510 | §2.7, AC-FE 7 |
| AC-1507 | §2.6 (in-flight), AC-FE 4 |
| AC-1508 | §3 `PROPOSAL_SLOT_FULL` |
| AC-1509 | §2.7, AC-FE 5 |
| AF-1501 | §2.8 |

---

# 8. Analytics

`quick_booking_started`, `quick_booking_result`, `quick_booking_confirm_clicked`, `quick_booking_confirmed` (`bookingStatus`), `quick_booking_slot_full`, `quick_booking_revised`, `quick_booking_cancelled`, `quick_booking_expired_retry`. Không gửi toạ độ.

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-03` | Bản nháp đầu |
| `v1.0` | `2026-10-03` | Chủ sản phẩm duyệt bản nháp; triển khai cùng PR (backend `modules/quick_booking`, frontend `features/assistant/quickBooking`) |
| `v1.1` | `2026-10-03` | Sau review Codex (7/10): khoá theo đề xuất cho xác nhận / đổi / huỷ; liên kết booking ↔ thẻ bền vững; trả lời gửi lại theo `refs.inReplyTo`; hết hạn thắng huỷ; khớp khu vực bỏ dấu; quét khung giờ theo lô; chỉ số đo được |
