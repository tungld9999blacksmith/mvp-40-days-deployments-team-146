"""booking_line: decisions the workshop records by phone, and the owner's dispute

TODOS P2 "Kênh ghi quyết định phát sinh qua điện thoại" (concern R2-2). Additive only and
idempotent (``IF NOT EXISTS``) like d2a8c6e4f1b7, because the shared Supabase DB is
migrated by hand.

Revision ID: a7e3c1f9d4b2
Revises: d2a8c6e4f1b7
Create Date: 2026-10-10
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7e3c1f9d4b2"
down_revision: str | Sequence[str] | None = "d2a8c6e4f1b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE booking_line ADD COLUMN IF NOT EXISTS decided_via VARCHAR(10)")
    op.execute("ALTER TABLE booking_line ADD COLUMN IF NOT EXISTS phone_confirmed_by VARCHAR(100)")
    op.execute(
        "ALTER TABLE booking_line ADD COLUMN IF NOT EXISTS recorded_by UUID "
        "REFERENCES workshop_owner(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE booking_line ADD COLUMN IF NOT EXISTS disputed_at TIMESTAMPTZ")
    # Decisions made before this column existed were all taken on the app.
    op.execute("UPDATE booking_line SET decided_via = 'APP' WHERE decided_at IS NOT NULL AND decided_via IS NULL")
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE booking_line ADD CONSTRAINT ck_booking_line_decided_via
                CHECK (decided_via IS NULL OR decided_via IN ('APP', 'PHONE'));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE booking_line ADD CONSTRAINT ck_booking_line_phone_confirmer
                CHECK (decided_via IS NULL OR decided_via <> 'PHONE' OR phone_confirmed_by IS NOT NULL);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE booking_line DROP CONSTRAINT IF EXISTS ck_booking_line_phone_confirmer")
    op.execute("ALTER TABLE booking_line DROP CONSTRAINT IF EXISTS ck_booking_line_decided_via")
    op.execute("ALTER TABLE booking_line DROP COLUMN IF EXISTS disputed_at")
    op.execute("ALTER TABLE booking_line DROP COLUMN IF EXISTS recorded_by")
    op.execute("ALTER TABLE booking_line DROP COLUMN IF EXISTS phone_confirmed_by")
    op.execute("ALTER TABLE booking_line DROP COLUMN IF EXISTS decided_via")
