"""Production RAG evaluation entrypoint.

Modes:
  smoke      Embedding -> Qdrant -> BM25 -> hybrid retrieval -> reranker.
  retrieval  Golden-set retrieval evaluation without answer generation.
  full       Retrieval plus production GroundedAnswerGenerator and negative cases.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
EVALUATION = BACKEND / "tests" / "evaluation" / "rag"
METRICS_DIR = EVALUATION / "scripts"
sys.path[:0] = [str(BACKEND), str(BACKEND / "src"), str(METRICS_DIR)]
load_dotenv(ROOT / ".env")

from rag_metrics import QueryResult, compute_metrics  # noqa: E402

from src.agents.tools.RAG.ingestion.qdrant_store import QdrantVectorStore  # noqa: E402
from src.agents.tools.RAG.query.bm25_searcher import BM25Searcher  # noqa: E402
from src.agents.tools.RAG.query.citation_builder import CitationBuilder  # noqa: E402
from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator  # noqa: E402
from src.agents.tools.RAG.query.hybrid import HybridRetriever  # noqa: E402
from src.agents.tools.RAG.query.reranker import RerankerService  # noqa: E402
from src.agents.tools.RAG.query.rewriter import QueryRewriter  # noqa: E402
from src.agents.tools.RAG.query.schemas import QueryAnalysis, UserVehicleContext  # noqa: E402


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * p
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def normalize_doc_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def token_set(value: str) -> set[str]:
    return {token for token in re.findall(r"\b[\w]+\b", value.casefold()) if len(token) >= 2}


def current_run_name() -> str:
    return datetime.now().astimezone().strftime("run_%Y%m%d_%H%M%S")


class ProductionRAGHarness:
    def __init__(self, collection: str | None, *, full: bool = False) -> None:
        self.store = QdrantVectorStore(collection_name=collection)
        self.bm25 = BM25Searcher()
        self.retriever = HybridRetriever(vector_store=self.store, bm25_searcher=self.bm25)
        self.bm25_chunks = self.retriever.sync_bm25_from_vector_store()
        self.reranker = RerankerService(provider="auto")
        self.rewriter = QueryRewriter()
        self.citation_builder = CitationBuilder()
        self.generator = GroundedAnswerGenerator() if full else None

    def actual_collection_dimension(self) -> int | None:
        info = self.store.client.get_collection(self.store.collection_name)
        params = getattr(getattr(info, "config", None), "params", None)
        vectors = getattr(params, "vectors", None)
        size = getattr(vectors, "size", None)
        if size is None and isinstance(vectors, dict):
            size = vectors.get("size")
        return int(size) if size is not None else None

    def environment(self, top_k: int) -> dict[str, Any]:
        provider = self.store.embedding_provider
        generation_provider = self.generator.llm_provider if self.generator else None
        return {
            "qdrant_collection": self.store.collection_name,
            "qdrant_points": self.store.count(),
            "embedding_provider": provider.__class__.__name__,
            "embedding_model": getattr(provider, "model", None),
            "embedding_dimension": self.store.vector_size,
            "collection_dimension": self.actual_collection_dimension(),
            "bm25_indexed_chunks": self.bm25_chunks,
            "reranker": self.reranker._reranker.__class__.__name__,
            "reranker_model": getattr(self.reranker._reranker, "model_name", None)
            or getattr(self.reranker._reranker, "model", None),
            "top_k": top_k,
            "generator": self.generator.__class__.__name__ if self.generator else None,
            "generation_model": getattr(generation_provider, "_model", None),
        }

    async def analysis_for(
        self, row: dict[str, Any], heuristic_rewriter: bool
    ) -> QueryAnalysis:
        vehicle = UserVehicleContext(model=row["model"]) if row.get("model") else None
        if heuristic_rewriter:
            return self.rewriter._heuristic_fallback(row["query"], vehicle)
        return await self.rewriter.analyze(row["query"], vehicle)

    def retrieve(self, query: str, analysis: QueryAnalysis, top_k: int) -> list[Any]:
        candidates = self.retriever.retrieve(analysis=analysis, top_candidates=25)
        ranked = self.reranker.rerank(query, candidates, top_k=max(top_k * 3, top_k))
        ranked = self.retriever.select_context(ranked, analysis=analysis, top_k=top_k)
        return self.retriever.expand_neighbors(ranked)


def print_environment(environment: dict[str, Any]) -> None:
    print("\nPRODUCTION CONFIGURATION")
    for key, value in environment.items():
        print(f"{key:24}: {value}")


async def run_smoke(args: argparse.Namespace, run_dir: Path) -> dict[str, Any]:
    print("\n========================================")
    print("RAG SMOKE EVALUATION")
    print("========================================")
    started = time.perf_counter()
    checks: dict[str, dict[str, Any]] = {}
    error: str | None = None
    try:
        harness = ProductionRAGHarness(args.collection)
        env = harness.environment(top_k=3)
        print_environment(env)
        checks["qdrant_connected"] = {"passed": env["qdrant_points"] > 0, "value": env["qdrant_points"]}
        checks["collection_dimension"] = {
            "passed": env["collection_dimension"] == env["embedding_dimension"],
            "expected": env["embedding_dimension"],
            "actual": env["collection_dimension"],
        }
        vector = await asyncio.to_thread(
            harness.store.embedding_provider.embed_query,
            "Lịch bảo dưỡng định kỳ xe VinFast VF8",
        )
        checks["embedding"] = {"passed": len(vector) == env["embedding_dimension"], "dimension": len(vector)}
        checks["bm25_sync"] = {"passed": harness.bm25_chunks > 0, "chunks": harness.bm25_chunks}
        row = {"query": "Lịch bảo dưỡng định kỳ xe VinFast VF8", "model": "VF8"}
        analysis = await harness.analysis_for(row, args.heuristic_rewriter)
        ranked = await asyncio.to_thread(harness.retrieve, row["query"], analysis, 3)
        checks["hybrid_retrieval"] = {"passed": bool(ranked), "chunks": len(ranked)}
        checks["reranker"] = {
            "passed": bool(ranked) and any(item.rerank_score is not None for item in ranked),
            "name": env["reranker"],
        }
        checks["chunks_returned"] = {
            "passed": bool(ranked),
            "doc_ids": [item.doc_id for item in ranked],
        }
    except Exception as exc:
        env = {}
        error = f"{type(exc).__name__}: {exc}"
    passed = bool(checks) and all(item["passed"] for item in checks.values()) and error is None
    status = "SYSTEM WORKING" if passed else "NOT WORKING"
    payload = {
        "mode": "smoke",
        "status": status,
        "environment": env,
        "checks": checks,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "error": error,
    }
    write_json(run_dir / "smoke" / "report.json", payload)
    print(f"\nStatus: {status}")
    if error:
        print(f"Error : {error}")
    print("========================================")
    return payload


def select_rows(rows: list[dict[str, Any]], args: argparse.Namespace, *, full: bool) -> list[dict[str, Any]]:
    selected = rows
    if full and args.sample_per_category:
        counts: dict[str, int] = defaultdict(int)
        sampled = []
        for row in rows:
            category = row.get("category", "general")
            if counts[category] < args.sample_per_category:
                sampled.append(row)
                counts[category] += 1
        selected = sampled
    if args.limit:
        selected = selected[: args.limit]
    return selected


async def evaluate_rows(
    harness: ProductionRAGHarness,
    rows: list[dict[str, Any]],
    *,
    top_k: int,
    full: bool,
    heuristic_rewriter: bool,
    concurrency: int,
    answer_delay: float,
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    generation_lock = asyncio.Lock()

    async def one(index: int, row: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        output: dict[str, Any] = {
            "id": row["id"], "query": row["query"], "category": row.get("category", "general"),
            "model": row.get("model"), "expected_doc_ids": row.get("relevant_doc_ids", []),
            "expected_keywords": row.get("expected_keywords", []), "error": None,
        }
        async with semaphore:
            # Measure processing time only. Starting before the semaphore would
            # incorrectly include time spent waiting behind earlier queries.
            started = time.perf_counter()
            try:
                analysis = await harness.analysis_for(row, heuristic_rewriter)
                ranked = await asyncio.to_thread(harness.retrieve, row["query"], analysis, top_k)
                doc_ids = [item.doc_id for item in ranked]
                scores = [
                    item.rerank_score if item.rerank_score is not None else item.dense_score or item.rrf_score or 0.0
                    for item in ranked
                ]
                expected = {normalize_doc_id(value) for value in row.get("relevant_doc_ids", [])}
                rank = next(
                    (position for position, value in enumerate(doc_ids, 1) if normalize_doc_id(value) in expected),
                    None,
                )
                output.update({
                    "analysis": analysis.model_dump(),
                    "retrieved_doc_ids": doc_ids,
                    "retrieved_chunks": [
                        {
                            "chunk_id": item.chunk_id,
                            "doc_id": item.doc_id,
                            "score": round(float(score), 4),
                            "metadata": item.metadata,
                            "content": item.content,
                        }
                        for item, score in zip(ranked, scores)
                    ],
                    "rank": rank,
                    "hit_at_1": rank == 1,
                    "hit_at_3": rank is not None and rank <= 3,
                    "hit_at_5": rank is not None and rank <= 5,
                    "reciprocal_rank": 1.0 / rank if rank else 0.0,
                    "top_score": round(float(scores[0]), 4) if scores else 0.0,
                })
                if full and harness.generator is not None:
                    context, citations = harness.citation_builder.build(ranked)
                    async with generation_lock:
                        if answer_delay:
                            await asyncio.sleep(answer_delay)
                        response = await harness.generator.generate(
                            query_analysis=analysis,
                            context_text=context,
                            citations=citations,
                            vehicle_context=UserVehicleContext(model=row["model"]) if row.get("model") else None,
                        )
                    cited = [item.document_id for item in response.citations]
                    answer_norm = response.answer.casefold()
                    keywords = row.get("expected_keywords", [])
                    keyword_coverage = (
                        sum(keyword.casefold() in answer_norm for keyword in keywords) / len(keywords)
                        if keywords else 1.0
                    )
                    retrieved_normalized = {normalize_doc_id(value) for value in doc_ids}
                    citation_validity = (
                        sum(normalize_doc_id(value) in retrieved_normalized for value in cited) / len(cited)
                        if cited else (1.0 if response.fallback_required else 0.0)
                    )
                    context_tokens = token_set(" ".join(item.content for item in ranked))
                    answer_tokens = token_set(response.answer)
                    grounded_overlap = (
                        len(answer_tokens & context_tokens) / len(answer_tokens) if answer_tokens else 0.0
                    )
                    expected_tokens = token_set(row.get("expected_answer", ""))
                    precision = len(answer_tokens & expected_tokens) / len(answer_tokens) if answer_tokens else 0.0
                    recall = len(answer_tokens & expected_tokens) / len(expected_tokens) if expected_tokens else 0.0
                    token_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
                    output["answer"] = {
                        "text": response.answer,
                        "confidence": response.confidence,
                        "fallback_required": response.fallback_required,
                        "cited_doc_ids": cited,
                        "metadata": response.metadata,
                        "keyword_coverage": round(keyword_coverage, 4),
                        "correctness_heuristic": round((token_f1 + keyword_coverage) / 2, 4),
                        "citation_validity": round(citation_validity, 4),
                        "faithfulness_heuristic": round(grounded_overlap, 4),
                    }
            except Exception as exc:
                output["error"] = f"{type(exc).__name__}: {exc}"
            output["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        print(
            f"[{index:03d}/{len(rows)}] {row['id']:<5} "
            f"rank={output.get('rank')} latency={output['latency_ms']:.1f}ms"
        )
        return index, output

    completed = await asyncio.gather(*(one(i, row) for i, row in enumerate(rows, 1)))
    return [row for _, row in sorted(completed)]


def retrieval_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    valid = [row for row in results if not row.get("error")]
    latencies = [float(row["latency_ms"]) for row in results]
    categories: dict[str, dict[str, Any]] = {}
    for category in sorted({row["category"] for row in results}):
        rows = [row for row in results if row["category"] == category]
        categories[category] = {
            "queries": len(rows),
            "hit_at_1": round(sum(bool(row.get("hit_at_1")) for row in rows) / len(rows), 4),
            "hit_at_3": round(sum(bool(row.get("hit_at_3")) for row in rows) / len(rows), 4),
            "hit_at_5": round(sum(bool(row.get("hit_at_5")) for row in rows) / len(rows), 4),
            "mrr": round(statistics.fmean(float(row.get("reciprocal_rank", 0)) for row in rows), 4),
        }
    return {
        "queries": total,
        "completed": len(valid),
        "errors": total - len(valid),
        "retrieval_success": round(sum(bool(row.get("hit_at_5")) for row in results) / total, 4) if total else 0.0,
        "hit_at_1": round(sum(bool(row.get("hit_at_1")) for row in results) / total, 4) if total else 0.0,
        "hit_at_3": round(sum(bool(row.get("hit_at_3")) for row in results) / total, 4) if total else 0.0,
        "hit_at_5": round(sum(bool(row.get("hit_at_5")) for row in results) / total, 4) if total else 0.0,
        "mrr": round(statistics.fmean(float(row.get("reciprocal_rank", 0)) for row in results), 4) if total else 0.0,
        "average_score": round(statistics.fmean(float(row.get("top_score", 0)) for row in valid), 4) if valid else None,
        "average_latency_ms": round(statistics.fmean(latencies), 1) if latencies else None,
        "p95_latency_ms": round(percentile(latencies, 0.95) or 0.0, 1) if latencies else None,
        "categories": categories,
        "failed_query_ids": [row["id"] for row in results if not row.get("hit_at_5")],
    }


async def evaluate_negative_cases(
    harness: ProductionRAGHarness, args: argparse.Namespace
) -> list[dict[str, Any]]:
    cases = load_json(EVALUATION / "datasets" / "rag_negative_cases.json")
    outputs: list[dict[str, Any]] = []
    assert harness.generator is not None
    for case in cases:
        started = time.perf_counter()
        try:
            analysis = harness.rewriter._heuristic_fallback(
                case["query"], UserVehicleContext(model=case["model"]) if case.get("model") else None
            )
            if case["type"] == "no_context":
                response = await harness.generator.generate(analysis, "Không có tài liệu tham khảo phù hợp.", [])
                retrieved_doc_ids: list[str] = []
                retrieved_text = ""
            else:
                ranked = await asyncio.to_thread(harness.retrieve, case["query"], analysis, args.top_k or 3)
                context, citations = harness.citation_builder.build(ranked)
                response = await harness.generator.generate(analysis, context, citations)
                retrieved_doc_ids = [item.doc_id for item in ranked]
                retrieved_text = " ".join(item.content for item in ranked).casefold()
            forbidden = [
                phrase for phrase in case.get("forbidden_phrases", [])
                if phrase.casefold() in response.answer.casefold()
                and phrase.casefold() not in retrieved_text
            ]
            regex_hits = [
                match.group(0)
                for pattern in case.get("forbidden_patterns", [])
                for match in re.finditer(pattern, response.answer, flags=re.IGNORECASE)
                if match.group(0).casefold() not in retrieved_text
            ]
            fallback_ok = response.fallback_required if case["expected_behavior"] == "fallback" else True
            passed = fallback_ok and not forbidden and not regex_hits
            outputs.append({
                "id": case["id"], "query": case["query"], "type": case["type"],
                "passed": passed, "fallback_required": response.fallback_required,
                "answer": response.answer, "citations": [item.document_id for item in response.citations],
                "retrieved_doc_ids": retrieved_doc_ids, "forbidden_phrase_hits": forbidden,
                "forbidden_pattern_hits": regex_hits,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": None,
            })
        except Exception as exc:
            outputs.append({
                "id": case["id"], "query": case["query"], "type": case["type"],
                "passed": False, "error": f"{type(exc).__name__}: {exc}",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            })
        print(f"[NEGATIVE] {case['id']}: {'PASS' if outputs[-1]['passed'] else 'FAIL'}")
    return outputs


def print_retrieval(summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    print("\n========================================")
    print("RAG RETRIEVAL EVALUATION")
    print("========================================")
    print(f"Queries: {summary['queries']}")
    print(f"Hit@1 : {summary['hit_at_1']:.2%}")
    print(f"Hit@3 : {summary['hit_at_3']:.2%}")
    print(f"Hit@5 : {summary['hit_at_5']:.2%}")
    print(f"MRR   : {summary['mrr']:.4f}")
    print(f"Avg latency : {summary['average_latency_ms']} ms")
    print(f"P95 latency : {summary['p95_latency_ms']} ms")
    print("\nCATEGORY")
    for name, values in summary["categories"].items():
        print(f"{name:12}: Hit@5={values['hit_at_5']:.2%} MRR={values['mrr']:.4f} ({values['queries']})")
    print("\nFAILED QUERIES")
    for row in results:
        if not row.get("hit_at_5"):
            print(
                f"{row['id']}: {row['query']} | expected={row['expected_doc_ids']} "
                f"retrieved={row.get('retrieved_doc_ids', [])} error={row.get('error')}"
            )
    print("========================================")


def full_summary(results: list[dict[str, Any]], negatives: list[dict[str, Any]]) -> dict[str, Any]:
    answers = [row["answer"] for row in results if row.get("answer")]
    latencies = [float(row["latency_ms"]) for row in results if not row.get("error")]
    def avg(name: str) -> float | None:
        return round(statistics.fmean(float(row[name]) for row in answers), 4) if answers else None
    negative_completed = [row for row in negatives if not row.get("error")]
    hallucinations = [row for row in negative_completed if not row.get("passed")]
    return {
        "evaluated_answers": len(answers),
        "retrieval_success": retrieval_summary(results)["retrieval_success"],
        "answer_correctness_heuristic": avg("correctness_heuristic"),
        "expected_keyword_coverage": avg("keyword_coverage"),
        "faithfulness_heuristic": avg("faithfulness_heuristic"),
        "citation_validity": avg("citation_validity"),
        "average_latency_ms": round(statistics.fmean(latencies), 1) if latencies else None,
        "p95_latency_ms": round(percentile(latencies, 0.95) or 0.0, 1) if latencies else None,
        "hallucination_rate_negative_cases": (
            round(len(hallucinations) / len(negative_completed), 4) if negative_completed else None
        ),
        "hallucination_rate_general": "NOT MEASURED",
        "negative_cases_passed": sum(bool(row.get("passed")) for row in negatives),
        "negative_cases_total": len(negatives),
    }


def update_markdown(run_name: str, run_dir: Path) -> Path:
    report_path = EVALUATION / "reports" / f"rag_system_evaluation_{run_name}.md"
    sections = [f"# RAG System Evaluation — {run_name}", "", "Các số liệu dưới đây được đọc trực tiếp từ raw result của run này.", ""]
    smoke_path = run_dir / "smoke" / "report.json"
    retrieval_path = run_dir / "retrieval" / "report.json"
    full_path = run_dir / "full_rag" / "report.json"
    if smoke_path.exists():
        smoke = load_json(smoke_path)
        sections += ["## Smoke", "", f"Status: **{smoke['status']}**", "", "```json", json.dumps(smoke.get("environment", {}), ensure_ascii=False, indent=2), "```", ""]
    if retrieval_path.exists():
        data = load_json(retrieval_path)
        m = data["metrics"]
        sections += [
            "## Retrieval", "",
            "| Metric | Score |", "|---|---:|",
            f"| Queries | {m['queries']} |", f"| Hit@1 | {m['hit_at_1']:.2%} |",
            f"| Hit@3 | {m['hit_at_3']:.2%} |", f"| Hit@5 | {m['hit_at_5']:.2%} |",
            f"| MRR | {m['mrr']:.4f} |", f"| Avg latency | {m['average_latency_ms']} ms |",
            f"| P95 latency | {m['p95_latency_ms']} ms |", "",
            f"Failed: {', '.join(m['failed_query_ids']) or 'None'}", "",
        ]
    if full_path.exists():
        data = load_json(full_path)
        m = data["metrics"]
        sections += ["## Full RAG", "", "| Metric | Score |", "|---|---:|"]
        for key, value in m.items():
            sections.append(f"| {key} | {value} |")
        sections += ["", "## Negative cases", ""]
        for row in data.get("negative_cases", []):
            sections.append(f"- `{row['id']}`: **{'PASS' if row.get('passed') else 'FAIL'}**")
        sections.append("")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(sections), encoding="utf-8")
    return report_path


async def run_quality(args: argparse.Namespace, run_dir: Path, *, full: bool) -> dict[str, Any]:
    top_k = args.top_k or (3 if full else 5)
    harness = ProductionRAGHarness(args.collection, full=full)
    environment = harness.environment(top_k)
    print_environment(environment)
    rows = select_rows(load_jsonl(args.golden), args, full=full)
    results = await evaluate_rows(
        harness, rows, top_k=top_k, full=full,
        heuristic_rewriter=args.heuristic_rewriter,
        concurrency=args.concurrency, answer_delay=args.answer_delay_seconds,
    )
    retrieval = retrieval_summary(results)
    if not full:
        payload = {"mode": "retrieval", "environment": environment, "metrics": retrieval, "results": results}
        write_json(run_dir / "retrieval" / "report.json", payload)
        metrics_text = json.dumps(retrieval, ensure_ascii=False, indent=2)
        (run_dir / "retrieval" / "metrics.txt").write_text(metrics_text, encoding="utf-8")
        print_retrieval(retrieval, results)
        return payload
    negatives = await evaluate_negative_cases(harness, args)
    metrics = full_summary(results, negatives)
    payload = {
        "mode": "full_rag", "environment": environment,
        "retrieval_metrics": retrieval, "metrics": metrics,
        "results": results, "negative_cases": negatives,
    }
    write_json(run_dir / "full_rag" / "report.json", payload)
    (run_dir / "full_rag" / "metrics.txt").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n========================================")
    print("FULL RAG EVALUATION")
    print("========================================")
    for key, value in metrics.items():
        print(f"{key:38}: {value}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the production EV Care RAG")
    parser.add_argument("--mode", required=True, choices=["smoke", "retrieval", "full"])
    parser.add_argument("--run-name", default=current_run_name())
    parser.add_argument("--collection")
    parser.add_argument("--golden", type=Path, default=EVALUATION / "datasets" / "rag_golden_set.jsonl")
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-per-category", type=int, default=1, help="Full mode only; 0 means all")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--answer-delay-seconds", type=float, default=0.0)
    parser.add_argument("--heuristic-rewriter", action="store_true")
    parser.add_argument(
        "--reuse-existing", action="store_true",
        help="Recompute summaries/reports from this run's existing raw result without external calls",
    )
    return parser


async def async_main(args: argparse.Namespace) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_name):
        raise SystemExit("--run-name chỉ được chứa chữ, số, dấu _, - hoặc .")
    run_dir = EVALUATION / "results" / args.run_name
    existing_path = run_dir / ("full_rag" if args.mode == "full" else args.mode) / "report.json"
    if args.reuse_existing:
        if not existing_path.exists():
            raise SystemExit(f"Không có raw result để reuse: {existing_path}")
        payload = load_json(existing_path)
        if args.mode == "full":
            payload["metrics"] = full_summary(payload.get("results", []), payload.get("negative_cases", []))
            write_json(existing_path, payload)
            (existing_path.parent / "metrics.txt").write_text(
                json.dumps(payload["metrics"], ensure_ascii=False, indent=2), encoding="utf-8"
            )
        print(f"Reused existing {args.mode} result; no external call was made.")
        exit_code = 0
    elif args.mode == "smoke":
        payload = await run_smoke(args, run_dir)
        exit_code = 0 if payload["status"] == "SYSTEM WORKING" else 2
    else:
        payload = await run_quality(args, run_dir, full=args.mode == "full")
        exit_code = 0 if not any(row.get("error") for row in payload["results"]) else 2
    report = update_markdown(args.run_name, run_dir)
    print(f"\nRaw result: {run_dir}")
    print(f"Report    : {report}")
    return exit_code


def main() -> int:
    return asyncio.run(async_main(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
