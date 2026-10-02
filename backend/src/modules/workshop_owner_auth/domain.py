"""Workshop-owner auth — domain layer (FEAT-AUTH-004).

ENT-301 ``WorkshopAuthEvent``: append-only audit log of sign-in, denied
sign-in, logout and session-revoke outcomes of a workshop owner. It is not a
session store and never holds tokens (BR-ENT-302).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

from src.common.request_context import RequestContext

__all__ = ["AuthEventType", "AuthEventResult", "WorkshopAuthEvent", "RequestContext"]


class AuthEventType(StrEnum):
    """Same values as the shared PG type ``auth_event_type_enum`` (ENT-101)."""

    LOGIN = "login"
    LOGOUT = "logout"
    SESSION_REVOKED = "session_revoked"
    SESSION_REVOKE_FAILED = "session_revoke_failed"
    LOGIN_DENIED = "login_denied"


class AuthEventResult(StrEnum):
    """Same values as the shared PG type ``auth_event_result_enum`` (ENT-101)."""

    SUCCESS = "success"
    DENIED = "denied"
    FAILED = "failed"


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class WorkshopAuthEvent(SQLModel, table=True):
    __tablename__ = "workshop_owner_auth_event"
    __table_args__ = (
        CheckConstraint(
            "(event_type IN ('login', 'logout', 'session_revoked') AND result = 'success') OR "
            "(event_type = 'login_denied' AND result = 'denied') OR "
            "(event_type = 'session_revoke_failed' AND result = 'failed')",
            name="ck_ws_auth_event_result",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_id: UUID = Field(
        sa_column=Column(ForeignKey("workshop_owner.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    event_type: AuthEventType = Field(
        sa_column=Column(
            SQLEnum(AuthEventType, name="auth_event_type_enum", values_callable=_enum_values),
            nullable=False,
        )
    )
    result: AuthEventResult = Field(
        sa_column=Column(
            SQLEnum(AuthEventResult, name="auth_event_result_enum", values_callable=_enum_values),
            nullable=False,
        )
    )
    reason: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    auth_provider: str | None = Field(
        default="google.com",
        sa_column=Column(String(32), nullable=True, server_default="google.com"),
    )
    ip_address: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    user_agent: str | None = Field(default=None, sa_column=Column(String(512), nullable=True))
    trace_id: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    )
