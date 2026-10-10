"""follow_up.safety_flag: keep the safety advice decided at answer time (us-041 BR-908, AI-007).

Before this column the API re-derived the safety advice from the keyword rules
on every read, so a safety sign found only by the LLM was lost on reload.
Existing rows stay NULL and keep the keyword-rule behaviour.

Revision ID: e8c4b1d7a2f5
Revises: e7a9c2b4d6f8
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8c4b1d7a2f5"
down_revision: str | Sequence[str] | None = "e7a9c2b4d6f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("follow_up", sa.Column("safety_flag", sa.Boolean(), nullable=True))
    op.create_check_constraint("ck_follow_up_safety_issue", "follow_up", "safety_flag IS NOT TRUE OR has_issue")


def downgrade() -> None:
    op.drop_constraint("ck_follow_up_safety_issue", "follow_up", type_="check")
    op.drop_column("follow_up", "safety_flag")
