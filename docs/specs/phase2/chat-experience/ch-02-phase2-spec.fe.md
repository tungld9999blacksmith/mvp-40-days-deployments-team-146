# Frontend Technical Specification — Thẻ tương tác trong chat

> Frontend cho Feature `FEAT-P2-CH02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ch-02-phase2-spec.ff.md). **API:** [API Spec](ch-02-phase2-spec.api.md) (phong bì thẻ, `status`, `actions`, `fallbackText`).
>
> **Nguyên tắc:** thẻ chỉ render `card.data` + `card.dynamic` từ backend; không tính lại số, không tự quyết nút nào hiện (dùng `card.actions`). Kiểu chữ theo DESIGN.md hiện hành: số liệu dùng `font-mono` (Inter + `tnum`), **không** dùng JetBrains Mono như FF §8 ghi (DESIGN.md đã thay font ngày 2026-10-11; PO chốt theo DESIGN.md ngày 2026-10-12).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-CH02` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | Thẻ trong SCR-601 AI trợ lý |
| Feature folder | `frontend/src/features/assistant/cards/` (mới; chuyển `BookingProposalCard`, `RegionPickerCard` vào đây) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `MessageCard` (router, sửa)

`features/assistant/components/MessageCard.tsx` dùng registry:

```ts
const CARD_RENDERERS: Record<string, { versions: number[]; render: (card: CardEnvelope) => ReactNode }> = {
  SCHEDULE_OPTIONS, SLOT_PICKER, BOOKING_PROPOSAL, BOOKING_TICKET, ESTIMATE,
  EXTRA_QUOTE, SERVICE_HISTORY_ITEM, PROACTIVE_HOLD, EARLY_SERVICE, QUICK_BOOKING_NEED_LOCATION,
}
```

- `type` không có hoặc `version` không hỗ trợ ⇒ `CardFallback`: `fallbackText` trong khối card + chip của tin (AF-CH02-01).
- Thẻ cũ (`BOOKING_LINES`, `QUOTE`, `ESTIMATE` dạng cũ) giữ nhánh hiện có.

## 2.2 Khung thẻ chung `CardShell`

| Phần | Quy định (DESIGN.md) |
|---|---|
| Nền | `bg-card elevation-sm rounded-2xl` (14 px), không viền màu, không gradient |
| Đầu thẻ | Tiêu đề 13 px semibold + `StatusBadge` theo `card.status` (`ACTIVE` không badge; `EXPIRED` "Đã hết hạn"; `SUPERSEDED` "Đã thay"; `COMPLETED` "Đã xong" / nhãn cụ thể của loại) |
| Số liệu | Tiền, km, giờ, mã lịch: `font-mono`; biển số: `PlateTile` |
| "Ước tính" | Mọi số tiền có `amountKind = ESTIMATE` có nhãn "ước tính" cạnh số (BR-CH02-04) |
| Nút | Từ `card.actions`: `PRIMARY` ⇒ `bg-brand text-on-brand`; `SECONDARY` ⇒ card + border; `DANGER` ⇒ chữ / viền lỗi. `status ≠ ACTIVE` ⇒ không render nút ngoài `actions` backend trả |
| Mobile 390 px | Nút xếp dọc full width dưới 400 px |
| Trình đọc màn hình | `role="group"` + `aria-label` = `fallbackText`; nút có nhãn đầy đủ |

## 2.3 Hành động

`features/assistant/cards/useCardAction.ts`:

| `kind` | Xử lý |
|---|---|
| `CHIP` | `useChipAction` (CH-01) với `chipId` |
| `API` | Bảng `api` → hàm: `PROPOSAL_CONFIRM/REVISE/CANCEL` (us-061 `useProposalActions`), `OPTION_SELECT` (BK-01), `PROACTIVE_CONFIRM` (BK-01), `CALENDAR_ADD` (BK-04), `EXTRA_DECIDE` (AD-04), `BOOKING_CANCEL` (mở `CancelBookingDialog` BK-02) |
| `LINK` | `navigate(href)` nội bộ hoặc `window.open` cho Google Maps / `tel:` |

Cờ in-flight theo `actionId`; trong lúc chạy mọi nút của thẻ disabled. Kết quả trả tin / thẻ mới ⇒ `dispatch('merge', …)`; thẻ cũ cập nhật `status` bằng `patchCard(messages, entity, patch)` (tổng quát hoá `patchProposalCard` của us-061).

## 2.4 Thẻ mới (render)

| Thẻ | Nội dung chính | Ghi chú |
|---|---|---|
| `SCHEDULE_OPTIONS` | Render `ScheduleOptionsList variant="chat"` (BK-01 FE §2.2) từ `data.options` + `dynamic` | Thẻ xưởng: tên, km, phút, đánh giá, phụ tùng (BK-09), số chỗ, lý do |
| `SLOT_PICKER` | Ngày + lưới khung (`SlotGrid` có sẵn) chỉ khung có chỗ | Nút khung là `CHIP` |
| `BOOKING_TICKET` | Mã (`font-mono`), xưởng, giờ, `BookingStatusBadge` có sẵn | Nút từ `actions` |
| `PROACTIVE_HOLD` | Như BK-01 SCR-BK01-04 rút gọn, đếm ngược `useCountdown(holdExpiresAt)`; hết giờ ở client ⇒ disabled nút Xác nhận và chờ backend xác nhận `EXPIRED` | |
| `SERVICE_HISTORY_ITEM` | HS-01 FE §2.5 | |
| `EXTRA_QUOTE` | AD-04 FE | |
| `EARLY_SERVICE` | BK-03 FE §2.1 | |

`BOOKING_PROPOSAL` giữ component us-061 (chuyển thư mục), thêm khối "Hạng mục gộp" khi `data.mergedItems` (HS-02).

## 2.5 Hiệu năng

Thẻ dựng ≤ 100 ms sau khi có payload (FF §18): không gọi API khi render (dữ liệu đã có trong `MessageDto`), component thẻ là hàm thuần của props; ảnh (AD-04) lazy-load.

---

# 3. API Integration & Errors

Không API mới. Lỗi của từng hành động theo spec API đích; lỗi chung ⇒ thông báo trong thẻ + "Thử lại" (gọi lại cùng hành động, an toàn vì API đích idempotent).

---

# 4. Acceptance Criteria (FE)

1. Con số trên thẻ = `card.data` / `card.dynamic` (test so sánh render với payload) (AC-CH02-01).
2. Thẻ `EXPIRED` không có nút Xác nhận, có "Tìm lại" khi backend trả (AC-CH02-02).
3. Thẻ cũ của cùng đối tượng không có nút (EDGE-CH02-01) — theo `actions = []` từ backend.
4. Loại / phiên bản lạ ⇒ hiện `fallbackText`, không lỗi trang.
5. Không dùng font / màu ngoài token DESIGN.md; hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `cards/registry.test.ts` | Router chọn renderer theo `type` + `version`; lạ ⇒ fallback | +3 |
| `cards/cardShell.test.tsx` | `renderToStaticMarkup`: badge theo `status`; nhãn "ước tính" khi `ESTIMATE` | +4 |
| `cards/patchCard.test.ts` | Cập nhật `status` thẻ cùng `entity` trong danh sách tin | +2 |
| `cards/useCardAction.test.ts` | Hàm thuần `resolveAction(action)` → handler đúng theo `kind` / `api`; in-flight chặn bấm trùng | +3 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| BR-CH02-01, AF-CH02-01 | §2.1 |
| BR-CH02-02, 04, 05, §8 | §2.2 |
| UC-CH02-02, EF-CH02-02 | §2.3 |
| UC-CH02-03, EF-CH02-01, AC-CH02-02, EDGE-CH02-01 | §2.2 (nút theo `actions`), §2.4 |

---

# 7. Analytics

`chat_card_rendered` (`type`, `status`), `chat_card_action` (`type`, `actionKind`, `label`), `chat_card_fallback` (`type`, `version`).

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
