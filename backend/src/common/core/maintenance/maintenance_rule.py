"""ENT-401 — MaintenanceRule: standard maintenance items and cost per model / milestone.

Columns follow ``docs/specs/entity/maintenance/maintenance_rule.entity.md``.
``model_id`` is the manufacturer's ``VehicleModel`` code (BR-003). Each row is
one item at one milestone; ``item_code`` identifies the item across milestones
and is the key used to match ``service_price`` (BR-ENT-425).
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class MaintenanceRule(SQLModel, table=True):
    __tablename__ = "maintenance_rule"
    __table_args__ = (
        CheckConstraint("odo_milestone > 0", name="ck_maintenance_rule_odo_milestone"),
        CheckConstraint("month_milestone > 0", name="ck_maintenance_rule_month_milestone"),
        CheckConstraint("estimated_cost >= 0", name="ck_maintenance_rule_estimated_cost"),
        CheckConstraint(
            "estimated_duration_minutes > 0", name="ck_maintenance_rule_estimated_duration"
        ),
        CheckConstraint(
            "item_code ~ '^[A-Z0-9_]{2,50}$'", name="ck_maintenance_rule_item_code_format"
        ),
        UniqueConstraint(
            "model_id",
            "odo_milestone",
            "item_name",
            name="ux_maintenance_rule_model_milestone_item",
        ),
        UniqueConstraint(
            "model_id",
            "odo_milestone",
            "item_code",
            name="ux_maintenance_rule_model_milestone_code",
        ),
        Index("ix_maintenance_rule_model_item_code", "model_id", "item_code"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    model_id: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    odo_milestone: int = Field(sa_column=Column(Integer, nullable=False))
    month_milestone: int = Field(sa_column=Column(Integer, nullable=False))
    item_code: str = Field(sa_column=Column(String(50), nullable=False))
    item_name: str = Field(sa_column=Column(String(200), nullable=False))
    is_covered_by_warranty: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default="false")
    )
    estimated_cost: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    estimated_duration_minutes: int = Field(sa_column=Column(Integer, nullable=False))

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class MaintenanceRuleRepository(SQLModelRepository[MaintenanceRule, UUID]):
    model = MaintenanceRule
