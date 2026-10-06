"""Persist booking idempotency receipts.

Revision ID: c9e4a2f6b8d1
Revises: b8d2f4a6c1e3
"""

import sqlalchemy as sa

from alembic import op

revision = "c9e4a2f6b8d1"
down_revision = "b8d2f4a6c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_request",
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("vehicle_user.user_id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("booking_id", sa.Uuid(), sa.ForeignKey("booking.id", ondelete="CASCADE"), nullable=False),
    )
    op.execute("ALTER TABLE booking_request ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("booking_request")
