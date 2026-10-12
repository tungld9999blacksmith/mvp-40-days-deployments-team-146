# Entity Specification — Giải thích và phản hồi gợi ý

> Entity cho Feature `FEAT-P2-PS03`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-03-phase2-spec.ff.md). **API:** [API Spec](ps-03-phase2-spec.api.md).
>
> **Nguyên tắc:** lý do đã được lưu cùng phương án (`scheduling_option.reasons` + `score_breakdown`, BK-01) nên truy vết được (AC-PS03-01). PS-03 thêm: danh mục mẫu câu (code, không bảng) và bảng phản hồi "Không phù hợp".

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-PS03` — PS-03 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [ps-03-phase2-spec.ff.md](ps-03-phase2-spec.ff.md) |
| Related API | [ps-03-phase2-spec.api.md](ps-03-phase2-spec.api.md) |
| Related FE | [ps-03-phase2-spec.fe.md](ps-03-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-PS03-01` | `RecommendationFeedback` | `recommendation_feedback` | **Mới** |
| `ENT-BK01-04` | `SchedulingOption` | `scheduling_option` | BK-01 — đọc `reasons`, `score_breakdown`; trạng thái thêm `rejected` |

---

# 2. `recommendation_feedback` (ENT-PS03-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `target_type` | `varchar(16)` | No | — | `SCHEDULING_OPTION`, `MERGE_ITEM` (HS-02), `COHORT_SUGGESTION` (PS-04) |
| `target_id` | `varchar(80)` | No | — | Id phương án / mục |
| `workshop_id` | `uuid` | Yes | `NULL` | |
| `reason` | `varchar(20)` | No | — | `TOO_FAR`, `BAD_TIME`, `DISLIKE_WORKSHOP`, `TOO_EXPENSIVE`, `OTHER` |
| `note` | `varchar(200)` | Yes | `NULL` | Khi `OTHER` |
| `slot_weekday` / `slot_part` | `smallint` / `varchar(10)` | Yes | | Khi `BAD_TIME` (để đếm lặp theo thứ + buổi) |
| `applied_to_memory` | `boolean` | No | `false` | Đã thành mục nhớ PS-01 / ràng buộc BK-01 |
| `created_at` | `timestamptz` | No | `now()` | |

```sql
CREATE INDEX ix_reco_feedback_user ON recommendation_feedback (user_id, reason, created_at DESC);
ALTER TABLE recommendation_feedback ADD CONSTRAINT ck_reco_feedback_reason
  CHECK (reason IN ('TOO_FAR','BAD_TIME','DISLIKE_WORKSHOP','TOO_EXPENSIVE','OTHER'));
```

Thuộc dữ liệu `CONSENT_PERSONALIZATION_DATA` (PL-01): xoá theo eraser. Phản hồi vẫn được dùng **cho yêu cầu hiện tại** khi không có đồng ý (không lưu bảng — chỉ áp trong lượt, EDGE-PS03-01 và BR-PL01-05).

---

# 3. Danh mục mẫu câu lý do

Code `scheduler/reasons.py` — bảng ánh xạ mã → mẫu (BR-PS03-01, không LLM):

| Mã (`reasons[].code`) | Yếu tố điểm | Mẫu |
|---|---|---|
| `PREFERRED_WORKSHOP` | `PREFERRED` | "Đúng xưởng bạn thích" |
| `NEAREST` / `DISTANCE` | `DISTANCE` | "Cách {km} km" |
| `USUAL_TIME` | `USUAL_TIME` | "Đúng giờ bạn hay chọn" |
| `PREVIOUSLY_SATISFIED` | `AFFINITY` | "Bạn chấm {n} sao lần trước" |
| `HIGH_RATING` | `RATING` | "Được đánh giá {avg} sao" |
| `PARTS_IN_STOCK` | (BK-09) | "Có sẵn phụ tùng" |
| `FEW_SLOTS_LEFT` | (sức chứa, thông tin) | "Còn {n} chỗ" |
| `COHORT_POPULAR` | (PS-04) | "Nhiều chủ {model} trong khu vực chọn" |
| `IN_FREE_WINDOW` | ràng buộc cứng thoả | "Trong giờ rảnh {buổi} {thứ}" |
| `EARLIEST` | BK-03 quá hạn | "Khung sớm nhất vì xe đã quá hạn" |
| `DEFAULT_FIT` | — | "Phù hợp khung giờ và khu vực của bạn" (EF-PS03-01) |

Mẫu không chứa dữ liệu của chủ xe khác (FF §21); `COHORT_POPULAR` chỉ dùng số liệu nhóm đã ẩn danh của PS-04.

---

# 4. `scheduling_option.status` — giá trị mới

`rejected`: chủ xe bấm "Không phù hợp" trên phương án (BK-01 CHECK `ck_so_status` thêm giá trị).

---

# 5. Migration

Một revision: bảng mới, sửa CHECK `scheduling_option.status`.

---

# 6. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
