"""add booking_proposal (us-061 quick booking from the AI assistant)

A proposal is the booking card shown in chat: status, the offered options and,
once the owner confirms, the booking it produced. Bookings are created from a
proposal only through the confirm endpoint (us-061 BR-1509).

Revision ID: b8d2f4a6c1e3
Revises: a3c7e9f1b2d4
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

_NOW = sa.func.now()

# revision identifiers, used by Alembic.
revision: str = "b8d2f4a6c1e3"
down_revision: str | Sequence[str] | None = "a3c7e9f1b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

proposal_status = postgresql.ENUM(
    "proposed", "confirmed", "cancelled", "superseded", "expired", name="booking_proposal_status_enum"
)


def upgrade() -> None:
    proposal_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "booking_proposal",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), sa.ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("chat_message.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="booking_proposal_status_enum", create_type=False),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column("superseded_reason", sa.String(16), nullable=True),
        sa.Column("odo_milestone", sa.Integer(), nullable=True),
        sa.Column("workshop_id", sa.Uuid(), sa.ForeignKey("workshop.id"), nullable=False),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("time_slot", sa.Time(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("location_basis", sa.String(16), nullable=False),
        sa.Column("booking_id", sa.Uuid(), sa.ForeignKey("booking.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint(
            "(status = 'confirmed') = (booking_id IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_booking_proposal_confirmed",
        ),
        sa.CheckConstraint(
            "(status = 'superseded') = (superseded_reason IS NOT NULL)",
            name="ck_booking_proposal_superseded",
        ),
        sa.CheckConstraint("source IN ('QUICK_BOOKING', 'CHAT_AGENT')", name="ck_booking_proposal_source"),
        sa.CheckConstraint(
            "location_basis IN ('DEVICE', 'PROFILE', 'PROVINCE', 'NONE')",
            name="ck_booking_proposal_location_basis",
        ),
    )
    op.create_index(
        "ux_booking_proposal_open_per_user",
        "booking_proposal",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'proposed'"),
    )
    op.create_index(
        "ux_booking_proposal_booking",
        "booking_proposal",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("booking_id IS NOT NULL"),
    )
    op.create_index("ix_booking_proposal_conversation", "booking_proposal", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_booking_proposal_conversation", table_name="booking_proposal")
    op.drop_index("ux_booking_proposal_booking", table_name="booking_proposal")
    op.drop_index("ux_booking_proposal_open_per_user", table_name="booking_proposal")
    op.drop_table("booking_proposal")
    proposal_status.drop(op.get_bind(), checkfirst=True)
