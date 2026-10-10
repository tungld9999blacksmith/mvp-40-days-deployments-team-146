"""two-tier booking pricing: booking.pricing_flow, booking_line, booking_line_photo

docs/designs/bao-gia-hai-tang.md (D3, D7). Additive only and idempotent
(``IF NOT EXISTS``) because the shared Supabase DB may already have parts of it;
``quote`` / ``quote_item`` and ``quote_status_enum`` are untouched (legacy flow).

Revision ID: d2a8c6e4f1b7
Revises: c6f2a8d4e9b1
Create Date: 2026-10-09
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2a8c6e4f1b7"
down_revision: str | Sequence[str] | None = "c6f2a8d4e9b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE booking ADD COLUMN IF NOT EXISTS pricing_flow VARCHAR(16) NOT NULL DEFAULT 'legacy'")
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE booking ADD CONSTRAINT ck_booking_pricing_flow
                CHECK (pricing_flow IN ('legacy', 'two_tier'));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS booking_line (
            id UUID PRIMARY KEY,
            booking_id UUID NOT NULL REFERENCES booking(id) ON DELETE CASCADE,
            kind VARCHAR(10) NOT NULL,
            line_status VARCHAR(20) NOT NULL,
            item_code VARCHAR(50),
            item_name VARCHAR(200) NOT NULL,
            maintenance_rule_id UUID REFERENCES maintenance_rule(id) ON DELETE SET NULL,
            service_price_id UUID REFERENCES service_price(id) ON DELETE SET NULL,
            price_source VARCHAR(20),
            unit_price NUMERIC(12, 2) NOT NULL,
            confirmed_price NUMERIC(12, 2),
            is_covered_by_warranty BOOLEAN NOT NULL DEFAULT false,
            is_safety_critical BOOLEAN NOT NULL DEFAULT false,
            reason TEXT,
            proposed_by UUID REFERENCES workshop_owner(id) ON DELETE SET NULL,
            confirmed_by UUID REFERENCES workshop_owner(id) ON DELETE SET NULL,
            confirmed_at TIMESTAMPTZ,
            decided_by INTEGER REFERENCES vehicle_user(user_id) ON DELETE SET NULL,
            decided_at TIMESTAMPTZ,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_booking_line_kind CHECK (kind IN ('PACKAGE', 'EXTRA')),
            CONSTRAINT ck_booking_line_status CHECK (
                line_status IN ('PENDING_CONFIRM', 'CONFIRMED', 'PROPOSED', 'APPROVED', 'DECLINED', 'WITHDRAWN')
            ),
            CONSTRAINT ck_booking_line_unit_price CHECK (unit_price >= 0),
            CONSTRAINT ck_booking_line_confirmed_price CHECK (confirmed_price IS NULL OR confirmed_price >= 0),
            CONSTRAINT ck_booking_line_version CHECK (version >= 1),
            CONSTRAINT ck_booking_line_extra_status CHECK (
                kind = 'PACKAGE' OR line_status IN ('PROPOSED', 'APPROVED', 'DECLINED', 'WITHDRAWN')
            )
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_booking_line_booking_id ON booking_line (booking_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS booking_line_photo (
            id UUID PRIMARY KEY,
            line_id UUID NOT NULL REFERENCES booking_line(id) ON DELETE CASCADE,
            storage_key VARCHAR(300) NOT NULL UNIQUE,
            content_type VARCHAR(50) NOT NULL,
            size_bytes INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_booking_line_photo_size CHECK (size_bytes > 0)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_booking_line_photo_line_id ON booking_line_photo (line_id)")

    # Supabase: block PostgREST access with the anon key (no policies).
    for table in ("booking_line", "booking_line_photo"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS booking_line_photo")
    op.execute("DROP TABLE IF EXISTS booking_line")
    op.execute("ALTER TABLE booking DROP CONSTRAINT IF EXISTS ck_booking_pricing_flow")
    op.execute("ALTER TABLE booking DROP COLUMN IF EXISTS pricing_flow")
