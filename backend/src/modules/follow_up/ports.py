"""Follow-up — ports (us-041)."""

from __future__ import annotations

from typing import Protocol

from .domain import Classification


class FeedbackClassifier(Protocol):
    """AI-007 ``classify_feedback`` (TOOL-702). Return ``None`` on timeout / bad output.

    The comment is passed as data inside a delimited block, never as an
    instruction (FF EF-906). Implementations must finish within 5 s.
    """

    async def classify(self, rating: int, comment: str) -> Classification | None: ...
