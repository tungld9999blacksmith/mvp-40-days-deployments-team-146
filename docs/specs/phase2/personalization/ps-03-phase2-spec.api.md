# API Technical Specification — Giải thích và phản hồi gợi ý

> Backend cho Feature `FEAT-P2-PS03`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-03-phase2-spec.ff.md). **Entity:** [Entity Spec](ps-03-phase2-spec.entity.md).
>
> **Tái dùng:** `engine.reasons` của BK-01 (chuyển thành `ReasonService` dùng chung), `SchedulerService.run` (đề xuất kế tiếp), `MemoryService.propose` (PS-01), ràng buộc loại trừ BK-01 / PS-02, PL-03 sự kiện `option_rejected`.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-PS03` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/scheduler/reasons.py`, `scheduler/feedback.py` (mới) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `SVC-PS03-01` | Internal | `ReasonService.for_option(option, ctx) → list[Reason]` | 1–3 lý do có thật | UC-PS03-01, BR-PS03-01 |
| `API-PS03-01` | `POST` | `/scheduling/options/{optionId}/feedback` | "Không phù hợp" + lý do ⇒ đề xuất kế tiếp | UC-PS03-02, BR-PS03-02..04 |
| `API-PS03-02` | `POST` | `/recommendations/feedback` | Phản hồi cho mục gộp (HS-02) / gợi ý nhóm (PS-04) | UC-PS03-02 |

---

# 2. SVC-PS03-01 — `ReasonService`

1. Từ `score_breakdown` của phương án: lấy các yếu tố có đóng góp > 0, sắp giảm dần, lấy tối đa 3; thêm lý do thông tin (`FEW_SLOTS_LEFT` khi `remaining_capacity ≤ 2`, `PARTS_IN_STOCK` khi BK-09 báo có) nếu còn chỗ.
2. Ánh xạ sang mẫu câu (entity §3). Không yếu tố nào > ngưỡng 5 điểm ⇒ `DEFAULT_FIT` (EF-PS03-01).
3. Mỗi lý do lưu kèm `factor` và `contribution` trong `scheduling_option.reasons` để truy vết (AC-PS03-01); log `reasons.generated` (`option_id`, `codes`, `factors`).
4. ≤ 50 ms cho 3 phương án (thuần, không truy vấn thêm ngoài dữ liệu đã có khi chấm điểm).

Dùng cho: BK-01 phương án, AD-01 cột so sánh (lý do xếp hạng), HS-02 mục gộp (`reason` riêng của HS-02), PS-04.

---

# 3. API-PS03-01 — "Không phù hợp"

## 3.1 Request

```json
{ "reason": "BAD_TIME", "note": null, "confirmDislike": false }
```

## 3.2 Processing

1. Phương án thuộc chủ xe, `status ∈ {offered, held}` ⇒ không thì `409 OPTION_INACTIVE`.
2. `reason = DISLIKE_WORKSHOP` và `confirmDislike = false` ⇒ `422 CONFIRMATION_REQUIRED` (`details.message` "Ẩn {xưởng} khỏi gợi ý của bạn?") — BR-PS03-03 (có xác nhận).
3. Ghi phản hồi: có `CONSENT_PERSONALIZATION_DATA` ⇒ chèn `recommendation_feedback`; không ⇒ chỉ dùng trong bước 4 (EDGE-PS03-01).
4. Phương án ⇒ `rejected`; phương án đang giữ (`held`) ⇒ trả chỗ (`PROACTIVE_HOLD_DISMISSED`, không tính điểm).
5. **Áp cho yêu cầu hiện tại** (BR-PS03-04), chạy lại `SchedulerService.run` cùng `trigger` + `overrides` cũ, thêm:

| Lý do | Áp ngay | Thành bộ nhớ / ràng buộc khi |
|---|---|---|
| `TOO_FAR` | `radiusKm = min(radius, distance_of_option − 0.5)` | Lặp ≥ `MEMORY_INFER_MIN_REPEAT` ⇒ đề xuất giảm bán kính hồ sơ (ràng buộc suy ra `pending_review`) |
| `BAD_TIME` | Loại khung (`excludeSlots`) và cùng buổi ngày đó | Lặp cùng (thứ, buổi) ⇒ PS-01 `preferred_time` tránh buổi đó (`INFERRED`) |
| `DISLIKE_WORKSHOP` | `excludeWorkshopIds += [xưởng]` | Ngay (đã xác nhận): ràng buộc `EXCLUDED_WORKSHOP`, `exclusion_source = NOT_SUITABLE` (AF-PS03-01) |
| `TOO_EXPENSIVE` | Tăng trọng số giá thấp cho lần chạy (AD-01 ước tính) nếu có giá; không thì không đổi | Không (Phase 2 chưa có ràng buộc giá) |
| `OTHER` | Loại phương án này | Không |

   Bộ nhớ chỉ ghi khi `CONSENT_LONG_TERM_MEMORY` hiệu lực (PS-01); `applied_to_memory = true`.
6. PL-03 `option_rejected` (`reason`, `rank`, `tier`).

## 3.3 Response `201`

`{ "data": { "run": RunDto } }` — đề xuất kế tiếp; với `BAD_TIME` không có phương án cùng khung (AC-PS03-02).

---

# 4. API-PS03-02 — phản hồi khác

`{ "targetType": "MERGE_ITEM" | "COHORT_SUGGESTION", "targetId": "…", "reason": "OTHER", "note": "…" }` ⇒ lưu (khi có đồng ý); HS-02: tương đương bỏ chọn + `merge_dismissal`; PS-04: ẩn gợi ý nhóm đó 90 ngày.

---

# 5. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 400 | `INVALID_REQUEST` | `reason` lạ, `OTHER` thiếu `note` > 200 |
| 404 | `OPTION_NOT_FOUND` | |
| 409 | `OPTION_INACTIVE` | |
| 422 | `CONFIRMATION_REQUIRED` | Ẩn xưởng chưa xác nhận |

---

# 6. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Lý do chỉ từ yếu tố > 0; tối đa 3; mặc định khi không có (AC-PS03-01) | +3 |
| Service | `BAD_TIME` ⇒ phương án kế không cùng khung (AC-PS03-02) | +1 |
| Service | `DISLIKE_WORKSHOP` cần xác nhận; sau xác nhận xưởng bị loại | +2 |
| Service | Lặp 2 lần `BAD_TIME` cùng buổi ⇒ mục nhớ suy ra; tắt bộ nhớ ⇒ không ghi (EDGE-PS03-01) | +2 |
| Perf | Sinh lý do ≤ 50 ms | +1 |

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
