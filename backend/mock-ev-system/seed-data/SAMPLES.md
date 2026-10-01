# mock-ev-system — Dữ liệu mẫu

3 dòng mẫu mỗi bảng, lấy từ mock-ev-system (http://localhost:8199) lúc 2026-10-01. Khi mock chạy bằng Docker, dữ liệu này đến từ bản dump dùng chung [`ev-mock-dump.sql`](ev-mock-dump.sql). Xem thêm hoặc truy vấn bằng [`tools/ev_mock_data`](../../../tools/ev_mock_data/README.md), ví dụ `python tools/ev_mock_data/ev_mock_data.py query vehicles`.

> Dữ liệu giả lập, không phải thông tin thật. Tạo lại file: `python tools/ev_mock_data/ev_mock_data.py samples`.

## Tổng quan

| Bảng (entity) | Mô tả | Khoá chính | Số dòng |
|---|---|---|---:|
| [`vehicle_models`](#vehicle_models) | Mẫu xe (master data) | `model_id` | 7 |
| [`owners`](#owners) | Chủ sở hữu xe | `owner_id` | 15 |
| [`service_centers`](#service_centers) | Đại lý / xưởng dịch vụ (kèm người quản lý dùng để xác thực) | `center_id` | 3 |
| [`vehicles`](#vehicles) | Xe cụ thể theo VIN | `vehicle_id` | 28 |
| [`vehicle_usage`](#vehicle_usage) | Snapshot ODO / pin hiện tại (1 xe : 1 dòng) | `vehicle_id` | 28 |
| [`warranty_policies`](#warranty_policies) | Chính sách bảo hành theo mẫu xe + bộ phận | `policy_id` | 28 |
| [`warranties`](#warranties) | Hợp đồng bảo hành của từng xe | `warranty_id` | 112 |
| [`warranty_claims`](#warranty_claims) | Yêu cầu bảo hành (approved / rejected / pending) | `claim_id` | 10 |
| [`maintenance_schedules`](#maintenance_schedules) | Lịch bảo dưỡng chuẩn theo mẫu xe | `schedule_id` | 35 |
| [`maintenance_items`](#maintenance_items) | Hạng mục trong một mốc bảo dưỡng | `item_id` | 27 |
| [`service_history`](#service_history) | Lịch sử bảo dưỡng thực tế | `order_id` | 68 |

## vehicle_models

Mẫu xe (master data) — 3/7 dòng.

| model_id | model_name | trim | battery_capacity_kwh | motor_power_kw | production_year |
|---|---|---|---|---|---|
| MDL-01 | VF5 | Plus | 37.2 | 134.0 | 2024 |
| MDL-03 | VF6 | Plus | 59.6 | 150.0 | 2024 |
| MDL-05 | VF8 | Eco | 87.7 | 300.0 | 2023 |

## owners

Chủ sở hữu xe — 3/15 dòng.

| owner_id | full_name | phone | email | national_id |
|---|---|---|---|---|
| OWN-001 | Nguyễn Văn An | 0901000001 | an.nguyen@example.com | 079200001001 |
| OWN-006 | Bùi Gia Nam | 0980668968 | nam.bui@example.com | 001074938273 |
| OWN-011 | Đỗ Anh Tuấn | 0942084090 | tuan.do@example.com | 001066531236 |

## service_centers

Đại lý / xưởng dịch vụ (kèm người quản lý dùng để xác thực) — 3/3 dòng.

| center_id | name | region | type | manager_email | manager_national_id |
|---|---|---|---|---|---|
| SC-01 | VinFast Thăng Long | Hà Nội | dealer | ha.tran.sc01@example.com | 001190000101 |
| SC-02 | VinFast Quận 7 | TP. Hồ Chí Minh | dealer | khoa.nguyen.sc02@example.com | 079190000202 |
| SC-03 | VinFast Đà Nẵng | Đà Nẵng | service_only | lan.vo.sc03@example.com | 048190000303 |

## vehicles

Xe cụ thể theo VIN — 3/28 dòng.

| vehicle_id | vin | model_id | current_owner_id | color | manufacture_date | license_plate |
|---|---|---|---|---|---|---|
| VEH-001 | VF5PLUS2024000001 | MDL-01 | OWN-001 | Xanh dương | 2024-03-15 | 30A-12345 |
| VEH-010 | VF8ECO20238238128 | MDL-05 | OWN-006 | Đỏ | 2023-11-04 | 30G-78767 |
| VEH-019 | VF8ECO20234882776 | MDL-05 | OWN-011 | Đỏ | 2023-02-02 | 30F-31153 |

## vehicle_usage

Snapshot ODO / pin hiện tại (1 xe : 1 dòng) — 3/28 dòng.

| vehicle_id | current_km | battery_soh | data_source | last_updated_at |
|---|---|---|---|---|
| VEH-001 | 42516 | 96.2 | telematics | 2026-10-01T05:40:43.728625 |
| VEH-010 | 54941 | 95.2 | manual | 2026-10-01T05:40:43.728625 |
| VEH-019 | 59334 | 96.2 | telematics | 2026-10-01T05:40:43.728625 |

## warranty_policies

Chính sách bảo hành theo mẫu xe + bộ phận — 3/28 dòng.

| policy_id | model_id | component | duration_months | km_limit | terms_description |
|---|---|---|---|---|---|
| WP-001 | MDL-01 | battery | 96 | 160000 | Pin lithium-ion: bảo hành 8 năm hoặc 160.000km (tùy điều kiện nào đến trước). Không áp dụng nếu pin bị hư do va đập, ngập nước, hoặc tự ý can thiệp. |
| WP-010 | MDL-03 | motor | 60 | 120000 | Động cơ điện: bảo hành 5 năm hoặc 120.000km. Không bao gồm hao mòn tự nhiên của bạc đạn. |
| WP-019 | MDL-05 | chassis | 36 | 100000 | Khung gầm: bảo hành 3 năm hoặc 100.000km. Không áp dụng cho hư hỏng do tai nạn. |

## warranties

Hợp đồng bảo hành của từng xe — 3/112 dòng.

| warranty_id | vehicle_id | policy_id | start_date | end_date | km_limit | status |
|---|---|---|---|---|---|---|
| WRT-001 | VEH-001 | WP-001 | 2024-03-15 | 2032-03-15 | 160000 | active |
| WRT-007 | VEH-002 | WP-019 | 2023-06-10 | 2026-06-10 | 100000 | expired |
| WRT-038 | VEH-010 | WP-018 | 2023-11-04 | 2028-11-04 | 120000 | active |

## warranty_claims

Yêu cầu bảo hành (approved / rejected / pending) — 3/10 dòng.

| claim_id | vehicle_id | warranty_id | claim_date | status | reject_reason |
|---|---|---|---|---|---|
| CLM-001 | VEH-002 | WRT-005 | 2026-07-15 | rejected | Pin giảm dung lượng 6.9% — chưa đạt ngưỡng bảo hành (>30% trong 8 năm đầu). Mức giảm nằm trong phạm vi hao mòn tự nhiên. |
| CLM-002 | VEH-007 | WRT-027 | 2026-02-10 | approved | — |
| CLM-004 | VEH-001 | WRT-002 | 2026-09-20 | pending | — |

## maintenance_schedules

Lịch bảo dưỡng chuẩn theo mẫu xe — 3/35 dòng.

| schedule_id | model_id | milestone_km | milestone_months | description |
|---|---|---|---|---|
| MS-001 | MDL-01 | 10000 | 6 | Bảo dưỡng định kỳ 10.000km / 6 tháng |
| MS-012 | MDL-03 | 20000 | 12 | Bảo dưỡng định kỳ 20.000km / 12 tháng |
| MS-023 | MDL-05 | 40000 | 24 | Bảo dưỡng lớn 40.000km / 24 tháng |

## maintenance_items

Hạng mục trong một mốc bảo dưỡng — 3/27 dòng.

| item_id | schedule_id | item_name | is_covered_by_warranty | reference_price |
|---|---|---|---|---|
| MI-001 | MS-001 | Kiểm tra & bổ sung dung dịch làm mát | True | 200000 |
| MI-010 | MS-003 | Thay lọc gió điều hòa | False | 350000 |
| MI-019 | MS-004 | Kiểm tra pin cao áp & hệ thống BMS | True | 0 |

## service_history

Lịch sử bảo dưỡng thực tế — 3/68 dòng.

| order_id | vehicle_id | service_center_id | service_date | km_at_service | items_done | is_periodic | total_cost |
|---|---|---|---|---|---|---|---|
| SH-001 | VEH-001 | SC-01 | 2024-09-20 | 10200 | Kiểm tra dung dịch làm mát, kiểm tra phanh, kiểm tra lốp | True | 150000 |
| SH-023 | VEH-009 | SC-01 | 2024-09-06 | 10936 | Bảo dưỡng định kỳ 10.000km / 6 tháng | True | 350000 |
| SH-045 | VEH-017 | SC-02 | 2024-09-12 | 20316 | Bảo dưỡng định kỳ 20.000km / 12 tháng | True | 0 |
