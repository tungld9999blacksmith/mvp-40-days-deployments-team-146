"""Customer-agent tools against the real services (AI-004, TOOL-VEH-001, TOOL-301).

In-memory SQLite + fakeredis, as in ``test_booking_service``: the tools open
their session and Redis toolkit through ``_services``, patched here. The owner
and the vehicle always come from the run config, never from tool arguments.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import time, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from sqlmodel import select

from src.agents.graph import build_graph
from src.agents.tools import (
    _services,
    estimate_service_cost,
    find_workshops,
    get_available_slots,
    get_due_maintenance,
    propose_booking,
)
from src.agents.tools.dependency import AgentToolServices, build_customer_agent_tools
from src.common.core.conversation import Conversation
from src.common.core.maintenance.booking import Booking
from src.common.core.maintenance.booking_proposal import BookingProposal
from src.common.core.workshop import BookingConfirmationMode
from src.common.core.workshop.service_price import ServicePrice
from src.infrastructure.redis import RedisToolkit
from src.modules.booking.dependency import get_booking_config, get_booking_service
from src.modules.booking.domain import now_vn
from src.modules.booking.location import get_location_finder
from src.modules.quick_booking.dependency import build_quick_booking_service
from tests._maintenance import add_booking, add_hours, add_workshop, make_session
from tests._user_vehicle import MODEL_ID, add_odometer, add_owner, add_rules, add_vehicle, mark_synced


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


@pytest.fixture(autouse=True, params=["legacy", "injected"])
def real_services_on_test_db(request, monkeypatch, session, toolkit):
    @contextmanager
    def open_session():
        yield session

    if request.param == "legacy":
        monkeypatch.setattr(_services, "open_session", open_session)
        monkeypatch.setattr(_services, "redis_toolkit", lambda: toolkit)
    else:
        services = AgentToolServices(
            open_session=open_session,
            user_vehicle_service=_services.user_vehicle_service,
            cost_estimation_service=_services.cost_estimation_service,
            booking_service=lambda db: get_booking_service(db, toolkit, get_location_finder(), get_booking_config()),
            quick_booking_service=lambda db: build_quick_booking_service(db, toolkit),
            rag_pipeline=Mock(side_effect=AssertionError("RAG is not used by these business-tool tests")),
        )
        # Exercise every assertion with the injected tools, while leaving the
        # production DB/Redis providers untouched. Accidental global access fails.
        for bound_tool in build_customer_agent_tools(services):
            if bound_tool.name in globals():
                monkeypatch.setitem(globals(), bound_tool.name, bound_tool)


@pytest.fixture
def day():
    return now_vn().date() + timedelta(days=3)


def _run(user, vehicle) -> dict:
    return {"configurable": {"user_id": user.user_id, "user_vehicle_id": str(vehicle.id)}}


def _price(session, workshop, code: str, price: int) -> None:
    session.add(ServicePrice(workshop_id=workshop.id, model_id=MODEL_ID, item_code=code, item_name=code, price=price))
    session.commit()


# ── get_due_maintenance ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_graph_delivers_trusted_chat_context_to_tools(session):
    """The graph must route session identity into its bound tools unchanged."""
    import json

    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    add_odometer(session, vehicle, 11_500)
    mark_synced(session, vehicle)
    llm = Mock()
    llm.bind_tools.return_value = llm
    llm.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(content="", tool_calls=[{"name": "get_due_maintenance", "args": {}, "id": "due-1"}]),
            AIMessage(content="Mốc bảo dưỡng kế tiếp là 12.000 km."),
        ]
    )
    runner = build_graph(llm=llm, tools=[get_due_maintenance], checkpointer=MemorySaver())
    config = _run(user, vehicle)
    config["configurable"]["thread_id"] = str(uuid4())

    result = await runner.ainvoke({"query": "Xe tôi cần bảo dưỡng gì?"}, config=config)

    tool_message = next(message for message in result["messages"] if isinstance(message, ToolMessage))
    data = json.loads(tool_message.content)
    assert data["user_vehicle_id"] == str(vehicle.id)
    assert data["odometer"]["odo_km"] == 11_500
    assert data["next_milestone"]["odo_milestone_km"] == 12_000
    assert result["messages"][-1].content == "Mốc bảo dưỡng kế tiếp là 12.000 km."


def test_due_maintenance_reads_the_session_vehicle(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    add_odometer(session, vehicle, 11_500)
    mark_synced(session, vehicle)

    result = get_due_maintenance.invoke({}, config=_run(user, vehicle))

    assert result["user_vehicle_id"] == str(vehicle.id)
    assert result["odometer"]["odo_km"] == 11_500
    assert result["next_milestone"]["odo_milestone_km"] == 12_000
    assert {i["item_code"] for i in result["next_milestone"]["items"]} == {"BRAKE_INSPECTION", "BATTERY_CHECK"}


def test_tools_refuse_without_chat_context(session):
    result = get_due_maintenance.invoke({})
    assert result["status"] == "ERROR"
    assert result["error_code"] == "CHAT_CONTEXT_MISSING"


def test_tools_never_reveal_another_owners_vehicle(session):
    owner = add_owner(session)
    vehicle = add_vehicle(session, owner)
    stranger = add_owner(session, uid="uid-2", email="other@example.com")

    result = get_due_maintenance.invoke({}, config=_run(stranger, vehicle))

    assert result["error_code"] == "VEHICLE_NOT_FOUND"


# ── estimate_service_cost ───────────────────────────────────────────────
def test_estimate_uses_the_workshop_price_list(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    workshop = add_workshop(session)
    _price(session, workshop, "BRAKE_INSPECTION", 350_000)

    result = estimate_service_cost.invoke(
        {"odo_milestone": 12_000, "workshop_id": str(workshop.id)}, config=_run(user, vehicle)
    )

    assert result["status"] == "READY"
    assert result["workshop"]["workshop_id"] == str(workshop.id)
    brake = next(i for i in result["items"] if i["item_code"] == "BRAKE_INSPECTION")
    assert brake["price_source"] == "WORKSHOP_PRICE"
    assert float(brake["price"]) == 350_000


def test_estimate_unknown_milestone_lists_valid_ones(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    workshop = add_workshop(session)

    result = estimate_service_cost.invoke(
        {"odo_milestone": 5_000, "workshop_id": str(workshop.id)}, config=_run(user, vehicle)
    )

    assert result["error_code"] == "MILESTONE_NOT_FOUND"
    assert result["details"]["validMilestones"] == [12_000, 24_000]


# ── find_workshops / get_available_slots ────────────────────────────────
@pytest.mark.asyncio
async def test_find_workshops_returns_active_workshops_of_the_area(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    hanoi = add_workshop(session, name="VinFast Long Bien", region="Ha Noi")
    add_workshop(session, name="VinFast Son Tra", region="Da Nang")

    result = await find_workshops.ainvoke({"area_or_address": "Ha Noi"}, config=_run(user, vehicle))

    assert [w["workshop_id"] for w in result["workshops"]] == [str(hanoi.id)]


@pytest.mark.asyncio
async def test_available_slots_follow_operating_hours_and_capacity(session, day):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session, total_technicians=1)
    add_hours(session, workshop, open_at=time(8), close_at=time(11))
    other = add_owner(session, uid="uid-2", email="other@example.com")
    other_vehicle = add_vehicle(session, other, vin="RLLV00000000000B2", external_vehicle_id="VEH-2")
    add_booking(session, other, other_vehicle, workshop, d=day, t=time(9))

    result = await get_available_slots.ainvoke(
        {"workshop_id": str(workshop.id), "target_date": day.isoformat()}, config=_run(user, vehicle)
    )

    assert [(s["time_slot"], s["available"]) for s in result["slots"]] == [
        ("08:00:00", True),
        ("09:00:00", False),
        ("10:00:00", True),
    ]


@pytest.mark.asyncio
async def test_available_slots_rejects_a_non_iso_date(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)

    result = await get_available_slots.ainvoke(
        {"workshop_id": str(workshop.id), "target_date": "Thứ Bảy"}, config=_run(user, vehicle)
    )

    assert result["error_code"] == "INVALID_DATE"


# ── propose_booking (us-061 TOOL-QB-01) ─────────────────────────────────
def _chat(session, user, vehicle) -> Conversation:
    conversation = Conversation(user_id=user.user_id, user_vehicle_id=vehicle.id)
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


async def _propose(user, vehicle, conversation, workshop, day, slot="09:00"):
    """Invoke as a tool call so the ToolMessage carries the card artifact."""
    config = _run(user, vehicle)
    config["configurable"]["conversation_id"] = str(conversation.id)
    return await propose_booking.ainvoke(
        {
            "type": "tool_call",
            "id": "call-1",
            "name": "propose_booking",
            "args": {
                "workshop_id": str(workshop.id),
                "booking_date": day.isoformat(),
                "time_slot": slot,
                "odo_milestone": 12_000,
            },
        },
        config=config,
    )


@pytest.mark.asyncio
async def test_propose_booking_makes_a_proposal_never_a_booking(session, day):
    """BR-1514: the agent proposes; only the card's confirm button books."""
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    add_odometer(session, vehicle, 11_500)
    mark_synced(session, vehicle)
    workshop = add_workshop(session, mode=BookingConfirmationMode.AUTO)
    add_hours(session, workshop)
    conversation = _chat(session, user, vehicle)

    message = await _propose(user, vehicle, conversation, workshop, day)

    assert '"status": "PROPOSED"' in message.content
    card = message.artifact
    assert card["type"] == "BOOKING_PROPOSAL"
    assert (card["primary"]["date"], card["primary"]["timeSlot"]) == (day.isoformat(), "09:00")
    [proposal] = session.exec(select(BookingProposal)).all()
    assert card["proposalId"] == str(proposal.id)
    assert (proposal.source, proposal.status.value) == ("CHAT_AGENT", "proposed")
    assert session.exec(select(Booking)).all() == []


@pytest.mark.asyncio
async def test_propose_booking_on_a_full_slot_returns_alternatives(session, day):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session, total_technicians=1)
    add_hours(session, workshop)
    other = add_owner(session, uid="uid-2", email="other@example.com")
    other_vehicle = add_vehicle(session, other, vin="RLLV00000000000B2", external_vehicle_id="VEH-2")
    add_booking(session, other, other_vehicle, workshop, d=day, t=time(9))
    conversation = _chat(session, user, vehicle)

    message = await _propose(user, vehicle, conversation, workshop, day)

    assert '"error_code": "SLOT_FULL"' in message.content
    assert '"alternatives"' in message.content
    assert message.artifact is None
    assert session.exec(select(BookingProposal)).all() == []


@pytest.mark.asyncio
async def test_propose_booking_needs_the_chat_conversation(session, day):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)

    result = await propose_booking.ainvoke(
        {"workshop_id": str(workshop.id), "booking_date": day.isoformat(), "time_slot": "09:00"},
        config=_run(user, vehicle),
    )

    assert result["error_code"] == "CHAT_CONTEXT_MISSING"
    assert session.exec(select(BookingProposal)).all() == []


@pytest.mark.asyncio
async def test_propose_booking_refuses_when_the_vehicle_already_has_a_booking(session, day):
    """BR-013 is reported at proposal time, not only at the confirm."""
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    add_hours(session, workshop)
    add_booking(session, user, vehicle, workshop, d=day, t=time(14))
    conversation = _chat(session, user, vehicle)

    message = await _propose(user, vehicle, conversation, workshop, day)

    assert '"error_code": "OPEN_BOOKING_EXISTS"' in message.content
    assert session.exec(select(BookingProposal)).all() == []
