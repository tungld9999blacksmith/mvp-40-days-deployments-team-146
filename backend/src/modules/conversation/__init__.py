"""Conversation feature (US-025): chat threads, messages, RAG turn, realtime.

Routers: ``route.router`` (owner REST + SSE), ``route.workshop_router`` (workshop
excerpt), ``ws.ws_router`` (WebSocket). Errors map via ``errors.status_for``.
"""

from .errors import ConversationError, status_for
from .route import router, workshop_router
from .ws import ws_router

__all__ = [
    "ConversationError",
    "router",
    "status_for",
    "workshop_router",
    "ws_router",
]
