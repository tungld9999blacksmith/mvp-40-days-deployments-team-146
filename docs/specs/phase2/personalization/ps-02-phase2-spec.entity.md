# Entity Specification — Cá nhân hoá theo phản hồi dịch vụ

> Entity cho Feature `FEAT-P2-PS02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-02-phase2-spec.ff.md). **API:** [API Spec](ps-02-phase2-spec.api.md).
>
> **Nguyên tắc:** điểm vẫn ở `follow_up.rating` (us-041, ENT-417), mỗi booking một lần. "Xưởng đã ẩn" của chủ xe **không** tạo bảng `owner_hidden_workshop` như FF §14 gợi ý mà dùng ràng buộc `EXCLUDED_WORKSHOP` của hồ sơ BK-01 (`owner_scheduling_constraint`, `exclusion_source = LOW_RATING`) — bộ lập lịch đã lọc theo bảng này (BR-BK01-13), tránh hai nguồn loại trừ. Tín hiệu ưu tiên theo từng chủ xe và điểm xưởng là bảng mới.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-PS02` — PS-02 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [ps-02-phase2-spec.ff.md](ps-02-phase2-spec.ff.md) |
| Related API | [ps-02-phase2-spec.api.md](ps-02-phase2-spec.api.md) |
| Related FE | [ps-02-phase2-spec.fe.md](ps-02-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-PS02-01` | `ReviewTag` | `review_tag` | **Mới** — tag gắn `follow_up` |
| `ENT-PS02-02` | `OwnerWorkshopPreferenceSignal` | `owner_workshop_preference_signal` | **Mới** — ưu tiên theo từng chủ xe |
| `ENT-PS02-03` | `WorkshopRatingSummary` | `workshop_rating_summary` | **Mới** — điểm xưởng 90 ngày (đệm) |
| `ENT-PS02-04` | `WorkshopWeeklyReviewReport` | `workshop_weekly_review_report` | **Mới** — báo cáo tuần |
| `ENT-417` | `FollowUp` | `follow_up` — **thêm cột** `rating_edited_at` | Có sẵn |
| `ENT-BK01-02` | `OwnerSchedulingConstraint` | dòng `EXCLUDED_WORKSHOP`, `exclusion_source = LOW_RATING` | BK-01 |

---

# 2. `review_tag` (ENT-PS02-01)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `follow_up_id` | `uuid` | No | PK (1/2), FK `follow_up.id` `ON DELETE CASCADE` |
| `tag` | `varchar(24)` | No | PK (2/2), §2.1 |

## 2.1 Danh mục tag (Q-PS02-01)

| `tag` | Nhãn | Nhóm | Hiện khi |
|---|---|---|---|
| `ON_TIME` | Đúng giờ | Tích cực | ≥ 4 sao |
| `PRICE_AS_QUOTED` | Giá đúng báo giá | Tích cực | ≥ 4 sao |
| `GOOD_QUALITY` | Chất lượng tốt | Tích cực | ≥ 4 sao |
| `GOOD_ATTITUDE` | Thái độ tốt | Tích cực | ≥ 4 sao |
| `CLEAN` | Sạch sẽ | Tích cực | ≥ 4 sao |
| `LONG_WAIT` | Chờ lâu | Cần cải thiện | ≤ 3 sao |
| `PRICE_ABOVE_QUOTE` | Giá cao hơn báo giá | Cần cải thiện | ≤ 3 sao |
| `NOT_THOROUGH` | Làm chưa kỹ | Cần cải thiện | ≤ 3 sao |
| `POOR_ATTITUDE` | Thái độ chưa tốt | Cần cải thiện | ≤ 3 sao |

Danh mục là enum trong code (`follow_up/review_tags.py`); tag không khớp nhóm với số sao bị từ chối.

---

# 3. `owner_workshop_preference_signal` (ENT-PS02-02)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `user_id` | `bigint` | No | PK (1/2), FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `workshop_id` | `uuid` | No | PK (2/2), FK `workshop.id` `ON DELETE CASCADE` |
| `affinity` | `smallint` | No | `+1` (đánh giá ≥ 4, BR-PS02-02); chỉ lưu tín hiệu tích cực — tiêu cực đi vào ràng buộc loại trừ BK-01 |
| `last_rating` | `smallint` | No | |
| `source_follow_up_id` | `uuid` | No | FK `follow_up.id` `ON DELETE CASCADE` |
| `updated_at` | `timestamptz` | No | |

Thuộc dữ liệu `CONSENT_PERSONALIZATION_DATA` (PL-01): chỉ ghi / đọc khi đồng ý hiệu lực; eraser PL-01 xoá bảng này. Ràng buộc loại trừ do điểm thấp là **lựa chọn của chủ xe về xưởng** nên giữ cả khi tắt đồng ý (chủ xe tự gỡ ở SCR-PS02-03).

---

# 4. `workshop_rating_summary` (ENT-PS02-03)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `workshop_id` | `uuid` | No | PK |
| `avg_rating_90d` | `numeric(3,2)` | Yes | `NULL` khi `count_90d < MIN_REVIEWS` (EF-PS02-01) |
| `count_90d` | `integer` | No | |
| `distribution` | `jsonb` | No | `{ "1": 0, …, "5": 12 }` |
| `computed_at` | `timestamptz` | No | |

Tính lại khi có đánh giá mới (ngay, BR §18) và hằng đêm (đánh giá rơi khỏi 90 ngày). `WorkshopRatingService.get(workshop_id)` đọc bảng này (dùng ở BK-01 yếu tố `RATING`, BK-05 thẻ xưởng).

---

# 5. `workshop_weekly_review_report` (ENT-PS02-04)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `workshop_id` | `uuid` | No | PK (1/2) |
| `week_start` | `date` | No | PK (2/2) |
| `avg_rating` | `numeric(3,2)` | Yes | |
| `review_count` | `integer` | No | |
| `distribution` | `jsonb` | No | |
| `top_positive_tags` / `top_improve_tags` | `jsonb` | No | `[{ tag, count }]` |
| `created_at` | `timestamptz` | No | |

Không có cột hay dữ liệu định danh khách (BR-PS02-05, AC-PS02-03); không trích bình luận tự do.

---

# 6. `follow_up` — cột mới

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `rating_edited_at` | `timestamptz` | Yes | Sửa một lần trong 24 giờ (EDGE-PS02-02) |

---

# 7. Migration

Một revision: 4 bảng, 1 cột. Backfill `workshop_rating_summary` từ `follow_up` 90 ngày.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
