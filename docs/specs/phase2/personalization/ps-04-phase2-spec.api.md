# API Technical Specification — Gợi ý từ chủ xe có đặc điểm tương đồng

> Backend cho Feature `FEAT-P2-PS04`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-04-phase2-spec.ff.md). **Entity:** [Entity Spec](ps-04-phase2-spec.entity.md).
>
> **Tái dùng:** BK-01 chấm điểm (thêm yếu tố `COHORT`), HS-02 `MergeAdvisor` (nguồn gợi ý thêm), PS-03 `ReasonService` (lý do `COHORT_POPULAR`), PL-01 `ConsentService` (`CONSENT_PERSONALIZATION_DATA`), `vehicle_usage` (km / tháng), PS-02 `workshop_rating_summary`. Không có endpoint cho chủ xe (FF §8: không màn riêng).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-PS04` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/cohort/` (mới): `keys.py` (tính khoá), `aggregate.py` (job), `service.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `SVC-PS04-01` | Internal | `CohortService.signal_for(user, vehicle)` | Chỉ số nhóm cho một chủ xe (hoặc `None`) | UC-PS04-02 |
| `JOB-PS04-01` | Celery | `cohort.weekly_aggregate` (Thứ Hai 03:00) | Tính `cohort_metric` | UC-PS04-01 |
| `API-PS04-01` | `GET` | `/internal/cohorts?week` | Vận hành / Team Data xem nhóm (claim `ops`) | FF §16 |
| `API-PS04-02` | `GET` / `POST` | `/internal/cohort-definitions` | Xem / thêm phiên bản luật (Team Data) | BR-PS04-02 |

---

# 2. JOB-PS04-01 — tổng hợp

1. Lấy chủ xe có `CONSENT_PERSONALIZATION_DATA` hiệu lực (EF-PS04-02 — chủ xe tắt không được tính vào nhóm nào).
2. Tính khoá nhóm từng chủ xe (trong bộ nhớ của job; không ghi DB).
3. Với mỗi nhóm: đếm thành viên; dưới `min_cohort` ⇒ áp `coarsen` theo thứ tự; vẫn dưới ⇒ bỏ (AC-PS04-01).
4. Nhóm đạt: 180 ngày lịch `completed` của thành viên ⇒ `workshop_stats` (share, avgRating từ `follow_up`), `extra_item_stats`; `area_workshop_count`.
5. Ghi `cohort_metric` (chỉ số tổng hợp). Kiểm tự động: không có trường id người dùng / booking (AC-PS04-02).
6. Log `cohort.aggregated` (`cohorts`, `dropped_below_min`, `coverage_pct`).

---

# 3. SVC-PS04-01 — `signal_for`

- Không đồng ý ⇒ `None`.
- Tính khoá nhóm (cùng `keys.py`), tra `cohort_metric` tuần gần nhất (áp `coarsen` như job để khớp); không có ⇒ `None` (EF-PS04-01).
- Trả `{ cohortLabel: "chủ VF 8 ở Cầu Giấy", workshopShares: {id: share}, popularExtras: [...], areaWorkshopCount }`. `cohortLabel` chỉ gồm model + khu vực (không km, không kiểu sử dụng để tránh cảm giác bị theo dõi).

## 3.1 Dùng trong BK-01 (BR-PS04-04, 05)

Yếu tố mới `COHORT` trong chấm điểm: `f = share` của xưởng trong nhóm (0–1). Trọng số:
- Chủ xe **chưa** có lịch sử cá nhân (không xưởng yêu thích, không lịch hoàn tất, không tín hiệu PS-02) ⇒ `SCHEDULER_WEIGHTS.COHORT_COLD = 25`.
- Có lịch sử ⇒ `COHORT_WARM = 5`, và luôn ≤ trọng số nhỏ nhất của yếu tố cá nhân đang có (`PREFERRED`, `USUAL_TIME`, `AFFINITY`) (AF-PS04-01, BR-PS04-05).

Lý do `COHORT_POPULAR` "Nhiều chủ {model} trong khu vực chọn xưởng này" (PS-03) chỉ khi `share ≥ 0,3` **và** `areaWorkshopCount ≥ 3` (EDGE-PS04-01).

## 3.2 Dùng trong HS-02

`popularExtras` có trong gợi ý gộp với `source = COHORT`, **không chọn sẵn**, lý do "Nhiều chủ {model} thường làm thêm". Chỉ hạng mục xưởng làm được và chưa có trong lịch. (HS-02 entity: `merge_source` thêm `COHORT`.)

---

# 4. API-PS04-01/02 — nội bộ

- `GET /internal/cohorts` ⇒ danh sách `cohort_key`, `member_count`, top xưởng (id, share) — không thông tin cá nhân.
- `POST /internal/cohort-definitions` ⇒ phiên bản mới (`active = false`); kích hoạt bằng `PUT …/{version}/activate`; job tuần sau dùng phiên bản mới. Đổi luật ghi `change_note` (giống BR-PL03-06).

---

# 5. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Khoá nhóm; `coarsen` quận → tỉnh | +3 |
| Job | Nhóm < 30 không có dòng (AC-PS04-01); bảng không có id người dùng (AC-PS04-02) | +2 |
| Service | Tắt đồng ý ⇒ `None`, không tính vào nhóm | +2 |
| Service | Trọng số nhóm ≤ yếu tố cá nhân khi có lịch sử (BR-PS04-05) | +1 |
| Service | Khu vực ≤ 2 xưởng ⇒ không lý do "nhiều người chọn" | +1 |

---

# 6. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
