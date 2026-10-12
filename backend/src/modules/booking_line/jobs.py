"""Overdue owner-reply alert — email the workshop owner (TODOS P3, open question 2 follow-up).

The board and Dashboard flag "Cần gọi" once a line waiting for the owner passes
``OWNER_REPLY_SLA``, but only while they are open. ``booking_line.alert_overdue_replies``
(every minute) emails the workshop owner once per ``asked_at``: one message per workshop
listing the lines that became overdue. Lines overdue for longer than ``ALERT_WINDOW`` are
left alone, so a stopped worker or a fresh deploy never mails a backlog.

``workshop_alerted_at`` is committed before the provider call (no transaction held over
HTTP); a retryable failure clears it so the next run tries again with the same
idempotency key. The board label stays the fallback whatever the email does.
"""

from __future__ import annotations

import html
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import or_, update
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import UserStatus
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.core.maintenance.booking import Booking
from src.common.core.maintenance.booking_line import BookingLine, LineStatus
from src.common.core.notification import DeliveryStatus
from src.common.core.notification.email import EmailSuppression
from src.common.core.workshop import Workshop
from src.modules.booking.domain import TZ_VN
from src.modules.notification.channels import DeliveryResult, NotificationMessage
from src.modules.notification.email_transport import address_hash
from src.modules.oem_integration.service import as_utc, utc_now

from .domain import DECIDABLE_STATUSES, OWNER_REPLY_SLA

logger = logging.getLogger(__name__)

ALERT_KIND = "WORKSHOP_REPLY_OVERDUE"
ALERT_WINDOW = timedelta(hours=1)


@dataclass(frozen=True)
class AlertConfig:
    email_mode: str  # mock | resend (callers skip the job when email is off or not configured)
    sender: str
    app_url: str


@dataclass
class AlertReport:
    workshops: int = 0
    lines: int = 0
    sent: int = 0
    failed: int = 0
    suppressed: int = 0


@dataclass(frozen=True)
class _Line:
    booking_id: str
    booking_code: str
    item_name: str
    asked_at: datetime


def _key(lines: list[BookingLine]) -> str:
    """Same lines asked at the same time ⇒ same delivery id (Resend idempotency key)."""
    parts = sorted(f"{line.id}@{as_utc(line.asked_at).isoformat()}" for line in lines)
    return str(uuid5(NAMESPACE_URL, f"{ALERT_KIND}:{','.join(parts)}"))


def alert_message(lines: list[_Line], config: AlertConfig, delivery_id: str) -> NotificationMessage:
    base = config.app_url.rstrip("/")
    bookings: dict[str, list[_Line]] = {}
    for line in lines:
        bookings.setdefault(line.booking_id, []).append(line)
    codes = sorted({line.booking_code for line in lines})
    subject = f"Cần gọi chủ xe: {codes[0]}" if len(codes) == 1 else f"Cần gọi chủ xe: {len(codes)} lịch hẹn"
    intro = (
        f"Chủ xe chưa trả lời sau {int(OWNER_REPLY_SLA.total_seconds() // 60)} phút. "
        "Gọi cho chủ xe rồi ghi quyết định trên bảng điều phối."
    )
    text, body = [intro], [f"<p>{html.escape(intro)}</p>"]
    for booking_id, group in bookings.items():
        link = f"{base}/technician/board/{booking_id}" if base else None
        items = [f"{line.item_name} (hỏi lúc {as_utc(line.asked_at).astimezone(TZ_VN):%H:%M})" for line in group]
        text.append("\n".join([group[0].booking_code, *(f"- {item}" for item in items)] + ([link] if link else [])))
        anchor = f' · <a href="{html.escape(link)}">Mở bảng điều phối</a>' if link else ""
        body.append(
            f"<p><strong>{html.escape(group[0].booking_code)}</strong>{anchor}</p>"
            f"<ul>{''.join(f'<li>{html.escape(item)}</li>' for item in items)}</ul>"
        )
    return NotificationMessage(
        subject=subject,
        body="\n\n".join(text),
        html="".join(body),
        kind=ALERT_KIND,
        delivery_id=delivery_id,
        sender=config.sender,
    )


class OverdueReplyAlertJob:
    def __init__(
        self,
        session: Session,
        transport,
        config: AlertConfig,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._db = session
        self._transport = transport
        self._config = config
        self._clock = clock

    async def run(self) -> AlertReport:
        report = AlertReport()
        now = self._clock()
        due_before = now - OWNER_REPLY_SLA
        rows = self._db.exec(
            select(BookingLine, Booking, WorkshopOwner)
            .join(Booking, Booking.id == BookingLine.booking_id)
            .join(Workshop, Workshop.id == Booking.workshop_id)
            .join(WorkshopOwner, WorkshopOwner.id == Workshop.owner_id)
            .where(
                BookingLine.line_status == LineStatus.PROPOSED,
                BookingLine.asked_at <= due_before,
                BookingLine.asked_at > due_before - ALERT_WINDOW,
                or_(
                    BookingLine.workshop_alerted_at.is_(None),
                    BookingLine.workshop_alerted_at < BookingLine.asked_at,
                ),
                Booking.status.in_(DECIDABLE_STATUSES),
                WorkshopOwner.status == UserStatus.ACTIVE,
            )
            .order_by(Booking.booking_code, BookingLine.asked_at)
            .with_for_update(of=BookingLine, skip_locked=True)
        ).all()
        groups: dict[str, tuple[WorkshopOwner, list[BookingLine], list[_Line]]] = {}
        for line, booking, owner in rows:
            _, lines, view = groups.setdefault(str(owner.id), (owner, [], []))
            lines.append(line)
            view.append(_Line(str(booking.id), booking.booking_code, line.item_name, line.asked_at))

        # Claim every line before any provider call, then release the row locks.
        sends: list[tuple[str, list, NotificationMessage]] = []
        for owner, lines, view in groups.values():
            for line in lines:
                line.workshop_alerted_at = now
                self._db.add(line)
            report.workshops += 1
            report.lines += len(lines)
            if self._db.get(EmailSuppression, address_hash(owner.email)) is not None:
                report.suppressed += 1
                continue
            delivery_id = _key(lines)
            sends.append((owner.email, [line.id for line in lines], alert_message(view, self._config, delivery_id)))
        self._db.commit()

        for recipient, line_ids, message in sends:
            result = await self._send(recipient, message)
            if result.status == DeliveryStatus.SENT:
                report.sent += 1
                continue
            report.failed += 1
            logger.warning(
                "booking_line.reply_alert_failed",
                extra={"delivery_id": message.delivery_id, "error_code": result.error_code},
            )
            if result.retryable:
                self._db.execute(
                    update(BookingLine)
                    .where(BookingLine.id.in_(line_ids), BookingLine.workshop_alerted_at == now)  # type: ignore[attr-defined]
                    .values(workshop_alerted_at=None)
                    .execution_options(synchronize_session=False)
                )
                self._db.commit()
        logger.info("booking_line.reply_alerts", extra=report.__dict__)
        return report

    async def _send(self, recipient: str, message: NotificationMessage) -> DeliveryResult:
        if self._config.email_mode == "mock":
            logger.info("booking_line.reply_alert_mock", extra={"delivery_id": message.delivery_id})
            return DeliveryResult.sent(f"mock-{message.delivery_id}")
        try:
            return await self._transport.send(recipient, message)
        except Exception:  # noqa: BLE001 - the transport must not stop the job
            logger.exception("booking_line.reply_alert_crashed")
            return DeliveryResult.failed("UNAVAILABLE")
