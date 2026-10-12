# Frontend Technical Specification — Gợi ý một chạm

> Frontend cho Feature `FEAT-P2-CH01` (SCR-CH01-01, SCR-CH01-02) trên SCR-601 AI trợ lý, và hàng chip ở Trang chủ.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ch-01-phase2-spec.ff.md). **API:** [API Spec](ch-01-phase2-spec.api.md) (`API-CH01-01..03`, `MessageDto.chips`).
>
> **Nguyên tắc:** frontend chỉ hiển thị chip backend trả và gửi `chipId`; không tự dựng chip, không gửi `intent`. Chip không bao giờ tạo booking — chỉ nút "Xác nhận đặt lịch" trên thẻ đề xuất (us-061) làm được việc đó.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-CH01` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-CH01-01 (hàng chip dưới khung chat), SCR-CH01-02 (lưới chip màn chat trống), hàng chip Trang chủ |
| Feature folder | `frontend/src/features/assistant/chips/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `ChipRow` (SCR-CH01-01)

File `features/assistant/chips/ChipRow.tsx`, đặt ngay trên `ChatComposer`.

| | |
|---|---|
| Nguồn | `chips` của tin trợ lý **mới nhất** có `chipState = ACTIVE` |
| Kiểu | `rounded-xl` chip, `min-h-11` (44 px, BR-CH01-08), chữ 13–14 px; `primary` ⇒ `bg-brand text-on-brand`; còn lại card + border |
| Bố cục | Mobile: một hàng cuộn ngang (`overflow-x-auto`, snap); ≥ `md`: xuống dòng |
| `kind = ACTION` | `onChipAction(chip)` ⇒ `API-CH01-02` |
| `kind = LINK` | `open_map` ⇒ `/booking/map?from=chat&conversationId=` (BK-05); `open_calendar` ⇒ mở `DaySlotsSheet`/widget BK-04 dạng sheet trong chat; `directions` ⇒ URL Google Maps tab mới |
| `kind = TYPE` | Focus ô nhập, không gọi API |
| Ẩn | Khi đang stream, khi có yêu cầu chip đang chạy, khi `chat.lockedReason` |

## 2.2 Chip trong lịch sử tin

Tin trợ lý cũ hiển thị chip của nó ở dạng nhạt (`opacity-60`, `aria-disabled`), không bấm được; tin `user` sinh từ chip hiện nhãn chip như bong bóng bình thường. Bấm chip cũ (khi UI chưa kịp cập nhật) ⇒ `409 CHIP_STALE` ⇒ toast "Gợi ý này đã hết hiệu lực" (EF-CH01-01).

## 2.3 Lưới chip mở đầu (SCR-CH01-02)

Màn chat trống (`AIAssistant.tsx` `emptyState`): thay danh sách câu gợi ý tĩnh bằng `OpeningChipGrid`:
- Tạo hội thoại khi cần (như `send`), gọi `API-CH01-01`.
- Lưới 2 cột (mobile) / 3 cột (≥ `md`), chip lớn hơn (`min-h-12`), giữ ô "Đặt lịch bảo dưỡng nhanh" của us-061 là phần tử đầu (FE us-061 AC 1).
- Lỗi tải ⇒ dùng danh sách mặc định cục bộ dạng **TYPE** (điền câu vào ô nhập, không gửi `chipId` giả).
- `ChatContextPanel` cột phải: mục "Câu hỏi gợi ý" dùng cùng tập chip.

## 2.4 `useChipAction`

`features/assistant/chips/useChipAction.ts` (logic ở hàm thuần `runChipAction` để test):

1. Cờ in-flight theo `chipId` — bấm hai lần chỉ gửi một lần.
2. `dispatch({ type: 'send', clientMessageId, content: chip.label })` để hiện ngay bong bóng chủ xe; `stage = 'chip'` ("Đang xử lý…").
3. `transport.chipAction(conversationId, { chipId, clientMessageId })`.
4. Thành công ⇒ `accepted(userMessage)`, `completed(assistantMessage)` (chip mới + thẻ đi kèm).
5. Lỗi: `CHIP_STALE` ⇒ bỏ tin chờ + toast; `CONVERSATION_BUSY` ⇒ như us-061; `RATE_LIMITED` ⇒ đếm ngược có sẵn; khác ⇒ `turn-failed`.

`ChatTransport` thêm `openingChips(conversationId)`, `chipAction(conversationId, body)`; `mockTransport` trả danh sách mặc định và ném `NOT_SUPPORTED_IN_MOCK` cho `chipAction`.

## 2.5 Chip Trang chủ

`features/dashboard/components/HomeChips.tsx`: dưới lời chào, tối đa 3 chip từ `API-CH01-03`; bấm ⇒ điều hướng `deepLink` (`/ai?chip=…`). `AIAssistant` đọc query `chip`, tạo hội thoại, gọi `API-CH01-01` rồi tự gửi chip có cùng `intent` (chip do backend phát, không dựng ở client). Không có chip ⇒ ẩn hàng.

## 2.6 Bàn phím & trình đọc màn hình

- `ChipRow` là `role="toolbar"` với `aria-label="Gợi ý trả lời"`; mũi tên trái/phải di chuyển giữa chip, `Enter`/`Space` bấm.
- Mỗi chip `aria-label` = nhãn đầy đủ (kể cả khi bị cắt "…").
- Khi chip mới xuất hiện, thông báo `aria-live="polite"`: "Có {n} gợi ý trả lời".

---

# 3. API Integration & Errors

| API | Lỗi | Xử lý |
|---|---|---|
| CH01-01 | `CONVERSATION_NOT_EMPTY` | Dùng chip của tin mới nhất |
| CH01-01 | Mạng / 5xx | Danh sách mặc định dạng TYPE |
| CH01-02 | `CHIP_STALE` | Toast, bỏ tin chờ, không thử lại |
| CH01-02 | `FLOW_VERSION_CONFLICT` | Gọi lại một lần với cùng `clientMessageId` |
| CH01-02 | `CONVERSATION_BUSY` / `RATE_LIMITED` / `VEHICLE_NOT_ACTIVE` | Như gửi tin us-025 / us-061 |
| CH01-03 | Bất kỳ | Ẩn hàng chip Trang chủ |

---

# 4. States

| State | UI |
|---|---|
| Đang xử lý chip | Bong bóng chủ xe pending + dòng "Đang xử lý…"; `ChipRow` ẩn |
| Không có chip | Không render hàng (không để khoảng trống) |
| 390 px | Hàng cuộn ngang, chip đầu sát lề 16 px, có fade mép phải bằng mask (không gradient màu) |

---

# 5. Acceptance Criteria (FE)

1. Luồng chuẩn hoàn tất chỉ bằng chạm, 0 ký tự trong ô nhập (AC-CH01-01) — test `runChipAction` + reducer.
2. Chỉ chip của tin mới nhất bấm được; chip cũ không gửi request (AC-CH01-03).
3. Bấm chip hai lần nhanh gửi một request.
4. Chip đạt 44 px vùng chạm và điều khiển được bằng bàn phím.
5. Không có code path nào tạo booking từ chip (chỉ `confirmProposal` của thẻ us-061).
6. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua; không thêm dependency.

---

# 6. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `chips/chipState.test.ts` | `activeChips(messages)` chỉ trả chip của tin trợ lý mới nhất, chưa dùng | +3 |
| `chips/runChipAction.test.ts` | Gọi `chipAction` đúng một lần; `CHIP_STALE` ⇒ `drop-pending`; không bao giờ gọi `sendMessage` | +4 |
| `chips/chipKeyboard.test.ts` | `nextChipIndex` theo phím | +2 |
| `chips/ChipRow.test.tsx` | `renderToStaticMarkup`: chip `primary` có lớp `bg-brand`; `LINK` có `href`/`aria-label` | +2 |
| `assistant/state/chatReducer.test.ts` | Tin user từ chip hiển thị như tin thường | +1 |

---

# 7. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-CH01-01, BR-CH01-01, 08 | §2.1, §2.6 |
| SCR-CH01-02, UC-CH01-01, BR-CH01-04 | §2.3 |
| UC-CH01-02, BR-CH01-02, 05 | §2.4 |
| EF-CH01-01, AC-CH01-03 | §2.2 |
| AF-CH01-03/04 | §2.1 (`LINK`) |
| Q-CH01-02 | §2.5 |

---

# 8. Analytics

Phía backend ghi `chip_shown` / `chip_clicked` (PL-03). Frontend chỉ thêm `chip_row_scrolled` (mobile, để biết chip ngoài màn có được thấy không) và `home_chip_clicked` (`intent`).

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
