"""SQLModel table models cho mock EV system.

Map 1-1 với proposed_erd.md (docs/specs/entity/proposed_erd.md).
SQLite in-memory — mỗi lần restart là fresh data.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, Relationship, SQLModel


# ── Enums ────────────────────────────────────────────────────────────


class DataSource(str, Enum):
    telematics = "telematics"
    manual = "manual"


class WarrantyComponent(str, Enum):
    battery = "battery"
    motor = "motor"
    chassis = "chassis"
    electronics = "electronics"


class WarrantyStatus(str, Enum):
    active = "active"
    expired = "expired"


class ClaimStatus(str, Enum):
    approved = "approved"
    rejected = "rejected"
    pending = "pending"


class CenterType(str, Enum):
    dealer = "dealer"
    service_only = "service_only"


# ── Master data ──────────────────────────────────────────────────────


class VehicleModel(SQLModel, table=True):
    """Mẫu xe: VF3, VF5, VF6, VF7, VF8, VF9."""

    __tablename__ = "vehicle_model"

    model_id: str = Field(primary_key=True)
    model_name: str
    trim: str
    battery_capacity_kwh: float
    motor_power_kw: float
    production_year: int

    # relationships
    vehicles: list["Vehicle"] = Relationship(back_populates="model")
    warranty_policies: list["WarrantyPolicy"] = Relationship(
        back_populates="model"
    )
    maintenance_schedules: list["MaintenanceSchedule"] = Relationship(
        back_populates="model"
    )


class Owner(SQLModel, table=True):
    """Chủ sở hữu xe."""

    __tablename__ = "owner"

    owner_id: str = Field(primary_key=True)
    full_name: str
    phone: str
    email: str
    national_id: str

    vehicles: list["Vehicle"] = Relationship(back_populates="owner")


class ServiceCenter(SQLModel, table=True):
    """Đại lý / xưởng dịch vụ chính hãng."""

    __tablename__ = "service_center"

    center_id: str = Field(primary_key=True)
    name: str
    region: str
    type: CenterType
    # Người quản lý xưởng đã đăng ký với hãng — dùng để xác thực chủ xưởng
    # trên EV Care. Một email quản lý chỉ gắn với đúng một xưởng.
    manager_email: str = Field(index=True, unique=True)
    manager_national_id: str

    service_histories: list["ServiceHistory"] = Relationship(
        back_populates="service_center"
    )


# ── Transactional data ───────────────────────────────────────────────


class Vehicle(SQLModel, table=True):
    """Một chiếc xe cụ thể (theo VIN)."""

    __tablename__ = "vehicle"

    vehicle_id: str = Field(primary_key=True)
    vin: str = Field(index=True, unique=True)
    model_id: str = Field(foreign_key="vehicle_model.model_id")
    current_owner_id: str = Field(foreign_key="owner.owner_id")
    color: str
    manufacture_date: date
    license_plate: str = Field(index=True, unique=True)

    model: Optional[VehicleModel] = Relationship(back_populates="vehicles")
    owner: Optional[Owner] = Relationship(back_populates="vehicles")
    usage: Optional["VehicleUsage"] = Relationship(back_populates="vehicle")
    warranties: list["Warranty"] = Relationship(back_populates="vehicle")
    service_histories: list["ServiceHistory"] = Relationship(
        back_populates="vehicle"
    )
    warranty_claims: list["WarrantyClaim"] = Relationship(
        back_populates="vehicle"
    )


class VehicleUsage(SQLModel, table=True):
    """Snapshot sử dụng hiện tại — 1 xe : 1 bản ghi."""

    __tablename__ = "vehicle_usage"

    vehicle_id: str = Field(
        primary_key=True, foreign_key="vehicle.vehicle_id"
    )
    current_km: int
    battery_soh: float  # 0-100 %
    data_source: DataSource = DataSource.telematics
    last_updated_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime, nullable=False)
    )

    vehicle: Optional[Vehicle] = Relationship(back_populates="usage")


# ── Warranty ─────────────────────────────────────────────────────────


class WarrantyPolicy(SQLModel, table=True):
    """Quy tắc bảo hành gốc — theo model + component."""

    __tablename__ = "warranty_policy"

    policy_id: str = Field(primary_key=True)
    model_id: str = Field(foreign_key="vehicle_model.model_id")
    component: WarrantyComponent
    duration_months: int
    km_limit: int
    terms_description: str

    model: Optional[VehicleModel] = Relationship(
        back_populates="warranty_policies"
    )
    warranties: list["Warranty"] = Relationship(back_populates="policy")


class Warranty(SQLModel, table=True):
    """Instance bảo hành áp cho 1 xe."""

    __tablename__ = "warranty"

    warranty_id: str = Field(primary_key=True)
    vehicle_id: str = Field(foreign_key="vehicle.vehicle_id")
    policy_id: str = Field(foreign_key="warranty_policy.policy_id")
    start_date: date
    end_date: date
    km_limit: int
    status: WarrantyStatus

    vehicle: Optional[Vehicle] = Relationship(back_populates="warranties")
    policy: Optional[WarrantyPolicy] = Relationship(
        back_populates="warranties"
    )
    claims: list["WarrantyClaim"] = Relationship(back_populates="warranty")


class WarrantyClaim(SQLModel, table=True):
    """Yêu cầu bảo hành — pain point 'vì sao bị từ chối'."""

    __tablename__ = "warranty_claim"

    claim_id: str = Field(primary_key=True)
    vehicle_id: str = Field(foreign_key="vehicle.vehicle_id")
    warranty_id: str = Field(foreign_key="warranty.warranty_id")
    claim_date: date
    status: ClaimStatus
    reject_reason: Optional[str] = None

    vehicle: Optional[Vehicle] = Relationship(
        back_populates="warranty_claims"
    )
    warranty: Optional[Warranty] = Relationship(back_populates="claims")


# ── Maintenance ──────────────────────────────────────────────────────


class MaintenanceSchedule(SQLModel, table=True):
    """Lịch bảo dưỡng chuẩn của hãng — theo model."""

    __tablename__ = "maintenance_schedule"

    schedule_id: str = Field(primary_key=True)
    model_id: str = Field(foreign_key="vehicle_model.model_id")
    milestone_km: int
    milestone_months: int
    description: str

    model: Optional[VehicleModel] = Relationship(
        back_populates="maintenance_schedules"
    )
    items: list["MaintenanceItem"] = Relationship(back_populates="schedule")


class MaintenanceItem(SQLModel, table=True):
    """Hạng mục trong 1 mốc bảo dưỡng."""

    __tablename__ = "maintenance_item"

    item_id: str = Field(primary_key=True)
    schedule_id: str = Field(
        foreign_key="maintenance_schedule.schedule_id"
    )
    item_name: str
    is_covered_by_warranty: bool = False
    reference_price: Decimal = Field(default=Decimal("0"), decimal_places=0)

    schedule: Optional[MaintenanceSchedule] = Relationship(
        back_populates="items"
    )


class ServiceHistory(SQLModel, table=True):
    """Lịch sử bảo dưỡng thực tế tại xưởng."""

    __tablename__ = "service_history"

    order_id: str = Field(primary_key=True)
    vehicle_id: str = Field(foreign_key="vehicle.vehicle_id")
    service_center_id: str = Field(
        foreign_key="service_center.center_id"
    )
    service_date: date
    km_at_service: int
    items_done: str  # JSON text ở MVP
    is_periodic: bool = Field(default=True)  # False = sửa chữa ngoài định kỳ
    total_cost: Decimal = Field(default=Decimal("0"), decimal_places=0)

    vehicle: Optional[Vehicle] = Relationship(
        back_populates="service_histories"
    )
    service_center: Optional[ServiceCenter] = Relationship(
        back_populates="service_histories"
    )
