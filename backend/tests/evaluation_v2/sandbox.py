"""Real domain services on an isolated SQL database and FakeAsyncRedis.

Only the chat/message adapters and (optionally) RAG are fixtures. No production
database/Redis factory is used and no email transport is instantiated.
"""
from __future__ import annotations

import json
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from fakeredis import FakeAsyncRedis
from sqlalchemy import MetaData
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from src.agents.tools.dependency import AgentToolServices, build_customer_agent_tools
from src.agents.tools.RAG.query.schemas import CitationItem, RAGResponse
from src.common.core.identity import VehicleUser
from src.common.core.maintenance.booking import Booking
from src.common.core.maintenance.booking_proposal import BookingProposal
from src.common.core.maintenance.maintenance_rule import MaintenanceRule
from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.workshop.service_price import ServicePrice
from src.infrastructure.redis import RedisToolkit
from src.modules.booking.domain import BookingConfig
from src.modules.booking.location import SimpleTextLocationFinder
from src.modules.booking.service import BookingService
from src.modules.cost_estimate.service import CostEstimationService
from src.modules.notification.context_service import ReminderContextService
from src.modules.notification.schemas import ChannelChangeIn, NotificationChannel, NotificationSettingsUpdateIn
from src.modules.notification.settings_service import NotificationSettingsService
from src.modules.quick_booking.domain import QuickBookingConfig
from src.modules.quick_booking.service import QuickBookingService
from src.modules.user_vehicle.domain import DueConfig
from src.modules.user_vehicle.service import UserVehicleService
from tests._maintenance import TABLES
from tests._user_vehicle import MODEL_ID, RecordingScheduler, _make_sqlite_compatible, add_rules
from tests.test_modules.test_quick_booking import FakeChat, FakeMessages, _owner_with_vehicle, _workshop

NOW = datetime(2026, 10, 7, 9, tzinfo=timezone(timedelta(hours=7)))


class FixtureRAG:
    def __init__(self, case):
        self.case = case

    def query_sync(self, **kwargs):
        # This mode tests orchestration only; its citations are explicitly fixtures.
        golden = self.case.get("golden", {})
        answer = golden.get("expected_answer") or "Không có tài liệu phù hợp để xác minh thông tin này."
        ids = golden.get("relevant_doc_ids", [])
        citations = [CitationItem(document_id=doc, chunk_id="fixture-" + doc, title="Evaluation fixture (not live retrieval)") for doc in ids]
        return RAGResponse(answer=answer, citations=citations, confidence="medium" if ids else "low", fallback_required=not ids, metadata={"fixture": True})


class Sandbox:
    def __init__(self, case: dict, *, rag_pipeline=None, database_path=None, engine=None, redis_client=None, key_prefix=None):
        self.clock = ExitStack()
        for module in ("src.modules.booking.domain", "src.modules.booking.service", "src.modules.quick_booking.service", "src.agents.prompts", "tests.test_modules.test_quick_booking"):
            self.clock.enter_context(patch(module + ".now_vn", return_value=NOW))
        url = "sqlite://" if database_path is None else "sqlite:///" + str(database_path)
        kwargs = {"poolclass": StaticPool} if database_path is None else {}
        self.engine = engine if engine is not None else create_engine(url, connect_args={"check_same_thread": False}, **kwargs)
        metadata = MetaData()
        for table in TABLES:
            cloned = table.to_metadata(metadata)
            if self.engine.dialect.name == "sqlite":
                _make_sqlite_compatible(cloned)
        metadata.create_all(self.engine)
        self.redis = redis_client if redis_client is not None else FakeAsyncRedis()
        self.toolkit = RedisToolkit(self.redis, key_prefix=key_prefix or "eval-v2-" + uuid4().hex, default_cache_ttl=60)
        self.case = case
        with self.open_session() as db:
            user, vehicle, conversation = _owner_with_vehicle(db, odo=case.get("odo", 12500))
            user.email_verified = True
            db.add(user)
            add_rules(db)
            workshops = [_workshop(db, "VinFast Thanh Xuan", 2), _workshop(db, "VinFast Ha Dong", 4)]
            for workshop in workshops:
                # Existing helper already creates hours. Keep its generated UUIDs
                # and render scenario placeholders from actual seeded IDs.
                for rule in db.exec(select(MaintenanceRule)).all():
                    db.add(ServicePrice(workshop_id=workshop.id, model_id=MODEL_ID, item_code=rule.item_code, item_name=rule.item_name, price=100000))
            db.commit()
            initial = case.get("notification_fixture")
            if initial:
                NotificationSettingsService(db, available_channels={ReminderChannel.IN_APP, ReminderChannel.EMAIL}, default_lead_days=2, email_mode="mock").update(
                    user, NotificationSettingsUpdateIn(
                        reminders_enabled=initial.get("reminders_enabled"),
                        reminder_lead_days=initial.get("reminder_lead_days"),
                        channels=[ChannelChangeIn(channel=NotificationChannel.EMAIL, enabled=initial["email_enabled"])] if "email_enabled" in initial else None,
                    ),
                )
            self.user_id, self.vehicle_id, self.conversation_id = user.user_id, vehicle.id, conversation.id
            self.workshop_a, self.workshop_b = (str(w.id) for w in workshops)
        self.context = {"model": "VF6", "current_odo": case.get("odo", 12500), "vehicle_id": str(self.vehicle_id)}
        pipeline = rag_pipeline or FixtureRAG(case)
        self.services = AgentToolServices(
            open_session=self.open_session,
            user_vehicle_service=self.vehicles,
            cost_estimation_service=self.estimates,
            booking_service=lambda db: BookingService(db, self.toolkit, SimpleTextLocationFinder(), config=BookingConfig()),
            quick_booking_service=self.quick_booking,
            rag_pipeline=lambda: pipeline,
            notification_settings_service=lambda db: NotificationSettingsService(db, available_channels={ReminderChannel.IN_APP, ReminderChannel.EMAIL}, default_lead_days=2, email_mode="mock"),
            reminder_context_service=lambda db: ReminderContextService(db, self.vehicles(db)),
        )
        self.tools = build_customer_agent_tools(self.services)

    @contextmanager
    def open_session(self):
        with Session(self.engine) as db:
            yield db

    def vehicles(self, db):
        return UserVehicleService(db, RecordingScheduler(), config=DueConfig(), clock=lambda: NOW)

    def estimates(self, db):
        vehicles = self.vehicles(db)
        def milestone(vehicle):
            result = vehicles.calculate(vehicle).next_milestone
            return result.odo_milestone_km if result else None
        service = CostEstimationService(db, SimpleTextLocationFinder(), milestone, clock=lambda: NOW)
        if self.case.get("fault") == "estimate_service_cost":
            from src.modules.cost_estimate.errors import CostEstimateError
            def failure(*args, **kwargs):
                raise CostEstimateError("Injected evaluation timeout; no price is available.")
            service.estimate_for_request = failure
        return service

    def quick_booking(self, db):
        finder = SimpleTextLocationFinder()
        return QuickBookingService(
            db, bookings=self.services.booking_service(db), vehicles=self.vehicles(db), estimates=self.estimates(db),
            finder=finder, toolkit=self.toolkit, config=QuickBookingConfig(), chat=FakeChat(), messages=FakeMessages(db), clock=lambda: NOW,
        )

    def render(self, value):
        replacements = {"{workshop_a}": self.workshop_a, "{workshop_b}": self.workshop_b, "{vehicle_id}": str(self.vehicle_id)}
        text = json.dumps(value, ensure_ascii=False)
        for key, replacement in replacements.items():
            text = text.replace(key, replacement)
        return json.loads(text)

    def config(self, thread_id):
        return {"configurable": {"thread_id": thread_id, "user_id": self.user_id, "user_vehicle_id": str(self.vehicle_id), "conversation_id": str(self.conversation_id)}, "recursion_limit": 20}

    def side_effects(self):
        with self.open_session() as db:
            return {"booking_count_before_confirm": len(db.exec(select(Booking)).all()), "proposal_count": len(db.exec(select(BookingProposal)).all())}

    def reminder_state(self):
        with self.open_session() as db:
            user = db.get(VehicleUser, self.user_id)
            settings = self.services.notification_settings_service(db).get(user)
            email = next(channel.enabled for channel in settings.channels if channel.channel.value == "EMAIL")
            return {"reminders_enabled": settings.reminders_enabled, "email_enabled": email, "reminder_lead_days": settings.reminder_lead_days}

    async def close(self):
        await self.toolkit.pubsub.stop()
        await self.toolkit.cache.write_back_buffer.stop(final_flush=False)
        await self.redis.aclose()
        self.engine.dispose()
        self.clock.close()
