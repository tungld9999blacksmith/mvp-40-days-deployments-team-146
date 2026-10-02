"""add conversation, chat_message and generic vector_embedding tables

Chat backbone + standardized vector store (US-025, docs/specs/entity/conversation/**):
    - ``conversation`` (ENT-421) — a chat thread owned by a vehicle owner, bound
      to one vehicle; its id is also the LangGraph checkpointer thread id.
    - ``chat_message`` (ENT-422) — append-only turns (user / assistant / tool);
      ordered by an identity ``seq``; assistant turns carry citations/tool_calls
      inline; a generated ``search_vector`` (accent-insensitive) backs keyword
      search.
    - ``vector_embedding`` (ENT-423) — the generic pgvector table behind the
      ``VectorStore`` interface, cosine HNSW index.
    - ``booking``/``quote`` gain ``source_message_id`` → ``chat_message`` so a
      record created from chat traces back to the confirming message (AC-F4-06).

Needs the ``vector`` and ``unaccent`` extensions. Apply with ``alembic upgrade head``.

Revision ID: b7e1c2f34d58
Revises: a7d2e9c4f1b3
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b7e1c2f34d58"
down_revision: str | Sequence[str] | None = "a7d2e9c4f1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024

chat_message_role = postgresql.ENUM("user", "assistant", "tool", name="chat_message_role_enum", create_type=False)

_SEARCH_EXPR = "to_tsvector('simple', immutable_unaccent(coalesce(content, '')))"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    # IMMUTABLE wrapper so unaccent can be used in a generated column / index.
    op.execute(
        "CREATE OR REPLACE FUNCTION immutable_unaccent(text) RETURNS text "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS "
        "$$ SELECT unaccent('unaccent', $1) $$"
    )
    chat_message_role.create(op.get_bind(), checkfirst=True)

    # ── conversation (ENT-421) ────────────────────────────────────────
    op.create_table(
        "conversation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["vehicle_user.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_vehicle_id"], ["user_vehicle.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_user_vehicle_last",
        "conversation",
        ["user_id", "user_vehicle_id", "last_message_at"],
    )
    op.create_index("ix_conversation_last_message_at", "conversation", ["last_message_at"])

    # ── chat_message (ENT-422, append-only) ───────────────────────────
    op.create_table(
        "chat_message",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("role", chat_message_role, nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=True),
        sa.Column("citations", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("tool_calls", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("tool_call_id", sa.String(length=64), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=True),
        sa.Column("refs", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("card", postgresql.JSONB(), nullable=True),
        sa.Column("intent", sa.String(length=50), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(_SEARCH_EXPR, persisted=True),
            nullable=True,
        ),
        sa.Column("embedded", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seq", name="uq_chat_message_seq"),
        sa.CheckConstraint(
            "role <> 'user' OR (length(content) > 0 "
            "AND jsonb_array_length(citations) = 0 "
            "AND jsonb_array_length(tool_calls) = 0)",
            name="ck_chat_message_user_shape",
        ),
        sa.CheckConstraint(
            "role <> 'tool' OR (tool_call_id IS NOT NULL AND tool_name IS NOT NULL)",
            name="ck_chat_message_tool_shape",
        ),
        sa.CheckConstraint(
            "role <> 'assistant' OR (length(content) > 0 OR jsonb_array_length(tool_calls) > 0)",
            name="ck_chat_message_assistant_shape",
        ),
    )
    op.create_index("ix_chat_message_conversation_seq", "chat_message", ["conversation_id", "seq"])
    op.create_index("ix_chat_message_created_at", "chat_message", ["created_at"])
    op.create_index("ix_chat_message_search", "chat_message", ["search_vector"], postgresql_using="gin")
    op.create_index(
        "ux_chat_message_client_id",
        "chat_message",
        ["conversation_id", "client_message_id"],
        unique=True,
        postgresql_where=sa.text("role = 'user' AND client_message_id IS NOT NULL"),
    )

    # ── vector_embedding (generic pgvector store, ENT-423) ────────────
    op.create_table(
        "vector_embedding",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("collection", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vector_embedding_collection", "vector_embedding", ["collection"])
    op.create_index(
        "ix_vector_embedding_hnsw",
        "vector_embedding",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # ── booking / quote → chat_message (AC-F4-06, BR-ENT-460) ─────────
    op.add_column("booking", sa.Column("source_message_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_booking_source_message",
        "booking",
        "chat_message",
        ["source_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("quote", sa.Column("source_message_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_quote_source_message",
        "quote",
        "chat_message",
        ["source_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_quote_source_message", "quote", type_="foreignkey")
    op.drop_column("quote", "source_message_id")
    op.drop_constraint("fk_booking_source_message", "booking", type_="foreignkey")
    op.drop_column("booking", "source_message_id")

    op.drop_index("ix_vector_embedding_hnsw", table_name="vector_embedding")
    op.drop_index("ix_vector_embedding_collection", table_name="vector_embedding")
    op.drop_table("vector_embedding")

    op.drop_index("ux_chat_message_client_id", table_name="chat_message")
    op.drop_index("ix_chat_message_search", table_name="chat_message")
    op.drop_index("ix_chat_message_created_at", table_name="chat_message")
    op.drop_index("ix_chat_message_conversation_seq", table_name="chat_message")
    op.drop_table("chat_message")

    op.drop_index("ix_conversation_last_message_at", table_name="conversation")
    op.drop_index("ix_conversation_user_vehicle_last", table_name="conversation")
    op.drop_table("conversation")

    chat_message_role.drop(op.get_bind(), checkfirst=True)
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
    # The ``vector`` and ``unaccent`` extensions are left installed.
