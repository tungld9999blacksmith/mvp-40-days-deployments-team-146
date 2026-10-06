"""Booking receipts: created_at and indexes on their foreign keys.

Written with IF [NOT] EXISTS: c9e4a2f6b8d1 was briefly edited in place to add
the same objects, so some local databases may already have them.

Revision ID: d4f1a7c3e9b2
Revises: c9e4a2f6b8d1
"""

from alembic import op

revision = "d4f1a7c3e9b2"
down_revision = "c9e4a2f6b8d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE booking_request ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()")
    # One receipt per booking; also keeps the ON DELETE CASCADE from booking cheap.
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_booking_request_booking ON booking_request (booking_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_booking_request_user_id ON booking_request (user_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_booking_request_user_id")
    op.execute("DROP INDEX IF EXISTS ux_booking_request_booking")
    op.execute("ALTER TABLE booking_request DROP COLUMN IF EXISTS created_at")
