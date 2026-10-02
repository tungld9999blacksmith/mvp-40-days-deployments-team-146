"""Database for the mock EV system — SQLite, in-memory or file-backed.

SQLModel (SQLAlchemy + Pydantic) defines each model once for both ORM and validation.

Provides:
- engine: in-memory SQLite by default (fresh data on every start). Set
  ``MOCK_DB_PATH`` to a file path (e.g. on a Docker volume) to keep the data
  across restarts and container re-creation.
- get_session: FastAPI dependency returning a Session.
- init_db: create the tables and load the startup data (dump or built-in seed).
"""

import logging
import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# uvicorn configures this logger, so startup messages show up in `docker logs`.
logger = logging.getLogger("uvicorn.error")

# Empty MOCK_DB_PATH → in-memory SQLite (fresh data on every restart).
# StaticPool makes every connection share one SQLite connection (required in-memory).
DB_PATH = os.getenv("MOCK_DB_PATH", "").strip()
if DB_PATH:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_PATH}" if DB_PATH else "sqlite://"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency — cung cấp DB session cho mỗi request."""
    with Session(engine) as session:
        yield session


def init_db(reset: bool = False) -> None:
    """Tạo tất cả bảng và nạp seed data.

    Gọi một lần trong lifespan của FastAPI app (xem main.py).
    Seed data cố định (deterministic) để test lặp lại được.

    With a file-backed DB (``MOCK_DB_PATH``) that already holds data, the data is
    kept unless ``reset`` is true (``POST /admin/reset``).
    """
    # Import models để SQLModel biết tất cả bảng
    from . import models as _models  # noqa: F401

    # Reset trước khi seed: engine in-memory sống suốt process, nên app được
    # khởi động lại (vd nhiều TestClient trong cùng phiên pytest) sẽ không
    # seed trùng khoá chính.
    # Only touch the mock's own tables: SQLModel.metadata is process-wide, so when
    # the mock shares a process with the EV Care app (e.g. pytest) it also holds
    # the app's PostgreSQL-only tables (JSONB, pgvector, regex CHECKs).
    mock_tables = [
        obj.__table__
        for obj in vars(_models).values()
        if isinstance(obj, type) and issubclass(obj, SQLModel) and hasattr(obj, "__table__")
    ]
    if DB_PATH and not reset and _has_data(mock_tables):
        # Add tables introduced since the file was created; existing ones are untouched.
        SQLModel.metadata.create_all(engine, tables=mock_tables)
        logger.info("Mock database kept from %s (POST /admin/reset to reload)", DB_PATH)
    else:
        _load_startup_data(mock_tables)

    # Owners + vehicles for the Gmail accounts in MOCK_DEV_OWNER_EMAILS.
    with Session(engine) as session:
        from .dev_accounts import ensure_dev_owners

        ensure_dev_owners(session)


def _has_data(tables: list) -> bool:
    """True when the file-backed DB already has the mock tables (data from a previous run)."""
    existing = set(inspect(engine).get_table_names())
    return any(table.name in existing for table in tables)


def _load_startup_data(mock_tables: list) -> None:
    """Drop the mock tables and load MOCK_SEED_DUMP, or the built-in seed when it is empty."""
    SQLModel.metadata.drop_all(engine, tables=mock_tables)

    dump = os.getenv("MOCK_SEED_DUMP", "").strip()
    if dump:
        _load_dump(Path(dump))
    else:
        SQLModel.metadata.create_all(engine, tables=mock_tables)
        with Session(engine) as session:
            from .seed import seed_all

            seed_all(session)


def _load_dump(path: Path) -> None:
    """Load a SQLite SQL dump (``GET /admin/dump``) instead of the built-in seed.

    The dump holds both the schema and the data, so the tables must be dropped first.
    """
    if not path.is_file():
        raise RuntimeError(f"MOCK_SEED_DUMP={path} does not exist")
    raw = engine.raw_connection()
    try:
        raw.driver_connection.executescript(path.read_text(encoding="utf-8"))
    finally:
        raw.close()
    logger.info("Mock database loaded from dump %s", path)
