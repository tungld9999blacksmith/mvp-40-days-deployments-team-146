"""add workshop_owner_auth_event (FEAT-AUTH-004)

ENT-301: append-only audit log of workshop-owner sign-in / denied sign-in /
logout / session revoke. Reuses the enum types of ENT-101 ``auth_event``.

Targets PostgreSQL / Supabase. Apply with ``alembic upgrade head``.

Revision ID: d4a9b2c5e6f1
Revises: c3f8a1d2e4b7
Create Date: 2026-09-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4a9b2c5e6f1"
down_revision: str | Sequence[str] | None = "c3f8a1d2e4b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Created by b2e5d7f1a9c4 (auth_event).
auth_event_type = postgresql.ENUM(name="auth_event_type_enum", create_type=False)
auth_event_result = postgresql.ENUM(name="auth_event_result_enum", create_type=False)


def upgrade() -> None:
    op.create_table(
        "workshop_owner_auth_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", auth_event_type, nullable=False),
        sa.Column("result", auth_event_result, nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("auth_provider", sa.String(length=32), nullable=True, server_default="google.com"),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["workshop_owner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(event_type IN ('login', 'logout', 'session_revoked') AND result = 'success') OR "
            "(event_type = 'login_denied' AND result = 'denied') OR "
            "(event_type = 'session_revoke_failed' AND result = 'failed')",
            name="ck_ws_auth_event_result",
        ),
    )
    op.create_index(
        "ix_ws_auth_event_owner_created",
        "workshop_owner_auth_event",
        ["owner_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_ws_auth_event_created_at", "workshop_owner_auth_event", ["created_at"])
    op.execute("ALTER TABLE workshop_owner_auth_event ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("workshop_owner_auth_event")
