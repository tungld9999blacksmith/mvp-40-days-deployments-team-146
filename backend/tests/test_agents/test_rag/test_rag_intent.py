import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
from src.agents.tools.RAG.query.rag_pipeline import RAGPipeline
from src.agents.tools.RAG.query.rag_tool import build_rag_tools
from src.agents.tools.RAG.query.schemas import CitationItem, QueryAnalysis, RAGResponse
from src.infrastructure.llm.base import LLMResponse


@pytest.mark.parametrize(
    ("tool_index", "arguments", "category"),
    [
        (0, {"query": "Service cost", "model": "VF5", "category": "pricing"}, "pricing"),
        (1, {"model": "VF5", "km": 12000}, "maintenance"),
        (2, {"model": "VF5", "component": "battery"}, "warranty"),
    ],
)
def test_tool_intent_reaches_pipeline(tool_index, arguments, category):
    pipeline = Mock()
    pipeline.query_sync.return_value = SimpleNamespace(answer="Sourced answer", citations=[])
    result = build_rag_tools(lambda: pipeline)[tool_index].invoke(arguments)
    assert result == "Sourced answer"
    assert pipeline.query_sync.call_args.kwargs["category"] == category
    assert pipeline.query_sync.call_args.kwargs["vehicle_context"].model == "VF5"


@pytest.mark.asyncio
async def test_explicit_category_overrides_rewriter_without_changing_model():
    analysis = QueryAnalysis(
        original_query="Service cost", rewritten_query="Service cost VF5",
        model="VF5", category="battery",
    )
    rewriter = Mock(analyze=AsyncMock(return_value=analysis))
    retriever = Mock()
    retriever.retrieve.return_value = []
    retriever.select_context.return_value = []
    retriever.expand_neighbors.return_value = []
    reranker = Mock()
    reranker.rerank.return_value = []
    generator = Mock(generate=AsyncMock(return_value=RAGResponse(
        answer="No sources", confidence="low", fallback_required=True,
    )))
    pipeline = RAGPipeline(
        rewriter=rewriter, hybrid_retriever=retriever,
        reranker=reranker, generator=generator,
    )
    await pipeline.query("Service cost", category=" Pricing ", expand_neighbors=False)
    used = retriever.retrieve.call_args.kwargs["analysis"]
    assert used.category == "pricing"
    assert used.model == "VF5"
    retriever.expand_neighbors.assert_not_called()


@pytest.mark.asyncio
async def test_category_does_not_override_out_of_scope_rejection():
    analysis = QueryAnalysis(
        original_query="Weather", rewritten_query="Weather", is_out_of_scope=True,
    )
    retriever = Mock()
    pipeline = RAGPipeline(
        rewriter=Mock(analyze=AsyncMock(return_value=analysis)),
        hybrid_retriever=retriever,
        reranker=Mock(), generator=Mock(),
    )
    response = await pipeline.query("Weather", category="maintenance")
    assert response.fallback_required
    assert response.metadata["reason"] == "out_of_scope"
    retriever.retrieve.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("references", [
    "[Tài liệu 2, Tài liệu 3]", "[Tài liệu 2, 3]", "[Tài liệu 2 và Tài liệu 3]",
])
async def test_grouped_citations_are_resolved_and_renumbered(references):
    provider = Mock(chat=AsyncMock(return_value=LLMResponse(
        text=json.dumps({
            "answer": f"Supported claim {references}. Unused [Tài liệu 1].",
            "confidence": "medium", "fallback_required": False,
            "cited_doc_indexes": [2, 3],
        }), model="test",
    )))
    citations = [
        CitationItem(document_id=f"doc{i}", title=f"Doc {i}", chunk_id=f"c{i}")
        for i in range(1, 4)
    ]
    result = await GroundedAnswerGenerator(provider).generate(
        QueryAnalysis(original_query="Question", rewritten_query="Question"),
        "Evidence", citations,
    )
    assert [c.document_id for c in result.citations] == ["doc2", "doc3"]
    assert "Supported claim [Tài liệu 1] [Tài liệu 2]." in result.answer
    assert "Unused [Tài liệu" not in result.answer
    assert not result.fallback_required


@pytest.mark.asyncio
async def test_fallback_answer_removes_undeclared_citation_tags():
    provider = Mock(chat=AsyncMock(return_value=LLMResponse(
        text=json.dumps({
            "answer": "Missing evidence [Tài liệu 99].",
            "confidence": "low", "fallback_required": True,
            "cited_doc_indexes": [99],
        }), model="test",
    )))
    result = await GroundedAnswerGenerator(provider).generate(
        QueryAnalysis(original_query="Question", rewritten_query="Question"),
        "Evidence", [CitationItem(document_id="doc", title="Doc", chunk_id="c")],
    )
    assert not result.citations
    assert "[Tài liệu" not in result.answer
    assert result.fallback_required


def _pipeline(answer: RAGResponse, analyze=None) -> tuple[RAGPipeline, Mock]:
    analysis = QueryAnalysis(original_query="Question", rewritten_query="Question")
    retriever = Mock()
    retriever.retrieve.return_value = []
    retriever.select_context.return_value = []
    retriever.expand_neighbors.return_value = []
    generator = Mock(generate=AsyncMock(return_value=answer))
    pipeline = RAGPipeline(
        rewriter=Mock(analyze=analyze or AsyncMock(return_value=analysis)),
        hybrid_retriever=retriever,
        reranker=Mock(rerank=Mock(return_value=[])),
        generator=generator,
    )
    return pipeline, generator


def test_repeated_sync_queries_reuse_one_event_loop():
    """LLM clients bind to the loop they first ran on; a fresh loop per query broke every later query."""
    loops = []
    analysis = QueryAnalysis(original_query="Question", rewritten_query="Question")

    async def loop_bound_analyze(**kwargs):
        loop = asyncio.get_running_loop()
        if loops and loops[0] is not loop:
            raise RuntimeError("Event loop is closed")
        loops.append(loop)
        return analysis

    pipeline, _ = _pipeline(RAGResponse(answer="ok", confidence="low"), analyze=loop_bound_analyze)
    for question in ("first", "second", "third"):
        assert pipeline.query_sync(question).answer == "ok"
    assert len(loops) == 3


@pytest.mark.asyncio
async def test_good_answers_are_cached_and_degraded_ones_are_not():
    pipeline, generator = _pipeline(RAGResponse(answer="Sourced", confidence="high"))
    first = await pipeline.query("Chính sách  bảo hành pin?", category="warranty")
    first.answer = "mutated by a caller"
    again = await pipeline.query("chính sách bảo hành PIN?", category="Warranty")
    assert again.answer == "Sourced"
    assert generator.generate.await_count == 1
    await pipeline.query("chính sách bảo hành pin?", category="pricing")  # another intent
    assert generator.generate.await_count == 2

    degraded, generator = _pipeline(RAGResponse(answer="No sources", confidence="low", fallback_required=True))
    await degraded.query("Question")
    await degraded.query("Question")
    assert generator.generate.await_count == 2


@pytest.mark.asyncio
async def test_agent_awaits_the_async_tool_variant():
    pipeline = Mock()
    pipeline.aquery = AsyncMock(return_value=SimpleNamespace(answer="Sourced answer", citations=[]))
    tool = build_rag_tools(lambda: pipeline)[0]
    result = await tool.ainvoke({"query": "Service cost", "model": "vf5", "category": "pricing"})
    assert result == "Sourced answer"
    assert pipeline.aquery.await_args.kwargs["category"] == "pricing"
    assert pipeline.aquery.await_args.kwargs["vehicle_context"].model == "VF5"
    pipeline.query_sync.assert_not_called()
