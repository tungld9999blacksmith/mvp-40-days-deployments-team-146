"""Failed, stalled or disconnected AI turns must terminate and release their lock."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis

from src.common.core.conversation import ChatMessage
from src.common.core.vehicle import UserVehicle
from src.infrastructure.messaging import AppendResult
from src.infrastructure.redis import RedisToolkit
from src.modules.conversation.service import ChatService


@pytest_asyncio.fixture
async def chat():
    redis = FakeAsyncRedis()
    toolkit = RedisToolkit(redis, key_prefix="stability-test")
    conversation_id = uuid4()
    vehicle = UserVehicle(id=uuid4(), user_id=1, license_plate="TEST")
    messages = Mock()

    async def append(cid, role, content, **kwargs):
        return AppendResult(
            ChatMessage(
                conversation_id=cid,
                role=role,
                content=content,
                seq=messages.append.await_count,
                created_at=datetime.now(UTC),
                **kwargs,
            ),
            created=True,
        )

    messages.append = AsyncMock(side_effect=append)
    messages.publish = AsyncMock()
    orchestrator = Mock()
    orchestrator.fetch_vehicle_context = AsyncMock(return_value={})

    async def answer(**kwargs):
        yield {"type": "token", "delta": "answer"}
        yield {"type": "completed", "message_data": {}}

    orchestrator.run_agent_turn = answer
    settings = SimpleNamespace(
        chat_run_timeout_seconds=1,
        chat_run_lock_ttl_seconds=2,
        chat_message_max_chars=3000,
        chat_rate_limit_per_minute=100,
        chat_rate_limit_per_day=1000,
    )
    service = ChatService(None, messages, toolkit, None, None, None, settings, orchestrator)
    service._get_chat_vehicle = Mock(return_value=vehicle)
    service._build_history_messages = Mock(return_value=[])
    yield service, conversation_id, toolkit, messages, orchestrator
    await toolkit.pubsub.stop()
    await toolkit.cache.write_back_buffer.stop(final_flush=False)
    await redis.aclose()


async def collect(service, conversation_id, is_disconnected=None):
    return [
        frame
        async for frame in service.stream_turn(
            1, conversation_id, uuid4(), "question", trace_id="trace-test", is_disconnected=is_disconnected
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["initialization", "context", "history", "persistence", "dto"])
async def test_post_acceptance_failure_returns_terminal_error_and_releases_lock(chat, stage):
    service, cid, toolkit, messages, orchestrator = chat
    failure = RuntimeError("dependency unavailable")
    if stage == "initialization":
        service._get_orchestrator = Mock(side_effect=failure)
    elif stage == "context":
        orchestrator.fetch_vehicle_context.side_effect = failure
    elif stage == "history":
        service._build_history_messages.side_effect = failure
    elif stage == "dto":
        service.to_dtos = Mock(side_effect=failure)
    else:
        original = messages.append.side_effect

        async def fail_second_append(*args, **kwargs):
            if messages.append.await_count == 2:
                raise failure
            return await original(*args, **kwargs)

        messages.append.side_effect = fail_second_append
    frames = await collect(service, cid)
    assert frames[0].event == "message.accepted"
    assert frames[-1].event == "error"
    assert frames[-1].data == {
        "code": "AGENT_ERROR",
        "message": "Trợ lý tạm thời không trả lời được.",
        "traceId": "trace-test",
    }
    assert not await toolkit.locks.is_locked(f"conversation-run:{cid}")


@pytest.mark.asyncio
@pytest.mark.parametrize("tokens", [False, True])
async def test_total_deadline_cancels_agent_even_if_tokens_keep_arriving(chat, tokens):
    service, cid, toolkit, messages, orchestrator = chat
    service._settings.chat_run_timeout_seconds = 0.15
    stopped = asyncio.Event()

    async def hang(**kwargs):
        try:
            yield {"type": "tool_start", "tool": "lookup"}
            if tokens:
                for _ in range(100):
                    await asyncio.sleep(0.02)
                    yield {"type": "token", "delta": "partial"}
            await asyncio.Event().wait()
        finally:
            stopped.set()

    orchestrator.run_agent_turn = hang
    frames = await asyncio.wait_for(collect(service, cid), timeout=1)
    assert frames[-1].event == "error"
    assert frames[-1].data["code"] == "CHAT_TIMEOUT"
    assert stopped.is_set()
    assert messages.append.await_count == 1  # no incomplete assistant response
    assert not await toolkit.locks.is_locked(f"conversation-run:{cid}")


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_task", [False, True])
async def test_disconnect_or_cancellation_stops_agent_before_first_token(chat, cancel_task):
    service, cid, toolkit, messages, orchestrator = chat
    entered, stopped, disconnected = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def hang(**kwargs):
        try:
            entered.set()
            await asyncio.Event().wait()
            yield {}
        finally:
            stopped.set()

    async def is_disconnected():
        return disconnected.is_set()

    orchestrator.run_agent_turn = hang
    request = asyncio.create_task(collect(service, cid, is_disconnected))
    await asyncio.wait_for(entered.wait(), 1)
    if cancel_task:
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
    else:
        disconnected.set()
        frames = await asyncio.wait_for(request, 1)
        assert not any(f.event == "message.completed" for f in frames)
    assert stopped.is_set()
    assert messages.append.await_count == 1
    assert not await toolkit.locks.is_locked(f"conversation-run:{cid}")


@pytest.mark.asyncio
async def test_deadline_during_answer_persistence_keeps_lock_until_write_finishes(chat):
    """The database worker cannot be cancelled; the lock must outlive it."""
    import time

    service, cid, toolkit, messages, _ = chat
    service._settings.chat_run_timeout_seconds = 0.15
    original = messages.append.side_effect
    committed = []

    async def slow_assistant_write(cid_, role, content, **kwargs):
        if messages.append.await_count == 2:
            await asyncio.to_thread(time.sleep, 0.4)  # a commit running in a worker thread
            committed.append(True)
        return await original(cid_, role, content, **kwargs)

    messages.append.side_effect = slow_assistant_write
    frames = await asyncio.wait_for(collect(service, cid), timeout=2)
    assert committed == [True]  # the turn ended only after the write completed
    assert frames[-1].event == "error" and frames[-1].data["code"] == "CHAT_TIMEOUT"
    assert not await toolkit.locks.is_locked(f"conversation-run:{cid}")


@pytest.mark.asyncio
async def test_timeout_before_acceptance_raises_chat_timeout_and_releases_lock(chat):
    import time

    from src.modules.conversation import errors

    service, cid, toolkit, messages, _ = chat
    service._settings.chat_run_timeout_seconds = 0.1
    committed = []

    async def slow_user_write(*args, **kwargs):
        await asyncio.to_thread(time.sleep, 0.4)  # a commit running in a worker thread
        committed.append(True)

    messages.append.side_effect = slow_user_write
    with pytest.raises(errors.ConversationError) as exc:
        await asyncio.wait_for(collect(service, cid), timeout=2)
    assert committed == [True]  # the lock outlived the write, so a retry cannot overlap it
    assert exc.value.code == "CHAT_TIMEOUT"
    assert errors.ERROR_STATUS["CHAT_TIMEOUT"] == 504
    assert not await toolkit.locks.is_locked(f"conversation-run:{cid}")


@pytest.mark.asyncio
async def test_disconnect_cancel_mid_stream_still_releases_the_run_lock(chat):
    """A client disconnect cancels the SSE task through anyio; the lock must not wait for its TTL."""
    import anyio

    service, cid, toolkit, _, orchestrator = chat
    streaming = asyncio.Event()

    async def hang_after_token(**kwargs):
        yield {"type": "token", "delta": "partial"}
        await asyncio.Event().wait()

    orchestrator.run_agent_turn = hang_after_token

    async def consume():
        async for frame in service.stream_turn(1, cid, uuid4(), "question", trace_id="t"):
            if frame.event == "token":
                streaming.set()

    async with anyio.create_task_group() as tg:
        tg.start_soon(consume)
        await streaming.wait()
        tg.cancel_scope.cancel()
    assert not await toolkit.locks.is_locked(f"conversation-run:{cid}")
