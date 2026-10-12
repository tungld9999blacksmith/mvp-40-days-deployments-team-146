# Entity Specification — Chọn xưởng theo phụ tùng sẵn có

> Entity cho Feature `FEAT-P2-BK09`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-09-phase2-spec.ff.md). **API:** [API Spec](bk-09-phase2-spec.api.md).
>
> **Nguyên tắc:** tồn kho đơn giản, không phải WMS (FF §21): số lượng hiện có + ngày hàng về + thời điểm cập nhật. Số khả dụng = tồn − đang giữ (BR-BK09-07), tính khi đọc. Mã phụ tùng dùng mã hãng; ánh xạ hạng mục → phụ tùng lấy từ danh mục hãng (Q-BK09-02: mock hãng mở rộng).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-BK09` — BK-09 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [bk-09-phase2-spec.ff.md](bk-09-phase2-spec.ff.md) |
| Related API | [bk-09-phase2-spec.api.md](bk-09-phase2-spec.api.md) |
| Related FE | [bk-09-phase2-spec.fe.md](bk-09-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-BK09-01` | `PartCatalog` | `part_catalog` | **Mới** — danh mục phụ tùng hãng |
| `ENT-BK09-02` | `ItemPartRequirement` | `item_part_requirement` | **Mới** — hạng mục → phụ tùng theo model |
| `ENT-BK09-03` | `WorkshopPartStock` | `workshop_part_stock` | **Mới** |
| `ENT-BK09-04` | `PartReservation` | `part_reservation` | **Mới** |
| `ENT-402` | `Booking` | `booking` — **thêm cột** `require_parts_in_stock`, `parts_preordered`, `parts_shortage` | Có sẵn |

---

# 2. `part_catalog` (ENT-BK09-01) & `item_part_requirement` (ENT-BK09-02)

`part_catalog`:

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `part_number` | `varchar(64)` | No | PK, mã hãng |
| `name_vi` | `varchar(200)` | No | |
| `model_ids` | `jsonb` | No | |
| `equivalent_part_numbers` | `jsonb` | No | Chỉ khi danh mục hãng ghi tương đương (EDGE-BK09-02) |
| `synced_at` | `timestamptz` | No | |

`item_part_requirement`:

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `item_code` | `varchar(50)` | No | PK (1/3): hạng mục mốc (`maintenance_rule`) hoặc sửa chữa (`repair_item`) |
| `model_id` | `varchar(64)` | No | PK (2/3) |
| `part_number` | `varchar(64)` | No | PK (3/3), FK `part_catalog.part_number` |
| `quantity` | `numeric(8,2)` | No | |

Hạng mục không có dòng ⇒ không cần phụ tùng (AF-BK09-02).

---

# 3. `workshop_part_stock` (ENT-BK09-03)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `workshop_id` | `uuid` | No | — | PK (1/2), FK `workshop.id` `ON DELETE CASCADE` |
| `part_number` | `varchar(64)` | No | — | PK (2/2), FK `part_catalog.part_number` |
| `quantity_on_hand` | `numeric(10,2)` | No | `0` | `≥ 0` |
| `expected_arrival_date` | `date` | Yes | `NULL` | Ngày hàng về (khi đang đặt) |
| `expected_quantity` | `numeric(10,2)` | Yes | `NULL` | |
| `updated_at` | `timestamptz` | No | `now()` | Lần chủ xưởng cập nhật (BR-BK09-02) |
| `updated_by_owner_id` | `uuid` | Yes | `NULL` | |

```sql
ALTER TABLE workshop_part_stock ADD CONSTRAINT ck_wps_qty CHECK (quantity_on_hand >= 0 AND (expected_quantity IS NULL OR expected_quantity > 0));
CREATE INDEX ix_wps_part ON workshop_part_stock (part_number);
```

## 3.1 Trạng thái hiển thị (tính khi đọc)

Với một lịch cần tập phụ tùng `P` (theo `item_part_requirement` của hạng mục + model xe):

| Trạng thái | Khi |
|---|---|
| `IN_STOCK` (Có sẵn) | Mọi `p ∈ P`: dòng tồn được cập nhật trong `STOCK_STALE_DAYS` **và** `quantity_on_hand − reserved(p) ≥ quantity cần` (tính cả mã tương đương) |
| `ARRIVING` (Về {ngày}) | Không đủ sẵn, nhưng mọi `p` thiếu có `expected_arrival_date` ≥ hôm nay (dữ liệu còn mới); ngày hiển thị = ngày về muộn nhất |
| `UNKNOWN` (Chưa rõ) | Còn lại: không có dòng, quá `STOCK_STALE_DAYS` (EF-BK09-01, AC-BK09-01), hoặc hết mà không có ngày về |
| `NOT_REQUIRED` | `P` rỗng (không hiển thị nhãn) |

`reserved(p)` = Σ `part_reservation.quantity` `status = reserved` của xưởng. Chủ xe không thấy số lượng (BR-BK09-07).

---

# 4. `part_reservation` (ENT-BK09-04)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `booking_id` | `uuid` | No | — | FK `booking.id` `ON DELETE CASCADE` |
| `workshop_id` | `uuid` | No | — | |
| `part_number` | `varchar(64)` | No | — | |
| `quantity` | `numeric(8,2)` | No | — | |
| `status` | `varchar(10)` | No | `'reserved'` | `reserved`, `consumed` (lịch `completed`), `released` (huỷ / đổi xưởng, BR-BK09-06) — FF §13 |
| `created_at` / `closed_at` | `timestamptz` | | | |

```sql
CREATE UNIQUE INDEX ux_part_reservation_live ON part_reservation (booking_id, part_number) WHERE status = 'reserved';
CREATE INDEX ix_part_reservation_stock ON part_reservation (workshop_id, part_number) WHERE status = 'reserved';
```

`consumed` ⇒ trừ `quantity_on_hand` tương ứng (xưởng không phải nhập tay lần nữa); `released` ⇒ không đổi `quantity_on_hand` (chỉ giải phóng phần giữ).

---

# 5. `booking` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `require_parts_in_stock` | `boolean` | No | `false` | Chủ xe chọn "Chỉ xưởng có sẵn" (BR-BK09-03) |
| `parts_preordered` | `boolean` | No | `false` | Đặt trước phụ tùng (UC-BK09-03) |
| `parts_shortage` | `boolean` | No | `false` | Xưởng nhận lịch nhưng không giữ đủ (EDGE-BK09-01) — nhãn Board |

---

# 6. Migration

Một revision: 4 bảng, 3 cột. Seed `part_catalog`, `item_part_requirement` từ mock hãng.

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
