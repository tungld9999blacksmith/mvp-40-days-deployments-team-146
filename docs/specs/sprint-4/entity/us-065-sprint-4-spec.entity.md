# Entity Specification — Lịch sử dịch vụ của xe

> Entity cho Feature `FEAT-VEH-002` (US-065 → US-068).
>
> **Nguyên tắc:** **không thêm bảng, không đổi cột.** Lịch sử dịch vụ đọc `vehicle_service_record` (ENT-415) đã đặc tả ở [us-017 Entity](../../sprint-2/entity/us-017-sprint-2-spec.entity.md#ent-415--vehicleservicerecord) và đã có migration. Tài liệu này ghi các truy vấn mới, luật đọc, và một đề xuất nhỏ cho cột `items_done` của dòng EV Care.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-VEH-002` — mở rộng F3 |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-07` |
| Related FF | [us-065-sprint-4-spec.ff.md](../feature-functional/us-065-sprint-4-spec.ff.md) |
| Related API | [us-065-sprint-4-spec.api.md](../api/us-065-sprint-4-spec.api.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Vai trò ở feature này |
|---|---|---|---|---|
| `ENT-415` | `VehicleServiceRecord` | `vehicle_service_record` | Có sẵn — **không đổi** | Mỗi dòng là một lần dịch vụ |
| `ENT-003` | `UserVehicle` | `user_vehicle` | Có sẵn — không đổi | Quyền sở hữu, trạng thái xe |
| `ENT-402` | `Booking` | `booking` | Có sẵn — không đổi | `booking_code`, `actual_cost` của dòng EV Care |
| `ENT-008` | `Workshop` | `workshop` | Có sẵn — không đổi | Tên xưởng, ghép theo `id` hoặc `external_center_id` |

---

# 2. Cột của ENT-415 dùng cho lịch sử

| Field | Type | Nullable | Ý nghĩa ở màn lịch sử | FF |
|---|---|---:|---|---|
| `id` | `uuid` | No | `recordId` | — |
| `user_vehicle_id` | `uuid` | No | Lọc theo xe (FK `ON DELETE CASCADE`) | BR-1608 |
| `source` | `service_record_source_enum` (`oem` / `ev_care`) | No | Nguồn | BR-1602 |
| `external_order_id` | `varchar(64)` | Yes | Khoá upsert của dòng `oem`; không trả ra API | BR-1602 |
| `booking_id` | `uuid` | Yes | Lịch hẹn của dòng `ev_care` (FK `ON DELETE SET NULL`) | BR-1609 |
| `service_date` | `date` | No | Ngày dịch vụ | BR-1603 |
| `odo_km` | `integer` | Yes | ODO lúc làm, `0…999999` | EDGE-1602 |
| `external_center_id` | `varchar(64)` | Yes | Mã trung tâm của hãng, dùng ghép xưởng khi `workshop_id` trống | BR-1606 |
| `workshop_id` | `uuid` | Yes | Xưởng EV Care (FK `ON DELETE SET NULL`) | BR-1606 |
| `items_done` | `text` | Yes | Ghi chú hạng mục | BR-1605 |
| `is_periodic` | `boolean` | No | Định kỳ / ngoài định kỳ, mặc định `true` | BR-1604 |

Các ràng buộc hiện có bảo đảm FF BR-1602:

- `ux_service_record_oem_order (user_vehicle_id, external_order_id) WHERE source = 'oem'` — một dòng mỗi đơn hãng.
- `ux_service_record_booking (booking_id) WHERE source = 'ev_care'` — một dòng mỗi lịch hẹn.
- `ck_service_record_booking_only_ev_care`, `ck_service_record_oem_order`, `ck_service_record_order_only_oem`.

---

# 3. Business Rules (đọc)

## BR-ENT-1601 — Chỉ ghi bởi hai writer

Chỉ `OemVehicleSyncService` (dòng `oem`) và `WorkshopBoardService._on_completed` (dòng `ev_care`, trong transaction của action `COMPLETE`) được ghi bảng này. Không có đường ghi nào từ request của chủ xe (FF BR-1601).

## BR-ENT-1602 — Thứ tự đọc

`ORDER BY service_date DESC, odo_km DESC NULLS LAST` (FF BR-1603).

## BR-ENT-1603 — Dòng EV Care lấy giá trị lúc hoàn tất

Khi `COMPLETE`: `service_date` = ngày hoàn tất theo giờ Việt Nam; `odo_km` = ODO lớn nhất đã ghi nhận của xe (`vehicle_odometer_reading`, ENT-414); `workshop_id`, `external_center_id` = xưởng của lịch hẹn; `is_periodic = (booking.odo_milestone IS NOT NULL)` (FF BR-1604); `items_done = NULL` (xem §5).

---

# 4. Index & Query

| Truy vấn | Index dùng |
|---|---|
| Lịch sử của một xe, mới nhất trước | `ix_service_record_vehicle_date (user_vehicle_id, service_date, odo_km)` |
| Ghép xưởng theo `id` hoặc `external_center_id` (1 truy vấn `IN`) | PK `workshop`, unique `workshop.external_center_id` |
| Ghép lịch hẹn (1 truy vấn `IN`) | PK `booking` |

Không cần index mới.

---

# 5. Đề xuất — `items_done` cho dòng EV Care (Q-1603)

Hiện `_on_completed` không ghi `items_done`, nên dòng EV Care chỉ hiện nhãn "Bảo dưỡng định kỳ". `[Đề xuất]` khi `booking.odo_milestone` có giá trị, ghi `items_done = 'Bảo dưỡng mốc {odo_milestone:,} km'` (định dạng `12.000`). Không cần migration (cột đã có). Chờ PO chốt.

---

# 6. Ownership, Sensitivity & Retention

| Mục | Quy tắc |
|---|---|
| Ownership | Dòng thuộc chủ xe qua `user_vehicle.user_id`; mọi truy vấn API lọc theo xe đã kiểm quyền |
| Sensitivity | `items_done` của hãng có thể chứa ghi chú tự do ⇒ không log, không đưa vào prompt AI khi không cần |
| Retention | Theo vòng đời `user_vehicle` (`ON DELETE CASCADE`); không có job xoá riêng |

---

# 7. Open Questions

| ID | Question | Status |
|---|---|---|
| `Q-1603` | Ghi `items_done` cho dòng `ev_care` (§5) | Open — `[Đề xuất]` có |
| `Q-1601` | Gộp dòng `oem` và `ev_care` của cùng một lần (FF EDGE-1601) | Open — `[Đề xuất]` MVP không gộp |

---

# 8. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-10-07` | Team 4 Người | Bản đầu |
