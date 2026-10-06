from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from .context import AgentCtx
from .graph import extract_text_from_content
from .state import AgentState

# Tắt tracing tự động nếu chưa cấu hình dự án LangSmith
os.environ["LANGCHAIN_TRACING_V2"] = "false"

logger = logging.getLogger(__name__)


async def fetch_vehicle_context(
    vehicle_id: str | UUID | None,
    *,
    session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
) -> dict[str, Any]:
    return await run_in_threadpool(_fetch_vehicle_context_sync, vehicle_id, session_factory=session_factory)


def _fetch_vehicle_context_sync(
    vehicle_id: str | UUID | None,
    *,
    session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
) -> dict[str, Any]:
    """Truy vấn thông tin xe từ database để nạp trước vào ngữ cảnh Agent (Pre-loaded Context).

    Đọc trung thực từ UserVehicle, VehicleOdometerReading và VehicleServiceRecord.
    Nếu thiếu dữ liệu, trả None (không tự fake về 0 hoặc bịa số liệu).
    """
    if not vehicle_id:
        return {}

    try:
        from datetime import date

        from sqlmodel import select

        try:
            from src.common.core.vehicle import (
                UserVehicle,
                VehicleOdometerReading,
                VehicleServiceRecord,
            )
        except ImportError:
            from common.core.vehicle import (  # type: ignore
                UserVehicle,
                VehicleOdometerReading,
                VehicleServiceRecord,
            )

        if session_factory is None:
            from .tools._services import open_session

            session_factory = open_session

        with session_factory() as session:
            v_uuid = UUID(str(vehicle_id)) if isinstance(vehicle_id, str) and len(str(vehicle_id)) == 36 else vehicle_id
            if isinstance(v_uuid, UUID):
                v = session.get(UserVehicle, v_uuid)
            else:
                v = session.exec(select(UserVehicle).where(UserVehicle.license_plate == str(vehicle_id))).first()

            if v:
                # 1. Truy vấn Odometer mới nhất
                odo_row = session.exec(
                    select(VehicleOdometerReading)
                    .where(VehicleOdometerReading.user_vehicle_id == v.id)
                    .order_by(VehicleOdometerReading.odo_km.desc(), VehicleOdometerReading.recorded_at.desc())
                    .limit(1)
                ).first()
                current_odo = odo_row.odo_km if odo_row else None

                # 2. Truy vấn Lịch sử bảo dưỡng định kỳ gần nhất
                last_record = session.exec(
                    select(VehicleServiceRecord)
                    .where(
                        VehicleServiceRecord.user_vehicle_id == v.id,
                        VehicleServiceRecord.is_periodic.is_(True),
                    )
                    .order_by(
                        VehicleServiceRecord.service_date.desc(),
                        VehicleServiceRecord.odo_km.desc().nulls_last(),
                    )
                    .limit(1)
                ).first()

                last_service_odo = last_record.odo_km if last_record else None
                months_since_last = None
                if last_record and last_record.service_date:
                    today = date.today()
                    months_since_last = (today.year - last_record.service_date.year) * 12 + (
                        today.month - last_record.service_date.month
                    )

                return {
                    "vehicle_id": str(v.id),
                    "user_id": v.user_id,
                    "model": v.external_model_id or v.declared_model_id or v.model_name or "VinFast",
                    "license_plate": v.license_plate,
                    "current_odo": current_odo,
                    "last_service_odo": last_service_odo,
                    "months_since_last": months_since_last,
                }
    except Exception as e:
        logger.debug("Không thể nạp thông tin xe từ database (%s), sử dụng ngữ cảnh mặc định.", e)

    return {}


def _run_config(ctx: AgentCtx) -> RunnableConfig:
    """Config của một lượt chạy graph.

    Chủ xe và xe của phiên chat: tool đọc từ đây (``tools/_services.caller``), không nhận
    từ tham số do LLM sinh ra. ``thread_id`` là khóa checkpoint của LangGraph (HITL).
    """
    return {
        "configurable": {
            "ctx": ctx,
            "thread_id": str(ctx.conversation_id),
            "user_id": ctx.user_id,
            "user_vehicle_id": str(ctx.vehicle_id) if ctx.vehicle_id else None,
            "conversation_id": str(ctx.conversation_id) if ctx.conversation_id else None,
        }
    }


class AgentOrchestrator:
    """Streaming agent runner with an injected graph and vehicle-context loader."""

    def __init__(
        self,
        graph: Any,
        vehicle_context_loader: Callable[[str | UUID | None], Awaitable[dict[str, Any]]],
    ) -> None:
        self._graph = graph
        self._vehicle_context_loader = vehicle_context_loader

    async def fetch_vehicle_context(self, vehicle_id: str | UUID | None) -> dict[str, Any]:
        return await self._vehicle_context_loader(vehicle_id)

    async def run_agent_turn(
        self,
        conversation_id: str | UUID,
        user_id: int | str,
        vehicle_id: str | UUID | None = None,
        message: str = "",
        vehicle_context: dict[str, Any] | None = None,
        history_messages: list[BaseMessage] | None = None,
        source_message_id: str | UUID | None = None,
        operation_key: str | None = None,
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
            resolved_context = await self.fetch_vehicle_context(vehicle_id)

        # Khởi tạo AgentCtx an toàn đưa vào config để Tool đọc qua context thay vì LLM truyền id
        agent_ctx = AgentCtx(
            user_id=user_id,
            vehicle_id=vehicle_id or (resolved_context.get("vehicle_id") or ""),
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            operation_key=operation_key,
        )
        run_config = _run_config(agent_ctx)

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
            # 3. Chạy vòng lặp ReAct qua astream_events với config chứa ctx
            async for event in self._graph.astream_events(initial_state, config=run_config, version="v2"):
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
            # BẢO VỆ GIAO DỊCH: TUYỆT ĐỐI KHÔNG fallback chạy lại ainvoke(initial_state)
            # để tránh double side-effect khi tool ghi đã kịp chạy trước khi stream đứt kết nối.
            if not accumulated_text:
                fallback_msg = "Hệ thống gặp sự cố trong quá trình xử lý yêu cầu. Quý khách vui lòng thử lại sau giây lát hoặc liên hệ hotline 1900 23 23 89."
                accumulated_text = fallback_msg
                yield {
                    "type": "token",
                    "delta": fallback_msg,
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

    async def confirm_booking_turn(
        self,
        conversation_id: str | UUID,
        user_id: int | str,
        confirmed: bool,
        vehicle_id: str | UUID | None = None,
        source_message_id: str | UUID | None = None,
        operation_key: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Resume graph sau khi user xác nhận hoặc hủy đặt lịch (HITL).

        Gọi hàm này khi frontend nhận được event 'hitl_required' và user đã bấm
        "Xác nhận" hoặc "Hủy". Graph sẽ được resume từ checkpoint, tiếp tục
        thực thi create_booking_draft (nếu confirmed=True) hoặc hủy (confirmed=False).

        Yields cùng format event như run_agent_turn:
            - {"type": "token", "delta": text}
            - {"type": "tool_start", ...}, {"type": "tool_end", ...}
            - {"type": "completed", "message_data": {...}}
        """
        agent_ctx = AgentCtx(
            user_id=user_id,
            vehicle_id=vehicle_id or "",
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            operation_key=operation_key,
        )
        run_config = _run_config(agent_ctx)

        # Resume graph với quyết định của user
        resume_command = Command(resume={"confirmed": confirmed})

        accumulated_text = ""
        citations: list[dict[str, Any]] = []

        try:
            async for event in self._graph.astream_events(resume_command, config=run_config, version="v2"):
                event_type = event.get("event")

                if event_type == "on_tool_start":
                    yield {
                        "type": "tool_start",
                        "tool": event.get("name", ""),
                        "input": event.get("data", {}).get("input", {}),
                    }
                elif event_type == "on_tool_end":
                    yield {
                        "type": "tool_end",
                        "tool": event.get("name", ""),
                        "output": event.get("data", {}).get("output", {}),
                    }
                elif event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        delta = extract_text_from_content(chunk.content)
                        if delta:
                            accumulated_text += delta
                            yield {"type": "token", "delta": delta}
                elif event_type == "on_chain_end":
                    output = event.get("data", {}).get("output")
                    if isinstance(output, dict) and output.get("citations"):
                        citations = output["citations"]

        except Exception as exc:
            logger.error("Lỗi khi resume HITL confirm_booking_turn: %s", exc, exc_info=True)
            if not accumulated_text:
                fallback_msg = (
                    "Hệ thống gặp sự cố khi xử lý xác nhận. Vui lòng thử lại hoặc liên hệ hotline 1900 23 23 89."
                )
                accumulated_text = fallback_msg
                yield {"type": "token", "delta": fallback_msg}

        yield {
            "type": "completed",
            "message_data": {
                "conversation_id": str(conversation_id),
                "user_id": str(user_id),
                "vehicle_id": str(vehicle_id) if vehicle_id else None,
                "role": "assistant",
                "content": accumulated_text,
                "citations": citations,
                "hitl_resolved": True,
                "confirmed": confirmed,
            },
        }


async def run_agent_turn(
    conversation_id: str | UUID,
    user_id: int | str,
    vehicle_id: str | UUID | None = None,
    message: str = "",
    vehicle_context: dict[str, Any] | None = None,
    history_messages: list[BaseMessage] | None = None,
    source_message_id: str | UUID | None = None,
    operation_key: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Compatibility entrypoint using the default dependency composition."""
    from .dependency import get_agent_orchestrator

    async for event in get_agent_orchestrator().run_agent_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        vehicle_id=vehicle_id,
        message=message,
        vehicle_context=vehicle_context,
        history_messages=history_messages,
        source_message_id=source_message_id,
        operation_key=operation_key,
    ):
        yield event


async def confirm_booking_turn(
    conversation_id: str | UUID,
    user_id: int | str,
    confirmed: bool,
    vehicle_id: str | UUID | None = None,
    source_message_id: str | UUID | None = None,
    operation_key: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Resume using the same graph instance as the original turn."""
    from .dependency import get_agent_orchestrator

    async for event in get_agent_orchestrator().confirm_booking_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        confirmed=confirmed,
        vehicle_id=vehicle_id,
        source_message_id=source_message_id,
        operation_key=operation_key,
    ):
        yield event
