"""Opt-in PostgreSQL checkpoint/migration tests, exclusively in an isolated schema."""

import asyncio
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4

import psycopg
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from src.agents.checkpoint import selector_loop_factory
from src.agents.graph import build_graph
from tests.test_agents.test_checkpoint_history import FakeChat

pytestmark = pytest.mark.staging


@pytest.fixture
def isolated_postgres():
    url = os.getenv("MEMORY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("MEMORY_TEST_DATABASE_URL is required; never use the repository .env")
    parsed = make_url(url)
    if parsed.host not in ("127.0.0.1", "localhost") or parsed.database != "memory_test" or parsed.port != 65432:
        pytest.fail("Use only the dedicated local memory_test database on port 65432")
    schema = "memory_test_" + uuid4().hex
    dsn = parsed.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    engine = create_engine(
        parsed.set(drivername="postgresql+psycopg"), connect_args={"options": f"-csearch_path={schema}"}
    )
    with engine.begin() as connection:
        # Only the FK targets needed to verify the new migration; no production schema.
        connection.exec_driver_sql("CREATE TABLE vehicle_user (user_id bigint PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE user_vehicle (id uuid PRIMARY KEY, user_id bigint REFERENCES vehicle_user ON DELETE CASCADE)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE conversation (id uuid PRIMARY KEY, user_id bigint REFERENCES vehicle_user ON DELETE CASCADE, user_vehicle_id uuid REFERENCES user_vehicle ON DELETE CASCADE)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE chat_message (id uuid PRIMARY KEY, conversation_id uuid REFERENCES conversation ON DELETE CASCADE, embedded boolean NOT NULL DEFAULT false)"
        )
        path = Path(__file__).resolve().parents[2] / "alembic/versions/e7c1a9b2d4f6_agent_memory.py"
        spec = importlib.util.spec_from_file_location("memory_migration_test", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
    saver_dsn = (
        make_url(dsn).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    )
    yield engine, saver_dsn, schema
    engine.dispose()
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_cascade_delete_enqueues_all_vector_ids_and_revokes_memory(isolated_postgres):
    engine, _, _ = isolated_postgres
    cid, vid, mid, memory_id = (uuid4() for _ in range(4))
    with engine.begin() as db:
        db.exec_driver_sql("INSERT INTO vehicle_user VALUES (1)")
        db.exec_driver_sql("INSERT INTO user_vehicle VALUES (%s, 1)", (vid,))
        db.exec_driver_sql("INSERT INTO conversation VALUES (%s, 1, %s)", (cid, vid))
        db.exec_driver_sql("INSERT INTO chat_message VALUES (%s, %s, false)", (mid, cid))
        db.exec_driver_sql(
            """INSERT INTO agent_user_memory VALUES
            (%s,1,'account','1','cost_display_preference','{"format":"total"}','active',%s,now(),now(),now(),now()+interval '180 days',1)""",
            (memory_id, mid),
        )
        db.exec_driver_sql("INSERT INTO agent_memory_source VALUES (%s,%s,%s)", (memory_id, mid, cid))
        # Cascade path, not the HTTP lifecycle service: trigger must catch it.
        db.exec_driver_sql("DELETE FROM vehicle_user WHERE user_id=1")
        assert db.exec_driver_sql("SELECT count(*) FROM agent_user_memory").scalar() == 0
        task = db.exec_driver_sql(
            "SELECT vector_ids FROM agent_memory_cleanup WHERE conversation_id=%s", (cid,)
        ).scalar()
        assert task == [str(mid)]


def test_memory_tables_require_backend_role_without_public_policies(isolated_postgres):
    engine, _, schema = isolated_postgres
    with engine.connect() as db:
        tables = db.exec_driver_sql(
            "SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=%s AND c.relname IN "
            "('conversation_summary','agent_memory_cleanup','agent_memory_setting','agent_user_memory','agent_memory_source')",
            (schema,),
        ).all()
        assert len(tables) == 5 and all(enabled for _, enabled in tables)
        assert db.exec_driver_sql("SELECT count(*) FROM pg_policies WHERE schemaname=%s", (schema,)).scalar() == 0


def test_reopened_postgres_saver_recovers_thread_and_deletes_all_snapshots(isolated_postgres):
    with asyncio.Runner(loop_factory=selector_loop_factory) as runner:
        runner.run(_verify_postgres_restart(isolated_postgres))


def test_index_row_lock_serializes_cascade_deletion(isolated_postgres):
    engine, _, _ = isolated_postgres
    cid, vid, mid = (uuid4() for _ in range(3))
    with engine.begin() as db:
        db.exec_driver_sql("INSERT INTO vehicle_user VALUES (1)")
        db.exec_driver_sql("INSERT INTO user_vehicle VALUES (%s, 1)", (vid,))
        db.exec_driver_sql("INSERT INTO conversation VALUES (%s, 1, %s)", (cid, vid))
        db.exec_driver_sql("INSERT INTO chat_message VALUES (%s, %s, false)", (mid, cid))
    started, finished = Event(), Event()

    def cascade_delete():
        with engine.begin() as db:
            db.exec_driver_sql("SET LOCAL statement_timeout='5s'")
            started.set()
            db.exec_driver_sql("DELETE FROM vehicle_user WHERE user_id=1")
        finished.set()

    with ThreadPoolExecutor(max_workers=1) as executor:
        with engine.begin() as indexing:
            indexing.exec_driver_sql("SELECT id FROM conversation WHERE id=%s FOR UPDATE", (cid,))
            pending = executor.submit(cascade_delete)
            assert started.wait(2)
            assert not finished.wait(0.1)
            # The indexing worker commits while the cascade waits on its row lock.
            indexing.exec_driver_sql("UPDATE chat_message SET embedded=true WHERE id=%s", (mid,))
        pending.result(timeout=5)
    with engine.connect() as db:
        assert db.exec_driver_sql("SELECT count(*) FROM chat_message").scalar() == 0
        assert db.exec_driver_sql(
            "SELECT vector_ids FROM agent_memory_cleanup WHERE conversation_id=%s", (cid,)
        ).scalar() == [str(mid)]


async def _verify_postgres_restart(isolated_postgres):
    engine, dsn, _ = isolated_postgres
    cid = str(uuid4())
    config = {"configurable": {"thread_id": cid}}
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await saver.setup()
        graph = build_graph(FakeChat(responses=["first"]), [], saver, system_prompt="Test")
        await graph.ainvoke({"messages": [HumanMessage(content="question", id="user-1")]}, config)
        assert await saver.aget_tuple(config) is not None
    # Closed pool, new connection and new graph: no in-process memory is reused.
    async with AsyncPostgresSaver.from_conn_string(dsn) as reopened:
        graph = build_graph(FakeChat(responses=["second"]), [], reopened, system_prompt="Test")
        before = await graph.aget_state(config)
        assert len(before.values["messages"]) == 2
        await graph.ainvoke({"messages": [HumanMessage(content="continue", id="user-2")]}, config)
        assert len((await graph.aget_state(config)).values["messages"]) == 4
        assert len([checkpoint async for checkpoint in reopened.alist(config)]) > 1
        await reopened.adelete_thread(cid)
        assert await reopened.aget_tuple(config) is None
        assert [checkpoint async for checkpoint in reopened.alist(config)] == []
    with engine.connect() as db:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            assert db.exec_driver_sql(f"SELECT count(*) FROM {table} WHERE thread_id=%s", (cid,)).scalar() == 0
