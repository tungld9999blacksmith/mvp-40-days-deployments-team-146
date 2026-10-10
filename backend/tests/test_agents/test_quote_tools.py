"""Quote tools of the customer agent (AI-005 TOOL-501 / TOOL-503) and the live CARD-QUOTE.

Same setup as ``test_ev_care_tools``: in-memory SQLite, real services, the owner
and vehicle from the run config. The agent only drafts; the owner submits.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlmodel import select

from src.agents.tools import _services, create_draft_quote, get_quote_status
from src.agents.tools.dependency import AgentToolServices, build_customer_agent_tools
from src.common.core.conversation import MessageRole
from src.common.core.maintenance.quote import Quote, QuoteStatus
from src.infrastructure.messaging import MessageDto
from src.modules.quote import schemas as quote_schemas
from src.modules.quote.cards import enrich_quote_cards
from tests._maintenance import add_workshop, add_workshop_owner, make_session
from tests._user_vehicle import add_owner, add_rules, add_vehicle


@pytest.fixture
def session():
    yield from make_session()


@pytest.fixture(autouse=True, params=["legacy", "injected"])
def real_services_on_test_db(request, monkeypatch, session):
    @contextmanager
    def open_session():
        yield session

    if request.param == "legacy":
        monkeypatch.setattr(_services, "open_session", open_session)
    else:
        services = AgentToolServices(
            open_session=open_session,
            user_vehicle_service=_services.user_vehicle_service,
            cost_estimation_service=_services.cost_estimation_service,
            booking_service=Mock(side_effect=AssertionError("booking is not used by quote tools")),
            quick_booking_service=Mock(side_effect=AssertionError("booking is not used by quote tools")),
            rag_pipeline=Mock(side_effect=AssertionError("RAG is not used by quote tools")),
        )
        for bound_tool in build_customer_agent_tools(services):
            if bound_tool.name in globals():
                monkeypatch.setitem(globals(), bound_tool.name, bound_tool)


@pytest.fixture
def world(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    owner = add_workshop_owner(session)
    workshop = add_workshop(session, owner=owner)
    add_rules(session)
    return user, vehicle, owner, workshop


def _run(user, vehicle, source_message_id=None) -> dict:
    configurable = {"user_id": user.user_id, "user_vehicle_id": str(vehicle.id)}
    if source_message_id is not None:
        configurable["source_message_id"] = str(source_message_id)
    return {"configurable": configurable}


def _draft(user, vehicle, workshop, *, milestone=12_000, source_message_id=None):
    """Invoke as a tool call so the ToolMessage carries the card artifact."""
    return create_draft_quote.invoke(
        {
            "type": "tool_call",
            "id": f"call-{uuid4()}",
            "name": "create_draft_quote",
            "args": {"workshop_id": str(workshop.id), "odo_milestone": milestone},
        },
        config=_run(user, vehicle, source_message_id),
    )


def _quote_service(session):
    return _services.quote_service(session)


def _content(message) -> dict:
    import json

    return json.loads(message.content)


def _card_message(card: dict) -> MessageDto:
    return MessageDto(id=uuid4(), role=MessageRole.ASSISTANT, content="", card=card, createdAt=datetime.now(UTC))


# ── create_draft_quote (TOOL-501) ─────────────────────────────────────────
def test_create_draft_quote_drafts_only_and_links_the_chat_message(session, world):
    user, vehicle, _owner, workshop = world
    chat_message_id = uuid4()

    message = _draft(user, vehicle, workshop, source_message_id=chat_message_id)

    data = _content(message)
    [quote] = session.exec(select(Quote)).all()
    assert (data["status"], data["reused"]) == ("DRAFT", False)
    assert data["quote"]["quote_id"] == str(quote.id)
    assert data["quote"]["estimated_total"] == 100_000  # the covered battery check costs 0
    assert {i["item_name"] for i in data["quote"]["items"]} == {
        "Brake system inspection",
        "High-voltage battery check",
    }
    assert "Gửi xưởng duyệt" in data["next_step"]
    # Never sent by the agent: the workshop cannot see a draft (BR-1103, BR-1110).
    assert (quote.status, quote.submitted_at) == (QuoteStatus.DRAFT, None)
    assert quote.source_message_id == chat_message_id
    card = message.artifact
    assert card["type"] == "QUOTE"
    assert (card["quote"]["quoteId"], card["quote"]["displayStatus"]) == (str(quote.id), "DRAFT")
    assert card["quote"]["workshop"]["name"] == workshop.name


def test_create_draft_quote_reuses_the_open_quote(session, world):
    """Asking twice drafts once; a pending quote is reported, not drafted again."""
    user, vehicle, _owner, workshop = world

    first = _content(_draft(user, vehicle, workshop, source_message_id=uuid4()))
    again = _content(_draft(user, vehicle, workshop, source_message_id=uuid4()))
    assert again["reused"] is True and again["quote"]["quote_id"] == first["quote"]["quote_id"]

    _quote_service(session).submit(user, UUID(first["quote"]["quote_id"]))
    pending = _draft(user, vehicle, workshop)
    assert _content(pending)["status"] == "PENDING_APPROVAL"
    assert "không cần gửi lại" in _content(pending)["next_step"]
    assert pending.artifact["quote"]["displayStatus"] == "PENDING_APPROVAL"
    assert len(session.exec(select(Quote)).all()) == 1


def test_a_draft_from_the_estimate_page_gets_the_chat_link(session, world):
    user, vehicle, _owner, workshop = world
    page_draft = _quote_service(session).create(
        user,
        quote_schemas.CreateQuoteRequest(user_vehicle_id=vehicle.id, workshop_id=workshop.id, odo_milestone=12_000),
    )
    chat_message_id = uuid4()

    data = _content(_draft(user, vehicle, workshop, source_message_id=chat_message_id))

    assert data["reused"] is True
    assert session.get(Quote, page_draft.quote_id).source_message_id == chat_message_id


def test_create_draft_quote_explains_an_unknown_milestone(session, world):
    user, vehicle, _owner, workshop = world

    message = _draft(user, vehicle, workshop, milestone=5_000)

    data = _content(message)
    assert data["error_code"] == "MILESTONE_NOT_FOUND"
    assert data["details"]["validMilestones"] == [12_000, 24_000]
    assert message.artifact is None
    assert session.exec(select(Quote)).all() == []


def test_create_draft_quote_rejects_a_made_up_workshop_id(session, world):
    user, vehicle, _owner, _workshop = world

    message = create_draft_quote.invoke(
        {
            "type": "tool_call",
            "id": "call-1",
            "name": "create_draft_quote",
            "args": {"workshop_id": "VinFast Long Bien", "odo_milestone": 12_000},
        },
        config=_run(user, vehicle),
    )

    assert _content(message)["error_code"] == "INVALID_REQUEST"
    assert message.artifact is None


def test_create_draft_quote_needs_the_chat_context(session, world):
    _user, _vehicle, _owner, workshop = world

    message = create_draft_quote.invoke(
        {
            "type": "tool_call",
            "id": "call-1",
            "name": "create_draft_quote",
            "args": {"workshop_id": str(workshop.id), "odo_milestone": 12_000},
        }
    )

    assert _content(message)["error_code"] == "CHAT_CONTEXT_MISSING"


# ── get_quote_status (TOOL-503) ───────────────────────────────────────────
def test_get_quote_status_reports_the_workshop_decision(session, world):
    user, vehicle, owner, workshop = world
    quote_id = UUID(_content(_draft(user, vehicle, workshop))["quote"]["quote_id"])
    quotes = _quote_service(session)
    submitted = quotes.submit(user, quote_id)
    paid = next(i for i in submitted.items if not i.covered)
    quotes.approve(
        owner,
        workshop.id,
        submitted.quote_id,
        quote_schemas.ApproveQuoteRequest(
            items=[
                quote_schemas.ApproveItemIn(quote_item_id=paid.quote_item_id, approved_price=90_000, note="Giảm giá")
            ]
        ),
    )

    result = get_quote_status.invoke({}, config=_run(user, vehicle))

    latest = result["latest"]
    assert (latest["quote_id"], latest["display_status"]) == (str(quote_id), "MODIFIED")
    assert latest["approved_total"] == 90_000 and latest["expires_at"] is not None
    assert next(i for i in latest["items"] if not i["covered"])["reviewer_note"] == "Giảm giá"
    assert result["others"] == []
    # The agent told the owner, so the BR-1109 badge clears.
    assert session.get(Quote, submitted.quote_id).result_seen_at is not None


def test_get_quote_status_without_quotes(session, world):
    user, vehicle, _owner, _workshop = world

    assert get_quote_status.invoke({}, config=_run(user, vehicle)) == {"latest": None, "others": []}


def test_get_quote_status_hides_another_owners_quote(session, world):
    user, vehicle, _owner, workshop = world
    quote_id = _content(_draft(user, vehicle, workshop))["quote"]["quote_id"]
    stranger = add_owner(session, uid="uid-2", email="other@example.com")
    stranger_vehicle = add_vehicle(session, stranger, vin="RLLV00000000000B2", external_vehicle_id="VEH-2")

    result = get_quote_status.invoke({"quote_id": quote_id}, config=_run(stranger, stranger_vehicle))

    assert result["error_code"] == "QUOTE_NOT_FOUND"


# ── CARD-QUOTE live status ────────────────────────────────────────────────
def test_quote_card_shows_the_current_quote(session, world):
    user, vehicle, owner, workshop = world
    snapshot = _draft(user, vehicle, workshop).artifact
    quote_id = UUID(snapshot["quote"]["quoteId"])
    quotes = _quote_service(session)
    quotes.submit(user, quote_id)
    quotes.approve(owner, workshop.id, quote_id, quote_schemas.ApproveQuoteRequest(items=[]))

    [live] = enrich_quote_cards(session, [_card_message(snapshot)])

    assert snapshot["quote"]["displayStatus"] == "DRAFT"  # the stored snapshot is untouched
    assert live.card["type"] == "QUOTE"
    assert live.card["quote"]["displayStatus"] == "APPROVED"
    assert live.card["quote"]["approvedTotal"] == 100_000


def test_quote_card_of_a_deleted_draft_is_dropped(session, world):
    user, vehicle, _owner, workshop = world
    snapshot = _draft(user, vehicle, workshop).artifact
    _quote_service(session).delete_draft(user, UUID(snapshot["quote"]["quoteId"]))
    other = {"type": "BOOKING_PROPOSAL", "proposalId": str(uuid4())}

    gone, untouched = enrich_quote_cards(session, [_card_message(snapshot), _card_message(other)])

    assert gone.card is None
    assert untouched.card == other


def test_the_agent_has_no_tool_that_sends_a_quote():
    """BR-1103: only the owner's "Gửi xưởng duyệt" button submits a quote."""
    from src.agents.tools import CUSTOMER_AGENT_TOOLS

    names = {t.name for t in CUSTOMER_AGENT_TOOLS}
    assert {"create_draft_quote", "get_quote_status"} <= names
    assert not names & {"submit_quote", "approve_quote", "reject_quote"}
