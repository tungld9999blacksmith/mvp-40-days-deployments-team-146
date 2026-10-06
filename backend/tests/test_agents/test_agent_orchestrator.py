"""Demo walkthrough of ``run_agent_turn`` with a live LLM and the real tools.

The tools run against an in-memory SQLite + fakeredis seeded with one owner,
one VF6 at 11,500 km and one workshop, like ``test_ev_care_tools``.
"""

import os
import sys
from contextlib import contextmanager
from datetime import time
from pathlib import Path

# Fix Windows console encoding for UTF-8
if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")

os.environ["LANGCHAIN_TRACING_V2"] = "false"

backend_dir = Path(__file__).resolve().parent.parent.parent

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from fakeredis import FakeAsyncRedis

env_path = backend_dir.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

from src.agents.orchestrator import run_agent_turn
from src.agents.tools import _services
from src.common.core.workshop.service_price import ServicePrice
from src.infrastructure.redis import RedisToolkit
from tests._maintenance import add_hours, add_workshop, make_session
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


@pytest.fixture
def seeded(monkeypatch, session, toolkit):
    @contextmanager
    def open_session():
        yield session

    monkeypatch.setattr(_services, "open_session", open_session)
    monkeypatch.setattr(_services, "redis_toolkit", lambda: toolkit)

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
    session.add(user)
    session.commit()
    return user, vehicle


@pytest.mark.asyncio
async def test_vf6_demo_walkthrough(seeded):
    """Chủ xe VF6 (11.500 km) hỏi cần làm gì, giá bao nhiêu, và nhờ tìm lịch chiều thứ Bảy."""
    user, vehicle = seeded
    vehicle_context = {"vehicle_id": str(vehicle.id), "model": "VF6", "license_plate": vehicle.license_plate}
    user_message = (
        "Xe của tôi sắp tới cần bảo dưỡng gì và chi phí bao nhiêu? "
        "Tìm giúp tôi khung giờ chiều thứ Bảy ở xưởng VinFast Thanh Xuân."
    )

    tools_called = []
    tokens = []
    completed_data = None

    print(f"\n[CHỦ XE]: {user_message}\n")
    async for event in run_agent_turn(
        conversation_id="conv-demo-01",
        user_id=user.user_id,
        vehicle_id=vehicle.id,
        message=user_message,
        vehicle_context=vehicle_context,
    ):
        if event["type"] == "tool_start":
            tools_called.append(event["tool"])
            print(f"\n⚙️ [GỌI TOOL]: {event['tool']} (Inputs: {event.get('input')})")
        elif event["type"] == "token":
            tokens.append(event["delta"])
            print(event["delta"], end="", flush=True)
        elif event["type"] == "completed":
            completed_data = event["message_data"]

    full_response = "".join(tokens) or (completed_data["content"] if completed_data else "")
    print(f"\n\nTools: {tools_called}")

    assert "get_due_maintenance" in tools_called
    assert "estimate_service_cost" in tools_called
    assert tools_called.index("get_due_maintenance") < tools_called.index("estimate_service_cost")
    assert "get_available_slots" in tools_called
    # Chủ xe chưa chốt giờ: chưa tạo cả đề xuất, và không tool nào tạo lịch hẹn.
    assert "propose_booking" not in tools_called

    resp_lower = full_response.lower()
    assert "12.000" in full_response or "12,000" in full_response, "Phải nêu mốc 12.000 km lấy từ dữ liệu xe"
    assert any(k in resp_lower for k in ["chi phí", "giá", "350"]), "Phải có dự toán chi phí"
    assert "khung giờ" in resp_lower or ":00" in resp_lower, "Phải đề xuất khung giờ"
