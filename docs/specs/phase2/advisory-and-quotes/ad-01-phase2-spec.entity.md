# Entity Specification — Giá bảo dưỡng theo mốc, tách phần bảo hành

> Entity cho Feature `FEAT-P2-AD01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-01-phase2-spec.ff.md). **API:** [API Spec](ad-01-phase2-spec.api.md).
>
> **Nguyên tắc:** AD-01 không thêm bảng. Dự toán vẫn là kết quả tính tại thời điểm hỏi từ `service_price` + `maintenance_rule` + bảo hành (F5, us-045). "Ngày cập nhật bảng giá" suy ra từ `service_price.updated_at` có sẵn; chỉ thêm index để đọc nhanh.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-AD01` — AD-01 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [ad-01-phase2-spec.ff.md](ad-01-phase2-spec.ff.md) |
| Related API | [ad-01-phase2-spec.api.md](ad-01-phase2-spec.api.md) |
| Related FE | [ad-01-phase2-spec.fe.md](ad-01-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-009` | `ServicePrice` | `service_price` | Có sẵn — thêm index | Đọc `max(updated_at)` theo (xưởng, model) |
| `ENT-401` | `MaintenanceRule` | `maintenance_rule` | Có sẵn — không đổi | Hạng mục của mốc |
| — | `VehicleWarranty` | `vehicle_warranty` | Có sẵn — không đổi | Hạng mục trong bảo hành (AD-03 mở rộng) |

---

# 2. Ngày cập nhật bảng giá

`price_updated_at(workshop, model) = max(service_price.updated_at)` của các dòng còn hiệu lực (`valid_to IS NULL OR valid_to ≥ today`) cho `model_id` của xe. Xưởng không có dòng nào ⇒ `NULL` (mọi hạng mục dùng giá tham khảo).

`stale = price_updated_at < now − PRICE_STALE_DAYS` (BR-AD01-02).

```sql
CREATE INDEX ix_service_price_freshness ON service_price (workshop_id, model_id, updated_at DESC);
```

Ghi chú: `updated_at` phải chỉ đổi khi giá / hạng mục thực sự đổi. Kiểm lại `PriceListService` (us-045): lưu bảng giá không đổi giá trị thì **không** chạm `updated_at` (tránh "làm mới giả"). Thay đổi nhỏ trong service, không đổi schema.

---

# 3. Phân loại bảo hành từng hạng mục

Giữ `is_covered_by_warranty` của F5; thêm trạng thái thứ ba trong **kết quả tính** (không lưu DB):

| `warrantyStatus` | Khi | Tiền tính vào |
|---|---|---|
| `COVERED` | Hạng mục thuộc bảo hành và xe còn bảo hành (theo `vehicle_warranty` + AD-03) | `warrantyTotal` |
| `CHARGEABLE` | Ngoài bảo hành | `ownerTotal` |
| `UNDETERMINED` | Không xác định được (thiếu dữ liệu bảo hành, EF-AD01-02) | `ownerTotal` (không tự giả định miễn phí) + nhãn "chưa xác định bảo hành" |

Bất biến (AC-AD01-03): `warrantyTotal + ownerTotal = itemsTotal` cho từng xưởng.

---

# 4. Migration

Một revision: index `ix_service_price_freshness`. Không đổi cột.

---

# 5. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
