"""add onboarding tables and vehicle_user columns

Adds the onboarding columns to ``vehicle_user`` and creates the onboarding
entities (ENT-002..ENT-006): user_location, user_vehicle, vehicle_warranty,
vehicle_verification_attempt, user_consent.

Targets PostgreSQL / Supabase. Apply with ``alembic upgrade head``.

Revision ID: a1f4c2d3e5b6
Revises: 272915ecc478
Create Date: 2026-09-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Enum types are created exactly once via .create(checkfirst=True) in upgrade();
# create_type=False stops create_table/add_column from emitting a 2nd CREATE TYPE.

# revision identifiers, used by Alembic.
revision: str = "a1f4c2d3e5b6"
down_revision: Union[str, Sequence[str], None] = "272915ecc478"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Reusable enum types ────────────────────────────────────────────────
onboarding_status = postgresql.ENUM(
    "onboarding_in_progress",
    "pending_vehicle_verification",
    "verification_failed",
    "active",
    name="onboarding_status_enum", create_type=False,
)
location_type = postgresql.ENUM("home", "work", "other", name="location_type_enum", create_type=False)
location_source = postgresql.ENUM("manual", "map_pick", "gps", name="location_source_enum", create_type=False)
vehicle_verification_status = postgresql.ENUM(
    "pending", "verified", "failed", name="vehicle_verification_status_enum", create_type=False
)
vehicle_link_status = postgresql.ENUM("active", "unlinked", name="vehicle_link_status_enum", create_type=False)
verification_attempt_status = postgresql.ENUM(
    "pending", "success", "failed", name="verification_attempt_status_enum", create_type=False
)
verification_failure_reason = postgresql.ENUM(
    "vin_not_found",
    "plate_mismatch",
    "model_mismatch",
    "owner_email_mismatch",
    "national_id_mismatch",
    "already_linked",
    "oem_unavailable",
    name="verification_failure_reason_enum", create_type=False,
)
warranty_component = postgresql.ENUM(
    "battery", "motor", "chassis", "electronics", name="warranty_component_enum", create_type=False
)
warranty_status = postgresql.ENUM("active", "expired", name="warranty_status_enum", create_type=False)
consent_type = postgresql.ENUM(
    "personal_data_processing", "oem_data_sharing", name="consent_type_enum", create_type=False
)

_ALL_ENUMS = [
    onboarding_status,
    location_type,
    location_source,
    vehicle_verification_status,
    vehicle_link_status,
    verification_attempt_status,
    verification_failure_reason,
    warranty_component,
    warranty_status,
    consent_type,
]


def upgrade() -> None:
    bind = op.get_bind()
    # Create every enum type once (verification_failure_reason_enum is shared
    # by two tables, so it must not be auto-created per column).
    for enum in _ALL_ENUMS:
        enum.create(bind, checkfirst=True)

    # ── vehicle_user: new onboarding columns ──────────────────────────
    op.add_column("vehicle_user", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("vehicle_user", sa.Column("auth_provider", sa.String(length=32), nullable=False, server_default="google.com"))
    op.add_column("vehicle_user", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.add_column("vehicle_user", sa.Column("avatar_url", sa.String(length=1024), nullable=True))
    op.add_column("vehicle_user", sa.Column("full_name", sa.String(length=150), nullable=True))
    op.add_column("vehicle_user", sa.Column("national_id", sa.String(length=12), nullable=True))
    op.add_column("vehicle_user", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column(
        "vehicle_user",
        sa.Column(
            "onboarding_status",
            onboarding_status,
            nullable=False,
            server_default="onboarding_in_progress",
        ),
    )
    op.add_column("vehicle_user", sa.Column("profile_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("vehicle_user", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_vehicle_user_national_id"), "vehicle_user", ["national_id"], unique=True)

    # external_owner_id: integer -> varchar(64) (manufacturer owner id is a string).
    # batch_alter_table keeps this portable (SQLite recreates the table; on
    # PostgreSQL it emits a normal ALTER with the USING cast).
    with op.batch_alter_table("vehicle_user") as batch_op:
        batch_op.alter_column(
            "external_owner_id",
            existing_type=sa.Integer(),
            type_=sa.String(length=64),
            existing_nullable=True,
            postgresql_using="external_owner_id::varchar",
        )

    # ── user_location ─────────────────────────────────────────────────
    op.create_table(
        "user_location",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("location_type", location_type, nullable=False, server_default="home"),
        sa.Column("address_line", sa.String(length=500), nullable=False),
        sa.Column("ward", sa.String(length=100), nullable=True),
        sa.Column("district", sa.String(length=100), nullable=True),
        sa.Column("province", sa.String(length=100), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("source", location_source, nullable=False, server_default="manual"),
        sa.Column("place_id", sa.String(length=255), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["vehicle_user.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_location_user_id"), "user_location", ["user_id"])
    op.create_index(
        "ux_user_location_primary",
        "user_location",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )

    # ── user_vehicle ──────────────────────────────────────────────────
    op.create_table(
        "user_vehicle",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("vin", sa.String(length=17), nullable=False),
        sa.Column("license_plate", sa.String(length=20), nullable=False),
        sa.Column("declared_model_id", sa.String(length=64), nullable=False),
        sa.Column("declared_manufacture_year", sa.SmallInteger(), nullable=True),
        sa.Column("external_vehicle_id", sa.String(length=64), nullable=True),
        sa.Column("external_owner_id", sa.String(length=64), nullable=True),
        sa.Column("external_model_id", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("trim", sa.String(length=50), nullable=True),
        sa.Column("color", sa.String(length=50), nullable=True),
        sa.Column("manufacture_date", sa.Date(), nullable=True),
        sa.Column("production_year", sa.SmallInteger(), nullable=True),
        sa.Column("battery_capacity_kwh", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("motor_power_kw", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("verification_status", vehicle_verification_status, nullable=False, server_default="pending"),
        sa.Column("verification_failure_reason", verification_failure_reason, nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("link_status", vehicle_link_status, nullable=False, server_default="active"),
        sa.Column("oem_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["vehicle_user.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_vehicle_user_id"), "user_vehicle", ["user_id"])
    op.create_index(op.f("ix_user_vehicle_vin"), "user_vehicle", ["vin"])
    op.create_index(op.f("ix_user_vehicle_license_plate"), "user_vehicle", ["license_plate"])
    # BR-002: a VIN can be actively verified for only one account.
    op.create_index(
        "ux_user_vehicle_vin_active",
        "user_vehicle",
        ["vin"],
        unique=True,
        postgresql_where=sa.text("verification_status = 'verified' AND link_status = 'active'"),
    )
    # One active draft (pending/failed) per user.
    op.create_index(
        "ux_user_vehicle_user_draft",
        "user_vehicle",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("link_status = 'active' AND verification_status <> 'verified'"),
    )
    # A user does not declare the same VIN twice while active.
    op.create_index(
        "ux_user_vehicle_user_vin",
        "user_vehicle",
        ["user_id", "vin"],
        unique=True,
        postgresql_where=sa.text("link_status = 'active'"),
    )

    # ── vehicle_warranty ──────────────────────────────────────────────
    op.create_table(
        "vehicle_warranty",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("external_warranty_id", sa.String(length=64), nullable=False),
        sa.Column("external_policy_id", sa.String(length=64), nullable=True),
        sa.Column("component", warranty_component, nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("km_limit", sa.Integer(), nullable=True),
        sa.Column("duration_months", sa.Integer(), nullable=True),
        sa.Column("terms_description", sa.Text(), nullable=True),
        sa.Column("oem_status", warranty_status, nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_vehicle_id"], ["user_vehicle.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_vehicle_id", "external_warranty_id", name="ux_vehicle_warranty_unique"),
    )
    op.create_index(op.f("ix_vehicle_warranty_user_vehicle_id"), "vehicle_warranty", ["user_vehicle_id"])

    # ── vehicle_verification_attempt ──────────────────────────────────
    op.create_table(
        "vehicle_verification_attempt",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("vin", sa.String(length=17), nullable=False),
        sa.Column("license_plate", sa.String(length=20), nullable=False),
        sa.Column("declared_model_id", sa.String(length=64), nullable=False),
        sa.Column("status", verification_attempt_status, nullable=False, server_default="pending"),
        sa.Column("failure_reason", verification_failure_reason, nullable=True),
        sa.Column("oem_http_status", sa.SmallInteger(), nullable=True),
        sa.Column("oem_request_id", sa.String(length=128), nullable=True),
        sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["vehicle_user.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_vehicle_id"], ["user_vehicle.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="ux_attempt_user_idempotency"),
    )
    op.create_index("ix_attempt_user_requested", "vehicle_verification_attempt", ["user_id", "requested_at"])
    op.create_index(op.f("ix_vehicle_verification_attempt_requested_at"), "vehicle_verification_attempt", ["requested_at"])
    op.create_index(
        "ux_attempt_user_pending",
        "vehicle_verification_attempt",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # ── user_consent ──────────────────────────────────────────────────
    op.create_table(
        "user_consent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("consent_type", consent_type, nullable=False),
        sa.Column("policy_version", sa.String(length=20), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["vehicle_user.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_consent_latest",
        "user_consent",
        ["user_id", "consent_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("user_consent")
    op.drop_table("vehicle_verification_attempt")
    op.drop_table("vehicle_warranty")
    op.drop_table("user_vehicle")
    op.drop_table("user_location")

    with op.batch_alter_table("vehicle_user") as batch_op:
        batch_op.alter_column(
            "external_owner_id",
            existing_type=sa.String(length=64),
            type_=sa.Integer(),
            existing_nullable=True,
            postgresql_using="external_owner_id::integer",
        )
    op.drop_index(op.f("ix_vehicle_user_national_id"), table_name="vehicle_user")
    for col in (
        "onboarding_completed_at",
        "profile_completed_at",
        "onboarding_status",
        "date_of_birth",
        "national_id",
        "full_name",
        "avatar_url",
        "display_name",
        "auth_provider",
        "email_verified",
    ):
        op.drop_column("vehicle_user", col)

    bind = op.get_bind()
    for enum in reversed(_ALL_ENUMS):
        enum.drop(bind, checkfirst=True)
