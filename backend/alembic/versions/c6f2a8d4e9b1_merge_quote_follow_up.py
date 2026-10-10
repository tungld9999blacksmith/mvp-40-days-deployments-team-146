"""Merge workshop quotes and the follow-up safety flag.

Revision ID: c6f2a8d4e9b1
Revises: b4e6f8a1c3d5, e8c4b1d7a2f5
Create Date: 2026-10-07
"""

from collections.abc import Sequence

revision: str = "c6f2a8d4e9b1"
down_revision: str | Sequence[str] | None = ("b4e6f8a1c3d5", "e8c4b1d7a2f5")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
