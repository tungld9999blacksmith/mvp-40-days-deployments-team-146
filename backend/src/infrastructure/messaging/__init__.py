"""Real-time messaging: persist chat messages to Postgres and fan them out over
Redis Pub/Sub, with optional (config-gated) vector indexing.

- ``MessageService`` — the single writer: persist + publish + optional index
- ``MessageDto`` / ``MessageEventDto`` — client + subscriber wire DTOs
- ``NewMessage`` / ``AppendResult`` — append inputs/outputs
- ``get_message_service`` — DI entry point
"""

from .dependency import get_message_service
from .events import MessageDto, MessageEventDto, conversation_channel
from .realtime import (
    AppendResult,
    ConversationNotFoundError,
    InvalidMessageError,
    MessageService,
    NewMessage,
)

__all__ = [
    "AppendResult",
    "ConversationNotFoundError",
    "InvalidMessageError",
    "MessageDto",
    "MessageEventDto",
    "MessageService",
    "NewMessage",
    "conversation_channel",
    "get_message_service",
]
