# Frontend Technical Specification — Gộp việc vào một lần đến xưởng

> Frontend cho Feature `FEAT-P2-HS02` (SCR-HS02-01).
>
> **Nguồn nghiệp vụ:** [Functional Spec](hs-02-phase2-spec.ff.md). **API:** [API Spec](hs-02-phase2-spec.api.md) (`API-HS02-01..03`, khối gộp trong `BOOKING_PROPOSAL`).
>
> **Nguyên tắc:** không bao giờ chọn sẵn mục tính phí; chỉ mục backend đánh dấu `preselected` (triệu hồi miễn phí) được tick sẵn. Không ngôn ngữ bán thêm.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-HS02` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-HS02-01 (khối "Làm luôn lần này?" trong thẻ đề xuất chat và màn `/booking/confirm`) |
| Feature folder | `frontend/src/features/bookings/merge/` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `MergeSuggestions` (SCR-HS02-01)

Dùng trong `BookingProposalCard` (chat, dưới khối thời gian) và `BookingConfirm` (wizard, trên khối chi phí; rail `BookingSummaryRail` hiện tổng thời lượng).

| Vùng | Nội dung |
|---|---|
| Tiêu đề | "Làm luôn lần này?" + câu phụ "Gộp để bớt một lần đến xưởng" |
| Mỗi dòng | Checkbox, tên, lý do (badge chữ: "Triệu hồi của hãng" / "Đến hạn 15/11" / "Xưởng đề xuất lần trước"), chi phí (`font-mono`, "Miễn phí" hoặc "~{estimate} ước tính"), "+{durationMin} phút" |
| Tổng | "Thời gian dự kiến: {totalDurationMin} phút" — cập nhật theo phản hồi server, không cộng ở client |
| Trạng thái | `preselected` ⇒ tick sẵn; còn lại bỏ tick |

**Áp dụng:** thay đổi tick ⇒ debounce 500 ms ⇒ chat: `API-HS02-02`; wizard: giữ trong state và gửi `mergedItems` khi xác nhận (gọi `API-HS02-01` lại để lấy thời lượng mới). Bỏ tick mục `preselected` ⇒ gửi kèm `deselectedDefaults`.

**Khung không đủ (AF-HS02-01):** `MERGE_SLOT_TOO_SHORT` ⇒ hộp "Khung {giờ} không đủ thời gian cho các việc đã chọn" với hai lựa chọn: "Giữ {giờ}, không gộp" (bỏ các tick mới) hoặc danh sách phương án từ `details.run` (`ScheduleOptionsList`).

---

# 3. API Integration & Errors

`features/bookings/merge/api.ts`: `getMergeSuggestions`, `applyMergeToProposal`; `createBooking` thêm `mergedItems`.

| Lỗi | Xử lý |
|---|---|
| `MERGE_SLOT_TOO_SHORT` | §2.1 |
| `MERGE_ITEM_INVALID` | Tải lại gợi ý, toast "Gợi ý đã thay đổi" |
| `PROPOSAL_EXPIRED` | Theo us-061 |

---

# 4. Acceptance Criteria (FE)

1. Không mục tính phí nào được tick sẵn (test với dữ liệu có `preselected = false`).
2. Tổng thời lượng lấy từ server.
3. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `bookings/merge/mergeView.test.ts` | Tick sẵn đúng `preselected`; nhãn chi phí; `deselectedDefaults` tính đúng | +4 |
| `bookings/merge/MergeSuggestions.test.tsx` | `renderToStaticMarkup`: mục tính phí không `checked` | +1 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-HS02-01, UC-HS02-01, BR-HS02-05 | §2.1 |
| UC-HS02-02, AF-HS02-01 | §2.1 áp dụng / khung không đủ |

---

# 7. Analytics

`merge_suggestions_shown` (`count`, `sources`), `merge_item_toggled` (`source`, `selected`), `merge_slot_too_short`.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
