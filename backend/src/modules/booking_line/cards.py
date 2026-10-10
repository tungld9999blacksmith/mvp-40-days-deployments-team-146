"""Chat card of the two-tier price lines (design 3A): a summary + "Mở phiếu để quyết định".

The card never carries a decision button: the booking ticket is the only place
where the owner approves or declines. Like the quote card, ``chat_message.card``
keeps a snapshot and every read replaces it with the current lines.
"""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from src.common.core.maintenance.booking import Booking
from src.infrastructure.messaging import MessageDto

from . import schemas
from .service import BookingLineService

CARD_BOOKING_LINES = "BOOKING_LINES"


def lines_card(booking: Booking, view: schemas.LinesOut) -> dict:
    pending = [line for line in view.lines if line.status == "PROPOSED"]
    return {
        "type": CARD_BOOKING_LINES,
        "bookingId": str(booking.id),
        "bookingCode": booking.booking_code,
        "bookingStatus": view.booking_status,
        "pendingCount": len(pending),
        "pendingItems": [
            {
                "lineId": str(line.line_id),
                "kind": line.kind,
                "itemName": line.item_name,
                "price": float(line.price),
                "isSafetyCritical": line.is_safety_critical,
            }
            for line in pending
        ],
        "currentTotal": float(view.current_total),
        "totalIfAllApproved": float(view.total_if_all_approved),
    }


def _booking_id(card: dict | None) -> UUID | None:
    if not card or card.get("type") != CARD_BOOKING_LINES:
        return None
    try:
        return UUID(str(card.get("bookingId")))
    except ValueError:
        return None


def enrich_line_cards(session: Session, messages: list[MessageDto]) -> list[MessageDto]:
    """Replace each BOOKING_LINES card with the booking's current lines (read only)."""
    if not any(_booking_id(m.card) for m in messages):
        return messages
    service = BookingLineService(session)
    out: list[MessageDto] = []
    for message in messages:
        booking_id = _booking_id(message.card)
        if booking_id is None:
            out.append(message)
            continue
        booking = session.get(Booking, booking_id)
        card = lines_card(booking, service.view(booking)) if booking else None
        out.append(message.model_copy(update={"card": card}))
    return out
