"""maintenance_rule: is_safety_critical

Open question 3 of docs/designs/bao-gia-hai-tang.md: which items are safety-critical now
comes from the maintenance schedule document (data/knowledge/raw/lich_bao_duong_ALL.md),
stored per rule, instead of keyword matching on booking line names. Flags are written by
``scripts/seed_maintenance_rules.py --safety-only --apply``. Additive only and idempotent
(``IF NOT EXISTS``) like a7e3c1f9d4b2, because the shared Supabase DB is migrated by hand.

Revision ID: b9d4f2a6c8e1
Revises: f8b2d6a4c1e9
Create Date: 2026-10-11
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9d4f2a6c8e1"
down_revision: str | Sequence[str] | None = "f8b2d6a4c1e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE maintenance_rule ADD COLUMN IF NOT EXISTS is_safety_critical BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE maintenance_rule DROP COLUMN IF EXISTS is_safety_critical")
