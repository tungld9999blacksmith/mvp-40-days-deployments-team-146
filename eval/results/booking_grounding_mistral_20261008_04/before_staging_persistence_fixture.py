"""Restart/confirm evidence, with explicit isolated PostgreSQL/Redis opt-in."""
from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlmodel import Session, create_engine, select

from src.common.core.maintenance.booking import Booking
from src.common.core.maintenance.booking_proposal import BookingProposal
from tests.evaluation_v2.sandbox import Sandbox


async def confirm_after_reopen(sandbox, reopen):
    tool = next(t for t in sandbox.tools if t.name == "propose_booking")
    config = sandbox.config("persist-" + uuid4().hex)
    result = await tool.ainvoke({"name": tool.name, "args": {"workshop_id": sandbox.workshop_a, "booking_date": "2026-10-10", "time_slot": "14:00"}, "id": "proposal", "type": "tool_call"}, config)
    assert result.artifact["type"] == "BOOKING_PROPOSAL"
    proposal_id = UUID(result.artifact["proposalId"])
    assert sandbox.side_effects() == {"booking_count_before_confirm": 0, "proposal_count": 1}
    booking_id = None
    for replayed in (False, True):
        sandbox.engine.dispose()
        sandbox.engine = reopen()
        with Session(sandbox.engine) as session:
            assert session.get(BookingProposal, proposal_id) is not None
            service = sandbox.quick_booking(session)
            # This test isolates booking persistence. HTTP/message rendering has
            # separate API tests; no transport or fake per-process message counter.
            service._messages = None
            confirmed = await service.confirm(sandbox.user_id, sandbox.conversation_id, proposal_id)
            assert confirmed.replayed is replayed
            rows = session.exec(select(Booking)).all()
            assert len(rows) == 1
            if booking_id is not None:
                assert rows[0].id == booking_id
            booking_id = rows[0].id


@pytest.mark.asyncio
async def test_sqlite_proposal_survives_engine_restart_and_confirm_is_idempotent(tmp_path):
    database = tmp_path / "isolated-booking.sqlite"
    sandbox = Sandbox({}, database_path=database)
    try:
        await confirm_after_reopen(sandbox, lambda: create_engine("sqlite:///" + str(database)))
    finally:
        await sandbox.close()


@pytest.mark.staging
@pytest.mark.asyncio
async def test_postgres_redis_restart_and_confirm_in_isolated_schema():
    database_url = os.getenv("EVAL_DATABASE_URL", "")
    redis_url = os.getenv("EVAL_REDIS_URL", "")
    if not database_url or not redis_url:
        pytest.fail("Set EVAL_DATABASE_URL and EVAL_REDIS_URL for a dedicated evaluation database; production settings are never used")
    admin = create_engine(database_url)
    if admin.dialect.name != "postgresql" or not str(admin.url.database).startswith("p146_eval"):
        admin.dispose()
        pytest.fail("PostgreSQL evaluation database name must start with p146_eval")
    schema = "eval_" + uuid4().hex
    prefix = "eval-v2-" + uuid4().hex
    sandbox = None
    redis = Redis.from_url(redis_url, socket_timeout=5, socket_connect_timeout=5)
    created = False
    connected = False
    try:
        await redis.ping()
        connected = True
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))
            created = True
        def reopen():
            return create_engine(database_url, connect_args={"options": "-csearch_path=" + schema})
        sandbox = Sandbox({}, engine=reopen(), redis_client=redis, key_prefix=prefix)
        await confirm_after_reopen(sandbox, reopen)
    finally:
        # Only this fixture's unique namespace/schema is eligible for cleanup.
        keys = [key async for key in redis.scan_iter(match=prefix + ":*")] if connected else []
        if keys:
            await redis.delete(*keys)
        if sandbox:
            await sandbox.close()
        else:
            await redis.aclose()
        if created:
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()
