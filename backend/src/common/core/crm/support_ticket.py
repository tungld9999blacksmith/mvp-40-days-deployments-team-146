"""ENT-413 — SupportTicket: an issue raised from a follow-up, handled by the workshop owner.

Columns and lifecycle follow ``docs/specs/entity/crm/support_ticket.entity.md``.
``user_vehicle_id`` is deliberately redundant (derivable via follow_up →
booking) for fast per-vehicle lookups; it must match the booking (BR-ENT-423).
"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.data_access import SQLModelRepository


class SupportTicketPriority(str, Enum):
    NORMAL = "normal"
    HIGH = "high"


class SupportTicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class SupportTicket(SQLModel, table=True):
    __tablename__ = "support_ticket"
    __table_args__ = (
        CheckConstraint(
            "status <> 'resolved' OR resolved_at IS NOT NULL", name="ck_support_ticket_resolved_at"
        ),
        CheckConstraint(
            "status = 'open' OR assigned_to IS NOT NULL", name="ck_support_ticket_assigned"
        ),
        CheckConstraint(
            "status <> 'resolved' OR resolution_note IS NOT NULL",
            name="ck_support_ticket_resolution",
        ),
        CheckConstraint(
            "status <> 'in_progress' OR started_at IS NOT NULL", name="ck_support_ticket_started"
        ),
        UniqueConstraint("follow_up_id", name="ux_support_ticket_follow_up"),
        Index("ix_support_ticket_assignee_status", "assigned_to", "status"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    follow_up_id: UUID = Field(
        sa_column=Column(
            ForeignKey("follow_up.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    user_vehicle_id: UUID = Field(
        sa_column=Column(
            ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    # Owner of the workshop that performed the booking (BR-ENT-424).
    assigned_to: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("workshop_owner.id", ondelete="SET NULL"), nullable=True),
    )
    issue_summary: str = Field(sa_column=Column(Text, nullable=False))
    status: SupportTicketStatus = Field(
        default=SupportTicketStatus.OPEN,
        sa_column=Column(
            SQLEnum(
                SupportTicketStatus, name="support_ticket_status_enum", values_callable=_enum_values
            ),
            nullable=False,
            server_default="open",
        ),
    )
    resolved_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # us-041 extension.
    priority: SupportTicketPriority = Field(
        default=SupportTicketPriority.NORMAL,
        sa_column=Column(
            SQLEnum(
                SupportTicketPriority,
                name="support_ticket_priority_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
            server_default="normal",
        ),
    )
    # Shown to the vehicle owner; required once resolved (BR-910).
    resolution_note: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
        )
    )


class SupportTicketRepository(SQLModelRepository[SupportTicket, UUID]):
    model = SupportTicket
