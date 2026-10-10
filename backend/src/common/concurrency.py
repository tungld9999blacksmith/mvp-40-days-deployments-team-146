"""Await work that must finish even when the awaiting request is cancelled."""

from __future__ import annotations

import asyncio

import anyio


async def wait_through_cancellation(task: asyncio.Future, timeout: float | None = None) -> bool:
    """Wait until ``task`` is done and return whether the caller was cancelled meanwhile.

    ``asyncio.wait`` never cancels the task it waits on, so a database write running
    in a worker thread finishes, while its locks are still held, however many times
    the caller is cancelled. The caller re-raises ``CancelledError`` after cleanup.

    With ``timeout``, stop waiting after that many seconds even if ``task`` is still
    running; the caller checks ``task.done()``.
    """
    cancelled = False
    loop = asyncio.get_running_loop()
    deadline = None if timeout is None else loop.time() + timeout
    # Starlette cancels a disconnected stream through an anyio scope that re-delivers
    # the cancellation on every loop tick; shield it so this loop does not spin. A
    # caller cancelled that way is cancelled again at its next checkpoint.
    with anyio.CancelScope(shield=True):
        while not task.done():
            remaining = None if deadline is None else deadline - loop.time()
            if remaining is not None and remaining <= 0:
                break
            try:
                await asyncio.wait({task}, timeout=remaining)
            except asyncio.CancelledError:
                cancelled = True
    return cancelled
