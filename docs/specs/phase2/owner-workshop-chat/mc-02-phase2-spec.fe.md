# Frontend Technical Specification — Agent cùng tham gia luồng chat

> Frontend cho Feature `FEAT-P2-MC02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](mc-02-phase2-spec.ff.md). **API:** [API Spec](mc-02-phase2-spec.api.md) (`API-MC02-01..04`).
>
> **Tái dùng:** `BookingThreadView` (MC-01), `RobotAvatar` (DESIGN.md: gương mặt trợ lý chủ xe — dùng cho tin "Trợ lý EV Care" trong luồng vì đó cùng là trợ lý EV Care), pill nguồn + `CitationDrawer`, `CardShell` (CH-02).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-MC02` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | Tin agent trong SCR-MC01-01/02; nhãn gắn cờ (Workshop Portal); nút "Tóm tắt" (xưởng); cài đặt bật / tắt |
| Feature folder | `frontend/src/features/booking-thread/` (sửa) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Tin của agent

- Bong bóng `bg-card elevation-sm` + `RobotAvatar` (mood `idle`) + nhãn "Trợ lý EV Care" (luôn hiện, BR-MC02-01); nguồn dạng pill dưới hairline; thẻ CH-02 nếu có.
- Câu gắn cờ phía chủ xe: dòng phụ "Xưởng sẽ trả lời trong giờ làm việc".
- Thẻ an toàn (`SAFETY_ADVICE`, AD-02) render như ở chat chủ xe.

## 2.2 Gọi trợ lý trong giờ

Composer (chủ xe) gợi ý "@Trợ lý" khi gõ "@"; chip nhỏ "Hỏi trợ lý" chèn tiền tố "@Trợ lý ". Không có gợi ý này khi `agentEnabled = false`.

## 2.3 Phía xưởng

| Chỗ | Nội dung |
|---|---|
| Danh sách luồng | Nhãn "Cần xưởng trả lời" (và "Khẩn") khi có tin `flagged` (`API-MC02-04`) |
| Trong luồng | Tin chủ xe `flagged` có badge chữ "Cần trả lời" phía trên bong bóng (không dùng viền trái màu — DESIGN.md); hết khi `answered` |
| Nút "Tóm tắt" | Trên đầu luồng ⇒ `API-MC02-03` ⇒ hộp (drawer) "Tóm tắt (chỉ xưởng thấy)" với nội dung + "tới tin lúc {giờ}" |
| Bật / tắt | `BookingSettingsPage`: công tắc "Trợ lý EV Care trả lời khách ngoài giờ" (`API-MC02-01`) + checkbox "Áp dụng cho các cuộc trò chuyện đang mở"; trong luồng: menu "…" ⇒ "Tắt trợ lý cho cuộc trò chuyện này" (`API-MC02-02`) |

---

# 3. API Integration & Errors

`features/booking-thread/api.ts` thêm `setWorkshopThreadAgent`, `setThreadAgent`, `summarizeThread`, `listFlaggedMessages`.

| Lỗi | Xử lý |
|---|---|
| `THREAD_CLOSED` | Ẩn tuỳ chọn bật agent |
| `FORBIDDEN` | Ẩn nút tóm tắt (chủ xe) |

---

# 4. Acceptance Criteria (FE)

1. Tin agent luôn có nhãn "Trợ lý EV Care".
2. Tóm tắt không bao giờ render ở phía chủ xe.
3. Không dùng viền trái màu để đánh dấu tin gắn cờ (DESIGN.md).
4. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `booking-thread/agentMessageView.test.ts` | Nhãn, nguồn, dòng gắn cờ phía chủ xe | +3 |
| `booking-thread/mentionAssist.test.ts` | Gợi ý "@Trợ lý" chỉ khi `agentEnabled` | +2 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| BR-MC02-01, FF §8 | §2.1 |
| AF-MC02-01, BR-MC02-04 | §2.2 |
| UC-MC02-02, 04, BR-MC02-05, FF §3.1 | §2.3 |

---

# 7. Analytics

`thread_agent_mentioned`, `thread_flag_answered` (`minutesToAnswer`), `thread_summary_requested`, `ws_thread_agent_toggled`.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
