"""Auth module — domain layer (FEAT-AUTH-002).

Contains the ``AuthEvent`` audit entity (ENT-101) and its enums.

Rules:
    - No FastAPI, no Session, no Firebase SDK here.
    - Enum values are stored lowercase in the DB; the API/logs map them to
      UPPER_SNAKE_CASE via ``enum.name`` where needed.
    - ``AuthEvent`` is append-only: never UPDATE/DELETE at the application
      layer (a retention job purges rows older than 60 days).
    - Never store ``id_token`` / ``refresh_token`` here (BR-ENT-102).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum, StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy import Enum as SQLEnum
from sqlmodel import Field, SQLModel

__all__ = [
    "AuthEventType",
    "AuthEventResult",
    "AuthEvent",
]


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Persist the lowercase ``value`` of each member (not its name)."""
    return [member.value for member in enum_cls]


class AuthEventType(StrEnum):
    """Kind of authentication event recorded for audit (ENT-101)."""

    LOGIN = "login"
    LOGOUT = "logout"
    SESSION_REVOKED = "session_revoked"
    SESSION_REVOKE_FAILED = "session_revoke_failed"
    LOGIN_DENIED = "login_denied"


class AuthEventResult(StrEnum):
    """Outcome of an authentication event."""

    SUCCESS = "success"
    DENIED = "denied"
    FAILED = "failed"


class AuthEvent(SQLModel, table=True):
    """Append-only audit record of a login / logout / revoke event.

    Not a session store: it never authenticates a request, proves an active
    session or decides token lifetime. It exists purely for audit and support.
    """

    __tablename__ = "auth_event"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    user_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("vehicle_user.user_id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )

    event_type: AuthEventType = Field(
        sa_column=Column(
            SQLEnum(
                AuthEventType,
                name="auth_event_type_enum",
                values_callable=_enum_values,
            ),
            nullable=False,
        )
    )

    result: AuthEventResult = Field(
        sa_column=Column(
            SQLEnum(
                AuthEventResult,
                name="auth_event_result_enum",
                values_callable=_enum_values,
            ),
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
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            index=True,
            nullable=False,
        )
    )
