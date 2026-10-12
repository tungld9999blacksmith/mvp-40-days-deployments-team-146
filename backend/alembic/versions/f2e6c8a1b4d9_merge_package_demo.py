"""Merge optimal maintenance package and current develop migrations.

Revision ID: f2e6c8a1b4d9
Revises: d5b2e8f4a1c7, e1c5a7b9d3f2
Create Date: 2026-10-11
"""

from collections.abc import Sequence

revision: str = "f2e6c8a1b4d9"
down_revision: str | Sequence[str] | None = ("d5b2e8f4a1c7", "e1c5a7b9d3f2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
