"""Transactional outbox table (infrastructure/outbox).

Revision ID: 12b82210986d
Revises: d8f1b3a5c7e9
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "12b82210986d"
down_revision = "d8f1b3a5c7e9"
branch_labels = None
depends_on = None


def upgrade():
    # Freeze the schema here so later model changes cannot change this revision.
    op.create_table(
        "outbox_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("aggregate_type", sa.String(64)),
        sa.Column("aggregate_id", sa.String(64)),
        sa.Column("dedup_key", sa.String(200), unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("locked_by", sa.String(100)),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("last_error", sa.String(100)),
        sa.Column("trace_id", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_outbox_event_event_type", "outbox_event", ["event_type"])
    op.create_index("ix_outbox_event_status_available_at", "outbox_event", ["status", "available_at"])
    op.create_index("ix_outbox_event_aggregate", "outbox_event", ["aggregate_type", "aggregate_id"])
    # Same policy as the other app tables: no anon-key access, only the backend.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE outbox_event ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("outbox_event")
