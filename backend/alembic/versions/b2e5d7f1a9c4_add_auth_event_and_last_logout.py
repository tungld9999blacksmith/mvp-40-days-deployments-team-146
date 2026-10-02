"""add auth_event table and vehicle_user.last_logout_at (FEAT-AUTH-002)

Adds ENT-101 ``auth_event`` (append-only auth audit log, retention 60 days) and
the ``last_logout_at`` column on ``vehicle_user``.

Targets PostgreSQL / Supabase. Apply with ``alembic upgrade head``.

Revision ID: b2e5d7f1a9c4
Revises: a1f4c2d3e5b6
Create Date: 2026-09-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Enum types are created exactly once via .create(checkfirst=True) in upgrade();
# create_type=False stops create_table/add_column from emitting a 2nd CREATE TYPE.

# revision identifiers, used by Alembic.
revision: str = "b2e5d7f1a9c4"
down_revision: Union[str, Sequence[str], None] = "a1f4c2d3e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


auth_event_type = postgresql.ENUM(
    "login",
    "logout",
    "session_revoked",
    "session_revoke_failed",
    "login_denied",
    name="auth_event_type_enum",
    create_type=False,
)
auth_event_result = postgresql.ENUM("success", "denied", "failed", name="auth_event_result_enum", create_type=False)

_ALL_ENUMS = [auth_event_type, auth_event_result]


def upgrade() -> None:
    bind = op.get_bind()
    for enum in _ALL_ENUMS:
        enum.create(bind, checkfirst=True)

    # ── vehicle_user: active-logout timestamp ─────────────────────────
    op.add_column(
        "vehicle_user",
        sa.Column("last_logout_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── auth_event (ENT-101) ──────────────────────────────────────────
    op.create_table(
        "auth_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", auth_event_type, nullable=False),
        sa.Column("result", auth_event_result, nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column(
            "auth_provider",
            sa.String(length=32),
            nullable=True,
            server_default="google.com",
        ),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["vehicle_user.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Audit lookup: a user's auth history, newest first.
    op.create_index("ix_auth_event_user_created", "auth_event", ["user_id", "created_at"])
    # Retention purge scans by created_at.
    op.create_index(op.f("ix_auth_event_created_at"), "auth_event", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_event_created_at"), table_name="auth_event")
    op.drop_index("ix_auth_event_user_created", table_name="auth_event")
    op.drop_table("auth_event")
    op.drop_column("vehicle_user", "last_logout_at")

    bind = op.get_bind()
    for enum in reversed(_ALL_ENUMS):
        enum.drop(bind, checkfirst=True)
