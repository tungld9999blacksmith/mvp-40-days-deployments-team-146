"""add core domain tables (core.entity.md v1.3)

Creates the core tables that had models but no migration yet — ENT-401
``maintenance_rule`` (with ``item_code``, Q-401/Q-402), ENT-402 ``booking``,
ENT-403 ``service_progress``, ENT-404 ``customer_profile_cdp``, ENT-405
``reminder`` — and the v1.2 tables: ENT-406 ``official_document``, ENT-407
``document_chunk`` (pgvector, 1024 dims), ENT-408 ``maintenance_rule_source``,
ENT-409 ``service_price``, ENT-410 ``quote``, ENT-411 ``quote_item``, ENT-412
``follow_up``, ENT-413 ``support_ticket``.

Also adds ``vehicle_user.preferred_workshop_id`` (left over by c3f8a1d2e4b7 for
the booking feature).

Targets PostgreSQL / Supabase (needs the ``vector`` extension, PostgreSQL 15+
for ``NULLS NOT DISTINCT``). Apply with ``alembic upgrade head``.

Revision ID: e5b1c7d9f2a3
Revises: d4a9b2c5e6f1
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b1c7d9f2a3"
down_revision: str | Sequence[str] | None = "d4a9b2c5e6f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── New enum types ─────────────────────────────────────────────────────
# create_type=False: each type is created exactly once in upgrade(); otherwise
# create_table would emit a second CREATE TYPE for every column using it.
booking_status = postgresql.ENUM(
    "pending",
    "confirmed",
    "checked_in",
    "in_progress",
    "completed",
    "cancelled",
    name="booking_status_enum",
    create_type=False,
)
service_stage = postgresql.ENUM(
    "checked_in",
    "inspecting",
    "servicing",
    "waiting_parts",
    "quality_check",
    "ready_for_pickup",
    name="service_stage_enum",
    create_type=False,
)
reminder_level = postgresql.ENUM("early", "warning", "urgent", "expired", name="reminder_level_enum", create_type=False)
reminder_channel = postgresql.ENUM("in_app", "push", "sms_zalo", name="reminder_channel_enum", create_type=False)
official_document_type = postgresql.ENUM(
    "owner_manual",
    "maintenance_manual",
    "warranty_policy",
    "service_bulletin",
    name="official_document_type_enum",
    create_type=False,
)
quote_status = postgresql.ENUM(
    "draft", "pending_approval", "approved", "rejected", name="quote_status_enum", create_type=False
)
follow_up_status = postgresql.ENUM(
    "pending", "sent", "responded", "closed", name="follow_up_status_enum", create_type=False
)
support_ticket_status = postgresql.ENUM(
    "open", "in_progress", "resolved", name="support_ticket_status_enum", create_type=False
)

_NEW_ENUMS = [
    booking_status,
    service_stage,
    reminder_level,
    reminder_channel,
    official_document_type,
    quote_status,
    follow_up_status,
    support_ticket_status,
]

_NOW = sa.text("(CURRENT_TIMESTAMP)")

_NEW_TABLES = (
    "maintenance_rule",
    "customer_profile_cdp",
    "reminder",
    "booking",
    "service_progress",
    "official_document",
    "document_chunk",
    "maintenance_rule_source",
    "service_price",
    "quote",
    "quote_item",
    "follow_up",
    "support_ticket",
)


def _timestamps(*, with_updated_at: bool = True) -> list[sa.Column]:
    cols = [sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False)]
    if with_updated_at:
        cols.append(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False))
    return cols


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    bind = op.get_bind()
    for enum in _NEW_ENUMS:
        enum.create(bind, checkfirst=True)

    # ── vehicle_user.preferred_workshop_id (ENT-001) ──────────────────
    op.add_column("vehicle_user", sa.Column("preferred_workshop_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_vehicle_user_preferred_workshop_id",
        "vehicle_user",
        "workshop",
        ["preferred_workshop_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_vehicle_user_preferred_workshop_id"), "vehicle_user", ["preferred_workshop_id"])

    # ── maintenance_rule (ENT-401) ────────────────────────────────────
    op.create_table(
        "maintenance_rule",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("odo_milestone", sa.Integer(), nullable=False),
        sa.Column("month_milestone", sa.Integer(), nullable=False),
        sa.Column("item_code", sa.String(length=50), nullable=False),
        sa.Column("item_name", sa.String(length=200), nullable=False),
        sa.Column("is_covered_by_warranty", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("estimated_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("odo_milestone > 0", name="ck_maintenance_rule_odo_milestone"),
        sa.CheckConstraint("month_milestone > 0", name="ck_maintenance_rule_month_milestone"),
        sa.CheckConstraint("estimated_cost >= 0", name="ck_maintenance_rule_estimated_cost"),
        sa.CheckConstraint("estimated_duration_minutes > 0", name="ck_maintenance_rule_estimated_duration"),
        sa.CheckConstraint("item_code ~ '^[A-Z0-9_]{2,50}$'", name="ck_maintenance_rule_item_code_format"),
        sa.UniqueConstraint("model_id", "odo_milestone", "item_name", name="ux_maintenance_rule_model_milestone_item"),
        sa.UniqueConstraint("model_id", "odo_milestone", "item_code", name="ux_maintenance_rule_model_milestone_code"),
    )
    op.create_index(op.f("ix_maintenance_rule_model_id"), "maintenance_rule", ["model_id"])
    op.create_index("ix_maintenance_rule_model_item_code", "maintenance_rule", ["model_id", "item_code"])

    # ── customer_profile_cdp (ENT-404) ────────────────────────────────
    op.create_table(
        "customer_profile_cdp",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("interaction_history", postgresql.JSONB(), nullable=True),
        sa.Column("preferences", postgresql.JSONB(), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_cold_start", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["vehicle_user.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # ── reminder (ENT-405) ────────────────────────────────────────────
    op.create_table(
        "reminder",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("target_odo_milestone", sa.Integer(), nullable=False),
        sa.Column("reminder_level", reminder_level, nullable=False, server_default="early"),
        sa.Column("channel", reminder_channel, nullable=False, server_default="in_app"),
        sa.Column("snooze_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_vehicle_id"], ["user_vehicle.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("target_odo_milestone > 0", name="ck_reminder_target_odo_milestone"),
        sa.CheckConstraint("snooze_count >= 0", name="ck_reminder_snooze_count"),
    )
    op.create_index(op.f("ix_reminder_user_vehicle_id"), "reminder", ["user_vehicle_id"])

    # ── booking (ENT-402) ─────────────────────────────────────────────
    op.create_table(
        "booking",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_code", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("workshop_id", sa.Uuid(), nullable=False),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("time_slot", sa.Time(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("actual_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", booking_status, nullable=False, server_default="pending"),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["vehicle_user.user_id"]),
        sa.ForeignKeyConstraint(["user_vehicle_id"], ["user_vehicle.id"]),
        sa.ForeignKeyConstraint(["workshop_id"], ["workshop.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("estimated_cost IS NULL OR estimated_cost >= 0", name="ck_booking_estimated_cost"),
        sa.CheckConstraint("actual_cost IS NULL OR actual_cost >= 0", name="ck_booking_actual_cost"),
    )
    op.create_index(op.f("ix_booking_booking_code"), "booking", ["booking_code"], unique=True)
    op.create_index(op.f("ix_booking_user_id"), "booking", ["user_id"])
    op.create_index(op.f("ix_booking_user_vehicle_id"), "booking", ["user_vehicle_id"])
    op.create_index(op.f("ix_booking_workshop_id"), "booking", ["workshop_id"])

    # ── service_progress (ENT-403, append-only) ───────────────────────
    op.create_table(
        "service_progress",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("stage", service_stage, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        *_timestamps(with_updated_at=False),
        sa.ForeignKeyConstraint(["booking_id"], ["booking.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_service_progress_booking_id"), "service_progress", ["booking_id"])

    # ── official_document (ENT-406) ───────────────────────────────────
    op.create_table(
        "official_document",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=True),
        sa.Column("document_type", official_document_type, nullable=False),
        sa.Column("version", sa.String(length=50), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "title",
            "version",
            name="ux_official_document_title_version",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_official_document_model_type", "official_document", ["model_id", "document_type"])

    # ── document_chunk (ENT-407, append-only) ─────────────────────────
    op.create_table(
        "document_chunk",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=False),
        *_timestamps(with_updated_at=False),
        sa.ForeignKeyConstraint(["document_id"], ["official_document.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_document_chunk_chunk_index"),
        sa.CheckConstraint("page_number IS NULL OR page_number > 0", name="ck_document_chunk_page_number"),
        sa.UniqueConstraint("document_id", "chunk_index", name="ux_document_chunk_document_index"),
    )
    op.create_index(
        "ix_document_chunk_embedding_hnsw",
        "document_chunk",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # ── maintenance_rule_source (ENT-408) ─────────────────────────────
    op.create_table(
        "maintenance_rule_source",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("maintenance_rule_id", sa.Uuid(), nullable=False),
        sa.Column("document_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(with_updated_at=False),
        sa.ForeignKeyConstraint(["maintenance_rule_id"], ["maintenance_rule.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_chunk_id"], ["document_chunk.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "maintenance_rule_id",
            "document_chunk_id",
            name="ux_maintenance_rule_source_rule_chunk",
        ),
    )
    op.create_index(
        op.f("ix_maintenance_rule_source_document_chunk_id"),
        "maintenance_rule_source",
        ["document_chunk_id"],
    )

    # ── service_price (ENT-409) ───────────────────────────────────────
    op.create_table(
        "service_price",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workshop_id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("item_code", sa.String(length=50), nullable=False),
        sa.Column("item_name", sa.String(length=200), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["workshop_id"], ["workshop.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("price >= 0", name="ck_service_price_price"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_service_price_validity",
        ),
    )
    op.create_index(
        "ix_service_price_workshop_model_item",
        "service_price",
        ["workshop_id", "model_id", "item_code"],
    )

    # ── quote (ENT-410) ───────────────────────────────────────────────
    op.create_table(
        "quote",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("workshop_id", sa.Uuid(), nullable=False),
        sa.Column("odo_milestone", sa.Integer(), nullable=True),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("status", quote_status, nullable=False, server_default="draft"),
        sa.Column("estimated_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("approved_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_vehicle_id"], ["user_vehicle.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workshop_id"], ["workshop.id"]),
        sa.ForeignKeyConstraint(["booking_id"], ["booking.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["workshop_owner.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("estimated_total >= 0", name="ck_quote_estimated_total"),
        sa.CheckConstraint("approved_total IS NULL OR approved_total >= 0", name="ck_quote_approved_total"),
        sa.CheckConstraint("odo_milestone IS NULL OR odo_milestone > 0", name="ck_quote_odo_milestone"),
        sa.CheckConstraint(
            "status NOT IN ('approved', 'rejected') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_quote_reviewed",
        ),
        sa.CheckConstraint(
            "status <> 'approved' OR (approved_total IS NOT NULL AND expires_at IS NOT NULL)",
            name="ck_quote_approved_fields",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR (reviewed_at IS NOT NULL AND expires_at > reviewed_at)",
            name="ck_quote_expires_after_review",
        ),
        sa.CheckConstraint("booking_id IS NULL OR status = 'approved'", name="ck_quote_booking_requires_approval"),
    )
    op.create_index(op.f("ix_quote_booking_id"), "quote", ["booking_id"])
    op.create_index(op.f("ix_quote_reviewed_by"), "quote", ["reviewed_by"])
    op.create_index("ix_quote_workshop_status", "quote", ["workshop_id", "status"])
    op.create_index("ix_quote_user_vehicle_created", "quote", ["user_vehicle_id", "created_at"])

    # ── quote_item (ENT-411) ──────────────────────────────────────────
    op.create_table(
        "quote_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("maintenance_rule_id", sa.Uuid(), nullable=True),
        sa.Column("item_code", sa.String(length=50), nullable=True),
        sa.Column("item_name", sa.String(length=200), nullable=False),
        sa.Column("estimated_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("approved_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["quote_id"], ["quote.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["maintenance_rule_id"], ["maintenance_rule.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("estimated_price >= 0", name="ck_quote_item_estimated_price"),
        sa.CheckConstraint("approved_price IS NULL OR approved_price >= 0", name="ck_quote_item_approved_price"),
    )
    op.create_index(op.f("ix_quote_item_quote_id"), "quote_item", ["quote_id"])
    op.create_index(op.f("ix_quote_item_maintenance_rule_id"), "quote_item", ["maintenance_rule_id"])

    # ── follow_up (ENT-412) ───────────────────────────────────────────
    op.create_table(
        "follow_up",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("customer_response", sa.Text(), nullable=True),
        sa.Column("has_issue", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", follow_up_status, nullable=False, server_default="pending"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["booking_id"], ["booking.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
        sa.CheckConstraint("status = 'pending' OR sent_at IS NOT NULL", name="ck_follow_up_sent_at"),
        sa.CheckConstraint(
            "status <> 'responded' OR (responded_at IS NOT NULL AND customer_response IS NOT NULL)",
            name="ck_follow_up_responded",
        ),
    )
    op.create_index(
        "ix_follow_up_pending_scheduled",
        "follow_up",
        ["scheduled_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # ── support_ticket (ENT-413) ──────────────────────────────────────
    op.create_table(
        "support_ticket",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("follow_up_id", sa.Uuid(), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_to", sa.Uuid(), nullable=True),
        sa.Column("issue_summary", sa.Text(), nullable=False),
        sa.Column("status", support_ticket_status, nullable=False, server_default="open"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["follow_up_id"], ["follow_up.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_vehicle_id"], ["user_vehicle.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to"], ["workshop_owner.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status <> 'resolved' OR resolved_at IS NOT NULL", name="ck_support_ticket_resolved_at"),
        sa.CheckConstraint("status = 'open' OR assigned_to IS NOT NULL", name="ck_support_ticket_assigned"),
    )
    op.create_index(op.f("ix_support_ticket_follow_up_id"), "support_ticket", ["follow_up_id"])
    op.create_index(op.f("ix_support_ticket_user_vehicle_id"), "support_ticket", ["user_vehicle_id"])
    op.create_index("ix_support_ticket_assignee_status", "support_ticket", ["assigned_to", "status"])

    # Supabase: block PostgREST access with the anon key (no policies).
    for table in _NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(_NEW_TABLES):
        op.drop_table(table)

    op.drop_index(op.f("ix_vehicle_user_preferred_workshop_id"), table_name="vehicle_user")
    op.drop_constraint("fk_vehicle_user_preferred_workshop_id", "vehicle_user", type_="foreignkey")
    op.drop_column("vehicle_user", "preferred_workshop_id")

    bind = op.get_bind()
    for enum in reversed(_NEW_ENUMS):
        enum.drop(bind, checkfirst=True)
    # The ``vector`` extension is left installed: other schemas may use it.
