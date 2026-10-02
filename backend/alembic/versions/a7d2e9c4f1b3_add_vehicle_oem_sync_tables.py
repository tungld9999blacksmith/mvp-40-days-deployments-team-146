"""add vehicle OEM sync tables (FEAT-VEH-001, us-017 entity spec v1.1)

Creates ENT-414 ``vehicle_odometer_reading``, ENT-415 ``vehicle_service_record``
and ENT-416 ``vehicle_oem_sync``: odometer and service history synced from the
manufacturer (periodic poll + webhook), plus the per-vehicle sync state.

Revision ID: a7d2e9c4f1b3
Revises: f6c3a8d1b2e4
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d2e9c4f1b3"
down_revision: str | Sequence[str] | None = "f6c3a8d1b2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False: each type is created once in upgrade(), not per column.
oem_usage_source = postgresql.ENUM("telematics", "manual", name="oem_usage_source_enum", create_type=False)
oem_sync_trigger = postgresql.ENUM("poll", "webhook", "initial", name="oem_sync_trigger_enum", create_type=False)
service_record_source = postgresql.ENUM("oem", "ev_care", name="service_record_source_enum", create_type=False)
ENUMS = (oem_usage_source, oem_sync_trigger, service_record_source)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "vehicle_odometer_reading",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_vehicle_id",
            sa.Uuid(),
            sa.ForeignKey("user_vehicle.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("odo_km", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("oem_data_source", oem_usage_source, nullable=False),
        sa.Column("received_via", oem_sync_trigger, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("odo_km BETWEEN 0 AND 999999", name="ck_odometer_odo_km"),
        sa.UniqueConstraint("user_vehicle_id", "recorded_at", name="ux_odometer_vehicle_recorded_at"),
    )
    op.execute(
        "CREATE INDEX ix_odometer_vehicle_odo "
        "ON vehicle_odometer_reading (user_vehicle_id, odo_km DESC, recorded_at DESC)"
    )

    op.create_table(
        "vehicle_service_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_vehicle_id",
            sa.Uuid(),
            sa.ForeignKey("user_vehicle.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", service_record_source, nullable=False),
        sa.Column("external_order_id", sa.String(64), nullable=True),
        sa.Column("booking_id", sa.Uuid(), sa.ForeignKey("booking.id", ondelete="SET NULL"), nullable=True),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("odo_km", sa.Integer(), nullable=True),
        sa.Column("external_center_id", sa.String(64), nullable=True),
        sa.Column(
            "workshop_id",
            sa.Uuid(),
            sa.ForeignKey("workshop.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("items_done", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("odo_km IS NULL OR odo_km BETWEEN 0 AND 999999", name="ck_service_record_odo_km"),
        sa.CheckConstraint("source <> 'oem' OR external_order_id IS NOT NULL", name="ck_service_record_oem_order"),
        sa.CheckConstraint("source = 'oem' OR external_order_id IS NULL", name="ck_service_record_order_only_oem"),
        sa.CheckConstraint(
            "source = 'ev_care' OR booking_id IS NULL",
            name="ck_service_record_booking_only_ev_care",
        ),
    )
    op.create_index(
        "ux_service_record_oem_order",
        "vehicle_service_record",
        ["user_vehicle_id", "external_order_id"],
        unique=True,
        postgresql_where=sa.text("source = 'oem'"),
    )
    op.create_index(
        "ux_service_record_booking",
        "vehicle_service_record",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("source = 'ev_care'"),
    )
    op.execute(
        "CREATE INDEX ix_service_record_vehicle_date "
        "ON vehicle_service_record (user_vehicle_id, service_date DESC, odo_km DESC NULLS LAST)"
    )

    op.create_table(
        "vehicle_oem_sync",
        sa.Column(
            "user_vehicle_id",
            sa.Uuid(),
            sa.ForeignKey("user_vehicle.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("usage_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("service_history_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_trigger", oem_sync_trigger, nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("consecutive_failures >= 0", name="ck_oem_sync_failures"),
    )

    # Same policy as the other app tables: no anon-key access, only the backend.
    for table in ("vehicle_odometer_reading", "vehicle_service_record", "vehicle_oem_sync"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("vehicle_oem_sync")
    op.drop_table("vehicle_service_record")
    op.drop_table("vehicle_odometer_reading")
    bind = op.get_bind()
    for enum in reversed(ENUMS):
        enum.drop(bind, checkfirst=True)
