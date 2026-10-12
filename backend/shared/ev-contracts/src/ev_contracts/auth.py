"""Asymmetric M2M (Machine-to-Machine) authentication utilities.

Specification: ``docs/specs/mock-system/m2m_authentication_spec.md`` (SPEC-SEC-OEM-M2M-001 v2.0).

Three token kinds, all signed with Ed25519 (EdDSA) or RS256:
- Client assertion (``typ=JWT``): EV Care -> OEM token endpoint (RFC 7523 §2.2).
- Access token (``typ=at+jwt``, RFC 9068): issued by the OEM, sent by EV Care on every API call.
- Webhook token (``typ=JWT``): OEM -> EV Care, one per webhook, bound to the body hash.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

M2M_AUTH_HEADER = "Authorization"
M2M_BEARER_PREFIX = "Bearer "

EVCARE_CLIENT_ID = "ev-care-backend"
OEM_ISSUER = "mock-ev-system"
OAUTH_TOKEN_PATH = "/oauth/token"
CLIENT_CREDENTIALS_GRANT = "client_credentials"
CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
SELF_SIGNED_TOKEN_TYPE = "JWT"
ACCESS_TOKEN_TYPE = "at+jwt"
BODY_HASH_CLAIM = "body_sha256"

M2M_CLOCK_SKEW_SECONDS = 60
CLIENT_ASSERTION_TTL_SECONDS = 60
ACCESS_TOKEN_TTL_SECONDS = 900
WEBHOOK_TOKEN_TTL_SECONDS = 180

_ALGORITHMS = ["EdDSA", "RS256"]


class M2MAuthError(Exception):
    """Base exception for M2M authentication failures."""

    code = "M2M_AUTH_FAILED"


class M2MTokenMissingError(M2MAuthError):
    """Raised when an M2M token was expected but missing."""

    code = "M2M_TOKEN_MISSING"


class M2MTokenExpiredError(M2MAuthError):
    """Raised when the M2M token has expired."""

    code = "M2M_TOKEN_EXPIRED"


class M2MTokenInvalidError(M2MAuthError):
    """Raised when the M2M token signature or format is invalid."""

    code = "M2M_SIGNATURE_INVALID"


class M2MTokenTypeError(M2MAuthError):
    """Raised when the token ``typ`` header is not the kind the receiver accepts."""

    code = "M2M_TOKEN_TYPE_INVALID"


class M2MAudienceMismatchError(M2MAuthError):
    """Raised when the audience claim does not match the expected receiver."""

    code = "M2M_AUDIENCE_MISMATCH"


class M2MIssuerMismatchError(M2MAuthError):
    """Raised when the issuer claim does not match the expected sender."""

    code = "M2M_ISSUER_MISMATCH"


class M2MSubjectMismatchError(M2MAuthError):
    """Raised when the subject claim is not the expected client."""

    code = "M2M_SUBJECT_MISMATCH"


def clean_pem(key_pem: str) -> str:
    """Normalize PEM string, converting literal escaped '\\n' to actual newlines."""
    cleaned = key_pem.strip()
    if "\\n" in cleaned and "\n" not in cleaned:
        cleaned = cleaned.replace("\\n", "\n")
    return cleaned.strip()


def body_sha256(raw_body: bytes) -> str:
    """Hex SHA-256 of a request body, carried in the webhook token."""
    return hashlib.sha256(raw_body).hexdigest()


def generate_key_pair(algorithm: Literal["Ed25519", "RS256"] = "Ed25519") -> tuple[str, str]:
    """Generate an asymmetric key pair returning (private_key_pem, public_key_pem)."""
    if algorithm == "Ed25519":
        private_key: Any = ed25519.Ed25519PrivateKey.generate()
    elif algorithm == "RS256":
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    else:
        raise ValueError(f"Unsupported algorithm '{algorithm}'. Choose 'Ed25519' or 'RS256'.")
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return private_pem, _public_pem(private_key)


def public_key_from_private(private_key_pem: str) -> str:
    """Derive the public key PEM of a private key PEM (the OEM verifies its own access tokens)."""
    private_key = serialization.load_pem_private_key(clean_pem(private_key_pem).encode("utf-8"), password=None)
    return _public_pem(private_key)


def _public_pem(private_key: Any) -> str:
    return (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )


def detect_algorithm(key_pem: str) -> str:
    """Detect whether a PEM key represents RSA (RS256) or Ed25519 (EdDSA) from the loaded key type."""
    data = clean_pem(key_pem).encode("utf-8")
    loaded: Any = None
    try:
        loaded = serialization.load_pem_private_key(data, password=None)
    except (ValueError, TypeError):
        try:
            loaded = serialization.load_pem_public_key(data)
        except (ValueError, TypeError):
            loaded = None
    if isinstance(loaded, rsa.RSAPrivateKey | rsa.RSAPublicKey):
        return "RS256"
    return "EdDSA"


def _sign(private_key_pem: str, payload: dict[str, Any], token_type: str) -> str:
    cleaned_key = clean_pem(private_key_pem)
    return jwt.encode(
        payload,
        cleaned_key,
        algorithm=detect_algorithm(cleaned_key),
        headers={"typ": token_type},
    )


def _base_claims(issuer: str, audience: str, expires_in_seconds: int, now: datetime | None) -> dict[str, Any]:
    now_ts = int((now or datetime.now(UTC)).timestamp())
    return {
        "iss": issuer,
        "aud": audience,
        "iat": now_ts,
        "exp": now_ts + expires_in_seconds,
        "jti": str(uuid.uuid4()),
    }


def _strip_bearer(token: str | None) -> str:
    if not token or not token.strip():
        raise M2MTokenMissingError("M2M token is missing")
    token_str = token.strip()
    if token_str.startswith(M2M_BEARER_PREFIX):
        token_str = token_str[len(M2M_BEARER_PREFIX) :].strip()
    if not token_str:
        raise M2MTokenMissingError("M2M token is missing")
    return token_str


def _decode(
    token: str | None,
    public_key_pem: str,
    *,
    expected_type: str,
    expected_issuer: str,
    expected_audience: str,
    tolerance_seconds: int,
    required: list[str],
) -> dict[str, Any]:
    token_str = _strip_bearer(token)
    try:
        header = jwt.get_unverified_header(token_str)
    except jwt.InvalidTokenError as exc:
        raise M2MTokenInvalidError(f"M2M token signature or format is invalid: {exc}") from exc
    token_type = str(header.get("typ") or "")
    if token_type.lower() != expected_type.lower():
        raise M2MTokenTypeError(f"M2M token type '{token_type}' is not '{expected_type}'")
    try:
        return jwt.decode(
            token_str,
            clean_pem(public_key_pem),
            algorithms=_ALGORITHMS,
            issuer=expected_issuer,
            audience=expected_audience,
            leeway=tolerance_seconds,
            options={"require": required},
        )
    except jwt.ExpiredSignatureError as exc:
        raise M2MTokenExpiredError(f"M2M token has expired: {exc}") from exc
    except jwt.InvalidAudienceError as exc:
        raise M2MAudienceMismatchError(f"M2M token audience mismatch: {exc}") from exc
    except jwt.InvalidIssuerError as exc:
        raise M2MIssuerMismatchError(f"M2M token issuer mismatch: {exc}") from exc
    except jwt.InvalidTokenError as exc:
        raise M2MTokenInvalidError(f"M2M token signature or format is invalid: {exc}") from exc


def create_m2m_token(
    private_key_pem: str,
    *,
    issuer: str,
    audience: str,
    expires_in_seconds: int = WEBHOOK_TOKEN_TTL_SECONDS,
    now: datetime | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a self-signed ``typ=JWT`` token (used for webhooks)."""
    payload = {**(extra_claims or {}), **_base_claims(issuer, audience, expires_in_seconds, now)}
    return _sign(private_key_pem, payload, SELF_SIGNED_TOKEN_TYPE)


def verify_m2m_token(
    token: str | None,
    public_key_pem: str,
    *,
    expected_issuer: str,
    expected_audience: str,
    tolerance_seconds: int = M2M_CLOCK_SKEW_SECONDS,
) -> dict[str, Any]:
    """Verify a self-signed ``typ=JWT`` token with the sender's public key; returns its claims."""
    return _decode(
        token,
        public_key_pem,
        expected_type=SELF_SIGNED_TOKEN_TYPE,
        expected_issuer=expected_issuer,
        expected_audience=expected_audience,
        tolerance_seconds=tolerance_seconds,
        required=["exp", "iat", "iss", "aud", "jti"],
    )


def create_client_assertion(
    private_key_pem: str,
    *,
    client_id: str = EVCARE_CLIENT_ID,
    audience: str = OEM_ISSUER,
    expires_in_seconds: int = CLIENT_ASSERTION_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Create the client assertion EV Care exchanges for an access token (``iss = sub = client_id``)."""
    payload = {**_base_claims(client_id, audience, expires_in_seconds, now), "sub": client_id}
    return _sign(private_key_pem, payload, SELF_SIGNED_TOKEN_TYPE)


def verify_client_assertion(
    token: str | None,
    public_key_pem: str,
    *,
    expected_client_id: str = EVCARE_CLIENT_ID,
    expected_audience: str = OEM_ISSUER,
    tolerance_seconds: int = M2M_CLOCK_SKEW_SECONDS,
) -> dict[str, Any]:
    """Verify a client assertion at the token endpoint. Replay (``jti``) is checked by the caller."""
    claims = _decode(
        token,
        public_key_pem,
        expected_type=SELF_SIGNED_TOKEN_TYPE,
        expected_issuer=expected_client_id,
        expected_audience=expected_audience,
        tolerance_seconds=tolerance_seconds,
        required=["exp", "iat", "iss", "sub", "aud", "jti"],
    )
    if claims.get("sub") != expected_client_id:
        raise M2MSubjectMismatchError("Client assertion subject must equal the client id")
    return claims


def create_access_token(
    private_key_pem: str,
    *,
    subject: str = EVCARE_CLIENT_ID,
    issuer: str = OEM_ISSUER,
    audience: str = OEM_ISSUER,
    expires_in_seconds: int = ACCESS_TOKEN_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    """Create the OEM-issued session token (``typ=at+jwt``)."""
    payload = {
        **_base_claims(issuer, audience, expires_in_seconds, now),
        "sub": subject,
        "client_id": subject,
    }
    return _sign(private_key_pem, payload, ACCESS_TOKEN_TYPE)


def verify_access_token(
    token: str | None,
    public_key_pem: str,
    *,
    expected_subject: str = EVCARE_CLIENT_ID,
    expected_issuer: str = OEM_ISSUER,
    expected_audience: str = OEM_ISSUER,
    tolerance_seconds: int = M2M_CLOCK_SKEW_SECONDS,
) -> dict[str, Any]:
    """Verify an OEM-issued access token; returns its claims."""
    claims = _decode(
        token,
        public_key_pem,
        expected_type=ACCESS_TOKEN_TYPE,
        expected_issuer=expected_issuer,
        expected_audience=expected_audience,
        tolerance_seconds=tolerance_seconds,
        required=["exp", "iat", "iss", "sub", "aud", "jti"],
    )
    if claims.get("sub") != expected_subject:
        raise M2MSubjectMismatchError("Access token subject is not the expected client")
    return claims
