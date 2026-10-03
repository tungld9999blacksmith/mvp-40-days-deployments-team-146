from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage

from .graph import agent, extract_text_from_content
from .state import AgentState

# Tắt tracing tự động nếu chưa cấu hình dự án LangSmith
os.environ["LANGCHAIN_TRACING_V2"] = "false"

logger = logging.getLogger(__name__)


async def fetch_vehicle_context(vehicle_id: str | UUID | None) -> dict[str, Any]:
    """Truy vấn thông tin xe từ database để nạp trước vào ngữ cảnh Agent (Pre-loaded Context)."""
    if not vehicle_id:
        return {}

    try:
        from sqlmodel import Session

        try:
            from src.common.core.vehicle import UserVehicle
        except ImportError:
            from common.core.vehicle import UserVehicle  # type: ignore

        try:
            from src.infrastructure.supabase.db import engine
        except ImportError:
            from infrastructure.supabase.db import engine  # type: ignore

        with Session(engine) as session:
            v_uuid = UUID(str(vehicle_id)) if isinstance(vehicle_id, str) else vehicle_id
            v = session.get(UserVehicle, v_uuid)
            if v:
                return {
                    "vehicle_id": str(v.id),
                    "model": v.external_model_id or v.declared_model_id or "VinFast",
                    "license_plate": v.license_plate,
                    "current_odo": getattr(v, "odometer_km", 0) or 0,
                    "last_service_odo": getattr(v, "last_service_odometer_km", None),
                    "months_since_last": getattr(v, "months_since_last_service", 0) or 0,
                }
    except Exception as e:
        logger.debug("Không thể nạp thông tin xe từ database (%s), sử dụng ngữ cảnh mặc định.", e)

    return {}


async def run_agent_turn(
    conversation_id: str,
    user_id: int | str,
    vehicle_id: str | UUID | None = None,
    message: str = "",
    vehicle_context: dict[str, Any] | None = None,
    history_messages: list[BaseMessage] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Thực thi một lượt hội thoại của Agent EV Care theo luồng ReAct.

    Yields:
        - {"type": "tool_start", "tool": name, "input": args}: Bắt đầu gọi tool
        - {"type": "tool_end", "tool": name, "output": output}: Kết thúc gọi tool
        - {"type": "token", "delta": text}: Từng phần của câu trả lời stream về
        - {"type": "completed", "message_data": {...}}: Hoàn tất toàn bộ lượt
    """
    # 1. Nạp trước ngữ cảnh xe (Pre-loaded Context)
    resolved_context = dict(vehicle_context or {})
    if not resolved_context and vehicle_id:
        resolved_context = await fetch_vehicle_context(vehicle_id)

    # 2. Chuẩn bị State ban đầu
    messages: list[BaseMessage] = list(history_messages or [])
    if message:
        messages.append(HumanMessage(content=message))

    initial_state: AgentState = {
        "messages": messages,
        "vehicle_context": resolved_context,
        "citations": [],
    }

    accumulated_text = ""
    citations: list[dict[str, Any]] = []

    try:
        # 3. Chạy vòng lặp ReAct qua astream_events
        async for event in agent.astream_events(initial_state, version="v2"):
            event_type = event.get("event")

            # A. Sự kiện Bắt đầu gọi Tool
            if event_type == "on_tool_start":
                tool_name = event.get("name", "")
                tool_input = event.get("data", {}).get("input", {})
                yield {
                    "type": "tool_start",
                    "tool": tool_name,
                    "input": tool_input,
                }

            # B. Sự kiện Kết thúc gọi Tool
            elif event_type == "on_tool_end":
                tool_name = event.get("name", "")
                tool_output = event.get("data", {}).get("output", {})
                yield {
                    "type": "tool_end",
                    "tool": tool_name,
                    "output": tool_output,
                }

            # C. Sự kiện Stream Token từ Chat Model (chỉ lấy token của node cuối trả lời user)
            elif event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content"):
                    delta = extract_text_from_content(chunk.content)
                    if delta:
                        accumulated_text += delta
                        yield {
                            "type": "token",
                            "delta": delta,
                        }

            # D. Ghi nhận citations từ output của node agent
            elif event_type == "on_chain_end":
                output = event.get("data", {}).get("output")
                if isinstance(output, dict) and output.get("citations"):
                    citations = output["citations"]

    except Exception as exc:
        logger.error("Lỗi trong vòng lặp agent astream_events: %s", exc, exc_info=True)
        # Fallback chạy ainvoke nếu astream_events gặp lỗi
        if not accumulated_text:
            result = await agent.ainvoke(initial_state)
            last_msg = result["messages"][-1]
            accumulated_text = extract_text_from_content(last_msg.content)
            if isinstance(result, dict) and result.get("citations"):
                citations = result["citations"]
            yield {
                "type": "token",
                "delta": accumulated_text,
            }

    # 4. Phát tín hiệu hoàn tất (message.completed)
    yield {
        "type": "completed",
        "message_data": {
            "conversation_id": str(conversation_id),
            "user_id": str(user_id),
            "vehicle_id": str(vehicle_id) if vehicle_id else None,
            "role": "assistant",
            "content": accumulated_text,
            "citations": citations,
        },
    }
