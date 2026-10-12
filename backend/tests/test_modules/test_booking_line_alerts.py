"""Overdue owner-reply alert: the workshop owner is emailed once per ``asked_at``."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlmodel import select

from src.common.core.maintenance.booking import BookingStatus, PricingFlow
from src.common.core.maintenance.booking_line import BookingLine, LineKind, LineStatus
from src.common.core.notification.email import EmailSuppression
from src.modules.booking_line.jobs import ALERT_KIND, AlertConfig, OverdueReplyAlertJob
from src.modules.notification.channels import DeliveryResult, NotificationMessage
from src.modules.notification.email_transport import ResendEmailTransport, address_hash
from tests._maintenance import add_booking, add_workshop, add_workshop_owner, make_session
from tests._user_vehicle import add_owner, add_vehicle

ASKED = datetime(2026, 10, 3, 2, 0, tzinfo=UTC)  # 09:00 VN
CONFIG = AlertConfig(email_mode="resend", sender="EVCare <noreply@example.com>", app_url="https://app.example/")


class FakeTransport:
    def __init__(self, *results: DeliveryResult) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, NotificationMessage]] = []

    async def send(self, recipient, message):
        self.calls.append((recipient, message))
        return self.results.pop(0) if self.results else DeliveryResult.sent("provider-1")


@pytest.fixture
def world():
    for session in make_session():
        user = add_owner(session)
        vehicle = add_vehicle(session, user)
        owner = add_workshop_owner(session)
        workshop = add_workshop(session, owner=owner)
        yield session, user, vehicle, owner, workshop


def _waiting(session, booking, *, name="Thay má phanh trước", asked=ASKED, status=LineStatus.PROPOSED):
    line = BookingLine(
        booking_id=booking.id,
        kind=LineKind.EXTRA,
        line_status=status,
        item_name=name,
        unit_price=Decimal(500_000),
        asked_at=asked,
    )
    session.add(line)
    session.commit()
    session.refresh(line)
    return line


def _booking(world, *, status=BookingStatus.IN_PROGRESS, code="EVC-0001"):
    session, user, vehicle, _, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 3), t=time(9), status=status, code=code)
    booking.pricing_flow = PricingFlow.TWO_TIER
    session.add(booking)
    session.commit()
    return booking


async def _run(session, transport, minutes, config=CONFIG):
    return await OverdueReplyAlertJob(
        session, transport, config, clock=lambda: ASKED + timedelta(minutes=minutes)
    ).run()


@pytest.mark.asyncio
async def test_workshop_is_emailed_once_when_the_owner_reply_is_overdue(world):
    session, _, _, owner, _ = world
    booking = _booking(world)
    line = _waiting(session, booking)
    transport = FakeTransport()

    assert (await _run(session, transport, 9.9)).lines == 0
    report = await _run(session, transport, 10)
    assert (report.workshops, report.lines, report.sent) == (1, 1, 1)
    recipient, message = transport.calls[0]
    assert recipient == owner.email and message.kind == ALERT_KIND
    assert message.subject == "Cần gọi chủ xe: EVC-0001"
    assert "Thay má phanh trước (hỏi lúc 09:00)" in message.body
    assert f"https://app.example/technician/board/{booking.id}" in message.body
    assert message.sender == CONFIG.sender and message.html

    # Once per asked_at: later runs stay quiet ...
    assert (await _run(session, transport, 11)).lines == 0
    assert len(transport.calls) == 1

    # ... until the workshop asks again (edit, raised price, dispute) and that goes overdue too.
    session.refresh(line)
    line.asked_at = ASKED + timedelta(minutes=12)
    session.add(line)
    session.commit()
    assert (await _run(session, transport, 21)).lines == 0
    assert (await _run(session, transport, 22)).sent == 1
    assert transport.calls[1][1].delivery_id != message.delivery_id


@pytest.mark.asyncio
async def test_lines_nobody_should_be_called_about_are_skipped(world):
    session = world[0]
    _waiting(session, _booking(world, code="EVC-DONE", status=BookingStatus.COMPLETED))
    _waiting(session, _booking(world, code="EVC-OK"), status=LineStatus.APPROVED)
    transport = FakeTransport()
    assert (await _run(session, transport, 30)).lines == 0

    # Overdue for longer than the window (a stopped worker, a fresh deploy): no backlog mail.
    _waiting(session, _booking(world, code="EVC-OLD"), asked=ASKED - timedelta(hours=2))
    assert (await _run(session, transport, 0)).lines == 0
    assert transport.calls == []


@pytest.mark.asyncio
async def test_one_email_per_workshop_lists_every_overdue_booking(world):
    session, user, _, _, workshop = world
    first = _booking(world, code="EVC-0001")
    other_vehicle = add_vehicle(session, user, vin="VF8OTHERVIN000001", external_vehicle_id="EXT-2")
    second = add_booking(
        session, user, other_vehicle, workshop, d=date(2026, 10, 3), status=BookingStatus.CHECKED_IN, code="EVC-0002"
    )
    _waiting(session, first, name="Thay má phanh")
    _waiting(session, first, name="Thay gạt mưa")
    _waiting(session, second, name="Cân chỉnh lốp")
    # Another workshop's line goes to that workshop's owner.
    other_owner = add_workshop_owner(session, uid="ws-uid-2")
    other_workshop = add_workshop(session, name="Other", owner=other_owner)
    other = add_booking(
        session,
        add_owner(session, uid="uid-2", email="owner2@example.com"),
        other_vehicle,
        other_workshop,
        d=date(2026, 10, 3),
        status=BookingStatus.IN_PROGRESS,
        code="EVC-0003",
    )
    _waiting(session, other, name="Thay lọc gió")

    transport = FakeTransport()
    report = await _run(session, transport, 10)
    assert (report.workshops, report.lines, report.sent) == (2, 4, 2)
    mails = {recipient: message for recipient, message in transport.calls}
    ours = mails[world[3].email]
    assert ours.subject == "Cần gọi chủ xe: 2 lịch hẹn"
    assert all(name in ours.body for name in ("EVC-0001", "EVC-0002", "Thay má phanh", "Thay gạt mưa", "Cân chỉnh lốp"))
    assert "Thay lọc gió" not in ours.body and "Thay lọc gió" in mails[other_owner.email].body


@pytest.mark.asyncio
async def test_a_transient_failure_is_retried_with_the_same_key(world):
    session = world[0]
    line = _waiting(session, _booking(world))
    transport = FakeTransport(DeliveryResult.failed("TIMEOUT"), DeliveryResult.failed("EMAIL_REJECTED"))

    assert (await _run(session, transport, 10)).failed == 1
    session.refresh(line)
    assert line.workshop_alerted_at is None  # released for the next run
    assert (await _run(session, transport, 11)).failed == 1
    assert transport.calls[0][1].delivery_id == transport.calls[1][1].delivery_id
    session.refresh(line)
    assert line.workshop_alerted_at is not None  # a permanent failure is not retried
    assert (await _run(session, transport, 12)).lines == 0


@pytest.mark.asyncio
async def test_suppressed_address_and_mock_mode_send_nothing(world):
    session, _, _, owner, _ = world
    _waiting(session, _booking(world))
    session.add(EmailSuppression(recipient_hash=address_hash(owner.email), reason="bounced", created_at=ASKED))
    session.commit()
    transport = FakeTransport()
    report = await _run(session, transport, 10)
    assert (report.lines, report.suppressed, report.sent) == (1, 1, 0) and transport.calls == []

    session.delete(session.exec(select(EmailSuppression)).one())
    session.commit()
    _waiting(session, _booking(world, code="EVC-0002"), asked=ASKED + timedelta(minutes=5))
    mock = AlertConfig(email_mode="mock", sender="", app_url="")
    assert (await _run(session, transport, 15, mock)).sent == 1 and transport.calls == []


@pytest.mark.asyncio
async def test_resend_transport_accepts_the_alert_with_its_own_idempotency_key():
    requests: list[httpx.Request] = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "provider-1"})

    transport = ResendEmailTransport(
        "key", client_factory=lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kw)
    )
    message = NotificationMessage("s", "b", html="<p>b</p>", kind=ALERT_KIND, delivery_id="d-1", sender="x@y")
    assert (await transport.send("ws@example.com", message)).provider_message_id == "provider-1"
    assert requests[0].headers["Idempotency-Key"] == "workshop-reply-overdue/d-1"
