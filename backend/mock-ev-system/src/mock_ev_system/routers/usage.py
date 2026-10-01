"""API endpoints: Vehicle Usage — snapshot + SSE streaming."""

import asyncio
import json
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from ..db import get_session
from ..service import UsageService, VehicleService
from ..simulator import subscribe, unsubscribe

router = APIRouter(tags=["Vehicle Usage"])


@router.get(
    "/vehicles/{vehicle_id}/usage",
    summary="Snapshot sử dụng hiện tại (km, battery SOH)",
)
def get_usage(
    vehicle_id: str,
    session: Session = Depends(get_session),
):
    v_svc = VehicleService(session)
    if not v_svc.get_vehicle(vehicle_id):
        raise HTTPException(404, f"Vehicle {vehicle_id} not found")

    u_svc = UsageService(session)
    usage = u_svc.get_usage(vehicle_id)
    if not usage:
        raise HTTPException(404, f"No usage data for {vehicle_id}")

    return {
        "vehicle_id": usage.vehicle_id,
        "current_km": usage.current_km,
        "battery_soh": usage.battery_soh,
        "data_source": usage.data_source.value,
        # Stored as naive UTC; emit an explicit offset so clients do not guess the zone.
        "last_updated_at": usage.last_updated_at.replace(tzinfo=UTC).isoformat(),
    }


@router.get(
    "/vehicles/{vehicle_id}/usage/stream",
    summary="SSE stream — cập nhật km realtime",
    response_class=StreamingResponse,
)
async def stream_usage(vehicle_id: str):
    """Server-Sent Events stream cho odometer updates.

    Client mở kết nối và nhận event mỗi khi simulator tick (mỗi 5s).
    Format: `data: {"vehicle_id": "...", "current_km": ..., ...}\n\n`
    """
    queue = await subscribe(vehicle_id)

    async def event_generator():
        try:
            while True:
                data = await queue.get()
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await unsubscribe(vehicle_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx
        },
    )
