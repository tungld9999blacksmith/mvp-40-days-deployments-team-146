"""The async tool must retain fallback and source identity through LangGraph."""
from unittest.mock import AsyncMock, Mock

import pytest

from src.agents.tools.RAG.query.rag_tool import build_rag_tools
from src.agents.tools.RAG.query.schemas import CitationItem, RAGResponse


@pytest.mark.asyncio
async def test_async_tool_message_preserves_evidence_and_uncertainty():
    response = RAGResponse(
        answer="Chưa xác minh hiệu lực nguồn [Tài liệu 1].",
        citations=[CitationItem(document_id="doc-vf8", chunk_id="chunk-charging", title="VF8 manual")],
        confidence="low",
        fallback_required=True,
        metadata={"source_rule_verified": False},
    )
    pipeline = Mock(aquery=AsyncMock(return_value=response))
    tool = build_rag_tools(lambda: pipeline)[0]
    message = await tool.ainvoke({
        "type": "tool_call", "id": "rag-call", "name": tool.name,
        "args": {"query": "Quy trình sạc VF8?", "model": "VF8"},
    })
    assert message.tool_call_id == "rag-call"
    assert message.artifact["type"] == "RAG_EVIDENCE"
    assert message.artifact["citations"][0]["chunk_id"] == "chunk-charging"
    assert message.artifact["fallback_required"] is True
    assert message.artifact["confidence"] == "low"
    assert message.artifact["metadata"]["source_rule_verified"] is False
    pipeline.query_sync.assert_not_called()
