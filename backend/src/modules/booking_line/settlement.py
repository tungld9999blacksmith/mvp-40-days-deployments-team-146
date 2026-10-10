"""Booking guards for two-tier pricing, called by ``BookingStateMachine.transition``.

Both guards lock the booking row first (re-review OV1): every line operation takes
the same lock, so a decision cannot slip in between the check and COMPLETE.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlmodel import Session, select

from src.common.core.maintenance.booking import Booking
from src.common.core.maintenance.booking_line import BookingLine

from . import errors
from .domain import billable_total, complete_block, start_block


def lock_booking(session: Session, booking_id: UUID) -> Booking:
    query = select(Booking).where(Booking.id == booking_id).with_for_update()
    return session.exec(query.execution_options(populate_existing=True)).one()


def lines_of(session: Session, booking_id: UUID) -> list[BookingLine]:
    return list(
        session.exec(
            select(BookingLine)
            .where(BookingLine.booking_id == booking_id)
            .order_by(BookingLine.kind.desc(), BookingLine.created_at, BookingLine.id)
        ).all()
    )


def guard_start(session: Session, booking: Booking) -> None:
    """D8 — the workshop confirms every reference price before starting work."""
    lock_booking(session, booking.id)
    pending = start_block(lines_of(session, booking.id))
    if pending:
        raise errors.LinesUnconfirmedError(pending)


def settle_complete(session: Session, booking: Booking, client_actual_cost: Decimal | None) -> Decimal:
    """D6 — refuse while lines are open; return the system-computed ``actual_cost``."""
    lock_booking(session, booking.id)
    lines = lines_of(session, booking.id)
    open_count = complete_block(lines)
    if open_count:
        raise errors.LinesUnsettledError(open_count)
    total = billable_total(lines)
    if client_actual_cost is not None and Decimal(client_actual_cost).quantize(Decimal("0.01")) != total:
        raise errors.ActualCostMismatchError(str(total))
    return total
