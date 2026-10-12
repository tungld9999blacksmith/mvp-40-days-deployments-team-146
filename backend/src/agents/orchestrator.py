from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool

from ..infrastructure.observability import agent_callbacks, current_trace_ids, step
from ..infrastructure.prompts import prompt_version
from .context import AgentCtx
from .conversation_guards import apply_output_guard, inspect_input
from .graph import extract_text_from_content
from .state import AgentState
from .telemetry import TurnRecorder, record_input_guard

logger = logging.getLogger(__name__)

# Checkpoint reads/writes hit the database; a dead connection must fail, not stall a turn.
_CHECKPOINT_TIMEOUT_SECONDS = 10.0


async def _checkpoint_call(awaitable: Awaitable[Any]) -> Any:
    return await asyncio.wait_for(awaitable, _CHECKPOINT_TIMEOUT_SECONDS)


async def _discard_thread(saver: Any, conversation_id: str | UUID) -> None:
    """Best-effort checkpoint reset on a cancelled turn; never replaces the cancellation."""
    try:
        await _checkpoint_call(saver.adelete_thread(str(conversation_id)))
    except Exception:
        logger.warning("Could not reset the agent checkpoint of %s", conversation_id, exc_info=True)


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


def _guarded_message_data(
    content: str,
    citations: list[dict[str, Any]],
    base: dict[str, Any],
) -> dict[str, Any]:
    """Apply the output guard to the final answer before it is stored/emitted.

    PII is always redacted (safety). The no-source-no-claim and cost-label flags
    are logged for observability; enforcement as a hard gate lives in the eval
    CI (see docs/specs/ai-agent/ai-eval-testing-strategy.spec.md #11).
    """
    safe_text, report = apply_output_guard(content, citations=citations)
    if report.pii_redacted:
        logger.warning("Output guard redacted PII in answer: %s", report.pii_redacted)
    if report.missing_citation:
        logger.warning("Output guard: technical claim without citation.")
    if report.unlabelled_cost:
        logger.warning("Output guard: cost figure without estimate label.")
    return {**base, "content": safe_text, "citations": citations}


def _run_config(ctx: AgentCtx) -> RunnableConfig:
    """Config của một lượt chạy graph.

    Chủ xe và xe của phiên chat: tool đọc từ đây (``tools/_services.caller``), không nhận
    từ tham số do LLM sinh ra. ``thread_id`` là khóa checkpoint của LangGraph (HITL).
    ``metadata`` travels with the run to LangSmith: ``otel_trace_id`` links the run
    to the request's trace in Grafana.
    """
    metadata: dict[str, str] = {}
    if ctx.conversation_id:
        metadata["conversation_id"] = str(ctx.conversation_id)
    trace_ids = current_trace_ids()
    if trace_ids:
        metadata["otel_trace_id"] = trace_ids[0]
    return {
        "metadata": metadata,
        # Grafana-side spans of the model calls (LangSmith traces them natively).
        "callbacks": agent_callbacks(),
        "configurable": {
            "ctx": ctx,
            "thread_id": str(ctx.conversation_id),
            "user_id": ctx.user_id,
            "user_vehicle_id": str(ctx.vehicle_id) if ctx.vehicle_id else None,
            "conversation_id": str(ctx.conversation_id) if ctx.conversation_id else None,
            "source_message_id": str(ctx.source_message_id) if ctx.source_message_id else None,
        },
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
        memory_summary: dict[str, Any] | None = None,
        memory_preferences: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Thực thi một lượt hội thoại của Agent EV Care theo luồng ReAct.

        The whole turn is one ``agent.turn``: the root LangSmith run (input guard,
        LangGraph, tools, RAG nest under it) and one Grafana span with the outcome.

        Yields:
            - {"type": "tool_start", "tool": name, "input": args}: Bắt đầu gọi tool
            - {"type": "tool_end", "tool": name, "output": output}: Kết thúc gọi tool
            - {"type": "token", "delta": text}: Từng phần của câu trả lời stream về
            - {"type": "completed", "message_data": {...}}: Hoàn tất toàn bộ lượt
        """
        recorder = TurnRecorder()
        with step(
            "agent.turn",
            attributes={"agent.name": "customer", "conversation.id": str(conversation_id)},
            inputs={"message": message},
            # thread_id groups the turns of one conversation in LangSmith "Threads".
            metadata={
                "thread_id": str(conversation_id),
                "conversation_id": str(conversation_id),
                "source_message_id": str(source_message_id) if source_message_id else None,
                # Names the system prompt version of the run, filterable in LangSmith.
                "prompt_version": f"ev_care_base@v{prompt_version('ev_care_base')}",
            },
            tags=["agent", "chat"],
        ) as current:
            try:
                async for event in self._run_turn(
                    recorder,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    vehicle_id=vehicle_id,
                    message=message,
                    vehicle_context=vehicle_context,
                    history_messages=history_messages,
                    source_message_id=source_message_id,
                    operation_key=operation_key,
                    memory_summary=memory_summary,
                    memory_preferences=memory_preferences,
                ):
                    if event.get("type") == "completed":
                        recorder.completed(event["message_data"])
                    yield event
            except (asyncio.CancelledError, GeneratorExit):
                recorder.cancelled()
                raise
            finally:
                recorder.finish(current)

    async def _run_turn(
        self,
        recorder: TurnRecorder,
        *,
        conversation_id: str | UUID,
        user_id: int | str,
        vehicle_id: str | UUID | None,
        message: str,
        vehicle_context: dict[str, Any] | None,
        history_messages: list[BaseMessage] | None,
        source_message_id: str | UUID | None,
        operation_key: str | None,
        memory_summary: dict[str, Any] | None,
        memory_preferences: list[dict[str, Any]] | None,
    ) -> AsyncIterator[dict[str, Any]]:
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
        # Private configurable keys are not serialized into checkpoint metadata.
        # Never retain a cached preference after revoke/toggle/source deletion.
        run_config["configurable"]["__memory_preferences"] = memory_preferences or []

        # Input guard: log injection attempts / pasted PII for observability.
        if message:
            with step("agent.guard.input", attributes={"guard.stage": "input"}, inputs={"message": message}) as guard:
                input_report = inspect_input(message)
                record_input_guard(guard, input_report)
            if input_report.has_injection:
                logger.warning("Input guard: possible prompt-injection in user turn.")
            if input_report.has_pii:
                logger.info("Input guard: user message contains PII %s", input_report.pii_found)

        # 2. Chuẩn bị State ban đầu
        messages: list[BaseMessage] = list(history_messages or [])
        # The durable checkpoint already contains tool messages and prior turns.
        # Seed database history only for a new/recovered thread.
        saver = getattr(self._graph, "checkpointer", None)
        checkpoint = await _checkpoint_call(saver.aget_tuple(run_config)) if saver is not None else None
        if checkpoint:
            known_ids = {m.id for m in checkpoint.checkpoint.get("channel_values", {}).get("messages", [])}
            # Include new committed booking-confirmation messages, without
            # replaying already checkpointed user/assistant messages.
            messages = [m for m in messages if m.id not in known_ids]
        if message:
            messages.append(HumanMessage(content=message, id=str(source_message_id) if source_message_id else None))

        initial_state: AgentState = {
            "messages": messages,
            "vehicle_context": resolved_context,
            "citations": [],
            "memory_summary": memory_summary or {},
        }

        accumulated_text = ""
        citations: list[dict[str, Any]] = []
        response_metadata: dict[str, Any] = {}
        from .booking_policy import guarded_booking_turn

        defer_business_tokens = guarded_booking_turn(messages)
        from .memory_guard import memory_change_request, memory_topic_request
        defer_business_tokens = defer_business_tokens or memory_change_request(message) or memory_topic_request(message)

        try:
            # 3. Chạy vòng lặp ReAct qua astream_events với config chứa ctx
            async for event in self._graph.astream_events(initial_state, config=run_config, version="v2"):
                event_type = event.get("event")

                # A. Sự kiện Bắt đầu gọi Tool
                if event_type == "on_tool_start":
                    tool_name = event.get("name", "")
                    recorder.tool_started(tool_name)
                    if tool_name in {"get_due_maintenance", "estimate_service_cost", "find_workshops", "get_available_slots", "propose_booking", "search_ev_knowledge", "get_maintenance_schedule_rag", "get_warranty_policy_rag", "remember_preference", "forget_preference"}:
                        # Model tokens have not yet passed the terminal fact guard.
                        if not defer_business_tokens:
                            accumulated_text = ""  # A pre-tool introduction is not a verified answer.
                        defer_business_tokens = True
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
                        if delta and not defer_business_tokens:
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
                    if isinstance(output, dict):
                        for key in ("confidence", "fallback_required"):
                            if key in output:
                                response_metadata[key] = output[key]
                        # Deterministic terminal nodes can replace unsafe model output
                        # or answer without invoking a model. Persist the graph's answer.
                        if output.get("response"):
                            accumulated_text = output["response"]

        except (asyncio.CancelledError, GeneratorExit):
            if saver is not None:
                await _discard_thread(saver, conversation_id)
            raise
        except Exception as exc:
            recorder.failed(exc)
            # Never run the turn again. Clear incomplete tool state; next turn
            # reconstructs committed user/assistant history with stable IDs.
            if saver is not None:
                await _checkpoint_call(saver.adelete_thread(str(conversation_id)))
            logger.error("Lỗi trong vòng lặp agent astream_events: %s", exc, exc_info=True)
            # BẢO VỆ GIAO DỊCH: TUYỆT ĐỐI KHÔNG fallback chạy lại ainvoke(initial_state)
            # để tránh double side-effect khi tool ghi đã kịp chạy trước khi stream đứt kết nối.
            if not accumulated_text:
                fallback_msg = "Hệ thống gặp sự cố trong quá trình xử lý yêu cầu. Quý khách vui lòng thử lại sau giây lát hoặc liên hệ hotline 1900 23 23 89."
                accumulated_text = fallback_msg
                if not defer_business_tokens:
                    yield {
                        "type": "token",
                        "delta": fallback_msg,
                    }

        # 4. Phát tín hiệu hoàn tất (message.completed)
        if defer_business_tokens and accumulated_text:
            yield {"type": "token", "delta": accumulated_text}
        yield {
            "type": "completed",
            "message_data": {
                "conversation_id": str(conversation_id),
                "user_id": str(user_id),
                "vehicle_id": str(vehicle_id) if vehicle_id else None,
                "role": "assistant",
                "content": accumulated_text,
                "citations": citations,
                **response_metadata,
            },
        }

    async def record_committed_answer(self, conversation_id, message_id, content):
        """Replace the final model ID with the database assistant ID after commit."""
        saver = getattr(self._graph, "checkpointer", None)
        if saver is None:
            return
        config = {"configurable": {"thread_id": str(conversation_id)}}
        try:
            state = await _checkpoint_call(self._graph.aget_state(config))
            messages = state.values.get("messages", [])
            if not messages:
                return
            last = messages[-1]
            if not isinstance(last, AIMessage) or last.tool_calls:
                await _checkpoint_call(saver.adelete_thread(str(conversation_id)))
                return
            replacement = last.model_copy(update={"id": str(message_id), "content": content})
            changes = [RemoveMessage(id=last.id), replacement] if last.id != str(message_id) else [replacement]
            await _checkpoint_call(self._graph.aupdate_state(config, {"messages": changes}, as_node="agent"))
        except Exception:
            # The DB reply is committed. Rebuild its history next turn.
            try:
                await _checkpoint_call(saver.adelete_thread(str(conversation_id)))
            except Exception:
                logger.warning("Checkpoint unavailable after assistant persistence")
            logger.warning("Checkpoint reset after assistant persistence mismatch")

    async def compact_committed_history(self, conversation_id, summary_result):
        """Update only a completed thread after durable summary commit; no tool replay."""
        config = {"configurable": {"thread_id": str(conversation_id)}}
        snapshot = await _checkpoint_call(self._graph.aget_state(config))
        if snapshot.next or snapshot.interrupts:
            return
        from .memory_context import turns

        messages = snapshot.values.get("messages", [])
        covered = set(summary_result["source_ids"])
        remove = []
        for group in turns(messages):
            users = [m for m in group if isinstance(m, HumanMessage)]
            if users and all(m.id in covered for m in users):
                remove.extend(RemoveMessage(id=m.id) for m in group if m.id)
        if remove:
            await _checkpoint_call(self._graph.aupdate_state(config,
                {"messages": remove, "memory_summary": summary_result["summary"]}, as_node="agent"))


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


__all__ = ["AgentOrchestrator", "fetch_vehicle_context", "run_agent_turn"]
