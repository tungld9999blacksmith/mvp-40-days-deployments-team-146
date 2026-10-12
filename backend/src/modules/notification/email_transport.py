"""Resend HTTP transport. Recipient authorization belongs to the calling service."""

import base64
import hashlib
import hmac
import time

import httpx

from .channels import DeliveryResult, NotificationMessage

# The only mail this transport sends, with the idempotency-key prefix of each kind:
# maintenance reminders to owners, and the overdue-reply alert to workshop owners.
EMAIL_KINDS = {"MAINTENANCE_REMINDER": "maintenance", "WORKSHOP_REPLY_OVERDUE": "workshop-reply-overdue"}


def address_hash(address: str) -> str:
    return hashlib.sha256(address.strip().casefold().encode()).hexdigest()


class ResendEmailTransport:
    def __init__(self, api_key: str, *, client_factory=httpx.AsyncClient):
        self.api_key, self.client_factory = api_key, client_factory

    async def send(self, recipient: str, message: NotificationMessage) -> DeliveryResult:
        prefix = EMAIL_KINDS.get(message.kind)
        if prefix is None or not message.delivery_id:
            return DeliveryResult.failed("EMAIL_MAINTENANCE_ONLY")
        try:
            async with self.client_factory(timeout=10) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Idempotency-Key": f"{prefix}/{message.delivery_id}",
                    },
                    json={
                        "from": message.sender,
                        "to": [recipient],
                        "subject": message.subject,
                        "text": message.body,
                        "html": message.html,
                        "tags": [{"name": "delivery_id", "value": message.delivery_id}],
                    },
                )
        except httpx.TimeoutException:
            return DeliveryResult.failed("TIMEOUT")
        except httpx.HTTPError:
            return DeliveryResult.failed("UNAVAILABLE")
        if response.status_code == 429:
            return DeliveryResult.failed("RATE_LIMITED")
        if response.status_code >= 500:
            return DeliveryResult.failed("UNAVAILABLE")
        if response.status_code in (401, 403):
            return DeliveryResult.failed("DELIVERY_FORBIDDEN")
        if response.status_code == 409:
            return DeliveryResult.failed("IDEMPOTENCY_CONFLICT")
        if not response.is_success:
            return DeliveryResult.failed("EMAIL_REJECTED")
        try:
            provider_id = response.json()["id"]
            if not isinstance(provider_id, str) or not provider_id or len(provider_id) > 255:
                raise ValueError("Invalid provider message ID")
        except (ValueError, KeyError, TypeError):
            return DeliveryResult.failed("UNAVAILABLE")
        return DeliveryResult.sent(provider_id)


def verify_webhook(raw: bytes, headers, secret: str, *, now: float | None = None) -> str:
    """Verify Svix HMAC against the raw body, with a five-minute replay window."""
    try:
        event_id = headers["svix-id"]
        timestamp = headers["svix-timestamp"]
        signatures = headers["svix-signature"].split()
        if not event_id or len(event_id) > 255:
            raise ValueError("Invalid event ID")
        if abs((time.time() if now is None else now) - int(timestamp)) > 300:
            raise ValueError("Expired signature")
        key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
        expected = base64.b64encode(
            hmac.new(key, f"{event_id}.{timestamp}.".encode() + raw, hashlib.sha256).digest()
        ).decode()
        if not any(hmac.compare_digest(sig, f"v1,{expected}") for sig in signatures):
            raise ValueError("Invalid signature")
        return event_id
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid webhook signature") from exc
