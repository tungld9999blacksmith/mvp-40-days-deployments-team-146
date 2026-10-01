"""Service tests for the sprint 3-4 APIs (in-memory SQLite, no Redis / Firebase).

us-033/us-053 booking ticket, us-037 Workshop Board, us-049 quotes,
us-041 follow-up + support tickets, us-057 service progress.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlmodel import select

from src.common.core.crm.follow_up import FollowUp, FollowUpStatus
from src.common.core.crm.support_ticket import SupportTicket, SupportTicketPriority
from src.common.core.maintenance.booking import BookingStatus
from src.common.core.maintenance.booking_status_event import BookingStatusEvent
from src.common.core.maintenance.quote import QuoteStatus
from src.common.core.maintenance.service_progress import ServiceStage
from src.common.core.vehicle import VehicleServiceRecord
from src.modules.booking import errors as booking_errors
from src.modules.booking.location import SimpleTextLocationFinder
from src.modules.booking.ticket import BookingTicketService, mask_plate
from src.modules.cost_estimate.service import CostEstimationService
from src.modules.follow_up import errors as fu_errors
from src.modules.follow_up.service import FollowUpService, WorkshopTicketService
from src.modules.quote import errors as quote_errors
from src.modules.quote import schemas as quote_schemas
from src.modules.quote.service import QuoteService
from src.modules.service_progress import errors as progress_errors
from src.modules.service_progress.service import ServiceProgressService
from src.modules.workshop_board import errors as board_errors
from src.modules.workshop_board import schemas as board_schemas
from src.modules.workshop_board.service import WorkshopBoardService
from tests._maintenance import add_booking, add_hours, add_workshop, add_workshop_owner, make_session
from tests._user_vehicle import add_owner, add_rules, add_vehicle

# 2026-10-03 09:00 VN.
NOW = datetime(2026, 10, 3, 2, 0, tzinfo=UTC)
TODAY = date(2026, 10, 3)


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
    return session, user, vehicle, owner, workshop


# ── us-033 / us-053 booking ticket ──────────────────────────────────────────
def _tickets(session, now=NOW):
    return BookingTicketService(session, clock=lambda: now)


def test_ticket_actions_attendance_and_cancel(world):
    session, user, vehicle, _, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=TODAY + timedelta(days=2))
    tickets = _tickets(session)

    ticket = tickets.get_ticket(user, booking.id)
    assert set(ticket.allowed_actions) == {"CONFIRM_ATTENDANCE", "CANCEL", "RESCHEDULE"}
    assert ticket.vehicle.plate_masked == "30A-***.45"
    assert ticket.qr_url == f"/api/v1/bookings/{booking.id}/qr"

    tickets.confirm_attendance(user, booking.id)
    assert "CONFIRM_ATTENDANCE" not in tickets.get_ticket(user, booking.id).allowed_actions

    out = tickets.cancel_by_owner(user, booking.id, source="REMINDER_24H", reason="Busy")
    assert out.status == "CANCELLED" and out.cancelled_by == "VEHICLE_OWNER"
    again = tickets.cancel_by_owner(user, booking.id, source="APP", reason=None)  # idempotent
    assert again.source == "REMINDER_24H"
    event = session.exec(select(BookingStatusEvent)).one()
    assert event.reason_code == "OWNER_CANCELLED"


def test_ticket_hides_other_owner_and_blocks_after_start(world):
    session, user, vehicle, _, workshop = world
    other = add_owner(session, uid="uid-2", email="o2@example.com")
    booking = add_booking(session, user, vehicle, workshop, d=TODAY, t=time(8))
    with pytest.raises(booking_errors.BookingNotFoundError):
        _tickets(session).get_ticket(other, booking.id)
    with pytest.raises(booking_errors.AppointmentStartedError):
        _tickets(session).cancel_by_owner(user, booking.id, source="APP", reason=None)


def test_my_bookings_paginates_and_finds_by_code(world):
    session, user, vehicle, _, workshop = world
    for i in range(3):
        add_booking(
            session, user, vehicle, workshop, d=TODAY + timedelta(days=i + 1), code=f"EVC-0000000{i}"
        )
    tickets = _tickets(session)
    first = tickets.list_for_user(user, limit=2)
    second = tickets.list_for_user(user, limit=2, cursor=first.next_cursor)
    assert len(first.items) == 2 and len(second.items) == 1 and second.next_cursor is None
    assert tickets.find_by_code(user, "evc-00000001") is not None
    png = tickets.qr_png(user, first.items[0].booking_id)
    assert png.startswith(b"\x89PNG")


def test_mask_plate():
    assert mask_plate("30A-123.45") == "30A-***.45"


# ── us-037 Workshop Board ───────────────────────────────────────────────────
def _board(session, now=NOW):
    return WorkshopBoardService(session, clock=lambda: now)


def _move(action, expected, **kw):
    return board_schemas.TransitionRequest(
        action=action, expected_status=expected, **kw
    )


@pytest.mark.asyncio
async def test_board_full_lifecycle_creates_record_and_follow_up(world):
    session, user, vehicle, owner, workshop = world
    booking = add_booking(
        session, user, vehicle, workshop, d=TODAY, t=time(15), status=BookingStatus.PENDING
    )
    booking.created_at = NOW - timedelta(hours=1)  # within the 12h confirm deadline
    session.add(booking)
    session.commit()
    board = _board(session)

    await board.transition(owner, workshop, booking.id, _move("ACCEPT", "PENDING"))
    await board.transition(owner, workshop, booking.id, _move("CHECK_IN", "CONFIRMED", source="QR_SCAN"))
    await board.transition(owner, workshop, booking.id, _move("START", "CHECKED_IN"))
    done = await board.transition(
        owner, workshop, booking.id, _move("COMPLETE", "IN_PROGRESS", actual_cost=Decimal(1_850_000))
    )
    assert done.status == "COMPLETED" and done.effects.follow_up_id is not None
    assert session.exec(select(VehicleServiceRecord)).one().booking_id == booking.id
    follow_up = session.exec(select(FollowUp)).one()
    # Completed 09:00 VN + 12h = 21:00 → moved to 08:00 next day (quiet hours).
    assert follow_up.scheduled_at.replace(tzinfo=UTC) == datetime(2026, 10, 4, 1, 0, tzinfo=UTC)
    history = board.detail(workshop, booking.id).status_history
    assert [h.to_status for h in history] == ["CONFIRMED", "CHECKED_IN", "IN_PROGRESS", "COMPLETED"]


@pytest.mark.asyncio
async def test_board_guards(world):
    session, user, vehicle, owner, workshop = world
    tomorrow = add_booking(session, user, vehicle, workshop, d=TODAY + timedelta(days=1))
    board = _board(session)
    with pytest.raises(board_errors.CheckInNotTodayError):
        await board.transition(owner, workshop, tomorrow.id, _move("CHECK_IN", "CONFIRMED"))
    with pytest.raises(board_errors.InvalidStatusTransitionError):
        await board.transition(owner, workshop, tomorrow.id, _move("COMPLETE", "IN_PROGRESS"))
    with pytest.raises(board_errors.ReasonRequiredError):
        await board.transition(owner, workshop, tomorrow.id, _move("CANCEL", "CONFIRMED"))
    today = add_booking(session, user, vehicle, workshop, d=TODAY, t=time(9), code="EVC-0002")
    with pytest.raises(board_errors.NoShowTooEarlyError):
        await board.transition(
            owner, workshop, today.id, _move("CANCEL", "CONFIRMED", reason_code="NO_SHOW")
        )
    other_ws = add_workshop(session, name="Other")
    with pytest.raises(board_errors.BookingNotFoundError):
        board.detail(other_ws, today.id)


@pytest.mark.asyncio
async def test_board_capacity_and_slot_block(world):
    session, user, vehicle, owner, workshop = world  # 4 technicians, no emergency reserve
    add_booking(session, user, vehicle, workshop, d=TODAY + timedelta(days=1), t=time(9))
    board = _board(session)
    out = await board.set_slot_block(
        owner,
        workshop,
        board_schemas.SlotBlockRequest(
            date=TODAY + timedelta(days=1), time_slot=time(9), blocked_count=3, reason="PHONE_BOOKING"
        ),
    )
    assert (out.occupied, out.blocked, out.remaining, out.max_block) == (1, 3, 0, 3)
    with pytest.raises(board_errors.BlockExceedsFreeCapacityError):
        await board.set_slot_block(
            owner,
            workshop,
            board_schemas.SlotBlockRequest(
                date=TODAY + timedelta(days=1), time_slot=time(9), blocked_count=4, reason="WALK_IN"
            ),
        )
    day = board.capacity(workshop, from_=TODAY + timedelta(days=1), days=1).days[0]
    nine = next(s for s in day.slots if s.time_slot == time(9))
    assert (nine.occupied, nine.blocked, nine.remaining) == (1, 3, 0)


# ── us-049 quotes ───────────────────────────────────────────────────────────
def _quotes(session, now=NOW):
    estimator = CostEstimationService(session, SimpleTextLocationFinder(), lambda _v: 12_000, clock=lambda: now)
    return QuoteService(session, estimator, clock=lambda: now)


def test_quote_draft_submit_approve(world):
    session, user, vehicle, owner, workshop = world
    add_rules(session)
    quotes = _quotes(session)
    draft = quotes.create(
        user,
        quote_schemas.CreateQuoteRequest(
            user_vehicle_id=vehicle.id, workshop_id=workshop.id, odo_milestone=12_000
        ),
    )
    assert draft.status == "DRAFT" and draft.estimated_total == Decimal(100_000)

    submitted = quotes.submit(user, draft.quote_id)
    assert submitted.display_status == "PENDING_APPROVAL"
    with pytest.raises(quote_errors.QuoteNotDraftError):
        quotes.submit(user, draft.quote_id)

    twin = quotes.create(
        user,
        quote_schemas.CreateQuoteRequest(
            user_vehicle_id=vehicle.id, workshop_id=workshop.id, odo_milestone=12_000
        ),
    )
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
    unseen = quotes.list_for_owner(
        user, user_vehicle_id=None, statuses=None, unseen_result=True, limit=10, cursor=None
    )
    assert unseen.items == []


def test_quote_workshop_scope_and_reject_note(world):
    session, user, vehicle, owner, workshop = world
    add_rules(session)
    quotes = _quotes(session)
    draft = quotes.create(
        user,
        quote_schemas.CreateQuoteRequest(
            user_vehicle_id=vehicle.id, workshop_id=workshop.id, odo_milestone=24_000
        ),
    )
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


# ── us-041 follow-up + tickets ──────────────────────────────────────────────
def _sent_follow_up(session, booking, sent_at=NOW - timedelta(hours=1)):
    follow_up = FollowUp(
        booking_id=booking.id,
        message="Xe chạy thế nào?",
        status=FollowUpStatus.SENT,
        scheduled_at=sent_at,
        sent_at=sent_at,
    )
    session.add(follow_up)
    session.commit()
    return follow_up


@pytest.mark.asyncio
async def test_follow_up_issue_creates_high_priority_ticket(world):
    session, user, vehicle, owner, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=TODAY, status=BookingStatus.COMPLETED)
    follow_up = _sent_follow_up(session, booking)
    service = FollowUpService(session, clock=lambda: NOW)

    out = await service.respond(user, follow_up.id, 2, "Về nhà thấy phanh trước kêu khi dừng")
    assert out.outcome.has_issue and out.outcome.safety_advice
    ticket = session.exec(select(SupportTicket)).one()
    assert ticket.priority == SupportTicketPriority.HIGH and ticket.assigned_to == owner.id
    with pytest.raises(fu_errors.FollowUpAlreadyRespondedError):
        await service.respond(user, follow_up.id, 5, None)

    tickets = WorkshopTicketService(session, clock=lambda: NOW)
    listed = tickets.list(owner, workshop.id, statuses=None, priority=None, limit=10, cursor=None)
    assert listed.summary["highOpen"] == 1
    with pytest.raises(fu_errors.ResolutionNoteRequiredError):
        await tickets.transition(
            owner, workshop.id, ticket.id, action="RESOLVE", expected_status="OPEN", resolution_note=" "
        )
    done = await tickets.transition(
        owner, workshop.id, ticket.id, action="RESOLVE", expected_status="OPEN",
        resolution_note="Called the owner; free brake check on 06/10.",
    )
    assert done.status == "RESOLVED" and done.allowed_actions == []
    mine = service.get_ticket(user, ticket.id)
    assert mine.resolution_note.startswith("Called")


@pytest.mark.asyncio
async def test_follow_up_satisfied_and_window(world):
    session, user, vehicle, _, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=TODAY, status=BookingStatus.COMPLETED)
    happy = _sent_follow_up(session, booking)
    service = FollowUpService(session, clock=lambda: NOW)
    out = await service.respond(user, happy.id, 5, None)
    assert not out.outcome.has_issue and out.outcome.ticket is None
    assert service.get(user, happy.id).closed_reason == "PROCESSED"

    other = add_booking(session, user, vehicle, workshop, d=TODAY, status=BookingStatus.COMPLETED, code="EVC-0002")
    late = _sent_follow_up(session, other, sent_at=NOW - timedelta(hours=80))
    with pytest.raises(fu_errors.FollowUpClosedError):
        await service.respond(user, late.id, 4, "ok")


# ── us-057 service progress ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_progress_order_and_note(world):
    session, user, vehicle, owner, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=TODAY, status=BookingStatus.IN_PROGRESS)
    progress = ServiceProgressService(session)
    progress.on_booking_transition(booking, "START")
    session.commit()

    out = await progress.append(
        booking, owner.id, stage=ServiceStage.SERVICING, note=None, expected_current=ServiceStage.INSPECTING
    )
    assert out.current_stage == "SERVICING" and out.next_stages == ["WAITING_PARTS", "QUALITY_CHECK"]
    with pytest.raises(progress_errors.NoteRequiredError):
        await progress.append(
            booking, owner.id, stage=ServiceStage.WAITING_PARTS, note="short",
            expected_current=ServiceStage.SERVICING,
        )
    with pytest.raises(progress_errors.InvalidStageTransitionError):
        await progress.append(
            booking, owner.id, stage=ServiceStage.READY_FOR_PICKUP, note=None,
            expected_current=ServiceStage.SERVICING,
        )
    with pytest.raises(progress_errors.ProgressChangedError):
        await progress.append(
            booking, owner.id, stage=ServiceStage.QUALITY_CHECK, note=None,
            expected_current=ServiceStage.INSPECTING,
        )
