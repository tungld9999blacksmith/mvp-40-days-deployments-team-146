# Entity Specification — Tư vấn bảo hành và gói bảo hành

> Entity cho Feature `FEAT-P2-AD03`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-03-phase2-spec.ff.md). **API:** [API Spec](ad-03-phase2-spec.api.md).
>
> **Nguyên tắc:** thời hạn bảo hành theo xe đã có trong `vehicle_warranty` (đồng bộ từ hãng lúc xác thực xe, F1: `component`, `start_date`, `end_date`, `km_limit`, `oem_status`). AD-03 thêm (1) làm mới định kỳ từ hãng, (2) ánh xạ hạng mục bảo dưỡng / sửa chữa → thành phần bảo hành, (3) danh mục gói bảo dưỡng / bảo hành mở rộng của hãng (Q-AD03-01: hãng cung cấp). Bảo hành theo **xe**, không theo chủ (EDGE-AD03-02).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-AD03` — AD-03 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [ad-03-phase2-spec.ff.md](ad-03-phase2-spec.ff.md) |
| Related API | [ad-03-phase2-spec.api.md](ad-03-phase2-spec.api.md) |
| Related FE | [ad-03-phase2-spec.fe.md](ad-03-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| — | `VehicleWarranty` | `vehicle_warranty` (sprint-1) | Có sẵn — **thêm cột** `last_refreshed_at`, `source_payload_hash` |
| `ENT-AD03-01` | `WarrantyComponentMap` | `warranty_component_map` | **Mới** — hạng mục → thành phần bảo hành |
| `ENT-AD03-02` | `WarrantyPlan` | `warranty_plan` | **Mới** — gói của hãng |
| `ENT-AD03-03` | `WarrantyPlanItem` | `warranty_plan_item` | **Mới** — nội dung gói |

---

# 2. `vehicle_warranty` — cột mới

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `last_refreshed_at` | `timestamptz` | Yes | Lần làm mới gần nhất từ hãng (job AD-03) |
| `source_payload_hash` | `char(64)` | Yes | Băm payload hãng để biết có thay đổi không |

Thành phần (`component`) giữ enum hiện có `battery`, `motor`, `chassis`, `electronics`; hãng (mock, P2Q-05) mở rộng thêm giá trị ⇒ thêm vào enum `warranty_component_enum` bằng migration (không dùng chuỗi tự do).

**Hiệu lực của một thành phần** (tính khi đọc): `ACTIVE` khi `oem_status = active` **và** `today ≤ end_date` **và** (`km_limit IS NULL` hoặc `odo_km < km_limit`); ngược lại `EXPIRED`. Nguồn km: ODO đồng bộ hãng (không nhập tay). Không tự suy diễn ân hạn (PQ-07).

---

# 3. `warranty_component_map` (ENT-AD03-01)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `item_code` | `varchar(50)` | No | PK (1/2): mã `maintenance_rule` / `repair_item` |
| `component` | `warranty_component_enum` | No | PK (2/2) |
| `source_chunk_id` | `uuid` | Yes | FK `document_chunk.id` — đoạn chính sách nêu hạng mục thuộc thành phần |

Dùng bởi AD-01 (`warrantyStatus` của từng dòng dự toán) và AD-02. Hạng mục không có dòng ⇒ `UNDETERMINED` (AD-01 entity §3).

---

# 4. `warranty_plan` (ENT-AD03-02) & `warranty_plan_item` (ENT-AD03-03)

`warranty_plan`:

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `external_plan_id` | `varchar(64)` | No | Unique, id của hãng |
| `kind` | `varchar(16)` | No | `MAINTENANCE_PACKAGE` (gói bảo dưỡng trả trước), `EXTENDED_WARRANTY` |
| `name` | `varchar(150)` | No | |
| `model_ids` | `jsonb` | No | `[]` = mọi model |
| `price_vnd` | `numeric(12,2)` | No | Giá niêm yết của hãng |
| `duration_months` | `smallint` | Yes | |
| `km_limit` | `integer` | Yes | |
| `eligibility` | `jsonb` | No | Điều kiện (tuổi xe tối đa, km tối đa lúc mua…) dạng có cấu trúc |
| `terms_document_id` | `uuid` | Yes | FK `official_document.id` — điều khoản (trích nguồn) |
| `active` | `boolean` | No | |
| `synced_at` | `timestamptz` | No | |

`warranty_plan_item`:

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `plan_id` | `uuid` | No | PK (1/2), FK `warranty_plan.id` `ON DELETE CASCADE` |
| `item_code` | `varchar(50)` | No | PK (2/2) |
| `times_included` | `smallint` | Yes | Số lần bao gồm (gói bảo dưỡng); `NULL` = không giới hạn trong thời hạn |
| `component` | `warranty_component_enum` | Yes | Với gói bảo hành mở rộng |

Không có API ghi cho chủ xe / chủ xưởng; đồng bộ từ hãng (mock mở rộng endpoint `GET /plans`).

---

# 5. Migration

Một revision: 2 cột `vehicle_warranty`, 3 bảng mới; seed `warranty_component_map` từ tài liệu `warranty_policy` (nhóm dữ liệu duyệt).

---

# 6. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
