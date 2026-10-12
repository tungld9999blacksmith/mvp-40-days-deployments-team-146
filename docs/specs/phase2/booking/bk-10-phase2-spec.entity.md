# Entity Specification — Tối ưu hoá lập lịch

> Entity cho Feature `FEAT-P2-BK10`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-10-phase2-spec.ff.md). **API:** [API Spec](bk-10-phase2-spec.api.md).
>
> **Nguyên tắc:** bộ tối ưu chỉ thay **xếp hạng và gán** (BR-BK10-01). Ràng buộc cứng, giữ chỗ, sức chứa vẫn do BK-01 / WS-02 / WS-03 quyết định; lời giải luôn được kiểm lại bằng chính các hàm đó trước khi áp dụng. Mọi lần chạy được lưu (đầu vào ẩn danh, giá trị từng T, so với lời giải theo luật) để đánh giá A/B (FF §18 Observability, BR-BK10-04).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-BK10` — BK-10 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team · Data Owner: Team Data (Phase 2) |
| Created Date | `2026-10-12` |
| Related FF | [bk-10-phase2-spec.ff.md](bk-10-phase2-spec.ff.md) |
| Related API | [bk-10-phase2-spec.api.md](bk-10-phase2-spec.api.md) |
| Related FE | [bk-10-phase2-spec.fe.md](bk-10-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-BK10-01` | `WorkshopBay` | `workshop_bay` | **Mới** — khoang làm việc |
| `ENT-BK10-02` | `WorkshopOptimizerSetting` | `workshop_optimizer_setting` | **Mới** |
| `ENT-BK10-03` | `OptimizerRun` | `optimizer_run` | **Mới** |
| `ENT-BK10-04` | `RescheduleProposal` | `reschedule_proposal` | **Mới** — đề xuất dời lịch cần chủ xe đồng ý |
| `ENT-BK10-05` | `OptimizerEvaluation` | `optimizer_evaluation` | **Mới** — kết quả A/B |
| `ENT-WS03-05` | `BookingAssignment` | `booking_assignment` — **thêm cột** `bay_id`, `planned_start_at`, `source` thêm `OPTIMIZER` | WS-03 |

Trọng số mặc định toàn hệ thống: config `OPTIMIZER_DEFAULT_WEIGHTS` (người vận hành đổi qua cấu hình triển khai, có lịch sử git) — không bảng.

---

# 2. `workshop_bay` (ENT-BK10-01)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `workshop_id` | `uuid` | No | FK `workshop.id` `ON DELETE CASCADE` |
| `name` | `varchar(40)` | No | "Khoang 1" |
| `active` | `boolean` | No | |
| `capabilities` | `jsonb` | No | `[]` = mọi việc; ví dụ `["TIRE"]` cho khoang có máy ra vào lốp |

Không có khoang khai báo ⇒ bộ tối ưu chỉ gán KTV (khoang không là ràng buộc).

---

# 3. `workshop_optimizer_setting` (ENT-BK10-02)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `workshop_id` | `uuid` | No | — | PK |
| `mode` | `varchar(8)` | No | `'off'` | `off`, `shadow`, `on` (FF §13) |
| `weight_overrides` | `jsonb` | No | `'{}'` | `{ "T3": 0.8, "T4": 1.3 }` — hệ số nhân trên mặc định, mỗi giá trị trong `[0.5, 1.5]` (BR-BK10-03, ±50 %) |
| `slider` | `smallint` | Yes | `NULL` | −100 ("Khách chờ ít") … +100 ("Thợ ít rảnh") — UI SCR-BK10-01; backend quy ra `weight_overrides` |
| `eligible` | `boolean` | No | `false` | Đủ `OPT_MIN_DATA_WEEKS` tuần dữ liệu **và** đạt `OPT_MIN_GAIN` trong shadow (BR-BK10-04) |
| `auto_off_reason` | `varchar(24)` | Yes | `NULL` | `GAIN_BELOW_THRESHOLD` (EF-BK10-03), `HARD_CONSTRAINT_VIOLATION` |
| `mode_changed_at` / `updated_at` | `timestamptz` | | | |

```sql
ALTER TABLE workshop_optimizer_setting ADD CONSTRAINT ck_wos_mode CHECK (mode IN ('off','shadow','on'));
ALTER TABLE workshop_optimizer_setting ADD CONSTRAINT ck_wos_on_eligible CHECK (mode <> 'on' OR eligible);
```

---

# 4. `optimizer_run` (ENT-BK10-03)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `workshop_id` | `uuid` | No | |
| `service_date` | `date` | No | |
| `kind` | `varchar(8)` | No | `BATCH`, `EVENT`, `RANK` |
| `trigger` | `varchar(24)` | Yes | Với `EVENT`: `CANCEL`, `DELAY`, `WALK_IN`, `TECH_ABSENT`, `EXTRA_APPROVED` |
| `mode` | `varchar(8)` | No | Chế độ xưởng lúc chạy (`shadow` / `on`) |
| `status` | `varchar(12)` | No | `SOLVED`, `TIMEOUT`, `INFEASIBLE`, `INVALID` (vi phạm cứng khi kiểm lại, EF-BK10-01), `ERROR` |
| `applied` | `boolean` | No | `true` chỉ khi `mode = on` và `status = SOLVED` và kiểm lại đạt |
| `objective` | `jsonb` | Yes | `{ "T1": …, "T2": …, "T3": …, "T4": …, "T5": …, "pref_penalty": …, "total": … }` (phút / điểm) |
| `baseline_objective` | `jsonb` | Yes | Cùng cấu trúc cho lời giải theo luật trên cùng đầu vào |
| `gain_pct` | `numeric(6,2)` | Yes | `(baseline.total − objective.total) / baseline.total` |
| `input_digest` | `jsonb` | No | Ẩn danh: số lịch, số KTV, số khoang, tổng phút, hash đầu vào (không id chủ xe) |
| `solver` | `varchar(32)` | No | `ortools-cpsat-9.x` / `rule-v1` |
| `weights_used` | `jsonb` | No | |
| `duration_ms` | `integer` | No | |
| `created_at` | `timestamptz` | No | |

```sql
CREATE INDEX ix_optimizer_run_ws_date ON optimizer_run (workshop_id, service_date, kind);
```

Giữ 13 tháng (như PL-03); xuất sang workspace Team Data bằng job PL-03.

---

# 5. `reschedule_proposal` (ENT-BK10-04)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `booking_id` | `uuid` | No | — | FK `booking.id` `ON DELETE CASCADE`; lịch `confirmed` |
| `run_id` | `uuid` | No | — | FK `optimizer_run.id` |
| `current_start_at` / `proposed_start_at` | `timestamptz` | No | — | |
| `gain_summary` | `varchar(120)` | No | — | "Lấy xe sớm hơn 40 phút" (BR-BK10-08) |
| `status` | `varchar(10)` | No | `'pending'` | `pending`, `accepted`, `declined`, `expired`, `void` (khung không còn) |
| `expires_at` | `timestamptz` | No | — | min(`created_at + 12h`, `current_start_at − 2h`) |
| `responded_at` | `timestamptz` | Yes | `NULL` | |

```sql
CREATE UNIQUE INDEX ux_reschedule_proposal_open ON reschedule_proposal (booking_id) WHERE status = 'pending';
```

AC-BK10-04: lịch `confirmed` chỉ đổi giờ qua `accepted` (đổi lịch us-053 với lý do `OPTIMIZER_ACCEPTED`).

---

# 6. `optimizer_evaluation` (ENT-BK10-05)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `workshop_id` | `uuid` | No | |
| `period_start` / `period_end` | `date` | No | |
| `runs` | `integer` | No | Số lần chạy shadow / on có cả hai lời giải |
| `median_gain_pct` | `numeric(6,2)` | No | |
| `metrics` | `jsonb` | No | M-09 (T₄, T₅), M-10 (T₃) trước / sau |
| `decision` | `varchar(16)` | No | `ELIGIBLE`, `NOT_ELIGIBLE`, `AUTO_OFF` |
| `created_at` | `timestamptz` | No | |

---

# 7. `booking_assignment` — thay đổi (WS-03)

| Thay đổi | Ghi chú |
|---|---|
| `bay_id uuid NULL` FK `workshop_bay.id` | Khoang được gán |
| `planned_start_at timestamptz NULL` | Giờ bắt đầu thực tế dự kiến trong ngày (thứ tự xe trong làn); BK-08 đọc khi có |
| `source` thêm `OPTIMIZER` | Bộ tối ưu không ghi đè `MANUAL` (AF-WS03-02) |

---

# 8. Migration

Một revision: 5 bảng, 2 cột + giá trị `source`. Tạo `workshop_optimizer_setting (off)` cho mọi xưởng.

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
