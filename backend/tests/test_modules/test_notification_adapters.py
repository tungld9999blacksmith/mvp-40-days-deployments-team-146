"""Email (SMTP) and SMS (eSMS) channel adapters (us-021 BR-506)."""

from __future__ import annotations

import json

import httpx
import pytest

from src.common.core.notification import DeliveryStatus
from src.config import Settings
from src.modules.notification.adapters import EsmsConfig, EsmsSmsAdapter
from src.modules.notification.adapters.sms import strip_diacritics
from src.modules.notification.channels import DeliveryResult, NotificationMessage
from src.modules.notification.dependency import configured_adapters
from src.modules.notification.email_service import MaintenanceEmailAdapter
from tests._user_vehicle import add_owner, make_session

MESSAGE = NotificationMessage(
    subject="Nhắc lịch hẹn",
    body="📅 Nhắc lịch hẹn: 09:00 Thứ Hai, 12/10 tại Xưởng Đà Nẵng\nMã lịch hẹn: BK-123",
    link="https://app.example.com/bookings/1",
)


@pytest.fixture
def session():
    yield from make_session()


@pytest.fixture
def owner(session):
    user = add_owner(session)
    user.email_verified = True
    user.phone = "+84901000001"
    session.add(user)
    session.commit()
    return user


# ── SMS (eSMS) ──────────────────────────────────────────────────────────────

CONFIG = EsmsConfig(api_key="key", secret_key="secret", brandname="EVCARE", url="https://esms.test/send")


def _sms(session, handler, config: EsmsConfig = CONFIG) -> EsmsSmsAdapter:
    return EsmsSmsAdapter(session, config, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_sms_posts_the_esms_payload(session, owner):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"CodeResult": "100", "SMSID": "abc"})

    result = await _sms(session, handler).send(owner.user_id, MESSAGE)

    assert result == DeliveryResult.sent()
    (request,) = requests
    assert str(request.url) == "https://esms.test/send"
    payload = json.loads(request.content)
    assert payload["Phone"] == "0901000001"
    assert payload["Brandname"] == "EVCARE" and payload["SmsType"] == "2"
    assert payload["IsUnicode"] == "0" and payload["Sandbox"] == "0"
    # No subject, no emoji, no diacritics; the link is appended.
    assert payload["Content"] == (
        "Nhac lich hen: 09:00 Thu Hai, 12/10 tai Xuong Da Nang\nMa lich hen: BK-123\nhttps://app.example.com/bookings/1"
    )


@pytest.mark.asyncio
async def test_sms_unicode_keeps_vietnamese(session, owner):
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"CodeResult": "100"})

    config = EsmsConfig(api_key="k", secret_key="s", brandname="B", unicode=True, sandbox=True, url="https://esms.test")
    await _sms(session, handler, config).send(owner.user_id, MESSAGE)

    assert sent[0]["IsUnicode"] == "1" and sent[0]["Sandbox"] == "1"
    assert "Xưởng Đà Nẵng" in sent[0]["Content"]


@pytest.mark.asyncio
async def test_sms_without_phone_has_no_recipient(session, owner):
    owner.phone = None
    session.add(owner)
    session.commit()

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not be called
        raise AssertionError("no request expected")

    result = await _sms(session, handler).send(owner.user_id, MESSAGE)

    assert result.status is DeliveryStatus.NO_RECIPIENT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response, code, retryable",
    [
        (httpx.Response(200, json={"CodeResult": "101"}), "AUTH_FAILED", False),
        (httpx.Response(200, json={"CodeResult": "146"}), "TEMPLATE_NOT_REGISTERED", False),
        (httpx.Response(200, json={"CodeResult": "777"}), "ESMS_777", False),
        (httpx.Response(503, text="down"), "UNAVAILABLE", True),
        (httpx.Response(429, text="slow down"), "RATE_LIMITED", True),
        (httpx.Response(200, text="<html>"), "UNAVAILABLE", True),
    ],
)
async def test_sms_failures_are_mapped(session, owner, response, code, retryable):
    result = await _sms(session, lambda request: response).send(owner.user_id, MESSAGE)

    assert result.status is DeliveryStatus.FAILED
    assert result.error_code == code and result.retryable is retryable


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error, code",
    [(httpx.ReadTimeout("slow"), "TIMEOUT"), (httpx.ConnectError("refused"), "UNAVAILABLE")],
)
async def test_sms_network_errors_are_retryable(session, owner, error, code):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    result = await _sms(session, handler).send(owner.user_id, MESSAGE)

    assert result.error_code == code and result.retryable


def test_strip_diacritics():
    assert strip_diacritics("Đặt lịch bảo dưỡng ✅") == "Dat lich bao duong"


# ── Registration ────────────────────────────────────────────────────────────


def _settings(**values) -> Settings:
    """Init values win over the process env, which may already hold the developer's .env."""
    blank = dict(email_mode="off", esms_api_key="", esms_secret_key="", esms_brandname="")
    return Settings(_env_file=None, **{**blank, **values})


def test_no_channel_without_provider_settings(session):
    assert configured_adapters(session, _settings()) == []


def test_channels_are_registered_once_configured(session):
    adapters = configured_adapters(
        session,
        _settings(
            email_mode="mock",
            esms_api_key="k",
            esms_secret_key="s",
            esms_brandname="EVCARE",
        ),
    )

    assert {type(adapter) for adapter in adapters} == {MaintenanceEmailAdapter, EsmsSmsAdapter}


def test_sms_needs_a_brandname(session):
    adapters = configured_adapters(session, _settings(esms_api_key="k", esms_secret_key="s"))

    assert adapters == []
