from __future__ import annotations

from functools import lru_cache

from ...config import get_settings
from ..redis.dependency import get_pubsub
from ..supabase.db import engine
from .realtime import MessageService


def _dispatch_index(message_id: str) -> None:
    """Hand indexing to the Celery worker (durable, retried). Imported lazily so
    the web process doesn't import the task graph at module load."""
    from ..celery.tasks.embedding_tasks import index_message_task

    index_message_task.delay(message_id)


@lru_cache
def get_message_service() -> MessageService:
    """Process-wide message service (persist + publish + optional index)."""
    settings = get_settings()
    return MessageService(
        db_engine=engine,
        pubsub=get_pubsub(),
        index_dispatch=_dispatch_index,
        semantic_index_enabled=settings.conversation_semantic_index_enabled,
    )
