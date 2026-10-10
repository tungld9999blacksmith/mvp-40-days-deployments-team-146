"""restore quotes approved by the workshop owner (F5b back in scope)

The quote review flow (us-049, ENT-410/411) returns to the MVP: recreates
``quote_status_enum``, ``quote`` and ``quote_item`` with the schema that
``a3c7e9f1b2d4`` dropped. Support tickets and the Discord link stay removed.

Revision ID: b4e6f8a1c3d5
Revises: e7a9c2b4d6f8
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

_NOW = sa.func.now()

# revision identifiers, used by Alembic.
revision: str = "b4e6f8a1c3d5"
down_revision: str | Sequence[str] | None = "e7a9c2b4d6f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

quote_status = postgresql.ENUM(
    "draft", "pending_approval", "approved", "rejected", name="quote_status_enum", create_type=False
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
    ]


def upgrade() -> None:
    quote_status.create(op.get_bind(), checkfirst=True)

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

    # Supabase: block PostgREST access with the anon key (no policies).
    for table in ("quote", "quote_item"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("quote_item")
    op.drop_table("quote")
    quote_status.drop(op.get_bind(), checkfirst=True)
