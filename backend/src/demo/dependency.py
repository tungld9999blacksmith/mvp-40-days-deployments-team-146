"""Firebase verification and application-scoped services; no SQL or Redis startup."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

from fastapi import Header, Request
from starlette.concurrency import run_in_threadpool

from .fixtures import ensure_user, seed_store
from .services import (
    MockBookingService,
    MockCostService,
    MockMaintenanceService,
    MockMessageService,
    MockVehicleService,
)
from .store import DemoError, DemoStore


@dataclass
class DemoServices:
    store: DemoStore
    vehicles: MockVehicleService
    maintenance: MockMaintenanceService
    cost: MockCostService
    messages: MockMessageService
    booking: MockBookingService


def make_services(store: DemoStore | None = None) -> DemoServices:
    persistent = store is None
    if store is None:
        store = DemoStore(skip_onboarding=False)
        if os.getenv("DEMO_NOW"):
            frozen = datetime.fromisoformat(os.environ["DEMO_NOW"])
            if frozen.utcoffset() is None:
                raise ValueError("DEMO_NOW must contain a timezone offset")
            frozen = frozen.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
            started = monotonic()
            store.clock = lambda: frozen + timedelta(seconds=monotonic() - started)
    seed_store(store)
    if persistent:
        from .persistence import load_registration

        default_path = Path(__file__).resolve().parents[3] / "data" / "demo" / "registration.json"
        load_registration(store, Path(os.getenv("DEMO_REGISTRATION_FILE", str(default_path))))
    vehicles = MockVehicleService(store)
    maintenance = MockMaintenanceService(store, vehicles)
    cost = MockCostService(store, vehicles, maintenance)
    messages = MockMessageService(store, vehicles)
    booking = MockBookingService(store, vehicles, cost, messages)
    return DemoServices(store, vehicles, maintenance, cost, messages, booking)


def services(request: Request) -> DemoServices:
    return request.app.state.services


def verify_token(token: str) -> dict:
    import firebase_admin
    from firebase_admin import auth

    # Reuse credentials already configured for the main backend. Lazy so the demo
    # can boot and report auth configuration errors without connecting to SQL.
    try:
        if not firebase_admin._apps:
            project = os.getenv("VITE_FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
            if os.getenv("FIREBASE_AUTH_EMULATOR_HOST") and project:
                firebase_admin.initialize_app(options={"projectId": project})
            else:
                from src.infrastructure.firebase.oauth import setup  # noqa: F401
        claims = auth.verify_id_token(token, clock_skew_seconds=10)
        return claims
    except Exception:
        # Firebase ID-token verification only needs project id + public signing
        # certificates; a service-account private key is not required here.
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2.id_token import verify_firebase_token

        project = os.getenv("VITE_FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project:
            raise DemoError("AUTH_NOT_CONFIGURED", "Cần cấu hình Firebase project/credential.", 503) from None
        try:
            claims = verify_firebase_token(token, GoogleRequest(), audience=project)
            if claims.get("iss") != f"https://securetoken.google.com/{project}":
                raise ValueError("Invalid issuer")
            claims["uid"] = claims["sub"]
            return claims
        except Exception:
            raise DemoError("UNAUTHORIZED", "Token Firebase không hợp lệ hoặc đã hết hạn.", 401) from None


async def verified_claims(request: Request, authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise DemoError("UNAUTHORIZED", "Vui lòng đăng nhập Firebase.", 401)
    claims = await run_in_threadpool(request.app.state.token_verifier, authorization[7:])
    if not claims.get("uid"):
        raise DemoError("UNAUTHORIZED", "Token không có định danh.", 401)
    return claims


async def current_user(request: Request, authorization: str | None = Header(default=None)) -> dict:
    claims = await verified_claims(request, authorization)
    return ensure_user(request.app.state.services.store, claims)
