from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Enum as SQLEnum, String
from sqlmodel import Field, SQLModel


class RoleCode(str, Enum):
    VEHICLE_USER = "vehicle_user"
    WORKSHOP_OWNER = "workshop_owner"
    MAINTENANCE_STAFF = "maintenance_staff"


class Role(SQLModel, table=True):
    __tablename__ = "roles"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    code: RoleCode = Field(
        sa_column=Column(
            SQLEnum(RoleCode, name="role_code_enum"),
            unique=True,
            nullable=False,
            index=True,
        )
    )

    name: str = Field(
        sa_column=Column(String(100), nullable=False)
    )

    description: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )

    is_system: bool = Field(default=True)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )