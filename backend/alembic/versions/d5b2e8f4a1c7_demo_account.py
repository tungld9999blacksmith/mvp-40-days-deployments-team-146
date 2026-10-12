"""demo account: vehicle_user.is_demo + demo_account_state

The shared "Dùng thử ngay" account (docs: frontend Login, backend modules/demo_account).
``vehicle_user.is_demo`` marks the account so outgoing notifications are skipped and its
profile / vehicles stay read-only; ``demo_account_state`` is a single row holding when
the account was last reset (the hourly job resets it every DEMO_RESET_INTERVAL_HOURS).
Additive only and idempotent (``IF NOT EXISTS``) like c3e7a1d5f9b2, because the shared
Supabase DB is migrated by hand.

Revision ID: d5b2e8f4a1c7
Revises: c3e7a1d5f9b2
Create Date: 2026-10-11
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5b2e8f4a1c7"
down_revision: str | Sequence[str] | None = "c3e7a1d5f9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE vehicle_user ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT false")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS demo_account_state (
            id SMALLINT PRIMARY KEY CHECK (id = 1),
            last_reset_at TIMESTAMPTZ NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS demo_account_state")
    op.execute("ALTER TABLE vehicle_user DROP COLUMN IF EXISTS is_demo")
