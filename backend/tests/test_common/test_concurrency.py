"""``wait_through_cancellation``: finish owned work however the caller is cancelled."""

import asyncio

import anyio
import pytest

from src.common.concurrency import wait_through_cancellation


@pytest.mark.asyncio
async def test_done_task_returns_without_waiting():
    task = asyncio.create_task(asyncio.sleep(0))
    await task
    assert await wait_through_cancellation(task) is False


@pytest.mark.asyncio
async def test_failed_task_keeps_its_exception():
    async def fail():
        raise RuntimeError("write failed")

    task = asyncio.create_task(fail())
    assert await wait_through_cancellation(task) is False
    assert isinstance(task.exception(), RuntimeError)


@pytest.mark.asyncio
async def test_repeated_native_cancel_waits_for_the_task():
    gate = asyncio.Event()
    inner = asyncio.create_task(gate.wait())
    outer = asyncio.create_task(wait_through_cancellation(inner))
    await asyncio.sleep(0)
    outer.cancel()
    await asyncio.sleep(0)
    outer.cancel()
    await asyncio.sleep(0)
    assert not outer.done()
    gate.set()
    assert await outer is True
    assert inner.done() and not inner.cancelled()


@pytest.mark.asyncio
async def test_anyio_cancellation_does_not_spin_the_event_loop(monkeypatch):
    """Starlette cancels a disconnected stream through an anyio scope, which re-delivers every tick."""
    calls = 0
    real_wait = asyncio.wait

    async def counting_wait(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await real_wait(*args, **kwargs)

    monkeypatch.setattr(asyncio, "wait", counting_wait)
    gate = asyncio.Event()
    inner = asyncio.create_task(gate.wait())

    async def scenario():
        async with anyio.create_task_group() as tg:
            tg.start_soon(wait_through_cancellation, inner)
            await anyio.sleep(0.01)
            tg.cancel_scope.cancel()

    running = asyncio.create_task(scenario())
    await asyncio.sleep(0.1)
    gate.set()
    await running
    assert inner.done() and not inner.cancelled()
    assert calls < 10
