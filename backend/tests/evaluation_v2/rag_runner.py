"""Read-only production RAG evaluation with separate retrieval and answer evidence."""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import time
from pathlib import Path

from src.agents.tools.RAG.ingestion.qdrant_store import QdrantVectorStore
from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
from src.agents.tools.RAG.query.hybrid import HybridRetriever
from src.agents.tools.RAG.query.rag_pipeline import RAGPipeline
from src.agents.tools.RAG.query.reranker import RerankerService
from src.agents.tools.RAG.query.rewriter import QueryRewriter
from src.agents.tools.RAG.query.schemas import RAGResponse, UserVehicleContext
from src.config import get_settings
from src.infrastructure.embedding.factory import create_embedding_engine
from src.infrastructure.llm.factory import create_llm_provider

from .artifacts import ROOT, create_run, digest, verify_history, write_new
from .scoring import retrieval_metrics

GOLDEN = ROOT / "backend/tests/test_agents/test_rag/evaluation/golden_set.jsonl"


class ReadOnlyStore(QdrantVectorStore):
    def _ensure_collection(self):
        # Never create, index, re-embed or delete a configured collection.
        info = self.client.get_collection(self.collection_name)
        vectors = info.config.params.vectors
        if getattr(vectors, "size", None) != self.vector_size:
            raise ValueError(f"Collection dimensions {getattr(vectors, 'size', None)} differ from embedding dimensions {self.vector_size}")

    def add_chunks(self, *args, **kwargs):
        raise RuntimeError("Evaluation storage is read-only")

    def clear(self):
        raise RuntimeError("Evaluation storage is read-only")


class RecordedProvider:
    def __init__(self, model, endpoint_order=None):
        settings = get_settings().model_copy(update={"openrouter_model": model})
        self.provider = create_llm_provider(settings, "openrouter")
        self.provider._client = self.provider._client.with_options(max_retries=0, timeout=60)
        self.events = []
        self.endpoint_order = endpoint_order

    @property
    def provider_name(self):
        return self.provider.provider_name

    async def chat(self, *args, **kwargs):
        started = time.perf_counter()
        if self.endpoint_order and kwargs.get("config") is not None:
            configuration = kwargs["config"]
            body = configuration.extra.get("extra_body", {})
            kwargs["config"] = configuration.model_copy(update={"extra": {**configuration.extra, "extra_body": {**body, "provider": {**body.get("provider", {}), "order": self.endpoint_order, "allow_fallbacks": True}}}})
        configuration = kwargs.get("config")
        request_parameters = {"temperature": configuration.temperature, "max_tokens": configuration.max_tokens, "extra": configuration.extra} if configuration else {}
        try:
            response = await self.provider.chat(*args, **kwargs)
            self.events.append({"model": response.model, "stop_reason": response.stop_reason, "usage": response.usage.model_dump(), "raw_text": response.text, "request_parameters": request_parameters, "latency_seconds": time.perf_counter() - started, "error": "Provider signaled finish_reason=error" if response.stop_reason == "error" else None})
            return response
        except Exception as exc:
            self.events.append({"error": f"{type(exc).__name__}: {exc}", "request_parameters": request_parameters, "latency_seconds": time.perf_counter() - started})
            raise


class RetrievalOnlyGenerator:
    async def generate(self, **kwargs):
        return RAGResponse(answer="", citations=kwargs["citations"], confidence="low", fallback_required=True, metadata={"mode": "retrieval_only_no_answer_score"})


class RecordedStore:
    def __init__(self, store):
        self.store = store
        self.errors = []

    def get_all_chunks(self):
        return self.store.get_all_chunks()

    def search(self, **kwargs):
        try:
            return self.store.search(**kwargs)
        except Exception as exc:
            self.errors.append(f"{type(exc).__name__}: {exc}")
            raise


async def run(args):
    golden = [json.loads(line) for line in args.golden.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        golden = golden[:args.limit]
    settings = get_settings()
    args.rewrite_model = args.rewrite_model or settings.openrouter_model_for_stage("rewrite")
    args.generation_model = args.generation_model or settings.openrouter_model_for_stage("rag")
    if not golden:
        raise ValueError("Empty golden set")
    configuration = {"golden_sha256": digest(args.golden), "selected_ids": [g["id"] for g in golden], "collection": args.collection or settings.qdrant_collection_name, "embedding_provider": settings.embedding_provider, "embedding_model": settings.embedding_gemini_model, "embedding_dimensions": settings.embedding_dimensions, "rewrite_model": args.rewrite_model, "rewrite_endpoint_order": args.rewrite_endpoint_order, "generation_model": args.generation_model if args.full_rag else None, "generation_endpoint_order": args.generation_endpoint_order, "mode": "full_rag" if args.full_rag else "retrieval_only", "top_k": 5, "sparse_only": args.sparse_only}
    directory, manifest = create_run("rag_v2", configuration, args.run_name)
    print(f"Run: {directory}", flush=True)
    rows = []
    preflight_error = None
    store = None
    try:
        if not settings.qdrant_url:
            raise ValueError("QDRANT_URL missing; evaluation will not create a local substitute")
        if settings.embedding_provider != "gemini" or settings.embedding_gemini_model.removeprefix("models/") != "gemini-embedding-001":
            raise ValueError("This evaluation requires the requested Gemini embedding-001 configuration")
        store = ReadOnlyStore(collection_name=args.collection, embedding_provider=create_embedding_engine(settings))
        recorded_store = RecordedStore(store)
        hybrid = HybridRetriever(vector_store=recorded_store, enable_dense=not args.sparse_only)
        count = hybrid.sync_bm25_from_vector_store()
        if not count:
            raise ValueError("Corpus is empty or could not be read")
        corpus = sorted(hybrid.bm25_searcher.corpus_chunks, key=lambda c: c["chunk_id"])
        write_new(directory / "corpus_snapshot.json", {"chunk_count": count, "documents": sorted({c["doc_id"] for c in corpus}), "content_sha256": hashlib.sha256(json.dumps(corpus, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest(), "collection_info": store.client.get_collection(store.collection_name).model_dump(mode="json")})
        rewrite = RecordedProvider(args.rewrite_model, args.rewrite_endpoint_order)
        generation = RecordedProvider(args.generation_model, args.generation_endpoint_order) if args.full_rag else None
        reranker = RerankerService()
        write_new(directory / "resolved_components.json", {"reranker": type(reranker._reranker).__name__, "embedding_model": store.embedding_provider.model, "embedding_dimensions": store.vector_size})
        pipeline = RAGPipeline(rewriter=QueryRewriter(rewrite), hybrid_retriever=hybrid, reranker=reranker, generator=GroundedAnswerGenerator(generation) if generation else RetrievalOnlyGenerator())
        with (directory / "case_results.jsonl").open("x", encoding="utf-8") as stream, (directory / "human_review.csv").open("x", encoding="utf-8", newline="") as review:
            writer = csv.writer(review)
            writer.writerow(["case_id", "question", "expected_answer", "actual_answer", "correctness", "citation_support", "reviewer", "notes"])
            for index, case in enumerate(golden, 1):
                rewrite.events.clear()
                if generation:
                    generation.events.clear()
                recorded_store.errors.clear()
                started = time.perf_counter()
                row = {"case_id": case["id"], "question": case["query"], "expected_answer": case["expected_answer"], "expected_doc_ids": case["relevant_doc_ids"], "ranked_doc_ids": [], "ranked_chunks": [], "answer": "", "error": None}
                try:
                    response = await pipeline.query(case["query"], UserVehicleContext(model=case.get("model")), top_k=5, category=case.get("category"))
                    row["ranked_chunks"] = response.metadata.get("ranked_chunks", [])
                    # Rank is over the five selected chunks BEFORE neighbor expansion.
                    row["ranked_doc_ids"] = [chunk["doc_id"] for chunk in row["ranked_chunks"]]
                    row["response"] = response.model_dump(mode="json")
                    row["answer"] = response.answer
                    errors = recorded_store.errors + [e["error"] for e in rewrite.events + (generation.events if generation else []) if e.get("error")]
                    errors.extend("Provider output truncated" for e in rewrite.events + (generation.events if generation else []) if e.get("stop_reason") == "length")
                    if response.metadata.get("mode") == "offline_summary" and not errors:
                        errors.append("Live generation fell back to an offline summary")
                    if pipeline.rewriter._llm_disabled_after_quota and not rewrite.events:
                        errors.append("Rewrite skipped after an earlier provider quota error")
                    row["error"] = " | ".join(errors) or None
                    if not args.sparse_only and hybrid._dense_disabled and not recorded_store.errors:
                        row["error"] = "Dense retrieval skipped after an earlier embedding failure"
                    evidence_ids = {(c["doc_id"], c["chunk_id"]) for c in row["ranked_chunks"]}
                    row["citation_id_membership_valid"] = all((c.document_id, c.chunk_id) in evidence_ids for c in response.citations)
                    row["semantic_correctness"] = "NEEDS_HUMAN_REVIEW" if args.full_rag else "NOT_MEASURED"
                    row["citation_claim_support"] = "NEEDS_HUMAN_REVIEW" if args.full_rag else "NOT_MEASURED"
                except Exception as exc:
                    row["error"] = f"{type(exc).__name__}: {exc}"
                row["latency_seconds"] = round(time.perf_counter() - started, 3)
                row["provider_events"] = {"rewrite": list(rewrite.events), "generation": list(generation.events) if generation else []}
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                stream.flush()
                writer.writerow([case["id"], case["query"], case["expected_answer"], row["answer"], "", "", "", ""])
                review.flush()
                print(f"[{index}/{len(golden)}] {case['id']} {'ERROR' if row['error'] else 'RECORDED'}", flush=True)
                permanent_error = any(marker in (row["error"] or "") for marker in ("LLMAuthError", "401", "402", "404"))
                consecutive_errors = len(rows) >= 3 and all(r["error"] for r in rows[-3:])
                if row["error"] and (index == 1 or permanent_error or consecutive_errors):
                    break
                if args.delay:
                    await asyncio.sleep(args.delay)
    except Exception as exc:
        preflight_error = f"{type(exc).__name__}: {exc}"
    finally:
        if store is not None:
            store.client.close()
    metrics = retrieval_metrics(rows)
    metrics.update({"selected": len(golden), "complete": len(rows) == len(golden), "preflight_error": preflight_error, "semantic_correctness": "NEEDS_HUMAN_REVIEW" if args.full_rag else "NOT_MEASURED", "production_acceptance": False})
    write_new(directory / "metrics.json", metrics)
    verify_history(directory, manifest)
    with (directory / "report.md").open("x", encoding="utf-8") as stream:
        stream.write("# RAG evaluation v2\n\nDEVELOPMENT ONLY. Source membership does not prove claim support.\n\n```json\n" + json.dumps(metrics, ensure_ascii=False, indent=2) + "\n```\n")
    print(f"Report: {directory / 'report.md'}", flush=True)
    return 2 if preflight_error or metrics["errors"] or not metrics["complete"] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=GOLDEN)
    parser.add_argument("--collection")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--full-rag", action="store_true")
    parser.add_argument("--sparse-only", action="store_true", help="Explicit diagnostic; not a hybrid acceptance run")
    parser.add_argument("--rewrite-model", help="Override OPENROUTER_REWRITE_MODEL (or shared OPENROUTER_MODEL)")
    parser.add_argument("--rewrite-endpoint-order", action="append")
    parser.add_argument("--generation-model", help="Override OPENROUTER_RAG_MODEL (or shared OPENROUTER_MODEL)")
    parser.add_argument("--generation-endpoint-order", action="append")
    parser.add_argument("--run-name")
    parser.add_argument("--delay", type=float, default=3)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("limit must be positive")
    logging.getLogger().setLevel(logging.WARNING)
    return asyncio.run(run(args))
