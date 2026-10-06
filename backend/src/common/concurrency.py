"""Await work that must finish even when the awaiting request is cancelled."""

from __future__ import annotations

import asyncio

import anyio


async def wait_through_cancellation(task: asyncio.Future) -> bool:
    """Wait until ``task`` is done and return whether the caller was cancelled meanwhile.

    ``asyncio.wait`` never cancels the task it waits on, so a database write running
    in a worker thread finishes, while its locks are still held, however many times
    the caller is cancelled. The caller re-raises ``CancelledError`` after cleanup.
    """
    cancelled = False
    # Starlette cancels a disconnected stream through an anyio scope that re-delivers
    # the cancellation on every loop tick; shield it so this loop does not spin. A
    # caller cancelled that way is cancelled again at its next checkpoint.
    with anyio.CancelScope(shield=True):
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError:
                cancelled = True
    return cancelled
