# Entity Specification — Chỉ số đo hiệu quả

> Entity cho Feature `FEAT-P2-PL03`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](pl-03-phase2-spec.ff.md). **API:** [API Spec](pl-03-phase2-spec.api.md).
>
> **Nguyên tắc:** kho sự kiện là bảng Postgres **của hạ tầng Phase 2** (Q-PL03-01), chỉ thêm, chia phân vùng theo tháng. Không có cột định danh cá nhân: người dùng chỉ xuất hiện dưới dạng `user_hash` (HMAC có muối, BR-PL03-02). Định nghĩa chỉ số có phiên bản (BR-PL03-06); bảng tổng hợp lưu kèm phiên bản định nghĩa đã dùng.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-PL03` — PL-03 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team · Data Owner: Team Data (Phase 2) |
| Created Date | `2026-10-12` |
| Related FF | [pl-03-phase2-spec.ff.md](pl-03-phase2-spec.ff.md) |
| Related API | [pl-03-phase2-spec.api.md](pl-03-phase2-spec.api.md) |
| Related FE | [pl-03-phase2-spec.fe.md](pl-03-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-PL03-01` | `ProductEvent` | `product_event` (phân vùng theo tháng) | **Mới** |
| `ENT-PL03-02` | `MetricDefinition` | `metric_definition` | **Mới** |
| `ENT-PL03-03` | `MetricDaily` | `metric_daily` | **Mới** |
| `ENT-PL03-04` | `DataExportRun` | `data_export_run` | **Mới** |

---

# 2. `product_event` (ENT-PL03-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK (cùng `occurred_at` vì phân vùng) |
| `event_name` | `varchar(48)` | No | — | Trong danh mục §2.1 |
| `schema_version` | `smallint` | No | `1` | Phiên bản schema `props` của sự kiện |
| `occurred_at` | `timestamptz` | No | — | UTC, thời điểm nghiệp vụ (không phải lúc ghi) |
| `received_at` | `timestamptz` | No | `now()` | Lúc ghi vào kho (EDGE-PL03-01) |
| `feature_id` | `varchar(16)` | No | — | `BK-01`, `CH-01`… |
| `user_hash` | `char(32)` | Yes | `NULL` | `hex(HMAC-SHA256(PL03_HASH_SALT, "u:" + user_id))[:32]`; `NULL` cho sự kiện không gắn chủ xe |
| `actor_hash` | `char(32)` | Yes | `NULL` | Chủ xưởng / KTV (`"w:" + owner_id`, `"t:" + technician_id`) |
| `workshop_id` | `uuid` | Yes | `NULL` | Không phải dữ liệu cá nhân |
| `session_hash` | `char(32)` | Yes | `NULL` | Băm `conversation_id` / phiên đặt lịch để ghép sự kiện của một luồng |
| `props` | `jsonb` | No | `'{}'` | Theo schema của sự kiện; chỉ số, mã, enum — không văn bản tự do |
| `idempotency_key` | `varchar(80)` | No | — | Chống ghi trùng khi thử lại |

```sql
CREATE TABLE product_event (...) PARTITION BY RANGE (occurred_at);
-- Phân vùng tháng tạo trước 2 tháng bằng job; giữ 13 tháng (Q-PL03-02).
CREATE UNIQUE INDEX ux_product_event_idem ON product_event (idempotency_key, occurred_at);
CREATE INDEX ix_product_event_name_time ON product_event (event_name, occurred_at);
CREATE INDEX ix_product_event_session ON product_event (session_hash, occurred_at) WHERE session_hash IS NOT NULL;
```

**Không có** FK tới bảng nghiệp vụ (để giữ được sau khi xoá tài khoản, EDGE-PL03-02, và để xuất sang workspace Team Data độc lập).

## 2.1 Danh mục sự kiện (P2-A, FF §14) — tên chuẩn

| `event_name` | `feature_id` | `props` chính |
|---|---|---|
| `booking_intent_started` | CH-01, BK-01 | `entry` (`CHIP`, `BOOKING_SCREEN`, `WIDGET`, `MAP`, `QUICK_BOOKING`, `DUE_JOB`) |
| `scheduler_run` | BK-01 | `trigger`, `outcome`, `optionCount`, `candidateCount`, `rejectedBy`, `durationMs`, `scorerVersion` |
| `option_shown` / `option_selected` / `option_rejected` | BK-01, PS-03 | `runId` (băm), `rank`, `tier`, `reasonCodes`; `rejectReason` |
| `booking_confirmed` | Booking | `taps`, `typedChars`, `entry`, `confirmationDecision`, `msSinceIntent` |
| `chip_shown` / `chip_clicked` | CH-01 | `intent`, `source`, `position`, `flowStep` |
| `booking_cancelled` | BK-02 | `cancelReason`, `hoursBefore` |
| `no_show_marked` / `no_show_waived` | BK-02 | `actor`, `waiveReason` |
| `booking_manual_review` | WS-01 | `reasonCodes` |
| `waitlist_offer_sent` / `waitlist_offer_accepted` | BK-07 | `minutesBefore`, `rank` |
| `advisor_answered` / `handoff_created` | AD-01…04, PL-02 | `topic` (`PRICE`, `WARRANTY`, `PARTS`), `handoffReason` |
| `checked_in`, `service_started`, `service_finished`, `vehicle_handed_over` | us-037, us-057 | `bookingHash`, `stage`, `minutesLate` |
| `technician_assistant_used` | TA-01 | `tool`, `channel` (`TEXT`, `VOICE`) |
| `consent_changed` | PL-01 | `code`, `newStatus`, `channel` |
| `memory_deleted` | PS-01 | `scope` (`ONE`, `ALL`), `key` |
| `chat_intent_detected` | AI-001 | `intent` (cho top ý định CH-01) |

Thêm sự kiện mới = thêm schema vào registry code (`modules/metrics/events.py`) + tăng `schema_version` khi đổi; review bởi Team Data.

## 2.2 Khoá cấm trong `props` (AC-PL03-02)

Validator từ chối sự kiện nếu `props` có khoá hoặc giá trị khớp: `name`, `fullName`, `phone`, `email`, `vin`, `licensePlate`, `address`, `lat`, `lng`, `userId`, `conversationId`, `content`; hoặc giá trị chuỗi khớp regex SĐT VN, email, VIN 17 ký tự, biển số đầy đủ. Id nghiệp vụ (booking, run) chỉ đi dưới dạng băm (`bookingHash`).

---

# 3. `metric_definition` (ENT-PL03-02)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `metric_code` | `varchar(8)` | No | PK (1/2): `M-01` … `M-12` |
| `version` | `smallint` | No | PK (2/2) |
| `name_vi` | `varchar(120)` | No | |
| `formula` | `text` | No | Mô tả + SQL tham chiếu (Team Data duyệt) |
| `unit` | `varchar(16)` | No | `SECONDS`, `COUNT`, `RATIO`, `MINUTES` |
| `target` | `varchar(60)` | Yes | Ví dụ `< 60s`, `>= 0.95` |
| `dimensions` | `jsonb` | No | `["workshop_id"]` hoặc `[]` |
| `active_from` | `date` | No | |
| `changed_by` | `varchar(60)` | No | |
| `change_note` | `text` | No | BR-PL03-06 |

Định nghĩa v1 lấy từ PRD §12 (API §4).

---

# 4. `metric_daily` (ENT-PL03-03)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `metric_date` | `date` | No | PK (1/4), theo Asia/Ho_Chi_Minh |
| `metric_code` | `varchar(8)` | No | PK (2/4) |
| `dimension_key` | `varchar(64)` | No | PK (3/4): `all` hoặc `workshop:{uuid}` |
| `definition_version` | `smallint` | No | PK (4/4) |
| `value` | `numeric(14,4)` | Yes | `NULL` khi không đủ mẫu |
| `sample_size` | `integer` | No | |
| `computed_at` | `timestamptz` | No | |

Tuần = tổng hợp từ ngày khi đọc (không lưu riêng). Job tính lại 3 ngày gần nhất mỗi đêm (EDGE-PL03-01) bằng upsert.

---

# 5. `data_export_run` (ENT-PL03-04)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `export_date` | `date` | No | Ngày dữ liệu |
| `target` | `varchar(32)` | No | `TEAM_DATA_WORKSPACE` |
| `object_path` | `varchar(300)` | Yes | `team-data/events/dt=2026-10-12/part-0.parquet` |
| `row_count` | `integer` | Yes | |
| `status` | `varchar(10)` | No | `running`, `done`, `failed` |
| `started_at` / `finished_at` | `timestamptz` | | |

---

# 6. Retention

| Bảng | Giữ |
|---|---|
| `product_event` | 13 tháng — job drop phân vùng cũ |
| `metric_daily`, `metric_definition` | Không xoá |
| `data_export_run` | 13 tháng |

Xoá tài khoản (EDGE-PL03-02): không cần làm gì — không có bảng ánh xạ `user_hash → user_id` (muối chỉ ở Secret Manager / env Phase 2).

---

# 7. Migration

Một revision trên **cơ sở dữ liệu Phase 2**: bảng phân vùng + 2 phân vùng đầu, 3 bảng còn lại, seed `metric_definition` v1. SQLite trong test: bảng thường (không phân vùng).

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
