"""Chạy 6 manual eval cases cho AI Agent MVP và in output thực tế.

TC-01 gọi LLM cấu hình thật qua ``run_agent_turn``. TC-02..TC-06 chạy các
business tools hiện hành trên SQLite in-memory + fakeredis với dữ liệu seed cố định.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import time, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR.parent / ".env")
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from fakeredis import FakeAsyncRedis  # noqa: E402
from langchain_core.messages import ToolMessage  # noqa: E402
from sqlmodel import select  # noqa: E402

from src.agents.orchestrator import run_agent_turn  # noqa: E402
from src.agents.tools import (  # noqa: E402
    _services,
    estimate_service_cost,
    find_workshops,
    get_available_slots,
    get_due_maintenance,
    propose_booking,
)
from src.common.core.conversation import Conversation  # noqa: E402
from src.common.core.maintenance.booking import Booking  # noqa: E402
from src.common.core.maintenance.booking_proposal import BookingProposal  # noqa: E402
from src.common.core.workshop.service_price import ServicePrice  # noqa: E402
from src.infrastructure.redis import RedisToolkit  # noqa: E402
from src.modules.booking.domain import now_vn  # noqa: E402
from tests._maintenance import add_hours, add_workshop, make_session  # noqa: E402
from tests._user_vehicle import (  # noqa: E402
    MODEL_ID,
    add_odometer,
    add_owner,
    add_rules,
    add_vehicle,
    mark_synced,
)


@dataclass
class EvalResult:
    case_id: str
    title: str
    verdict: str
    duration_ms: float
    input: Any
    actual_output: Any
    checks: dict[str, bool]


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def get_verdict(checks: dict[str, bool]) -> str:
    return "PASS" if all(checks.values()) else "FAIL"


def print_result(result: EvalResult) -> None:
    print(f"\n=== {result.case_id}: {result.title} ===")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))


def run_config(user: Any, vehicle: Any, conversation: Conversation | None = None) -> dict[str, Any]:
    configurable: dict[str, Any] = {
        "user_id": user.user_id,
        "user_vehicle_id": str(vehicle.id),
    }
    if conversation is not None:
        configurable["conversation_id"] = str(conversation.id)
    return {"configurable": configurable}


async def tc01_e2e(user: Any, vehicle: Any) -> EvalResult:
    user_input = (
        "Xe của tôi sắp tới cần bảo dưỡng gì và chi phí bao nhiêu? "
        "Tìm giúp tôi khung giờ chiều thứ Bảy ở xưởng VinFast Thanh Xuân."
    )
    context = {
        "vehicle_id": str(vehicle.id),
        "model": "VF6",
        "license_plate": vehicle.license_plate,
    }
    started = perf_counter()
    tools_called: list[str] = []
    tokens: list[str] = []
    completed: dict[str, Any] = {}

    async for event in run_agent_turn(
        conversation_id="manual-eval-conversation",
        user_id=user.user_id,
        vehicle_id=vehicle.id,
        message=user_input,
        vehicle_context=context,
    ):
        if event["type"] == "tool_start":
            tools_called.append(event["tool"])
        elif event["type"] == "token":
            tokens.append(event["delta"])
        elif event["type"] == "completed":
            completed = event["message_data"]

    answer = "".join(tokens) or str(completed.get("content", ""))
    answer_lower = answer.lower()
    checks = {
        "maintenance_called": "get_due_maintenance" in tools_called,
        "cost_called": "estimate_service_cost" in tools_called,
        "maintenance_before_cost": (
            "get_due_maintenance" in tools_called
            and "estimate_service_cost" in tools_called
            and tools_called.index("get_due_maintenance")
            < tools_called.index("estimate_service_cost")
        ),
        "slots_called": "get_available_slots" in tools_called,
        "no_premature_proposal": "propose_booking" not in tools_called,
        "answer_has_milestone": "12.000" in answer or "12,000" in answer,
        "answer_has_cost": any(term in answer_lower for term in ("chi phí", "giá", "350")),
        "answer_has_slots": "khung giờ" in answer_lower or ":00" in answer,
    }
    return EvalResult(
        "TC-01",
        "Walkthrough End-to-End với Gemini thật",
        get_verdict(checks),
        round((perf_counter() - started) * 1000, 2),
        {"message": user_input, "vehicle_context": context},
        {"tools_called": tools_called, "answer": answer, "citations": completed.get("citations", [])},
        checks,
    )


def tc02_maintenance(user: Any, vehicle: Any) -> EvalResult:
    started = perf_counter()
    output = get_due_maintenance.invoke({}, config=run_config(user, vehicle))
    checks = {
        "correct_vehicle": output.get("user_vehicle_id") == str(vehicle.id),
        "odometer_11500": output.get("odometer", {}).get("odo_km") == 11_500,
        "next_milestone_12000": output.get("next_milestone", {}).get("odo_milestone_km") == 12_000,
        "has_maintenance_items": bool(output.get("next_milestone", {}).get("items")),
    }
    return EvalResult(
        "TC-02",
        "Đọc đúng trạng thái bảo dưỡng của xe trong phiên",
        get_verdict(checks),
        round((perf_counter() - started) * 1000, 2),
        {},
        output,
        checks,
    )


def tc03_missing_context() -> EvalResult:
    started = perf_counter()
    output = get_due_maintenance.invoke({})
    checks = {
        "status_error": output.get("status") == "ERROR",
        "context_error": output.get("error_code") == "CHAT_CONTEXT_MISSING",
        "no_vehicle_data_leaked": "user_vehicle_id" not in output,
    }
    return EvalResult(
        "TC-03",
        "Guardrail từ chối khi thiếu authenticated chat context",
        get_verdict(checks),
        round((perf_counter() - started) * 1000, 2),
        {},
        output,
        checks,
    )


def tc04_cost(user: Any, vehicle: Any, workshop: Any) -> EvalResult:
    case_input = {"odo_milestone": 12_000, "workshop_id": str(workshop.id)}
    started = perf_counter()
    output = estimate_service_cost.invoke(case_input, config=run_config(user, vehicle))
    brake = next(
        (item for item in output.get("items", []) if item.get("item_code") == "BRAKE_INSPECTION"),
        {},
    )
    checks = {
        "status_ready": output.get("status") == "READY",
        "correct_workshop": output.get("workshop", {}).get("workshop_id") == str(workshop.id),
        "workshop_price_source": brake.get("price_source") == "WORKSHOP_PRICE",
        "brake_price_350000": float(brake.get("price", 0)) == 350_000,
    }
    return EvalResult(
        "TC-04",
        "Dự toán dùng bảng giá của xưởng",
        get_verdict(checks),
        round((perf_counter() - started) * 1000, 2),
        case_input,
        output,
        checks,
    )


async def tc05_workshop_slots(user: Any, vehicle: Any, workshop: Any, day: Any) -> EvalResult:
    case_input = {"area_or_address": "Hà Nội", "target_date": day.isoformat()}
    started = perf_counter()
    found = await find_workshops.ainvoke(
        {"area_or_address": case_input["area_or_address"]}, config=run_config(user, vehicle)
    )
    slots = await get_available_slots.ainvoke(
        {"workshop_id": str(workshop.id), "target_date": day.isoformat()},
        config=run_config(user, vehicle),
    )
    found_ids = [item.get("workshop_id") for item in found.get("workshops", [])]
    checks = {
        "expected_workshop_found": str(workshop.id) in found_ids,
        "correct_workshop_id": slots.get("workshop_id") == str(workshop.id),
        "correct_date": slots.get("date") == day.isoformat(),
        "has_available_slots": any(slot.get("available") for slot in slots.get("slots", [])),
    }
    return EvalResult(
        "TC-05",
        "Tìm xưởng và khung giờ từ service layer",
        get_verdict(checks),
        round((perf_counter() - started) * 1000, 2),
        case_input,
        {"workshops": found, "slots": slots},
        checks,
    )


async def tc06_proposal(
    session: Any,
    user: Any,
    vehicle: Any,
    workshop: Any,
    conversation: Conversation,
    day: Any,
) -> EvalResult:
    case_input = {
        "workshop_id": str(workshop.id),
        "booking_date": day.isoformat(),
        "time_slot": "09:00",
        "odo_milestone": 12_000,
    }
    started = perf_counter()
    message = await propose_booking.ainvoke(
        {"type": "tool_call", "id": "manual-eval-proposal", "name": "propose_booking", "args": case_input},
        config=run_config(user, vehicle, conversation),
    )
    assert isinstance(message, ToolMessage)
    proposals = session.exec(select(BookingProposal)).all()
    bookings = session.exec(select(Booking)).all()
    checks = {
        "status_proposed": '"status": "PROPOSED"' in message.content,
        "proposal_card_created": bool(message.artifact) and message.artifact.get("type") == "BOOKING_PROPOSAL",
        "proposal_persisted": len(proposals) == 1,
        "no_booking_created": bookings == [],
        "requires_owner_confirmation": "Xác nhận đặt lịch" in message.content,
    }
    return EvalResult(
        "TC-06",
        "Tạo đề xuất đặt lịch, chưa tự tạo booking",
        get_verdict(checks),
        round((perf_counter() - started) * 1000, 2),
        case_input,
        {"tool_message": to_jsonable(message), "proposal_count": len(proposals), "booking_count": len(bookings)},
        checks,
    )


async def main() -> int:
    session_source = make_session()
    session = next(session_source)
    redis = FakeAsyncRedis()
    toolkit = RedisToolkit(redis, key_prefix="manual-eval", default_cache_ttl=60)

    @contextmanager
    def open_session():
        yield session

    _services.open_session = open_session
    _services.redis_toolkit = lambda: toolkit

    try:
        user = add_owner(session)
        vehicle = add_vehicle(session, user)
        add_rules(session)
        add_odometer(session, vehicle, 11_500)
        mark_synced(session, vehicle)
        workshop = add_workshop(session, name="VinFast Thanh Xuân", region="Hà Nội")
        add_hours(session, workshop, open_at=time(8), close_at=time(17))
        session.add(
            ServicePrice(
                workshop_id=workshop.id,
                model_id=MODEL_ID,
                item_code="BRAKE_INSPECTION",
                item_name="Brake system inspection",
                price=350_000,
            )
        )
        user.preferred_workshop_id = workshop.id
        conversation = Conversation(user_id=user.user_id, user_vehicle_id=vehicle.id)
        session.add(user)
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        day = now_vn().date() + timedelta(days=3)

        results = [
            await tc01_e2e(user, vehicle),
            tc02_maintenance(user, vehicle),
            tc03_missing_context(),
            tc04_cost(user, vehicle, workshop),
            await tc05_workshop_slots(user, vehicle, workshop, day),
            await tc06_proposal(session, user, vehicle, workshop, conversation, day),
        ]
        for result in results:
            print_result(result)

        summary = {
            "total": len(results),
            "PASS": sum(result.verdict == "PASS" for result in results),
            "PARTIAL": sum(result.verdict == "PARTIAL" for result in results),
            "FAIL": sum(result.verdict == "FAIL" for result in results),
        }
        print("\n=== SUMMARY ===")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if summary["FAIL"] else 0
    finally:
        await toolkit.pubsub.stop()
        await toolkit.cache.write_back_buffer.stop(final_flush=False)
        await redis.flushall()
        await redis.aclose()
        session_source.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
