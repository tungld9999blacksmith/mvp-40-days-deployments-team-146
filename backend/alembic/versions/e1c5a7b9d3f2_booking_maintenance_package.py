"""Persist the optimizer package selected for a booking.

Revision ID: e1c5a7b9d3f2
Revises: d2a8c6e4f1b7
Create Date: 2026-10-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e1c5a7b9d3f2"
down_revision: str | Sequence[str] | None = "d2a8c6e4f1b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE booking ADD COLUMN IF NOT EXISTS maintenance_package_code VARCHAR(20)")
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE booking ADD CONSTRAINT ck_booking_maintenance_package_code
                CHECK (maintenance_package_code IS NULL OR maintenance_package_code IN ('ESSENTIAL', 'BALANCED', 'COMPREHENSIVE'));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE booking DROP CONSTRAINT IF EXISTS ck_booking_maintenance_package_code")
    op.execute("ALTER TABLE booking DROP COLUMN IF EXISTS maintenance_package_code")
