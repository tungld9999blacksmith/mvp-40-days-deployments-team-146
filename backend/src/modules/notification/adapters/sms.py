"""SMS channel through eSMS.vn (us-021 BR-506).

API: ``POST SendMultipleMessage_V4_post_json`` — https://developers.esms.vn.
``CodeResult == "100"`` only means eSMS accepted the request, not that the
handset received it. Customer-care (CSKH, ``SmsType=2``) messages must match a
template registered with eSMS for the brandname, otherwise eSMS answers 146.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass

import httpx
from sqlmodel import Session

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.reminder import ReminderChannel

from ..channels import DeliveryResult, NotificationChannelAdapter, NotificationMessage
from ..recipients import phone_number

logger = logging.getLogger(__name__)

ESMS_SEND_URL = "https://rest.esms.vn/MainService.svc/json/SendMultipleMessage_V4_post_json/"
ESMS_OK = "100"
# Documented eSMS result codes; any other code is stored as ESMS_<code>.
ESMS_ERRORS = {
    "99": "REJECTED",
    "101": "AUTH_FAILED",
    "104": "BRANDNAME_INVALID",
    "124": "DUPLICATE_REQUEST",
    "146": "TEMPLATE_NOT_REGISTERED",
}


@dataclass(frozen=True)
class EsmsConfig:
    api_key: str
    secret_key: str
    brandname: str
    sms_type: str = "2"
    unicode: bool = False
    sandbox: bool = False
    url: str = ESMS_SEND_URL
    timeout_seconds: float = 10.0


def to_local_phone(phone: str) -> str:
    """``+84901234567`` -> ``0901234567`` (the format eSMS documents)."""
    return "0" + phone[3:] if phone.startswith("+84") else phone


def strip_diacritics(text: str) -> str:
    """Vietnamese to plain ASCII (``Nhắc lịch hẹn`` -> ``Nhac lich hen``); emoji are dropped."""
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii")
    return "\n".join(line.strip() for line in ascii_text.splitlines()).strip()


def sms_text(message: NotificationMessage, *, unicode: bool) -> str:
    """SMS has no subject: the body, plus the link when the body does not carry it."""
    text = message.body
    if message.link and message.link not in text:
        text += f"\n{message.link}"
    return text if unicode else strip_diacritics(text)


class EsmsSmsAdapter(NotificationChannelAdapter):
    channel = ReminderChannel.SMS

    def __init__(
        self,
        session: Session,
        config: EsmsConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._db = session
        self._config = config
        self._transport = transport

    async def send(self, user_id: int, message: NotificationMessage) -> DeliveryResult:
        phone = phone_number(self._db.get(VehicleUser, user_id))
        if phone is None:
            return DeliveryResult.no_recipient()
        cfg = self._config
        payload = {
            "ApiKey": cfg.api_key,
            "SecretKey": cfg.secret_key,
            "Phone": to_local_phone(phone),
            "Content": sms_text(message, unicode=cfg.unicode),
            "Brandname": cfg.brandname,
            "SmsType": cfg.sms_type,
            "IsUnicode": "1" if cfg.unicode else "0",
            "Sandbox": "1" if cfg.sandbox else "0",
        }
        try:
            async with httpx.AsyncClient(timeout=cfg.timeout_seconds, transport=self._transport) as client:
                response = await client.post(cfg.url, json=payload)
        except httpx.TimeoutException:
            return DeliveryResult.failed("TIMEOUT")
        except httpx.TransportError:
            return DeliveryResult.failed("UNAVAILABLE")

        if response.status_code == 429:
            return DeliveryResult.failed("RATE_LIMITED")
        if response.status_code >= 500:
            return DeliveryResult.failed("UNAVAILABLE")
        try:
            code = str(response.json().get("CodeResult", ""))
        except ValueError:
            return DeliveryResult.failed("UNAVAILABLE")
        if code == ESMS_OK:
            return DeliveryResult.sent()
        # Never log the payload: it holds the secret key and the phone number.
        logger.warning("esms.rejected", extra={"code_result": code})
        return DeliveryResult.failed(ESMS_ERRORS.get(code, f"ESMS_{code or 'UNKNOWN'}"))
