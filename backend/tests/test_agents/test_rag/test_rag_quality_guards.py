from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "src")]

from src.agents.tools.RAG.ingestion import DocumentChunker, IngestionEngine, TextCleaner
from src.agents.tools.RAG.query.bm25_searcher import BM25Searcher
from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
from src.agents.tools.RAG.query.hybrid import HybridRetriever
from src.agents.tools.RAG.query.reranker import HeuristicReranker
from src.agents.tools.RAG.query.rewriter import QueryRewriter
from src.agents.tools.RAG.query.schemas import CitationItem, QueryAnalysis, RetrievalCandidate

EVAL_DIR = Path(__file__).resolve().parent / "evaluation"
sys.path.insert(0, str(EVAL_DIR))
from metrics import (  # noqa: E402
    QueryResult,
    compute_answer_relevancy,
    compute_citation_correctness,
    compute_context_precision,
    compute_context_recall,
)


def candidate(
    chunk_id: str,
    doc_id: str,
    content: str,
    *,
    model: str = "ALL",
    category: str = "maintenance",
    section: str = "Mục",
    score: float = 0.8,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk_id,
        doc_id=doc_id,
        content=content,
        metadata={
            "doc_id": doc_id,
            "model": model,
            "category": category,
            "section_header": section,
        },
        rerank_score=score,
    )


class ContextSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analysis = QueryAnalysis(
            original_query="VF7 bảo dưỡng 15.000 km gồm những gì?",
            rewritten_query="VF7 bảo dưỡng 15.000 km gồm những gì?",
            model="VF7",
            category="maintenance",
        )

    def test_select_context_filters_wrong_model_and_diversifies_documents(self) -> None:
        retriever = HybridRetriever(vector_store=object())
        candidates = [
            candidate("a_chk_0001", "a", "VF7 bảo dưỡng 15.000 km", model="VF7", score=0.9),
            candidate("a_chk_0002", "a", "VF7 kiểm tra tại 15.000 km", model="VF7", score=0.89),
            candidate("b_chk_0001", "b", "Lịch bảo dưỡng VF7 ở 15.000 km", score=0.85),
            candidate("c_chk_0001", "c", "VF8 bảo dưỡng 15.000 km", model="VF8", score=0.99),
        ]

        selected = retriever.select_context(candidates, self.analysis, top_k=3)

        self.assertEqual([item.doc_id for item in selected], ["a", "b"])

    def test_select_context_accepts_spaced_model_alias(self) -> None:
        analysis = QueryAnalysis(
            original_query="Bảo dưỡng xe VF MPV 7",
            rewritten_query="Bảo dưỡng xe VF MPV 7",
            model="VF MPV 7",
            category="maintenance",
        )
        candidates = [
            candidate("mpv_chk_0001", "mpv", "Bảo dưỡng VF MPV 7", model="VFMPV7"),
            candidate("vf8_chk_0001", "vf8", "Bảo dưỡng VF8", model="VF8"),
        ]

        selected = HybridRetriever(vector_store=object()).select_context(
            candidates, analysis, top_k=2
        )

        self.assertEqual([item.doc_id for item in selected], ["mpv"])

    def test_bm25_model_filter_accepts_spaced_model_alias(self) -> None:
        searcher = BM25Searcher()
        searcher.fit([
            {
                "chunk_id": "mpv_chk_0001",
                "doc_id": "mpv",
                "content": "VF MPV 7 maintenance service schedule",
                "metadata": {"model": "VFMPV7", "category": "maintenance"},
            },
            {
                "chunk_id": "vf8_chk_0001",
                "doc_id": "vf8",
                "content": "VF8 maintenance service schedule",
                "metadata": {"model": "VF8", "category": "maintenance"},
            },
        ])

        results = searcher.search(
            query="maintenance service schedule",
            model="VF MPV 7",
            category="maintenance",
        )

        self.assertEqual([item.doc_id for item in results], ["mpv"])

    def test_battery_context_can_keep_two_sections_from_same_faq(self) -> None:
        analysis = QueryAnalysis(
            original_query="Cứu hộ pin VinFast hoạt động và có giá bao nhiêu?",
            rewritten_query="Cứu hộ pin VinFast hoạt động và có giá bao nhiêu?",
            model="ALL",
            category="battery",
        )
        candidates = [
            candidate("faq_chk_0001", "faq", "Quy trình cứu hộ pin", category="battery", section="Quy trình", score=0.9),
            candidate("faq_chk_0002", "faq", "Giá cứu hộ pin 50.000 VNĐ", category="battery", section="Chi phí", score=0.85),
            candidate("other_chk_0001", "other", "Pin ô tô", category="battery", score=0.5),
        ]

        selected = HybridRetriever(vector_store=object()).select_context(
            candidates, analysis, top_k=3
        )

        self.assertEqual([item.chunk_id for item in selected[:2]], ["faq_chk_0001", "faq_chk_0002"])

    def test_neighbor_is_merged_only_within_same_section(self) -> None:
        searcher = BM25Searcher()
        searcher.fit([
            candidate("a_chk_0001", "a", "phần trước", section="Bảng").model_dump(),
            candidate("a_chk_0002", "a", "phần chính", section="Bảng").model_dump(),
            candidate("a_chk_0003", "a", "phần khác", section="Phụ lục").model_dump(),
        ])
        retriever = HybridRetriever(vector_store=object(), bm25_searcher=searcher)

        expanded = retriever.expand_neighbors([
            candidate("a_chk_0002", "a", "phần chính", section="Bảng")
        ])

        self.assertEqual(len(expanded), 1)
        self.assertIn("phần trước", expanded[0].content)
        self.assertNotIn("phần khác", expanded[0].content)
        self.assertEqual(expanded[0].metadata["expanded_chunk_ids"], ["a_chk_0001", "a_chk_0002"])

    def test_official_source_url_survives_ingestion_and_chunking(self) -> None:
        path = ROOT / "data/knowledge/raw/pricing_tram_sac_ALL.md"
        document = IngestionEngine().ingest_file(path)
        chunks = DocumentChunker().chunk_document(TextCleaner().clean(document))
        self.assertTrue(chunks)
        self.assertEqual(
            chunks[0].metadata["source_url"],
            "https://vinfastauto.com/vn_vi/dich-vu-pin-oto-dien",
        )

    def test_pricing_document_keeps_category_for_charger_sections(self) -> None:
        path = ROOT / "data/knowledge/raw/pricing_thiet_bi_sac_ALL.md"
        document = IngestionEngine().ingest_file(path)
        chunks = DocumentChunker().chunk_document(TextCleaner().clean(document))

        self.assertTrue(chunks)
        self.assertEqual({chunk.metadata["category"] for chunk in chunks}, {"pricing"})

    def test_exact_price_query_limits_context_to_one_document(self) -> None:
        analysis = QueryAnalysis(
            original_query="Bộ sạc AC 11 kW giá bao nhiêu?",
            rewritten_query="Bộ sạc AC 11 kW giá bao nhiêu?",
            model="ALL",
            category="pricing",
        )
        candidates = [
            candidate(f"p{i}_chk_0001", f"p{i}", "Bộ sạc AC 11 kW", category="pricing", score=0.9 - i * 0.05)
            for i in range(4)
        ]

        selected = HybridRetriever(vector_store=object()).select_context(
            candidates, analysis, top_k=5
        )

        self.assertEqual(len(selected), 1)

    def test_pricing_intent_prioritizes_official_pricing_document(self) -> None:
        candidates = [
            candidate(
                "faq_chk_0001",
                "faq_baoduong_baohanh_ALL",
                "Bộ sạc AC 11 kW VinFast có giá bao nhiêu",
                category="pricing",
            ),
            candidate(
                "pricing_chk_0001",
                "pricing_thiet_bi_sac_ALL",
                "Bộ sạc treo tường AC 11 kW có giá 11.781.818 VNĐ",
                category="pricing",
            ),
        ]

        ranked = HeuristicReranker().rerank(
            "Bộ sạc AC 11 kW giá bao nhiêu?", candidates, top_k=2
        )

        self.assertEqual(ranked[0].doc_id, "pricing_thiet_bi_sac_ALL")

    def test_rescue_price_query_keeps_the_official_faq(self) -> None:
        candidates = [
            candidate(
                "faq_chk_0001",
                "faq_baoduong_baohanh_ALL",
                "Dịch vụ cứu hộ pin có chi phí 50.000 VNĐ/lần",
                category="pricing",
            ),
            candidate(
                "pricing_chk_0001",
                "pricing_tram_sac_ALL",
                "Bảng giá sạc tại trạm",
                category="pricing",
            ),
        ]

        ranked = HeuristicReranker().rerank(
            "Dịch vụ cứu hộ pin có mất tiền không?", candidates, top_k=2
        )

        self.assertEqual(ranked[0].doc_id, "faq_baoduong_baohanh_ALL")

    def test_booking_maintenance_query_is_classified_as_procedure(self) -> None:
        analysis = QueryRewriter(llm_provider=None)._heuristic_fallback(
            "Đặt lịch bảo dưỡng xe VinFast qua app như thế nào?"
        )

        self.assertEqual(analysis.category, "procedure")

    def test_query_rewriter_disables_llm_after_quota_error(self) -> None:
        class QuotaLimitedProvider:
            calls = 0

            async def chat(self, **kwargs):
                self.calls += 1
                raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")

        provider = QuotaLimitedProvider()
        rewriter = QueryRewriter(llm_provider=provider)

        first = asyncio.run(rewriter.analyze("Bảo dưỡng xe VF8 mốc 15.000 km"))
        second = asyncio.run(rewriter.analyze("Chính sách bảo hành pin VF8"))

        self.assertEqual(provider.calls, 1)
        self.assertEqual(first.category, "maintenance")
        self.assertEqual(second.category, "warranty")


class CitationTests(unittest.TestCase):
    def test_only_declared_and_rendered_citations_are_returned(self) -> None:
        citations = [
            CitationItem(document_id=f"doc{i}", title=f"Doc {i}", chunk_id=f"c{i}")
            for i in range(1, 4)
        ]
        resolved, indexes = GroundedAnswerGenerator()._resolve_citations(
            answer="Thông tin A [Tài liệu 2]. Thông tin B [Tài liệu 3].",
            cited_indexes=[1, 2, 99],
            citations=citations,
        )
        self.assertEqual(indexes, [2])
        self.assertEqual([item.document_id for item in resolved], ["doc2"])

    def test_offline_response_only_returns_citations_rendered_in_answer(self) -> None:
        citations = [
            CitationItem(document_id=f"doc{i}", title=f"Doc {i}", chunk_id=f"c{i}")
            for i in range(1, 5)
        ]

        response = GroundedAnswerGenerator()._build_offline_response(citations)

        self.assertEqual(
            [citation.document_id for citation in response.citations],
            ["doc1", "doc2", "doc3"],
        )
        self.assertNotIn("[Tài liệu 4]", response.answer)


class MetricTests(unittest.TestCase):
    def test_metrics_use_exact_normalized_document_ids(self) -> None:
        result = QueryResult(
            id="x",
            query="Giá sạc VinFast bao nhiêu?",
            model=None,
            category="pricing",
            retrieved_doc_ids=["pricing_ALL_chk_0001", "pricing_old_ALL"],
            relevant_doc_ids=["pricing_ALL"],
            actual_answer="Giá sạc VinFast là 3.858 đồng mỗi kWh.",
            cited_doc_ids=["pricing_ALL_chk_0001"],
        )
        self.assertEqual(compute_context_precision(result), 0.5)
        self.assertEqual(compute_context_recall(result), 1.0)
        self.assertEqual(compute_citation_correctness(result), 1.0)
        self.assertGreater(compute_answer_relevancy(result) or 0.0, 0.5)

    def test_answer_metrics_are_not_fabricated_without_generated_answer(self) -> None:
        result = QueryResult(id="x", query="pin", model=None, category="battery")
        self.assertIsNone(compute_answer_relevancy(result))
        self.assertIsNone(compute_citation_correctness(result))


if __name__ == "__main__":
    unittest.main()
