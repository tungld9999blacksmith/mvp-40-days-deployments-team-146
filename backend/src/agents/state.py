from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """State schema cho LangGraph agent EV Care.

    Mỗi node đọc và ghi vào state này.
    total=False cho phép tất cả fields là optional.
    """

    query: str
    vehicle_model: str | None
    current_odometer_km: int | None
    context: str
    analysis: str
    response: str
    citations: list[dict[str, Any]]
    confidence: str
    fallback_required: bool
    error: str
    metadata: dict[str, Any]
