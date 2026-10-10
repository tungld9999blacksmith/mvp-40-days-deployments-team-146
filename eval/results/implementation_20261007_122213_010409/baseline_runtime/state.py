from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """State schema cho LangGraph ReAct agent EV Care.

    - messages: Lịch sử hội thoại tự động append bởi add_messages
    - vehicle_context: Thông tin ngữ cảnh xe được nạp trước từ session
    - draft_booking: Thông tin bản nháp đặt lịch hẹn (HOLD) nếu có
    - citations: Danh sách tài liệu kỹ thuật / cẩm nang đã trích dẫn
    - query, response, metadata: Các trường tương thích ngược
    """

    messages: Annotated[list[BaseMessage], add_messages]
    vehicle_context: dict[str, Any]
    draft_booking: dict[str, Any] | None
    citations: list[dict[str, Any]]

    # Trường tương thích ngược
    query: str
    vehicle_model: str | None
    current_odometer_km: int | None
    context: str
    analysis: str
    response: str
    confidence: str
    fallback_required: bool
    error: str
    metadata: dict[str, Any]
