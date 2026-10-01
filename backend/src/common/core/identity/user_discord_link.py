"""ENT-417 - UserDiscordLink: the Discord account and private channel of a vehicle owner.

Columns follow ``docs/specs/entity/identity/user_discord_link.entity.md``. The
OAuth2 / bot flow that fills this table is not implemented yet; reminder
notifications only read it to find the recipient (FEAT-NOTI-001 BR-507).
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class DiscordLinkStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class UserDiscordLink(SQLModel, table=True):
    __tablename__ = "user_discord_link"
    __table_args__ = (
        CheckConstraint("discord_user_id ~ '^[0-9]{5,32}$'", name="ck_discord_link_user_id"),
        CheckConstraint(
            "discord_channel_id IS NULL OR discord_channel_id ~ '^[0-9]{5,32}$'",
            name="ck_discord_link_channel_id",
        ),
        CheckConstraint(
            "status <> 'active' OR (discord_channel_id IS NOT NULL AND linked_at IS NOT NULL)",
            name="ck_discord_link_active_needs_channel",
        ),
        Index(
            "ux_user_discord_link_discord_user_active",
            "discord_user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    user_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("vehicle_user.user_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    discord_user_id: str = Field(sa_column=Column(String(32), nullable=False))
    discord_username: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    discord_channel_id: str | None = Field(
        default=None, sa_column=Column(String(32), unique=True, nullable=True)
    )
    status: DiscordLinkStatus = Field(
        default=DiscordLinkStatus.PENDING,
        sa_column=Column(
            SQLEnum(
                DiscordLinkStatus, name="discord_link_status_enum", values_callable=_enum_values
            ),
            nullable=False,
            server_default="pending",
        ),
    )
    revoked_reason: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    linked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    last_delivered_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class UserDiscordLinkRepository(SQLModelRepository[UserDiscordLink, int]):
    model = UserDiscordLink
