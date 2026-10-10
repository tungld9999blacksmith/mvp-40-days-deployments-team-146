"""Three separate processes, real migrated DB/Redis/message persistence, synthetic owners."""
import argparse
import asyncio
import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from redis.asyncio import Redis  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402
from sqlmodel import Session, create_engine, select  # noqa: E402
from src.common.core.conversation import ChatMessage, MessageRole  # noqa: E402
from src.common.core.maintenance.booking import Booking  # noqa: E402
from src.common.core.maintenance.booking_proposal import BookingProposal  # noqa: E402
from src.infrastructure.messaging import MessageService  # noqa: E402
from src.infrastructure.redis import RedisToolkit  # noqa: E402
from src.modules.booking.domain import BookingConfig  # noqa: E402
from src.modules.booking.location import SimpleTextLocationFinder  # noqa: E402
from src.modules.booking.service import BookingService  # noqa: E402
from src.modules.cost_estimate.service import CostEstimationService  # noqa: E402
from src.modules.quick_booking.domain import QuickBookingConfig  # noqa: E402
from src.modules.quick_booking.service import QuickBookingService  # noqa: E402
from src.modules.user_vehicle.domain import DueConfig  # noqa: E402
from src.modules.user_vehicle.service import UserVehicleService  # noqa: E402
from tests._user_vehicle import RecordingScheduler  # noqa: E402
from tests.evaluation_v2.sandbox import NOW, Sandbox  # noqa: E402
from tests.test_modules.test_quick_booking import FakeChat  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=("propose", "confirm", "replay"))
args = parser.parse_args()


def save(name, data):
    with (HERE / name).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, default=str)


async def run():
    engine = create_engine("postgresql+psycopg://p146_eval:p146_eval_local@127.0.0.1:35432/p146_eval_booking")
    with engine.connect() as connection:
        assert tuple(connection.execute(text("SELECT current_database(), current_user")).one()) == ("p146_eval_booking", "p146_eval")
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "e7a9c2b4d6f8"
    redis = Redis.from_url("redis://127.0.0.1:36379/0", socket_timeout=5, socket_connect_timeout=5)
    await redis.ping()
    fixture_path = HERE / "staging_process_fixture.json"
    prefix = "eval-process-" + uuid4().hex if args.mode == "propose" else json.loads(fixture_path.read_text(encoding="utf-8"))["redis_prefix"]
    toolkit = RedisToolkit(redis, key_prefix=prefix)
    sandbox = None
    try:
        if args.mode == "propose":
            tables_before = set(inspect(engine).get_table_names(schema="public"))
            with Session(engine) as db:
                assert not db.exec(select(Booking)).all()
                assert not db.exec(select(BookingProposal)).all()
            sandbox = Sandbox({}, engine=engine, redis_client=redis, key_prefix=prefix)
            assert set(inspect(engine).get_table_names(schema="public")) == tables_before, "Existing Alembic schema only; no new fixture tables"
            toolkit = sandbox.toolkit
            tool = next(t for t in sandbox.tools if t.name == "propose_booking")
            result = await tool.ainvoke({"name": tool.name, "args": {"workshop_id": sandbox.workshop_a, "booking_date": "2026-10-10", "time_slot": "14:00"}, "id": "persist-proposal", "type": "tool_call"}, sandbox.config("process-" + uuid4().hex))
            proposal_id = UUID(result.artifact["proposalId"])
            # Persist the actual artifact with the real PostgreSQL message store;
            # this driver does not invoke HTTP/Firebase/LLM or the ChatService.
            messages = MessageService(engine, toolkit.pubsub)
            card_message = await messages.append(sandbox.conversation_id, MessageRole.ASSISTANT, "Synthetic proposal persistence check", card=result.artifact)
            with Session(engine) as db:
                proposal = db.get(BookingProposal, proposal_id)
                proposal.message_id = card_message.message.id
                db.add(proposal)
                db.commit()
                assert len(db.exec(select(Booking)).all()) == 0
                assert len(db.exec(select(BookingProposal)).all()) == 1
            fixture = {"user_id": sandbox.user_id, "conversation_id": str(sandbox.conversation_id), "proposal_id": str(proposal_id), "proposal_message_id": str(card_message.message.id), "redis_prefix": prefix}
            save("staging_process_fixture.json", fixture)
            receipt = {"booking_count": 0, "proposal_count": 1, "message_count": 1, "migrated_schema_reused": True}
        else:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            with ExitStack() as clock:
                for module in ("src.modules.booking.domain", "src.modules.booking.service", "src.modules.quick_booking.service"):
                    clock.enter_context(patch(module + ".now_vn", return_value=NOW))
                with Session(engine) as db:
                    proposal = db.get(BookingProposal, UUID(fixture["proposal_id"]))
                    assert proposal is not None and db.get(ChatMessage, UUID(fixture["proposal_message_id"])) is not None
                    finder = SimpleTextLocationFinder()
                    vehicles = UserVehicleService(db, RecordingScheduler(), config=DueConfig(), clock=lambda: NOW)
                    def milestone(vehicle):
                        next_due = vehicles.calculate(vehicle).next_milestone
                        return next_due.odo_milestone_km if next_due else None
                    service = QuickBookingService(db, bookings=BookingService(db, toolkit, finder, config=BookingConfig()), vehicles=vehicles, estimates=CostEstimationService(db, finder, milestone, clock=lambda: NOW), finder=finder, toolkit=toolkit, config=QuickBookingConfig(), chat=FakeChat(), messages=MessageService(engine, toolkit.pubsub), clock=lambda: NOW)
                    confirmed = await service.confirm(fixture["user_id"], UUID(fixture["conversation_id"]), UUID(fixture["proposal_id"]))
                    assert confirmed.replayed is (args.mode == "replay")
                    bookings = db.exec(select(Booking)).all()
                    messages = db.exec(select(ChatMessage)).all()
                    assert len(bookings) == 1 and len(messages) == 2
                    if args.mode == "replay":
                        previous = json.loads((HERE / "staging_process_confirm.json").read_text(encoding="utf-8"))
                        assert str(bookings[0].id) == previous["booking_id"]
                    receipt = {"booking_count": len(bookings), "booking_id": str(bookings[0].id), "message_count": len(messages), "replayed": confirmed.replayed, "proposal_card_survived": True}
        receipt.update({"mode": args.mode, "process_id": os.getpid(), "scope": "SYNTHETIC_PROCESS_RESTART_NOT_HTTP_OR_UI", "database_port": 35432, "redis_port": 36379, "llm_called": False, "email_sent": False})
        save(f"staging_process_{args.mode}.json", receipt)
        print(json.dumps(receipt))
    finally:
        if sandbox is not None:
            await sandbox.close()
        else:
            await toolkit.pubsub.stop()
            await toolkit.cache.write_back_buffer.stop(final_flush=False)
            await redis.aclose()
            engine.dispose()


asyncio.run(run())
