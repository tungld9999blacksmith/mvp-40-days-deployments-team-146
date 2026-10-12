# Frontend Technical Specification — Gợi ý từ chủ xe có đặc điểm tương đồng

> Frontend cho Feature `FEAT-P2-PS04`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-04-phase2-spec.ff.md). **API:** [API Spec](ps-04-phase2-spec.api.md).
>
> **Phạm vi:** FF §8 — **không có màn riêng**. Gợi ý nhóm chỉ hiện qua lý do trên thẻ đề xuất (PS-03) và mục gộp (HS-02). Tài liệu này ghi các điểm chạm nhỏ để frontend không tự dựng thêm.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-PS04` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | Không màn mới; dùng `ScheduleOptionsList` (BK-01 / PS-03), `MergeSuggestions` (HS-02) |
| Created Date | `2026-10-12` |

---

# 2. Điểm chạm

| Chỗ | Hành vi |
|---|---|
| Thẻ phương án | Lý do `COHORT_POPULAR` hiển thị như mọi lý do khác (PS-03 FE §2.1); không thêm icon "nhóm" hay số người |
| Mục gộp HS-02 | `source = COHORT` hiển thị badge lý do "Nhiều chủ {model} thường làm thêm"; **không** tick sẵn |
| "Không phù hợp" | Trên mục gộp nhóm ⇒ `POST /recommendations/feedback` (`targetType = COHORT_SUGGESTION`, PS-03) |
| Quyền riêng tư | Giải thích của công tắc `CONSENT_PERSONALIZATION_DATA` (PL-01 FE §2.6) đã bao gồm "gợi ý theo nhóm chủ xe tương đồng" — cập nhật câu: "Dùng đánh giá, phản hồi và dữ liệu ẩn danh của các chủ xe tương tự để gợi ý xưởng, khung giờ phù hợp hơn." |

Trang nội bộ `/internal/metrics` (PL-03) có thể thêm tab "Nhóm" đọc `GET /internal/cohorts` — tuỳ chọn, chỉ claim `ops`.

---

# 3. Acceptance Criteria (FE)

1. Không có thông tin nào về chủ xe khác (tên, số người cụ thể) trên UI chủ xe.
2. Mục gộp nguồn nhóm không tick sẵn.
3. `npm test`, `npx tsc --noEmit -p .` qua.

---

# 4. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `bookings/merge/mergeView.test.ts` (mở rộng) | `source = COHORT` không tick sẵn, nhãn lý do | +1 |

---

# 5. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
