"""Service tests for quotes approved by the workshop owner (us-049, HITL).

In-memory SQLite; the booking cases also use fakeredis for the real slot lock
and the single-use confirmation token.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis

from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.quote import Quote, QuoteStatus
from src.infrastructure.redis import RedisToolkit
from src.modules.booking import errors as booking_errors
from src.modules.booking.domain import BookingConfig, now_vn
from src.modules.booking.location import SimpleTextLocationFinder
from src.modules.booking.schemas import HoldRequest
from src.modules.booking.service import BookingService
from src.modules.booking.ticket import BookingTicketService
from src.modules.cost_estimate.service import CostEstimationService
from src.modules.quote import errors as quote_errors
from src.modules.quote import schemas as quote_schemas
from src.modules.quote.service import QuoteService
from tests._maintenance import add_hours, add_workshop, add_workshop_owner, make_session
from tests._user_vehicle import add_owner, add_rules, add_vehicle

# 2026-10-03 09:00 VN.
NOW = datetime(2026, 10, 3, 2, 0, tzinfo=UTC)


@pytest.fixture
def session():
    yield from make_session()


@pytest.fixture
def world(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    owner = add_workshop_owner(session)
    workshop = add_workshop(session, owner=owner)
    add_hours(session, workshop)
    add_rules(session)
    return session, user, vehicle, owner, workshop


@pytest_asyncio.fixture
async def toolkit():
    redis = FakeAsyncRedis()
    tk = RedisToolkit(redis, key_prefix="test", default_cache_ttl=60)
    yield tk
    await tk.pubsub.stop()
    await tk.cache.write_back_buffer.stop(final_flush=False)
    await redis.flushall()
    await redis.aclose()


def _quotes(session, now=NOW):
    estimator = CostEstimationService(session, SimpleTextLocationFinder(), lambda _v: 12_000, clock=lambda: now)
    return QuoteService(session, estimator, clock=lambda: now)


def _draft(quotes, user, vehicle, workshop, milestone=12_000):
    return quotes.create(
        user,
        quote_schemas.CreateQuoteRequest(user_vehicle_id=vehicle.id, workshop_id=workshop.id, odo_milestone=milestone),
    )


def _approved(quotes, user, vehicle, owner, workshop):
    draft = _draft(quotes, user, vehicle, workshop)
    quotes.submit(user, draft.quote_id)
    return quotes.approve(owner, workshop.id, draft.quote_id, quote_schemas.ApproveQuoteRequest(items=[]))


# ── draft → submit → review ─────────────────────────────────────────────────
def test_quote_draft_submit_approve(world):
    session, user, vehicle, owner, workshop = world
    quotes = _quotes(session)
    draft = _draft(quotes, user, vehicle, workshop)
    assert draft.status == "DRAFT" and draft.estimated_total == Decimal(100_000)

    submitted = quotes.submit(user, draft.quote_id)
    assert submitted.display_status == "PENDING_APPROVAL"
    with pytest.raises(quote_errors.QuoteNotDraftError):
        quotes.submit(user, draft.quote_id)

    twin = _draft(quotes, user, vehicle, workshop)
    with pytest.raises(quote_errors.QuoteAlreadyPendingError):
        quotes.submit(user, twin.quote_id)

    covered = next(i for i in submitted.items if i.covered)
    with pytest.raises(quote_errors.CoveredItemLockedError):
        quotes.approve(
            owner,
            workshop.id,
            draft.quote_id,
            quote_schemas.ApproveQuoteRequest(
                items=[quote_schemas.ApproveItemIn(quote_item_id=covered.quote_item_id, approved_price=5)]
            ),
        )
    paid = next(i for i in submitted.items if not i.covered)
    approved = quotes.approve(
        owner,
        workshop.id,
        draft.quote_id,
        quote_schemas.ApproveQuoteRequest(
            items=[quote_schemas.ApproveItemIn(quote_item_id=paid.quote_item_id, approved_price=90_000)]
        ),
    )
    assert approved.display_status == "MODIFIED" and approved.approved_total == Decimal(90_000)
    assert approved.can_attach_to_booking
    with pytest.raises(quote_errors.QuoteAlreadyReviewedError):
        quotes.reject(owner, workshop.id, draft.quote_id, "Too late to reject now")

    mine = quotes.get_for_owner(user, draft.quote_id)  # marks the result as seen
    assert mine.status == "APPROVED"
    unseen = quotes.list_for_owner(user, user_vehicle_id=None, statuses=None, unseen_result=True, limit=10, cursor=None)
    assert unseen.items == []


def test_quote_workshop_scope_and_reject_note(world):
    session, user, vehicle, owner, workshop = world
    quotes = _quotes(session)
    draft = _draft(quotes, user, vehicle, workshop, milestone=24_000)
    with pytest.raises(quote_errors.QuoteNotFoundError):  # drafts are invisible to the workshop
        quotes.get_for_workshop(workshop.id, draft.quote_id)
    quotes.submit(user, draft.quote_id)
    with pytest.raises(quote_errors.ReviewerNoteRequiredError):
        quotes.reject(owner, workshop.id, draft.quote_id, "short")
    rejected = quotes.reject(owner, workshop.id, draft.quote_id, "Needs a battery check first.")
    assert rejected.status == "REJECTED"
    listed = quotes.list_for_workshop(
        workshop.id, statuses=[QuoteStatus.REJECTED], date_from=None, date_to=None, limit=5, cursor=None
    )
    assert [q.quote_id for q in listed.items] == [draft.quote_id]


# ── booking with an approved quote (BR-1108, HOOK-QT-02) ────────────────────
async def _book(session, toolkit, user, vehicle, workshop, quote_id, days=3):
    service = BookingService(session, toolkit, SimpleTextLocationFinder(), config=BookingConfig())
    day = now_vn().date() + timedelta(days=days)
    availability = await service.check_availability(user, workshop.id, day, time(9), with_alternatives=False)
    token = availability.requested.confirmation_token
    return service, await service.create_hold(
        user, HoldRequest(confirmation_token=token, user_vehicle_id=vehicle.id, quote_id=quote_id)
    )


@pytest.mark.asyncio
async def test_booking_attaches_approved_quote_and_cancel_releases_it(world, toolkit):
    session, user, vehicle, owner, workshop = world
    approved = _approved(_quotes(session, now=datetime.now(UTC)), user, vehicle, owner, workshop)

    _, out = await _book(session, toolkit, user, vehicle, workshop, approved.quote_id)

    assert out.quote_id == approved.quote_id
    assert out.estimated_cost == approved.approved_total
    quote = session.get(Quote, approved.quote_id)
    assert quote.booking_id == out.booking_id
    tickets = BookingTicketService(session)
    ticket = tickets.get_ticket(user, out.booking_id)
    assert ticket.cost.label == "APPROVED_QUOTE" and ticket.cost.quote_id == approved.quote_id

    tickets.cancel_by_owner(user, out.booking_id, source="APP", reason=None)
    session.refresh(quote)
    assert quote.booking_id is None  # the quote can be attached again


@pytest.mark.asyncio
async def test_booking_refuses_quote_of_another_workshop(world, toolkit):
    session, user, vehicle, owner, workshop = world
    approved = _approved(_quotes(session, now=datetime.now(UTC)), user, vehicle, owner, workshop)
    other = add_workshop(session, name="Other")
    add_hours(session, other)

    with pytest.raises(booking_errors.QuoteExpiredError):
        await _book(session, toolkit, user, vehicle, other, approved.quote_id)


@pytest.mark.asyncio
async def test_booking_refuses_quote_already_used_by_a_completed_booking(world, toolkit):
    """HOOK-QT-01: attach only when ``booking_id IS NULL`` (a cancel detaches)."""
    session, user, vehicle, owner, workshop = world
    approved = _approved(_quotes(session, now=datetime.now(UTC)), user, vehicle, owner, workshop)
    _, first = await _book(session, toolkit, user, vehicle, workshop, approved.quote_id)
    booking = session.get(Booking, first.booking_id)
    booking.status = BookingStatus.COMPLETED
    session.add(booking)
    session.commit()

    with pytest.raises(booking_errors.QuoteExpiredError):
        await _book(session, toolkit, user, vehicle, workshop, approved.quote_id, days=4)
    assert session.get(Quote, approved.quote_id).booking_id == first.booking_id


@pytest.mark.asyncio
async def test_booking_refuses_expired_quote(world, toolkit):
    session, user, vehicle, owner, workshop = world
    approved = _approved(_quotes(session, now=datetime.now(UTC) - timedelta(days=8)), user, vehicle, owner, workshop)

    with pytest.raises(booking_errors.QuoteExpiredError):
        await _book(session, toolkit, user, vehicle, workshop, approved.quote_id)
