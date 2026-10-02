from __future__ import annotations

import asyncio
import logging
import time

from .citation_builder import CitationBuilder
from .generator import GroundedAnswerGenerator
from .hybrid import HybridRetriever
from .reranker import RerankerService
from .rewriter import QueryRewriter
from .schemas import RAGResponse, UserVehicleContext

logger = logging.getLogger(__name__)


class RAGPipeline:
    """Orchestrator kết nối trọn vẹn 6 bước của Advanced RAG Pipeline:

    Query -> Rewriter -> Metadata Filter + Hybrid Retrieval -> Rerank Top-K -> Citation Packaging -> Grounded LLM Response.
    """

    def __init__(
        self,
        rewriter: QueryRewriter | None = None,
        hybrid_retriever: HybridRetriever | None = None,
        reranker: RerankerService | None = None,
        citation_builder: CitationBuilder | None = None,
        generator: GroundedAnswerGenerator | None = None,
    ) -> None:
        self.rewriter = rewriter or QueryRewriter()
        self.hybrid_retriever = hybrid_retriever or HybridRetriever()
        self.reranker = reranker or RerankerService()
        self.citation_builder = citation_builder or CitationBuilder()
        self.generator = generator or GroundedAnswerGenerator()

    async def query(
        self,
        query: str,
        vehicle_context: UserVehicleContext | None = None,
        top_k: int = 4,
    ) -> RAGResponse:
        """Xử lý truy vấn end-to-end theo luồng RAG nâng cao."""
        start_time = time.time()
        logger.info(f"Bắt đầu xử lý câu hỏi: '{query}'")

        # BƯỚC 1: Viết lại query & Trích xuất Metadata Filter bằng LLM
        query_analysis = await self.rewriter.analyze(
            query=query,
            vehicle_context=vehicle_context,
        )
        logger.debug(
            f"Query analysis: rewritten='{query_analysis.rewritten_query}', "
            f"model='{query_analysis.model}', category='{query_analysis.category}'"
        )

        # Nếu câu hỏi hoàn toàn ngoài phạm vi, trả về luôn
        if query_analysis.is_out_of_scope:
            return RAGResponse(
                answer="Xin lỗi, tôi là trợ lý chuyên biệt về dịch vụ hậu mãi và bảo dưỡng xe điện VinFast. Câu hỏi này nằm ngoài phạm vi hỗ trợ.",
                citations=[],
                confidence="low",
                fallback_required=True,
                metadata={
                    "latency_ms": round((time.time() - start_time) * 1000, 2),
                    "reason": "out_of_scope",
                },
            )

        # BƯỚC 2: Metadata Filter & Hybrid Retrieval (Dense Qdrant + Sparse BM25 + RRF)
        fused_candidates = self.hybrid_retriever.retrieve(
            analysis=query_analysis,
            top_candidates=20,
        )
        logger.debug(f"Hybrid retrieval thu được: {len(fused_candidates)} candidates")

        # BƯỚC 3: Cross-Encoder Reranking Top-K
        reranked_chunks = self.reranker.rerank(
            query=query_analysis.rewritten_query,
            candidates=fused_candidates,
            top_k=max(top_k * 3, top_k),
        )
        reranked_chunks = self.hybrid_retriever.select_context(
            candidates=reranked_chunks,
            analysis=query_analysis,
            top_k=top_k,
        )
        reranked_chunks = self.hybrid_retriever.expand_neighbors(reranked_chunks)
        logger.debug(f"Sau Rerank còn lại: {len(reranked_chunks)} chunks")

        # BƯỚC 4: Đóng gói Context & Trích dẫn có cấu trúc
        context_text, citations = self.citation_builder.build(candidates=reranked_chunks)

        # BƯỚC 5: Sinh câu trả lời Grounded Answer tuân thủ JSON schema
        response = await self.generator.generate(
            query_analysis=query_analysis,
            context_text=context_text,
            citations=citations,
            vehicle_context=vehicle_context,
        )

        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        response.metadata["latency_ms"] = elapsed_ms
        response.metadata["retrieved_chunks_count"] = len(fused_candidates)
        response.metadata["reranked_chunks_count"] = len(reranked_chunks)

        logger.info(f"Hoàn thành xử lý trong {elapsed_ms}ms, citations: {len(response.citations)}")
        return response

    def query_sync(
        self,
        query: str,
        vehicle_context: UserVehicleContext | None = None,
        top_k: int = 4,
    ) -> RAGResponse:
        """Wrapper đồng bộ cho các script kiểm thử hoặc batch evaluation."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(lambda: asyncio.run(self.query(query, vehicle_context, top_k)))
                return future.result()
        else:
            return asyncio.run(self.query(query, vehicle_context, top_k))
