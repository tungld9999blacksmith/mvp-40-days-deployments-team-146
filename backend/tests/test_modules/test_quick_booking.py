"""Quick booking from the AI assistant (us-061 API-QB-01..04, HOOK-QB-01).

In-memory SQLite + fakeredis, as in ``test_booking_service``: the real
BookingService / UserVehicleService / CostEstimationService run underneath; the
chat gate and the message store are small fakes (no LLM, no pub/sub).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from sqlmodel import Session, select

from src.common.core.conversation import ChatMessage, Conversation, MessageRole
from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.booking_proposal import BookingProposal, BookingProposalStatus
from src.common.core.maintenance.booking_status_event import BookingStatusEvent
from src.common.core.workshop import BookingConfirmationMode
from src.common.core.workshop.service_price import ServicePrice
from src.infrastructure.messaging import AppendResult, MessageDto
from src.infrastructure.redis import RedisToolkit
from src.modules.booking.domain import BookingConfig, now_vn
from src.modules.booking.location import SimpleTextLocationFinder
from src.modules.booking.service import BookingService
from src.modules.cost_estimate.service import CostEstimationService
from src.modules.quick_booking import errors
from src.modules.quick_booking.cards import enrich_cards
from src.modules.quick_booking.domain import QuickBookingConfig
from src.modules.quick_booking.schemas import DeviceLocation, QuickBookingRequest, ReviseRequest
from src.modules.quick_booking.service import QuickBookingService
from src.modules.user_vehicle.domain import DueConfig
from src.modules.user_vehicle.service import UserVehicleService
from src.modules.vehicle_owner_onboarding.domain import (
    UserLocation,
    VehicleWarranty,
    WarrantyComponent,
    WarrantyStatus,
)
from tests._maintenance import add_booking, add_hours, add_workshop, make_session
from tests._user_vehicle import (
    MODEL_ID,
    RecordingScheduler,
    add_odometer,
    add_owner,
    add_rules,
    add_vehicle,
    mark_synced,
)

ANCHOR = (21.0, 105.8)


# ── fakes ────────────────────────────────────────────────────────────────
class FakeChat:
    def __init__(self) -> None:
        self.rate_limited: list[int] = []

    async def check_rate_limit(self, user_id: int) -> None:
        self.rate_limited.append(user_id)

    @asynccontextmanager
    async def run_lock(self, conversation_id):
        yield


class FakeMessages:
    """Writes chat messages into the test session (MessageService needs Postgres identity)."""

    def __init__(self, session: Session) -> None:
        self._db = session
        self._seq = 0

    async def append(self, conversation_id, role, content="", **kwargs) -> AppendResult:
        client_id = kwargs.get("client_message_id")
        if role == MessageRole.USER and client_id is not None:
            existing = self._db.exec(
                select(ChatMessage).where(
                    ChatMessage.conversation_id == conversation_id, ChatMessage.client_message_id == client_id
                )
            ).first()
            if existing is not None:
                return AppendResult(existing, created=False)
        self._seq += 1
        message = ChatMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            seq=self._seq,
            client_message_id=client_id,
            citations=[],
            tool_calls=[],
            refs=kwargs.get("refs") or {},
            card=kwargs.get("card"),
        )
        self._db.add(message)
        self._db.commit()
        self._db.refresh(message)
        return AppendResult(message, created=True)


# ── fixtures ─────────────────────────────────────────────────────────────
@pytest.fixture
def session():
    yield from make_session()


@pytest_asyncio.fixture
async def toolkit():
    redis = FakeAsyncRedis()
    tk = RedisToolkit(redis, key_prefix="test", default_cache_ttl=60)
    yield tk
    await tk.pubsub.stop()
    await tk.cache.write_back_buffer.stop(final_flush=False)
    await redis.flushall()
    await redis.aclose()


def _service(session, toolkit, *, messages: FakeMessages | None = None, config=QuickBookingConfig()):
    finder = SimpleTextLocationFinder()
    vehicles = UserVehicleService(session, RecordingScheduler(), config=DueConfig())

    def next_milestone(vehicle):
        m = vehicles.calculate(vehicle).next_milestone
        return m.odo_milestone_km if m else None

    return QuickBookingService(
        session,
        bookings=BookingService(session, toolkit, finder, config=BookingConfig()),
        vehicles=vehicles,
        estimates=CostEstimationService(session, finder, next_milestone),
        finder=finder,
        toolkit=toolkit,
        config=config,
        chat=FakeChat(),
        messages=messages or FakeMessages(session),
    )


def _today() -> date:
    return now_vn().date()


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, 28))


def _owner_with_vehicle(
    session, *, uid="uid-1", email="owner1@example.com", vin=None, ext=None, purchase=None, odo=12_500
):
    """VF6 with rules 12,000 km / 12 months; default ODO 12,500 km ⇒ OVERDUE whatever the date."""
    user = add_owner(session, uid=uid, email=email)
    kwargs = {"with_warranty": False}
    if vin:
        kwargs |= {"vin": vin, "external_vehicle_id": ext}
    vehicle = add_vehicle(session, user, **kwargs)
    purchase = purchase or _add_months(_today(), -6)
    session.add(
        VehicleWarranty(
            user_vehicle_id=vehicle.id,
            external_warranty_id=f"WAR-{vehicle.id.hex[:6]}",
            component=WarrantyComponent.BATTERY,
            start_date=purchase,
            end_date=purchase + timedelta(days=3650),
            km_limit=200_000,
            oem_status=WarrantyStatus.ACTIVE,
        )
    )
    session.commit()
    if odo is not None:
        add_odometer(session, vehicle, odo, recorded_at=datetime.now(UTC))
    mark_synced(session, vehicle)
    conversation = Conversation(user_id=user.user_id, user_vehicle_id=vehicle.id, title="Chat")
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return user, vehicle, conversation


def _workshop(
    session, name, km_north: float | None, *, mode=BookingConfirmationMode.AUTO, techs=4, region="Ha Noi", hours=True
):
    workshop = add_workshop(session, name=name, mode=mode, total_technicians=techs, region=region)
    if km_north is not None:
        workshop.latitude = Decimal(str(round(ANCHOR[0] + km_north / 111.0, 6)))
        workshop.longitude = Decimal(str(ANCHOR[1]))
        session.add(workshop)
        session.commit()
    if hours:
        add_hours(session, workshop, open_at=time(0), close_at=time(23))
    return workshop


def _request(*, location=True, province=None) -> QuickBookingRequest:
    return QuickBookingRequest(
        clientMessageId=uuid4(),
        location=DeviceLocation(lat=ANCHOR[0], lng=ANCHOR[1]) if location else None,
        province=province,
    )


def _bookings(session, vehicle) -> list[Booking]:
    return list(session.exec(select(Booking).where(Booking.user_vehicle_id == vehicle.id)).all())


async def _propose(service, user, conversation, **kwargs):
    data = await service.propose_quick(user.user_id, conversation.id, _request(**kwargs))
    return data.assistantMessage


def _proposal_id(message: MessageDto) -> UUID:
    return UUID(message.card["proposalId"])


# ── API-QB-01 ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_chip_builds_a_card_and_books_nothing(session, toolkit):
    """AC-1502: the chip only proposes; no booking, no slot hold."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)

    message = await _propose(_service(session, toolkit), user, conversation)

    assert message.card["type"] == "BOOKING_PROPOSAL"
    assert message.card["status"] == "PROPOSED"
    assert message.card["booking"] is None
    assert _bookings(session, vehicle) == []
    keys = [k.decode() for k in await toolkit.redis.keys("*")]
    assert not [k for k in keys if "booking:vehicle" in k or "cft" in k]


@pytest.mark.asyncio
async def test_milestone_is_the_service_result(session, toolkit):
    """AC-1503: milestone, due date, status and items come from get_maintenance_status."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)

    message = await _propose(service, user, conversation)
    status = UserVehicleService(session, RecordingScheduler(), config=DueConfig()).get_maintenance_status(vehicle)

    milestone = message.card["milestone"]
    assert milestone["odoMilestoneKm"] == status.next_milestone.odo_milestone_km == 12_000
    assert milestone["dueDate"] == status.next_milestone.due_date.isoformat()
    assert milestone["dueStatus"] == status.due_status == "OVERDUE"
    assert [i["itemCode"] for i in milestone["items"]] == [i.item_code for i in status.next_milestone.items]
    assert "quá mốc" in message.card["reason"]


@pytest.mark.asyncio
async def test_workshops_ranked_by_distance_not_preference(session, toolkit):
    """AC-1504: nearest workshop with a slot first; the preferred one gets no boost; full ones are skipped."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast Closed", 1, hours=False)  # nearest, but never open
    near = _workshop(session, "VinFast Near", 2)
    preferred = _workshop(session, "VinFast Preferred", 5)
    far = _workshop(session, "VinFast Far", 9)
    user.preferred_workshop_id = preferred.id
    session.add(user)
    session.commit()

    card = (await _propose(_service(session, toolkit), user, conversation)).card

    assert card["primary"]["workshopId"] == str(near.id)
    assert [a["workshopId"] for a in card["alternatives"]] == [str(preferred.id), str(far.id)]
    assert card["primary"]["distanceKm"] == pytest.approx(2, abs=0.05)
    assert card["alternatives"][0]["isPreferred"] is True


@pytest.mark.asyncio
async def test_region_only_never_shows_a_distance(session, toolkit):
    """AC-1505: a province anchor gives no km at all."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast Ha Noi", 2, region="Ha Noi")

    card = (await _propose(_service(session, toolkit), user, conversation, location=False, province="Ha Noi")).card

    assert card["locationBasis"] == "PROVINCE"
    assert card["locationLabel"] == "Xưởng trong khu vực Ha Noi"
    assert card["primary"]["distanceKm"] is None
    assert all(a["distanceKm"] is None for a in card["alternatives"])


@pytest.mark.asyncio
async def test_profile_location_is_used_when_the_device_gives_none(session, toolkit):
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    near = _workshop(session, "VinFast Near", 2)
    _workshop(session, "VinFast Far", 9)
    session.add(
        UserLocation(
            user_id=user.user_id,
            is_primary=True,
            address_line="1 Tran Duy Hung",
            province="Ha Noi",
            latitude=Decimal(str(ANCHOR[0])),
            longitude=Decimal(str(ANCHOR[1])),
        )
    )
    session.commit()

    card = (await _propose(_service(session, toolkit), user, conversation, location=False)).card

    assert card["locationBasis"] == "PROFILE"
    assert card["primary"]["workshopId"] == str(near.id)


@pytest.mark.asyncio
async def test_no_location_asks_for_the_area(session, toolkit):
    """AF-1501."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast Ha Noi", 2, region="Ha Noi")
    _workshop(session, "VinFast Da Nang", 600, region="Da Nang")

    message = await _propose(_service(session, toolkit), user, conversation, location=False)

    assert message.card == {"type": "QUICK_BOOKING_NEED_LOCATION", "version": 1, "regions": ["Da Nang", "Ha Noi"]}
    assert session.exec(select(BookingProposal)).all() == []


@pytest.mark.asyncio
async def test_open_booking_blocks_a_new_proposal(session, toolkit):
    """EF-1501 (BR-013)."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    workshop = _workshop(session, "VinFast A", 2)
    booking = add_booking(session, user, vehicle, workshop, d=_today() + timedelta(days=5))

    message = await _propose(_service(session, toolkit), user, conversation)

    assert message.card is None
    assert message.refs["bookingId"] == str(booking.id)
    assert "đã có lịch hẹn" in message.content


@pytest.mark.asyncio
async def test_missing_oem_data_is_explained_not_guessed(session, toolkit):
    """EF-1502: no history sync yet ⇒ UNKNOWN, no card."""
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    conversation = Conversation(user_id=user.user_id, user_vehicle_id=vehicle.id)
    session.add(conversation)
    session.commit()
    _workshop(session, "VinFast A", 2)

    message = await _propose(_service(session, toolkit), user, conversation)

    assert message.card is None
    assert "dữ liệu xe từ hãng" in message.content


@pytest.mark.asyncio
async def test_not_due_and_far_from_due_makes_no_proposal(session, toolkit):
    """EF-1504: NORMAL with the due date beyond the look-ahead."""
    user, vehicle, conversation = _owner_with_vehicle(session, purchase=_add_months(_today(), -1), odo=1_000)
    add_rules(session)
    _workshop(session, "VinFast A", 2)

    message = await _propose(_service(session, toolkit), user, conversation)

    assert message.card is None
    assert "chưa đến hạn" in message.content


@pytest.mark.asyncio
async def test_not_due_but_close_proposes_near_the_due_date(session, toolkit):
    """BR-1504 NORMAL: slot within [due − 7 days, due]."""
    purchase = _today() + timedelta(days=40) - timedelta(days=365)
    user, vehicle, conversation = _owner_with_vehicle(session, purchase=purchase, odo=1_000)
    add_rules(session)
    _workshop(session, "VinFast A", 2)

    card = (await _propose(_service(session, toolkit), user, conversation)).card

    due = date.fromisoformat(card["milestone"]["dueDate"])
    assert card["milestone"]["dueStatus"] == "NORMAL"
    slot_day = date.fromisoformat(card["primary"]["date"])
    assert due - timedelta(days=7) <= slot_day <= due


@pytest.mark.asyncio
async def test_a_second_chip_supersedes_the_first_proposal(session, toolkit):
    """BR-1508."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)

    first = await _propose(service, user, conversation)
    second = await _propose(service, user, conversation)

    old = session.get(BookingProposal, _proposal_id(first))
    assert old.status == BookingProposalStatus.SUPERSEDED
    assert old.superseded_reason == "NEW_PROPOSAL"
    assert session.get(BookingProposal, _proposal_id(second)).status == BookingProposalStatus.PROPOSED


@pytest.mark.asyncio
async def test_estimate_on_the_card_uses_the_workshop_price(session, toolkit):
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    workshop = _workshop(session, "VinFast A", 2)
    for code, price in (("BRAKE_INSPECTION", 350_000), ("BATTERY_CHECK", 0)):
        session.add(
            ServicePrice(workshop_id=workshop.id, model_id=MODEL_ID, item_code=code, item_name=code, price=price)
        )
    session.commit()

    card = (await _propose(_service(session, toolkit), user, conversation)).card

    assert Decimal(card["primary"]["estimate"]["chargeableTotal"]) == 350_000
    assert card["primary"]["estimate"]["hasReferencePrice"] is False


# ── API-QB-02 ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_confirm_at_an_auto_workshop_books_confirmed_with_a_code(session, toolkit):
    """AC-1509 (AUTO) + BR-1510 source / source_message_id."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2, mode=BookingConfirmationMode.AUTO)
    service = _service(session, toolkit)
    message = await _propose(service, user, conversation)

    result = await service.confirm(user.user_id, conversation.id, _proposal_id(message))

    assert result.booking.status == "CONFIRMED"
    assert result.booking.bookingCode.startswith("EVC-")
    assert result.booking.bookingCode in result.message.content
    assert result.message.refs == {"bookingId": str(result.booking.bookingId)}
    [booking] = _bookings(session, vehicle)
    assert booking.source_message_id == message.id
    assert booking.odo_milestone == 12_000
    created = session.exec(
        select(BookingStatusEvent).where(
            BookingStatusEvent.booking_id == booking.id, BookingStatusEvent.from_status.is_(None)
        )
    ).one()
    assert created.source == "CHAT"


@pytest.mark.asyncio
async def test_confirm_at_a_manual_workshop_waits_without_a_code(session, toolkit):
    """AC-1509 (MANUAL)."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2, mode=BookingConfirmationMode.MANUAL)
    service = _service(session, toolkit)
    message = await _propose(service, user, conversation)

    result = await service.confirm(user.user_id, conversation.id, _proposal_id(message))

    assert result.booking.status == "PENDING"
    assert result.booking.bookingCode is None
    assert "Xưởng sẽ xác nhận" in result.message.content
    assert "Mã đặt lịch" not in result.message.content


@pytest.mark.asyncio
async def test_confirm_twice_in_a_row_and_in_parallel_books_once(session, toolkit):
    """AC-1507."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)
    proposal_id = _proposal_id(await _propose(service, user, conversation))

    first, second = await asyncio.gather(
        service.confirm(user.user_id, conversation.id, proposal_id),
        service.confirm(user.user_id, conversation.id, proposal_id),
    )
    third = await service.confirm(user.user_id, conversation.id, proposal_id)

    assert len(_bookings(session, vehicle)) == 1
    assert first.booking.bookingId == second.booking.bookingId == third.booking.bookingId
    assert [first.replayed, second.replayed].count(True) == 1
    assert third.replayed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["superseded", "cancelled", "expired"])
async def test_inactive_proposals_never_book(session, toolkit, how):
    """AC-1506."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)
    proposal_id = _proposal_id(await _propose(service, user, conversation))
    if how == "superseded":
        await _propose(service, user, conversation)
    elif how == "cancelled":
        await service.cancel(user.user_id, conversation.id, proposal_id)
    else:
        proposal = session.get(BookingProposal, proposal_id)
        proposal.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.add(proposal)
        session.commit()

    expected = errors.ProposalExpiredError if how == "expired" else errors.ProposalInactiveError
    with pytest.raises(expected):
        await service.confirm(user.user_id, conversation.id, proposal_id)
    assert _bookings(session, vehicle) == []


@pytest.mark.asyncio
async def test_another_conversation_or_owner_cannot_confirm(session, toolkit):
    """AC-1506 / BR-1509."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)
    proposal_id = _proposal_id(await _propose(service, user, conversation))
    other_chat = Conversation(user_id=user.user_id, user_vehicle_id=vehicle.id)
    session.add(other_chat)
    session.commit()
    stranger, _, stranger_chat = _owner_with_vehicle(
        session, uid="uid-2", email="other@example.com", vin="RLLV00000000000B2", ext="VEH-2"
    )

    with pytest.raises(errors.ProposalNotFoundError):
        await service.confirm(user.user_id, other_chat.id, proposal_id)
    with pytest.raises(errors.ProposalNotFoundError):
        await service.confirm(stranger.user_id, stranger_chat.id, proposal_id)
    with pytest.raises(errors.QuickBookingError) as exc:
        await service.confirm(stranger.user_id, conversation.id, proposal_id)
    assert exc.value.code == "CONVERSATION_NOT_FOUND"
    assert _bookings(session, vehicle) == []


@pytest.mark.asyncio
async def test_slot_taken_before_confirm_proposes_again(session, toolkit):
    """AC-1508: no booking, a new card, and the new card books."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    workshop = _workshop(session, "VinFast A", 2, techs=1)
    _workshop(session, "VinFast B", 5)
    messages = FakeMessages(session)
    service = _service(session, toolkit, messages=messages)
    message = await _propose(service, user, conversation)
    primary = message.card["primary"]
    other, other_vehicle, _ = _owner_with_vehicle(
        session, uid="uid-2", email="other@example.com", vin="RLLV00000000000B2", ext="VEH-2"
    )
    add_booking(
        session,
        other,
        other_vehicle,
        workshop,
        d=date.fromisoformat(primary["date"]),
        t=time.fromisoformat(primary["timeSlot"]),
        code="EVC-OTHER",
    )

    with pytest.raises(errors.ProposalSlotFullError) as exc:
        await service.confirm(user.user_id, conversation.id, _proposal_id(message))

    assert _bookings(session, vehicle) == []
    old = session.get(BookingProposal, _proposal_id(message))
    assert (old.status, old.superseded_reason) == (BookingProposalStatus.SUPERSEDED, "SLOT_FULL")
    new_id = UUID(exc.value.details["proposalId"])
    assert exc.value.details["message"]["card"]["proposalId"] == str(new_id)
    result = await service.confirm(user.user_id, conversation.id, new_id)
    assert result.status == "CONFIRMED"
    assert len(_bookings(session, vehicle)) == 1


@pytest.mark.asyncio
async def test_lost_proposal_update_is_repaired_on_the_next_confirm(session, toolkit):
    """A confirm created the booking but stopped before marking the proposal (API §5.2 step 6)."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    workshop = _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)
    message = await _propose(service, user, conversation)
    proposal = session.get(BookingProposal, _proposal_id(message))
    booking = add_booking(session, user, vehicle, workshop, d=proposal.booking_date, t=proposal.time_slot)
    booking.source_message_id = message.id
    session.add(booking)
    session.commit()

    result = await service.confirm(user.user_id, conversation.id, proposal.id)

    assert result.replayed is True
    assert result.booking.bookingId == booking.id
    assert session.get(BookingProposal, proposal.id).status == BookingProposalStatus.CONFIRMED


# ── API-QB-03 / QB-04 ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_revise_to_an_alternative_needs_a_new_confirmation(session, toolkit):
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    other = _workshop(session, "VinFast B", 5)
    service = _service(session, toolkit)
    message = await _propose(service, user, conversation)
    alternative = next(a for a in message.card["alternatives"] if a["workshopId"] == str(other.id))

    data = await service.revise(
        user.user_id,
        conversation.id,
        _proposal_id(message),
        ReviseRequest(
            workshopId=other.id,
            date=date.fromisoformat(alternative["date"]),
            timeSlot=time.fromisoformat(alternative["timeSlot"]),
        ),
    )

    assert data.message.card["primary"]["workshopId"] == str(other.id)
    assert session.get(BookingProposal, _proposal_id(message)).superseded_reason == "REVISED"
    assert _bookings(session, vehicle) == []
    with pytest.raises(errors.ProposalInactiveError):
        await service.confirm(user.user_id, conversation.id, _proposal_id(message))


@pytest.mark.asyncio
async def test_revise_rejects_a_workshop_not_offered_and_a_too_early_slot(session, toolkit):
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    workshop = _workshop(session, "VinFast A", 2)
    stranger = _workshop(session, "VinFast Never Offered", None, region="Hue", hours=False)
    service = _service(session, toolkit)
    proposal_id = _proposal_id(await _propose(service, user, conversation))
    soon = now_vn() + timedelta(minutes=30)

    with pytest.raises(errors.ReviseWorkshopNotOfferedError):
        await service.revise(
            user.user_id,
            conversation.id,
            proposal_id,
            ReviseRequest(workshopId=stranger.id, date=_today() + timedelta(days=3), timeSlot=time(9)),
        )
    with pytest.raises(errors.SlotTooSoonError):
        await service.revise(
            user.user_id,
            conversation.id,
            proposal_id,
            ReviseRequest(workshopId=workshop.id, date=soon.date(), timeSlot=time(soon.hour)),
        )


@pytest.mark.asyncio
async def test_cancel_books_nothing_is_idempotent_and_refuses_a_booked_proposal(session, toolkit):
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)
    first = _proposal_id(await _propose(service, user, conversation))

    assert (await service.cancel(user.user_id, conversation.id, first)).status == "CANCELLED"
    assert (await service.cancel(user.user_id, conversation.id, first)).status == "CANCELLED"
    assert _bookings(session, vehicle) == []

    second = _proposal_id(await _propose(service, user, conversation))
    await service.confirm(user.user_id, conversation.id, second)
    with pytest.raises(errors.ProposalAlreadyConfirmedError):
        await service.cancel(user.user_id, conversation.id, second)


# ── HOOK-QB-01 ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_reopened_conversation_shows_the_live_state(session, toolkit):
    """AC-1510 / AC-1509: status and booking are read live; MANUAL → confirmed later shows the code."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2, mode=BookingConfirmationMode.MANUAL)
    service = _service(session, toolkit)
    message = await _propose(service, user, conversation)
    [later] = enrich_cards(session, [message], now=datetime.now(UTC) + timedelta(hours=1))
    assert later.card["status"] == "EXPIRED"  # read-only: the row itself is untouched
    await service.confirm(user.user_id, conversation.id, _proposal_id(message))
    stored = session.get(ChatMessage, message.id)
    assert "status" not in stored.card  # the stored snapshot stays static

    [pending] = enrich_cards(session, [MessageDto.from_message(stored)])
    assert pending.card["status"] == "CONFIRMED"
    assert (pending.card["booking"]["status"], pending.card["booking"]["bookingCode"]) == ("PENDING", None)

    booking = _bookings(session, vehicle)[0]
    booking.status = BookingStatus.CONFIRMED
    session.add(booking)
    session.commit()
    [confirmed] = enrich_cards(session, [MessageDto.from_message(stored)])
    assert confirmed.card["booking"]["bookingCode"] == booking.booking_code


# ── agent: no write tool ─────────────────────────────────────────────────
def test_the_agent_has_no_tool_that_books():
    """BR-1514 / AC-1506."""
    from src.agents.tools import CUSTOMER_AGENT_TOOLS

    names = {t.name for t in CUSTOMER_AGENT_TOOLS}
    assert "propose_booking" in names
    assert not names & {"create_booking_draft", "create_booking", "cancel_booking", "reschedule_booking"}


def test_chat_turn_takes_the_card_from_the_tool_artifact():
    """TOOL-QB-01: ChatService reads the card from the ToolMessage artifact (the LLM never sees it)."""
    from langchain_core.messages import ToolMessage

    from src.modules.conversation.service import _proposal_card

    card = {"type": "BOOKING_PROPOSAL", "proposalId": str(uuid4())}
    assert _proposal_card(ToolMessage(content='{"status": "PROPOSED"}', tool_call_id="1", artifact=card)) == card
    assert _proposal_card(ToolMessage(content='{"status": "ERROR"}', tool_call_id="1")) is None


@pytest.mark.asyncio
async def test_a_chip_during_the_confirm_does_not_lose_the_booking(session, toolkit):
    """Race: the chip supersedes the proposal while its booking is being created."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)
    proposal_id = _proposal_id(await _propose(service, user, conversation))
    real_create_hold = service._bookings.create_hold

    async def create_hold_while_chip_runs(*args, **kwargs):
        proposal = session.get(BookingProposal, proposal_id)
        proposal.status = BookingProposalStatus.SUPERSEDED
        proposal.superseded_reason = "NEW_PROPOSAL"
        session.add(proposal)
        session.commit()
        return await real_create_hold(*args, **kwargs)

    service._bookings.create_hold = create_hold_while_chip_runs

    result = await service.confirm(user.user_id, conversation.id, proposal_id)

    assert result.status == "CONFIRMED"
    proposal = session.get(BookingProposal, proposal_id)
    assert (proposal.status, proposal.superseded_reason) == (BookingProposalStatus.CONFIRMED, None)
    assert len(_bookings(session, vehicle)) == 1


@pytest.mark.asyncio
async def test_province_without_accents_matches_and_regions_are_deduplicated(session, toolkit):
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    hanoi = _workshop(session, "VinFast Long Bien", None, region="Hà Nội")
    _workshop(session, "VinFast Cau Giay", None, region="Ha Noi")
    service = _service(session, toolkit)

    card = (await _propose(service, user, conversation, location=False, province="ha noi")).card
    assert card["primary"]["workshopId"] in {str(hanoi.id)} | {a["workshopId"] for a in card["alternatives"]}

    assert service._regions() == ["Ha Noi"]


@pytest.mark.asyncio
async def test_scan_of_fully_booked_workshops_stays_a_few_queries(session, toolkit):
    """Worst case (5 workshops × 14 days, all full): a bounded number of SQL statements, not one per slot."""
    from sqlalchemy import event

    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    for i in range(5):
        workshop = _workshop(session, f"VinFast Full {i}", i + 1, techs=2)
        workshop.emergency_slots_reserved = 2  # no capacity left on any slot
        session.add(workshop)
    session.commit()
    service = _service(session, toolkit)
    statements: list[str] = []
    engine = session.get_bind()

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        message = await _propose(service, user, conversation)
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert message.card is None
    assert "không còn khung giờ" in message.content
    assert len(statements) < 60, len(statements)


@pytest.mark.asyncio
async def test_confirm_and_cancel_at_once_have_one_outcome(session, toolkit):
    """The proposal lock serialises them: booked and CONFIRMED, or CANCELLED with no booking."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)
    proposal_id = _proposal_id(await _propose(service, user, conversation))

    confirm, cancel = await asyncio.gather(
        service.confirm(user.user_id, conversation.id, proposal_id),
        service.cancel(user.user_id, conversation.id, proposal_id),
        return_exceptions=True,
    )

    status = session.get(BookingProposal, proposal_id).status
    if status == BookingProposalStatus.CONFIRMED:
        assert isinstance(cancel, errors.ProposalAlreadyConfirmedError)
        assert len(_bookings(session, vehicle)) == 1
    else:
        assert status == BookingProposalStatus.CANCELLED
        assert isinstance(confirm, errors.ProposalInactiveError)
        assert _bookings(session, vehicle) == []


@pytest.mark.asyncio
async def test_cancelling_an_expired_proposal_reports_expired(session, toolkit):
    """Expiry wins over cancel (BR-ENT-1501)."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)
    proposal_id = _proposal_id(await _propose(service, user, conversation))
    proposal = session.get(BookingProposal, proposal_id)
    proposal.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.add(proposal)
    session.commit()

    with pytest.raises(errors.ProposalExpiredError):
        await service.cancel(user.user_id, conversation.id, proposal_id)
    assert session.get(BookingProposal, proposal_id).status == BookingProposalStatus.EXPIRED


@pytest.mark.asyncio
async def test_a_card_whose_booking_was_cancelled_never_books_again(session, toolkit):
    """Lost proposal update + the booking later cancelled: the same card replays, it does not book twice."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    workshop = _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)
    message = await _propose(service, user, conversation)
    proposal = session.get(BookingProposal, _proposal_id(message))
    booking = add_booking(
        session, user, vehicle, workshop, d=proposal.booking_date, t=proposal.time_slot, status=BookingStatus.CANCELLED
    )
    booking.source_message_id = message.id
    session.add(booking)
    session.commit()

    result = await service.confirm(user.user_id, conversation.id, proposal.id)

    assert result.replayed is True
    assert result.booking.bookingId == booking.id
    assert len(_bookings(session, vehicle)) == 1


@pytest.mark.asyncio
async def test_resending_the_chip_returns_its_own_answer(session, toolkit):
    """Replay finds the answer by refs.inReplyTo, not merely the next assistant message."""
    user, vehicle, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    messages = FakeMessages(session)
    service = _service(session, toolkit, messages=messages)
    request = _request()
    first = await service.propose_quick(user.user_id, conversation.id, request)
    # Some unrelated assistant message lands right after the chip message.
    unrelated = (await messages.append(conversation.id, MessageRole.ASSISTANT, "Tin khác")).message
    first_reply = session.get(ChatMessage, first.assistantMessage.id)
    first_reply.seq = 100  # move the real answer out of the way, then put the unrelated one right after the chip
    session.commit()
    unrelated.seq = first.userMessage.seq + 1
    session.commit()

    again = await service.propose_quick(user.user_id, conversation.id, request)

    assert again.replayed is True
    assert again.assistantMessage.id == first.assistantMessage.id
    assert again.assistantMessage.refs["inReplyTo"] == str(first.userMessage.id)


@pytest.mark.asyncio
async def test_status_read_runs_off_the_event_loop(session, toolkit, monkeypatch):
    """In demo mode the status read may seed an ODO (a blocking DB write)."""
    import threading

    user, _, conversation = _owner_with_vehicle(session)
    add_rules(session)
    _workshop(session, "VinFast A", 2)
    service = _service(session, toolkit)
    original = service._vehicles.get_maintenance_status
    threads = []

    def record_thread(vehicle):
        threads.append(threading.get_ident())
        return original(vehicle)

    monkeypatch.setattr(service._vehicles, "get_maintenance_status", record_thread)
    await _propose(service, user, conversation)

    assert threads and threading.get_ident() not in threads
