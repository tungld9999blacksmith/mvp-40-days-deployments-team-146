# Frontend Technical Specification — Giải thích và phản hồi gợi ý

> Frontend cho Feature `FEAT-P2-PS03` (SCR-PS03-01, SCR-PS03-02).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-03-phase2-spec.ff.md). **API:** [API Spec](ps-03-phase2-spec.api.md) (`API-PS03-01/02`).
>
> **Nguyên tắc:** hiển thị đúng `reasons[].text` backend trả; không hiển thị điểm khớp dạng số (Q-PS03-01).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-PS03` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-PS03-01 (dòng lý do trên thẻ phương án), SCR-PS03-02 (bảng "Không phù hợp") |
| Feature folder | `frontend/src/features/scheduler/` (sửa `ScheduleOptionsList`) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Dòng lý do (SCR-PS03-01)

Trong thẻ phương án (BK-01 FE §2.2): các lý do nối bằng " · " trên một dòng (ví dụ "Đúng xưởng bạn thích · Cách 2,1 km · Còn 3 chỗ"), xuống dòng trên 390 px; số trong lý do dùng `font-mono`. Cũng dùng ở mục gộp HS-02 và gợi ý nhóm PS-04.

## 2.2 "Không phù hợp" (SCR-PS03-02)

- Nút ghost nhỏ "Không phù hợp" trên mỗi thẻ phương án (cạnh "Chọn").
- Bottom sheet: 4 lý do nhanh dạng nút lớn — "Xa quá", "Giờ không tiện", "Không thích xưởng này", "Giá cao" — và "Khác" (ô chữ ≤ 200 ký tự).
- "Không thích xưởng này" ⇒ `422 CONFIRMATION_REQUIRED` ⇒ `DecisionSheet` "Ẩn {xưởng} khỏi gợi ý của bạn? Bạn gỡ được trong Thói quen đặt lịch." ⇒ gửi lại `confirmDislike = true`.
- Thành công ⇒ thay danh sách bằng `run` mới, toast "Đã ghi nhận, đây là gợi ý khác"; phương án bị từ chối không còn hiển thị.
- Chat: thẻ `SCHEDULE_OPTIONS` có cùng nút; kết quả `merge` thẻ mới.

---

# 3. API Integration & Errors

`features/scheduler/api.ts`: `sendOptionFeedback(optionId, body)`, `sendRecommendationFeedback(body)`.

| Lỗi | Xử lý |
|---|---|
| `CONFIRMATION_REQUIRED` | §2.2 |
| `OPTION_INACTIVE` | Chạy lại `runScheduler` |

---

# 4. Acceptance Criteria (FE)

1. Không có số điểm khớp nào trên UI.
2. Ẩn xưởng luôn qua xác nhận.
3. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `scheduler/reasonLine.test.ts` | Nối lý do, tối đa 3 | +2 |
| `scheduler/feedbackSheet.test.ts` | Ánh xạ nút → `reason`; `OTHER` cần ghi chú | +3 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-PS03-01, UC-PS03-01, Q-PS03-01 | §2.1 |
| SCR-PS03-02, UC-PS03-02, AF-PS03-01 | §2.2 |

---

# 7. Analytics

`option_feedback_opened`, `option_feedback_sent` (`reason`, `rank`).

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
