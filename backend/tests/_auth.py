"""Shared test helpers for the auth module (FEAT-AUTH-002).

Provides an in-memory SQLite session with ``vehicle_user`` + ``auth_event``
tables created, and an in-memory ``SessionRevoker`` stub so tests never touch
Celery, Redis or Firebase.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# Import models so their tables register on SQLModel.metadata.
from src.common.core.identity import vehicle_user as _vehicle_user  # noqa: F401
from src.modules.auth import domain as _auth_domain  # noqa: F401
from src.modules.auth.ports import RevokeEnqueueError

_AUTH_TABLES = [
    _vehicle_user.VehicleUser.__table__,
    _auth_domain.AuthEvent.__table__,
]


def make_session() -> Iterator[Session]:
    """Yield a fresh in-memory SQLite session with auth tables created."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine, tables=_AUTH_TABLES)
    with Session(engine) as session:
        yield session


class StubRevoker:
    """Records enqueue calls; can be told to fail (broker down)."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    def enqueue_revoke(
        self, *, uid: str, user_id: int, trace_id: str | None = None
    ) -> None:
        if self.fail:
            raise RevokeEnqueueError("stub broker down")
        self.calls.append({"uid": uid, "user_id": user_id, "trace_id": trace_id})


def make_user(session: Session, *, uid: str = "uid-1", email: str = "a@example.com"):
    from src.common.core.identity.vehicle_user import UserStatus, VehicleUser

    user = VehicleUser(
        firebase_uid=uid,
        email=email,
        email_verified=True,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
