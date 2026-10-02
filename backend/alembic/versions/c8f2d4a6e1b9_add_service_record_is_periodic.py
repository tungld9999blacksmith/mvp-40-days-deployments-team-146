"""add vehicle_service_record.is_periodic (FEAT-VEH-001, us-017 Q-304)

Flags a service record as periodic maintenance (true) or a repair outside the
periodic schedule (false). Only periodic records are used as the baseline of
the maintenance due status.

Revision ID: c8f2d4a6e1b9
Revises: b7e1c2f34d58
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8f2d4a6e1b9"
down_revision: str | Sequence[str] | None = "b7e1c2f34d58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "vehicle_service_record",
        sa.Column("is_periodic", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("vehicle_service_record", "is_periodic")
