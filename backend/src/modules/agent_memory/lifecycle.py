"""Conversation deletion outbox and inactivity retention, with the chat run lock."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, update
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from src.common.core.conversation import ChatMessage, Conversation
from src.common.core.conversation.memory import AgentMemorySource, AgentUserMemory, ConversationSummary, MemoryCleanup
from src.modules.conversation.errors import ConversationBusy, ConversationNotFound

logger = logging.getLogger(__name__)


class ConversationMemoryLifecycleService:
    def __init__(self, engine, settings, run_lock, saver, vectors=None):
        self.engine, self.settings, self.run_lock = engine, settings, run_lock
        self.saver, self.vectors = saver, vectors

    async def delete(self, user_id: int, conversation_id: UUID) -> None:
        async with self.run_lock(conversation_id):
            await run_in_threadpool(self._delete, user_id, conversation_id)
            await self.cleanup_one(conversation_id)

    def _delete(self, user_id: int, conversation_id: UUID, cutoff=None) -> bool:
        with Session(self.engine) as db:
            conversation = db.exec(
                select(Conversation).where(Conversation.id == conversation_id).with_for_update()
            ).first()
            if conversation is None or conversation.user_id != user_id:
                raise ConversationNotFound()
            if cutoff is not None and _utc(conversation.last_message_at) >= cutoff:
                return False
            messages = db.exec(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)).all()
            # Include unflagged messages: indexing may have written a vector before
            # its DB transaction failed. Deleting a nonexistent vector is harmless.
            ids = [str(m.id) for m in messages]
            task = db.get(MemoryCleanup, conversation_id)
            if task is None:
                db.add(MemoryCleanup(conversation_id=conversation_id, vector_ids=ids))
            else:
                task.vector_ids = sorted(set(task.vector_ids + ids))
                db.add(task)
            # Explicit statements also support SQLite test engines without FK cascades.
            memory_ids = select(AgentMemorySource.memory_id).where(
                AgentMemorySource.source_conversation_id == conversation_id
            )
            db.exec(delete(AgentUserMemory).where(AgentUserMemory.id.in_(memory_ids)))
            db.exec(delete(AgentMemorySource).where(AgentMemorySource.source_conversation_id == conversation_id))
            db.exec(delete(ConversationSummary).where(ConversationSummary.conversation_id == conversation_id))
            db.delete(conversation)
            db.commit()
            return True

    async def cleanup_one(self, conversation_id: UUID) -> bool:
        def load():
            with Session(self.engine) as db:
                task = db.get(MemoryCleanup, conversation_id)
                return list(task.vector_ids) if task is not None else None

        ids = await run_in_threadpool(load)
        if ids is None:
            return True
        try:
            if self.saver is None:
                raise RuntimeError("Checkpoint saver is not available")
            await asyncio.wait_for(self.saver.adelete_thread(str(conversation_id)), 10)
            if ids:
                from src.infrastructure.vectorstore import CONVERSATION_MESSAGES

                if self.vectors is None:
                    raise RuntimeError("Vector adapter is not available")
                await asyncio.wait_for(run_in_threadpool(self.vectors().delete, CONVERSATION_MESSAGES, ids), 10)
        except Exception as exc:
            error_type = type(exc).__name__

            def failed():
                with Session(self.engine) as db:
                    task = db.get(MemoryCleanup, conversation_id)
                    if task:
                        task.attempts += 1
                        task.last_attempt_at = datetime.now(UTC)
                        task.last_error = error_type
                        db.add(task)
                        db.commit()

            await run_in_threadpool(failed)
            logger.warning(
                "memory_cleanup_pending conversation_id=%s error_type=%s", conversation_id, type(exc).__name__
            )
            return False

        def complete():
            with Session(self.engine) as db:
                task = db.get(MemoryCleanup, conversation_id)
                if task:
                    db.delete(task)
                    db.commit()

        await run_in_threadpool(complete)
        return True

    async def cleanup_pending(self) -> dict:
        def expire_preferences():
            with Session(self.engine) as db:
                result = db.exec(
                    update(AgentUserMemory)
                    .where(AgentUserMemory.status == "active", AgentUserMemory.expires_at <= datetime.now(UTC))
                    .values(status="expired")
                )
                db.commit()
                return result.rowcount

        expired = await run_in_threadpool(expire_preferences)
        def load():
            with Session(self.engine) as db:
                return db.exec(
                    select(MemoryCleanup).order_by(MemoryCleanup.created_at).limit(self.settings.chat_purge_batch)
                ).all()

        tasks = await run_in_threadpool(load)
        done = 0
        busy = 0
        for task in tasks:
            try:
                # Cascading account/vehicle deletion can enqueue work while a
                # turn still owns the thread. Wait until it can no longer write
                # checkpoints before draining the durable outbox.
                async with self.run_lock(task.conversation_id):
                    done += await self.cleanup_one(task.conversation_id)
            except ConversationBusy:
                busy += 1
        oldest = max((datetime.now(UTC) - _utc(t.created_at)).total_seconds() for t in tasks) if tasks else 0
        return {
            "selected": len(tasks),
            "completed": done,
            "pending": len(tasks) - done,
            "busy": busy,
            "expired_preferences": expired,
            "oldest_selected_seconds": oldest,
        }

    async def purge(self, *, dry_run: bool = True) -> dict:
        cutoff = datetime.now(UTC) - timedelta(days=self.settings.chat_retention_days)

        def load():
            with Session(self.engine) as db:
                return db.exec(
                    select(Conversation)
                    .where(Conversation.last_message_at < cutoff)
                    .order_by(Conversation.last_message_at)
                    .limit(self.settings.chat_purge_batch)
                ).all()

        rows = await run_in_threadpool(load)
        result = {"dry_run": dry_run, "selected_ids": [str(c.id) for c in rows], "deleted": 0, "busy": 0}
        if dry_run:
            return result
        for conversation in rows:
            try:
                async with self.run_lock(conversation.id):
                    deleted = await run_in_threadpool(self._delete, conversation.user_id, conversation.id, cutoff)
                    if deleted:
                        result["deleted"] += 1
                        await self.cleanup_one(conversation.id)
            except ConversationBusy:
                result["busy"] += 1
            except ConversationNotFound:
                pass
        logger.info("memory_retention deleted=%s busy=%s", result["deleted"], result["busy"])
        return result


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
