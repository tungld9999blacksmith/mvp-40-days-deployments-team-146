"""Outgoing webhooks: the mock manufacturer notifies EV Care about new data.

Mirrors how a real manufacturer would push "vehicle data changed" signals
(FEAT-VEH-001, API-VEH-004). Each call is signed with HMAC-SHA256 using the
shared contract in ``ev_contracts``.

Configuration (environment variables):
- ``MOCK_WEBHOOK_URL``: EV Care receiver URL. Unset -> webhooks disabled.
- ``MOCK_WEBHOOK_SECRET``: shared HMAC secret (must equal EV Care's ``OEM_WEBHOOK_SECRET``).
- ``MOCK_WEBHOOK_USAGE_MIN_INTERVAL_SECONDS``: minimum gap between two
  ``vehicle.usage.updated`` events for the same vehicle (default 300). The
  odometer simulator ticks every few seconds, so usage events are throttled.
- ``MOCK_WEBHOOK_TIMEOUT_SECONDS``: HTTP timeout per attempt (default 5).

Delivery uses the standard library (``urllib``) in a worker thread so the mock
needs no extra HTTP client dependency.
"""

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from ev_contracts import (
    WEBHOOK_EVENT_ID_HEADER,
    WEBHOOK_SIGNATURE_HEADER,
    WEBHOOK_TIMESTAMP_HEADER,
    WebhookEventType,
    sign_webhook,
)

logger = logging.getLogger(__name__)

RETRY_BACKOFF_SECONDS = (1.0, 4.0)  # 3 attempts in total


@dataclass(frozen=True)
class WebhookSettings:
    url: str | None
    secret: str
    usage_min_interval_seconds: float
    timeout_seconds: float

    @property
    def enabled(self) -> bool:
        return bool(self.url)


@dataclass(frozen=True)
class DeliveryResult:
    event_id: str
    delivered: bool
    status_code: int | None
    attempts: int
    error: str | None = None


def load_settings() -> WebhookSettings:
    return WebhookSettings(
        url=os.getenv("MOCK_WEBHOOK_URL") or None,
        secret=os.getenv("MOCK_WEBHOOK_SECRET", ""),
        usage_min_interval_seconds=float(os.getenv("MOCK_WEBHOOK_USAGE_MIN_INTERVAL_SECONDS", "300")),
        timeout_seconds=float(os.getenv("MOCK_WEBHOOK_TIMEOUT_SECONDS", "5")),
    )


def build_request(
    event_type: WebhookEventType,
    vehicle_id: str,
    secret: str,
    *,
    now: datetime | None = None,
) -> tuple[str, dict[str, str], bytes]:
    """Build (event_id, headers, raw_body) for one signed webhook call."""
    now = now or datetime.now(UTC)
    event_id = f"evt_{uuid4().hex}"
    body = json.dumps(
        {
            "eventType": event_type.value,
            "vehicleId": vehicle_id,
            "occurredAt": now.isoformat().replace("+00:00", "Z"),
        },
        separators=(",", ":"),
    ).encode()
    timestamp = str(int(now.timestamp()))
    headers = {
        "Content-Type": "application/json",
        WEBHOOK_EVENT_ID_HEADER: event_id,
        WEBHOOK_TIMESTAMP_HEADER: timestamp,
        WEBHOOK_SIGNATURE_HEADER: sign_webhook(secret, timestamp, body),
    }
    return event_id, headers, body


def _post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> int:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


async def send_event(
    event_type: WebhookEventType,
    vehicle_id: str,
    settings: WebhookSettings | None = None,
) -> DeliveryResult | None:
    """Send one webhook with retries. Returns None when webhooks are disabled.

    Retries on network errors and 5xx; a 4xx means the receiver rejected the
    call (bad signature, unknown event), so it is not retried.
    """
    settings = settings or load_settings()
    if not settings.enabled:
        return None

    event_id, headers, body = build_request(event_type, vehicle_id, settings.secret)
    last_error: str | None = None
    status: int | None = None
    max_attempts = len(RETRY_BACKOFF_SECONDS) + 1

    for attempt in range(1, max_attempts + 1):
        try:
            status = await asyncio.to_thread(_post, settings.url, headers, body, settings.timeout_seconds)
            last_error = None
            if status < 500:
                break
            last_error = f"HTTP {status}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        if attempt < max_attempts:
            await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt - 1])

    delivered = status is not None and 200 <= status < 300
    if not delivered:
        logger.warning(
            "Webhook %s %s for %s not delivered: %s",
            event_id,
            event_type.value,
            vehicle_id,
            last_error or f"HTTP {status}",
        )
    return DeliveryResult(
        event_id=event_id,
        delivered=delivered,
        status_code=status,
        attempts=attempt,
        error=last_error,
    )


# ---------------------------------------------------------------------------
# Fire-and-forget helpers used by the simulator and write endpoints
# ---------------------------------------------------------------------------
_background_tasks: set[asyncio.Task] = set()
_last_usage_sent: dict[str, float] = {}


def dispatch(event_type: WebhookEventType, vehicle_id: str) -> None:
    """Schedule a webhook without blocking the caller (no-op when disabled)."""
    settings = load_settings()
    if not settings.enabled:
        return
    task = asyncio.create_task(send_event(event_type, vehicle_id, settings))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def dispatch_usage_updated(vehicle_id: str) -> None:
    """Send ``vehicle.usage.updated`` at most once per configured interval."""
    settings = load_settings()
    if not settings.enabled:
        return
    now = time.monotonic()
    last = _last_usage_sent.get(vehicle_id)
    if last is not None and now - last < settings.usage_min_interval_seconds:
        return
    _last_usage_sent[vehicle_id] = now
    dispatch(WebhookEventType.VEHICLE_USAGE_UPDATED, vehicle_id)


def reset_throttle() -> None:
    """Forget throttle state (used by tests)."""
    _last_usage_sent.clear()
