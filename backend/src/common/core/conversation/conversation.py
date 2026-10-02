"""Conversation (ENT-421): a chat thread between one vehicle owner and the agent.

Spec: ``docs/specs/entity/conversation/conversation.entity.md``. A conversation
groups its ``chat_message`` rows and is the unit for history reload, per-vehicle
listing, ownership checks and deletion (FF F4 BR-601/604/605/608). Its ``id`` is
also the LangGraph checkpointer ``thread_id``.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, func
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class Conversation(SQLModel, table=True):
    __tablename__ = "conversation"
    __table_args__ = (
        # Latest conversation of a vehicle, and listing per owner/vehicle (ENT-421 §11).
        Index(
            "ix_conversation_user_vehicle_last",
            "user_id",
            "user_vehicle_id",
            "last_message_at",
        ),
        # Retention purge sweep (BR-ENT-463).
        Index("ix_conversation_last_message_at", "last_message_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Owner (vehicle_user.user_id is an int identity PK).
    user_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("vehicle_user.user_id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    user_vehicle_id: UUID = Field(sa_column=Column(ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False))
    title: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    last_message_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )
    )


class ConversationRepository(SQLModelRepository[Conversation, UUID]):
    model = Conversation
    default_order_by = ("-last_message_at",)
