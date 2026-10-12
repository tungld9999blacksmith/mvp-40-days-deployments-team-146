# Frontend Technical Specification — Agent trả lời theo phong cách giao tiếp

> Frontend cho Feature `FEAT-P2-PS05` (SCR-PS05-01).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-05-phase2-spec.ff.md). **API:** [API Spec](ps-05-phase2-spec.api.md) (`API-PS05-01/02`).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-PS05` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-PS05-01 (khối trong `/settings/memory`), chip "Xem chi tiết" trong chat |
| Feature folder | `frontend/src/features/memory/` (sửa), `features/assistant` (header) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Phong cách trả lời (SCR-PS05-01)

Khối "Phong cách trả lời" ở đầu `MemoryPage` (PS-01) và trong `MemoryDrawer`:

| Phần | Nội dung |
|---|---|
| Lựa chọn | Radio: "Tự động" (mặc định), "Ngắn gọn", "Chi tiết", "Dễ hiểu (ít thuật ngữ)" |
| Tự động | Dòng phụ hiện phong cách đang suy ra khi có: "Hiện tại: ngắn gọn" |
| Xưng hô | Link tới mục nhớ `addressing` (PS-01) |
| Câu cố định | "Phong cách chỉ đổi cách trình bày. Giá, số liệu, nguồn và cảnh báo an toàn luôn giữ nguyên." |

Lưu ⇒ `API-PS05-02`. Phản hồi `stored = CLIENT_ONLY` (bộ nhớ tắt) ⇒ lưu `localStorage` khoá `evcare.style.v1` (try/catch) và dòng "Lựa chọn chỉ lưu trên thiết bị này vì bạn đang tắt bộ nhớ".

## 2.2 Gửi kèm khi chat

`httpTransport` (features/assistant) đọc `evcare.style.v1` và gửi header `X-Style-Preference: SHORT|DETAILED|PLAIN` khi có (chỉ dùng khi server không đọc được mục nhớ).

## 2.3 "Xem chi tiết"

Tin trợ lý có `refs.style.length = SHORT` kèm chip "Xem chi tiết" (CH-01 chip do backend phát, intent `expand_last_answer`). Không xử lý riêng ở frontend ngoài `ChipRow`.

Thẻ `SAFETY_ADVICE` không bao giờ bị rút gọn (render như AD-02 bất kể phong cách).

---

# 3. Acceptance Criteria (FE)

1. Lựa chọn thủ công được gửi kèm khi bộ nhớ tắt.
2. Câu "Phong cách chỉ đổi cách trình bày…" luôn hiện.
3. `npm test`, `npx tsc --noEmit -p .` qua; hai theme, 390 px.

---

# 4. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `memory/styleSetting.test.ts` | Ánh xạ radio ↔ preset; `CLIENT_ONLY` lưu cục bộ (storage giả, lỗi không throw) | +3 |
| `assistant/transport/stylePreference.test.ts` | Header chỉ gửi khi có lựa chọn | +2 |

---

# 5. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-PS05-01, UC-PS05-02, BR-PS05-03 | §2.1, §2.2 |
| BR-PS05-02, EF-PS05-01 | §2.3 |
| UC-PS05-03 | PL-02 FE §2.1 (chip "Gặp người của xưởng") |

---

# 6. Analytics

`style_preference_set` (`preset`, `stored`), `expand_answer_clicked`.

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
