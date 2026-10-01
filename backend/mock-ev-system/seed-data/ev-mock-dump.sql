BEGIN TRANSACTION;
CREATE TABLE maintenance_item (
	item_id VARCHAR NOT NULL, 
	schedule_id VARCHAR NOT NULL, 
	item_name VARCHAR NOT NULL, 
	is_covered_by_warranty BOOLEAN NOT NULL, 
	reference_price NUMERIC NOT NULL, 
	PRIMARY KEY (item_id), 
	FOREIGN KEY(schedule_id) REFERENCES maintenance_schedule (schedule_id)
);
INSERT INTO "maintenance_item" VALUES('MI-001','MS-001','Kiểm tra & bổ sung dung dịch làm mát',1,200000);
INSERT INTO "maintenance_item" VALUES('MI-002','MS-001','Kiểm tra hệ thống phanh',1,0);
INSERT INTO "maintenance_item" VALUES('MI-003','MS-001','Kiểm tra lốp & áp suất',0,150000);
INSERT INTO "maintenance_item" VALUES('MI-004','MS-001','Kiểm tra hệ thống treo',1,0);
INSERT INTO "maintenance_item" VALUES('MI-005','MS-002','Thay lọc gió điều hòa',0,350000);
INSERT INTO "maintenance_item" VALUES('MI-006','MS-002','Kiểm tra & bổ sung dung dịch làm mát',1,200000);
INSERT INTO "maintenance_item" VALUES('MI-007','MS-002','Kiểm tra hệ thống phanh',1,0);
INSERT INTO "maintenance_item" VALUES('MI-008','MS-002','Kiểm tra bình ắc-quy 12V',1,0);
INSERT INTO "maintenance_item" VALUES('MI-009','MS-002','Kiểm tra hệ thống sạc',1,0);
INSERT INTO "maintenance_item" VALUES('MI-010','MS-003','Thay lọc gió điều hòa',0,350000);
INSERT INTO "maintenance_item" VALUES('MI-011','MS-003','Thay dung dịch làm mát',0,800000);
INSERT INTO "maintenance_item" VALUES('MI-012','MS-003','Thay dung dịch phanh',0,450000);
INSERT INTO "maintenance_item" VALUES('MI-013','MS-003','Kiểm tra má phanh',1,0);
INSERT INTO "maintenance_item" VALUES('MI-014','MS-003','Kiểm tra hệ thống treo & gầm',1,0);
INSERT INTO "maintenance_item" VALUES('MI-015','MS-003','Cân bằng & đảo lốp',0,300000);
INSERT INTO "maintenance_item" VALUES('MI-016','MS-004','Thay lọc gió điều hòa',0,350000);
INSERT INTO "maintenance_item" VALUES('MI-017','MS-004','Thay dung dịch phanh',0,450000);
INSERT INTO "maintenance_item" VALUES('MI-018','MS-004','Thay má phanh trước',0,1500000);
INSERT INTO "maintenance_item" VALUES('MI-019','MS-004','Kiểm tra pin cao áp & hệ thống BMS',1,0);
INSERT INTO "maintenance_item" VALUES('MI-020','MS-004','Kiểm tra motor & hộp giảm tốc',1,0);
INSERT INTO "maintenance_item" VALUES('MI-021','MS-005','Thay lọc gió điều hòa',0,350000);
INSERT INTO "maintenance_item" VALUES('MI-022','MS-005','Thay dung dịch làm mát',0,800000);
INSERT INTO "maintenance_item" VALUES('MI-023','MS-005','Thay dung dịch phanh',0,450000);
INSERT INTO "maintenance_item" VALUES('MI-024','MS-005','Thay má phanh sau',0,1200000);
INSERT INTO "maintenance_item" VALUES('MI-025','MS-005','Thay lốp (bộ 4)',0,12000000);
INSERT INTO "maintenance_item" VALUES('MI-026','MS-005','Kiểm tra toàn diện hệ thống điện cao áp',1,0);
INSERT INTO "maintenance_item" VALUES('MI-027','MS-005','Cân chỉnh hệ thống ADAS',1,0);
CREATE TABLE maintenance_schedule (
	schedule_id VARCHAR NOT NULL, 
	model_id VARCHAR NOT NULL, 
	milestone_km INTEGER NOT NULL, 
	milestone_months INTEGER NOT NULL, 
	description VARCHAR NOT NULL, 
	PRIMARY KEY (schedule_id), 
	FOREIGN KEY(model_id) REFERENCES vehicle_model (model_id)
);
INSERT INTO "maintenance_schedule" VALUES('MS-001','MDL-01',10000,6,'Bảo dưỡng định kỳ 10.000km / 6 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-002','MDL-01',20000,12,'Bảo dưỡng định kỳ 20.000km / 12 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-003','MDL-01',40000,24,'Bảo dưỡng lớn 40.000km / 24 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-004','MDL-01',60000,36,'Bảo dưỡng lớn 60.000km / 36 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-005','MDL-01',80000,48,'Bảo dưỡng toàn diện 80.000km / 48 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-006','MDL-02',10000,6,'Bảo dưỡng định kỳ 10.000km / 6 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-007','MDL-02',20000,12,'Bảo dưỡng định kỳ 20.000km / 12 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-008','MDL-02',40000,24,'Bảo dưỡng lớn 40.000km / 24 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-009','MDL-02',60000,36,'Bảo dưỡng lớn 60.000km / 36 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-010','MDL-02',80000,48,'Bảo dưỡng toàn diện 80.000km / 48 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-011','MDL-03',10000,6,'Bảo dưỡng định kỳ 10.000km / 6 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-012','MDL-03',20000,12,'Bảo dưỡng định kỳ 20.000km / 12 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-013','MDL-03',40000,24,'Bảo dưỡng lớn 40.000km / 24 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-014','MDL-03',60000,36,'Bảo dưỡng lớn 60.000km / 36 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-015','MDL-03',80000,48,'Bảo dưỡng toàn diện 80.000km / 48 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-016','MDL-04',10000,6,'Bảo dưỡng định kỳ 10.000km / 6 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-017','MDL-04',20000,12,'Bảo dưỡng định kỳ 20.000km / 12 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-018','MDL-04',40000,24,'Bảo dưỡng lớn 40.000km / 24 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-019','MDL-04',60000,36,'Bảo dưỡng lớn 60.000km / 36 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-020','MDL-04',80000,48,'Bảo dưỡng toàn diện 80.000km / 48 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-021','MDL-05',10000,6,'Bảo dưỡng định kỳ 10.000km / 6 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-022','MDL-05',20000,12,'Bảo dưỡng định kỳ 20.000km / 12 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-023','MDL-05',40000,24,'Bảo dưỡng lớn 40.000km / 24 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-024','MDL-05',60000,36,'Bảo dưỡng lớn 60.000km / 36 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-025','MDL-05',80000,48,'Bảo dưỡng toàn diện 80.000km / 48 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-026','MDL-06',10000,6,'Bảo dưỡng định kỳ 10.000km / 6 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-027','MDL-06',20000,12,'Bảo dưỡng định kỳ 20.000km / 12 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-028','MDL-06',40000,24,'Bảo dưỡng lớn 40.000km / 24 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-029','MDL-06',60000,36,'Bảo dưỡng lớn 60.000km / 36 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-030','MDL-06',80000,48,'Bảo dưỡng toàn diện 80.000km / 48 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-031','MDL-07',10000,6,'Bảo dưỡng định kỳ 10.000km / 6 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-032','MDL-07',20000,12,'Bảo dưỡng định kỳ 20.000km / 12 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-033','MDL-07',40000,24,'Bảo dưỡng lớn 40.000km / 24 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-034','MDL-07',60000,36,'Bảo dưỡng lớn 60.000km / 36 tháng');
INSERT INTO "maintenance_schedule" VALUES('MS-035','MDL-07',80000,48,'Bảo dưỡng toàn diện 80.000km / 48 tháng');
CREATE TABLE owner (
	owner_id VARCHAR NOT NULL, 
	full_name VARCHAR NOT NULL, 
	phone VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	national_id VARCHAR NOT NULL, 
	PRIMARY KEY (owner_id)
);
INSERT INTO "owner" VALUES('OWN-001','Nguyễn Văn An','0901000001','an.nguyen@example.com','079200001001');
INSERT INTO "owner" VALUES('OWN-002','Trần Thị Bình','0901000002','binh.tran@example.com','079200001002');
INSERT INTO "owner" VALUES('OWN-003','Lê Hoàng Cường','0901000003','cuong.le@example.com','079200001003');
INSERT INTO "owner" VALUES('OWN-004','Phạm Minh Dũng','0901000004','dung.pham@example.com','079200001004');
INSERT INTO "owner" VALUES('OWN-005','Hoàng Thị Em','0901000005','em.hoang@example.com','079200001005');
INSERT INTO "owner" VALUES('OWN-006','Bùi Gia Nam','0980668968','nam.bui@example.com','001074938273');
INSERT INTO "owner" VALUES('OWN-007','Phạm Hoài Tâm','0973233523','tam.pham@example.com','001190749231');
INSERT INTO "owner" VALUES('OWN-008','Ngô Hữu Long','0960563108','long.ngo@example.com','001065000224');
INSERT INTO "owner" VALUES('OWN-009','Dương Bảo Hạnh','0904583896','hanh.duong@example.com','079095418546');
INSERT INTO "owner" VALUES('OWN-010','Huỳnh Thanh Hà','0955799328','ha.huynh@example.com','079189521773');
INSERT INTO "owner" VALUES('OWN-011','Đỗ Anh Tuấn','0942084090','tuan.do@example.com','001066531236');
INSERT INTO "owner" VALUES('OWN-012','Võ Ngọc Hoa','0995988852','hoa.vo@example.com','079163771109');
INSERT INTO "owner" VALUES('OWN-013','Vũ Hữu Hà','0974477168','ha.vu@example.com','031094716966');
INSERT INTO "owner" VALUES('OWN-014','Võ Thanh Yến','0961641870','yen.vo@example.com','049083376552');
INSERT INTO "owner" VALUES('OWN-015','Huỳnh Anh Nam','0972356296','nam.huynh@example.com','049071329957');
CREATE TABLE service_center (
	center_id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	region VARCHAR NOT NULL, 
	type VARCHAR(12) NOT NULL, 
	manager_email VARCHAR NOT NULL, 
	manager_national_id VARCHAR NOT NULL, 
	PRIMARY KEY (center_id)
);
INSERT INTO "service_center" VALUES('SC-01','VinFast Thăng Long','Hà Nội','dealer','ha.tran.sc01@example.com','001190000101');
INSERT INTO "service_center" VALUES('SC-02','VinFast Quận 7','TP. Hồ Chí Minh','dealer','khoa.nguyen.sc02@example.com','079190000202');
INSERT INTO "service_center" VALUES('SC-03','VinFast Đà Nẵng','Đà Nẵng','service_only','lan.vo.sc03@example.com','048190000303');
CREATE TABLE service_history (
	order_id VARCHAR NOT NULL, 
	vehicle_id VARCHAR NOT NULL, 
	service_center_id VARCHAR NOT NULL, 
	service_date DATE NOT NULL, 
	km_at_service INTEGER NOT NULL, 
	items_done VARCHAR NOT NULL, 
	is_periodic BOOLEAN NOT NULL, 
	total_cost NUMERIC NOT NULL, 
	PRIMARY KEY (order_id), 
	FOREIGN KEY(vehicle_id) REFERENCES vehicle (vehicle_id), 
	FOREIGN KEY(service_center_id) REFERENCES service_center (center_id)
);
INSERT INTO "service_history" VALUES('SH-001','VEH-001','SC-01','2024-09-20',10200,'Kiểm tra dung dịch làm mát, kiểm tra phanh, kiểm tra lốp',1,150000);
INSERT INTO "service_history" VALUES('SH-002','VEH-001','SC-01','2025-03-15',20500,'Thay lọc gió điều hòa, kiểm tra phanh, kiểm tra ắc-quy 12V',1,350000);
INSERT INTO "service_history" VALUES('SH-003','VEH-001','SC-01','2026-02-10',38100,'Thay lọc gió, thay dung dịch làm mát, thay dung dịch phanh, đảo lốp',1,1900000);
INSERT INTO "service_history" VALUES('SH-004','VEH-002','SC-01','2023-12-05',9800,'Kiểm tra dung dịch làm mát, kiểm tra phanh',1,0);
INSERT INTO "service_history" VALUES('SH-005','VEH-002','SC-02','2024-07-20',21000,'Thay lọc gió điều hòa, kiểm tra ắc-quy',1,350000);
INSERT INTO "service_history" VALUES('SH-006','VEH-002','SC-01','2025-06-10',41500,'Thay dung dịch làm mát, thay dung dịch phanh, cân bằng lốp',1,1550000);
INSERT INTO "service_history" VALUES('SH-007','VEH-003','SC-02','2024-08-01',10500,'Kiểm tra phanh, kiểm tra lốp & áp suất',1,150000);
INSERT INTO "service_history" VALUES('SH-008','VEH-003','SC-02','2025-03-20',22000,'Thay lọc gió điều hòa, kiểm tra hệ thống sạc',1,350000);
INSERT INTO "service_history" VALUES('SH-009','VEH-004','SC-03','2024-03-10',10100,'Kiểm tra dung dịch, kiểm tra phanh',1,0);
INSERT INTO "service_history" VALUES('SH-010','VEH-004','SC-03','2024-10-15',20800,'Thay lọc gió điều hòa, kiểm tra ắc-quy, kiểm tra sạc',1,350000);
INSERT INTO "service_history" VALUES('SH-011','VEH-004','SC-03','2025-12-01',42000,'Thay dung dịch làm mát, thay dung dịch phanh, đảo lốp',1,1550000);
INSERT INTO "service_history" VALUES('SH-012','VEH-005','SC-01','2024-05-20',10300,'Kiểm tra phanh, kiểm tra hệ thống treo',1,0);
INSERT INTO "service_history" VALUES('SH-013','VEH-005','SC-01','2025-01-10',21200,'Thay lọc gió điều hòa',1,350000);
INSERT INTO "service_history" VALUES('SH-014','VEH-005','SC-01','2026-01-20',40500,'Thay dung dịch làm mát, thay dung dịch phanh, cân bằng đảo lốp',1,1900000);
INSERT INTO "service_history" VALUES('SH-015','VEH-006','SC-01','2024-11-20',10000,'Kiểm tra dung dịch, phanh, lốp',1,150000);
INSERT INTO "service_history" VALUES('SH-016','VEH-006','SC-02','2025-07-05',20200,'Thay lọc gió điều hòa, kiểm tra ắc-quy 12V',1,350000);
INSERT INTO "service_history" VALUES('SH-017','VEH-007','SC-02','2023-10-15',10400,'Kiểm tra dung dịch, phanh, lốp',1,0);
INSERT INTO "service_history" VALUES('SH-018','VEH-007','SC-02','2024-05-10',20900,'Thay lọc gió điều hòa, kiểm tra ắc-quy, kiểm tra sạc',1,350000);
INSERT INTO "service_history" VALUES('SH-019','VEH-007','SC-02','2025-03-01',41800,'Thay dung dịch làm mát, thay dung dịch phanh, đảo lốp, kiểm tra má phanh',1,1550000);
INSERT INTO "service_history" VALUES('SH-020','VEH-008','SC-01','2024-03-24',10204,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,150000);
INSERT INTO "service_history" VALUES('SH-021','VEH-008','SC-01','2024-11-02',19912,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,900000);
INSERT INTO "service_history" VALUES('SH-022','VEH-008','SC-01','2026-02-11',40251,'Bảo dưỡng lớn 40.000km / 24 tháng',1,2500000);
INSERT INTO "service_history" VALUES('SH-023','VEH-009','SC-01','2024-09-06',10936,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,350000);
INSERT INTO "service_history" VALUES('SH-024','VEH-009','SC-01','2025-02-11',19385,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,1900000);
INSERT INTO "service_history" VALUES('SH-025','VEH-009','SC-01','2026-03-23',40976,'Bảo dưỡng lớn 40.000km / 24 tháng',1,900000);
INSERT INTO "service_history" VALUES('SH-026','VEH-010','SC-01','2024-05-22',10378,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,150000);
INSERT INTO "service_history" VALUES('SH-027','VEH-010','SC-01','2024-12-17',21171,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,2500000);
INSERT INTO "service_history" VALUES('SH-028','VEH-010','SC-01','2025-12-19',40162,'Bảo dưỡng lớn 40.000km / 24 tháng',1,900000);
INSERT INTO "service_history" VALUES('SH-029','VEH-011','SC-01','2024-02-01',10423,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,1900000);
INSERT INTO "service_history" VALUES('SH-030','VEH-011','SC-01','2024-07-25',19937,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,350000);
INSERT INTO "service_history" VALUES('SH-031','VEH-011','SC-01','2025-08-01',40155,'Bảo dưỡng lớn 40.000km / 24 tháng',1,900000);
INSERT INTO "service_history" VALUES('SH-032','VEH-011','SC-01','2026-08-20',61058,'Bảo dưỡng lớn 60.000km / 36 tháng',1,350000);
INSERT INTO "service_history" VALUES('SH-033','VEH-012','SC-01','2025-04-07',10181,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,2500000);
INSERT INTO "service_history" VALUES('SH-034','VEH-012','SC-01','2025-11-19',20220,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,0);
INSERT INTO "service_history" VALUES('SH-035','VEH-013','SC-01','2023-08-02',9841,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,2500000);
INSERT INTO "service_history" VALUES('SH-036','VEH-013','SC-01','2024-01-17',19476,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,900000);
INSERT INTO "service_history" VALUES('SH-037','VEH-013','SC-01','2025-01-29',41162,'Bảo dưỡng lớn 40.000km / 24 tháng',1,0);
INSERT INTO "service_history" VALUES('SH-038','VEH-013','SC-01','2025-12-14',59527,'Bảo dưỡng lớn 60.000km / 36 tháng',1,1900000);
INSERT INTO "service_history" VALUES('SH-039','VEH-014','SC-01','2026-01-21',20523,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,0);
INSERT INTO "service_history" VALUES('SH-040','VEH-015','SC-01','2025-04-10',10848,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,150000);
INSERT INTO "service_history" VALUES('SH-041','VEH-015','SC-01','2025-09-22',19623,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,1900000);
INSERT INTO "service_history" VALUES('SH-042','VEH-016','SC-02','2024-07-15',19580,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,350000);
INSERT INTO "service_history" VALUES('SH-043','VEH-016','SC-02','2025-11-22',40048,'Bảo dưỡng lớn 40.000km / 24 tháng',1,900000);
INSERT INTO "service_history" VALUES('SH-044','VEH-017','SC-02','2024-01-13',10999,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,2500000);
INSERT INTO "service_history" VALUES('SH-045','VEH-017','SC-02','2024-09-12',20316,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,0);
INSERT INTO "service_history" VALUES('SH-046','VEH-017','SC-02','2026-01-27',39521,'Bảo dưỡng lớn 40.000km / 24 tháng',1,1900000);
INSERT INTO "service_history" VALUES('SH-047','VEH-018','SC-02','2025-01-28',21155,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,150000);
INSERT INTO "service_history" VALUES('SH-048','VEH-019','SC-01','2023-09-16',10048,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,0);
INSERT INTO "service_history" VALUES('SH-049','VEH-020','SC-01','2024-10-10',11093,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,350000);
INSERT INTO "service_history" VALUES('SH-050','VEH-020','SC-01','2025-04-27',20416,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,900000);
INSERT INTO "service_history" VALUES('SH-051','VEH-020','SC-01','2026-07-09',40998,'Bảo dưỡng lớn 40.000km / 24 tháng',1,2500000);
INSERT INTO "service_history" VALUES('SH-052','VEH-021','SC-02','2024-12-24',9901,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,1900000);
INSERT INTO "service_history" VALUES('SH-053','VEH-022','SC-02','2024-12-10',10069,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,350000);
INSERT INTO "service_history" VALUES('SH-054','VEH-022','SC-02','2025-08-24',19972,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,900000);
INSERT INTO "service_history" VALUES('SH-055','VEH-023','SC-01','2024-09-14',10415,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,150000);
INSERT INTO "service_history" VALUES('SH-056','VEH-023','SC-03','2025-03-10',20531,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,350000);
INSERT INTO "service_history" VALUES('SH-057','VEH-023','SC-03','2026-02-18',40265,'Bảo dưỡng lớn 40.000km / 24 tháng',1,350000);
INSERT INTO "service_history" VALUES('SH-058','VEH-024','SC-02','2025-06-18',10726,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,2500000);
INSERT INTO "service_history" VALUES('SH-059','VEH-024','SC-01','2025-12-28',21147,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,1900000);
INSERT INTO "service_history" VALUES('SH-060','VEH-025','SC-03','2024-05-07',10910,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,2500000);
INSERT INTO "service_history" VALUES('SH-061','VEH-025','SC-03','2024-10-17',19276,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,150000);
INSERT INTO "service_history" VALUES('SH-062','VEH-026','SC-02','2025-07-08',9291,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,900000);
INSERT INTO "service_history" VALUES('SH-063','VEH-026','SC-03','2026-06-26',21188,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,2500000);
INSERT INTO "service_history" VALUES('SH-064','VEH-027','SC-02','2023-10-02',9784,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,150000);
INSERT INTO "service_history" VALUES('SH-065','VEH-027','SC-03','2024-04-14',19586,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,2500000);
INSERT INTO "service_history" VALUES('SH-066','VEH-027','SC-02','2026-06-29',60183,'Bảo dưỡng lớn 60.000km / 36 tháng',1,350000);
INSERT INTO "service_history" VALUES('SH-067','VEH-028','SC-01','2024-07-28',9708,'Bảo dưỡng định kỳ 10.000km / 6 tháng',1,0);
INSERT INTO "service_history" VALUES('SH-068','VEH-028','SC-01','2025-02-24',20192,'Bảo dưỡng định kỳ 20.000km / 12 tháng',1,2500000);
CREATE TABLE vehicle (
	vehicle_id VARCHAR NOT NULL, 
	vin VARCHAR NOT NULL, 
	model_id VARCHAR NOT NULL, 
	current_owner_id VARCHAR NOT NULL, 
	color VARCHAR NOT NULL, 
	manufacture_date DATE NOT NULL, 
	license_plate VARCHAR NOT NULL, 
	PRIMARY KEY (vehicle_id), 
	FOREIGN KEY(model_id) REFERENCES vehicle_model (model_id), 
	FOREIGN KEY(current_owner_id) REFERENCES owner (owner_id)
);
INSERT INTO "vehicle" VALUES('VEH-001','VF5PLUS2024000001','MDL-01','OWN-001','Xanh dương','2024-03-15','30A-12345');
INSERT INTO "vehicle" VALUES('VEH-002','VF8ECO20230000001','MDL-05','OWN-001','Đen','2023-06-10','30A-67890');
INSERT INTO "vehicle" VALUES('VEH-003','VF6ECO20240000001','MDL-02','OWN-002','Trắng','2024-01-20','51A-11111');
INSERT INTO "vehicle" VALUES('VEH-004','VF7ECO20230000001','MDL-04','OWN-003','Đỏ','2023-09-05','43A-22222');
INSERT INTO "vehicle" VALUES('VEH-005','VF9PLUS2023000001','MDL-07','OWN-003','Bạc','2023-11-01','43A-33333');
INSERT INTO "vehicle" VALUES('VEH-006','VF6PLUS2024000001','MDL-03','OWN-004','Xám','2024-05-12','29A-44444');
INSERT INTO "vehicle" VALUES('VEH-007','VF8PLUS2023000001','MDL-06','OWN-005','Trắng ngọc trai','2023-04-01','51A-55555');
INSERT INTO "vehicle" VALUES('VEH-008','VF8ECO20239606110','MDL-05','OWN-006','Vàng','2023-08-04','30K-74343');
INSERT INTO "vehicle" VALUES('VEH-009','VF6PLUS2024584529','MDL-03','OWN-006','Đỏ','2024-02-15','30K-48288');
INSERT INTO "vehicle" VALUES('VEH-010','VF8ECO20238238128','MDL-05','OWN-006','Đỏ','2023-11-04','30G-78767');
INSERT INTO "vehicle" VALUES('VEH-011','VF8ECO20235161129','MDL-05','OWN-007','Trắng ngọc trai','2023-07-25','29K-94785');
INSERT INTO "vehicle" VALUES('VEH-012','VF6PLUS2024961346','MDL-03','OWN-007','Trắng ngọc trai','2024-08-22','29B-67468');
INSERT INTO "vehicle" VALUES('VEH-013','VF8ECO20233335171','MDL-05','OWN-008','Trắng','2023-02-12','29D-25835');
INSERT INTO "vehicle" VALUES('VEH-014','VF6PLUS2024432054','MDL-03','OWN-008','Trắng ngọc trai','2024-09-16','29G-29468');
INSERT INTO "vehicle" VALUES('VEH-015','VF5PLUS2024499147','MDL-01','OWN-008','Đỏ','2024-09-18','29F-99495');
INSERT INTO "vehicle" VALUES('VEH-016','VF8PLUS2023047434','MDL-06','OWN-009','Vàng','2023-03-30','51K-16316');
INSERT INTO "vehicle" VALUES('VEH-017','VF7ECO20235465836','MDL-04','OWN-010','Vàng','2023-04-01','51K-73183');
INSERT INTO "vehicle" VALUES('VEH-018','VF8PLUS2023830265','MDL-06','OWN-010','Đen','2023-10-21','51K-38382');
INSERT INTO "vehicle" VALUES('VEH-019','VF8ECO20234882776','MDL-05','OWN-011','Đỏ','2023-02-02','30F-31153');
INSERT INTO "vehicle" VALUES('VEH-020','VF5PLUS2024719141','MDL-01','OWN-011','Xanh dương','2024-02-18','30K-85560');
INSERT INTO "vehicle" VALUES('VEH-021','VF5PLUS2024729075','MDL-01','OWN-012','Đen','2024-05-24','51F-47952');
INSERT INTO "vehicle" VALUES('VEH-022','VF5PLUS2024649037','MDL-01','OWN-012','Trắng','2024-03-24','51B-25503');
INSERT INTO "vehicle" VALUES('VEH-023','VF6PLUS2024239343','MDL-03','OWN-013','Đỏ','2024-03-16','15A-12175');
INSERT INTO "vehicle" VALUES('VEH-024','VF5PLUS2024881487','MDL-01','OWN-013','Bạc','2024-12-02','15A-92294');
INSERT INTO "vehicle" VALUES('VEH-025','VF7ECO20237953451','MDL-04','OWN-014','Xám','2023-10-08','92E-34628');
INSERT INTO "vehicle" VALUES('VEH-026','VF6PLUS2024766517','MDL-03','OWN-014','Đen','2024-10-06','92E-28082');
INSERT INTO "vehicle" VALUES('VEH-027','VF8PLUS2023533475','MDL-06','OWN-014','Xám','2023-03-22','92B-21211');
INSERT INTO "vehicle" VALUES('VEH-028','VF6ECO20241957858','MDL-02','OWN-015','Trắng','2024-01-15','92K-97517');
CREATE TABLE vehicle_model (
	model_id VARCHAR NOT NULL, 
	model_name VARCHAR NOT NULL, 
	trim VARCHAR NOT NULL, 
	battery_capacity_kwh FLOAT NOT NULL, 
	motor_power_kw FLOAT NOT NULL, 
	production_year INTEGER NOT NULL, 
	PRIMARY KEY (model_id)
);
INSERT INTO "vehicle_model" VALUES('MDL-01','VF5','Plus',37.2,134.0,2024);
INSERT INTO "vehicle_model" VALUES('MDL-02','VF6','Eco',59.6,150.0,2024);
INSERT INTO "vehicle_model" VALUES('MDL-03','VF6','Plus',59.6,150.0,2024);
INSERT INTO "vehicle_model" VALUES('MDL-04','VF7','Eco',75.3,174.0,2023);
INSERT INTO "vehicle_model" VALUES('MDL-05','VF8','Eco',87.7,300.0,2023);
INSERT INTO "vehicle_model" VALUES('MDL-06','VF8','Plus',87.7,300.0,2023);
INSERT INTO "vehicle_model" VALUES('MDL-07','VF9','Plus',123.0,300.0,2023);
CREATE TABLE vehicle_usage (
	vehicle_id VARCHAR NOT NULL, 
	current_km INTEGER NOT NULL, 
	battery_soh FLOAT NOT NULL, 
	data_source VARCHAR(10) NOT NULL, 
	last_updated_at DATETIME NOT NULL, 
	PRIMARY KEY (vehicle_id), 
	FOREIGN KEY(vehicle_id) REFERENCES vehicle (vehicle_id)
);
INSERT INTO "vehicle_usage" VALUES('VEH-001',42510,96.2,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-002',55810,93.1,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-003',38210,97.5,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-004',48010,94.8,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-005',44610,95.3,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-006',30110,98.0,'manual','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-007',58310,91.7,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-008',50370,97.0,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-009',51220,96.9,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-010',54935,95.2,'manual','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-011',63291,93.7,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-012',34261,96.8,'manual','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-013',76179,92.2,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-014',31071,97.1,'manual','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-015',39442,97.2,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-016',52954,94.6,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-017',48943,94.5,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-018',48923,95.2,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-019',59328,96.2,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-020',44947,95.0,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-021',39738,95.5,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-022',35476,96.0,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-023',53110,96.0,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-024',36072,98.0,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-025',55872,96.5,'manual','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-026',24433,96.9,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-027',64896,95.1,'telematics','2026-10-01 05:35:11.021848');
INSERT INTO "vehicle_usage" VALUES('VEH-028',49192,97.1,'telematics','2026-10-01 05:35:11.021848');
CREATE TABLE warranty (
	warranty_id VARCHAR NOT NULL, 
	vehicle_id VARCHAR NOT NULL, 
	policy_id VARCHAR NOT NULL, 
	start_date DATE NOT NULL, 
	end_date DATE NOT NULL, 
	km_limit INTEGER NOT NULL, 
	status VARCHAR(7) NOT NULL, 
	PRIMARY KEY (warranty_id), 
	FOREIGN KEY(vehicle_id) REFERENCES vehicle (vehicle_id), 
	FOREIGN KEY(policy_id) REFERENCES warranty_policy (policy_id)
);
INSERT INTO "warranty" VALUES('WRT-001','VEH-001','WP-001','2024-03-15','2032-03-15',160000,'active');
INSERT INTO "warranty" VALUES('WRT-002','VEH-001','WP-002','2024-03-15','2029-03-15',120000,'active');
INSERT INTO "warranty" VALUES('WRT-003','VEH-001','WP-003','2024-03-15','2027-03-15',100000,'active');
INSERT INTO "warranty" VALUES('WRT-004','VEH-001','WP-004','2024-03-15','2027-03-15',100000,'active');
INSERT INTO "warranty" VALUES('WRT-005','VEH-002','WP-017','2023-06-10','2031-06-10',160000,'active');
INSERT INTO "warranty" VALUES('WRT-006','VEH-002','WP-018','2023-06-10','2028-06-10',120000,'active');
INSERT INTO "warranty" VALUES('WRT-007','VEH-002','WP-019','2023-06-10','2026-06-10',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-008','VEH-002','WP-020','2023-06-10','2026-06-10',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-009','VEH-003','WP-005','2024-01-20','2032-01-20',160000,'active');
INSERT INTO "warranty" VALUES('WRT-010','VEH-003','WP-006','2024-01-20','2029-01-20',120000,'active');
INSERT INTO "warranty" VALUES('WRT-011','VEH-003','WP-007','2024-01-20','2027-01-20',100000,'active');
INSERT INTO "warranty" VALUES('WRT-012','VEH-003','WP-008','2024-01-20','2027-01-20',100000,'active');
INSERT INTO "warranty" VALUES('WRT-013','VEH-004','WP-013','2023-09-05','2031-09-05',160000,'active');
INSERT INTO "warranty" VALUES('WRT-014','VEH-004','WP-014','2023-09-05','2028-09-05',120000,'active');
INSERT INTO "warranty" VALUES('WRT-015','VEH-004','WP-015','2023-09-05','2026-09-05',100000,'active');
INSERT INTO "warranty" VALUES('WRT-016','VEH-004','WP-016','2023-09-05','2026-09-05',100000,'active');
INSERT INTO "warranty" VALUES('WRT-017','VEH-005','WP-025','2023-11-01','2031-11-01',160000,'active');
INSERT INTO "warranty" VALUES('WRT-018','VEH-005','WP-026','2023-11-01','2028-11-01',120000,'active');
INSERT INTO "warranty" VALUES('WRT-019','VEH-005','WP-027','2023-11-01','2026-11-01',100000,'active');
INSERT INTO "warranty" VALUES('WRT-020','VEH-005','WP-028','2023-11-01','2026-11-01',100000,'active');
INSERT INTO "warranty" VALUES('WRT-021','VEH-006','WP-009','2024-05-12','2032-05-12',160000,'active');
INSERT INTO "warranty" VALUES('WRT-022','VEH-006','WP-010','2024-05-12','2029-05-12',120000,'active');
INSERT INTO "warranty" VALUES('WRT-023','VEH-006','WP-011','2024-05-12','2027-05-12',100000,'active');
INSERT INTO "warranty" VALUES('WRT-024','VEH-006','WP-012','2024-05-12','2027-05-12',100000,'active');
INSERT INTO "warranty" VALUES('WRT-025','VEH-007','WP-021','2023-04-01','2031-04-01',160000,'active');
INSERT INTO "warranty" VALUES('WRT-026','VEH-007','WP-022','2023-04-01','2028-04-01',120000,'active');
INSERT INTO "warranty" VALUES('WRT-027','VEH-007','WP-023','2023-04-01','2026-04-01',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-028','VEH-007','WP-024','2023-04-01','2026-04-01',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-029','VEH-008','WP-017','2023-08-04','2031-08-04',160000,'active');
INSERT INTO "warranty" VALUES('WRT-030','VEH-008','WP-018','2023-08-04','2028-08-04',120000,'active');
INSERT INTO "warranty" VALUES('WRT-031','VEH-008','WP-019','2023-08-04','2026-08-04',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-032','VEH-008','WP-020','2023-08-04','2026-08-04',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-033','VEH-009','WP-009','2024-02-15','2032-02-15',160000,'active');
INSERT INTO "warranty" VALUES('WRT-034','VEH-009','WP-010','2024-02-15','2029-02-15',120000,'active');
INSERT INTO "warranty" VALUES('WRT-035','VEH-009','WP-011','2024-02-15','2027-02-15',100000,'active');
INSERT INTO "warranty" VALUES('WRT-036','VEH-009','WP-012','2024-02-15','2027-02-15',100000,'active');
INSERT INTO "warranty" VALUES('WRT-037','VEH-010','WP-017','2023-11-04','2031-11-04',160000,'active');
INSERT INTO "warranty" VALUES('WRT-038','VEH-010','WP-018','2023-11-04','2028-11-04',120000,'active');
INSERT INTO "warranty" VALUES('WRT-039','VEH-010','WP-019','2023-11-04','2026-11-04',100000,'active');
INSERT INTO "warranty" VALUES('WRT-040','VEH-010','WP-020','2023-11-04','2026-11-04',100000,'active');
INSERT INTO "warranty" VALUES('WRT-041','VEH-011','WP-017','2023-07-25','2031-07-25',160000,'active');
INSERT INTO "warranty" VALUES('WRT-042','VEH-011','WP-018','2023-07-25','2028-07-25',120000,'active');
INSERT INTO "warranty" VALUES('WRT-043','VEH-011','WP-019','2023-07-25','2026-07-25',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-044','VEH-011','WP-020','2023-07-25','2026-07-25',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-045','VEH-012','WP-009','2024-08-22','2032-08-22',160000,'active');
INSERT INTO "warranty" VALUES('WRT-046','VEH-012','WP-010','2024-08-22','2029-08-22',120000,'active');
INSERT INTO "warranty" VALUES('WRT-047','VEH-012','WP-011','2024-08-22','2027-08-22',100000,'active');
INSERT INTO "warranty" VALUES('WRT-048','VEH-012','WP-012','2024-08-22','2027-08-22',100000,'active');
INSERT INTO "warranty" VALUES('WRT-049','VEH-013','WP-017','2023-02-12','2031-02-12',160000,'active');
INSERT INTO "warranty" VALUES('WRT-050','VEH-013','WP-018','2023-02-12','2028-02-12',120000,'active');
INSERT INTO "warranty" VALUES('WRT-051','VEH-013','WP-019','2023-02-12','2026-02-12',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-052','VEH-013','WP-020','2023-02-12','2026-02-12',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-053','VEH-014','WP-009','2024-09-16','2032-09-16',160000,'active');
INSERT INTO "warranty" VALUES('WRT-054','VEH-014','WP-010','2024-09-16','2029-09-16',120000,'active');
INSERT INTO "warranty" VALUES('WRT-055','VEH-014','WP-011','2024-09-16','2027-09-16',100000,'active');
INSERT INTO "warranty" VALUES('WRT-056','VEH-014','WP-012','2024-09-16','2027-09-16',100000,'active');
INSERT INTO "warranty" VALUES('WRT-057','VEH-015','WP-001','2024-09-18','2032-09-18',160000,'active');
INSERT INTO "warranty" VALUES('WRT-058','VEH-015','WP-002','2024-09-18','2029-09-18',120000,'active');
INSERT INTO "warranty" VALUES('WRT-059','VEH-015','WP-003','2024-09-18','2027-09-18',100000,'active');
INSERT INTO "warranty" VALUES('WRT-060','VEH-015','WP-004','2024-09-18','2027-09-18',100000,'active');
INSERT INTO "warranty" VALUES('WRT-061','VEH-016','WP-021','2023-03-30','2031-03-30',160000,'active');
INSERT INTO "warranty" VALUES('WRT-062','VEH-016','WP-022','2023-03-30','2028-03-30',120000,'active');
INSERT INTO "warranty" VALUES('WRT-063','VEH-016','WP-023','2023-03-30','2026-03-30',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-064','VEH-016','WP-024','2023-03-30','2026-03-30',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-065','VEH-017','WP-013','2023-04-01','2031-04-01',160000,'active');
INSERT INTO "warranty" VALUES('WRT-066','VEH-017','WP-014','2023-04-01','2028-04-01',120000,'active');
INSERT INTO "warranty" VALUES('WRT-067','VEH-017','WP-015','2023-04-01','2026-04-01',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-068','VEH-017','WP-016','2023-04-01','2026-04-01',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-069','VEH-018','WP-021','2023-10-21','2031-10-21',160000,'active');
INSERT INTO "warranty" VALUES('WRT-070','VEH-018','WP-022','2023-10-21','2028-10-21',120000,'active');
INSERT INTO "warranty" VALUES('WRT-071','VEH-018','WP-023','2023-10-21','2026-10-21',100000,'active');
INSERT INTO "warranty" VALUES('WRT-072','VEH-018','WP-024','2023-10-21','2026-10-21',100000,'active');
INSERT INTO "warranty" VALUES('WRT-073','VEH-019','WP-017','2023-02-02','2031-02-02',160000,'active');
INSERT INTO "warranty" VALUES('WRT-074','VEH-019','WP-018','2023-02-02','2028-02-02',120000,'active');
INSERT INTO "warranty" VALUES('WRT-075','VEH-019','WP-019','2023-02-02','2026-02-02',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-076','VEH-019','WP-020','2023-02-02','2026-02-02',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-077','VEH-020','WP-001','2024-02-18','2032-02-18',160000,'active');
INSERT INTO "warranty" VALUES('WRT-078','VEH-020','WP-002','2024-02-18','2029-02-18',120000,'active');
INSERT INTO "warranty" VALUES('WRT-079','VEH-020','WP-003','2024-02-18','2027-02-18',100000,'active');
INSERT INTO "warranty" VALUES('WRT-080','VEH-020','WP-004','2024-02-18','2027-02-18',100000,'active');
INSERT INTO "warranty" VALUES('WRT-081','VEH-021','WP-001','2024-05-24','2032-05-24',160000,'active');
INSERT INTO "warranty" VALUES('WRT-082','VEH-021','WP-002','2024-05-24','2029-05-24',120000,'active');
INSERT INTO "warranty" VALUES('WRT-083','VEH-021','WP-003','2024-05-24','2027-05-24',100000,'active');
INSERT INTO "warranty" VALUES('WRT-084','VEH-021','WP-004','2024-05-24','2027-05-24',100000,'active');
INSERT INTO "warranty" VALUES('WRT-085','VEH-022','WP-001','2024-03-24','2032-03-24',160000,'active');
INSERT INTO "warranty" VALUES('WRT-086','VEH-022','WP-002','2024-03-24','2029-03-24',120000,'active');
INSERT INTO "warranty" VALUES('WRT-087','VEH-022','WP-003','2024-03-24','2027-03-24',100000,'active');
INSERT INTO "warranty" VALUES('WRT-088','VEH-022','WP-004','2024-03-24','2027-03-24',100000,'active');
INSERT INTO "warranty" VALUES('WRT-089','VEH-023','WP-009','2024-03-16','2032-03-16',160000,'active');
INSERT INTO "warranty" VALUES('WRT-090','VEH-023','WP-010','2024-03-16','2029-03-16',120000,'active');
INSERT INTO "warranty" VALUES('WRT-091','VEH-023','WP-011','2024-03-16','2027-03-16',100000,'active');
INSERT INTO "warranty" VALUES('WRT-092','VEH-023','WP-012','2024-03-16','2027-03-16',100000,'active');
INSERT INTO "warranty" VALUES('WRT-093','VEH-024','WP-001','2024-12-02','2032-12-02',160000,'active');
INSERT INTO "warranty" VALUES('WRT-094','VEH-024','WP-002','2024-12-02','2029-12-02',120000,'active');
INSERT INTO "warranty" VALUES('WRT-095','VEH-024','WP-003','2024-12-02','2027-12-02',100000,'active');
INSERT INTO "warranty" VALUES('WRT-096','VEH-024','WP-004','2024-12-02','2027-12-02',100000,'active');
INSERT INTO "warranty" VALUES('WRT-097','VEH-025','WP-013','2023-10-08','2031-10-08',160000,'active');
INSERT INTO "warranty" VALUES('WRT-098','VEH-025','WP-014','2023-10-08','2028-10-08',120000,'active');
INSERT INTO "warranty" VALUES('WRT-099','VEH-025','WP-015','2023-10-08','2026-10-08',100000,'active');
INSERT INTO "warranty" VALUES('WRT-100','VEH-025','WP-016','2023-10-08','2026-10-08',100000,'active');
INSERT INTO "warranty" VALUES('WRT-101','VEH-026','WP-009','2024-10-06','2032-10-06',160000,'active');
INSERT INTO "warranty" VALUES('WRT-102','VEH-026','WP-010','2024-10-06','2029-10-06',120000,'active');
INSERT INTO "warranty" VALUES('WRT-103','VEH-026','WP-011','2024-10-06','2027-10-06',100000,'active');
INSERT INTO "warranty" VALUES('WRT-104','VEH-026','WP-012','2024-10-06','2027-10-06',100000,'active');
INSERT INTO "warranty" VALUES('WRT-105','VEH-027','WP-021','2023-03-22','2031-03-22',160000,'active');
INSERT INTO "warranty" VALUES('WRT-106','VEH-027','WP-022','2023-03-22','2028-03-22',120000,'active');
INSERT INTO "warranty" VALUES('WRT-107','VEH-027','WP-023','2023-03-22','2026-03-22',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-108','VEH-027','WP-024','2023-03-22','2026-03-22',100000,'expired');
INSERT INTO "warranty" VALUES('WRT-109','VEH-028','WP-005','2024-01-15','2032-01-15',160000,'active');
INSERT INTO "warranty" VALUES('WRT-110','VEH-028','WP-006','2024-01-15','2029-01-15',120000,'active');
INSERT INTO "warranty" VALUES('WRT-111','VEH-028','WP-007','2024-01-15','2027-01-15',100000,'active');
INSERT INTO "warranty" VALUES('WRT-112','VEH-028','WP-008','2024-01-15','2027-01-15',100000,'active');
CREATE TABLE warranty_claim (
	claim_id VARCHAR NOT NULL, 
	vehicle_id VARCHAR NOT NULL, 
	warranty_id VARCHAR NOT NULL, 
	claim_date DATE NOT NULL, 
	status VARCHAR(8) NOT NULL, 
	reject_reason VARCHAR, 
	PRIMARY KEY (claim_id), 
	FOREIGN KEY(vehicle_id) REFERENCES vehicle (vehicle_id), 
	FOREIGN KEY(warranty_id) REFERENCES warranty (warranty_id)
);
INSERT INTO "warranty_claim" VALUES('CLM-001','VEH-002','WRT-005','2026-07-15','rejected','Pin giảm dung lượng 6.9% — chưa đạt ngưỡng bảo hành (>30% trong 8 năm đầu). Mức giảm nằm trong phạm vi hao mòn tự nhiên.');
INSERT INTO "warranty_claim" VALUES('CLM-002','VEH-007','WRT-027','2026-02-10','approved',NULL);
INSERT INTO "warranty_claim" VALUES('CLM-003','VEH-004','WRT-016','2026-10-20','rejected','Hợp đồng bảo hành hệ thống điện tử đã hết hạn ngày 2026-09-05 (3 năm kể từ ngày sản xuất). Yêu cầu ngoài thời hạn bảo hành.');
INSERT INTO "warranty_claim" VALUES('CLM-004','VEH-001','WRT-002','2026-09-20','pending',NULL);
INSERT INTO "warranty_claim" VALUES('CLM-005','VEH-008','WRT-029','2026-03-11','approved',NULL);
INSERT INTO "warranty_claim" VALUES('CLM-006','VEH-011','WRT-043','2023-09-11','approved',NULL);
INSERT INTO "warranty_claim" VALUES('CLM-007','VEH-016','WRT-062','2026-03-22','pending',NULL);
INSERT INTO "warranty_claim" VALUES('CLM-008','VEH-017','WRT-065','2024-07-12','approved',NULL);
INSERT INTO "warranty_claim" VALUES('CLM-009','VEH-018','WRT-071','2025-05-22','rejected','Xe đã được can thiệp, sửa chữa tại cơ sở không chính hãng.');
INSERT INTO "warranty_claim" VALUES('CLM-010','VEH-027','WRT-106','2024-03-18','pending',NULL);
CREATE TABLE warranty_policy (
	policy_id VARCHAR NOT NULL, 
	model_id VARCHAR NOT NULL, 
	component VARCHAR(11) NOT NULL, 
	duration_months INTEGER NOT NULL, 
	km_limit INTEGER NOT NULL, 
	terms_description VARCHAR NOT NULL, 
	PRIMARY KEY (policy_id), 
	FOREIGN KEY(model_id) REFERENCES vehicle_model (model_id)
);
INSERT INTO "warranty_policy" VALUES('WP-001','MDL-01','battery',96,160000,'Pin lithium-ion: bảo hành 8 năm hoặc 160.000km (tùy điều kiện nào đến trước). Không áp dụng nếu pin bị hư do va đập, ngập nước, hoặc tự ý can thiệp.');
INSERT INTO "warranty_policy" VALUES('WP-002','MDL-01','motor',60,120000,'Động cơ điện: bảo hành 5 năm hoặc 120.000km. Không bao gồm hao mòn tự nhiên của bạc đạn.');
INSERT INTO "warranty_policy" VALUES('WP-003','MDL-01','chassis',36,100000,'Khung gầm: bảo hành 3 năm hoặc 100.000km. Không áp dụng cho hư hỏng do tai nạn.');
INSERT INTO "warranty_policy" VALUES('WP-004','MDL-01','electronics',36,100000,'Hệ thống điện tử (màn hình, ADAS, ECU): bảo hành 3 năm hoặc 100.000km.');
INSERT INTO "warranty_policy" VALUES('WP-005','MDL-02','battery',96,160000,'Pin lithium-ion: bảo hành 8 năm hoặc 160.000km (tùy điều kiện nào đến trước). Không áp dụng nếu pin bị hư do va đập, ngập nước, hoặc tự ý can thiệp.');
INSERT INTO "warranty_policy" VALUES('WP-006','MDL-02','motor',60,120000,'Động cơ điện: bảo hành 5 năm hoặc 120.000km. Không bao gồm hao mòn tự nhiên của bạc đạn.');
INSERT INTO "warranty_policy" VALUES('WP-007','MDL-02','chassis',36,100000,'Khung gầm: bảo hành 3 năm hoặc 100.000km. Không áp dụng cho hư hỏng do tai nạn.');
INSERT INTO "warranty_policy" VALUES('WP-008','MDL-02','electronics',36,100000,'Hệ thống điện tử (màn hình, ADAS, ECU): bảo hành 3 năm hoặc 100.000km.');
INSERT INTO "warranty_policy" VALUES('WP-009','MDL-03','battery',96,160000,'Pin lithium-ion: bảo hành 8 năm hoặc 160.000km (tùy điều kiện nào đến trước). Không áp dụng nếu pin bị hư do va đập, ngập nước, hoặc tự ý can thiệp.');
INSERT INTO "warranty_policy" VALUES('WP-010','MDL-03','motor',60,120000,'Động cơ điện: bảo hành 5 năm hoặc 120.000km. Không bao gồm hao mòn tự nhiên của bạc đạn.');
INSERT INTO "warranty_policy" VALUES('WP-011','MDL-03','chassis',36,100000,'Khung gầm: bảo hành 3 năm hoặc 100.000km. Không áp dụng cho hư hỏng do tai nạn.');
INSERT INTO "warranty_policy" VALUES('WP-012','MDL-03','electronics',36,100000,'Hệ thống điện tử (màn hình, ADAS, ECU): bảo hành 3 năm hoặc 100.000km.');
INSERT INTO "warranty_policy" VALUES('WP-013','MDL-04','battery',96,160000,'Pin lithium-ion: bảo hành 8 năm hoặc 160.000km (tùy điều kiện nào đến trước). Không áp dụng nếu pin bị hư do va đập, ngập nước, hoặc tự ý can thiệp.');
INSERT INTO "warranty_policy" VALUES('WP-014','MDL-04','motor',60,120000,'Động cơ điện: bảo hành 5 năm hoặc 120.000km. Không bao gồm hao mòn tự nhiên của bạc đạn.');
INSERT INTO "warranty_policy" VALUES('WP-015','MDL-04','chassis',36,100000,'Khung gầm: bảo hành 3 năm hoặc 100.000km. Không áp dụng cho hư hỏng do tai nạn.');
INSERT INTO "warranty_policy" VALUES('WP-016','MDL-04','electronics',36,100000,'Hệ thống điện tử (màn hình, ADAS, ECU): bảo hành 3 năm hoặc 100.000km.');
INSERT INTO "warranty_policy" VALUES('WP-017','MDL-05','battery',96,160000,'Pin lithium-ion: bảo hành 8 năm hoặc 160.000km (tùy điều kiện nào đến trước). Không áp dụng nếu pin bị hư do va đập, ngập nước, hoặc tự ý can thiệp.');
INSERT INTO "warranty_policy" VALUES('WP-018','MDL-05','motor',60,120000,'Động cơ điện: bảo hành 5 năm hoặc 120.000km. Không bao gồm hao mòn tự nhiên của bạc đạn.');
INSERT INTO "warranty_policy" VALUES('WP-019','MDL-05','chassis',36,100000,'Khung gầm: bảo hành 3 năm hoặc 100.000km. Không áp dụng cho hư hỏng do tai nạn.');
INSERT INTO "warranty_policy" VALUES('WP-020','MDL-05','electronics',36,100000,'Hệ thống điện tử (màn hình, ADAS, ECU): bảo hành 3 năm hoặc 100.000km.');
INSERT INTO "warranty_policy" VALUES('WP-021','MDL-06','battery',96,160000,'Pin lithium-ion: bảo hành 8 năm hoặc 160.000km (tùy điều kiện nào đến trước). Không áp dụng nếu pin bị hư do va đập, ngập nước, hoặc tự ý can thiệp.');
INSERT INTO "warranty_policy" VALUES('WP-022','MDL-06','motor',60,120000,'Động cơ điện: bảo hành 5 năm hoặc 120.000km. Không bao gồm hao mòn tự nhiên của bạc đạn.');
INSERT INTO "warranty_policy" VALUES('WP-023','MDL-06','chassis',36,100000,'Khung gầm: bảo hành 3 năm hoặc 100.000km. Không áp dụng cho hư hỏng do tai nạn.');
INSERT INTO "warranty_policy" VALUES('WP-024','MDL-06','electronics',36,100000,'Hệ thống điện tử (màn hình, ADAS, ECU): bảo hành 3 năm hoặc 100.000km.');
INSERT INTO "warranty_policy" VALUES('WP-025','MDL-07','battery',96,160000,'Pin lithium-ion: bảo hành 8 năm hoặc 160.000km (tùy điều kiện nào đến trước). Không áp dụng nếu pin bị hư do va đập, ngập nước, hoặc tự ý can thiệp.');
INSERT INTO "warranty_policy" VALUES('WP-026','MDL-07','motor',60,120000,'Động cơ điện: bảo hành 5 năm hoặc 120.000km. Không bao gồm hao mòn tự nhiên của bạc đạn.');
INSERT INTO "warranty_policy" VALUES('WP-027','MDL-07','chassis',36,100000,'Khung gầm: bảo hành 3 năm hoặc 100.000km. Không áp dụng cho hư hỏng do tai nạn.');
INSERT INTO "warranty_policy" VALUES('WP-028','MDL-07','electronics',36,100000,'Hệ thống điện tử (màn hình, ADAS, ECU): bảo hành 3 năm hoặc 100.000km.');
CREATE UNIQUE INDEX ix_service_center_manager_email ON service_center (manager_email);
CREATE UNIQUE INDEX ix_vehicle_license_plate ON vehicle (license_plate);
CREATE UNIQUE INDEX ix_vehicle_vin ON vehicle (vin);
COMMIT;
