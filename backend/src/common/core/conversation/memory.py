"""Durable summaries, explicit preferences and deletion outbox."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


def now() -> datetime:
    return datetime.now(UTC)


class ConversationSummary(SQLModel, table=True):
    __tablename__ = "conversation_summary"
    conversation_id: UUID = Field(sa_column=Column(ForeignKey("conversation.id", ondelete="CASCADE"), primary_key=True))
    summary_json: dict = Field(default_factory=dict, sa_column=Column(JSON_TYPE, nullable=False))
    source_message_ids: list = Field(default_factory=list, sa_column=Column(JSON_TYPE, nullable=False))
    covered_until_seq: int = Field(default=0, sa_column=Column(BigInteger, nullable=False))
    version: int = 1
    schema_version: int = 1
    model: str = "extractive-v1"
    prompt_version: str = "user-quotes-v1"
    compacted: bool = False
    updated_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False))


class MemoryCleanup(SQLModel, table=True):
    """No FK to conversation: this outbox must survive cascade deletion."""

    __tablename__ = "agent_memory_cleanup"
    conversation_id: UUID = Field(primary_key=True)
    vector_ids: list = Field(default_factory=list, sa_column=Column(JSON_TYPE, nullable=False))
    attempts: int = 0
    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False))
    last_attempt_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    # Error class only: exception strings can contain credentials or chat text.
    last_error: str | None = Field(default=None, sa_column=Column(String(100)))


class AgentMemorySetting(SQLModel, table=True):
    __tablename__ = "agent_memory_setting"
    user_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), primary_key=True)
    )
    enabled: bool = True


class AgentUserMemory(SQLModel, table=True):
    __tablename__ = "agent_user_memory"
    __table_args__ = (
        CheckConstraint("scope_type IN ('account', 'vehicle')", name="ck_agent_memory_scope"),
        CheckConstraint("status IN ('active', 'revoked', 'expired')", name="ck_agent_memory_status"),
        CheckConstraint(
            "memory_key IN ('preferred_service_window', 'preferred_workshop_id', 'cost_display_preference')",
            name="ck_agent_memory_key",
        ),
        Index(
            "ux_agent_memory_active",
            "user_id",
            "scope_type",
            "scope_id",
            "memory_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False, index=True)
    )
    scope_type: str = Field(sa_column=Column(String(16), nullable=False))
    scope_id: str = Field(sa_column=Column(String(40), nullable=False))
    memory_key: str = Field(sa_column=Column(String(64), nullable=False))
    value_json: dict = Field(sa_column=Column(JSON_TYPE, nullable=False))
    status: str = Field(default="active", sa_column=Column(String(16), nullable=False))
    consent_message_id: UUID = Field(
        sa_column=Column(ForeignKey("chat_message.id", ondelete="CASCADE"), nullable=False)
    )
    consented_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False))
    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    version: int = 1


class AgentMemorySource(SQLModel, table=True):
    __tablename__ = "agent_memory_source"
    memory_id: UUID = Field(sa_column=Column(ForeignKey("agent_user_memory.id", ondelete="CASCADE"), primary_key=True))
    source_message_id: UUID = Field(
        sa_column=Column(ForeignKey("chat_message.id", ondelete="CASCADE"), primary_key=True)
    )
    source_conversation_id: UUID = Field(
        sa_column=Column(ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False)
    )
