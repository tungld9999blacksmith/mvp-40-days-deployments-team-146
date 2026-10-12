# Frontend Technical Specification — Cá nhân hoá theo phản hồi dịch vụ

> Frontend cho Feature `FEAT-P2-PS02` (SCR-PS02-01..03).
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-02-phase2-spec.ff.md). **API:** [API Spec](ps-02-phase2-spec.api.md) (`API-PS02-01..06`).

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-PS02` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-PS02-01 (sửa `/follow-ups/:followUpId`), SCR-PS02-02 (Workshop Portal), SCR-PS02-03 (khối trong `/settings/scheduling`) |
| Routes | `/technician/reviews` (mới) |
| Feature folder | `frontend/src/features/after-service/` (sửa), `features/workshop-board/` |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 Hỏi thăm có tag (SCR-PS02-01)

`features/after-service` (trang `FollowUp`): sau khi chọn sao, hiện chip tag (`API-PS02-03` theo số sao — chọn nhiều, nút toggle `aria-pressed`, 44 px). Đổi số sao sang nhóm khác ⇒ xoá tag không còn hợp lệ. Gửi cùng phản hồi.

Sau gửi, theo `effects`:
- `workshopHidden` ⇒ dòng "Mình sẽ không gợi ý {xưởng} cho bạn nữa. [Hoàn tác]" (Hoàn tác = `API-PS02-05`).
- `handoffCreated` ⇒ dòng "Xưởng sẽ liên hệ bạn" (PL-02).
- Trong 24 giờ: nút "Sửa đánh giá" (một lần) ⇒ `API-PS02-02`.

Câu hỏi xưởng yêu thích (EF-PS02-02): thông báo + `DecisionSheet` "Bỏ {xưởng} khỏi xưởng yêu thích?" (Có ⇒ `PUT /scheduling/profile`; Không ⇒ giữ).

## 2.2 Xưởng đã ẩn (SCR-PS02-03)

Trong `SchedulingProfilePage` (BK-01 FE §2.1, khối "Xưởng đã loại"): danh sách từ `API-PS02-04` với lý do ("Bạn chấm thấp", "Bạn đánh dấu không phù hợp", "Bạn tự ẩn") + nút "Gợi ý lại".

Khi BK-01 trả `prompt = UNHIDE_WORKSHOP` (chủ xe tự chọn xưởng đã ẩn) ⇒ hỏi "Gợi ý lại xưởng này từ nay?" (Có ⇒ `API-PS02-05`). Khi `reason = ALL_EXCLUDED` ⇒ `RelaxationPanel` hiện nút "Gợi ý lại các xưởng đã ẩn".

## 2.3 Báo cáo tuần (SCR-PS02-02)

Route `/technician/reviews`; link từ `TechnicianDashboard` và thông báo tuần.
- Thẻ tổng: điểm trung bình 90 ngày (`font-mono`), số đánh giá, phân bố 5 thanh ngang (SVG thuần, nhãn số).
- Theo tuần (8 tuần): điểm + số đánh giá; tuần ít đánh giá có ghi chú.
- Top tag "Khách khen" / "Cần cải thiện" với số lần.
- Không có danh tính khách ở bất kỳ đâu.

---

# 3. API Integration & Errors

`features/after-service/api.ts`: `submitFollowUp` thêm `tags`, `editRating`, `getReviewTags`; `features/scheduler/api.ts`: `listHiddenWorkshops`, `unhideWorkshop`; `features/workshop-board/api.ts`: `getReviewReports`.

| Lỗi | Xử lý |
|---|---|
| `INVALID_TAGS` | Tải lại tag, giữ số sao |
| `RATING_EDIT_NOT_ALLOWED` | Ẩn nút sửa |

---

# 4. Acceptance Criteria (FE)

1. Tag hiện đúng nhóm theo số sao.
2. Báo cáo tuần không render tên / SĐT / biển số (snapshot).
3. Hai theme, 390 px; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `after-service/reviewTags.test.ts` | `tagsForRating`, lọc tag khi đổi sao | +3 |
| `after-service/effectsView.test.ts` | Thông điệp theo `effects` | +3 |
| `workshop-board/reviewReport.test.ts` | Phân bố, ghi chú tuần ít đánh giá | +2 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| SCR-PS02-01, UC-PS02-01, EDGE-PS02-02, EF-PS02-02 | §2.1 |
| SCR-PS02-03, AF-PS02-01, EDGE-PS02-01 | §2.2 |
| SCR-PS02-02, UC-PS02-03, BR-PS02-05 | §2.3 |

---

# 7. Analytics

`review_tags_selected` (`rating`, `count`), `workshop_unhidden` (`reason`), `rating_edited`, `ws_review_report_viewed`.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
