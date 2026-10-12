# Entity Specification — Gợi ý từ chủ xe có đặc điểm tương đồng

> Entity cho Feature `FEAT-P2-PS04`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-04-phase2-spec.ff.md). **API:** [API Spec](ps-04-phase2-spec.api.md).
>
> **Nguyên tắc (BR-PS04-03, AC-PS04-02):** **không lưu thành viên nhóm**. Khoá nhóm của một chủ xe được tính tại thời điểm dùng từ thuộc tính xe / hồ sơ; bảng chỉ lưu số liệu **tổng hợp** của nhóm đủ ngưỡng `MIN_COHORT`. Không cột nào chứa định danh chủ xe hay id lịch hẹn.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-PS04` — PS-04 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team · Data Owner: Team Data (Phase 2) |
| Created Date | `2026-10-12` |
| Related FF | [ps-04-phase2-spec.ff.md](ps-04-phase2-spec.ff.md) |
| Related API | [ps-04-phase2-spec.api.md](ps-04-phase2-spec.api.md) |
| Related FE | [ps-04-phase2-spec.fe.md](ps-04-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-PS04-01` | `CohortDefinition` | `cohort_definition` | **Mới** — luật phân nhóm có phiên bản |
| `ENT-PS04-02` | `CohortMetric` | `cohort_metric` | **Mới** — chỉ số tổng hợp mỗi nhóm mỗi tuần |

---

# 2. `cohort_definition` (ENT-PS04-01)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `version` | `smallint` | No | PK |
| `rules` | `jsonb` | No | §2.1 |
| `min_cohort` | `smallint` | No | `MIN_COHORT` lúc áp dụng (30) |
| `active` | `boolean` | No | Đúng một phiên bản `active` |
| `created_by` | `varchar(60)` | No | Team Data |
| `change_note` | `text` | No | |
| `created_at` | `timestamptz` | No | |

## 2.1 `rules` (v1, theo luật — BR-PS04-01, 02)

```json
{ "dimensions": [
    { "name": "model", "source": "user_vehicle.model_id" },
    { "name": "area", "source": "district", "fallback": "province" },
    { "name": "kmBand", "source": "monthly_km", "bands": [0, 500, 1000, 2000, 3000, 999999] },
    { "name": "usage", "source": "usage_type", "values": ["PERSONAL", "COMMERCIAL", "UNKNOWN"] } ],
  "coarsen": ["area:district->province", "kmBand:merge-adjacent"] }
```

- `area`: quận / huyện từ điểm neo hồ sơ BK-01 hoặc PS-01 `location_anchor` (không toạ độ); không có ⇒ tỉnh của xưởng hay đến; không có nữa ⇒ không gán nhóm.
- `monthly_km`: dự báo km / tháng có sẵn (`vehicle_usage`).
- `usage_type`: thuộc tính xe nếu hãng / hồ sơ có (Q-ENT-PS04-01); không có ⇒ `UNKNOWN`.
- `coarsen`: nhóm dưới ngưỡng thì gộp dần (quận → tỉnh, gộp dải km kề) trước khi bỏ.

Khoá nhóm: `"{model}|{area}|{kmBand}|{usage}"` (chuỗi mô tả nhóm, không định danh người).

---

# 3. `cohort_metric` (ENT-PS04-02)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `cohort_key` | `varchar(160)` | No | PK (1/3) |
| `definition_version` | `smallint` | No | PK (2/3) |
| `week_start` | `date` | No | PK (3/3) |
| `member_count` | `integer` | No | `≥ min_cohort` (không lưu nhóm dưới ngưỡng — AC-PS04-01) |
| `workshop_stats` | `jsonb` | No | `[{ workshopId, share, bookings, avgRating, ratingCount }]` top 5; chỉ xưởng có ≥ 5 lịch từ nhóm |
| `extra_item_stats` | `jsonb` | No | `[{ itemCode, share }]` hạng mục làm thêm phổ biến (từ dòng `EXTRA` / gộp HS-02 được chấp nhận), `share ≥ 10 %` |
| `area_workshop_count` | `smallint` | No | Số xưởng `ACTIVE` trong khu vực của nhóm (EDGE-PS04-01) |
| `computed_at` | `timestamptz` | No | |

```sql
CREATE INDEX ix_cohort_metric_latest ON cohort_metric (cohort_key, week_start DESC);
ALTER TABLE cohort_metric ADD CONSTRAINT ck_cohort_min CHECK (member_count >= 30);
```

`CHECK` dùng hằng số v1; tăng `MIN_COHORT` ⇒ migration sửa CHECK.

---

# 4. Retention

`cohort_metric` giữ 26 tuần; xuất sang workspace Team Data qua PL-03.

---

# 5. Open Questions

| ID | Câu hỏi | Đề xuất |
|---|---|---|
| `Q-ENT-PS04-01` | Nguồn "kiểu sử dụng" (cá nhân / dịch vụ)? | Hỏi hãng (mock) hoặc thêm câu hỏi tuỳ chọn ở onboarding; trước đó `UNKNOWN` |

---

# 6. Migration

Một revision: 2 bảng; seed `cohort_definition` v1.

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
