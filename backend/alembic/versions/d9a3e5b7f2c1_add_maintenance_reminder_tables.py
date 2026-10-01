"""add maintenance reminder + notification settings tables (FEAT-NOTI-001, us-021)

Creates ENT-417 ``user_discord_link``, ENT-418 ``user_notification_setting``,
ENT-419 ``user_notification_channel`` and ENT-420 ``reminder_delivery``; adds
``zalo`` to ``reminder_channel_enum`` and the unique key of ``reminder``
(one reminder per vehicle, milestone and level).

Revision ID: d9a3e5b7f2c1
Revises: c8f2d4a6e1b9
Create Date: 2026-09-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9a3e5b7f2c1"
down_revision: str | Sequence[str] | None = "c8f2d4a6e1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False: each type is created once in upgrade(), not per column.
discord_link_status = postgresql.ENUM(
    "pending", "active", "revoked", name="discord_link_status_enum", create_type=False
)
delivery_status = postgresql.ENUM(
    "pending",
    "sent",
    "failed",
    "no_recipient",
    name="notification_delivery_status_enum",
    create_type=False,
)
reminder_channel = postgresql.ENUM(name="reminder_channel_enum", create_type=False)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    # A value added by ALTER TYPE cannot be used in the same transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE reminder_channel_enum ADD VALUE IF NOT EXISTS 'zalo'")

    discord_link_status.create(op.get_bind(), checkfirst=True)
    delivery_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "user_discord_link",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("vehicle_user.user_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("discord_user_id", sa.String(32), nullable=False),
        sa.Column("discord_username", sa.String(64), nullable=True),
        sa.Column("discord_channel_id", sa.String(32), nullable=True, unique=True),
        sa.Column("status", discord_link_status, server_default="pending", nullable=False),
        sa.Column("revoked_reason", sa.String(64), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_delivered_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("discord_user_id ~ '^[0-9]{5,32}$'", name="ck_discord_link_user_id"),
        sa.CheckConstraint(
            "discord_channel_id IS NULL OR discord_channel_id ~ '^[0-9]{5,32}$'",
            name="ck_discord_link_channel_id",
        ),
        sa.CheckConstraint(
            "status <> 'active' OR (discord_channel_id IS NOT NULL AND linked_at IS NOT NULL)",
            name="ck_discord_link_active_needs_channel",
        ),
    )
    op.create_index(
        "ux_user_discord_link_discord_user_active",
        "user_discord_link",
        ["discord_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "user_notification_setting",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("vehicle_user.user_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("reminders_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("reminder_lead_days", sa.SmallInteger(), server_default="2", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("reminder_lead_days BETWEEN 0 AND 30", name="ck_notification_lead_days"),
    )

    op.create_table(
        "user_notification_channel",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("vehicle_user.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", reminder_channel, nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "channel", name="ux_notification_channel_user_channel"),
    )

    # Clear duplicates first so the unique key can be created (no writer exists yet).
    op.execute(
        "DELETE FROM reminder r USING reminder d "
        "WHERE r.user_vehicle_id = d.user_vehicle_id "
        "AND r.target_odo_milestone = d.target_odo_milestone "
        "AND r.reminder_level = d.reminder_level AND r.id > d.id"
    )
    op.create_unique_constraint(
        "ux_reminder_vehicle_milestone_level",
        "reminder",
        ["user_vehicle_id", "target_odo_milestone", "reminder_level"],
    )

    op.create_table(
        "reminder_delivery",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "reminder_id",
            sa.Uuid(),
            sa.ForeignKey("reminder.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", reminder_channel, nullable=False),
        sa.Column("status", delivery_status, server_default="pending", nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("reminder_id", "channel", name="ux_reminder_delivery_reminder_channel"),
        sa.CheckConstraint("attempts >= 0", name="ck_reminder_delivery_attempts"),
        sa.CheckConstraint("status <> 'sent' OR sent_at IS NOT NULL", name="ck_reminder_delivery_sent_at"),
    )
    op.create_index(
        "ix_reminder_delivery_retry",
        "reminder_delivery",
        ["status", "attempts"],
        postgresql_where=sa.text("status = 'failed'"),
    )


def downgrade() -> None:
    op.drop_index("ix_reminder_delivery_retry", table_name="reminder_delivery")
    op.drop_table("reminder_delivery")
    op.drop_constraint("ux_reminder_vehicle_milestone_level", "reminder", type_="unique")
    op.drop_table("user_notification_channel")
    op.drop_table("user_notification_setting")
    op.drop_index("ux_user_discord_link_discord_user_active", table_name="user_discord_link")
    op.drop_table("user_discord_link")
    delivery_status.drop(op.get_bind(), checkfirst=True)
    discord_link_status.drop(op.get_bind(), checkfirst=True)
    # 'zalo' stays in reminder_channel_enum: PostgreSQL cannot drop enum values.
