"""drop quotes, support tickets and the Discord link (features removed from scope)

The quote review flow (us-049), support tickets (us-041) and the Discord
connection (ENT-417) are no longer part of the product:

- Drops ``quote_item``, ``quote``, ``support_ticket``, ``user_discord_link`` and
  their enum types.
- Reminders are shown in the in-app feed only: ``reminder.channel`` moves from
  ``discord`` to ``in_app`` (new default ``in_app``); Discord channel choices and
  unsent Discord deliveries are deleted. Sent deliveries stay as history.

PostgreSQL cannot drop enum values, so ``discord`` stays in
``reminder_channel_enum`` as a deprecated value (never written by the app).

Revision ID: a3c7e9f1b2d4
Revises: f1d3b5a7c9e2
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

_NOW = sa.func.now()

# revision identifiers, used by Alembic.
revision: str = "a3c7e9f1b2d4"
down_revision: str | Sequence[str] | None = "f1d3b5a7c9e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

quote_status = postgresql.ENUM(
    "draft", "pending_approval", "approved", "rejected", name="quote_status_enum", create_type=False
)
ticket_status = postgresql.ENUM("open", "in_progress", "resolved", name="support_ticket_status_enum", create_type=False)
ticket_priority = postgresql.ENUM("normal", "high", name="support_ticket_priority_enum", create_type=False)
discord_link_status = postgresql.ENUM(
    "pending", "active", "revoked", name="discord_link_status_enum", create_type=False
)
_ENUMS = (quote_status, ticket_status, ticket_priority, discord_link_status)
_DELIVERY_TABLES = ("reminder_delivery", "booking_reminder_delivery", "follow_up_delivery")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
    ]


def upgrade() -> None:
    op.drop_table("quote_item")
    op.drop_table("quote")
    op.drop_table("support_ticket")
    op.drop_table("user_discord_link")
    bind = op.get_bind()
    for enum in _ENUMS:
        enum.drop(bind, checkfirst=True)

    op.execute("UPDATE reminder SET channel = 'in_app' WHERE channel = 'discord'")
    op.execute("ALTER TABLE reminder ALTER COLUMN channel SET DEFAULT 'in_app'")
    op.execute("DELETE FROM user_notification_channel WHERE channel = 'discord'")
    for table in _DELIVERY_TABLES:
        op.execute(f"DELETE FROM {table} WHERE channel = 'discord' AND status <> 'sent'")


def downgrade() -> None:
    # Data of the dropped tables is gone; this only restores the schema of f1d3b5a7c9e2.
    op.execute("ALTER TABLE reminder ALTER COLUMN channel SET DEFAULT 'discord'")
    op.execute("UPDATE reminder SET channel = 'discord' WHERE channel = 'in_app'")

    bind = op.get_bind()
    for enum in _ENUMS:
        enum.create(bind, checkfirst=True)

    # ── user_discord_link (ENT-417) ───────────────────────────────────────
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

    # ── quote (ENT-410) ───────────────────────────────────────────────────
    op.create_table(
        "quote",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("workshop_id", sa.Uuid(), nullable=False),
        sa.Column("odo_milestone", sa.Integer(), nullable=True),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("status", quote_status, nullable=False, server_default="draft"),
        sa.Column("estimated_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("approved_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_vehicle_id"], ["user_vehicle.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workshop_id"], ["workshop.id"]),
        sa.ForeignKeyConstraint(["booking_id"], ["booking.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["workshop_owner.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_message_id"], ["chat_message.id"], ondelete="SET NULL", name="fk_quote_source_message"
        ),
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
        sa.CheckConstraint("status = 'draft' OR submitted_at IS NOT NULL", name="ck_quote_submitted_at"),
        sa.CheckConstraint(
            "reviewed_at IS NULL OR submitted_at IS NULL OR reviewed_at >= submitted_at",
            name="ck_quote_reviewed_after_submit",
        ),
    )
    op.create_index(op.f("ix_quote_booking_id"), "quote", ["booking_id"])
    op.create_index(op.f("ix_quote_reviewed_by"), "quote", ["reviewed_by"])
    op.create_index("ix_quote_workshop_status", "quote", ["workshop_id", "status"])
    op.create_index("ix_quote_user_vehicle_created", "quote", ["user_vehicle_id", "created_at"])
    op.create_index(
        "uq_quote_pending_per_milestone",
        "quote",
        ["user_vehicle_id", "workshop_id", "odo_milestone"],
        unique=True,
        postgresql_where=sa.text("status = 'pending_approval'"),
    )

    # ── quote_item (ENT-411) ──────────────────────────────────────────────
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
        sa.Column("is_covered_by_warranty", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("price_source", sa.String(20), nullable=True),
        sa.Column("reviewer_note", sa.String(255), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["quote_id"], ["quote.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["maintenance_rule_id"], ["maintenance_rule.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("estimated_price >= 0", name="ck_quote_item_estimated_price"),
        sa.CheckConstraint("approved_price IS NULL OR approved_price >= 0", name="ck_quote_item_approved_price"),
        sa.CheckConstraint(
            "NOT is_covered_by_warranty OR (estimated_price = 0 AND (approved_price IS NULL OR approved_price = 0))",
            name="ck_quote_item_covered_zero",
        ),
    )
    op.create_index(op.f("ix_quote_item_quote_id"), "quote_item", ["quote_id"])
    op.create_index(op.f("ix_quote_item_maintenance_rule_id"), "quote_item", ["maintenance_rule_id"])

    # ── support_ticket (ENT-413) ──────────────────────────────────────────
    op.create_table(
        "support_ticket",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("follow_up_id", sa.Uuid(), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_to", sa.Uuid(), nullable=True),
        sa.Column("issue_summary", sa.Text(), nullable=False),
        sa.Column("status", ticket_status, nullable=False, server_default="open"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", ticket_priority, server_default="normal", nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["follow_up_id"], ["follow_up.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_vehicle_id"], ["user_vehicle.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to"], ["workshop_owner.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("follow_up_id", name="ux_support_ticket_follow_up"),
        sa.CheckConstraint("status <> 'resolved' OR resolved_at IS NOT NULL", name="ck_support_ticket_resolved_at"),
        sa.CheckConstraint("status = 'open' OR assigned_to IS NOT NULL", name="ck_support_ticket_assigned"),
        sa.CheckConstraint("status <> 'resolved' OR resolution_note IS NOT NULL", name="ck_support_ticket_resolution"),
        sa.CheckConstraint("status <> 'in_progress' OR started_at IS NOT NULL", name="ck_support_ticket_started"),
    )
    op.create_index(op.f("ix_support_ticket_follow_up_id"), "support_ticket", ["follow_up_id"])
    op.create_index(op.f("ix_support_ticket_user_vehicle_id"), "support_ticket", ["user_vehicle_id"])
    op.create_index("ix_support_ticket_assignee_status", "support_ticket", ["assigned_to", "status"])

    # Supabase: block PostgREST access with the anon key (no policies).
    for table in ("quote", "quote_item", "support_ticket"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
