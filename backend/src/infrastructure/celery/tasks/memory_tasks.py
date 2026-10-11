"""Scheduled cleanup/retention; use the CLI when a worker is not running."""

import asyncio

from src.celery_tasks import celery


async def run_memory_maintenance(*, purge=False, dry_run=True):
    from src.agents.checkpoint import checkpoint_lifespan
    from src.config import get_settings
    from src.infrastructure.supabase.db import engine
    from src.infrastructure.vectorstore.dependency import get_vector_store
    from src.modules.agent_memory.lifecycle import ConversationMemoryLifecycleService
    from src.modules.conversation.dependency import get_chat_service

    settings = get_settings()
    async with checkpoint_lifespan(settings) as saver:
        service = ConversationMemoryLifecycleService(
            engine, settings, get_chat_service().run_lock, saver, get_vector_store
        )
        if purge:
            return await service.purge(dry_run=dry_run)
        return await service.cleanup_pending()


@celery.task(name="agent_memory.cleanup")
def cleanup():
    from src.agents.checkpoint import selector_loop_factory

    with asyncio.Runner(loop_factory=selector_loop_factory) as runner:
        return runner.run(run_memory_maintenance())


@celery.task(name="agent_memory.retention")
def retention():
    from src.config import get_settings

    if not get_settings().agent_memory_retention_enabled:
        return {"disabled": True}
    from src.agents.checkpoint import selector_loop_factory

    with asyncio.Runner(loop_factory=selector_loop_factory) as runner:
        return runner.run(run_memory_maintenance(purge=True, dry_run=False))
