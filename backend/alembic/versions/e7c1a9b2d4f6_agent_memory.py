"""Durable agent memory, explicit consent and cascade-safe cleanup outbox."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "e7c1a9b2d4f6"
down_revision = "c6f2a8d4e9b1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversation_summary",
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversation.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("summary_json", pg.JSONB(), nullable=False),
        sa.Column("source_message_ids", pg.JSONB(), nullable=False),
        sa.Column("covered_until_seq", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("compacted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_memory_cleanup",
        sa.Column("conversation_id", sa.Uuid(), primary_key=True),
        sa.Column("vector_ids", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(100)),
    )
    op.create_table(
        "agent_memory_setting",
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "agent_user_memory",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(40), nullable=False),
        sa.Column("memory_key", sa.String(64), nullable=False),
        sa.Column("value_json", pg.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "consent_message_id", sa.Uuid(), sa.ForeignKey("chat_message.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("scope_type IN ('account', 'vehicle')", name="ck_agent_memory_scope"),
        sa.CheckConstraint("status IN ('active', 'revoked', 'expired')", name="ck_agent_memory_status"),
        sa.CheckConstraint(
            "memory_key IN ('preferred_service_window', 'preferred_workshop_id', 'cost_display_preference')",
            name="ck_agent_memory_key",
        ),
    )
    op.create_index("ix_agent_user_memory_user_id", "agent_user_memory", ["user_id"])
    op.create_index(
        "ux_agent_memory_active",
        "agent_user_memory",
        ["user_id", "scope_type", "scope_id", "memory_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "agent_memory_source",
        sa.Column("memory_id", sa.Uuid(), sa.ForeignKey("agent_user_memory.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "source_message_id", sa.Uuid(), sa.ForeignKey("chat_message.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "source_conversation_id", sa.Uuid(), sa.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
        ),
    )
    # Covers account/vehicle FK cascades and any non-HTTP delete path, too.
    op.execute("""
        CREATE FUNCTION enqueue_agent_memory_cleanup() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            INSERT INTO agent_memory_cleanup (conversation_id, vector_ids)
            SELECT OLD.id, COALESCE(jsonb_agg(id::text), '[]'::jsonb)
            FROM chat_message WHERE conversation_id = OLD.id
            ON CONFLICT (conversation_id) DO UPDATE
              SET vector_ids = agent_memory_cleanup.vector_ids || EXCLUDED.vector_ids;
            RETURN OLD;
        END $$;
        CREATE TRIGGER conversation_memory_cleanup BEFORE DELETE ON conversation
        FOR EACH ROW EXECUTE FUNCTION enqueue_agent_memory_cleanup();
    """)
    # Memory is available exclusively through the backend's Firebase owner guard.
    # Supabase default grants must not expose these tables through PostgREST.
    for name in (
        "conversation_summary", "agent_memory_cleanup", "agent_memory_setting",
        "agent_user_memory", "agent_memory_source",
    ):
        op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.execute("DROP TRIGGER conversation_memory_cleanup ON conversation")
    op.execute("DROP FUNCTION enqueue_agent_memory_cleanup()")
    for name in (
        "agent_memory_source",
        "agent_user_memory",
        "agent_memory_setting",
        "agent_memory_cleanup",
        "conversation_summary",
    ):
        op.drop_table(name)
