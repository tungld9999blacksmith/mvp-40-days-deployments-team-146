"""Seed data deterministic cho mock EV system.

Dữ liệu cố định, lặp lại được giữa các lần chạy — phục vụ test ổn định.
Quy ước id: <entity-prefix>-<number> (vd: MDL-01, VEH-001, OWN-001).
"""

import os
from datetime import date, datetime
from decimal import Decimal

from sqlmodel import Session

from .models import (
    ClaimStatus,
    CenterType,
    DataSource,
    MaintenanceItem,
    MaintenanceSchedule,
    Owner,
    ServiceCenter,
    ServiceHistory,
    Vehicle,
    VehicleModel,
    VehicleUsage,
    Warranty,
    WarrantyClaim,
    WarrantyComponent,
    WarrantyPolicy,
    WarrantyStatus,
)


def seed_all(session: Session) -> None:
    """Nạp toàn bộ seed data theo thứ tự FK."""
    _seed_vehicle_models(session)
    _seed_owners(session)
    _seed_service_centers(session)
    _seed_vehicles(session)
    _seed_vehicle_usage(session)
    _seed_warranty_policies(session)
    _seed_warranties(session)
    _seed_warranty_claims(session)
    _seed_maintenance_schedules(session)
    _seed_maintenance_items(session)
    _seed_service_history(session)
    session.commit()


# ── Vehicle Models (5 models × 1-2 trims) ───────────────────────────


def _seed_vehicle_models(session: Session) -> None:
    models = [
        VehicleModel(
            model_id="MDL-01", model_name="VF5", trim="Plus",
            battery_capacity_kwh=37.2, motor_power_kw=134,
            production_year=2024,
        ),
        VehicleModel(
            model_id="MDL-02", model_name="VF6", trim="Eco",
            battery_capacity_kwh=59.6, motor_power_kw=150,
            production_year=2024,
        ),
        VehicleModel(
            model_id="MDL-03", model_name="VF6", trim="Plus",
            battery_capacity_kwh=59.6, motor_power_kw=150,
            production_year=2024,
        ),
        VehicleModel(
            model_id="MDL-04", model_name="VF7", trim="Eco",
            battery_capacity_kwh=75.3, motor_power_kw=174,
            production_year=2023,
        ),
        VehicleModel(
            model_id="MDL-05", model_name="VF8", trim="Eco",
            battery_capacity_kwh=87.7, motor_power_kw=300,
            production_year=2023,
        ),
        VehicleModel(
            model_id="MDL-06", model_name="VF8", trim="Plus",
            battery_capacity_kwh=87.7, motor_power_kw=300,
            production_year=2023,
        ),
        VehicleModel(
            model_id="MDL-07", model_name="VF9", trim="Plus",
            battery_capacity_kwh=123.0, motor_power_kw=300,
            production_year=2023,
        ),
    ]
    session.add_all(models)


# ── Owners ───────────────────────────────────────────────────────────


def _owner_email(owner_id: str, default: str) -> str:
    """Email chủ xe; override bằng env ``MOCK_<ID>_EMAIL`` (vd. ``MOCK_OWN001_EMAIL``).

    Dùng để đăng nhập Google thật ở app chủ xe và xác thực xe của chủ đó.
    """
    env_key = f"MOCK_{owner_id.replace('-', '')}_EMAIL"
    return (os.getenv(env_key) or default).strip().lower()


def _seed_owners(session: Session) -> None:
    owners = [
        Owner(
            owner_id="OWN-001", full_name="Nguyễn Văn An",
            phone="0901000001", email=_owner_email("OWN-001", "an.nguyen@example.com"),
            national_id="079200001001",
        ),
        Owner(
            owner_id="OWN-002", full_name="Trần Thị Bình",
            phone="0901000002", email=_owner_email("OWN-002", "binh.tran@example.com"),
            national_id="079200001002",
        ),
        Owner(
            owner_id="OWN-003", full_name="Lê Hoàng Cường",
            phone="0901000003", email=_owner_email("OWN-003", "cuong.le@example.com"),
            national_id="079200001003",
        ),
        Owner(
            owner_id="OWN-004", full_name="Phạm Minh Dũng",
            phone="0901000004", email=_owner_email("OWN-004", "dung.pham@example.com"),
            national_id="079200001004",
        ),
        Owner(
            owner_id="OWN-005", full_name="Hoàng Thị Em",
            phone="0901000005", email=_owner_email("OWN-005", "em.hoang@example.com"),
            national_id="079200001005",
        ),
    ]
    session.add_all(owners)


# ── Service Centers ──────────────────────────────────────────────────


def _manager_email(center_id: str, default: str) -> str:
    """Email quản lý xưởng; override bằng env ``MOCK_<ID>_MANAGER_EMAIL``.

    Ví dụ ``MOCK_SC01_MANAGER_EMAIL=you@gmail.com`` để đăng nhập Google thật
    trên Workshop Portal với vai trò quản lý SC-01.
    """
    env_key = f"MOCK_{center_id.replace('-', '')}_MANAGER_EMAIL"
    return (os.getenv(env_key) or default).strip().lower()


def _seed_service_centers(session: Session) -> None:
    centers = [
        ServiceCenter(
            center_id="SC-01", name="VinFast Thăng Long",
            region="Hà Nội", type=CenterType.dealer,
            manager_email=_manager_email("SC-01", "ha.tran.sc01@example.com"),
            manager_national_id="001190000101",
        ),
        ServiceCenter(
            center_id="SC-02", name="VinFast Quận 7",
            region="TP. Hồ Chí Minh", type=CenterType.dealer,
            manager_email=_manager_email("SC-02", "khoa.nguyen.sc02@example.com"),
            manager_national_id="079190000202",
        ),
        ServiceCenter(
            center_id="SC-03", name="VinFast Đà Nẵng",
            region="Đà Nẵng", type=CenterType.service_only,
            manager_email=_manager_email("SC-03", "lan.vo.sc03@example.com"),
            manager_national_id="048190000303",
        ),
    ]
    session.add_all(centers)


# ── Vehicles (7 xe, owner 1-2 chiếc) ────────────────────────────────


def _seed_vehicles(session: Session) -> None:
    vehicles = [
        # OWN-001: 2 xe
        Vehicle(
            vehicle_id="VEH-001", vin="VF5PLUS2024000001",
            model_id="MDL-01", current_owner_id="OWN-001",
            color="Xanh dương", manufacture_date=date(2024, 3, 15),
            license_plate="30A-12345",
        ),
        Vehicle(
            vehicle_id="VEH-002", vin="VF8ECO20230000001",
            model_id="MDL-05", current_owner_id="OWN-001",
            color="Đen", manufacture_date=date(2023, 6, 10),
            license_plate="30A-67890",
        ),
        # OWN-002: 1 xe
        Vehicle(
            vehicle_id="VEH-003", vin="VF6ECO20240000001",
            model_id="MDL-02", current_owner_id="OWN-002",
            color="Trắng", manufacture_date=date(2024, 1, 20),
            license_plate="51A-11111",
        ),
        # OWN-003: 2 xe
        Vehicle(
            vehicle_id="VEH-004", vin="VF7ECO20230000001",
            model_id="MDL-04", current_owner_id="OWN-003",
            color="Đỏ", manufacture_date=date(2023, 9, 5),
            license_plate="43A-22222",
        ),
        Vehicle(
            vehicle_id="VEH-005", vin="VF9PLUS2023000001",
            model_id="MDL-07", current_owner_id="OWN-003",
            color="Bạc", manufacture_date=date(2023, 11, 1),
            license_plate="43A-33333",
        ),
        # OWN-004: 1 xe
        Vehicle(
            vehicle_id="VEH-006", vin="VF6PLUS2024000001",
            model_id="MDL-03", current_owner_id="OWN-004",
            color="Xám", manufacture_date=date(2024, 5, 12),
            license_plate="29A-44444",
        ),
        # OWN-005: 1 xe
        Vehicle(
            vehicle_id="VEH-007", vin="VF8PLUS2023000001",
            model_id="MDL-06", current_owner_id="OWN-005",
            color="Trắng ngọc trai", manufacture_date=date(2023, 4, 1),
            license_plate="51A-55555",
        ),
    ]
    session.add_all(vehicles)


# ── Vehicle Usage (snapshot) ─────────────────────────────────────────


def _seed_vehicle_usage(session: Session) -> None:
    # km tương quan tuổi xe (~17.000 km/năm)
    now = datetime(2026, 9, 1, 8, 0, 0)
    usages = [
        VehicleUsage(
            vehicle_id="VEH-001", current_km=42_500,
            battery_soh=96.2, data_source=DataSource.telematics,
            last_updated_at=now,
        ),
        VehicleUsage(
            vehicle_id="VEH-002", current_km=55_800,
            battery_soh=93.1, data_source=DataSource.telematics,
            last_updated_at=now,
        ),
        VehicleUsage(
            vehicle_id="VEH-003", current_km=38_200,
            battery_soh=97.5, data_source=DataSource.telematics,
            last_updated_at=now,
        ),
        VehicleUsage(
            vehicle_id="VEH-004", current_km=48_000,
            battery_soh=94.8, data_source=DataSource.telematics,
            last_updated_at=now,
        ),
        VehicleUsage(
            vehicle_id="VEH-005", current_km=44_600,
            battery_soh=95.3, data_source=DataSource.telematics,
            last_updated_at=now,
        ),
        VehicleUsage(
            vehicle_id="VEH-006", current_km=30_100,
            battery_soh=98.0, data_source=DataSource.manual,
            last_updated_at=now,
        ),
        VehicleUsage(
            vehicle_id="VEH-007", current_km=58_300,
            battery_soh=91.7, data_source=DataSource.telematics,
            last_updated_at=now,
        ),
    ]
    session.add_all(usages)


# ── Warranty Policies (mỗi model 4 component) ───────────────────────


def _seed_warranty_policies(session: Session) -> None:
    policies: list[WarrantyPolicy] = []
    counter = 0

    # Chuẩn bảo hành VinFast-like
    component_rules: list[tuple[WarrantyComponent, int, int, str]] = [
        (WarrantyComponent.battery, 96, 160_000,
         "Pin lithium-ion: bảo hành 8 năm hoặc 160.000km (tùy điều kiện nào đến trước). "
         "Không áp dụng nếu pin bị hư do va đập, ngập nước, hoặc tự ý can thiệp."),
        (WarrantyComponent.motor, 60, 120_000,
         "Động cơ điện: bảo hành 5 năm hoặc 120.000km. "
         "Không bao gồm hao mòn tự nhiên của bạc đạn."),
        (WarrantyComponent.chassis, 36, 100_000,
         "Khung gầm: bảo hành 3 năm hoặc 100.000km. "
         "Không áp dụng cho hư hỏng do tai nạn."),
        (WarrantyComponent.electronics, 36, 100_000,
         "Hệ thống điện tử (màn hình, ADAS, ECU): bảo hành 3 năm hoặc 100.000km."),
    ]

    model_ids = [
        "MDL-01", "MDL-02", "MDL-03", "MDL-04",
        "MDL-05", "MDL-06", "MDL-07",
    ]

    for model_id in model_ids:
        for comp, months, km, desc in component_rules:
            counter += 1
            policies.append(WarrantyPolicy(
                policy_id=f"WP-{counter:03d}",
                model_id=model_id,
                component=comp,
                duration_months=months,
                km_limit=km,
                terms_description=desc,
            ))

    session.add_all(policies)


# ── Warranty instances (mỗi xe 4 hợp đồng) ─────────────────────────


def _seed_warranties(session: Session) -> None:
    from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]

    # Map vehicle → (model, manufacture_date)
    vehicle_info: list[tuple[str, str, date]] = [
        ("VEH-001", "MDL-01", date(2024, 3, 15)),
        ("VEH-002", "MDL-05", date(2023, 6, 10)),
        ("VEH-003", "MDL-02", date(2024, 1, 20)),
        ("VEH-004", "MDL-04", date(2023, 9, 5)),
        ("VEH-005", "MDL-07", date(2023, 11, 1)),
        ("VEH-006", "MDL-03", date(2024, 5, 12)),
        ("VEH-007", "MDL-06", date(2023, 4, 1)),
    ]

    component_specs = [
        (WarrantyComponent.battery, 96, 160_000),
        (WarrantyComponent.motor, 60, 120_000),
        (WarrantyComponent.chassis, 36, 100_000),
        (WarrantyComponent.electronics, 36, 100_000),
    ]

    warranties: list[Warranty] = []
    counter = 0
    today = date(2026, 9, 1)

    for veh_id, model_id, mfg_date in vehicle_info:
        # Tìm policy_id offset dựa trên model
        model_idx = int(model_id.split("-")[1])  # 01..07
        policy_base = (model_idx - 1) * 4  # 0,4,8,12,...

        for i, (comp, months, km) in enumerate(component_specs):
            counter += 1
            end = mfg_date + relativedelta(months=months)
            status = (
                WarrantyStatus.active if end > today
                else WarrantyStatus.expired
            )
            warranties.append(Warranty(
                warranty_id=f"WRT-{counter:03d}",
                vehicle_id=veh_id,
                policy_id=f"WP-{policy_base + i + 1:03d}",
                start_date=mfg_date,
                end_date=end,
                km_limit=km,
                status=status,
            ))

    session.add_all(warranties)


# ── Warranty Claims (một số approved, một số rejected) ───────────────


def _seed_warranty_claims(session: Session) -> None:
    claims = [
        # VEH-002 (VF8 Eco, xe cũ nhất) — claim pin bị rejected vì ngoài điều kiện
        WarrantyClaim(
            claim_id="CLM-001", vehicle_id="VEH-002",
            warranty_id="WRT-005",  # battery warranty VEH-002
            claim_date=date(2026, 7, 15),
            status=ClaimStatus.rejected,
            reject_reason=(
                "Pin giảm dung lượng 6.9% — chưa đạt ngưỡng bảo hành (>30% "
                "trong 8 năm đầu). Mức giảm nằm trong phạm vi hao mòn tự nhiên."
            ),
        ),
        # VEH-007 (VF8 Plus, 58k km) — claim khung gầm approved
        WarrantyClaim(
            claim_id="CLM-002", vehicle_id="VEH-007",
            warranty_id="WRT-027",  # chassis warranty VEH-007
            claim_date=date(2026, 2, 10),
            status=ClaimStatus.approved,
            reject_reason=None,
        ),
        # VEH-004 (VF7 Eco) — claim electronics rejected (quá hạn)
        WarrantyClaim(
            claim_id="CLM-003", vehicle_id="VEH-004",
            warranty_id="WRT-016",  # electronics warranty VEH-004
            claim_date=date(2026, 10, 20),
            status=ClaimStatus.rejected,
            reject_reason=(
                "Hợp đồng bảo hành hệ thống điện tử đã hết hạn ngày 2026-09-05 "
                "(3 năm kể từ ngày sản xuất). Yêu cầu ngoài thời hạn bảo hành."
            ),
        ),
        # VEH-001 (VF5 Plus) — claim pending
        WarrantyClaim(
            claim_id="CLM-004", vehicle_id="VEH-001",
            warranty_id="WRT-002",  # motor warranty VEH-001
            claim_date=date(2026, 9, 20),
            status=ClaimStatus.pending,
            reject_reason=None,
        ),
    ]
    session.add_all(claims)


# ── Maintenance Schedules (chuẩn hãng theo model) ───────────────────


def _seed_maintenance_schedules(session: Session) -> None:
    # Áp dụng chung cho tất cả model (EV maintenance khá giống nhau)
    milestones: list[tuple[int, int, str]] = [
        (10_000, 6, "Bảo dưỡng định kỳ 10.000km / 6 tháng"),
        (20_000, 12, "Bảo dưỡng định kỳ 20.000km / 12 tháng"),
        (40_000, 24, "Bảo dưỡng lớn 40.000km / 24 tháng"),
        (60_000, 36, "Bảo dưỡng lớn 60.000km / 36 tháng"),
        (80_000, 48, "Bảo dưỡng toàn diện 80.000km / 48 tháng"),
    ]

    model_ids = [
        "MDL-01", "MDL-02", "MDL-03", "MDL-04",
        "MDL-05", "MDL-06", "MDL-07",
    ]

    schedules: list[MaintenanceSchedule] = []
    counter = 0

    for model_id in model_ids:
        for km, months, desc in milestones:
            counter += 1
            schedules.append(MaintenanceSchedule(
                schedule_id=f"MS-{counter:03d}",
                model_id=model_id,
                milestone_km=km,
                milestone_months=months,
                description=desc,
            ))

    session.add_all(schedules)


# ── Maintenance Items ────────────────────────────────────────────────


def _seed_maintenance_items(session: Session) -> None:
    # Items cho mốc 10k (MS-001 cho MDL-01, pattern lặp)
    # Chỉ seed items cho model MDL-01 (VF5) làm mẫu, các model khác tương tự
    items: list[MaintenanceItem] = []
    counter = 0

    # Mốc 10k (MS-001)
    items_10k: list[tuple[str, bool, int]] = [
        ("Kiểm tra & bổ sung dung dịch làm mát", True, 200_000),
        ("Kiểm tra hệ thống phanh", True, 0),
        ("Kiểm tra lốp & áp suất", False, 150_000),
        ("Kiểm tra hệ thống treo", True, 0),
    ]
    for name, warranty, price in items_10k:
        counter += 1
        items.append(MaintenanceItem(
            item_id=f"MI-{counter:03d}",
            schedule_id="MS-001",
            item_name=name,
            is_covered_by_warranty=warranty,
            reference_price=Decimal(price),
        ))

    # Mốc 20k (MS-002)
    items_20k: list[tuple[str, bool, int]] = [
        ("Thay lọc gió điều hòa", False, 350_000),
        ("Kiểm tra & bổ sung dung dịch làm mát", True, 200_000),
        ("Kiểm tra hệ thống phanh", True, 0),
        ("Kiểm tra bình ắc-quy 12V", True, 0),
        ("Kiểm tra hệ thống sạc", True, 0),
    ]
    for name, warranty, price in items_20k:
        counter += 1
        items.append(MaintenanceItem(
            item_id=f"MI-{counter:03d}",
            schedule_id="MS-002",
            item_name=name,
            is_covered_by_warranty=warranty,
            reference_price=Decimal(price),
        ))

    # Mốc 40k (MS-003)
    items_40k: list[tuple[str, bool, int]] = [
        ("Thay lọc gió điều hòa", False, 350_000),
        ("Thay dung dịch làm mát", False, 800_000),
        ("Thay dung dịch phanh", False, 450_000),
        ("Kiểm tra má phanh", True, 0),
        ("Kiểm tra hệ thống treo & gầm", True, 0),
        ("Cân bằng & đảo lốp", False, 300_000),
    ]
    for name, warranty, price in items_40k:
        counter += 1
        items.append(MaintenanceItem(
            item_id=f"MI-{counter:03d}",
            schedule_id="MS-003",
            item_name=name,
            is_covered_by_warranty=warranty,
            reference_price=Decimal(price),
        ))

    # Mốc 60k (MS-004)
    items_60k: list[tuple[str, bool, int]] = [
        ("Thay lọc gió điều hòa", False, 350_000),
        ("Thay dung dịch phanh", False, 450_000),
        ("Thay má phanh trước", False, 1_500_000),
        ("Kiểm tra pin cao áp & hệ thống BMS", True, 0),
        ("Kiểm tra motor & hộp giảm tốc", True, 0),
    ]
    for name, warranty, price in items_60k:
        counter += 1
        items.append(MaintenanceItem(
            item_id=f"MI-{counter:03d}",
            schedule_id="MS-004",
            item_name=name,
            is_covered_by_warranty=warranty,
            reference_price=Decimal(price),
        ))

    # Mốc 80k (MS-005)
    items_80k: list[tuple[str, bool, int]] = [
        ("Thay lọc gió điều hòa", False, 350_000),
        ("Thay dung dịch làm mát", False, 800_000),
        ("Thay dung dịch phanh", False, 450_000),
        ("Thay má phanh sau", False, 1_200_000),
        ("Thay lốp (bộ 4)", False, 12_000_000),
        ("Kiểm tra toàn diện hệ thống điện cao áp", True, 0),
        ("Cân chỉnh hệ thống ADAS", True, 0),
    ]
    for name, warranty, price in items_80k:
        counter += 1
        items.append(MaintenanceItem(
            item_id=f"MI-{counter:03d}",
            schedule_id="MS-005",
            item_name=name,
            is_covered_by_warranty=warranty,
            reference_price=Decimal(price),
        ))

    session.add_all(items)


# ── Service History ──────────────────────────────────────────────────


def _seed_service_history(session: Session) -> None:
    history = [
        # VEH-001 (VF5, 42.5k km) — đã làm mốc 10k, 20k, 40k
        ServiceHistory(
            order_id="SH-001", vehicle_id="VEH-001",
            service_center_id="SC-01",
            service_date=date(2024, 9, 20), km_at_service=10_200,
            items_done="Kiểm tra dung dịch làm mát, kiểm tra phanh, kiểm tra lốp",
            total_cost=Decimal(150_000),
        ),
        ServiceHistory(
            order_id="SH-002", vehicle_id="VEH-001",
            service_center_id="SC-01",
            service_date=date(2025, 3, 15), km_at_service=20_500,
            items_done="Thay lọc gió điều hòa, kiểm tra phanh, kiểm tra ắc-quy 12V",
            total_cost=Decimal(350_000),
        ),
        ServiceHistory(
            order_id="SH-003", vehicle_id="VEH-001",
            service_center_id="SC-01",
            service_date=date(2026, 2, 10), km_at_service=38_100,
            items_done="Thay lọc gió, thay dung dịch làm mát, thay dung dịch phanh, đảo lốp",
            total_cost=Decimal(1_900_000),
        ),
        # VEH-002 (VF8, 55.8k km) — đã làm mốc 10k, 20k, 40k
        ServiceHistory(
            order_id="SH-004", vehicle_id="VEH-002",
            service_center_id="SC-01",
            service_date=date(2023, 12, 5), km_at_service=9_800,
            items_done="Kiểm tra dung dịch làm mát, kiểm tra phanh",
            total_cost=Decimal(0),
        ),
        ServiceHistory(
            order_id="SH-005", vehicle_id="VEH-002",
            service_center_id="SC-02",
            service_date=date(2024, 7, 20), km_at_service=21_000,
            items_done="Thay lọc gió điều hòa, kiểm tra ắc-quy",
            total_cost=Decimal(350_000),
        ),
        ServiceHistory(
            order_id="SH-006", vehicle_id="VEH-002",
            service_center_id="SC-01",
            service_date=date(2025, 6, 10), km_at_service=41_500,
            items_done="Thay dung dịch làm mát, thay dung dịch phanh, cân bằng lốp",
            total_cost=Decimal(1_550_000),
        ),
        # VEH-003 (VF6, 38.2k km) — đã làm mốc 10k, 20k
        ServiceHistory(
            order_id="SH-007", vehicle_id="VEH-003",
            service_center_id="SC-02",
            service_date=date(2024, 8, 1), km_at_service=10_500,
            items_done="Kiểm tra phanh, kiểm tra lốp & áp suất",
            total_cost=Decimal(150_000),
        ),
        ServiceHistory(
            order_id="SH-008", vehicle_id="VEH-003",
            service_center_id="SC-02",
            service_date=date(2025, 3, 20), km_at_service=22_000,
            items_done="Thay lọc gió điều hòa, kiểm tra hệ thống sạc",
            total_cost=Decimal(350_000),
        ),
        # VEH-004 (VF7, 48k km) — đã làm mốc 10k, 20k, 40k
        ServiceHistory(
            order_id="SH-009", vehicle_id="VEH-004",
            service_center_id="SC-03",
            service_date=date(2024, 3, 10), km_at_service=10_100,
            items_done="Kiểm tra dung dịch, kiểm tra phanh",
            total_cost=Decimal(0),
        ),
        ServiceHistory(
            order_id="SH-010", vehicle_id="VEH-004",
            service_center_id="SC-03",
            service_date=date(2024, 10, 15), km_at_service=20_800,
            items_done="Thay lọc gió điều hòa, kiểm tra ắc-quy, kiểm tra sạc",
            total_cost=Decimal(350_000),
        ),
        ServiceHistory(
            order_id="SH-011", vehicle_id="VEH-004",
            service_center_id="SC-03",
            service_date=date(2025, 12, 1), km_at_service=42_000,
            items_done="Thay dung dịch làm mát, thay dung dịch phanh, đảo lốp",
            total_cost=Decimal(1_550_000),
        ),
        # VEH-005 (VF9, 44.6k km) — đã làm mốc 10k, 20k, 40k
        ServiceHistory(
            order_id="SH-012", vehicle_id="VEH-005",
            service_center_id="SC-01",
            service_date=date(2024, 5, 20), km_at_service=10_300,
            items_done="Kiểm tra phanh, kiểm tra hệ thống treo",
            total_cost=Decimal(0),
        ),
        ServiceHistory(
            order_id="SH-013", vehicle_id="VEH-005",
            service_center_id="SC-01",
            service_date=date(2025, 1, 10), km_at_service=21_200,
            items_done="Thay lọc gió điều hòa",
            total_cost=Decimal(350_000),
        ),
        ServiceHistory(
            order_id="SH-014", vehicle_id="VEH-005",
            service_center_id="SC-01",
            service_date=date(2026, 1, 20), km_at_service=40_500,
            items_done="Thay dung dịch làm mát, thay dung dịch phanh, cân bằng đảo lốp",
            total_cost=Decimal(1_900_000),
        ),
        # VEH-006 (VF6 Plus, 30.1k km) — đã làm mốc 10k, 20k
        ServiceHistory(
            order_id="SH-015", vehicle_id="VEH-006",
            service_center_id="SC-01",
            service_date=date(2024, 11, 20), km_at_service=10_000,
            items_done="Kiểm tra dung dịch, phanh, lốp",
            total_cost=Decimal(150_000),
        ),
        ServiceHistory(
            order_id="SH-016", vehicle_id="VEH-006",
            service_center_id="SC-02",
            service_date=date(2025, 7, 5), km_at_service=20_200,
            items_done="Thay lọc gió điều hòa, kiểm tra ắc-quy 12V",
            total_cost=Decimal(350_000),
        ),
        # VEH-007 (VF8 Plus, 58.3k km) — xe cũ nhất, đã làm mốc 10k,20k,40k
        ServiceHistory(
            order_id="SH-017", vehicle_id="VEH-007",
            service_center_id="SC-02",
            service_date=date(2023, 10, 15), km_at_service=10_400,
            items_done="Kiểm tra dung dịch, phanh, lốp",
            total_cost=Decimal(0),
        ),
        ServiceHistory(
            order_id="SH-018", vehicle_id="VEH-007",
            service_center_id="SC-02",
            service_date=date(2024, 5, 10), km_at_service=20_900,
            items_done="Thay lọc gió điều hòa, kiểm tra ắc-quy, kiểm tra sạc",
            total_cost=Decimal(350_000),
        ),
        ServiceHistory(
            order_id="SH-019", vehicle_id="VEH-007",
            service_center_id="SC-02",
            service_date=date(2025, 3, 1), km_at_service=41_800,
            items_done="Thay dung dịch làm mát, thay dung dịch phanh, đảo lốp, kiểm tra má phanh",
            total_cost=Decimal(1_550_000),
        ),
    ]
    session.add_all(history)
