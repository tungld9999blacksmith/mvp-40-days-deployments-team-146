"""Tests for M2M authentication between EV Care and the manufacturer system.

Specification: ``docs/specs/mock-system/m2m_authentication_spec.md`` (SPEC-SEC-OEM-M2M-001 v2.0).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import httpx
import pytest
from ev_contracts import (
    BODY_HASH_CLAIM,
    CLIENT_ASSERTION_TYPE,
    M2MAudienceMismatchError,
    M2MIssuerMismatchError,
    M2MSubjectMismatchError,
    M2MTokenExpiredError,
    M2MTokenInvalidError,
    M2MTokenMissingError,
    M2MTokenTypeError,
    WebhookEventType,
    body_sha256,
    clean_pem,
    create_access_token,
    create_client_assertion,
    create_m2m_token,
    detect_algorithm,
    generate_key_pair,
    public_key_from_private,
    verify_access_token,
    verify_client_assertion,
    verify_m2m_token,
)
from fakeredis import FakeAsyncRedis, FakeServer
from fastapi.testclient import TestClient
from mock_ev_system import webhooks as mock_webhooks
from mock_ev_system.db import init_db
from mock_ev_system.main import app as mock_app

from src.infrastructure.oem.auth import OemAccessTokenProvider, OemAuthError
from src.infrastructure.oem.gateway import HttpOemVehicleGateway, OemHttpClient
from src.modules.oem_integration.errors import WebhookSignatureInvalidError
from src.modules.oem_integration.service import OemWebhookService
from src.modules.vehicle_owner_onboarding.ports import OemTimeoutError
from tests._user_vehicle import MemoryEventStore

BASE_URL = "http://oem.test"
TOKEN_KEY = "test:oem:m2m:access_token"


# ---------------------------------------------------------------------------
# ev_contracts.auth
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("algorithm", ["Ed25519", "RS256"])
def test_self_signed_token_round_trip(algorithm):
    priv_pem, pub_pem = generate_key_pair(algorithm)
    token = create_m2m_token(priv_pem, issuer="mock-ev-system", audience="ev-care-backend")
    claims = verify_m2m_token(token, pub_pem, expected_issuer="mock-ev-system", expected_audience="ev-care-backend")
    assert claims["iss"] == "mock-ev-system"
    assert claims["aud"] == "ev-care-backend"
    assert claims["jti"]


def test_detect_algorithm_uses_key_type():
    rsa_priv, rsa_pub = generate_key_pair("RS256")
    ed_priv, ed_pub = generate_key_pair("Ed25519")
    assert detect_algorithm(rsa_priv) == detect_algorithm(rsa_pub) == "RS256"
    assert detect_algorithm(ed_priv) == detect_algorithm(ed_pub) == "EdDSA"


def test_public_key_from_private_matches_pair():
    priv_pem, pub_pem = generate_key_pair("Ed25519")
    assert public_key_from_private(priv_pem).strip() == pub_pem.strip()


def test_clean_pem_unescapes_literal_newlines():
    escaped = "-----BEGIN PUBLIC KEY-----\\nMEYwDQYJKoZIhvcNAQEBBQAD\\n-----END PUBLIC KEY-----"
    cleaned = clean_pem(escaped)
    assert "\\n" not in cleaned
    assert "\n" in cleaned


def test_expired_token_rejected():
    priv_pem, pub_pem = generate_key_pair("Ed25519")
    token = create_m2m_token(
        priv_pem,
        issuer="ev-care-backend",
        audience="mock-ev-system",
        expires_in_seconds=60,
        now=datetime.now(UTC) - timedelta(minutes=10),
    )
    with pytest.raises(M2MTokenExpiredError):
        verify_m2m_token(token, pub_pem, expected_issuer="ev-care-backend", expected_audience="mock-ev-system")


def test_audience_and_issuer_mismatch():
    priv_pem, pub_pem = generate_key_pair("Ed25519")
    with pytest.raises(M2MAudienceMismatchError):
        verify_m2m_token(
            create_m2m_token(priv_pem, issuer="ev-care-backend", audience="wrong"),
            pub_pem,
            expected_issuer="ev-care-backend",
            expected_audience="mock-ev-system",
        )
    with pytest.raises(M2MIssuerMismatchError):
        verify_m2m_token(
            create_m2m_token(priv_pem, issuer="wrong", audience="mock-ev-system"),
            pub_pem,
            expected_issuer="ev-care-backend",
            expected_audience="mock-ev-system",
        )


def test_invalid_signature_and_missing_token():
    priv_pem, _ = generate_key_pair("Ed25519")
    _, other_pub = generate_key_pair("Ed25519")
    token = create_m2m_token(priv_pem, issuer="ev-care-backend", audience="mock-ev-system")
    with pytest.raises(M2MTokenInvalidError):
        verify_m2m_token(token, other_pub, expected_issuer="ev-care-backend", expected_audience="mock-ev-system")
    with pytest.raises(M2MTokenMissingError):
        verify_m2m_token("", other_pub, expected_issuer="ev-care-backend", expected_audience="mock-ev-system")


def test_client_assertion_and_access_token_round_trip():
    evcare_priv, evcare_pub = generate_key_pair("Ed25519")
    oem_priv, oem_pub = generate_key_pair("Ed25519")
    claims = verify_client_assertion(create_client_assertion(evcare_priv), evcare_pub)
    assert claims["iss"] == claims["sub"] == "ev-care-backend"
    assert claims["aud"] == "mock-ev-system"
    assert claims["exp"] - claims["iat"] == 60

    access = verify_access_token(create_access_token(oem_priv), oem_pub)
    assert access["iss"] == access["aud"] == "mock-ev-system"
    assert access["sub"] == access["client_id"] == "ev-care-backend"


def test_token_kinds_are_not_interchangeable():
    priv_pem, pub_pem = generate_key_pair("Ed25519")
    access = create_access_token(priv_pem)
    assertion = create_client_assertion(priv_pem)
    # An access token is neither an assertion nor a webhook token.
    with pytest.raises(M2MTokenTypeError):
        verify_client_assertion(access, pub_pem)
    with pytest.raises(M2MTokenTypeError):
        verify_m2m_token(access, pub_pem, expected_issuer="mock-ev-system", expected_audience="mock-ev-system")
    # A self-signed token is not an access token.
    with pytest.raises(M2MTokenTypeError):
        verify_access_token(assertion, pub_pem)


def test_access_token_for_another_subject_rejected():
    priv_pem, pub_pem = generate_key_pair("Ed25519")
    with pytest.raises(M2MSubjectMismatchError):
        verify_access_token(create_access_token(priv_pem, subject="someone-else"), pub_pem)


# ---------------------------------------------------------------------------
# mock-ev-system: token endpoint + protected business routes
# ---------------------------------------------------------------------------
@pytest.fixture
def keys():
    evcare_priv, evcare_pub = generate_key_pair("Ed25519")
    oem_priv, oem_pub = generate_key_pair("Ed25519")
    return {"evcare_priv": evcare_priv, "evcare_pub": evcare_pub, "oem_priv": oem_priv, "oem_pub": oem_pub}


@pytest.fixture
def mock_with_keys(monkeypatch, keys):
    init_db()
    monkeypatch.setenv("EVCARE_PUBLIC_KEY", keys["evcare_pub"])
    monkeypatch.setenv("MOCK_PRIVATE_KEY", keys["oem_priv"])
    monkeypatch.setenv("MOCK_ACCESS_TOKEN_TTL_SECONDS", "900")
    monkeypatch.delenv("MOCK_AUTH_REQUIRED", raising=False)
    return TestClient(mock_app)


def _token_form(assertion: str, **overrides) -> dict[str, str]:
    return {
        "grant_type": "client_credentials",
        "client_assertion_type": CLIENT_ASSERTION_TYPE,
        "client_assertion": assertion,
        **overrides,
    }


def test_token_endpoint_issues_verifiable_access_token(mock_with_keys, keys):
    resp = mock_with_keys.post("/oauth/token", data=_token_form(create_client_assertion(keys["evcare_priv"])))
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    claims = verify_access_token(body["access_token"], keys["oem_pub"])
    assert claims["exp"] - claims["iat"] == 900


def test_token_endpoint_rejects_replayed_assertion(mock_with_keys, keys):
    form = _token_form(create_client_assertion(keys["evcare_priv"]))
    assert mock_with_keys.post("/oauth/token", data=form).status_code == 200
    replay = mock_with_keys.post("/oauth/token", data=form)
    assert replay.status_code == 401
    assert replay.json()["error"] == "invalid_client"


@pytest.mark.parametrize(
    "overrides,status,error",
    [
        ({"grant_type": "password"}, 400, "unsupported_grant_type"),
        ({"client_assertion_type": "other"}, 400, "invalid_request"),
        ({"client_id": "intruder"}, 401, "invalid_client"),
    ],
)
def test_token_endpoint_rejects_bad_requests(mock_with_keys, keys, overrides, status, error):
    resp = mock_with_keys.post(
        "/oauth/token", data=_token_form(create_client_assertion(keys["evcare_priv"]), **overrides)
    )
    assert resp.status_code == status
    assert resp.json()["error"] == error


def test_token_endpoint_rejects_assertion_signed_by_another_key(mock_with_keys):
    intruder_priv, _ = generate_key_pair("Ed25519")
    resp = mock_with_keys.post("/oauth/token", data=_token_form(create_client_assertion(intruder_priv)))
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_client"


def test_token_endpoint_unavailable_without_keys(monkeypatch, keys):
    monkeypatch.delenv("EVCARE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("MOCK_PRIVATE_KEY", raising=False)
    resp = TestClient(mock_app).post("/oauth/token", data=_token_form(create_client_assertion(keys["evcare_priv"])))
    assert resp.status_code == 503


def test_business_route_accepts_only_access_tokens(mock_with_keys, keys):
    missing = mock_with_keys.get("/models")
    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "M2M_TOKEN_MISSING"
    assert missing.headers["www-authenticate"] == "Bearer"

    # v1.0 style: a self-signed EV Care token sent straight to the API.
    assertion = create_client_assertion(keys["evcare_priv"])
    wrong_kind = mock_with_keys.get("/models", headers={"Authorization": f"Bearer {assertion}"})
    assert wrong_kind.status_code == 401
    assert wrong_kind.json()["detail"]["code"] == "M2M_TOKEN_TYPE_INVALID"

    expired = create_access_token(keys["oem_priv"], now=datetime.now(UTC) - timedelta(hours=1))
    resp_expired = mock_with_keys.get("/models", headers={"Authorization": f"Bearer {expired}"})
    assert resp_expired.json()["detail"]["code"] == "M2M_TOKEN_EXPIRED"

    forged = create_access_token(generate_key_pair("Ed25519")[0])
    resp_forged = mock_with_keys.get("/models", headers={"Authorization": f"Bearer {forged}"})
    assert resp_forged.json()["detail"]["code"] == "M2M_SIGNATURE_INVALID"

    access = mock_with_keys.post("/oauth/token", data=_token_form(assertion)).json()["access_token"]
    ok = mock_with_keys.get("/models", headers={"Authorization": f"Bearer {access}"})
    assert ok.status_code == 200
    assert isinstance(ok.json(), list)


def test_business_route_bypassed_without_key(monkeypatch):
    init_db()
    monkeypatch.delenv("EVCARE_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("MOCK_AUTH_REQUIRED", "false")
    assert TestClient(mock_app).get("/models").status_code == 200


# ---------------------------------------------------------------------------
# EV Care: OemAccessTokenProvider + OemHttpClient against the mock app
# ---------------------------------------------------------------------------
class CountingTransport(httpx.AsyncBaseTransport):
    """ASGI transport into the mock app that counts calls per path."""

    def __init__(self) -> None:
        self._inner = httpx.ASGITransport(app=mock_app)
        self.calls: dict[str, int] = {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls[request.url.path] = self.calls.get(request.url.path, 0) + 1
        return await self._inner.handle_async_request(request)


@pytest.fixture
def redis_server():
    return FakeServer()


@pytest.fixture
def transport():
    return CountingTransport()


def _provider(keys, redis_server, transport, **overrides) -> OemAccessTokenProvider:
    options = {
        "private_key": keys["evcare_priv"],
        "oem_public_key": keys["oem_pub"],
        "redis_factory": lambda: FakeAsyncRedis(server=redis_server),
        "key_prefix": "test",
        "refresh_margin_seconds": 60,
        "transport": transport,
        **overrides,
    }
    return OemAccessTokenProvider(BASE_URL, **options)


def _client(provider, transport) -> OemHttpClient:
    return OemHttpClient(BASE_URL, token_provider=provider, transport=transport)


@pytest.mark.asyncio
async def test_token_is_fetched_once_and_cached_below_its_lifetime(mock_with_keys, keys, redis_server, transport):
    client = _client(_provider(keys, redis_server, transport), transport)

    assert (await client.request("GET", "/models")).status_code == 200
    assert (await client.request("GET", "/models")).status_code == 200

    assert transport.calls["/oauth/token"] == 1
    assert transport.calls["/models"] == 2
    redis = FakeAsyncRedis(server=redis_server)
    ttl = await redis.ttl(TOKEN_KEY)
    # Cache TTL = expires_in (900) - margin (60): the cache never outlives the token.
    assert 830 <= ttl <= 840
    verify_access_token((await redis.get(TOKEN_KEY)).decode(), keys["oem_pub"])


@pytest.mark.asyncio
async def test_rejected_cached_token_is_refreshed_and_retried_once(mock_with_keys, keys, redis_server, transport):
    stale = create_access_token(keys["oem_priv"], now=datetime.now(UTC) - timedelta(hours=1))
    await FakeAsyncRedis(server=redis_server).set(TOKEN_KEY, stale, ex=600)
    client = _client(_provider(keys, redis_server, transport), transport)

    assert (await client.request("GET", "/models")).status_code == 200

    assert transport.calls["/models"] == 2
    assert transport.calls["/oauth/token"] == 1
    assert (await FakeAsyncRedis(server=redis_server).get(TOKEN_KEY)).decode() != stale


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_token_fetch(mock_with_keys, keys, redis_server, transport):
    provider = _provider(keys, redis_server, transport)
    tokens = await asyncio.gather(*(provider.get_token() for _ in range(5)))
    assert len(set(tokens)) == 1
    assert transport.calls["/oauth/token"] == 1


@pytest.mark.asyncio
async def test_access_token_signed_by_unexpected_key_is_refused(mock_with_keys, keys, redis_server, transport):
    _, other_pub = generate_key_pair("Ed25519")
    provider = _provider(keys, redis_server, transport, oem_public_key=other_pub)
    with pytest.raises(OemAuthError):
        await provider.get_token()
    assert await FakeAsyncRedis(server=redis_server).get(TOKEN_KEY) is None

    # The gateway reports it like an outage so the onboarding stays pending.
    gateway = HttpOemVehicleGateway(_client(provider, transport))
    with pytest.raises(OemTimeoutError):
        await gateway.list_models()


@pytest.mark.asyncio
async def test_missing_oem_public_key_is_an_auth_error(mock_with_keys, keys, redis_server, transport):
    with pytest.raises(OemAuthError):
        await _provider(keys, redis_server, transport, oem_public_key="").get_token()


@pytest.mark.asyncio
async def test_token_still_issued_when_redis_is_down(mock_with_keys, keys, redis_server, transport):
    redis_server.connected = False
    token = await _provider(keys, redis_server, transport).get_token()
    verify_access_token(token, keys["oem_pub"])


@pytest.mark.asyncio
async def test_no_private_key_sends_no_authorization(monkeypatch):
    init_db()
    monkeypatch.delenv("EVCARE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("MOCK_AUTH_REQUIRED", raising=False)
    settings = MagicMock(evcare_private_key="")
    assert OemAccessTokenProvider.from_settings(settings) is None

    seen: list[httpx.Request] = []

    async def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    client = OemHttpClient(BASE_URL, transport=httpx.MockTransport(record))
    await client.request("GET", "/models")
    assert "authorization" not in seen[0].headers


# ---------------------------------------------------------------------------
# EV Care: OemWebhookService verifies body-bound webhook tokens
# ---------------------------------------------------------------------------
def _webhook_service(oem_pub: str, auth_mode: str) -> OemWebhookService:
    service = OemWebhookService(
        MagicMock(),
        MagicMock(),
        MemoryEventStore(),
        secret="test-secret",
        oem_public_key=oem_pub,
        auth_mode=auth_mode,
    )
    service._find_vehicle_id = MagicMock(return_value=None)
    return service


@pytest.mark.asyncio
async def test_webhook_jwt_from_mock_is_accepted(keys):
    event_id, headers, body = mock_webhooks.build_request(
        WebhookEventType.VEHICLE_USAGE_UPDATED, "VEH-001", "", private_key=keys["oem_priv"]
    )
    result = await _webhook_service(keys["oem_pub"], "jwt").handle(
        event_id=event_id, timestamp=None, signature=None, raw_body=body, auth_header=headers["Authorization"]
    )
    assert result.accepted is True
    assert result.ignored is True


@pytest.mark.asyncio
async def test_webhook_jwt_replayed_with_another_body_is_rejected(keys):
    _, headers, _ = mock_webhooks.build_request(
        WebhookEventType.VEHICLE_USAGE_UPDATED, "VEH-001", "", private_key=keys["oem_priv"]
    )
    tampered = json.dumps(
        {
            "eventType": WebhookEventType.VEHICLE_USAGE_UPDATED.value,
            "vehicleId": "VEH-999",
            "occurredAt": datetime.now(UTC).isoformat(),
        }
    ).encode()
    with pytest.raises(WebhookSignatureInvalidError):
        await _webhook_service(keys["oem_pub"], "jwt").handle(
            event_id="evt_tampered",
            timestamp=None,
            signature=None,
            raw_body=tampered,
            auth_header=headers["Authorization"],
        )


@pytest.mark.asyncio
async def test_webhook_jwt_without_body_hash_is_rejected(keys):
    body = b'{"eventType":"vehicle.usage.updated","vehicleId":"VEH-001","occurredAt":"2026-10-12T00:00:00Z"}'
    token = create_m2m_token(keys["oem_priv"], issuer="mock-ev-system", audience="ev-care-backend")
    with pytest.raises(WebhookSignatureInvalidError):
        await _webhook_service(keys["oem_pub"], "jwt").handle(
            event_id="evt_no_hash", timestamp=None, signature=None, raw_body=body, auth_header=f"Bearer {token}"
        )
    # Sanity: the same token with the matching hash passes.
    bound = create_m2m_token(
        keys["oem_priv"],
        issuer="mock-ev-system",
        audience="ev-care-backend",
        extra_claims={BODY_HASH_CLAIM: body_sha256(body)},
    )
    result = await _webhook_service(keys["oem_pub"], "jwt").handle(
        event_id="evt_hash", timestamp=None, signature=None, raw_body=body, auth_header=f"Bearer {bound}"
    )
    assert result.accepted is True


@pytest.mark.asyncio
async def test_webhook_hmac_mode_ignores_jwt(keys):
    event_id, headers, body = mock_webhooks.build_request(
        WebhookEventType.VEHICLE_USAGE_UPDATED, "VEH-001", "", private_key=keys["oem_priv"]
    )
    with pytest.raises(WebhookSignatureInvalidError):
        await _webhook_service(keys["oem_pub"], "hmac").handle(
            event_id=event_id,
            timestamp=headers["X-OEM-Timestamp"],
            signature=None,
            raw_body=body,
            auth_header=headers["Authorization"],
        )
