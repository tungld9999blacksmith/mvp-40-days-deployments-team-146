"""Shared test helpers for the maintenance flows (cost estimate, bookings, quotes, CRM).

Builds on ``tests._user_vehicle`` (same in-memory SQLite approach) and adds the
workshop-side tables plus seed helpers for workshops, owners and bookings.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import MetaData
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from src.common.core.crm.follow_up import FollowUp
from src.common.core.crm.support_ticket import SupportTicket
from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.booking_status_event import BookingReschedule, BookingStatusEvent
from src.common.core.notification import (
    BookingReminder,
    BookingReminderDelivery,
    FollowUpDelivery,
)
from src.common.core.maintenance.quote import Quote
from src.common.core.maintenance.quote_item import QuoteItem
from src.common.core.maintenance.service_progress import ServiceProgress
from src.common.core.vehicle import UserVehicle
from src.common.core.workshop import (
    BookingConfirmationMode,
    ServiceCenterType,
    Workshop,
    WorkshopOperatingHour,
    WorkshopSlotBlock,
    WorkshopStatus,
)
from tests._user_vehicle import TABLES as VEHICLE_TABLES
from tests._user_vehicle import _make_sqlite_compatible

TABLES = [
    *VEHICLE_TABLES,
    WorkshopOperatingHour.__table__,
    WorkshopSlotBlock.__table__,
    Quote.__table__,
    QuoteItem.__table__,
    ServiceProgress.__table__,
    FollowUp.__table__,
    SupportTicket.__table__,
    BookingStatusEvent.__table__,
    BookingReschedule.__table__,
    BookingReminder.__table__,
    BookingReminderDelivery.__table__,
    FollowUpDelivery.__table__,
]


def make_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata = MetaData()
    for table in TABLES:
        _make_sqlite_compatible(table.to_metadata(metadata))
    metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def add_workshop_owner(session: Session, *, uid: str = "ws-uid-1") -> WorkshopOwner:
    owner = WorkshopOwner(firebase_uid=uid, email=f"{uid}@example.com", full_name="Owner " + uid)
    session.add(owner)
    session.commit()
    session.refresh(owner)
    return owner


def add_workshop(
    session: Session,
    *,
    name: str = "VinFast Smart City",
    owner: WorkshopOwner | None = None,
    status: WorkshopStatus = WorkshopStatus.ACTIVE,
    mode: BookingConfirmationMode = BookingConfirmationMode.AUTO,
    total_technicians: int = 4,
    region: str = "Ha Noi",
) -> Workshop:
    if status == WorkshopStatus.ACTIVE and owner is None:
        owner = add_workshop_owner(session, uid=f"ws-{name.lower().replace(' ', '-')}")
    workshop = Workshop(
        external_center_id=f"C-{name}",
        name=name,
        region=region,
        type=ServiceCenterType.DEALER,
        address=f"{name} address",
        total_technicians=total_technicians,
        emergency_slots_reserved=0,
        status=status,
        booking_confirmation_mode=mode,
        owner_id=owner.id if owner else None,
    )
    session.add(workshop)
    session.commit()
    session.refresh(workshop)
    return workshop


def add_hours(
    session: Session, workshop: Workshop, *, open_at: time = time(8), close_at: time = time(17)
) -> None:
    """Open every day of the week between ``open_at`` and ``close_at``."""
    for dow in range(1, 8):
        session.add(
            WorkshopOperatingHour(
                workshop_id=workshop.id,
                day_of_week=dow,
                is_closed=False,
                open_time=open_at,
                close_time=close_at,
            )
        )
    session.commit()


def add_booking(
    session: Session,
    user: VehicleUser,
    vehicle: UserVehicle,
    workshop: Workshop,
    *,
    d: date,
    t: time = time(9),
    status: BookingStatus = BookingStatus.CONFIRMED,
    code: str = "EVC-0001",
    hold_expires_at: datetime | None = None,
    booking_id: UUID | None = None,
) -> Booking:
    booking = Booking(
        booking_code=code,
        user_id=user.user_id,
        user_vehicle_id=vehicle.id,
        workshop_id=workshop.id,
        booking_date=d,
        time_slot=t,
        status=status,
        hold_expires_at=hold_expires_at,
    )
    if booking_id is not None:
        booking.id = booking_id
    session.add(booking)
    session.commit()
    session.refresh(booking)
    return booking
