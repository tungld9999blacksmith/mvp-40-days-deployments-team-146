"""Conversation module — ChatService (US-025).

Orchestrates a chat turn on top of the infrastructure built-ins:

- rate limit via a Redis sorted-set sliding window,
- one-run-per-conversation via a Redis critical-section lock,
- the single writer ``MessageService`` (persist + publish + optional index),
- retrieval via the knowledge vector store, generation via ``LLMProvider.chat_stream``.

The full LangGraph orchestrator (AI-001) is a separate spec; this service is the
seam it will plug into. Reads use sync repositories; the streaming path is async.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlmodel import Session

from src.common.core.conversation import (
    ChatMessage,
    ChatMessageRepository,
    Conversation,
    ConversationRepository,
    MessageRole,
)
from src.common.core.vehicle import UserVehicle, VehicleLinkStatus
from src.common.data_access import eq, ge, gt, in_, lt
from src.config import Settings
from src.infrastructure.llm.base import ChatMessage as LlmMessage
from src.infrastructure.llm.base import LLMProvider, LLMProviderError
from src.infrastructure.messaging import AppendResult, ConversationNotFoundError, MessageService
from src.infrastructure.redis import RedisToolkit
from src.infrastructure.vectorstore import CONVERSATION_MESSAGES, VectorStore

from . import errors
from .schemas import SseFrame

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Bạn là trợ lý chăm sóc xe điện của EV Care. Trả lời bằng tiếng Việt, ngắn gọn. "
    "Chỉ khẳng định thông tin kỹ thuật/bảo hành khi có trong tài liệu chính hãng được "
    "cung cấp; nếu không có nguồn, hãy nói rõ chưa có dữ liệu chính hãng và gợi ý liên hệ xưởng."
)
_HISTORY_TURNS = 20
_RETRIEVE_K = 5


class ChatService:
    def __init__(
        self,
        engine,
        message_service: MessageService,
        toolkit: RedisToolkit,
        llm: LLMProvider,
        knowledge_store: VectorStore,
        vector_store: VectorStore,
        settings: Settings,
    ) -> None:
        self._engine = engine
        self._messages = message_service
        self._toolkit = toolkit
        self._llm = llm
        self._knowledge = knowledge_store
        self._vectors = vector_store
        self._settings = settings

    # -- conversations ----------------------------------------------------
    def create_conversation(
        self, user_id: int, user_vehicle_id: UUID, title: str | None
    ) -> Conversation:
        with Session(self._engine) as session:
            vehicle = session.get(UserVehicle, user_vehicle_id)
            if vehicle is None or vehicle.user_id != user_id:
                raise errors.VehicleNotFound()
            if vehicle.link_status != VehicleLinkStatus.ACTIVE:
                raise errors.VehicleNotActive()
            repo = ConversationRepository(session)
            conversation = repo.create(
                {"user_id": user_id, "user_vehicle_id": user_vehicle_id, "title": title}
            )
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

    def last_message_preview(self, conversation_id: UUID) -> str | None:
        with Session(self._engine) as session:
            stmt = (
                select(ChatMessage.content)
                .where(
                    ChatMessage.conversation_id == conversation_id,
                    ChatMessage.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
                )
                .order_by(ChatMessage.seq.desc())
                .limit(1)
            )
            content = session.execute(stmt).scalars().first()
        return content[:100] if content else None

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
            rows = ChatMessageRepository(session).search(
                filters=filters, order_by=order_by, limit=limit + 1
            )
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
            select(ChatMessage, Conversation.title, headline)
            .join(Conversation, Conversation.id == ChatMessage.conversation_id)
            .where(
                Conversation.user_id == user_id,
                ChatMessage.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
                ChatMessage.search_vector.op("@@")(tsquery),
            )
            .order_by(ChatMessage.seq.desc())
            .limit(limit + 1)
        )
        if user_vehicle_id is not None:
            stmt = stmt.where(Conversation.user_vehicle_id == user_vehicle_id)
        if before_seq is not None:
            stmt = stmt.where(ChatMessage.seq < before_seq)
        with Session(self._engine) as session:
            rows = session.execute(stmt).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        hits = [(row[0], row[1], row[2]) for row in rows]  # (message, title, snippet)
        next_cursor = int(hits[-1][0].seq) if has_more and hits else None
        return hits, next_cursor, has_more

    def semantic_search(
        self, conversation_id: UUID, query: str, k: int
    ) -> list[tuple[ChatMessage, float]]:
        if not self._settings.conversation_semantic_index_enabled:
            raise errors.SemanticSearchDisabled()
        results = self._vectors.similarity_search(
            CONVERSATION_MESSAGES, query, k=k, where={"conversationId": str(conversation_id)}
        )
        ids = [UUID(r.id) for r in results]
        if not ids:
            return []
        with Session(self._engine) as session:
            found = {m.id: m for m in ChatMessageRepository(session).find_in("id", ids)}
        return [(found[UUID(r.id)], r.score) for r in results if UUID(r.id) in found]

    # -- deletion ---------------------------------------------------------
    def delete_conversation(self, user_id: int, conversation_id: UUID) -> None:
        conversation = self.get_owned_conversation(user_id, conversation_id)
        vector_ids: list[str] = []
        with Session(self._engine) as session:
            if self._settings.conversation_semantic_index_enabled:
                stmt = select(ChatMessage.id).where(
                    ChatMessage.conversation_id == conversation_id,
                    ChatMessage.embedded.is_(True),
                )
                vector_ids = [str(mid) for mid in session.execute(stmt).scalars().all()]
            # cascade deletes chat_message; booking/quote.source_message_id -> NULL.
            row = session.get(Conversation, conversation.id)
            if row is not None:
                session.delete(row)
                session.commit()
        # Best-effort side cleanups (never block the delete).
        if vector_ids:
            try:
                self._vectors.delete(CONVERSATION_MESSAGES, vector_ids)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to delete vectors for conversation %s", conversation_id)
        # TODO(AI-001): delete LangGraph checkpointer thread once integrated.

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

        conversation = self.get_owned_conversation(user_id, conversation_id)
        with Session(self._engine) as session:
            vehicle = session.get(UserVehicle, conversation.user_vehicle_id)
        if vehicle is None or vehicle.link_status != VehicleLinkStatus.ACTIVE:
            raise errors.VehicleNotActive()

        await self._check_rate_limit(user_id)

        lock = self._toolkit.locks.critical_section(
            f"conversation-run:{conversation_id}",
            ttl=self._settings.chat_run_lock_ttl_seconds,
            auto_renew=True,
        )
        if not await lock.acquire(blocking=False):
            raise errors.ConversationBusy()

        try:
            async for frame in self._run_turn(
                conversation_id, client_message_id, content, trace_id, is_disconnected
            ):
                yield frame
        finally:
            try:
                await lock.release()
            except Exception:  # noqa: BLE001 — TTL will reclaim it
                logger.warning("Run lock release failed for %s", conversation_id)

    async def _run_turn(
        self,
        conversation_id: UUID,
        client_message_id: UUID,
        content: str,
        trace_id: str | None,
        is_disconnected: Callable[[], Awaitable[bool]] | None,
    ) -> AsyncIterator[SseFrame]:
        from src.infrastructure.messaging import MessageDto

        try:
            user_result = await self._messages.append(
                conversation_id,
                MessageRole.USER,
                content,
                client_message_id=client_message_id,
            )
        except ConversationNotFoundError:
            raise errors.ConversationNotFound()

        replay = self._replay_if_answered(conversation_id, user_result)
        if replay is not None:
            yield SseFrame(
                event="message.accepted",
                data={"userMessage": MessageDto.from_message(user_result.message).model_dump(mode="json"), "replayed": True},
            )
            yield SseFrame(
                event="message.completed",
                data={"message": MessageDto.from_message(replay).model_dump(mode="json")},
            )
            return

        yield SseFrame(
            event="message.accepted",
            data={"userMessage": MessageDto.from_message(user_result.message).model_dump(mode="json"), "replayed": False},
        )

        yield SseFrame(event="status", data={"stage": "retrieving"})
        citations, context = await self._retrieve(content)

        yield SseFrame(event="status", data={"stage": "generating"})
        agent_run_id = uuid4()
        pieces: list[str] = []
        try:
            async for delta in self._llm.chat_stream(self._build_prompt(conversation_id, content, context)):
                pieces.append(delta)
                yield SseFrame(event="token", data={"delta": delta})
                if is_disconnected is not None and await is_disconnected():
                    logger.info("Client disconnected mid-stream for %s; discarding turn", conversation_id)
                    return
        except LLMProviderError as exc:
            yield SseFrame(
                event="error",
                data={"code": "LLM_UNAVAILABLE", "message": "Trợ lý tạm thời không trả lời được.", "traceId": trace_id},
            )
            logger.warning("LLM error for %s: %s", conversation_id, exc)
            return

        answer = "".join(pieces).strip()
        assistant = await self._messages.append(
            conversation_id,
            MessageRole.ASSISTANT,
            answer,
            citations=citations,
            intent=None,
            agent_run_id=agent_run_id,
            trace_id=trace_id,
        )
        yield SseFrame(
            event="message.completed",
            data={"message": MessageDto.from_message(assistant.message).model_dump(mode="json")},
        )

    def _replay_if_answered(
        self, conversation_id: UUID, user_result: AppendResult
    ) -> ChatMessage | None:
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
            hits = await self._knowledge.asimilarity_search("*", query, k=_RETRIEVE_K)
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

    def _build_prompt(
        self, conversation_id: UUID, user_content: str, context: str
    ) -> list[LlmMessage]:
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
            messages.append(LlmMessage(role=msg.role.value, content=msg.content))
        if context:
            messages.append(
                LlmMessage(role="system", content=f"Tài liệu chính hãng liên quan:\n{context}")
            )
        return messages

    # -- rate limit -------------------------------------------------------
    async def _check_rate_limit(self, user_id: int) -> None:
        now = time.time()
        await self._enforce_window(
            f"chat:rl:{user_id}:min", now, 60, self._settings.chat_rate_limit_per_minute
        )
        await self._enforce_window(
            f"chat:rl:{user_id}:day", now, 86400, self._settings.chat_rate_limit_per_day
        )

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
