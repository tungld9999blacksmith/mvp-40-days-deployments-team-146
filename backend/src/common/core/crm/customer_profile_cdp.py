"""ENT-404 — CustomerProfileCDP: per-user context collected from chat sessions for AI personalisation.

Columns follow ``docs/specs/entity/crm/customer_profile_cdp.entity.md``.
One row per ``vehicle_user`` (``user_id`` is both PK and FK).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class CustomerProfileCDP(SQLModel, table=True):
    __tablename__ = "customer_profile_cdp"

    user_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("vehicle_user.user_id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    interaction_history: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    preferences: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    last_active_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    is_cold_start: bool = Field(
        default=True, sa_column=Column(Boolean, nullable=False, server_default="true")
    )

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class CustomerProfileCDPRepository(SQLModelRepository[CustomerProfileCDP, int]):
    model = CustomerProfileCDP
