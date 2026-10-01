"""Odometer simulator — tăng km theo thời gian thực + SSE stream.

Background task chạy khi app startup:
- Mỗi TICK_SECONDS giây, tăng current_km của mỗi xe thêm KM_PER_TICK.
- Subscribers (SSE clients) nhận event mỗi khi có update.

Dùng asyncio.Event để decouple producer (background) và consumer (SSE).
"""

import asyncio
import json
from collections import defaultdict
from datetime import UTC, datetime

from sqlmodel import Session, select

from .db import engine
from .models import VehicleUsage
from .webhooks import dispatch_usage_updated

# Cấu hình simulation
TICK_SECONDS = 5  # Cập nhật mỗi 5 giây
KM_PER_TICK = 2  # +2 km mỗi tick (tương đương ~34 km/phút — tăng nhanh cho demo)

# Subscribers: vehicle_id → list of asyncio.Queue
_subscribers: dict[str, list[asyncio.Queue[dict]]] = defaultdict(list)

# Lock để tránh race condition khi thêm/xóa subscriber
_lock = asyncio.Lock()


async def subscribe(vehicle_id: str) -> asyncio.Queue[dict]:
    """Đăng ký nhận update cho 1 xe. Trả về Queue để SSE đọc."""
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=50)
    async with _lock:
        _subscribers[vehicle_id].append(queue)
    return queue


async def unsubscribe(vehicle_id: str, queue: asyncio.Queue[dict]) -> None:
    """Hủy đăng ký khi SSE client disconnect."""
    async with _lock:
        try:
            _subscribers[vehicle_id].remove(queue)
        except ValueError:
            pass


async def _notify(vehicle_id: str, data: dict) -> None:
    """Gửi data đến tất cả subscriber của 1 xe."""
    async with _lock:
        queues = list(_subscribers.get(vehicle_id, []))
    for q in queues:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass  # Bỏ qua client chậm


async def odometer_tick() -> None:
    """Một lần tick: tăng km cho tất cả xe, gửi event."""
    with Session(engine) as session:
        usages = list(session.exec(select(VehicleUsage)).all())
        # Stored as naive UTC (SQLite has no tz); exposed with an explicit offset.
        now = datetime.now(UTC).replace(tzinfo=None)

        for usage in usages:
            usage.current_km += KM_PER_TICK
            usage.last_updated_at = now
            session.add(usage)

            # Notify subscribers
            data = {
                "vehicle_id": usage.vehicle_id,
                "current_km": usage.current_km,
                "battery_soh": usage.battery_soh,
                "last_updated_at": now.replace(tzinfo=UTC).isoformat(),
            }
            await _notify(usage.vehicle_id, data)

        vehicle_ids = [usage.vehicle_id for usage in usages]
        session.commit()

    # Notify EV Care after commit so its pull sees the new value (throttled per vehicle).
    for vehicle_id in vehicle_ids:
        dispatch_usage_updated(vehicle_id)


async def run_simulator() -> None:
    """Background loop — chạy liên tục cho đến khi app shutdown."""
    while True:
        await odometer_tick()
        await asyncio.sleep(TICK_SECONDS)
