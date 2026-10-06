"""Quick booking — chat card helpers (us-061 API §3, HOOK-QB-01).

``chat_message.card`` keeps the snapshot shown when the proposal was made; the
proposal status and the booking it produced are read from the database every
time messages are returned, so a reopened conversation shows the current state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session, select

from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.booking_proposal import BookingProposal, BookingProposalStatus
from src.infrastructure.messaging import MessageDto
from src.modules.oem_integration.service import as_utc

from .domain import CARD_PROPOSAL

# Statuses for which the booking code is shown (``BookingService._to_out`` hides it while pending).
CODE_VISIBLE_STATUSES = {
    BookingStatus.CONFIRMED,
    BookingStatus.CHECKED_IN,
    BookingStatus.IN_PROGRESS,
    BookingStatus.COMPLETED,
}


def proposal_status(proposal: BookingProposal | None, now: datetime) -> str:
    """BR-ENT-1501: a ``proposed`` row past ``expires_at`` reads as EXPIRED."""
    if proposal is None:
        return BookingProposalStatus.EXPIRED.value.upper()
    if proposal.status == BookingProposalStatus.PROPOSED and as_utc(proposal.expires_at) <= now:
        return BookingProposalStatus.EXPIRED.value.upper()
    return proposal.status.value.upper()


def booking_summary(booking: Booking | None) -> dict | None:
    if booking is None:
        return None
    return {
        "bookingId": str(booking.id),
        "bookingCode": booking.booking_code if booking.status in CODE_VISIBLE_STATUSES else None,
        "status": booking.status.value.upper(),
        "ownerCancelableUntil": (
            as_utc(booking.hold_expires_at).isoformat()
            if booking.status == BookingStatus.PENDING and booking.hold_expires_at
            else None
        ),
    }


def enrich_cards(session: Session, messages: list[MessageDto], *, now: datetime | None = None) -> list[MessageDto]:
    """Attach the live ``status`` and ``booking`` to every BOOKING_PROPOSAL card (read only)."""
    ids: list[UUID] = []
    for message in messages:
        card = message.card or {}
        if card.get("type") == CARD_PROPOSAL and card.get("proposalId"):
            try:
                ids.append(UUID(str(card["proposalId"])))
            except ValueError:
                continue
    if not ids:
        return messages

    now = now or datetime.now(UTC)
    proposals = {p.id: p for p in session.exec(select(BookingProposal).where(BookingProposal.id.in_(ids))).all()}
    booking_ids = [p.booking_id for p in proposals.values() if p.booking_id]
    bookings = (
        {b.id: b for b in session.exec(select(Booking).where(Booking.id.in_(booking_ids))).all()} if booking_ids else {}
    )

    out: list[MessageDto] = []
    for message in messages:
        card = message.card or {}
        if card.get("type") != CARD_PROPOSAL or not card.get("proposalId"):
            out.append(message)
            continue
        try:
            proposal = proposals.get(UUID(str(card["proposalId"])))
        except ValueError:
            proposal = None
        booking = bookings.get(proposal.booking_id) if proposal and proposal.booking_id else None
        live = {**card, "status": proposal_status(proposal, now), "booking": booking_summary(booking)}
        out.append(message.model_copy(update={"card": live}))
    return out


def attach_message(session: Session, proposal_id: UUID, message_id: UUID) -> None:
    """Link a proposal to the chat message carrying its card (set once, right after the save)."""
    proposal = session.get(BookingProposal, proposal_id)
    if proposal is not None and proposal.message_id is None:
        proposal.message_id = message_id
        session.add(proposal)
        session.commit()
