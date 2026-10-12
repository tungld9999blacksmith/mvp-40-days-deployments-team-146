# Entity Specification — Bảo dưỡng sớm hoặc trễ so với mốc

> Entity cho Feature `FEAT-P2-BK03`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-03-phase2-spec.ff.md). **API:** [API Spec](bk-03-phase2-spec.api.md).
>
> **Nguyên tắc:** BK-03 không đổi công thức đến hạn F3 (FF §3.2). Thêm (1) ngưỡng sớm theo model có nguồn, (2) hạng mục chuẩn "Kiểm tra nhanh", (3) cờ trên booking để biết lịch là bảo dưỡng mốc hay kiểm tra nhanh và chủ xe đã xác nhận làm quá sớm.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-BK03` — BK-03 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [bk-03-phase2-spec.ff.md](bk-03-phase2-spec.ff.md) |
| Related API | [bk-03-phase2-spec.api.md](bk-03-phase2-spec.api.md) |
| Related FE | [bk-03-phase2-spec.fe.md](bk-03-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-BK03-01` | `EarlyServiceWindow` | `early_service_window` | **Mới** | Ngưỡng sớm theo model, có nguồn |
| `ENT-402` | `Booking` | `booking` | Có sẵn — **thêm cột** | `service_kind`, `early_classification`, `early_confirmed_at` |
| `ENT-009` | `ServicePrice` | `service_price` | Có sẵn — thêm dữ liệu | Hạng mục chuẩn `QUICK_CHECK` (giá do xưởng) |
| `ENT-WS02-01` | `ServiceItemDuration` | `service_item_duration` | WS-02 — thêm dữ liệu | Thời lượng mặc định `QUICK_CHECK` = 30 phút |

---

# 2. `early_service_window` (ENT-BK03-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `model_id` | `varchar(64)` | Yes | `NULL` | Cùng khoá model với `maintenance_rule.model_id`; `NULL` = mặc định hệ thống |
| `odo_milestone` | `integer` | Yes | `NULL` | `NULL` = mọi mốc của model |
| `early_days` | `smallint` | No | — | `1..365` |
| `early_km` | `integer` | No | — | `100..20000` |
| `source_type` | `varchar(12)` | No | — | `OEM_DOC` (có nguồn) / `CONFIG` (tham số `EARLY_SERVICE_DAYS` / `EARLY_SERVICE_KM`, BR-BK03-07) |
| `document_chunk_id` | `uuid` | Yes | `NULL` | FK `document_chunk.id` `ON DELETE SET NULL`; bắt buộc khi `OEM_DOC` |
| `created_at` / `updated_at` | `timestamptz` | No | `now()` | |

```sql
CREATE UNIQUE INDEX ux_esw_scope ON early_service_window (coalesce(model_id, '*'), coalesce(odo_milestone, 0));
ALTER TABLE early_service_window ADD CONSTRAINT ck_esw_source
  CHECK ((source_type = 'OEM_DOC') = (document_chunk_id IS NOT NULL));
```

**Tra cứu:** (model, mốc) → (model, mọi mốc) → mặc định hệ thống (`CONFIG`, seed từ `EARLY_SERVICE_DAYS` / `EARLY_SERVICE_KM`). Bảng do nhóm dữ liệu nạp từ tài liệu hãng (P2Q-09), không có API ghi cho người dùng.

---

# 3. `booking` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `service_kind` | `varchar(16)` | No | `'MAINTENANCE'` | `MAINTENANCE` (bảo dưỡng mốc), `QUICK_CHECK` (kiểm tra nhanh, không đóng mốc — BR-BK03-06), `REPAIR` (AD-02, sửa chữa) |
| `early_classification` | `varchar(12)` | Yes | `NULL` | `WITHIN`, `TOO_EARLY`, `OVERDUE`, `UNKNOWN` lúc đặt (chụp lại) |
| `early_confirmed_at` | `timestamptz` | Yes | `NULL` | Chủ xe xác nhận lần hai khi `TOO_EARLY` + `MAINTENANCE` (BR-BK03-02) |

```sql
ALTER TABLE booking ADD CONSTRAINT ck_booking_service_kind CHECK (service_kind IN ('MAINTENANCE', 'QUICK_CHECK', 'REPAIR'));
ALTER TABLE booking ADD CONSTRAINT ck_booking_early_confirm CHECK (
  NOT (service_kind = 'MAINTENANCE' AND early_classification = 'TOO_EARLY') OR early_confirmed_at IS NOT NULL);
```

- `QUICK_CHECK`: `odo_milestone = NULL`; một lịch mở mỗi xe (us-029 BR-013) vẫn áp dụng.
- Lịch `QUICK_CHECK` hoàn tất **không** được coi là đã làm mốc: F3 chỉ tính mốc từ lịch sử dịch vụ do hãng đồng bộ (`vehicle_service_record` với loại bảo dưỡng định kỳ), nên không cần đổi F3; nhắc mốc F7 tiếp tục (AC-BK03-03).

---

# 4. Dữ liệu chuẩn `QUICK_CHECK`

| Bảng | Dòng |
|---|---|
| `service_item_duration` (WS-02) | `item_code = 'QUICK_CHECK'`, `workshop_id = NULL`, `duration_min = 30`, `source = ADMIN` |
| `service_price` | Xưởng tự thêm giá cho `QUICK_CHECK` ở Bảng giá (us-045). Xưởng **không có** dòng giá ⇒ xưởng không cung cấp kiểm tra nhanh ⇒ nút ẩn (SCR-BK03-01) |

Q-BK03-02: hạng mục chuẩn toàn hệ thống, giá do xưởng.

---

# 5. Business Rules (bổ sung)

## BR-ENT-BK03-01 — Phân loại "điều kiện nào đến trước"

`WITHIN` khi `remaining_days ≤ early_days` **hoặc** `remaining_km ≤ early_km` (BR-BK03-01, EDGE-BK03-01); `TOO_EARLY` khi cả hai lớn hơn; `OVERDUE` / `UNKNOWN` lấy thẳng từ F3. `DUE_SOON` luôn là `WITHIN`.

## BR-ENT-BK03-02 — Không giảm ODO

Lịch sử hãng gửi ODO thấp hơn ODO đã ghi: giữ quy tắc F3 hiện có (không giảm), dòng `vehicle_service_record` vẫn lưu để truy vết (EF-BK03-03). Không thêm cột.

---

# 6. Migration

- Một revision: bảng `early_service_window`, 3 cột `booking` (mặc định `MAINTENANCE`, không backfill khác), CHECK.
- Seed: một dòng mặc định `CONFIG` (30 ngày / 1.000 km); dòng `QUICK_CHECK` trong `service_item_duration`.

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
