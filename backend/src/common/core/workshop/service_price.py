"""ENT-409 — ServicePrice: the price of one service item at one workshop for one model.

Columns follow ``docs/specs/entity/workshop/service_price.entity.md``. Prices are
matched to standard items by (``model_id``, ``item_code``) and take priority over
``maintenance_rule.estimated_cost`` when quoting (BR-ENT-411). Validity periods of
the same (workshop, model, item) must not overlap (BR-ENT-412, enforced in service).
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class ServicePrice(SQLModel, table=True):
    __tablename__ = "service_price"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_service_price_price"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_service_price_validity",
        ),
        Index("ix_service_price_workshop_model_item", "workshop_id", "model_id", "item_code"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workshop_id: UUID = Field(
        sa_column=Column(ForeignKey("workshop.id", ondelete="CASCADE"), nullable=False)
    )
    model_id: str = Field(sa_column=Column(String(64), nullable=False))
    item_code: str = Field(sa_column=Column(String(50), nullable=False))
    item_name: str = Field(sa_column=Column(String(200), nullable=False))
    price: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    # NULL bounds mean "open-ended" on that side.
    valid_from: date | None = Field(default=None, sa_column=Column(Date, nullable=True))
    valid_to: date | None = Field(default=None, sa_column=Column(Date, nullable=True))

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class ServicePriceRepository(SQLModelRepository[ServicePrice, UUID]):
    model = ServicePrice
