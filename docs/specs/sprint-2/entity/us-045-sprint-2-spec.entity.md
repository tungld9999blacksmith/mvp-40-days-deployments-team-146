# Entity Specification — Dự toán chi phí bảo dưỡng

> Entity cho Feature `FEAT-COST-001` — PRD F5 (US-045 → US-048).
>
> **Nguyên tắc:** F5 **không tạo bảng mới** và **không ghi** dữ liệu nghiệp vụ (FF BR-1007). Tài liệu này ghi rõ entity nào được đọc, cột nào được dùng, index cần có, và các điểm dữ liệu còn thiếu cần chốt.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-COST-001` — F5 |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-09-30` |
| Updated Date | `2026-09-30` |
| Related FF | [us-045-sprint-2-spec.ff.md](../feature-functional/us-045-sprint-2-spec.ff.md) |
| Related API | [us-045-sprint-2-spec.api.md](../api/us-045-sprint-2-spec.api.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Vai trò trong F5 |
|---|---|---|---|---|
| `ENT-401` | `MaintenanceRule` | `maintenance_rule` | Có sẵn — **không đổi** | Hạng mục theo (`model_id`, `odo_milestone`), `is_covered_by_warranty`, `estimated_cost` (giá tham khảo) |
| `ENT-409` | `ServicePrice` | `service_price` | Có sẵn — **không đổi** | Giá xưởng theo (`workshop_id`, `model_id`, `item_code`) + hiệu lực |
| `ENT-008` | `Workshop` | `workshop` | Có sẵn — không đổi | `status = active`, vị trí (xưởng mặc định) |
| `ENT-003` | `UserVehicle` | `user_vehicle` | Có sẵn — không đổi | Sở hữu, `external_model_id` |
| `ENT-004` | `VehicleWarranty` | `vehicle_warranty` | Có sẵn — không đổi | Xác định xe còn bảo hành (component `chassis` — Q-1001) |
| `ENT-001` / `ENT-002` | `VehicleUser` / `UserLocation` | `vehicle_user` / `user_location` | Có sẵn — không đổi | Xưởng ưa thích / vị trí hồ sơ |
| `ENT-422` | `ChatMessage` | `chat_message` | Có sẵn — không đổi | `meta.estimate` lưu kết quả tool trong chat (us-025) |

---

# 2. Quy tắc đọc dữ liệu

## RD-1001 — Ghép hạng mục với giá

```text
maintenance_rule r  (r.model_id = :model, r.odo_milestone = :k)
LEFT JOIN service_price p
       ON p.workshop_id = :ws AND p.model_id = r.model_id AND p.item_code = r.item_code
      AND (p.valid_from IS NULL OR p.valid_from <= :today)
      AND (p.valid_to   IS NULL OR p.valid_to   >= :today)
price        = COALESCE(p.price, r.estimated_cost)
price_source = CASE WHEN p.price IS NOT NULL THEN 'WORKSHOP_PRICE' ELSE 'REFERENCE_PRICE' END
```

Khoá ghép là (`model_id`, `item_code`) — **không** ghép theo `item_name` (quy ước Q-402 core v1.3).

## RD-1002 — Xe còn bảo hành `[Đề xuất — Q-1001]`

```text
under_warranty = NOT EXISTS (vehicle_warranty WHERE user_vehicle_id=:v AND component='chassis')
              OR EXISTS     (vehicle_warranty WHERE user_vehicle_id=:v AND component='chassis' AND end_date >= :today)
```

Trường hợp không có dòng `chassis` ⇒ `warrantyStatus = UNKNOWN`, xử lý như còn bảo hành.

## RD-1003 — `model_id` của xe

Dùng `user_vehicle.external_model_id` (mã model từ hãng) — cùng miền với `maintenance_rule.model_id` và `service_price.model_id`.

---

# 3. Index & Query Requirements

| Query | Fields | Frequency | Index |
|---|---|---|---|
| Hạng mục theo mốc | `maintenance_rule(model_id, odo_milestone)` | Cao | Có (unique `model_id, odo_milestone, item_code` — core v1.3) |
| Danh sách mốc của model | `maintenance_rule(model_id)` | Trung bình | Dùng chung index trên |
| Giá hiện hành | `service_price(workshop_id, model_id, item_code)` | Cao | Có (service_price §11) |
| Bảo hành theo component | `vehicle_warranty(user_vehicle_id, component)` | Trung bình | Unique composite có sẵn (us-001) |

---

# 4. Khoảng trống dữ liệu (cần chốt)

| ID | Vấn đề | Ảnh hưởng | Đề xuất |
|---|---|---|---|
| `Q-ENT-1001` | `warranty_component_enum` không có "bảo hành toàn xe"; `maintenance_rule` không gắn component | Không xác định chính xác mục nào hết miễn phí khi một phần bảo hành hết hạn | MVP dùng `chassis`; phase sau thêm cột `maintenance_rule.warranty_component warranty_component_enum NULL` |
| `Q-ENT-1002` | `service_price` chưa có ràng buộc DB chống chồng lấn hiệu lực (BR-ENT-412 kiểm ở service) | Có thể ra 2 giá cho một hạng mục | Exclusion constraint `EXCLUDE USING gist (workshop_id WITH =, model_id WITH =, item_code WITH =, daterange(valid_from, valid_to, '[]') WITH &&)` — cần extension `btree_gist` |
| `Q-ENT-1003` | Chưa có seed `maintenance_rule` và `service_price` (kiểm tra 2026-09-30: `backend/seed.sql` không có `INSERT` cho hai bảng; chỉ có migration tạo bảng) | Dự toán luôn `NO_RULE` hoặc toàn giá tham khảo | Bổ sung seed định mức theo model + bảng giá 3–5 xưởng mock trước Demo 1 (M4) |

---

# 5. Ownership & Security

- Không có write. Đọc theo quyền chủ xe (xe của mình).
- Không đưa VIN/CCCD vào `chat_message.meta.estimate`; chỉ `model_id`, mốc, xưởng, dòng giá.

---

# 6. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu — xác nhận F5 không cần bảng mới; ghi khoảng trống dữ liệu bảo hành |
