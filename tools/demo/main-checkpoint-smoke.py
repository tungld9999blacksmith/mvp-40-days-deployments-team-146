"""Real PostgreSQL checkpoint reopen test, fake model and a unique test thread.

Initializes checkpoint tables if needed; deletes only its own test thread.
No user/business data, LLM requests or email are used.
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from langchain_core.messages import AIMessage, HumanMessage
from src.agents.checkpoint import checkpoint_lifespan
from src.agents.graph import build_graph
from src.agents.orchestrator import AgentOrchestrator
from src.config import get_settings
from tests.test_agents.test_checkpoint_history import FakeChat


async def run():
    cfg = get_settings().model_copy(update={"agent_checkpoint_mode": "postgres"})
    cid = uuid4()
    artifacts = ROOT / ".cache/main-real-services-email"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "checkpoint-smoke-thread.txt").write_text(str(cid), encoding="utf-8")
    history = []
    try:
        async with checkpoint_lifespan(cfg) as saver:
            graph = build_graph(FakeChat(responses=["answer-1", "answer-2"]), [], saver)
            runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
            for n in range(2):
                mid, aid = uuid4(), uuid4()
                result = [
                    e
                    async for e in runner.run_agent_turn(
                        cid,
                        1,
                        message=f"question-{n}",
                        history_messages=history,
                        source_message_id=mid,
                    )
                ]
                content = result[-1]["message_data"]["content"]
                await runner.record_committed_answer(cid, aid, content)
                history += [
                    HumanMessage(content=f"question-{n}", id=str(mid)),
                    AIMessage(content=content, id=str(aid)),
                ]
        # Reopen pool and saver, just as a separate API process would.
        async with checkpoint_lifespan(cfg) as reopened:
            graph = build_graph(FakeChat(responses=["answer-3"]), [], reopened)
            runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
            mid, aid = uuid4(), uuid4()
            result = [
                e
                async for e in runner.run_agent_turn(
                    cid,
                    1,
                    message="question-2",
                    history_messages=history,
                    source_message_id=mid,
                )
            ]
            content = result[-1]["message_data"]["content"]
            assert content == "answer-3"
            await runner.record_committed_answer(cid, aid, content)
            messages = (
                await graph.aget_state({"configurable": {"thread_id": str(cid)}})
            ).values["messages"]
            assert len(messages) == 6 and len({m.id for m in messages}) == 6
            print(
                json.dumps(
                    {
                        "postgres_checkpoint": True,
                        "reopened_pool": True,
                        "three_turns": True,
                        "messages": len(messages),
                        "unique_ids": True,
                    }
                )
            )
    finally:
        async with checkpoint_lifespan(cfg) as saver:
            await saver.adelete_thread(str(cid))


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(run())
