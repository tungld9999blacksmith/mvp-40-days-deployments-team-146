"""reminder channel: discord / email / sms / telegram / slack (PRD v3.4)

``reminder_channel_enum`` was ``in_app / push / sms_zalo`` with default
``in_app``. The MVP now sends every notification through Discord (BR-ENT-408);
email / sms / telegram / slack are reserved for the later channel-settings
feature (PRD appendix B, NOTI-01).

- Adds ``discord, email, sms, telegram, slack`` to the enum.
- Moves existing rows on the deprecated values to ``discord``.
- Sets the column default to ``discord``.

PostgreSQL cannot drop enum values, so ``in_app / push / sms_zalo`` stay in the
type as deprecated values (never written by the app).

Revision ID: f6c3a8d1b2e4
Revises: e5b1c7d9f2a3
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6c3a8d1b2e4"
down_revision: str | Sequence[str] | None = "e5b1c7d9f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_VALUES = ("discord", "email", "sms", "telegram", "slack")
DEPRECATED_VALUES = ("in_app", "push", "sms_zalo")


def upgrade() -> None:
    # A value added by ALTER TYPE cannot be used in the same transaction, so the
    # additions are committed first in an autocommit block.
    with op.get_context().autocommit_block():
        for value in NEW_VALUES:
            op.execute(f"ALTER TYPE reminder_channel_enum ADD VALUE IF NOT EXISTS '{value}'")

    deprecated = ", ".join(f"'{value}'" for value in DEPRECATED_VALUES)
    op.execute(f"UPDATE reminder SET channel = 'discord' WHERE channel IN ({deprecated})")
    op.execute("ALTER TABLE reminder ALTER COLUMN channel SET DEFAULT 'discord'")


def downgrade() -> None:
    # Enum values cannot be removed; map rows back to the old default instead.
    new_values = ", ".join(f"'{value}'" for value in NEW_VALUES)
    op.execute(f"UPDATE reminder SET channel = 'in_app' WHERE channel IN ({new_values})")
    op.execute("ALTER TABLE reminder ALTER COLUMN channel SET DEFAULT 'in_app'")
