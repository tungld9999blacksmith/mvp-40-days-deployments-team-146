"""Quote module — chat card helpers (us-049 CARD-QUOTE, AI-005 TOOL-501).

``chat_message.card`` keeps the quote as it was when the agent drafted it; the
quote itself is read from the database every time messages are returned, so a
reopened conversation shows whether it was sent, approved, rejected or expired.
"""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from src.infrastructure.messaging import MessageDto

from . import schemas
from .service import QuoteService

CARD_QUOTE = "QUOTE"


def quote_card(quote: schemas.QuoteOut) -> dict:
    """Card payload read by the chat UI (``MessageCard`` → ``QuoteChatCard``)."""
    return {"type": CARD_QUOTE, "quote": quote.model_dump(mode="json", by_alias=True)}


def _quote_id(card: dict | None) -> UUID | None:
    if not card or card.get("type") != CARD_QUOTE:
        return None
    try:
        return UUID(str((card.get("quote") or {}).get("quoteId")))
    except ValueError:
        return None


def enrich_quote_cards(session: Session, messages: list[MessageDto]) -> list[MessageDto]:
    """Replace every QUOTE card's snapshot with the quote's current state (read only).

    A quote that no longer exists (a draft deleted or purged, BR-1112) drops its card.
    """
    ids = [quote_id for m in messages if (quote_id := _quote_id(m.card)) is not None]
    if not ids:
        return messages
    current = QuoteService(session, None).details(ids)
    out: list[MessageDto] = []
    for message in messages:
        quote_id = _quote_id(message.card)
        if quote_id is None:
            out.append(message)
            continue
        quote = current.get(quote_id)
        out.append(message.model_copy(update={"card": quote_card(quote) if quote else None}))
    return out
