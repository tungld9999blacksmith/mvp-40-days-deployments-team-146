from collections.abc import Generator

from sqlmodel import Session, create_engine

from ...config import get_settings

settings = get_settings()
_url = settings.sqlalchemy_database_url
# Postgres only: a stalled pooler (Supavisor queue, half-open TCP) raises instead of blocking a request forever.
_connect_args = (
    {
        "connect_timeout": settings.database_connect_timeout_seconds,
        "keepalives": 1,
        "keepalives_idle": settings.database_keepalive_idle_seconds,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    }
    if _url.startswith("postgresql")
    else {}
)
engine = create_engine(_url, pool_pre_ping=True, connect_args=_connect_args)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def end_read_transaction(session: Session) -> None:
    """Return the pooled connection after reads; rows already loaded stay usable.

    Async paths must call this before awaiting Redis (locks, tokens): a transaction
    left open there pins a Supavisor connection "idle in transaction" (the 2026-10-06
    outage). ``rollback()`` would expire every loaded object, and the next attribute
    read on the event loop would open a new transaction.
    """
    if not session.in_transaction():
        return
    if session.new or session.dirty or session.deleted:
        raise RuntimeError("end_read_transaction() would commit pending writes")
    expire, session.expire_on_commit = session.expire_on_commit, False
    try:
        session.commit()
    finally:
        session.expire_on_commit = expire


def run_then_release(session: Session, fn, /, *args, **kwargs):
    """``fn(*args, **kwargs)``, then end the transaction (rolled back if ``fn`` raised).

    Meant for ``run_in_threadpool`` before a Redis await; see ``end_read_transaction``.
    """
    try:
        result = fn(*args, **kwargs)
    except BaseException:
        session.rollback()
        raise
    end_read_transaction(session)
    return result
