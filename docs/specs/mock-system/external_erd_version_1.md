# Lược đồ thực thể quan hệ từ databse bên ngoài

- Đây là những thực thể (entity) của hệ thống công ty xe điện cần thiết cho hệ thống bảo trì, chúng ta sẽ dựa vào list những entity và trường gợi ý để hiểu, thêm, sửa...

## Nhóm entity từ system hệ thống xe điện

| Entity | Vai trò | Field gợi ý chính |
|---|---|---|
| **VehicleModel** | Định nghĩa mẫu xe (VF6, VF7, VF8...) | model_id, model_name, version/trim, battery_capacity, motor_spec, production_year |
| **Vehicle** | Một chiếc xe cụ thể (theo VIN) | vehicle_id, VIN, model_id (FK), color, manufacture_date, license_plate, current_owner_id (FK) |
| **Owner** | Chủ sở hữu xe | owner_id, full_name, phone, email, national_id, address |
| **VehicleUsageInfo** | Số km, dữ liệu sử dụng thực tế | vehicle_id (FK), current_km, last_updated_at, data_source (telematics/manual) |
| **Warranty** | Bảo hành áp dụng cho 1 xe cụ thể | warranty_id, vehicle_id (FK), warranty_type, start_date, end_date, km_limit, status |

## Đề xuất bổ sung — nhóm nên có (core)

| Entity | Vì sao cần | Field gợi ý chính |
|---|---|---|
| **WarrantyPolicy** | Bảo hành xe điện thường **không đồng nhất**: pin có thể là 8 năm/160.000km, động cơ 5 năm, khung gầm 3 năm... `Warranty` chỉ là instance áp dụng cho 1 xe, còn đây là **quy tắc gốc** theo model, để hệ thống biết áp dụng đúng điều khoản. | policy_id, model_id (FK), component_type, duration_months, km_limit, terms_description |
| **WarrantyComponent** (loại hạng mục bảo hành) | Tách riêng "Pin", "Động cơ điện", "Khung gầm", "Hệ thống điện tử"... mỗi loại có điều khoản khác nhau — cần bảng danh mục để chuẩn hóa, tránh hard-code text. | component_id, component_name, description |
| **BatteryInfo** | Pin là bộ phận đặc thù & đắt giá nhất ở xe điện, thường theo dõi/bảo hành riêng biệt. Cần biết tình trạng pin (SOH) để tư vấn đúng và xác định có thuộc diện bảo hành hay không. | vehicle_id (FK), battery_serial_number, design_capacity, current_soh, charge_cycles |
| **MaintenanceSchedule** (lịch bảo dưỡng chuẩn của hãng) | Đây chính là "nguồn sự thật" cho flow AI nhắc lịch — hãng định nghĩa mốc km/tháng cần làm gì theo từng model, **không phải hệ thống bạn tự đặt**. | schedule_id, model_id (FK), milestone_km, milestone_months, description |
| **MaintenanceItem** | Chi tiết từng hạng mục trong 1 mốc bảo dưỡng (thay lọc gió, kiểm tra phanh...), có cờ trong/ngoài bảo hành, giá tham khảo — chính là dữ liệu flow "AI tư vấn chi phí" cần tra. | item_id, schedule_id (FK), item_name, is_covered_by_warranty, reference_price |
| **ServiceHistory / RepairOrder** | Bản ghi mỗi lần xe được bảo dưỡng/sửa chữa thực tế tại xưởng chính hãng — ngày, km lúc đó, hạng mục đã làm, chi phí thực tế. Đây là nguồn để tính "mốc bảo dưỡng gần nhất" thay vì chỉ dựa vào lịch chuẩn lý thuyết. | order_id, vehicle_id (FK), service_center_id (FK), date, km_at_service, items_done, total_cost |
| **WarrantyClaim** | Ghi nhận từng lần khách **yêu cầu bảo hành**: được duyệt hay từ chối, lý do — liên quan trực tiếp pain point "không hiểu vì sao bị từ chối bảo hành" bạn nêu ở đầu dự án. | claim_id, vehicle_id (FK), warranty_id (FK), claim_date, status, reject_reason |
| **ServiceCenter / Dealer** | Đại lý/xưởng dịch vụ chính hãng — nơi bán xe và nơi thực hiện bảo dưỡng. Cần cho `ServiceHistory`, và là dữ liệu gốc để hệ thống bạn (xưởng đặt lịch) tham chiếu. | center_id, name, address, region, type (dealer/service_only) |

## Nhóm nên cân nhắc thêm (mở rộng, không bắt buộc ở MVP)

| Entity | Vì sao có thể cần | Ghi chú |
|---|---|---|
| **OwnershipHistory** | Xe bán lại cho chủ mới — bảo hành có được chuyển tiếp hay không tùy chính sách hãng. Nếu chỉ lưu `current_owner_id` trên bảng `Vehicle` sẽ mất lịch sử này. | Quan trọng nếu sản phẩm định hỗ trợ cả xe cũ đã sang tên |
| **RecallCampaign** | Chiến dịch triệu hồi/khắc phục lỗi hàng loạt theo model hoặc lô sản xuất — khác bảo dưỡng định kỳ nhưng ảnh hưởng đến việc AI có cần chủ động nhắc khách ngoài lịch thường hay không. | Có thể bổ sung ở phase sau |
| **PartCatalog** | Danh mục phụ tùng + đơn giá theo model, liên kết với `WarrantyComponent` để biết phụ tùng có được bảo hành không. | Giúp flow tư vấn giá chính xác hơn, nhưng có thể dùng `MaintenanceItem.reference_price` tạm ở MVP |
| **SoftwareVersion (OTA)** | Xe điện có cập nhật phần mềm qua OTA, một số hãng có điều khoản bảo hành riêng cho phần mềm/tính năng. | Thường không cần thiết ở MVP trừ khi dự án có liên quan đến lỗi phần mềm |

---

**Quan hệ chính (tóm tắt):**
`VehicleModel` 1—n `Vehicle` · `Vehicle` 1—n `VehicleUsageInfo`/`ServiceHistory`/`WarrantyClaim` · `Vehicle` n—1 `Owner` (qua `OwnershipHistory` nếu cần lịch sử) · `VehicleModel` 1—n `WarrantyPolicy` và `MaintenanceSchedule` · `MaintenanceSchedule` 1—n `MaintenanceItem` · `Vehicle` 1—1 `BatteryInfo` · `ServiceHistory` n—1 `ServiceCenter`.

