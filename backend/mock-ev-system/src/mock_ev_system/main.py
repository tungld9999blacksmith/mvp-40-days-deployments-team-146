"""FastAPI app — Mock EV System.

Giả lập toàn bộ API hệ thống hãng xe điện:
- Thông tin xe, chủ xe (lookup, tra cứu VIN/biển số)
- Bảo hành (policy, contract, claim + lý do từ chối)
- Bảo dưỡng (lịch chuẩn, lịch sử thực tế, mốc tiếp theo computed)
- Usage realtime (snapshot + SSE stream odometer)
- Master data (models, service centers)

Chạy: uv run --package mock-ev-system uvicorn mock_ev_system.main:app --reload --port 8100
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from .auth import require_access_token
from .db import init_db
from .routers import admin, lookup, maintenance, oauth, usage, vehicles, verify, warranty, webhooks
from .simulator import run_simulator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Khởi tạo DB + seed data
    init_db()

    # Odometer simulator: tắt mặc định (km đứng yên, không bắn webhook hàng loạt).
    # Bật lại bằng MOCK_ODOMETER_SIMULATOR=1.
    simulator_task = (
        asyncio.create_task(run_simulator())
        if os.getenv("MOCK_ODOMETER_SIMULATOR", "").lower() in {"1", "true", "yes"}
        else None
    )

    yield

    # Cleanup khi shutdown
    if simulator_task is not None:
        simulator_task.cancel()
        try:
            await simulator_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Mock EV System",
    description=(
        "Giả lập toàn bộ API hệ thống công ty xe điện.\n\n"
        "**Nhóm API:**\n"
        "- 🚗 Vehicles & Owners — thông tin xe, chủ xe, tra cứu VIN/biển số\n"
        "- 🛡️ Warranty — chính sách, hợp đồng, yêu cầu bảo hành\n"
        "- 🔧 Maintenance — lịch bảo dưỡng, lịch sử, mốc tiếp theo\n"
        "- 📊 Vehicle Usage — snapshot & SSE stream odometer realtime\n"
        "- 📋 Lookup — mẫu xe, xưởng dịch vụ\n"
        "- 🔔 Webhooks — signed notifications to EV Care (usage / service history)\n"
        "- 🔑 OAuth — `POST /oauth/token`: client assertion → access token (M2M)"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Business routers require an access token from POST /oauth/token (SPEC-SEC-OEM-M2M-001 v2.0)
# once EVCARE_PUBLIC_KEY is configured or MOCK_AUTH_REQUIRED is on.
m2m_deps = [Depends(require_access_token)]
app.include_router(oauth.router)
app.include_router(vehicles.router, dependencies=m2m_deps)
app.include_router(verify.router, dependencies=m2m_deps)
app.include_router(warranty.router, dependencies=m2m_deps)
app.include_router(maintenance.router, dependencies=m2m_deps)
app.include_router(usage.router, dependencies=m2m_deps)
app.include_router(lookup.router, dependencies=m2m_deps)
app.include_router(webhooks.router)
app.include_router(admin.router)


@app.get("/health", tags=["System"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
