"""Celery tasks for vector indexing (durable, out-of-band embedding).

- ``embedding.index_message`` — embed one chat message and upsert it into the
  ``conversation_messages`` collection, then flag ``chat_message.embedded``.
  Enqueued by ``MessageService`` after a message is persisted, so the realtime
  publish never waits on the embedding provider. Retries on provider outage.

Metadata is built by ``VectorRecordBuilder`` under the collection's
``VectorMetadataPolicy`` (BR-ENT-474): only system + filter keys plus a
masked ``sourceMeta`` — never the raw message metadata (no citation/tool leak).

Each run opens its own DB session. Indexing is gated by
``settings.conversation_semantic_index_enabled`` (Q-604): the task is a no-op
when the feature is off.
"""

from __future__ import annotations

import logging
from uuid import UUID

from src.celery_tasks import celery

logger = logging.getLogger(__name__)

RETRY_DELAYS_SECONDS = (10, 60, 300)


@celery.task(
    name="embedding.index_message",
    bind=True,
    acks_late=True,
    max_retries=len(RETRY_DELAYS_SECONDS),
)
def index_message_task(self, message_id: str) -> str:
    from src.common.core.conversation import ChatMessageRepository, MessageRole
    from src.config import get_settings
    from src.infrastructure.supabase.db import get_session
    from src.infrastructure.vectorstore import (
        CONVERSATION_MESSAGES,
        VectorRecordBuilder,
        get_vector_store,
    )

    if not get_settings().conversation_semantic_index_enabled:
        return "disabled"

    session = next(get_session())
    try:
        repo = ChatMessageRepository(session)
        message = repo.get(UUID(message_id))
        if message is None:
            logger.warning("index_message: message %s not found", message_id)
            return "missing"
        if message.role == MessageRole.TOOL:
            return "skipped"
        if message.embedded:
            return "already_indexed"

        try:
            record = VectorRecordBuilder.from_message(message)
            get_vector_store().add(CONVERSATION_MESSAGES, [record])
        except Exception as exc:  # noqa: BLE001 — retry on provider/store failure
            countdown = RETRY_DELAYS_SECONDS[
                min(self.request.retries, len(RETRY_DELAYS_SECONDS) - 1)
            ]
            raise self.retry(exc=exc, countdown=countdown)

        repo.update(message, {"embedded": True})
        session.commit()
        return "indexed"
    finally:
        session.close()
