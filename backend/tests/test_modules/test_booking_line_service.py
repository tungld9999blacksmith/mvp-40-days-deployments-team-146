"""Two-tier booking pricing (docs/designs/bao-gia-hai-tang.md) — service + state-machine tests.

In-memory SQLite (``FOR UPDATE`` is a no-op there); the Workshop Board drives
START / COMPLETE through the shared ``BookingStateMachine``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlmodel import select

from src.common.core.maintenance.booking import BookingStatus, PricingFlow
from src.common.core.maintenance.booking_line import BookingLine, BookingLinePhoto, LineKind, LineStatus
from src.common.core.maintenance.maintenance_rule import MaintenanceRule
from src.common.core.maintenance.reminder import Reminder, ReminderChannel, ReminderLevel
from src.common.core.maintenance.service_progress import ServiceProgress, ServiceStage
from src.common.core.vehicle import VehicleServiceRecord
from src.common.core.workshop.service_price import ServicePrice
from src.infrastructure.storage import StorageNotFoundError, StoredObject
from src.modules.booking_line import errors
from src.modules.booking_line import schemas as s
from src.modules.booking_line.domain import billable_total
from src.modules.booking_line.photos import LinePhotos, pending_prefix, sniff_image_type
from src.modules.booking_line.service import BookingLineService
from src.modules.workshop_board import schemas as board_schemas
from src.modules.workshop_board.service import WorkshopBoardService
from tests._maintenance import add_booking, add_hours, add_workshop, add_workshop_owner, make_session
from tests._user_vehicle import MODEL_ID, add_owner, add_rules, add_vehicle

NOW = datetime(2026, 10, 3, 2, 0, tzinfo=UTC)  # 09:00 VN
TODAY = date(2026, 10, 3)


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def notify(self, user_id, message):
        self.sent.append((user_id, message.body))
        return 1


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
    add_rules(session)  # 12,000 km: BRAKE_INSPECTION (chargeable), BATTERY_CHECK (warranty)
    session.add(
        MaintenanceRule(
            model_id=MODEL_ID,
            odo_milestone=12_000,
            month_milestone=12,
            item_code="CABIN_FILTER",
            item_name="Replace cabin air filter",
            estimated_cost=250_000,
            estimated_duration_minutes=15,
        )
    )
    # Workshop price for the brake inspection only; the cabin filter keeps its reference price.
    session.add(
        ServicePrice(
            workshop_id=workshop.id, model_id=MODEL_ID, item_code="BRAKE_INSPECTION", item_name="x", price=300_000
        )
    )
    session.commit()
    return session, user, vehicle, owner, workshop


def _booking(session, user, vehicle, workshop, *, status=BookingStatus.CHECKED_IN, odo=12_000, code="EVC-0001"):
    booking = add_booking(session, user, vehicle, workshop, d=TODAY, t=time(9), status=status, code=code)
    booking.pricing_flow = PricingFlow.TWO_TIER
    booking.odo_milestone = odo
    session.add(booking)
    BookingLineService(session).snapshot_package(booking, vehicle, workshop)
    session.commit()
    session.refresh(booking)
    return booking


def _lines(session, booking) -> dict[str, BookingLine]:
    rows = session.exec(select(BookingLine).where(BookingLine.booking_id == booking.id)).all()
    return {row.item_code or row.item_name: row for row in rows}


def _svc(session, notifier=None, photos=None) -> BookingLineService:
    return BookingLineService(session, notifier=notifier, photos=photos, clock=lambda: NOW)


def _board(session) -> WorkshopBoardService:
    return WorkshopBoardService(session, clock=lambda: NOW)


def _move(action, expected, **kw):
    return board_schemas.TransitionRequest(action=action, expected_status=expected, **kw)


def _extra(price=500_000, reason="Má phanh trước còn 2mm, cần thay", **kw) -> s.ProposeExtraRequest:
    return s.ProposeExtraRequest(item_name=kw.pop("item_name", "Thay má phanh trước"), price=price, reason=reason, **kw)


# ── domain ──────────────────────────────────────────────────────────────────
def test_sniff_image_type():
    assert sniff_image_type(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert sniff_image_type(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert sniff_image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_image_type(b"GIF89a") is None


# ── tier 1 ──────────────────────────────────────────────────────────────────
def test_snapshot_prices_package_lines(world):
    session, user, vehicle, _, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.CONFIRMED)
    lines = _lines(session, booking)

    brake = lines["BRAKE_INSPECTION"]
    assert brake.line_status == LineStatus.CONFIRMED and brake.unit_price == 300_000
    assert brake.price_source == "WORKSHOP_PRICE" and brake.service_price_id is not None
    assert brake.is_safety_critical  # flag of the BRAKE_INSPECTION rule
    battery = lines["BATTERY_CHECK"]
    assert battery.is_covered_by_warranty and battery.unit_price == 0 and battery.line_status == LineStatus.CONFIRMED
    cabin = lines["CABIN_FILTER"]
    assert cabin.line_status == LineStatus.PENDING_CONFIRM and cabin.unit_price == 250_000
    assert booking.estimated_cost == 550_000

    # A later price-list change never alters the snapshot.
    price = session.exec(select(ServicePrice)).one()
    price.price = 999_000
    session.add(price)
    session.commit()
    view = _svc(session).view(booking)
    assert next(x for x in view.lines if x.item_code == "BRAKE_INSPECTION").unit_price == 300_000


@pytest.mark.asyncio
async def test_safety_flag_comes_from_the_rule_not_the_name(world):
    session, user, vehicle, owner, workshop = world
    rules = {r.item_code: r for r in session.exec(select(MaintenanceRule))}
    rules["BRAKE_INSPECTION"].is_safety_critical = False
    rules["CABIN_FILTER"].is_safety_critical = True
    rules["BRAKE_FLUID"].is_safety_critical = False
    session.add_all(rules.values())
    session.commit()

    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    lines = _lines(session, booking)
    assert not lines["BRAKE_INSPECTION"].is_safety_critical
    assert lines["CABIN_FILTER"].is_safety_critical

    view = await _svc(session).propose_extra(
        owner,
        workshop,
        booking.id,
        s.ProposeExtraRequest(item_code="BRAKE_FLUID", price=400_000, reason="Dầu phanh đã ngả màu"),
    )
    assert not view.lines[-1].is_safety_critical


def test_no_rule_books_without_package_lines(world):
    session, user, vehicle, _, workshop = world
    booking = _booking(session, user, vehicle, workshop, odo=15_000)
    view = _svc(session).view(booking)
    assert view.lines == [] and view.package_notice == "Giá gói do xưởng báo khi nhận xe"
    assert view.blocked_actions == []


def test_legacy_booking_has_no_lines(world):
    session, user, vehicle, _, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=TODAY)
    view = _svc(session).view(booking)
    assert view.pricing_flow == "legacy" and view.lines == [] and view.package_notice is None


# ── check-in confirmation + START guard (D8) ────────────────────────────────
@pytest.mark.asyncio
async def test_start_blocked_until_reference_prices_confirmed(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop)
    board = _board(session)

    detail = board.detail(workshop, booking.id)
    assert [(b.action, b.reason_code) for b in detail.blocked_actions] == [("START", "BOOKING_LINES_UNCONFIRMED")]
    with pytest.raises(errors.LinesUnconfirmedError):
        await board.transition(owner, workshop, booking.id, _move("START", "CHECKED_IN"))
    session.refresh(booking)
    assert booking.status == BookingStatus.CHECKED_IN

    notifier = FakeNotifier()
    cabin = _lines(session, booking)["CABIN_FILTER"]
    view = await _svc(session, notifier).confirm_package(
        owner, workshop, booking.id, cabin.id, s.ConfirmPackageRequest(expected_version=1, price=200_000)
    )
    line = next(x for x in view.lines if x.item_code == "CABIN_FILTER")
    assert line.status == "CONFIRMED" and line.price == 200_000 and line.version == 2
    assert notifier.sent and "200.000 đ" in notifier.sent[0][1]
    session.refresh(cabin)
    assert cabin.confirmed_by == owner.id and cabin.confirmed_at is not None

    await board.transition(owner, workshop, booking.id, _move("START", "CHECKED_IN"))
    session.refresh(booking)
    assert booking.status == BookingStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_price_increase_needs_reason_and_owner_decision(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop)
    cabin = _lines(session, booking)["CABIN_FILTER"]
    svc = _svc(session, FakeNotifier())

    with pytest.raises(errors.ReasonRequiredError):
        await svc.confirm_package(
            owner, workshop, booking.id, cabin.id, s.ConfirmPackageRequest(expected_version=1, price=300_000)
        )
    view = await svc.confirm_package(
        owner,
        workshop,
        booking.id,
        cabin.id,
        s.ConfirmPackageRequest(expected_version=1, price=300_000, reason="Lọc chính hãng tăng giá từ tháng 9"),
    )
    assert view.pending_decision_count == 1 and view.unconfirmed_count == 0
    assert view.current_total == 300_000  # brake 300k + warranty 0
    assert view.total_if_all_approved == 600_000

    # A PROPOSED price increase does not block START, only COMPLETE.
    board = _board(session)
    await board.transition(owner, workshop, booking.id, _move("START", "CHECKED_IN"))
    with pytest.raises(errors.LinesUnsettledError):
        await board.transition(owner, workshop, booking.id, _move("COMPLETE", "IN_PROGRESS"))


# ── owner decision (HITL) ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_owner_decides_on_the_version_they_saw(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    svc = _svc(session, FakeNotifier())
    view = await svc.propose_extra(owner, workshop, booking.id, _extra())
    extra = next(x for x in view.lines if x.kind == "EXTRA")
    assert extra.status == "PROPOSED" and extra.version == 1 and extra.price_label == "Phát sinh"

    # The workshop edits the price while the owner still looks at version 1.
    await svc.edit_line(
        owner,
        workshop,
        booking.id,
        extra.line_id,
        s.EditLineRequest(expected_version=1, price=650_000, reason="Má phanh trước còn 2mm, đĩa cũng mòn"),
    )
    with pytest.raises(errors.LineChangedError) as exc:
        svc.decide(user, booking.id, extra.line_id, s.DecideRequest(decision="APPROVE", seen_version=1))
    assert exc.value.details["line"]["price"] == 650_000 and exc.value.details["line"]["version"] == 2

    view = svc.decide(user, booking.id, extra.line_id, s.DecideRequest(decision="APPROVE", seen_version=2))
    assert next(x for x in view.lines if x.kind == "EXTRA").status == "APPROVED"
    # Final: a second click (or a second tab) cannot change it.
    with pytest.raises(errors.LineChangedError):
        svc.decide(user, booking.id, extra.line_id, s.DecideRequest(decision="DECLINE", seen_version=3))


@pytest.mark.asyncio
async def test_declining_a_safety_item_needs_confirmation(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    svc = _svc(session)
    # A free-text item is flagged by the workshop; catalog items carry the flag themselves.
    view = await svc.propose_extra(owner, workshop, booking.id, _extra(is_safety_critical=True))
    line = view.lines[-1]
    assert line.is_safety_critical
    with pytest.raises(errors.SafetyConfirmationRequiredError):
        svc.decide(user, booking.id, line.line_id, s.DecideRequest(decision="DECLINE", seen_version=1))
    view = svc.decide(
        user, booking.id, line.line_id, s.DecideRequest(decision="DECLINE", seen_version=1, confirm_safety=True)
    )
    assert view.lines[-1].status == "DECLINED"


@pytest.mark.asyncio
async def test_other_owner_and_other_workshop_see_nothing(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    svc = _svc(session)
    view = await svc.propose_extra(owner, workshop, booking.id, _extra())
    stranger = add_owner(session, uid="uid-2", email="other@example.com")
    with pytest.raises(errors.BookingNotFoundError):
        svc.decide(stranger, booking.id, view.lines[-1].line_id, s.DecideRequest(decision="APPROVE", seen_version=1))
    other_ws = add_workshop(session, name="Other Workshop")
    with pytest.raises(errors.BookingNotFoundError):
        await svc.propose_extra(owner, other_ws, booking.id, _extra())


# ── extras ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_extra_rules(world):
    session, user, vehicle, owner, workshop = world
    notifier = FakeNotifier()
    svc = _svc(session, notifier)
    checked_in = _booking(session, user, vehicle, workshop)
    with pytest.raises(errors.BookingStatusInvalidError):
        await svc.propose_extra(owner, workshop, checked_in.id, _extra())

    other_vehicle = add_vehicle(session, user, vin="RLLV00000000000B2", external_vehicle_id="VEH-2")
    booking = _booking(session, user, other_vehicle, workshop, status=BookingStatus.IN_PROGRESS, code="EVC-0002")
    with pytest.raises(errors.ReasonRequiredError):
        await svc.propose_extra(owner, workshop, booking.id, _extra(reason="ngắn"))

    view = await svc.propose_extra(owner, workshop, booking.id, _extra())
    assert notifier.sent[-1][1].endswith("Chỉ làm khi bạn đồng ý.")
    extra = view.lines[-1]
    view = svc.withdraw(workshop, booking.id, extra.line_id, s.WithdrawRequest(expected_version=1))
    assert view.lines[-1].status == "WITHDRAWN"
    with pytest.raises(errors.LineChangedError):
        svc.withdraw(workshop, booking.id, extra.line_id, s.WithdrawRequest(expected_version=2))

    # Catalog item: name and safety flag come from the model's rule.
    view = await svc.propose_extra(
        owner,
        workshop,
        booking.id,
        s.ProposeExtraRequest(item_code="BRAKE_FLUID", price=400_000, reason="Dầu phanh đã ngả màu"),
    )
    assert view.lines[-1].item_name == "Replace brake fluid" and view.lines[-1].is_safety_critical

    # No extras from QUALITY_CHECK on.
    for stage in (ServiceStage.INSPECTING, ServiceStage.SERVICING, ServiceStage.QUALITY_CHECK):
        session.add(ServiceProgress(booking_id=booking.id, stage=stage, created_at=NOW + timedelta(minutes=len(stage))))
    session.commit()
    with pytest.raises(errors.StageNotAllowedError):
        await svc.propose_extra(owner, workshop, booking.id, _extra())


# ── COMPLETE (D6, RR1) ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_complete_computes_actual_cost(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    cabin = _lines(session, booking)["CABIN_FILTER"]
    cabin.line_status = LineStatus.CONFIRMED  # confirmed at check-in
    session.add(cabin)
    session.commit()
    svc = _svc(session)
    approved = (await svc.propose_extra(owner, workshop, booking.id, _extra(price=500_000))).lines[-1]
    declined = (
        await svc.propose_extra(owner, workshop, booking.id, _extra(price=90_000, item_name="Vệ sinh khoang máy"))
    ).lines[-1]
    board = _board(session)
    with pytest.raises(errors.LinesUnsettledError):
        await board.transition(owner, workshop, booking.id, _move("COMPLETE", "IN_PROGRESS"))
    assert board.detail(workshop, booking.id).blocked_actions[0].reason_code == "BOOKING_LINES_UNSETTLED"

    svc.decide(user, booking.id, approved.line_id, s.DecideRequest(decision="APPROVE", seen_version=1))
    svc.decide(user, booking.id, declined.line_id, s.DecideRequest(decision="DECLINE", seen_version=1))
    # 300k brake + 0 warranty + 250k cabin + 500k approved extra.
    with pytest.raises(errors.ActualCostMismatchError) as exc:
        await board.transition(
            owner, workshop, booking.id, _move("COMPLETE", "IN_PROGRESS", actual_cost=Decimal(1_000_000))
        )
    assert exc.value.details["actualCost"] == "1050000.00"
    done = await board.transition(owner, workshop, booking.id, _move("COMPLETE", "IN_PROGRESS"))
    assert done.status == "COMPLETED" and done.actual_cost == 1_050_000
    assert billable_total(_lines(session, booking).values()) == done.actual_cost


@pytest.mark.asyncio
async def test_declined_package_item_keeps_the_milestone_open(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop)
    for done in (False,):
        session.add(
            Reminder(
                user_vehicle_id=vehicle.id,
                target_odo_milestone=12_000,
                reminder_level=ReminderLevel.WARNING,
                channel=ReminderChannel.IN_APP,
                is_resolved=done,
                scheduled_at=NOW,
            )
        )
    session.commit()
    svc = _svc(session)
    cabin = _lines(session, booking)["CABIN_FILTER"]
    await svc.confirm_package(
        owner,
        workshop,
        booking.id,
        cabin.id,
        s.ConfirmPackageRequest(expected_version=1, price=400_000, reason="Lọc chính hãng tăng giá từ tháng 9"),
    )
    board = _board(session)
    await board.transition(owner, workshop, booking.id, _move("START", "CHECKED_IN"))
    svc.decide(user, booking.id, cabin.id, s.DecideRequest(decision="DECLINE", seen_version=2))
    done = await board.transition(owner, workshop, booking.id, _move("COMPLETE", "IN_PROGRESS"))

    assert done.actual_cost == 300_000  # the refused item is not charged
    record = session.exec(select(VehicleServiceRecord)).one()
    assert "Chủ xe từ chối hạng mục" in record.items_done and "cabin" in record.items_done
    assert session.exec(select(Reminder)).one().is_resolved is False


@pytest.mark.asyncio
async def test_two_tier_guards_follow_the_booking_not_the_flag(world):
    """D7 — the column decides; a legacy-flagged service still guards a two-tier booking."""
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop)
    with pytest.raises(errors.LinesUnconfirmedError):
        await _board(session).transition(owner, workshop, booking.id, _move("START", "CHECKED_IN"))


# ── legacy regression (D11) ─────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("actual_cost", [Decimal(1_850_000), None])
async def test_legacy_booking_keeps_manual_actual_cost(world, actual_cost):
    session, user, vehicle, owner, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=TODAY, status=BookingStatus.CHECKED_IN)
    session.add(
        BookingLine(
            booking_id=booking.id, kind=LineKind.EXTRA, line_status=LineStatus.PROPOSED, item_name="x", unit_price=1
        )
    )
    session.commit()  # stray lines never affect a legacy booking
    board = _board(session)
    await board.transition(owner, workshop, booking.id, _move("START", "CHECKED_IN"))
    done = await board.transition(
        owner, workshop, booking.id, _move("COMPLETE", "IN_PROGRESS", actual_cost=actual_cost)
    )
    assert done.status == "COMPLETED" and done.actual_cost == actual_cost
    assert board.detail(workshop, booking.id).blocked_actions == []


# ── photos (D16, RR2, OV5, OV6) ─────────────────────────────────────────────
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, datetime]] = {}
        self.deleted: list[str] = []

    def put(self, key, data, at=NOW):
        self.objects[key] = (data, at)

    def info(self, key):
        if key not in self.objects:
            raise StorageNotFoundError(key)
        data, at = self.objects[key]
        return StoredObject(key=key, name=key.rsplit("/", 1)[-1], size=len(data), created_at=at)

    def download(self, key):
        return self.objects[key][0]

    def delete(self, keys):
        keys = [keys] if isinstance(keys, str) else keys
        for k in keys:
            self.objects.pop(k, None)
            self.deleted.append(k)
        return keys

    def signed_urls(self, keys, expires_in):
        return {k: f"https://signed/{k}?ttl={expires_in}" for k in keys}

    def iter_objects(self, prefix=None, *, recursive=False, page_size=100):
        for key, (data, at) in list(self.objects.items()):
            yield StoredObject(key=key, name=key, size=len(data), created_at=at)

    def create_signed_upload(self, key, *, overwrite=False):
        from src.infrastructure.storage import SignedUpload

        return SignedUpload(key=key, url=f"https://upload/{key}", token="t")


@pytest.mark.asyncio
async def test_photo_attach_rules(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    storage = FakeStorage()
    photos = LinePhotos(storage, clock=lambda: NOW)
    svc = _svc(session, photos=photos)
    prefix = pending_prefix(booking.id)

    upload = svc.sign_photo_upload(workshop, booking.id, "image/jpeg")
    assert upload.key.startswith(prefix)
    with pytest.raises(errors.PhotoInvalidError):
        svc.sign_photo_upload(workshop, booking.id, "image/gif")

    good, big, fake, old = (prefix + f"{i:032x}" for i in range(1, 5))
    storage.put(good, JPEG)
    storage.put(big, b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024))
    storage.put(fake, b"not an image at all")
    storage.put(old, JPEG, at=NOW - timedelta(hours=13))
    cases = {
        pending_prefix(booking.id).replace(str(booking.id), "00000000-0000-0000-0000-000000000000")
        + f"{9:032x}": "WRONG_BOOKING",
        prefix + f"{8:032x}": "MISSING",
        big: "TOO_LARGE",
        fake: "BAD_TYPE",
        old: "EXPIRED",
    }
    for key, reason in cases.items():
        with pytest.raises(errors.PhotoInvalidError) as exc:
            await svc.propose_extra(owner, workshop, booking.id, _extra(photo_keys=[key]))
        assert exc.value.details["reason"] == reason
    assert big in storage.deleted and fake in storage.deleted

    view = await svc.propose_extra(owner, workshop, booking.id, _extra(photo_keys=[good]))
    assert view.lines[-1].photos[0].url.startswith("https://signed/") and "ttl=600" in view.lines[-1].photos[0].url
    photo = session.exec(select(BookingLinePhoto)).one()
    assert photo.content_type == "image/jpeg" and photo.storage_key == good


def test_purge_removes_only_old_unattached_pending(world):
    session, user, vehicle, _, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    line = BookingLine(
        booking_id=booking.id, kind=LineKind.EXTRA, line_status=LineStatus.PROPOSED, item_name="x", unit_price=1
    )
    session.add(line)
    session.commit()
    storage = FakeStorage()
    prefix = pending_prefix(booking.id)
    attached, stale, fresh = (prefix + f"{i:032x}" for i in range(1, 4))
    for key in (attached, stale):
        storage.put(key, JPEG, at=NOW - timedelta(hours=30))
    storage.put(fresh, JPEG, at=NOW - timedelta(hours=1))
    session.add(BookingLinePhoto(line_id=line.id, storage_key=attached, content_type="image/jpeg", size_bytes=10))
    session.commit()

    assert LinePhotos(storage, clock=lambda: NOW).purge_pending(session) == 1
    assert storage.deleted == [stale]


# ── booking creation hook (_create_booking_locked) ──────────────────────────
@pytest_asyncio.fixture
async def toolkit():
    from fakeredis import FakeAsyncRedis

    from src.infrastructure.redis import RedisToolkit

    redis = FakeAsyncRedis()
    tk = RedisToolkit(redis, key_prefix="test", default_cache_ttl=60)
    yield tk
    await tk.pubsub.stop()
    await tk.cache.write_back_buffer.stop(final_flush=False)
    await redis.flushall()
    await redis.aclose()


def _booking_service(session, toolkit, flow):
    from src.modules.booking.domain import BookingConfig
    from src.modules.booking.location import SimpleTextLocationFinder
    from src.modules.booking.service import BookingService

    return BookingService(session, toolkit, SimpleTextLocationFinder(), config=BookingConfig(pricing_flow=flow))


@pytest.mark.asyncio
@pytest.mark.parametrize("flow", ["two_tier", "legacy"])
async def test_new_booking_takes_the_flow_of_the_flag(world, toolkit, flow):
    from src.common.core.maintenance.booking import Booking
    from src.modules.booking.domain import now_vn

    session, user, vehicle, _, workshop = world
    day = now_vn().date() + timedelta(days=3)
    out = await _booking_service(session, toolkit, flow).create_for_slot(
        user, vehicle.id, workshop.id, day, time(9), source="APP", odo_milestone=12_000
    )
    booking = session.get(Booking, out.booking_id)
    lines = _lines(session, booking)
    assert booking.pricing_flow == flow
    if flow == "two_tier":
        assert set(lines) == {"BRAKE_INSPECTION", "BATTERY_CHECK", "CABIN_FILTER"}
        assert out.estimated_cost == 550_000
    else:
        assert lines == {} and out.estimated_cost is None


@pytest.mark.asyncio
async def test_two_tier_refuses_a_legacy_quote(world, toolkit):
    from uuid import uuid4

    from src.modules.booking import errors as booking_errors
    from src.modules.booking.domain import now_vn

    session, user, vehicle, _, workshop = world
    with pytest.raises(booking_errors.LegacyQuoteNotAcceptedError):
        await _booking_service(session, toolkit, "two_tier").create_for_slot(
            user, vehicle.id, workshop.id, now_vn().date() + timedelta(days=3), time(9), source="APP", quote_id=uuid4()
        )


# ── in-app feed (re-review OV8) ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_feed_has_one_entry_per_line_version(world):
    from src.modules.notification.feed_service import NotificationFeedService

    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    svc = _svc(session)
    line = (await svc.propose_extra(owner, workshop, booking.id, _extra())).lines[-1]
    feed = NotificationFeedService(session, clock=lambda: datetime.now(UTC))

    def entries():
        return [i for i in feed.list_for_user(user).items if i.kind == "BOOKING_LINE"]

    assert [(i.id, i.unread) for i in entries()] == [(f"booking-line:{line.line_id}:1", True)]
    await svc.edit_line(
        owner, workshop, booking.id, line.line_id, s.EditLineRequest(expected_version=1, price=1, reason="x" * 10)
    )
    assert [i.id for i in entries()] == [f"booking-line:{line.line_id}:2"]
    svc.decide(user, booking.id, line.line_id, s.DecideRequest(decision="APPROVE", seen_version=2))
    assert entries() == []


# ── pricing flow for the apps ───────────────────────────────────────────────
@pytest.mark.parametrize("flow", ["legacy", "two_tier"])
def test_pricing_flow_endpoint_reports_the_flag(monkeypatch, flow):
    from types import SimpleNamespace

    from src.modules.booking_line import route

    monkeypatch.setattr(route, "get_settings", lambda: SimpleNamespace(quote_flow=flow))
    out = route.get_pricing_flow().model_dump(by_alias=True)
    assert out == {"data": {"quoteFlow": flow}}


# Regression: ISSUE-004 — a reference price the workshop confirmed still read "Giá tham khảo"
# Found by /qa on 2026-10-10
# Report: .gstack/qa-reports/run-20261009T201844Z/qa-report-localhost-2026-10-10.md
@pytest.mark.asyncio
async def test_confirmed_reference_price_is_labelled_as_confirmed(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop)
    cabin = _lines(session, booking)["CABIN_FILTER"]
    assert (
        next(x for x in _svc(session).view(booking).lines if x.item_code == "CABIN_FILTER").price_label
        == "Giá tham khảo"
    )
    view = await _svc(session).confirm_package(
        owner, workshop, booking.id, cabin.id, s.ConfirmPackageRequest(expected_version=1, price=200_000)
    )
    assert next(x for x in view.lines if x.item_code == "CABIN_FILTER").price_label == "Xưởng đã xác nhận"


# Design review 2026-10-10 D1 = A: the workshop dashboard counts extras waiting for the owner
@pytest.mark.asyncio
async def test_board_counts_lines_awaiting_the_owner(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    board = _board(session)
    assert board.list_bookings(workshop, from_=TODAY, to=TODAY, statuses=None, q=None).items[0].awaiting_owner == 0
    svc = _svc(session)
    first = (await svc.propose_extra(owner, workshop, booking.id, _extra())).lines[-1]
    await svc.propose_extra(owner, workshop, booking.id, _extra(price=90_000, item_name="Vệ sinh khoang máy"))
    assert board.list_bookings(workshop, from_=TODAY, to=TODAY, statuses=None, q=None).items[0].awaiting_owner == 2
    svc.decide(user, booking.id, first.line_id, s.DecideRequest(decision="APPROVE", seen_version=1))
    assert board.list_bookings(workshop, from_=TODAY, to=TODAY, statuses=None, q=None).items[0].awaiting_owner == 1


# ── decisions recorded by phone (TODOS P2, concern R2-2) ───────────────────
def _phone(decision="APPROVE", seen=1, name="Anh Trung (chủ xe)", **kw) -> s.PhoneDecisionRequest:
    return s.PhoneDecisionRequest(decision=decision, seen_version=seen, confirmed_by_name=name, **kw)


@pytest.mark.asyncio
async def test_workshop_records_a_phone_answer_and_the_owner_is_told(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    notifier = FakeNotifier()
    svc = _svc(session, notifier)
    proposed = await svc.propose_extra(owner, workshop, booking.id, _extra())
    extra = proposed.lines[-1]
    notifier.sent.clear()

    view = await svc.record_phone_decision(owner, workshop, booking.id, extra.line_id, _phone())
    line = view.lines[-1]
    assert line.status == "APPROVED" and line.decided_via == "PHONE" and line.version == 2
    assert line.phone_confirmed_by == "Anh Trung (chủ xe)" and line.can_dispute
    assert view.current_total == proposed.current_total + 500_000  # charged like an app approval
    row = _lines(session, booking)["Thay má phanh trước"]
    assert row.recorded_by == owner.id and row.decided_by is None
    assert (
        len(notifier.sent) == 1
        and "qua điện thoại" in notifier.sent[0][1]
        and "Tôi không đồng ý" in notifier.sent[0][1]
    )

    # The owner's own decision is APP and cannot be disputed.
    other = (
        await svc.propose_extra(owner, workshop, booking.id, _extra(price=90_000, item_name="Vệ sinh khoang máy"))
    ).lines[-1]
    decided = svc.decide(user, booking.id, other.line_id, s.DecideRequest(decision="APPROVE", seen_version=1)).lines[-1]
    assert decided.decided_via == "APP" and not decided.can_dispute
    with pytest.raises(errors.InvalidRequestError):
        svc.dispute(user, booking.id, other.line_id, s.DisputeRequest(seen_version=2))


@pytest.mark.asyncio
async def test_phone_decision_guards(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    svc = _svc(session)
    extra = (await svc.propose_extra(owner, workshop, booking.id, _extra(is_safety_critical=True))).lines[-1]
    with pytest.raises(ValueError):
        _phone(name=" ")
    with pytest.raises(errors.SafetyConfirmationRequiredError):
        await svc.record_phone_decision(owner, workshop, booking.id, extra.line_id, _phone("DECLINE"))
    with pytest.raises(errors.LineChangedError):
        await svc.record_phone_decision(owner, workshop, booking.id, extra.line_id, _phone(seen=7))
    view = await svc.record_phone_decision(
        owner, workshop, booking.id, extra.line_id, _phone("DECLINE", confirm_safety=True)
    )
    assert view.lines[-1].status == "DECLINED"
    # Already settled: a second recording (or the owner on the app) loses.
    with pytest.raises(errors.LineChangedError):
        await svc.record_phone_decision(owner, workshop, booking.id, extra.line_id, _phone(seen=1))
    other_ws = add_workshop(session, name="Other", owner=add_workshop_owner(session, uid="ws-2"))
    with pytest.raises(errors.BookingNotFoundError):
        await svc.record_phone_decision(owner, other_ws, booking.id, extra.line_id, _phone(seen=2))


@pytest.mark.asyncio
async def test_owner_disputes_a_phone_decision_before_complete(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    svc, board = _svc(session), _board(session)
    extra = (await svc.propose_extra(owner, workshop, booking.id, _extra())).lines[-1]
    recorded = (await svc.record_phone_decision(owner, workshop, booking.id, extra.line_id, _phone())).lines[-1]
    approved_total = svc.view(booking).current_total

    with pytest.raises(errors.LineChangedError):  # the owner decides on what they saw
        svc.dispute(user, booking.id, extra.line_id, s.DisputeRequest(seen_version=1))
    view = svc.dispute(user, booking.id, extra.line_id, s.DisputeRequest(seen_version=recorded.version))
    line = view.lines[-1]
    assert line.status == "PROPOSED" and line.decided_via is None and line.phone_confirmed_by is None
    assert line.disputed_at is not None and line.version == recorded.version + 1
    assert view.current_total == approved_total - 500_000  # not charged until the owner decides again
    assert board.detail(workshop, booking.id).blocked_actions[0].reason_code == "BOOKING_LINES_UNSETTLED"

    # The owner then decides on the app like any proposed line.
    decided = svc.decide(
        user, booking.id, extra.line_id, s.DecideRequest(decision="DECLINE", seen_version=line.version)
    )
    assert decided.lines[-1].status == "DECLINED" and decided.lines[-1].decided_via == "APP"


@pytest.mark.asyncio
async def test_no_dispute_once_the_booking_is_complete(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    cabin = _lines(session, booking)["CABIN_FILTER"]
    cabin.line_status = LineStatus.CONFIRMED  # confirmed at check-in
    session.add(cabin)
    session.commit()
    svc, board = _svc(session), _board(session)
    extra = (await svc.propose_extra(owner, workshop, booking.id, _extra())).lines[-1]
    recorded = (await svc.record_phone_decision(owner, workshop, booking.id, extra.line_id, _phone())).lines[-1]
    await board.transition(owner, workshop, booking.id, _move("COMPLETE", "IN_PROGRESS"))
    assert not svc.view(booking).lines[-1].can_dispute
    with pytest.raises(errors.BookingStatusInvalidError):
        svc.dispute(user, booking.id, extra.line_id, s.DisputeRequest(seen_version=recorded.version))


# Regression: smoke test 2026-10-10 — a decision the workshop recorded by phone never reached the feed
@pytest.mark.asyncio
async def test_feed_shows_a_phone_decision_until_complete(world):
    from src.modules.notification.feed_service import NotificationFeedService

    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    svc = _svc(session)
    line = (await svc.propose_extra(owner, workshop, booking.id, _extra())).lines[-1]
    await svc.record_phone_decision(owner, workshop, booking.id, line.line_id, _phone())
    feed = NotificationFeedService(session, clock=lambda: datetime.now(UTC))
    [entry] = [i for i in feed.list_for_user(user).items if i.kind == "BOOKING_LINE"]
    assert entry.id == f"booking-line:{line.line_id}:2" and entry.unread
    assert entry.booking_line.status == "APPROVED" and entry.booking_line.decided_via == "PHONE"
    assert entry.booking_line.phone_confirmed_by == "Anh Trung (chủ xe)"

    # Disputed: the line is PROPOSED again (version 3) and the phone entry is gone.
    svc.dispute(user, booking.id, line.line_id, s.DisputeRequest(seen_version=2))
    assert [i.id for i in feed.list_for_user(user).items if i.kind == "BOOKING_LINE"] == [
        f"booking-line:{line.line_id}:3"
    ]


# ── owner reply SLA (open question 2: the workshop calls after 10 minutes) ──
def _at(minutes: float):
    return lambda: NOW + timedelta(minutes=minutes)


@pytest.mark.asyncio
async def test_workshop_calls_the_owner_ten_minutes_after_asking(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop, status=BookingStatus.IN_PROGRESS)
    notifier = FakeNotifier()
    extra = (await _svc(session, notifier).propose_extra(owner, workshop, booking.id, _extra())).lines[-1]
    assert extra.reply_due_at == NOW + timedelta(minutes=10) and not extra.call_owner
    assert "Chưa có trả lời sau 10 phút, xưởng sẽ gọi cho bạn." in notifier.sent[-1][1]

    def at(minutes):
        return BookingLineService(session, clock=_at(minutes)).view(booking).lines[-1]

    assert not at(9.9).call_owner
    assert at(10).call_owner
    board = WorkshopBoardService(session, clock=_at(10)).list_bookings(
        workshop, from_=TODAY, to=TODAY, statuses=None, q=None
    )
    item = next(i for i in board.items if i.booking_id == booking.id)
    assert (item.awaiting_owner, item.owner_reply_overdue) == (1, 1)

    # Resending the line restarts the clock.
    edited = (
        await BookingLineService(session, clock=_at(12)).edit_line(
            owner,
            workshop,
            booking.id,
            extra.line_id,
            s.EditLineRequest(expected_version=1, price=450_000, reason=extra.reason),
        )
    ).lines[-1]
    assert edited.reply_due_at == NOW + timedelta(minutes=22) and not edited.call_owner

    # Once the owner answers there is nothing to call about.
    decided = BookingLineService(session, clock=_at(30)).decide(
        user, booking.id, extra.line_id, s.DecideRequest(decision="APPROVE", seen_version=edited.version)
    )
    assert decided.lines[-1].reply_due_at is None and not decided.lines[-1].call_owner


@pytest.mark.asyncio
async def test_a_raised_package_price_and_a_dispute_also_start_the_clock(world):
    session, user, vehicle, owner, workshop = world
    booking = _booking(session, user, vehicle, workshop)
    cabin = _lines(session, booking)["CABIN_FILTER"]
    raised = await _svc(session).confirm_package(
        owner,
        workshop,
        booking.id,
        cabin.id,
        s.ConfirmPackageRequest(expected_version=1, price=300_000, reason="Lọc gió loại cao cấp hơn"),
    )
    line = next(x for x in raised.lines if x.item_code == "CABIN_FILTER")
    assert line.status == "PROPOSED" and line.reply_due_at == NOW + timedelta(minutes=10)

    booking.status = BookingStatus.IN_PROGRESS
    session.add(booking)
    session.commit()
    svc = BookingLineService(session, clock=_at(20))
    recorded = (
        await svc.record_phone_decision(owner, workshop, booking.id, line.line_id, _phone(seen=line.version))
    ).lines
    recorded_line = next(x for x in recorded if x.line_id == line.line_id)
    assert recorded_line.reply_due_at is None
    disputed = svc.dispute(user, booking.id, line.line_id, s.DisputeRequest(seen_version=recorded_line.version))
    again = next(x for x in disputed.lines if x.line_id == line.line_id)
    assert again.reply_due_at == NOW + timedelta(minutes=30)
