"""Conversation module — ChatService (US-025).

Orchestrates a chat turn on top of the infrastructure built-ins:

- rate limit via a Redis sorted-set sliding window,
- one-run-per-conversation via a Redis critical-section lock,
- the single writer ``MessageService`` (persist + publish + optional index),
- tool execution and generation via the injected ``AgentOrchestrator``.

Reads use sync repositories; the streaming path is async.
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing, asynccontextmanager
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import anyio
from langchain_core.messages import BaseMessage
from sqlalchemy import func, select
from sqlmodel import Session, col
from starlette.concurrency import run_in_threadpool

from src.common.client_ip import client_key, current_client_ip
from src.common.concurrency import wait_through_cancellation
from src.common.core.conversation import (
    ChatMessage,
    ChatMessageRepository,
    Conversation,
    ConversationRepository,
    MessageRole,
)
from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.vehicle import UserVehicle, VehicleLinkStatus
from src.common.data_access import eq, ge, gt, in_, lt
from src.config import Settings
from src.infrastructure.llm.base import ChatMessage as LlmMessage
from src.infrastructure.llm.base import LLMProvider, Role
from src.infrastructure.messaging import AppendResult, ConversationNotFoundError, MessageDto, MessageService
from src.infrastructure.prompts import load_prompt
from src.infrastructure.redis import RedisToolkit
from src.infrastructure.vectorstore import CONVERSATION_MESSAGES, VectorStore
from src.modules.booking_line.cards import CARD_BOOKING_LINES, enrich_line_cards
from src.modules.quick_booking.cards import attach_message, enrich_cards
from src.modules.quick_booking.domain import CARD_PROPOSAL
from src.modules.quote.cards import CARD_QUOTE, enrich_quote_cards

from . import errors
from .schemas import SseFrame

if TYPE_CHECKING:
    from src.agents.orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = load_prompt("customer_chat")
_HISTORY_TURNS = 20
_RETRIEVE_K = 5


class ChatService:
    def __init__(
        self,
        engine,
        message_service: MessageService,
        toolkit: RedisToolkit,
        llm: LLMProvider | None,
        knowledge_store: VectorStore | None,
        vector_store: VectorStore | None,
        settings: Settings,
        orchestrator: AgentOrchestrator | None,
    ) -> None:
        self._engine = engine
        self._messages = message_service
        self._toolkit = toolkit
        self._llm = llm
        self._knowledge = knowledge_store
        self._vectors = vector_store
        self._settings = settings
        self._orchestrator = orchestrator

    def _get_orchestrator(self) -> AgentOrchestrator:
        if self._orchestrator is None:
            from src.agents.dependency import get_agent_orchestrator

            self._orchestrator = get_agent_orchestrator()
        return self._orchestrator

    def _get_vectors(self) -> VectorStore:
        if self._vectors is None:
            from src.infrastructure.vectorstore.dependency import get_vector_store

            self._vectors = get_vector_store()
        return self._vectors

    def _get_knowledge(self) -> VectorStore:
        if self._knowledge is None:
            from src.infrastructure.vectorstore.dependency import get_knowledge_vector_store

            self._knowledge = get_knowledge_vector_store()
        return self._knowledge

    # -- conversations ----------------------------------------------------
    def create_conversation(self, user_id: int, user_vehicle_id: UUID, title: str | None) -> Conversation:
        with Session(self._engine) as session:
            vehicle = session.get(UserVehicle, user_vehicle_id)
            if vehicle is None or vehicle.user_id != user_id:
                raise errors.VehicleNotFound()
            if vehicle.link_status != VehicleLinkStatus.ACTIVE:
                raise errors.VehicleNotActive()
            repo = ConversationRepository(session)
            conversation = repo.create({"user_id": user_id, "user_vehicle_id": user_vehicle_id, "title": title})
            session.commit()
            session.refresh(conversation)
            return conversation

    def get_owned_conversation(self, user_id: int, conversation_id: UUID) -> Conversation:
        with Session(self._engine) as session:
            conversation = ConversationRepository(session).get(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise errors.ConversationNotFound()
        return conversation

    def list_conversations(
        self,
        user_id: int,
        user_vehicle_id: UUID | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Conversation], str | None, bool]:
        filters = [eq("user_id", user_id)]
        if user_vehicle_id is not None:
            filters.append(eq("user_vehicle_id", user_vehicle_id))
        with Session(self._engine) as session:
            page = ConversationRepository(session).paginate_cursor(
                limit=limit, cursor=cursor, filters=filters, order_by=("-last_message_at", "-id")
            )
        return page.items, page.next_cursor, page.has_next

    def last_message_previews(self, conversation_ids: list[UUID]) -> dict[UUID, str | None]:
        """Fetch previews in one query instead of opening a connection per row."""
        if not conversation_ids:
            return {}
        latest = (
            select(ChatMessage.conversation_id, func.max(ChatMessage.seq).label("seq"))
            .where(
                col(ChatMessage.conversation_id).in_(conversation_ids),
                col(ChatMessage.role).in_([MessageRole.USER, MessageRole.ASSISTANT]),
            )
            .group_by(ChatMessage.conversation_id)
            .subquery()
        )
        statement = select(ChatMessage.conversation_id, ChatMessage.content).join(
            latest,
            (ChatMessage.conversation_id == latest.c.conversation_id) & (ChatMessage.seq == latest.c.seq),
        )
        with Session(self._engine) as session:
            rows = session.execute(statement).all()
        return {conversation_id: content[:100] if content else None for conversation_id, content in rows}

    # -- messages ---------------------------------------------------------
    def list_messages(
        self,
        conversation_id: UUID,
        limit: int,
        before: int | None,
        after: int | None,
    ) -> tuple[list[ChatMessage], str | None, bool]:
        if before is not None and after is not None:
            raise errors.InvalidRequest("Use only one of 'before' or 'after'.")
        filters = [
            eq("conversation_id", conversation_id),
            in_("role", [MessageRole.USER, MessageRole.ASSISTANT]),
        ]
        ascending = after is not None
        if after is not None:
            filters.append(gt("seq", after))
        elif before is not None:
            filters.append(lt("seq", before))
        order_by = ("seq",) if ascending else ("-seq",)
        with Session(self._engine) as session:
            rows = ChatMessageRepository(session).search(filters=filters, order_by=order_by, limit=limit + 1)
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = str(rows[-1].seq) if has_more and rows else None
        return rows, next_cursor, has_more

    def search_messages(
        self,
        user_id: int,
        query: str,
        user_vehicle_id: UUID | None,
        limit: int,
        before_seq: int | None,
    ) -> tuple[list[tuple[ChatMessage, str | None, str]], int | None, bool]:
        tsquery = func.plainto_tsquery("simple", func.immutable_unaccent(query))
        headline = func.ts_headline(
            "simple",
            ChatMessage.content,
            tsquery,
            "MaxWords=25, MinWords=10, StartSel=<mark>, StopSel=</mark>",
        )
        stmt = (
            select(ChatMessage, col(Conversation.title), headline)
            .join(Conversation, col(Conversation.id) == ChatMessage.conversation_id)
            .where(
                col(Conversation.user_id) == user_id,
                col(ChatMessage.role).in_([MessageRole.USER, MessageRole.ASSISTANT]),
                col(ChatMessage.search_vector).op("@@")(tsquery),
            )
            .order_by(col(ChatMessage.seq).desc())
            .limit(limit + 1)
        )
        if user_vehicle_id is not None:
            stmt = stmt.where(col(Conversation.user_vehicle_id) == user_vehicle_id)
        if before_seq is not None:
            stmt = stmt.where(col(ChatMessage.seq) < before_seq)
        with Session(self._engine) as session:
            rows = session.execute(stmt).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        hits = [(row[0], row[1], row[2]) for row in rows]  # (message, title, snippet)
        next_cursor = int(hits[-1][0].seq) if has_more and hits else None
        return hits, next_cursor, has_more

    def semantic_search(self, conversation_id: UUID, query: str, k: int) -> list[tuple[ChatMessage, float]]:
        if not self._settings.conversation_semantic_index_enabled:
            raise errors.SemanticSearchDisabled()
        results = self._get_vectors().similarity_search(
            CONVERSATION_MESSAGES, query, k=k, where={"conversationId": str(conversation_id)}
        )
        ids = [UUID(r.id) for r in results]
        if not ids:
            return []
        with Session(self._engine) as session:
            found = {m.id: m for m in ChatMessageRepository(session).find_in("id", ids)}
        return [(found[UUID(r.id)], r.score) for r in results if UUID(r.id) in found]

    # -- deletion ---------------------------------------------------------
    async def delete_conversation(self, user_id: int, conversation_id: UUID) -> None:
        from src.agents.checkpoint import current_checkpointer
        from src.modules.agent_memory.lifecycle import ConversationMemoryLifecycleService

        service = ConversationMemoryLifecycleService(
            self._engine, self._settings, self.run_lock, current_checkpointer(), self._get_vectors
        )
        await service.delete(user_id, conversation_id)

    # -- streaming a turn -------------------------------------------------
    async def stream_turn(
        self,
        user_id: int,
        conversation_id: UUID,
        client_message_id: UUID,
        content: str,
        *,
        trace_id: str | None,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[SseFrame]:
        content = content.strip()
        if not content or len(content) > self._settings.chat_message_max_chars:
            raise errors.InvalidRequest("content must be 1..max chars.")

        vehicle = await run_in_threadpool(self._get_chat_vehicle, user_id, conversation_id)

        await self._check_rate_limit(user_id)

        async with self.run_lock(conversation_id):
            async with aclosing(
                self._run_turn(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    vehicle=vehicle,
                    client_message_id=client_message_id,
                    content=content,
                    trace_id=trace_id,
                    is_disconnected=is_disconnected,
                )
            ) as frames:
                async for frame in frames:
                    yield frame

    def _get_chat_vehicle(self, user_id: int, conversation_id: UUID) -> UserVehicle:
        conversation = self.get_owned_conversation(user_id, conversation_id)
        with Session(self._engine) as session:
            vehicle = session.get(UserVehicle, conversation.user_vehicle_id)
        if vehicle is None or vehicle.link_status != VehicleLinkStatus.ACTIVE:
            raise errors.VehicleNotActive()
        return vehicle

    @asynccontextmanager
    async def run_lock(self, conversation_id: UUID) -> AsyncIterator[None]:
        """One run per conversation (chat turn or quick-booking action); busy ⇒ ``ConversationBusy``."""
        lock = self._toolkit.locks.critical_section(
            f"conversation-run:{conversation_id}",
            ttl=self._settings.chat_run_lock_ttl_seconds,
            auto_renew=True,
        )
        if not await lock.acquire(blocking=False):
            raise errors.ConversationBusy()
        try:
            yield
        finally:
            # A disconnected stream is cancelled through anyio; still free the lock now.
            with anyio.CancelScope(shield=True):
                try:
                    await lock.release()
                except Exception:  # noqa: BLE001 — TTL will reclaim it
                    logger.warning("Run lock release failed for %s", conversation_id)

    async def check_rate_limit(self, user_id: int) -> None:
        """Chat rate limit, shared by the quick-booking endpoints (us-061 API §2)."""
        await self._check_rate_limit(user_id)

    def to_dtos(self, messages: list[ChatMessage]) -> list[MessageDto]:
        """Client DTOs; proposal and quote cards get their live status (us-061 HOOK-QB-01, us-049)."""
        dtos = [MessageDto.from_message(m) for m in messages]
        if not any(d.card for d in dtos):
            return dtos
        with Session(self._engine) as session:
            return enrich_line_cards(session, enrich_quote_cards(session, enrich_cards(session, dtos)))

    async def _run_turn(
        self,
        conversation_id: UUID,
        user_id: int,
        vehicle: UserVehicle,
        client_message_id: UUID,
        content: str,
        trace_id: str | None,
        is_disconnected: Callable[[], Awaitable[bool]] | None,
    ) -> AsyncIterator[SseFrame]:
        """Bound the entire turn, including initialization and persistence.

        Wait on disconnect independently of token delivery. Closing this generator
        cancels the pending agent step before its conversation lock is released.
        """
        frames = self._run_turn_frames(conversation_id, user_id, vehicle, client_message_id, content, trace_id)
        deadline = asyncio.get_running_loop().time() + self._settings.chat_run_timeout_seconds
        cleanup_timeout = getattr(self._settings, "chat_run_cleanup_timeout_seconds", 15)
        accepted = False
        pending: asyncio.Task | None = None

        async def watch_disconnect() -> None:
            while True:
                if await is_disconnected():
                    return
                await asyncio.sleep(0.1)

        disconnected = asyncio.create_task(watch_disconnect()) if is_disconnected else None
        abandoned = False  # a step that ignored cancellation past cleanup_timeout
        try:
            while True:
                pending = asyncio.create_task(anext(frames))
                waiting = {pending, disconnected} if disconnected is not None else {pending}
                done, _ = await asyncio.wait(
                    waiting,
                    timeout=max(0, deadline - asyncio.get_running_loop().time()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if disconnected is not None and disconnected in done:
                    disconnected.result()
                    logger.info("Client disconnected for %s (accepted=%s); ending turn", conversation_id, accepted)
                    return
                if pending not in done:
                    raise TimeoutError("Chat run exceeded its deadline")
                try:
                    frame = pending.result()
                except StopAsyncIteration:
                    return
                accepted |= frame.event == "message.accepted"
                yield frame
                if frame.event in {"message.completed", "error"}:
                    return
        except Exception as exc:
            if not accepted:
                if isinstance(exc, TimeoutError):
                    raise errors.ConversationError(
                        "The assistant timed out. Please retry.", code="CHAT_TIMEOUT"
                    ) from exc
                raise
            logger.warning("Chat turn failed for %s", conversation_id, exc_info=True)
            # Stop the producer (and let an in-flight write finish) before reporting
            # a terminal frame to the client.
            if pending is not None and await _stop(pending, cleanup_timeout, frames):
                raise asyncio.CancelledError from exc
            abandoned = pending is not None and not pending.done()
            yield SseFrame(
                event="error",
                data={
                    "code": "CHAT_TIMEOUT" if isinstance(exc, TimeoutError) else "AGENT_ERROR",
                    "message": "Trợ lý xử lý quá lâu. Vui lòng thử lại."
                    if isinstance(exc, TimeoutError)
                    else "Trợ lý tạm thời không trả lời được.",
                    "traceId": trace_id,
                },
            )
        finally:
            # Finish every cleanup step, then honour a cancellation of this task.
            cancelled = False
            with anyio.CancelScope(shield=True):
                for task in (pending, disconnected):
                    if task is not None and not (task is pending and abandoned):
                        cancelled |= await _stop(task, cleanup_timeout, frames if task is pending else None)
                # An abandoned step is still running the generator, which cannot be closed then.
                if pending is None or pending.done():
                    await frames.aclose()
            if cancelled:
                raise asyncio.CancelledError

    async def _run_turn_frames(
        self,
        conversation_id: UUID,
        user_id: int,
        vehicle: UserVehicle,
        client_message_id: UUID,
        content: str,
        trace_id: str | None,
    ) -> AsyncIterator[SseFrame]:
        # The insert runs in a worker thread a deadline cannot stop; keep the
        # conversation lock until it has finished, then publish (cancellable).
        write = asyncio.create_task(
            self._messages.append(
                conversation_id,
                MessageRole.USER,
                content,
                client_message_id=client_message_id,
                publish=False,
            )
        )
        if await wait_through_cancellation(write):
            raise asyncio.CancelledError
        try:
            user_result = write.result()
        except ConversationNotFoundError:
            raise errors.ConversationNotFound()
        if user_result.created:
            await self._messages.publish(conversation_id, user_result.message)

        replay = await run_in_threadpool(self._replay_if_answered, conversation_id, user_result)
        if replay is not None:
            yield SseFrame(
                event="message.accepted",
                data={
                    "userMessage": MessageDto.from_message(user_result.message).model_dump(mode="json"),
                    "replayed": True,
                },
            )
            yield SseFrame(
                event="message.completed",
                data={"message": (await run_in_threadpool(self.to_dtos, [replay]))[0].model_dump(mode="json")},
            )
            return

        yield SseFrame(
            event="message.accepted",
            data={
                "userMessage": MessageDto.from_message(user_result.message).model_dump(mode="json"),
                "replayed": False,
            },
        )

        # Seam tích hợp LangGraph Agent Orchestrator (Mục 6 README)
        yield SseFrame(event="status", data={"stage": "analyzing"})
        agent_run_id = uuid4()
        pieces: list[str] = []
        collected_citations: list[dict] = []
        completed_answer: str | None = None
        response_metadata: dict = {}
        # The last booking or quote card belongs to the committed answer.
        card: dict | None = None

        orchestrator = await run_in_threadpool(self._get_orchestrator)
        vehicle_context = await orchestrator.fetch_vehicle_context(vehicle.id)
        if not vehicle_context:
            vehicle_context = {
                "vehicle_id": str(vehicle.id),
                "model": vehicle.external_model_id or vehicle.declared_model_id or "VinFast",
                "license_plate": vehicle.license_plate,
                "current_odo": getattr(vehicle, "odometer_km", None),
                "last_service_odo": getattr(vehicle, "last_service_odometer_km", None),
                "months_since_last": getattr(vehicle, "months_since_last_service", None),
            }

        history_messages = await run_in_threadpool(
            self._build_history_messages, conversation_id, exclude_seq=user_result.message.seq
        )
        memory_inputs = {}
        if isinstance(self._settings, Settings):
            memory_inputs = await run_in_threadpool(self._memory_inputs, user_id, vehicle.id, conversation_id)

        try:
            async with aclosing(
                orchestrator.run_agent_turn(
                    conversation_id=str(conversation_id),
                    user_id=user_id,
                    vehicle_id=vehicle.id,
                    message=content,
                    vehicle_context=vehicle_context,
                    history_messages=history_messages,
                    source_message_id=user_result.message.id,
                    operation_key=str(client_message_id),
                    **memory_inputs,
                )
            ) as events:
                async for event in events:
                    event_type = event.get("type")
                    if event_type == "token":
                        delta = event.get("delta", "")
                        pieces.append(delta)
                        yield SseFrame(event="token", data={"delta": delta})
                    elif event_type == "tool_start":
                        tool_name = event.get("tool", "")
                        yield SseFrame(
                            event="status",
                            data={"stage": f"Đang tra cứu {tool_name}...", "tool": tool_name},
                        )
                    elif event_type == "tool_end" and event.get("tool") in _CARD_TOOLS:
                        card = _tool_card(event.get("output")) or card
                    elif event_type == "completed":
                        msg_data = event.get("message_data", {})
                        if "citations" in msg_data and isinstance(msg_data["citations"], list):
                            collected_citations = msg_data["citations"]
                        if isinstance(msg_data.get("content"), str):
                            completed_answer = msg_data["content"]
                        for key in ("confidence", "fallback_required"):
                            if key in msg_data:
                                response_metadata[key] = msg_data[key]

        except Exception as exc:
            yield SseFrame(
                event="error",
                data={"code": "AGENT_ERROR", "message": "Trợ lý tạm thời không trả lời được.", "traceId": trace_id},
            )
            logger.warning("Agent error for %s: %s", conversation_id, exc, exc_info=True)
            return

        answer = (completed_answer if completed_answer is not None else "".join(pieces)).strip()
        if card is not None and not answer:
            answer = _CARD_FALLBACK_ANSWER[card["type"]]
        # Finish protected writes before releasing the conversation lock.
        persist = asyncio.create_task(
            self._persist_answer(conversation_id, answer, collected_citations, card, agent_run_id, trace_id, response_metadata)
        )
        if await wait_through_cancellation(persist):
            raise asyncio.CancelledError
        assistant = persist.result()
        record = getattr(orchestrator, "record_committed_answer", None)
        if callable(record):
            await record(conversation_id, assistant.message.id, assistant.message.content)
        if self._settings.agent_memory_context_mode in ("on", "shadow"):
            from src.modules.agent_memory.summary import SummaryService

            try:
                summary = await run_in_threadpool(SummaryService(self._engine, self._settings).update, conversation_id)
                if summary and self._settings.agent_memory_context_mode == "on":
                    await orchestrator.compact_committed_history(conversation_id, summary)
                    await run_in_threadpool(SummaryService(self._engine, self._settings).mark_compacted,
                                            conversation_id, summary["version"])
            except Exception as exc:
                # Committed answers must remain successful if summarizing fails.
                logger.warning("agent_memory_summary_failed conversation_id=%s error_type=%s", conversation_id, type(exc).__name__)
        if assistant.created:
            await self._messages.publish(conversation_id, assistant.message)
        yield SseFrame(
            event="message.completed",
            data={"message": (await run_in_threadpool(self.to_dtos, [assistant.message]))[0].model_dump(mode="json")},
        )

    async def _persist_answer(
        self,
        conversation_id: UUID,
        answer: str,
        citations: list[dict],
        card: dict | None,
        agent_run_id: UUID,
        trace_id: str | None,
        response_metadata: dict | None = None,
    ) -> AppendResult:
        assistant = await self._messages.append(
            conversation_id,
            MessageRole.ASSISTANT,
            answer,
            citations=citations,
            card=card,
            intent=None,
            agent_run_id=agent_run_id,
            trace_id=trace_id,
            refs={"rag": response_metadata} if response_metadata else {},
            publish=False,  # published by the caller, outside the protected write
        )
        if card is not None and card["type"] == CARD_PROPOSAL:
            await run_in_threadpool(self._attach_proposal_message, card, assistant.message.id)
        return assistant

    def _attach_proposal_message(self, proposal_card: dict, message_id: UUID) -> None:
        with Session(self._engine) as session:
            attach_message(session, UUID(proposal_card["proposalId"]), message_id)

    def _replay_if_answered(self, conversation_id: UUID, user_result: AppendResult) -> ChatMessage | None:
        """On an idempotent resend, return the assistant reply if one already exists."""
        if user_result.created:
            return None
        with Session(self._engine) as session:
            return ChatMessageRepository(session).find_one(
                filters=[
                    eq("conversation_id", conversation_id),
                    eq("role", MessageRole.ASSISTANT),
                    ge("seq", user_result.message.seq or 0),
                ],
                order_by=("seq",),
            )

    async def _retrieve(self, query: str) -> tuple[list[dict], str]:
        try:
            knowledge = await run_in_threadpool(self._get_knowledge)
            hits = await knowledge.asimilarity_search("*", query, k=_RETRIEVE_K)
        except Exception:  # noqa: BLE001 — no knowledge configured / empty store
            logger.debug("Knowledge retrieval unavailable", exc_info=True)
            return [], ""
        citations = [
            {
                "chunkId": h.id,
                "documentId": h.metadata.get("document_id"),
                "pageNumber": h.metadata.get("page_number"),
                "snippet": h.content[:500],
                "score": h.score,
            }
            for h in hits
        ]
        context = "\n\n".join(f"[{i + 1}] {h.content}" for i, h in enumerate(hits))
        return citations, context

    def _build_prompt(self, conversation_id: UUID, user_content: str, context: str) -> list[LlmMessage]:
        messages: list[LlmMessage] = [LlmMessage(role="system", content=_SYSTEM_PROMPT)]
        with Session(self._engine) as session:
            history = ChatMessageRepository(session).search(
                filters=[
                    eq("conversation_id", conversation_id),
                    in_("role", [MessageRole.USER, MessageRole.ASSISTANT]),
                ],
                order_by=("-seq",),
                limit=_HISTORY_TURNS,
            )
        for msg in reversed(history):
            role: Role = "user" if msg.role == MessageRole.USER else "assistant"
            messages.append(LlmMessage(role=role, content=msg.content))
        if context:
            messages.append(LlmMessage(role="system", content=f"Tài liệu chính hãng liên quan:\n{context}"))
        return messages

    def _build_history_messages(self, conversation_id: UUID, exclude_seq: int | None = None) -> list[BaseMessage]:
        """Chuyển đổi lịch sử chat thành định dạng BaseMessage cho LangGraph Agent."""
        from src.modules.agent_memory.summary import SummaryService

        if self._settings.agent_memory_context_mode == "on":
            SummaryService(self._engine, self._settings).update(conversation_id)
        return SummaryService(self._engine, self._settings).history(conversation_id, exclude_seq)[0]

    def _memory_inputs(self, user_id, vehicle_id, conversation_id):
        from src.common.core.conversation.memory import ConversationSummary
        from src.modules.agent_memory.preferences import PreferenceService

        with Session(self._engine) as session:
            summary = session.get(ConversationSummary, conversation_id)
            preferences = PreferenceService(session, self._settings).recall(user_id, vehicle_id)
            use_summary = summary and (summary.compacted or self._settings.agent_memory_context_mode == "on")
            return {"memory_summary": dict(summary.summary_json) if use_summary else {}, "memory_preferences": preferences}

    # -- rate limit -------------------------------------------------------
    async def _check_rate_limit(self, user_id: int) -> None:
        now = time.time()
        if self._settings.demo_login_enabled and await run_in_threadpool(self._is_demo_user, user_id):
            # One account for every visitor: limit each client IP, and the account as a whole.
            s = self._settings
            key = client_key(current_client_ip())
            await self._enforce_window(f"chat:rl:demo:{key}:min", now, 60, s.demo_chat_rate_limit_per_minute)
            await self._enforce_window(f"chat:rl:demo:{key}:day", now, 86400, s.demo_chat_rate_limit_per_day)
            await self._enforce_window("chat:rl:demo:all:day", now, 86400, s.demo_chat_total_per_day)
            return
        await self._enforce_window(f"chat:rl:{user_id}:min", now, 60, self._settings.chat_rate_limit_per_minute)
        await self._enforce_window(f"chat:rl:{user_id}:day", now, 86400, self._settings.chat_rate_limit_per_day)

    def _is_demo_user(self, user_id: int) -> bool:
        with Session(self._engine) as session:
            user = session.get(VehicleUser, user_id)
            return bool(user and user.is_demo)

    async def _enforce_window(self, key: str, now: float, window: int, limit: int) -> None:
        zset = self._toolkit.sorted_set(key, str, ttl=window)
        await zset.remove_by_score("-inf", now - window)
        if await zset.count() >= limit:
            raise errors.RateLimited(retry_after=window)
        await zset.add(f"{now}:{uuid4().hex}", now)

    # -- workshop excerpt -------------------------------------------------
    def excerpt_for_source(self, source_type: str, source_message_id: UUID, source_id: UUID) -> dict:
        limit = self._settings.chat_excerpt_max_messages
        with Session(self._engine) as session:
            src = session.get(ChatMessage, source_message_id)
            if src is None:
                raise errors.ExcerptNotAvailable()
            rows = ChatMessageRepository(session).search(
                filters=[
                    eq("conversation_id", src.conversation_id),
                    in_("role", [MessageRole.USER, MessageRole.ASSISTANT]),
                    lt("seq", (src.seq or 0) + 1),
                ],
                order_by=("-seq",),
                limit=limit,
            )
        rows.reverse()
        return {
            "source": {"type": source_type, "id": source_id, "confirmedMessageId": source_message_id},
            "messages": rows,
        }


async def _stop(task: asyncio.Task, timeout: float | None = None, awaiting: object = None) -> bool:
    """Cancel ``task``, wait until it has really finished and report whether we were cancelled.

    A step that ignores cancellation for ``timeout`` seconds (a hung network call) is
    abandoned, so the turn ends and its run lock is released; where ``awaiting`` (the
    turn's frame generator) is stuck is logged.
    """
    task.cancel()
    cancelled = await wait_through_cancellation(task, timeout)
    if not task.done():
        logger.error(
            "Abandoned a turn step still running %.0fs after cancellation; stuck at:\n%s",
            timeout,
            "\n".join(_await_chain(awaiting)) or "<unknown>",
        )
        task.add_done_callback(_retrieve_result)
        return cancelled
    _retrieve_result(task)
    return cancelled


def _retrieve_result(task: asyncio.Task) -> None:
    if not task.cancelled():
        task.exception()  # already handled or reported by the turn; mark it retrieved


def _await_chain(awaitable: object) -> list[str]:
    """Source locations of the coroutine/async-generator chain ``awaitable`` is suspended in."""
    chain = []
    for _ in range(100):
        if awaitable is None:
            break
        frame = getattr(awaitable, "cr_frame", None) or getattr(awaitable, "ag_frame", None)
        if frame is None:
            frame = getattr(awaitable, "gi_frame", None)
        if frame is None:
            # ``async for`` awaits an ``async_generator_asend`` that only references its generator.
            inner = [r for r in gc.get_referents(awaitable) if hasattr(r, "ag_frame") or hasattr(r, "cr_frame")]
            if inner:
                awaitable = inner[0]
                continue
            chain.append(f"  awaiting {awaitable!r}"[:300])
            break
        chain.append(f"  {frame.f_code.co_filename}:{frame.f_lineno} in {frame.f_code.co_name}")
        awaitable = (
            getattr(awaitable, "cr_await", None)
            or getattr(awaitable, "ag_await", None)
            or getattr(awaitable, "gi_yieldfrom", None)
        )
    return chain


# Tools whose ToolMessage artifact is a chat card, and the answer used when the model says nothing.
_CARD_TOOLS = frozenset({"propose_booking", "create_draft_quote", "get_booking_lines"})
_CARD_FALLBACK_ANSWER = {
    CARD_PROPOSAL: 'Mình đã chuẩn bị đề xuất đặt lịch. Bấm "Xác nhận đặt lịch" trên thẻ để đặt.',
    CARD_QUOTE: 'Mình đã lập báo giá nháp. Bấm "Gửi xưởng duyệt" trên thẻ để gửi xưởng.',
    CARD_BOOKING_LINES: 'Bạn xem các hạng mục xưởng đề xuất và tự quyết trên phiếu: bấm "Mở phiếu để quyết định".',
}


def _is_card(card) -> bool:
    if not isinstance(card, dict):
        return False
    if card.get("type") == CARD_PROPOSAL:
        return bool(card.get("proposalId"))
    if card.get("type") == CARD_QUOTE:
        return isinstance(card.get("quote"), dict) and bool(card["quote"].get("quoteId"))
    if card.get("type") == CARD_BOOKING_LINES:
        return bool(card.get("bookingId"))
    return False


def _tool_card(output) -> dict | None:
    """Card artifact of a card tool's ToolMessage (never shown to the LLM)."""
    artifact = getattr(output, "artifact", None)
    if _is_card(artifact):
        return artifact
    content = getattr(output, "content", None)
    if isinstance(content, str):
        try:
            data = json.loads(content)
        except ValueError:
            return None
        card = data.get("card") if isinstance(data, dict) else None
        if _is_card(card):
            return card
    return None
