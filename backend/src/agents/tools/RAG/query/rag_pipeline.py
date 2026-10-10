from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from collections import OrderedDict

from .citation_builder import CitationBuilder
from .generator import GroundedAnswerGenerator
from .hybrid import HybridRetriever
from .reranker import RerankerService
from .rewriter import QueryRewriter
from .schemas import RAGResponse, UserVehicleContext

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()

# Answers come from static manuals: repeat questions (quick chips) skip ~10 s of LLM calls.
_CACHE_TTL_SECONDS = 600
_CACHE_MAX_ENTRIES = 128


def _rag_loop() -> asyncio.AbstractEventLoop:
    """One long-lived loop for every RAG query.

    The rewriter/generator LLM clients keep connections bound to the loop that first
    used them; a fresh ``asyncio.run`` per query failed every call after the first one
    with "Event loop is closed".
    """
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, name="rag-loop", daemon=True).start()
        return _loop


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
        self._cache: OrderedDict[tuple, tuple[float, RAGResponse]] = OrderedDict()
        self._cache_lock = threading.Lock()

    async def query(
        self,
        query: str,
        vehicle_context: UserVehicleContext | None = None,
        top_k: int = 4,
        category: str | None = None,
        expand_neighbors: bool = True,
    ) -> RAGResponse:
        """Xử lý truy vấn end-to-end theo luồng RAG nâng cao."""
        key = (
            " ".join(query.lower().split()),
            vehicle_context.model_dump_json() if vehicle_context else None,
            top_k,
            (category or "").strip().lower(),
            expand_neighbors,
        )
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        response = await self._answer(query, vehicle_context, top_k, category, expand_neighbors)
        # Never cache a degraded answer (LLM down, nothing retrieved).
        if not response.fallback_required and response.confidence != "low":
            self._cache_put(key, response)
        return response

    def _cache_get(self, key: tuple) -> RAGResponse | None:
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None or entry[0] < time.monotonic():
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return entry[1].model_copy(deep=True)

    def _cache_put(self, key: tuple, response: RAGResponse) -> None:
        with self._cache_lock:
            self._cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, response.model_copy(deep=True))
            self._cache.move_to_end(key)
            while len(self._cache) > _CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)

    async def _answer(
        self,
        query: str,
        vehicle_context: UserVehicleContext | None,
        top_k: int,
        category: str | None,
        expand_neighbors: bool,
    ) -> RAGResponse:
        start_time = time.time()
        logger.info(f"Bắt đầu xử lý câu hỏi: '{query}'")

        # BƯỚC 1: Viết lại query & Trích xuất Metadata Filter bằng LLM
        query_analysis = await self.rewriter.analyze(
            query=query,
            vehicle_context=vehicle_context,
        )
        # Explicit tool intent takes precedence over the inferred category.
        # Hybrid retrieval still includes broader FAQ evidence by design.
        if category and category.strip():
            query_analysis.category = category.strip().lower()
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
        # Blocking I/O (embedding, Qdrant) and CPU (rerank) run off the event loop.
        fused_candidates = await asyncio.to_thread(
            self.hybrid_retriever.retrieve,
            analysis=query_analysis,
            top_candidates=20,
        )
        logger.debug(f"Hybrid retrieval thu được: {len(fused_candidates)} candidates")

        # BƯỚC 3: Cross-Encoder Reranking Top-K
        reranked_chunks = await asyncio.to_thread(
            self.reranker.rerank,
            query=query_analysis.rewritten_query,
            candidates=fused_candidates,
            top_k=max(top_k * 3, top_k),
        )
        reranked_chunks = self.hybrid_retriever.select_context(
            candidates=reranked_chunks,
            analysis=query_analysis,
            top_k=top_k,
        )
        ranked_chunks = [chunk.model_dump(mode="json") for chunk in reranked_chunks]
        if expand_neighbors:
            reranked_chunks = await asyncio.to_thread(self.hybrid_retriever.expand_neighbors, reranked_chunks)
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
        response.metadata["ranked_chunks"] = ranked_chunks
        response.metadata["evidence_chunks"] = [chunk.model_dump(mode="json") for chunk in reranked_chunks]
        response.metadata["query_analysis"] = query_analysis.model_dump(mode="json")

        logger.info(f"Hoàn thành xử lý trong {elapsed_ms}ms, citations: {len(response.citations)}")
        return response

    def _submit(self, *args) -> concurrent.futures.Future[RAGResponse]:
        return asyncio.run_coroutine_threadsafe(self.query(*args), _rag_loop())

    async def aquery(
        self,
        query: str,
        vehicle_context: UserVehicleContext | None = None,
        top_k: int = 4,
        category: str | None = None,
        expand_neighbors: bool = True,
    ) -> RAGResponse:
        """``query`` on the RAG loop, awaitable from any loop; cancelling it cancels the query."""
        return await asyncio.wrap_future(self._submit(query, vehicle_context, top_k, category, expand_neighbors))

    def query_sync(
        self,
        query: str,
        vehicle_context: UserVehicleContext | None = None,
        top_k: int = 4,
        category: str | None = None,
        expand_neighbors: bool = True,
    ) -> RAGResponse:
        """Wrapper đồng bộ cho các script kiểm thử hoặc batch evaluation."""
        return self._submit(query, vehicle_context, top_k, category, expand_neighbors).result()
