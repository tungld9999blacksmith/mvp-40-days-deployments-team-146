"""Extractive committed-user summaries: questions remain quotes, never facts."""

import json
import logging
import time
from datetime import UTC, datetime
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from sqlmodel import Session, select

from src.agents.memory_context import count_text
from src.common.core.conversation import ChatMessage, Conversation, MessageRole
from src.common.core.conversation.memory import ConversationSummary
from src.infrastructure.vectorstore.record_policy import mask_pii

logger = logging.getLogger(__name__)


class SummaryService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings

    def history(self, conversation_id: UUID, exclude_seq: int | None = None):
        with Session(self.engine) as db:
            summary = db.get(ConversationSummary, conversation_id)
            use_summary = summary is not None and (summary.compacted or self.settings.agent_memory_context_mode == "on")
            cursor = summary.covered_until_seq if use_summary else 0
            stmt = select(ChatMessage).where(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
                ChatMessage.seq > cursor,
            )
            if exclude_seq is not None:
                stmt = stmt.where(ChatMessage.seq < exclude_seq)
            rows = db.exec(stmt.order_by(ChatMessage.seq)).all()
            if not use_summary and self.settings.agent_memory_context_mode in ("off", "shadow"):
                rows = rows[-20:]
            messages = [
                (HumanMessage if row.role == MessageRole.USER else AIMessage)(content=row.content, id=str(row.id))
                for row in rows
            ]
            return messages, dict(summary.summary_json) if use_summary else {}

    def mark_compacted(self, conversation_id, version):
        with Session(self.engine) as db:
            row = db.exec(
                select(ConversationSummary)
                .where(ConversationSummary.conversation_id == conversation_id)
                .with_for_update()
            ).first()
            if row is not None and row.version == version:
                row.compacted = True
                db.add(row)
                db.commit()

    def update(self, conversation_id: UUID, *, force=False):
        started = time.monotonic()
        with Session(self.engine) as db:
            conversation = db.exec(
                select(Conversation).where(Conversation.id == conversation_id).with_for_update()
            ).first()
            if conversation is None:
                return None
            current = db.get(ConversationSummary, conversation_id)
            cursor = current.covered_until_seq if current else 0
            rows = db.exec(
                select(ChatMessage)
                .where(
                    ChatMessage.conversation_id == conversation_id,
                    ChatMessage.seq > cursor,
                    ChatMessage.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
                )
                .order_by(ChatMessage.seq)
            ).all()
            # Only completed turns are eligible; keep N recent complete user turns.
            user_indices = [i for i, row in enumerate(rows) if row.role == MessageRole.USER]
            if len(user_indices) <= self.settings.agent_memory_recent_turns:
                return None
            boundary = user_indices[-self.settings.agent_memory_recent_turns]
            older = rows[:boundary]
            if not older or older[-1].role != MessageRole.ASSISTANT:
                return None
            input_size = sum(count_text(row.content) + 24 for row in rows)
            from src.agents.prompts import format_system_prompt
            from src.agents.tools import CUSTOMER_AGENT_TOOLS

            input_size += count_text(format_system_prompt({}))
            input_size += sum(
                count_text(
                    json.dumps({"name": t.name, "description": t.description, "args": t.args}, ensure_ascii=False)
                )
                + 24
                for t in CUSTOMER_AGENT_TOOLS
            )
            if (
                not force
                and input_size
                < self.settings.agent_memory_input_token_budget * self.settings.agent_memory_summary_trigger_ratio
            ):
                return None
            quotes = list((current.summary_json if current else {}).get("user_quotes", []))
            # Never summarize the model's assertions as facts. Preserve exact user
            # wording, question marks and source IDs; dynamic data must be re-read.
            for row in older:
                if row.role == MessageRole.USER:
                    quotes.append(
                        {"message_id": str(row.id), "text": mask_pii(row.content)[:400], "kind": "user_quote"}
                    )

            # Keep salient requests/preferences and recent quotes in a bounded summary.
            def priority(quote):
                text = quote["text"].lower()
                weights = {"hãy nhớ": 8, "remember": 8, "prefer": 4, "xưởng": 4, "thứ": 4, "muốn": 2, "chọn": 2}
                return sum(weight for term, weight in weights.items() if term in text)

            chosen = []
            for quote in sorted(enumerate(quotes), key=lambda item: (priority(item[1]), item[0]), reverse=True):
                candidate = sorted(chosen + [quote], key=lambda item: item[0])
                payload = {
                    "user_quotes": [q for _, q in candidate],
                    "notice": "Historical user statements, not verified current business facts",
                }
                if count_text(json.dumps(payload, ensure_ascii=False)) <= self.settings.agent_memory_summary_max_tokens:
                    chosen = candidate
            payload = {
                "user_quotes": [q for _, q in chosen],
                "notice": "Historical user statements, not verified current business facts",
            }
            if current is None:
                current = ConversationSummary(conversation_id=conversation_id)
            else:
                current.version += 1
            current.summary_json = payload
            current.source_message_ids = [q["message_id"] for _, q in chosen]
            current.covered_until_seq = older[-1].seq
            current.updated_at = datetime.now(UTC)
            db.add(current)
            db.commit()
            logger.info(
                "agent_memory_summary conversation_id=%s version=%s quote_count=%s duration_ms=%s",
                conversation_id,
                current.version,
                len(chosen),
                round((time.monotonic() - started) * 1000),
            )
            return {
                "summary": payload,
                "covered_until_seq": current.covered_until_seq,
                "source_ids": [str(r.id) for r in older],
                "version": current.version,
            }
