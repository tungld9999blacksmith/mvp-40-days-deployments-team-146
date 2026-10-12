# Entity Specification — Tra cứu lịch sử bảo dưỡng phía chủ xe

> Entity cho Feature `FEAT-P2-HS01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](hs-01-phase2-spec.ff.md). **API:** [API Spec](hs-01-phase2-spec.api.md).
>
> **Nguyên tắc:** lịch sử là dữ liệu chỉ đọc đối với chủ xe (FF §21). `vehicle_service_record` (có sẵn, nguồn `OEM` và `EV_CARE`) vẫn là gốc; HS-01 thêm (1) chi tiết hạng mục có nhóm để lọc, (2) khoá gộp trùng giữa hai nguồn, (3) link chia sẻ. Khuyến nghị chưa làm đọc từ `booking_line` bị từ chối (báo giá hai tầng) và AD-04, không có bảng riêng.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-HS01` — HS-01 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [hs-01-phase2-spec.ff.md](hs-01-phase2-spec.ff.md) |
| Related API | [hs-01-phase2-spec.api.md](hs-01-phase2-spec.api.md) |
| Related FE | [hs-01-phase2-spec.fe.md](hs-01-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| — | `VehicleServiceRecord` | `vehicle_service_record` | Có sẵn — **thêm cột** | `dedupe_key`, `merged_into_id`, `odo_mismatch_km` |
| `ENT-HS01-01` | `VehicleServiceRecordItem` | `vehicle_service_record_item` | **Mới** | Hạng mục / phụ tùng / chi phí từng dòng |
| `ENT-HS01-02` | `ServiceItemCategory` | `service_item_category` | **Mới** | `item_code` → nhóm (Phanh, Lốp, Pin…) |
| `ENT-HS01-03` | `HistoryShareLink` | `history_share_link` | **Mới** | Link chỉ đọc có hạn |
| — | `BookingLine` / `BookingLinePhoto` | có sẵn | Không đổi | Chi phí từng dòng, ảnh, dòng bị từ chối = khuyến nghị chưa làm |

---

# 2. `vehicle_service_record` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `dedupe_key` | `varchar(120)` | No | — | `{user_vehicle_id}:{service_date}:{workshop_key}`; `workshop_key` = `workshop_id` hoặc `external_center_id` (BR-HS01-01) |
| `merged_into_id` | `uuid` | Yes | `NULL` | FK tự tham chiếu. Bản `EV_CARE` trùng với bản `OEM` trỏ vào bản `OEM` (ưu tiên hãng) |
| `odo_mismatch_km` | `integer` | Yes | `NULL` | `odo_ev_care − odo_oem` khi gộp và lệch (EDGE-HS01-01) |

```sql
CREATE INDEX ix_vsr_dedupe ON vehicle_service_record (dedupe_key);
CREATE INDEX ix_vsr_vehicle_date ON vehicle_service_record (user_vehicle_id, service_date DESC) WHERE merged_into_id IS NULL;
```

**Gộp (BR-HS01-01):** khi chèn / cập nhật một bản ghi, tìm bản ghi khác nguồn cùng `dedupe_key`; có thì bản `EV_CARE` nhận `merged_into_id = <OEM>`. Danh sách chỉ đọc `merged_into_id IS NULL`; chi tiết của mục gộp lấy ngày, ODO, xưởng từ `OEM`, còn chi phí từng dòng, ảnh, báo giá từ `EV_CARE` (hãng thường thiếu chi phí, AF-HS01-02). Gộp chạy trong đồng bộ OEM (`oem_integration`) và khi tạo bản ghi `EV_CARE` lúc hoàn tất lịch.

---

# 3. `vehicle_service_record_item` (ENT-HS01-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `record_id` | `uuid` | No | — | FK `vehicle_service_record.id` `ON DELETE CASCADE` |
| `item_code` | `varchar(50)` | Yes | `NULL` | Khi khớp danh mục |
| `item_name` | `varchar(200)` | No | — | |
| `kind` | `varchar(10)` | No | — | `LABOR`, `PART`, `CHECK` |
| `part_number` | `varchar(64)` | Yes | `NULL` | Phụ tùng đã thay (nếu hãng / xưởng cung cấp) |
| `quantity` | `numeric(8,2)` | Yes | `NULL` | |
| `amount_vnd` | `numeric(12,2)` | Yes | `NULL` | |
| `amount_kind` | `varchar(12)` | Yes | `NULL` | `ACTUAL` (hãng / xưởng chốt), `APPROVED_QUOTE` (báo giá đã duyệt), `ESTIMATE` (chỉ có dự toán ⇒ nhãn "ước tính", BR-HS01-03) |
| `is_covered_by_warranty` | `boolean` | No | `false` | |
| `booking_line_id` | `uuid` | Yes | `NULL` | FK `booking_line.id` `ON DELETE SET NULL` khi từ EV Care |
| `source` | `varchar(8)` | No | — | `OEM`, `EV_CARE` |

```sql
CREATE INDEX ix_vsri_record ON vehicle_service_record_item (record_id);
CREATE INDEX ix_vsri_code ON vehicle_service_record_item (item_code);
```

**Nguồn dữ liệu:**
- `OEM`: tách từ payload `ServiceHistory` khi đồng bộ (nếu hãng trả danh sách hạng mục; chỉ có chuỗi `items_done` ⇒ một dòng `item_name = items_done`, `item_code = NULL`, `kind = CHECK`).
- `EV_CARE`: tạo khi lịch `completed`, từ `booking_line` đã xác nhận (`kind PACKAGE/EXTRA`, `confirmed_price`) hoặc báo giá us-049 (`pricing_flow = legacy`).
- Backfill cho bản ghi hiện có theo hai quy tắc trên.

---

# 4. `service_item_category` (ENT-HS01-02)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `item_code` | `varchar(50)` | No | PK |
| `category` | `varchar(16)` | No | `BRAKE`, `TIRE`, `BATTERY`, `COOLANT`, `CABIN_FILTER`, `AC`, `SUSPENSION`, `LIGHTING`, `SOFTWARE`, `GENERAL_CHECK`, `OTHER` |
| `label_vi` | `varchar(40)` | No | "Phanh", "Lốp", "Pin cao áp"… |

Seed từ danh sách `maintenance_rule.item_code`. Dòng không có `item_code` ⇒ phân nhóm bằng từ khoá tiếng Việt trên `item_name` (bảng từ khoá trong code, `history/categories.py`); không khớp ⇒ `OTHER`.

---

# 5. `history_share_link` (ENT-HS01-03)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `user_vehicle_id` | `uuid` | No | — | FK `user_vehicle.id` `ON DELETE CASCADE` |
| `token_hash` | `char(64)` | No | — | SHA-256 của token; token gốc (32 byte ngẫu nhiên, base64url) chỉ trả **một lần** lúc tạo |
| `token_hint` | `varchar(6)` | No | — | 6 ký tự cuối để chủ xe nhận ra link trong danh sách |
| `status` | `varchar(8)` | No | `'active'` | `active`, `revoked` (`expired` tính khi đọc: `now ≥ expires_at`) |
| `expires_at` | `timestamptz` | No | — | `created_at + SHARE_LINK_DAYS` |
| `revoked_at` | `timestamptz` | Yes | `NULL` | |
| `view_count` | `integer` | No | `0` | |
| `last_viewed_at` | `timestamptz` | Yes | `NULL` | |
| `created_at` | `timestamptz` | No | `now()` | |

```sql
CREATE UNIQUE INDEX ux_hsl_token ON history_share_link (token_hash);
CREATE INDEX ix_hsl_vehicle_active ON history_share_link (user_vehicle_id) WHERE status = 'active';
```

BR-HS01-08 (tối đa 3 link đang hoạt động / xe) kiểm ở service (đếm `active` và chưa hết hạn), không bằng index.

---

# 6. Business Rules (bổ sung)

## BR-ENT-HS01-01 — Chủ mới chỉ thấy phần hãng

Xe đổi chủ (`user_vehicle` mới cho cùng VIN): danh sách của chủ hiện tại gồm mọi bản `OEM` của VIN, cộng bản `EV_CARE` có `booking.user_id = chủ hiện tại`. Ảnh (`booking_line_photo`), ghi chú, báo giá của chủ cũ không hiện; mục `OEM` đã gộp với `EV_CARE` của chủ cũ chỉ hiện phần `OEM` (BR-HS01-06).

## BR-ENT-HS01-02 — Lịch huỷ không vào lịch sử

Chỉ lịch `completed` tạo bản ghi `EV_CARE` (EDGE-HS01-02).

---

# 7. Migration

- Một revision: 3 cột `vehicle_service_record`, 3 bảng mới, index.
- Backfill: `dedupe_key` cho mọi bản ghi; chạy gộp một lượt; tạo `vehicle_service_record_item` từ `booking_line` / `items_done`; seed `service_item_category`.
- `downgrade`: drop bảng, drop cột.

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
