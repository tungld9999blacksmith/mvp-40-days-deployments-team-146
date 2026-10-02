"""Evaluate the production Qdrant + BM25 + reranker retrieval pipeline.

This runner intentionally does not use Chroma. It reads the collection configured
by QDRANT_URL/QDRANT_API_KEY/QDRANT_COLLECTION_NAME and uses the same query-side
components as the application.

Run from the repository root:
    .venv/bin/python backend/tests/test_agents/test_rag/evaluation/run_eval.py
    .venv/bin/python backend/tests/test_agents/test_rag/evaluation/run_eval.py --full-rag

The default uses golden_set.jsonl for retrieval evaluation. Add --full-rag to
also generate and score answers; that mode calls the configured LLM API.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parents[4]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "src"), str(EVAL_DIR)]

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from metrics import QueryResult, compute_metrics, format_metrics_report  # noqa: E402
from src.agents.tools.RAG.ingestion.qdrant_store import QdrantVectorStore  # noqa: E402
from src.agents.tools.RAG.ingestion.embedding import BaseEmbeddingProvider  # noqa: E402
from src.agents.tools.RAG.query.bm25_searcher import BM25Searcher  # noqa: E402
from src.agents.tools.RAG.query.hybrid import HybridRetriever  # noqa: E402
from src.agents.tools.RAG.query.citation_builder import CitationBuilder  # noqa: E402
from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator  # noqa: E402
from src.agents.tools.RAG.query.reranker import RerankerService  # noqa: E402
from src.agents.tools.RAG.query.rewriter import QueryRewriter  # noqa: E402
from src.agents.tools.RAG.query.schemas import UserVehicleContext  # noqa: E402


class _EmbeddingDisabled(BaseEmbeddingProvider):
    """Guard provider for sparse-only runs that must not call an embedding API."""

    model = "models/gemini-embedding-001"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("Embeddings are disabled for sparse-only evaluation.")

    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("Embeddings are disabled for sparse-only evaluation.")


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--golden",
        type=Path,
        default=EVAL_DIR / "golden_set.jsonl",
        help="Grounded JSONL evaluation set (default: golden_set.jsonl)",
    )
    parser.add_argument("--collection", help="Override Qdrant collection name")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--limit", type=int, help="Evaluate only the first N rows (smoke test)")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent production queries")
    parser.add_argument("--sample-per-category", type=int, help="Take N rows from each category")
    parser.add_argument("--heuristic-rewriter", action="store_true", help="Use the production rewriter fallback path")
    parser.add_argument("--answer-delay-seconds", type=float, default=0.0, help="Delay before each real LLM answer call")
    parser.add_argument("--output-stem", default="evaluation", help="Output filename prefix")
    parser.add_argument(
        "--evaluate-answers",
        "--full-rag",
        dest="evaluate_answers",
        action="store_true",
        help="Also generate and score real answers (calls the configured LLM API)",
    )
    parser.add_argument(
        "--sparse-only",
        action="store_true",
        help="Skip query embeddings and evaluate Qdrant payload + BM25",
    )
    args = parser.parse_args()

    golden = load_jsonl(args.golden)
    if args.sample_per_category:
        counts: dict[str, int] = defaultdict(int)
        sampled = []
        for row in golden:
            category = row.get("category", "general")
            if counts[category] < args.sample_per_category:
                sampled.append(row)
                counts[category] += 1
        golden = sampled
    if args.limit:
        golden = golden[: args.limit]
    if not golden:
        raise ValueError(f"No evaluation rows in {args.golden}")

    store = QdrantVectorStore(
        collection_name=args.collection,
        embedding_provider=_EmbeddingDisabled() if args.sparse_only else None,
    )
    bm25 = BM25Searcher()
    retriever = HybridRetriever(
        vector_store=store,
        bm25_searcher=bm25,
        enable_dense=not args.sparse_only,
    )
    indexed = retriever.sync_bm25_from_vector_store()
    reranker = RerankerService(provider="auto")
    initial_reranker_name = reranker._reranker.__class__.__name__
    rewriter = QueryRewriter()
    citation_builder = CitationBuilder()
    generator = GroundedAnswerGenerator() if args.evaluate_answers else None
    generation_lock = asyncio.Lock()

    print(f"Collection : {store.collection_name}")
    print(f"Points     : {store.count()}")
    print(f"BM25 chunks: {indexed}")
    print(f"Golden set : {args.golden.name} ({len(golden)} queries)")
    print(f"Reranker   : {reranker._reranker.__class__.__name__}")
    print(f"Top-K      : {args.top_k}")

    async def evaluate_row(index: int, row: dict, semaphore: asyncio.Semaphore) -> tuple[int, QueryResult]:
        result = QueryResult(
            id=row["id"],
            query=row["query"],
            model=row.get("model"),
            category=row.get("category", "general"),
            relevant_doc_ids=row.get("relevant_doc_ids", []),
            expected_keywords=row.get("expected_keywords", []),
            min_score=row.get("min_score", 0.50),
            expected_answer=row.get("expected_answer", ""),
        )

        async with semaphore:
            started = time.perf_counter()
            try:
                vehicle_context = (
                    UserVehicleContext(model=row["model"]) if row.get("model") else None
                )
                analysis = (
                    rewriter._heuristic_fallback(row["query"], vehicle_context)
                    if args.heuristic_rewriter
                    else await rewriter.analyze(row["query"], vehicle_context)
                )

                def retrieve_and_rank():
                    candidates = retriever.retrieve(analysis=analysis, top_candidates=25)
                    ranked_items = reranker.rerank(
                        row["query"], candidates, top_k=max(args.top_k * 3, args.top_k)
                    )
                    ranked_items = retriever.select_context(
                        ranked_items, analysis=analysis, top_k=args.top_k
                    )
                    return retriever.expand_neighbors(ranked_items)

                ranked = await asyncio.to_thread(retrieve_and_rank)
                result.retrieved_texts = [candidate.content for candidate in ranked]
                result.retrieved_doc_ids = [candidate.doc_id for candidate in ranked]
                result.scores = [
                    round(candidate.dense_score or candidate.rerank_score or 0.0, 4)
                    for candidate in ranked
                ]
                result.top_score = max(
                    (
                        candidate.dense_score
                        if candidate.dense_score is not None
                        else candidate.rerank_score or 0.0
                        for candidate in ranked
                    ),
                    default=0.0,
                )
                if generator is not None:
                    context_text, citations = citation_builder.build(ranked)
                    async with generation_lock:
                        if args.answer_delay_seconds > 0:
                            await asyncio.sleep(args.answer_delay_seconds)
                    response = await generator.generate(
                            query_analysis=analysis,
                            context_text=context_text,
                            citations=citations,
                    )
                    result.generation_metadata = response.metadata
                    # Offline fallback không phải generated-answer evaluation.
                    if response.metadata.get("mode") != "offline_summary":
                        result.actual_answer = response.answer
                        result.cited_doc_ids = [c.document_id for c in response.citations]
                result.analysis = analysis.model_dump()
            except Exception as exc:
                result.error = f"{type(exc).__name__}: {exc}"
            result.latency_ms = (time.perf_counter() - started) * 1000
        print(f"[{index:02d}/{len(golden)}] {result.id:<4} score={result.top_score:.3f} {result.latency_ms:7.1f}ms")
        return index, result

    async def evaluate_all() -> list[QueryResult]:
        semaphore = asyncio.Semaphore(max(args.concurrency, 1))
        completed = await asyncio.gather(*(
            evaluate_row(index, row, semaphore)
            for index, row in enumerate(golden, 1)
        ))
        return [result for _, result in sorted(completed, key=lambda item: item[0])]

    results = asyncio.run(evaluate_all())

    metrics = compute_metrics(results)
    report = format_metrics_report(metrics)
    print("\n" + report)

    from metrics import compute_keyword_ratio, compute_reciprocal_rank, is_pass

    report_data = []
    for result in results:
        report_data.append(
            {
                "id": result.id,
                "query": result.query,
                "model": result.model,
                "category": result.category,
                "top_score": round(result.top_score, 4),
                "keyword_ratio": round(compute_keyword_ratio(result), 3),
                "rr": round(compute_reciprocal_rank(result), 3),
                "pass": is_pass(result),
                "latency_ms": round(result.latency_ms, 1),
                "retrieved_docs": result.retrieved_doc_ids,
                "keywords_missing": [
                    keyword
                    for keyword in result.expected_keywords
                    if keyword.casefold()
                    not in " ".join(result.retrieved_texts).casefold()
                ],
                "error": result.error,
                "actual_answer": result.actual_answer,
                "cited_docs": result.cited_doc_ids,
                "analysis": getattr(result, "analysis", None),
                "generation_metadata": getattr(result, "generation_metadata", None),
            }
        )

    def normalized(value: str) -> str:
        import re
        return re.sub(r"[^\w]+", "", value.casefold())

    def token_set(value: str) -> set[str]:
        import re
        return {token for token in re.findall(r"\b[\w]+\b", value.casefold()) if len(token) >= 2}

    answer_rows = [result for result in results if result.actual_answer.strip()]
    answer_correctness = []
    answer_completeness = []
    answer_coherence = []
    citation_support = []
    for result in answer_rows:
        actual_tokens = token_set(result.actual_answer)
        expected_tokens = token_set(result.expected_answer)
        precision = len(actual_tokens & expected_tokens) / len(actual_tokens) if actual_tokens else 0.0
        recall = len(actual_tokens & expected_tokens) / len(expected_tokens) if expected_tokens else 1.0
        token_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        keyword_hits = sum(
            normalized(keyword) in normalized(result.actual_answer)
            for keyword in result.expected_keywords
        )
        completeness = keyword_hits / len(result.expected_keywords) if result.expected_keywords else 1.0
        answer_correctness.append((token_f1 + completeness) / 2)
        answer_completeness.append(completeness)
        import re
        sentences = [
            s.strip().casefold()
            for s in re.split(r"(?:[.!?]\s+|\n+)", result.actual_answer)
            if len(s.strip()) >= 15
        ]
        answer_coherence.append(1.0 if sentences and len(sentences) == len(set(sentences)) else 0.0)
        support_scores = []
        for cited_doc in result.cited_doc_ids:
            cited_text = " ".join(
                text
                for doc_id, text in zip(result.retrieved_doc_ids, result.retrieved_texts)
                if doc_id.casefold() == cited_doc.casefold()
            )
            keyword_supported = any(
                normalized(keyword) in normalized(cited_text)
                for keyword in result.expected_keywords
            )
            overlap = token_set(result.actual_answer) & token_set(cited_text)
            support_scores.append(1.0 if keyword_supported or len(overlap) >= 3 else 0.0)
        citation_support.append(sum(support_scores) / len(support_scores) if support_scores else 0.0)

    answer_metrics = {
        "evaluated": len(answer_rows),
        "coverage": round(len(answer_rows) / len(results), 4) if results else 0.0,
        "correctness": round(sum(answer_correctness) / len(answer_correctness), 4) if answer_correctness else None,
        "completeness": round(sum(answer_completeness) / len(answer_completeness), 4) if answer_completeness else None,
        "relevancy": round(metrics.answer_relevancy, 4) if metrics.answer_relevancy is not None else None,
        "coherence": round(sum(answer_coherence) / len(answer_coherence), 4) if answer_coherence else None,
        "citation_correctness": round(metrics.citation_correctness, 4) if metrics.citation_correctness is not None else None,
        "citation_support": round(sum(citation_support) / len(citation_support), 4) if citation_support else None,
    }

    payload = {
        "backend": "qdrant_production_pipeline",
        "collection": store.collection_name,
        "golden_set": args.golden.name,
        "pipeline": {
            "dense_enabled": not args.sparse_only,
            "query_embeddings": (
                "disabled"
                if args.sparse_only
                else f"{store.embedding_provider.__class__.__name__}/Qdrant dense"
            ),
            "embedding_model": getattr(store.embedding_provider, "model", None),
            "dense_disabled_after_quota": retriever._dense_disabled,
            "rewriter": rewriter.__class__.__name__,
            "rewriter_mode": "heuristic_fallback" if args.heuristic_rewriter else "llm_with_fallback",
            "rewrite_model": (
                None
                if args.heuristic_rewriter
                else getattr(rewriter.llm_provider, "_model", None)
            ),
            "reranker": initial_reranker_name,
            "rerank_model": getattr(reranker._reranker, "model", None),
            "reranker_final": reranker._reranker.__class__.__name__,
            "reranker_fallback_count": getattr(reranker, "fallback_count", 0),
            "generator": generator.__class__.__name__ if generator else None,
            "generation_model": (
                getattr(generator.llm_provider, "_model", None) if generator else None
            ),
            "top_k": args.top_k,
        },
        "retrieval_metrics": {
            "total": metrics.total,
            "pass_rate": round(metrics.pass_rate, 4),
            "hit_at_1": round(metrics.hit_at_1, 4),
            "hit_at_3": round(metrics.hit_at_3, 4),
            "hit_at_5": round(metrics.hit_at_5, 4),
            "mrr": round(metrics.mrr, 4),
            "avg_top_score": round(metrics.avg_top_score, 4),
            "avg_kw_ratio": round(metrics.avg_keyword_ratio, 4),
            "avg_latency_ms": round(metrics.avg_latency_ms, 1),
            "p95_latency_ms": round(metrics.p95_latency_ms, 1),
            "context_precision": round(metrics.context_precision, 4),
            "context_recall": round(metrics.context_recall, 4),
            "category_stats": metrics.category_stats,
        },
        "answer_metrics": answer_metrics,
        "results": report_data,
    }
    (EVAL_DIR / f"{args.output_stem}_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (EVAL_DIR / f"{args.output_stem}_metrics.txt").write_text(report, encoding="utf-8")
    return 0 if metrics.pass_rate >= 0.80 else 2


if __name__ == "__main__":
    raise SystemExit(main())
