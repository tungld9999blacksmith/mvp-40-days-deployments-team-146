"""PII / secret redaction processor for structlog.

Runs on every event dict (structlog and stdlib records alike) right before
rendering, so no output — stdout or files — ever sees the raw values.

Two passes:

1. **By key** — values under sensitive keys are dropped (``[REDACTED]``) or
   masked (emails, phones), wherever they sit in nested dicts / lists.
2. **By value** — free text (messages, query strings, tracebacks) is scanned for
   bearer / basic credentials, JWTs, well-known API key formats,
   ``key=value`` secrets, emails and phone numbers.

Values are copied, never mutated in place: the objects passed to a log call
may still be used by the caller.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from structlog.types import EventDict, WrappedLogger

REDACTED = "[REDACTED]"

# Values dropped entirely. Keys are compared lower-cased with "-" -> "_".
DEFAULT_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "client_secret",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "api_key",
        "apikey",
        "x_api_key",
        "authorization",
        "proxy_authorization",
        "cookie",
        "set_cookie",
        "private_key",
        "otp",
        "verification_code",
    }
)
# Suffixes that also mark a key as secret (e.g. "telegram_bot_token").
# "_tokens" (LLM usage counters) and "_key" (cache / idempotency keys) are
# deliberately NOT included.
_SECRET_SUFFIXES = ("_token", "_secret", "_password", "_api_key", "_apikey")

# Personal data dropped entirely.
DEFAULT_PERSONAL_KEYS: frozenset[str] = frozenset(
    {
        "full_name",
        "first_name",
        "last_name",
        "display_name",
        "address",
        "home_address",
        "date_of_birth",
        "dob",
        "birthday",
        "national_id",
        "id_number",
        "id_card",
        "cccd",
        "passport",
        "passport_number",
    }
)
_EMAIL_KEYS = frozenset({"email", "email_address", "user_email"})
_PHONE_KEYS = frozenset({"phone", "phone_number", "mobile", "mobile_phone", "tel", "telephone"})

# Our own tracing / bookkeeping fields: never scanned (hex ids could look like digits).
_SAFE_KEYS = frozenset(
    {
        "timestamp",
        "level",
        "logger",
        "correlation_id",
        "trace_id",
        "parent_span_id",
        "span_id",
        "duration_ms",
        "status_code",
        "http_method",
        "http_path",
    }
)

# ── value patterns ──────────────────────────────────────────────────────
_AUTH_SCHEME = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9\-._~+/]+=*")
_JWT = re.compile(r"\beyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]{5,}")
_API_KEYS = re.compile(
    r"\b(?:"
    r"sk-(?:ant-|proj-)?[A-Za-z0-9_\-]{16,}"  # OpenAI / Anthropic
    r"|AIza[0-9A-Za-z_\-]{35}"  # Google
    r"|gh[pousr]_[A-Za-z0-9]{36,}"  # GitHub
    r"|xox[abprs]-[A-Za-z0-9\-]{10,}"  # Slack
    r"|AKIA[0-9A-Z]{16}"  # AWS access key id
    r")"
)
# key=value / "key": "value" style secrets inside free text or query strings.
_KV_SECRET = re.compile(
    r"(?i)\b(access_token|refresh_token|id_token|token|api[_-]?key|x-api-key|"
    r"client_secret|secret|password|passwd|pwd)"
    r"(\"?'?\s*[:=]\s*\"?'?)"
    r"([^\s&\"',;}]+)"
)
_EMAIL = re.compile(r"\b([A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]*@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")
# Vietnamese mobiles (0 / 84 / +84 prefix) and any "+"-prefixed international number.
_PHONE = re.compile(
    r"(?<![\w+])(?:"
    r"(?:\+?84|0)[35789](?:[\s.\-]?\d){8}"
    r"|\+\d{1,3}[\s.\-]?\d(?:[\s.\-]?\d){6,12}"
    r")(?!\w)"
)


def mask_email(value: str) -> str:
    """``tung@gmail.com`` -> ``t***@gmail.com``."""
    return _EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", value)


def mask_phone(value: str) -> str:
    """Keep only the last 3 digits: ``0912345678`` -> ``*******678``."""
    digits = re.sub(r"\D", "", value)
    if len(digits) <= 3:
        return "*" * len(digits)
    return "*" * (len(digits) - 3) + digits[-3:]


def redact_text(value: str) -> str:
    """Scrub secrets and PII out of free text."""
    value = _AUTH_SCHEME.sub(lambda m: f"{m.group(1)} {REDACTED}", value)
    value = _JWT.sub(REDACTED, value)
    value = _API_KEYS.sub(REDACTED, value)
    value = _KV_SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", value)
    value = mask_email(value)
    return _PHONE.sub(lambda m: mask_phone(m.group(0)), value)


class PiiRedactor:
    """structlog processor: redact secrets / PII from the whole event dict."""

    def __init__(
        self,
        *,
        secret_keys: Iterable[str] = DEFAULT_SECRET_KEYS,
        personal_keys: Iterable[str] = DEFAULT_PERSONAL_KEYS,
    ) -> None:
        self.drop_keys = {_norm(k) for k in (*secret_keys, *personal_keys)}

    def __call__(self, logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
        return {key: value if key in _SAFE_KEYS else self._redact(key, value) for key, value in event_dict.items()}

    def _redact(self, key: Any, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(key, str):
            norm = _norm(key)
            if norm in self.drop_keys or norm.endswith(_SECRET_SUFFIXES):
                return REDACTED
            if norm in _EMAIL_KEYS and isinstance(value, str):
                return mask_email(value) if "@" in value else REDACTED
            if norm in _PHONE_KEYS and isinstance(value, str | int):
                return mask_phone(str(value))
        return self._scrub(value)

    def _scrub(self, value: Any) -> Any:
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, Mapping):
            return {k: self._redact(k, v) for k, v in value.items()}
        if isinstance(value, list | tuple | set | frozenset):
            return [self._scrub(v) for v in value]
        return value


def _norm(key: str) -> str:
    return key.lower().replace("-", "_")
