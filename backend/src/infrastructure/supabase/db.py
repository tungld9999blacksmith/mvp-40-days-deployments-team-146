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
