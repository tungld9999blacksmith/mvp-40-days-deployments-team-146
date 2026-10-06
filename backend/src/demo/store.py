"""One shared store per demo application, with injectable clock for tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo


def now_vn() -> datetime:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))


class DemoError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, **details: Any):
        super().__init__(message)
        self.code, self.status, self.details = code, status, details


@dataclass
class DemoStore:
    registration_path: Path | None = None
    registration_lock: Any = field(default_factory=RLock)
    clock: Callable[[], datetime] = now_vn
    skip_onboarding: bool = False
    onboarding: dict[str, dict] = field(default_factory=dict)
    onboarding_operations: dict[tuple[str, str], tuple[dict, dict]] = field(default_factory=dict)
    users: dict[str, dict] = field(default_factory=dict)
    workshop_owners: dict[str, dict] = field(default_factory=dict)
    vehicles: dict[str, dict] = field(default_factory=dict)
    workshops: dict[str, dict] = field(default_factory=dict)
    prices: dict[str, dict[str, int]] = field(default_factory=dict)
    rules: list[dict] = field(default_factory=list)
    slot_capacity: dict[tuple[str, str, str], int] = field(default_factory=dict)
    conversations: dict[str, dict] = field(default_factory=dict)
    messages: dict[str, list[dict]] = field(default_factory=dict)
    bookings: dict[str, dict] = field(default_factory=dict)
    tokens: dict[str, dict] = field(default_factory=dict)
    proposals: dict[str, dict] = field(default_factory=dict)
    operations: dict[tuple[int, str], tuple[str, str]] = field(default_factory=dict)
    chat_locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    booking_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    seq: int = 0

    def timestamp(self) -> str:
        return self.clock().isoformat()
