"""ChatMessage (ENT-422): one turn of a conversation, persisted append-only.

Spec: ``docs/specs/entity/conversation/chat_message.entity.md``. A message is a
user turn, a complete assistant turn, or a tool-call result. Rows are immutable
after insert; ordering and keyset pagination use ``seq`` (a DB identity), not
``created_at`` (BR-ENT-468). Assistant turns carry their evidence inline
(``citations`` snapshot, ``tool_calls``, ``refs``, ``trace_id``) so it survives
document re-ingest (BR-ENT-603/609).
"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


# Generated tsvector for keyword search (BR-ENT-467). ``immutable_unaccent`` is
# created by the migration so search is accent- and case-insensitive (BR-615).
_SEARCH_EXPR = "to_tsvector('simple', immutable_unaccent(coalesce(content, '')))"


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_message"
    __table_args__ = (
        # Fetch a thread newest-first and page it by seq (ENT-422 §11).
        Index("ix_chat_message_conversation_seq", "conversation_id", "seq"),
        # Keyword search (GIN over the generated tsvector).
        Index("ix_chat_message_search", "search_vector", postgresql_using="gin"),
        # Anonymised export sweep by time.
        Index("ix_chat_message_created_at", "created_at"),
        # Idempotent resend: one user row per (conversation, client_message_id) (BR-ENT-465).
        Index(
            "ux_chat_message_client_id",
            "conversation_id",
            "client_message_id",
            unique=True,
            postgresql_where=text("role = 'user' AND client_message_id IS NOT NULL"),
        ),
        # Role-shaped constraints (BR-ENT-466).
        CheckConstraint(
            "role <> 'user' OR (length(content) > 0 "
            "AND jsonb_array_length(citations) = 0 "
            "AND jsonb_array_length(tool_calls) = 0)",
            name="ck_chat_message_user_shape",
        ),
        CheckConstraint(
            "role <> 'tool' OR (tool_call_id IS NOT NULL AND tool_name IS NOT NULL)",
            name="ck_chat_message_tool_shape",
        ),
        CheckConstraint(
            "role <> 'assistant' OR (length(content) > 0 OR jsonb_array_length(tool_calls) > 0)",
            name="ck_chat_message_assistant_shape",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    conversation_id: UUID = Field(
        sa_column=Column(
            ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
        )
    )
    # Global monotonic order; larger = newer. Assigned by the DB.
    seq: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(always=True), unique=True, nullable=False),
    )
    role: MessageRole = Field(
        sa_column=Column(
            SQLEnum(MessageRole, name="chat_message_role_enum", values_callable=_enum_values),
            nullable=False,
        )
    )
    content: str = Field(sa_column=Column(Text, nullable=False, server_default=""))
    # Client-generated id, present only on user turns; backs idempotent resend.
    client_message_id: UUID | None = Field(
        default=None, sa_column=Column(Uuid, nullable=True)
    )
    citations: list = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    tool_calls: list = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default="[]"),
    )
    tool_call_id: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    tool_name: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    refs: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
    card: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    intent: str | None = Field(default=None, sa_column=Column(String(50), nullable=True))
    agent_run_id: UUID | None = Field(default=None, sa_column=Column(Uuid, nullable=True))
    trace_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    # Generated keyword-search vector (read-only; DB computes it).
    search_vector: str | None = Field(
        default=None,
        sa_column=Column(TSVECTOR, Computed(_SEARCH_EXPR, persisted=True), nullable=True),
    )
    # Set once indexed into the vector store (optional feature, BR-ENT-469).
    embedded: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), nullable=False
        )
    )


class ChatMessageRepository(SQLModelRepository[ChatMessage, UUID]):
    model = ChatMessage
    default_order_by = ("seq",)
