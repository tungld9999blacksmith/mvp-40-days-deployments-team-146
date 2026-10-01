"""
Wire format shared by pub/sub messages and queue entries:

    <meta JSON>\\n<payload bytes>

The meta line is JSON (never contains a raw newline); the payload is whatever the
channel's / queue's Serializer produced, so binary serializers work too.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import SerializationError


def pack(meta: dict[str, Any], payload: bytes) -> bytes:
    return json.dumps(meta, separators=(",", ":")).encode() + b"\n" + payload


def unpack(raw: bytes) -> tuple[dict[str, Any], bytes]:
    head, sep, payload = raw.partition(b"\n")
    if not sep:
        raise SerializationError("Malformed envelope: missing meta separator")
    try:
        return json.loads(head), payload
    except ValueError as exc:
        raise SerializationError(f"Malformed envelope meta: {exc}") from exc
