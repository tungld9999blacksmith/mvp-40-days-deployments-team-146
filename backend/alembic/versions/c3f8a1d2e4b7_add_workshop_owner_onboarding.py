"""add workshop-owner onboarding tables (FEAT-AUTH-003)

Creates ENT-007 ``workshop_owner``, the core ``workshop`` table (core.entity.md
+ FEAT-AUTH-003 columns), ENT-009 ``workshop_operating_hour``, ENT-010
``workshop_registration``, ENT-011 ``workshop_verification_attempt``, ENT-012
``workshop_owner_consent``.

``vehicle_user.preferred_workshop_id`` (core) is left to the booking feature.

Targets PostgreSQL / Supabase. Apply with ``alembic upgrade head``.

Revision ID: c3f8a1d2e4b7
Revises: b2e5d7f1a9c4
Create Date: 2026-09-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f8a1d2e4b7"
down_revision: str | Sequence[str] | None = "b2e5d7f1a9c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── New enum types ─────────────────────────────────────────────────────
# create_type=False: each type is created exactly once in upgrade(); otherwise
# create_table would emit a second CREATE TYPE for every column using it.
workshop_owner_onboarding_status = postgresql.ENUM(
    "onboarding_in_progress",
    "pending_workshop_verification",
    "verification_failed",
    "active",
    name="workshop_owner_onboarding_status_enum",
    create_type=False,
)
workshop_verification_status = postgresql.ENUM(
    "pending", "verified", "failed", name="workshop_verification_status_enum", create_type=False
)
workshop_status = postgresql.ENUM("active", "inactive", name="workshop_status_enum", create_type=False)
service_center_type = postgresql.ENUM(
    "dealer", "service_only", name="service_center_type_enum", create_type=False
)

_NEW_ENUMS = [
    workshop_owner_onboarding_status,
    workshop_verification_status,
    workshop_status,
    service_center_type,
]

# ── Existing enum types (created by earlier revisions) ─────────────────
user_status = postgresql.ENUM(name="user_status_enum", create_type=False)
verification_attempt_status = postgresql.ENUM(
    name="verification_attempt_status_enum", create_type=False
)
consent_type = postgresql.ENUM(name="consent_type_enum", create_type=False)

_NOW = sa.text("(CURRENT_TIMESTAMP)")


def upgrade() -> None:
    bind = op.get_bind()
    for enum in _NEW_ENUMS:
        enum.create(bind, checkfirst=True)

    # ── workshop_owner (ENT-007) ──────────────────────────────────────
    op.create_table(
        "workshop_owner",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("firebase_uid", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auth_provider", sa.String(length=32), nullable=False, server_default="google.com"),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
        sa.Column("full_name", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("national_id", sa.String(length=12), nullable=True),
        sa.Column("status", user_status, nullable=False, server_default="active"),
        sa.Column(
            "onboarding_status",
            workshop_owner_onboarding_status,
            nullable=False,
            server_default="onboarding_in_progress",
        ),
        sa.Column("profile_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_logout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "onboarding_status <> 'active' OR onboarding_completed_at IS NOT NULL",
            name="ck_workshop_owner_active_completed",
        ),
        sa.CheckConstraint(
            "profile_completed_at IS NULL OR "
            "(full_name IS NOT NULL AND phone IS NOT NULL AND national_id IS NOT NULL)",
            name="ck_workshop_owner_profile_complete",
        ),
        sa.CheckConstraint(
            "national_id IS NULL OR national_id ~ '^[0-9]{12}$'",
            name="ck_workshop_owner_national_id",
        ),
    )
    op.create_index("ix_workshop_owner_firebase_uid", "workshop_owner", ["firebase_uid"], unique=True)
    op.create_index("ix_workshop_owner_email", "workshop_owner", ["email"], unique=True)
    op.create_index("ix_workshop_owner_phone", "workshop_owner", ["phone"], unique=True)
    op.create_index("ix_workshop_owner_national_id", "workshop_owner", ["national_id"], unique=True)
    op.create_index(
        "ix_workshop_owner_onboarding_created",
        "workshop_owner",
        ["onboarding_status", "created_at"],
        postgresql_where=sa.text("onboarding_status <> 'active'"),
    )

    # ── workshop (core + FEAT-AUTH-003 columns) ───────────────────────
    op.create_table(
        "workshop",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_center_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("region", sa.String(length=50), nullable=False),
        sa.Column("type", service_center_type, nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("total_technicians", sa.Integer(), nullable=False),
        sa.Column("emergency_slots_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", workshop_status, nullable=False, server_default="active"),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("hotline", sa.String(length=20), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oem_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["workshop_owner.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("total_technicians > 0", name="ck_workshop_total_technicians"),
        sa.CheckConstraint(
            "emergency_slots_reserved >= 0 AND emergency_slots_reserved <= total_technicians",
            name="ck_workshop_emergency_slots",
        ),
        sa.CheckConstraint(
            "status <> 'active' OR owner_id IS NOT NULL", name="ck_workshop_active_has_owner"
        ),
        sa.CheckConstraint(
            "owner_id IS NULL OR (hotline IS NOT NULL AND onboarded_at IS NOT NULL)",
            name="ck_workshop_owner_fields",
        ),
        sa.CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)", name="ck_workshop_coordinates"
        ),
    )
    op.create_index("ix_workshop_external_center_id", "workshop", ["external_center_id"], unique=True)
    # W-05: one owner ↔ one workshop.
    op.create_index(
        "ux_workshop_owner",
        "workshop",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NOT NULL"),
    )
    op.create_index("ix_workshop_status_region", "workshop", ["status", "region"])

    # ── workshop_operating_hour (ENT-009) ─────────────────────────────
    op.create_table(
        "workshop_operating_hour",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workshop_id", sa.Uuid(), nullable=False),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("open_time", sa.Time(), nullable=True),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["workshop_id"], ["workshop.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workshop_id", "day_of_week", name="ux_workshop_operating_hour_day"),
        sa.CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_operating_hour_day"),
        sa.CheckConstraint(
            "(is_closed AND open_time IS NULL AND close_time IS NULL) OR "
            "(NOT is_closed AND open_time IS NOT NULL AND close_time IS NOT NULL "
            "AND close_time > open_time)",
            name="ck_operating_hour_range",
        ),
    )
    op.create_index("ix_workshop_operating_hour_workshop_id", "workshop_operating_hour", ["workshop_id"])

    # ── workshop_registration (ENT-010) ───────────────────────────────
    op.create_table(
        "workshop_registration",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("hotline", sa.String(length=20), nullable=False),
        sa.Column("total_technicians", sa.Integer(), nullable=False),
        sa.Column("emergency_slots_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("operating_hours", postgresql.JSONB(), nullable=False),
        sa.Column(
            "verification_status",
            workshop_verification_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("verification_failure_reason", sa.String(length=64), nullable=True),
        sa.Column("external_center_id", sa.String(length=64), nullable=True),
        sa.Column("workshop_id", sa.Uuid(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["workshop_owner.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workshop_id"], ["workshop.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "verification_status <> 'verified' OR "
            "(workshop_id IS NOT NULL AND external_center_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_workshop_registration_verified",
        ),
        sa.CheckConstraint(
            "verification_status <> 'failed' OR verification_failure_reason IS NOT NULL",
            name="ck_workshop_registration_failed",
        ),
        sa.CheckConstraint(
            "emergency_slots_reserved BETWEEN 0 AND total_technicians",
            name="ck_workshop_registration_slots",
        ),
    )
    op.create_index("ix_workshop_registration_owner_id", "workshop_registration", ["owner_id"])
    op.create_index(
        "ux_workshop_registration_owner_draft",
        "workshop_registration",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("verification_status <> 'verified'"),
    )

    # ── workshop_verification_attempt (ENT-011) ───────────────────────
    op.create_table(
        "workshop_verification_attempt",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("registration_id", sa.Uuid(), nullable=False),
        sa.Column("status", verification_attempt_status, nullable=False, server_default="pending"),
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
        sa.Column("external_center_id", sa.String(length=64), nullable=True),
        sa.Column("oem_http_status", sa.SmallInteger(), nullable=True),
        sa.Column("oem_request_id", sa.String(length=128), nullable=True),
        sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["workshop_owner.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registration_id"], ["workshop_registration.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="ux_ws_attempt_owner_idempotency"),
        sa.CheckConstraint("status = 'pending' OR responded_at IS NOT NULL", name="ck_ws_attempt_responded"),
        sa.CheckConstraint("status <> 'failed' OR failure_reason IS NOT NULL", name="ck_ws_attempt_failed"),
        sa.CheckConstraint("retry_count BETWEEN 0 AND 5", name="ck_ws_attempt_retry_count"),
    )
    op.create_index(
        "ix_ws_attempt_owner_requested",
        "workshop_verification_attempt",
        ["owner_id", sa.text("requested_at DESC")],
    )
    op.create_index(
        "ux_ws_attempt_owner_pending",
        "workshop_verification_attempt",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_ws_attempt_pending",
        "workshop_verification_attempt",
        ["next_retry_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_ws_attempt_requested_at", "workshop_verification_attempt", ["requested_at"])

    # ── workshop_owner_consent (ENT-012) ──────────────────────────────
    op.create_table(
        "workshop_owner_consent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("consent_type", consent_type, nullable=False),
        sa.Column("policy_version", sa.String(length=20), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["workshop_owner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workshop_owner_consent_latest",
        "workshop_owner_consent",
        ["owner_id", "consent_type", "created_at"],
    )

    # Supabase: block PostgREST access with the anon key (no policies).
    for table in (
        "workshop_owner",
        "workshop",
        "workshop_operating_hour",
        "workshop_registration",
        "workshop_verification_attempt",
        "workshop_owner_consent",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("workshop_owner_consent")
    op.drop_table("workshop_verification_attempt")
    op.drop_table("workshop_registration")
    op.drop_table("workshop_operating_hour")
    op.drop_table("workshop")
    op.drop_table("workshop_owner")

    bind = op.get_bind()
    for enum in reversed(_NEW_ENUMS):
        enum.drop(bind, checkfirst=True)
