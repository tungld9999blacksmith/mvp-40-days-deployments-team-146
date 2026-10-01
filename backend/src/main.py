import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .infrastructure.fastapi.middlewares import (
    REQUEST_ID_HEADER,
    AuditLogMiddleware,
    CorrelationIdMiddleware,
)
from .infrastructure.logging import configure_logging
from .infrastructure.redis import get_redis_toolkit
from .modules.auth.errors import AuthError
from .modules.auth.errors import status_for as auth_status_for
from .modules.auth.route import oauth_router as auth_oauth_router
from .modules.booking import BookingError
from .modules.booking import status_for as booking_status_for
from .modules.booking.route import router as booking_router
from .modules.conversation import ConversationError
from .modules.conversation import status_for as conversation_status_for
from .modules.conversation.route import router as conversation_router
from .modules.conversation.route import workshop_router as conversation_workshop_router
from .modules.conversation.ws import ws_router as conversation_ws_router
from .modules.cost_estimate import CostEstimateError
from .modules.cost_estimate import status_for as cost_estimate_status_for
from .modules.cost_estimate.route import router as cost_estimate_router
from .modules.examples.route import vehicle_router
from .modules.follow_up import FollowUpError
from .modules.follow_up import status_for as follow_up_status_for
from .modules.follow_up.route import router as follow_up_router
from .modules.follow_up.route import workshop_router as follow_up_workshop_router
from .modules.health.route import router as health_router
from .modules.oauth.route import router as oauth_router
from .modules.notification.errors import NotificationError
from .modules.notification.errors import status_for as notification_status_for
from .modules.notification.route import router as notification_router
from .modules.oem_integration.errors import OemWebhookError
from .modules.oem_integration.errors import status_for as oem_webhook_status_for
from .modules.oem_integration.route import router as oem_integration_router
from .modules.quote import QuoteError
from .modules.quote import status_for as quote_status_for
from .modules.quote.route import router as quote_router
from .modules.quote.route import workshop_router as quote_workshop_router
from .modules.service_progress import ProgressError
from .modules.service_progress import status_for as progress_status_for
from .modules.user_vehicle.errors import UserVehicleError
from .modules.user_vehicle.errors import status_for as user_vehicle_status_for
from .modules.user_vehicle.route import router as user_vehicle_router
from .modules.vehicle_owner_onboarding.errors import (
    OnboardingError,
    VerificationAttemptsExceededError,
    status_for,
)
from .modules.vehicle_owner_onboarding.route import (
    oauth_router as onboarding_oauth_router,
)
from .modules.vehicle_owner_onboarding.route import (
    onboarding_router,
)
from .modules.workshop_board import BoardError
from .modules.workshop_board import status_for as board_status_for
from .modules.workshop_board.route import router as workshop_board_router
from .modules.workshop_owner_auth.errors import WorkshopAuthError
from .modules.workshop_owner_auth.errors import status_for as workshop_auth_status_for
from .modules.workshop_owner_auth.route import router as workshop_auth_router
from .modules.workshop_owner_onboarding.errors import WorkshopOnboardingError
from .modules.workshop_owner_onboarding.errors import (
    status_for as workshop_status_for,
)
from .modules.workshop_owner_onboarding.route import (
    router as workshop_onboarding_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    try:
        # Firebase Admin must be initialized before any auth.verify_id_token call.
        import src.infrastructure.firebase.oauth.setup  # noqa: F401
    except Exception as exc:  # noqa: BLE001 — keep the API up without credentials (tests, CI)
        logging.getLogger(__name__).warning("Firebase Admin not initialized: %s", exc)
    redis_toolkit = get_redis_toolkit()
    await redis_toolkit.start()
    yield
    print("Shutting down...")
    await redis_toolkit.close()


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
# Route application (logging.getLogger(__name__)), uvicorn and structlog loggers
# through one structlog pipeline; request context comes from structlog.contextvars.
configure_logging(
    level=settings.log_level,
    json_logs=settings.log_json,
    redact_pii=settings.log_redact_pii,
    file_formats=settings.log_file_formats,
    log_dir=settings.log_dir,
    max_bytes=settings.log_file_max_bytes,
    backup_count=settings.log_file_backup_count,
)
# httpx (used by the Qdrant client) logs every request at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)
origins = [os.getenv("FRONTEND_URL", "")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)
# add_middleware wraps outermost last: CorrelationId -> AuditLog -> CORS -> app.
app.add_middleware(AuditLogMiddleware)
app.add_middleware(CorrelationIdMiddleware)

app.include_router(vehicle_router, prefix="/api/v1")
app.include_router(oauth_router, prefix="/api/v1/oauth", tags=["oauth"])
app.include_router(onboarding_oauth_router, prefix="/api/v1")
app.include_router(onboarding_router, prefix="/api/v1")
app.include_router(auth_oauth_router, prefix="/api/v1")
app.include_router(workshop_onboarding_router, prefix="/api/v1")
app.include_router(workshop_auth_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
app.include_router(user_vehicle_router, prefix="/api/v1")
app.include_router(cost_estimate_router, prefix="/api/v1")
app.include_router(booking_router, prefix="/api/v1")
app.include_router(oem_integration_router, prefix="/api/v1")
app.include_router(notification_router, prefix="/api/v1")
app.include_router(conversation_router, prefix="/api/v1")
app.include_router(conversation_workshop_router, prefix="/api/v1")
app.include_router(conversation_ws_router, prefix="/api/v1")
app.include_router(workshop_board_router, prefix="/api/v1")
app.include_router(quote_router, prefix="/api/v1")
app.include_router(quote_workshop_router, prefix="/api/v1")
app.include_router(follow_up_router, prefix="/api/v1")
app.include_router(follow_up_workshop_router, prefix="/api/v1")


def _error_body(code: str, message: str, trace_id: str | None, details=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "traceId": trace_id,
        }
    }


@app.exception_handler(OnboardingError)
async def onboarding_error_handler(request: Request, exc: OnboardingError) -> JSONResponse:
    """Translate domain errors into the shared error envelope."""
    trace_id = request.headers.get("X-Request-ID")
    details = None
    field = getattr(exc, "field", None)
    if field:
        details = {"field": field}
    headers = {}
    if isinstance(exc, VerificationAttemptsExceededError):
        headers["Retry-After"] = str(exc.retry_after_seconds)
        details = {"retryAfterSeconds": exc.retry_after_seconds}
    return JSONResponse(
        status_code=status_for(exc.code),
        content=_error_body(exc.code, exc.message, trace_id, details),
        headers=headers,
    )


@app.exception_handler(WorkshopOnboardingError)
async def workshop_onboarding_error_handler(
    request: Request, exc: WorkshopOnboardingError
) -> JSONResponse:
    """Workshop-owner onboarding errors (FEAT-AUTH-003) in the shared envelope."""
    headers = {}
    retry_after = getattr(exc, "retry_after_seconds", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=workshop_status_for(exc.code),
        content=_error_body(
            exc.code, exc.message, request.headers.get("X-Request-ID"), exc.details()
        ),
        headers=headers,
    )


@app.exception_handler(WorkshopAuthError)
async def workshop_auth_error_handler(request: Request, exc: WorkshopAuthError) -> JSONResponse:
    """Workshop-owner logout / session-check errors (FEAT-AUTH-004)."""
    return JSONResponse(
        status_code=workshop_auth_status_for(exc.code),
        content=_error_body(exc.code, exc.message, request.headers.get("X-Request-ID")),
    )


@app.exception_handler(UserVehicleError)
async def user_vehicle_error_handler(request: Request, exc: UserVehicleError) -> JSONResponse:
    """Vehicle profile / due-status errors (FEAT-VEH-001)."""
    return JSONResponse(
        status_code=user_vehicle_status_for(exc.code),
        content=_error_body(exc.code, exc.message, request.headers.get("X-Request-ID")),
    )


@app.exception_handler(BookingError)
async def booking_error_handler(request: Request, exc: BookingError) -> JSONResponse:
    """Booking-by-capacity errors (FEAT-BOOK-001). SLOT_FULL carries alternatives."""
    details = exc.details
    alternatives = getattr(exc, "alternatives", None)
    if alternatives:
        details = {**(details or {}), "alternatives": jsonable_encoder(alternatives)}
    return JSONResponse(
        status_code=booking_status_for(exc.code),
        content=_error_body(exc.code, exc.message, request.headers.get("X-Request-ID"), details),
    )


@app.exception_handler(CostEstimateError)
async def cost_estimate_error_handler(request: Request, exc: CostEstimateError) -> JSONResponse:
    """Cost-estimate errors (FEAT-COST-001); milestone errors carry validMilestones."""
    return JSONResponse(
        status_code=cost_estimate_status_for(exc.code),
        content=_error_body(
            exc.code, exc.message, request.headers.get("X-Request-ID"), exc.details
        ),
    )


def _domain_error_response(request: Request, exc, status_for_code) -> JSONResponse:
    """Shared envelope for module errors that carry ``code``, ``message`` and ``details``."""
    return JSONResponse(
        status_code=status_for_code(exc.code),
        content=_error_body(
            exc.code, exc.message, request.headers.get("X-Request-ID"), getattr(exc, "details", None)
        ),
    )


@app.exception_handler(BoardError)
async def board_error_handler(request: Request, exc: BoardError) -> JSONResponse:
    """Workshop Board errors (us-037)."""
    return _domain_error_response(request, exc, board_status_for)


@app.exception_handler(QuoteError)
async def quote_error_handler(request: Request, exc: QuoteError) -> JSONResponse:
    """Quote errors (us-049)."""
    return _domain_error_response(request, exc, quote_status_for)


@app.exception_handler(FollowUpError)
async def follow_up_error_handler(request: Request, exc: FollowUpError) -> JSONResponse:
    """Follow-up & support ticket errors (us-041)."""
    return _domain_error_response(request, exc, follow_up_status_for)


@app.exception_handler(ProgressError)
async def progress_error_handler(request: Request, exc: ProgressError) -> JSONResponse:
    """Service progress errors (us-057)."""
    return _domain_error_response(request, exc, progress_status_for)


@app.exception_handler(ConversationError)
async def conversation_error_handler(request: Request, exc: ConversationError) -> JSONResponse:
    """Chat / conversation errors (US-025) in the shared envelope."""
    headers = {}
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        status_code=conversation_status_for(exc.code),
        content=_error_body(exc.code, exc.message, request.headers.get("X-Request-ID")),
        headers=headers,
    )


@app.exception_handler(NotificationError)
async def notification_error_handler(request: Request, exc: NotificationError) -> JSONResponse:
    """Notification settings errors (FEAT-NOTI-001)."""
    return JSONResponse(
        status_code=notification_status_for(exc.code),
        content=_error_body(exc.code, exc.message, request.headers.get("X-Request-ID")),
    )


@app.exception_handler(OemWebhookError)
async def oem_webhook_error_handler(request: Request, exc: OemWebhookError) -> JSONResponse:
    """Manufacturer webhook errors (FEAT-VEH-001 API-VEH-004)."""
    return JSONResponse(
        status_code=oem_webhook_status_for(exc.code),
        content=_error_body(exc.code, exc.message, request.headers.get("X-Request-ID")),
    )


@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    """Translate auth (logout) domain errors into the shared error envelope."""
    trace_id = request.headers.get("X-Request-ID")
    return JSONResponse(
        status_code=auth_status_for(exc.code),
        content=_error_body(exc.code, exc.message, trace_id),
    )


_ONBOARDING_PREFIXES = (
    "/api/v1/onboarding",
    "/api/v1/oauth/sign-in",
    "/api/v1/workshop-owner",
    "/api/v1/user-vehicles",
    "/api/v1/integrations/oem",
    "/api/v1/bookings",
    "/api/v1/workshops",
    "/api/v1/quotes",
    "/api/v1/follow-ups",
    "/api/v1/support-tickets",
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return onboarding request-validation failures in the shared envelope (400).

    Other routes keep FastAPI's default 422 behavior so their existing
    contracts are unaffected.
    """
    if not request.url.path.startswith(_ONBOARDING_PREFIXES):
        return JSONResponse(
            status_code=422, content={"detail": jsonable_encoder(exc.errors())}
        )
    trace_id = request.headers.get("X-Request-ID")
    first = exc.errors()[0] if exc.errors() else {}
    loc = first.get("loc", [])
    field = ".".join(str(p) for p in loc if p not in ("body", "query", "path"))
    return JSONResponse(
        status_code=400,
        content=_error_body(
            "INVALID_REQUEST",
            first.get("msg", "Invalid request."),
            trace_id,
            {"field": field} if field else None,
        ),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
