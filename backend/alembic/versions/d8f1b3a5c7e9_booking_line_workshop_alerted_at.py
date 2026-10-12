"""booking_line: workshop_alerted_at (email the workshop when the owner reply is overdue)

The workshop sees "Cần gọi" only while the board or Dashboard is open. A Celery job now
emails the workshop owner once per ``asked_at`` when a line waiting for the owner passes
OWNER_REPLY_SLA; ``workshop_alerted_at`` records that alert. Additive only and idempotent
(``IF NOT EXISTS``) like c3e7a1d5f9b2, because the shared Supabase DB is migrated by hand.

Revision ID: d8f1b3a5c7e9
Revises: 9b7d3e1f5a6c
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f1b3a5c7e9"
down_revision: str | Sequence[str] | None = "9b7d3e1f5a6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE booking_line ADD COLUMN IF NOT EXISTS workshop_alerted_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE booking_line DROP COLUMN IF EXISTS workshop_alerted_at")
