"""Conversation domain: chat threads (ENT-421) and their messages (ENT-422).

Specs: ``docs/specs/entity/conversation/{conversation,chat_message}.entity.md``.
Written through ``infrastructure/messaging.MessageService`` (the only writer);
read via the repositories here.
"""

from .conversation import Conversation, ConversationRepository
from .message import ChatMessage, ChatMessageRepository, MessageRole

__all__ = [
    "ChatMessage",
    "ChatMessageRepository",
    "Conversation",
    "ConversationRepository",
    "MessageRole",
]
