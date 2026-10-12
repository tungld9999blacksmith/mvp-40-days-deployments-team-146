# API Technical Specification — Cá nhân hoá theo phản hồi dịch vụ

> Backend cho Feature `FEAT-P2-PS02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-02-phase2-spec.ff.md). **Entity:** [Entity Spec](ps-02-phase2-spec.entity.md).
>
> **Tái dùng:** hỏi thăm sau dịch vụ F9 (`modules/follow_up`: route gửi phản hồi, `classifier.py`, BR-006 một booking một lần), BK-01 hồ sơ (`owner_scheduling_constraint`) và chấm điểm, PL-02 `HandoffService` (điểm thấp), PL-01 `ConsentService`, thông báo Workshop Portal + email chủ xưởng.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-PS02` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/follow_up/` (mở rộng: `review_tags.py`, `ratings.py`), `modules/scheduler` (đọc tín hiệu) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-PS02-01` | `POST` | `/follow-ups/{followUpId}/response` (sửa, us-041) | Nhận `rating` + `tags[]` | UC-PS02-01, BR-PS02-01 |
| `API-PS02-02` | `PATCH` | `/follow-ups/{followUpId}/rating` | Sửa điểm một lần trong 24 giờ | EDGE-PS02-02 |
| `API-PS02-03` | `GET` | `/review-tags?rating` | Danh mục tag theo số sao | SCR-PS02-01 |
| `API-PS02-04` | `GET` | `/scheduling/hidden-workshops` | Xưởng đã ẩn (SCR-PS02-03) | — |
| `API-PS02-05` | `DELETE` | `/scheduling/hidden-workshops/{workshopId}` | "Gợi ý lại" | AF-PS02-01 |
| `API-PS02-06` | `GET` | `/workshop-owner/review-reports?weeks=8` | Báo cáo tuần (SCR-PS02-02) | UC-PS02-03 |
| `HOOK-PS02-01` | Internal | `on_rating_recorded(follow_up)` | Áp quy tắc ngay | UC-PS02-02, BR-PS02-02 |
| `JOB-PS02-01` | Celery | `reviews.weekly_report` (Thứ Hai 07:00) | Tổng hợp + gửi chủ xưởng | BR-PS02-03 |
| `JOB-PS02-02` | Celery | `reviews.recompute_summary` (02:00) | Điểm 90 ngày | BR-PS02-03 |

---

# 2. Authorization & Guards

Chủ xe: follow-up của mình (booking `completed`, BR-PS02-04). Chủ xưởng: báo cáo xưởng mình, không danh tính (BR-PS02-05).

---

# 3. API-PS02-01 — phản hồi có tag (sửa)

Thêm `tags: string[]` (0–5) vào body hiện có. Kiểm: tag thuộc danh mục và đúng nhóm theo `rating` (≥ 4 ⇒ tích cực; ≤ 3 ⇒ cần cải thiện) ⇒ không thì `400 INVALID_TAGS`. Lưu `review_tag` cùng transaction với `follow_up.rating`. Sau commit: `HOOK-PS02-01`. Phản hồi thêm `effects` để frontend báo cho chủ xe:

```json
{ "effects": { "workshopHidden": true, "preferredWorkshopRemoved": false, "handoffCreated": true } }
```

---

# 4. HOOK-PS02-01 — áp quy tắc (ngay, FF §18)

1. `rating ≤ LOW_RATING_MAX`:
   - Upsert `owner_scheduling_constraint (EXCLUDED_WORKSHOP, workshop_id, exclusion_source = LOW_RATING, source = USER)` (AC-PS02-01). Không cần đồng ý vì đây là lựa chọn của chủ xe (entity §3).
   - Xưởng là xưởng yêu thích (BK-01 hồ sơ / PS-01) ⇒ **không tự bỏ**; gắn `owner_scheduling_profile.needs_review = true` và thông báo "Bỏ {xưởng} khỏi xưởng yêu thích?" (EF-PS02-02 — "hỏi chủ xe xác nhận").
   - PL-02 `create(reason = LOW_RATING)` (đã có hook PL-02 trên follow-up; không tạo trùng).
   - PS-01: `propose(service_feedback, source = FEEDBACK)` khi có đồng ý bộ nhớ.
2. `rating ≥ 4` và `CONSENT_PERSONALIZATION_DATA` hiệu lực ⇒ upsert `owner_workshop_preference_signal (affinity = +1)`; xoá ràng buộc loại trừ `LOW_RATING` cũ của cùng xưởng nếu có (chủ xe đã quay lại và hài lòng).
3. Cập nhật `workshop_rating_summary` của xưởng.

**BK-01 dùng tín hiệu:** yếu tố mới `AFFINITY` trong chấm điểm (BK-01 API §4.2 bước 8): `f = 1` khi có tín hiệu `+1` cho xưởng, trọng số `SCHEDULER_WEIGHTS.AFFINITY = 10` (cấu hình); lý do `PREVIOUSLY_SATISFIED` "Bạn từng hài lòng ở xưởng này". Yếu tố `RATING` chỉ dùng `avg_rating_90d` khi `count_90d ≥ MIN_REVIEWS` (AC-PS02-02).

**EDGE-PS02-01:** BK-01 thấy mọi xưởng trong bán kính đều bị loại (`rejected_by.EXCLUDED` = toàn bộ) ⇒ `NO_OPTION` với `reason = ALL_EXCLUDED` và `relaxationOffers` thêm `UNHIDE_WORKSHOPS` (kèm danh sách) — chủ xe chọn mới gỡ.

---

# 5. API-PS02-02 — sửa điểm

Trong 24 giờ sau lần đánh giá đầu, `rating_edited_at IS NULL` ⇒ cho sửa `rating` + `tags` một lần; chạy lại hook theo điểm mới (gỡ loại trừ / tín hiệu cũ nếu không còn đúng). Quá hạn / đã sửa ⇒ `409 RATING_EDIT_NOT_ALLOWED`.

---

# 6. Xưởng đã ẩn — API-PS02-04/05

- `GET` ⇒ `[{ workshopId, name, reason: "LOW_RATING" | "NOT_SUITABLE" | "USER", since }]` từ `owner_scheduling_constraint` (`EXCLUDED_WORKSHOP`).
- `DELETE` ⇒ `status = rejected` cho dòng loại trừ (AF-PS02-01). Bộ lập lịch dùng lại xưởng từ lần chạy sau.
- AF-PS02-01 (chủ xe tự chọn xưởng đã ẩn ở wizard / bản đồ): cho phép; `POST /scheduling/runs` với `overrides.workshopId` của xưởng bị ẩn ⇒ BK-01 bỏ qua loại trừ cho lần đó và trả `prompt: "UNHIDE_WORKSHOP"` để frontend hỏi "Gợi ý lại xưởng này từ nay?".

---

# 7. Báo cáo tuần — JOB-PS02-01 / API-PS02-06

- Tổng hợp tuần trước theo xưởng: số đánh giá, trung bình, phân bố, top 3 tag mỗi nhóm ⇒ `workshop_weekly_review_report`; tuần < 3 đánh giá ⇒ vẫn lưu nhưng ghi "Ít đánh giá, chưa đủ để kết luận".
- Thông báo Workshop Portal + email "Báo cáo đánh giá tuần".
- `GET` trả 8 tuần gần nhất + tổng 90 ngày. Không có tên, SĐT, biển số, mã lịch (AC-PS02-03 — test quét payload).

---

# 8. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 400 | `INVALID_TAGS` | Tag lạ / sai nhóm |
| 404 | `FOLLOW_UP_NOT_FOUND` | |
| 409 | `RATING_EDIT_NOT_ALLOWED` | |

---

# 9. Test Checklist

| Layer | What | Count |
|---|---|---|
| Service | Chấm 1 sao ⇒ lần đặt sau không có xưởng đó (AC-PS02-01) | +1 |
| Service | Xưởng < `MIN_REVIEWS` không ảnh hưởng xếp hạng chung (AC-PS02-02) | +1 |
| Service | Xưởng yêu thích bị chấm thấp ⇒ hỏi, không tự bỏ (EF-PS02-02) | +1 |
| Service | Sửa điểm trong 24 giờ một lần; hook áp theo điểm mới | +2 |
| Service | Tắt `CONSENT_PERSONALIZATION_DATA` ⇒ không ghi tín hiệu `+1`, loại trừ vẫn áp | +1 |
| Job | Báo cáo không chứa dữ liệu định danh (AC-PS02-03) | +1 |
| Unit | Tag sai nhóm ⇒ `400` | +2 |

---

# 10. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
