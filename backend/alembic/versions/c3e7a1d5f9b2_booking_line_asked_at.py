"""booking_line: asked_at (owner reply SLA)

Open question 2 of docs/designs/bao-gia-hai-tang.md: when the owner has not answered a
line waiting for them 10 minutes after the workshop asked, the workshop calls them; both
sides see that deadline. ``asked_at`` is when the owner was last asked. Lines already
waiting get their last change (a PROPOSED line only changes when the workshop resends it).
Additive only and idempotent (``IF NOT EXISTS``) like b9d4f2a6c8e1, because the shared
Supabase DB is migrated by hand.

Revision ID: c3e7a1d5f9b2
Revises: b9d4f2a6c8e1
Create Date: 2026-10-11
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e7a1d5f9b2"
down_revision: str | Sequence[str] | None = "b9d4f2a6c8e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE booking_line ADD COLUMN IF NOT EXISTS asked_at TIMESTAMPTZ")
    op.execute("UPDATE booking_line SET asked_at = updated_at WHERE line_status = 'PROPOSED' AND asked_at IS NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE booking_line DROP COLUMN IF EXISTS asked_at")
