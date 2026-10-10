"""Fresh paired 8-case pilots for the RAG evidence preservation revision."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import statistics
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import step4_generation as generation
import step4_rewrite as common
from langchain_core.callbacks import BaseCallbackHandler
from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
from src.agents.tools.RAG.query.rag_pipeline import RAGPipeline
from step4_rewrite_contract_revision import RevisionProvider
from tests.evaluation_v2 import runner
from tests.evaluation_v2.sandbox import Sandbox

MASTER = ROOT / "eval/results/rag_evidence_preservation_revision_20261008_28"
PREVIOUS = ROOT / "eval/results/step4_configuration_full_20261008_26"
IDS = ["RAG-001", "RAG-007", "RAG-027", "RAG-083", "BOOK-05", "BOOK-19", "GUARD-09", "REMINDER-03"]
MISTRAL = "mistralai/mistral-small-2603"
MODELS = {"base": MISTRAL, "agent_gemma": "google/gemma-4-26b-a4b-it"}
MAX_AGENT_CALLS = 6
MAX_RAG_CALLS = 2


class AgentCapture(BaseCallbackHandler):
    raise_error = True

    def __init__(self):
        self.events = []
        self.pending = {}

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        if len(self.events) >= MAX_AGENT_CALLS:
            raise RuntimeError("Evaluation Agent call budget exhausted before provider request")
        event = {"messages": [[m.model_dump(mode="json") for m in batch] for batch in messages],
                 "started": time.perf_counter(), "error": None}
        self.events.append(event)
        self.pending[run_id] = event

    def on_llm_end(self, response, *, run_id, **kwargs):
        event = self.pending.pop(run_id)
        message = response.generations[0][0].message
        metadata = message.response_metadata
        output = response.llm_output or {}
        usage = metadata.get("token_usage") or output.get("token_usage") or {}
        event.update({"latency_seconds": time.perf_counter() - event.pop("started"),
                      "model": metadata.get("model_name") or output.get("model_name"),
                      "usage": usage, "cost_usd": usage.get("cost"),
                      "message": message.model_dump(mode="json"),
                      "stop_reason": metadata.get("finish_reason") or (response.generations[0][0].generation_info or {}).get("finish_reason")})

    def on_llm_error(self, error, *, run_id, **kwargs):
        event = self.pending.pop(run_id, None)
        if event is not None:
            event.update({"latency_seconds": time.perf_counter() - event.pop("started"),
                          "error": f"{type(error).__name__}: {error}"})


class LiveRAG:
    """Keep async provider connections on the graph's event loop across tools."""

    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.events = []
        self.loop = None
        self.lock = threading.Lock()

    async def query(self, kwargs):
        started = time.perf_counter()
        event = {"tool_input": {k: v.model_dump(mode="json") if hasattr(v, "model_dump") else v for k, v in kwargs.items()}, "error": None}
        try:
            response = await self.pipeline.query(**kwargs)
            event["response"] = response.model_dump(mode="json")
            return response
        except Exception as exc:
            event["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            event["latency_seconds"] = time.perf_counter() - started
            self.events.append(event)

    def query_sync(self, **kwargs):
        with self.lock:
            if getattr(self, "started_calls", 0) >= MAX_RAG_CALLS:
                self.events.append({"error": "Evaluation RAG call budget exhausted before provider request"})
                raise RuntimeError(self.events[-1]["error"])
            self.started_calls = getattr(self, "started_calls", 0) + 1
        if not self.loop or threading.get_ident() == self.loop_thread:
            raise RuntimeError("Live RAG bridge must execute from the tool worker thread")
        future = asyncio.run_coroutine_threadsafe(self.query(kwargs), self.loop)
        try:
            return future.result(timeout=180)
        except TimeoutError:
            future.cancel()
            raise

    def reset(self):
        self.events.clear()
        self.started_calls = 0
        self.loop = asyncio.get_running_loop()
        self.loop_thread = threading.get_ident()


def corpus_snapshot(store):
    corpus = sorted(store.get_all_chunks(), key=lambda c: c["chunk_id"])
    return {"chunk_count": len(corpus), "content_sha256": common.content_hash(corpus),
            "documents": sorted({c["doc_id"] for c in corpus})}


def preservation():
    manifest = common.read(MASTER / "manifest.json")
    checks = {key: common.verify(common.read(MASTER / name)) for key, name in
              (("history", "protected_previous_files.json"), ("corpus", "protected_corpus.json"), ("source", "source_revision.json"))}
    checks["previous_runtime"] = common.verify(common.read(MASTER / "previous_runtime_lock.json"))
    checks.update({"env_unchanged": common.digest(ROOT / ".env") == manifest["env_sha256"],
                   "subset_unchanged": common.digest(MASTER / "selected_cases.json") == manifest["selected_cases_sha256"],
                   "rubric_unchanged": common.digest(MASTER / "rubric.json") == manifest["rubric_sha256"]})
    if not all(v["unchanged"] if isinstance(v, dict) else v for v in checks.values()):
        raise RuntimeError("Frozen evaluation conditions changed")
    return checks


def prepare():
    if not common.verify(common.read(MASTER / "previous_runtime_lock.json"))["unchanged"]:
        raise RuntimeError("Application or frozen revision-27 helpers changed")
    previous_revision = ROOT / "eval/results/rag_evidence_preservation_revision_20261008_27"
    for name in ("closed_master_hashes.json", "completed_producer_hashes.json"):
        if not common.verify(common.read(previous_revision / name))["unchanged"]:
            raise RuntimeError("Interrupted revision-27 evidence changed")
    for name in ("closed_master_hashes.json", "completed_producer_hashes.json"):
        if not common.verify(common.read(PREVIOUS / name))["unchanged"]:
            raise RuntimeError("Closed full-run evidence changed")
    before = common.read(MASTER / "source_before.json")
    changed = {str(p).replace("\\", "/") for p in common.verify(before)["changed"]}
    allowed = {"backend/src/agents/graph.py", "backend/src/agents/evidence.py",
               "backend/src/agents/tools/RAG/query/maintenance_gate.py", "backend/src/agents/tools/RAG/query/generator.py"}
    if changed != allowed:
        raise RuntimeError(f"Unexpected application/source revision: {changed}")
    if not common.verify(common.read(MASTER / "protected_previous_files.json"))["unchanged"]:
        raise RuntimeError("Historical results changed")
    env_hash = common.digest(ROOT / ".env")
    if env_hash != common.read(MASTER / "env_before.json")["sha256"]:
        raise RuntimeError("Environment changed during revision")
    source = {name: common.digest(ROOT / name) for name in before}
    for name in ("eval/step4_rag_preservation_retry.py", "eval/test_rag_preservation_gate.py", "eval/step4_rag_preservation_retry_report.py"):
        source[name] = common.digest(ROOT / name)
    common.write(MASTER / "source_revision.json", source)
    common.write(MASTER / "source_change_audit.json", {"changed_paths": sorted(changed), "old_source_copies_preserved": True})
    previous = common.read(PREVIOUS / "manifest.json")
    cases = {c["id"]: c for c in common.read(common.DATASET)["cases"]}
    common.write(MASTER / "selected_cases.json", [cases[i] for i in IDS])
    common.write(MASTER / "rubric.json", {
        "status": "DEVELOPMENT_REVISION_NOT_SEMANTIC_ACCEPTANCE", "scorer_version": runner.SCORER_VERSION,
        "technical_gate": "same per-case provider/raw JSON/raw argument/retrieval/safety checks as full 26",
        "additional_gate": "RAG-007 must use coolant_source_value_unverified before generation; fallback RAG-only answers must preserve tool content and low-confidence/fallback state",
        "stop": "first failed technical or additional preservation gate; no retries or skipped-case success",
        "labels": "0 independent labels; review deferred", "historical_verdicts": "unchanged; no rescoring",
        "boundary": "Pure RAG turns are deterministically grounded; mixed business writes keep their own guards; not general entailment/correctness",
    })
    for name in ("live_corpus_lock.json", "components_lock.json"):
        common.write(MASTER / name, common.read(PREVIOUS / name))
    common.write(MASTER / "manifest.json", previous | {
        "scope": "RAG_EVIDENCE_PRESERVATION_CORRECTED_EVALUATOR_FRESH_8_CASE_DEVELOPMENT",
        "previous_interrupted_pilots": "eval/results/rag_evidence_preservation_revision_20261008_27",
        "application_runtime_same_as_27": True,
        "evaluator_change": "Preservation gate applies to current-turn RAG-only ToolMessages, regardless of case category; mixed tools excluded exactly as runtime. Original verdicts unchanged.",
        "previous_full_run": str(PREVIOUS.relative_to(ROOT)), "selected_ids": IDS,
        "selected_cases_sha256": common.digest(MASTER / "selected_cases.json"), "rubric_sha256": common.digest(MASTER / "rubric.json"),
        "source_revision_sha256": common.digest(MASTER / "source_revision.json"), "env_sha256": env_hash,
        "selection": "8 unchanged exposed cases, adds RAG-007 focus to paired regression coverage; not holdout",
        "intentional_changes": ["Maintenance gate uses supplied vehicle context when query omits model", "Pure RAG fallback answer is preserved after Agent response; raw output retained", "Aggregate current-turn uncertainty across RAG tools"],
        "pilot_gate": "New scoped evaluator regression PASS, unchanged runtime reuses 82 focused PASS/1 skip; broader 610 PASS/3 OEM fixture failures/5 skip. OEM alone passes 5/5 and dotenv alone reproduces all 3 failures without RAG imports. See offline_validation.json; both configurations use same new runtime revision",
        "expansion_rule": "one fresh 8-case pilot/configuration; no automatic full/holdout rerun",
    })
    print(json.dumps({"revision_frozen": True, "cases": len(IDS), "application_changed_paths": sorted(changed)}), flush=True)


def analyze(row):
    live = row["live"]
    failures = []
    if row["trace"].get("error"):
        failures.append(row["trace"]["error"])
    if not row["metrics"]["task_passed"]:
        failures.append("Agent scorer gate failed")
    if row["metrics"]["raw_argument_errors"]:
        failures.append("Agent raw argument contract failed")
    if row["category"] == "rag" and not live["rag"]:
        failures.append("Expected live RAG was not executed")
    for stage, events in (("agent", live["agent"]), ("rewrite", live["rewrite"]), ("generation", live["generation"])):
        expected = row["agent_model"] if stage == "agent" else MISTRAL
        for e in events:
            if e.get("error"):
                failures.append(f"{stage}: {e['error']}")
            elif e.get("model") != expected:
                failures.append(f"{stage}: actual model differs from requested")
            if e.get("stop_reason") in {"length", "error"}:
                failures.append(f"{stage}: finish_reason={e['stop_reason']}")
            if stage != "agent" and not e.get("error"):
                validator = common.raw_contract if stage == "rewrite" else generation.raw_contract
                if validator(e.get("raw_text", ""))[1]:
                    failures.append(f"{stage}: strict raw JSON failed")
    failures.extend(live["retrieval_errors"])
    if live["dense_disabled"] or live["rewrite_fallback_calls"]:
        failures.append("Dense/Rewrite fallback occurred")
    for e in live["rag"]:
        if e.get("error"):
            failures.append(e["error"])
            continue
        response = e["response"]
        evidence = response["metadata"].get("evidence_chunks", [])
        ids = {(c["doc_id"], c["chunk_id"]) for c in evidence}
        if any((c["document_id"], c["chunk_id"]) not in ids for c in response["citations"]):
            failures.append("Citation identity has no returned live evidence")
        if response["metadata"].get("mode") == "offline_summary":
            failures.append("Generation offline fallback occurred")
    rag_events = live["rag"]
    current_tools = []
    for message in row["trace"].get("messages", []):
        if message.get("type") == "human":
            current_tools.clear()
        elif message.get("type") == "tool":
            current_tools.append(message)
    rag_only = bool(current_tools) and all(isinstance(m.get("artifact"), dict) and m["artifact"].get("type") == "RAG_EVIDENCE" for m in current_tools)
    final = (row["trace"].get("messages") or [{}])[-1]
    if rag_only and any(e.get("response", {}).get("fallback_required") for e in rag_events):
        if not final.get("response_metadata", {}).get("rag_fallback_preserved"):
            failures.append("RAG fallback was not preserved in final Agent response")
        if row["trace"].get("fallback_required") is not True or row["trace"].get("confidence") != "low":
            failures.append("RAG fallback/confidence state lost")
        tool_texts = [c.get("result", {}).get("text", "") for c in row["trace"]["calls"] if isinstance(c.get("artifact"), dict) and c["artifact"].get("type") == "RAG_EVIDENCE"]
        if not tool_texts or any(text not in row["trace"]["answer"] for text in tool_texts if text):
            failures.append("Final RAG answer differs from bounded tool evidence")
    if row["case_id"] == "RAG-007":
        if len(rag_events) != 1 or rag_events[0].get("response", {}).get("metadata", {}).get("reason") != "coolant_source_value_unverified":
            failures.append("Coolant evidence gate missing for RAG-007")
        if live["generation"]:
            failures.append("RAG-007 unexpectedly reached generation provider")
    return {"technical_pass": not failures, "failures": failures,
            "rag_only_preservation_applicable": rag_only, "semantic_correctness": "NOT_MEASURED", "citation_claim_support": "NOT_MEASURED"}


def metrics(rows, preflight_error=None):
    costs = {}
    missing = {}
    for stage in ("agent", "rewrite", "generation"):
        values = [(e.get("cost_usd") if stage == "agent" else e.get("usage", {}).get("cost_usd")) for r in rows for e in r["live"][stage]]
        costs[stage] = sum(v for v in values if isinstance(v, (int, float)))
        missing[stage] = sum(not isinstance(v, (int, float)) for v in values)
    return {"selected": len(IDS), "attempted": len(rows), "complete": len(rows) == len(IDS),
            "technical_pass": sum(r["configuration_gate"]["technical_pass"] for r in rows),
            "scorer_pass": sum(r["metrics"]["task_passed"] for r in rows),
            "safety_violations": sum(len(r["metrics"]["safety_violations"]) for r in rows),
            "raw_argument_errors": sum(len(r["metrics"]["raw_argument_errors"]) for r in rows),
            "preflight_error": preflight_error, "known_stage_cost_usd": costs, "known_total_llm_cost_usd": sum(costs.values()),
            "missing_receipts_by_stage": missing, "embedding_calls": sum(len(r["live"]["embedding"]) for r in rows), "embedding_cost_usd": None,
            "stage_calls": {s: sum(len(r["live"][s]) for r in rows) for s in ("agent", "rewrite", "generation")},
            "live_rag_calls": sum(len(r["live"]["rag"]) for r in rows),
            "mean_task_seconds": statistics.fmean(r["trace"]["latency_seconds"] for r in rows) if rows else None,
            "production_acceptance": False, "independent_labels": 0, "semantic_correctness": "NOT_MEASURED"}


async def run(key):
    preservation()
    directory = ROOT / "eval/results" / f"rag_evidence_preservation_{key}_20261008_28"
    directory.mkdir(exist_ok=False)
    common.write(directory / "manifest.json", common.read(MASTER / "manifest.json") | {"configuration_key": key})
    rows, store, providers = [], None, []
    preflight_error = None
    try:
        settings = common.get_settings()
        if settings.embedding_provider != "gemini" or settings.embedding_dimensions != 3072:
            raise RuntimeError("Configured Gemini embedding-001/3072 required")
        embedding = common.ObservedEmbedding(common.create_embedding_engine(settings))
        store = common.ReadOnlyStore(embedding_provider=embedding)
        before = corpus_snapshot(store)
        common.write(directory / "corpus_before.json", before)
        if before != common.read(MASTER / "live_corpus_lock.json"):
            raise RuntimeError("Live Qdrant corpus changed since Rewrite baseline")
        recorded = common.RecordedStore(store)
        hybrid = common.HybridRetriever(vector_store=recorded)
        if not hybrid.sync_bm25_from_vector_store():
            raise RuntimeError("BM25 live corpus unavailable")
        reranker = common.RerankerService()
        components = {"reranker": type(reranker._reranker).__name__, "reranker_model": getattr(reranker._reranker, "model_name", getattr(reranker._reranker, "model", None)),
                      "embedding": embedding.model, "dimensions": embedding.dimensions}
        common.write(directory / "resolved_components.json", components)
        if components != common.read(MASTER / "components_lock.json"):
            raise RuntimeError("Resolved retrieval components changed")
        for _ in range(2):
            inner = common.create_llm_provider(settings.model_copy(update={"openrouter_model": MISTRAL, "openrouter_endpoint_order": "mistral/us,mistral/eu"}), "openrouter")
            inner._client = inner._client.with_options(max_retries=0, timeout=60)
            providers.append(RevisionProvider(inner, MISTRAL))
        rewrite, generate = providers
        rewriter = common.ObservedRewriter(rewrite)
        pipeline = LiveRAG(RAGPipeline(rewriter=rewriter, hybrid_retriever=hybrid, reranker=reranker, generator=GroundedAnswerGenerator(generate)))
        args = SimpleNamespace(max_tokens=2048, timeout=60, endpoint_order=["mistral/us", "mistral/eu"] if key == "base" else [])
        original_provider = runner.provider

        class LiveSandbox(Sandbox):
            def __init__(self, case):
                super().__init__(case, rag_pipeline=pipeline)

        snapshot = LiveSandbox({})
        try:
            common.write(directory / "schema_snapshot.json", {t.name: t.tool_call_schema.model_json_schema() for t in snapshot.tools})
        finally:
            await snapshot.close()
        with (directory / "case_results.jsonl").open("x", encoding="utf-8") as stream, (directory / "human_review.csv").open("x", encoding="utf-8", newline="") as review:
            writer = csv.writer(review)
            writer.writerow(["case_id", "correctness", "citation_support", "task_success", "reviewer", "notes"])
            for index, case in enumerate(common.read(MASTER / "selected_cases.json"), 1):
                capture = AgentCapture()
                for p in providers:
                    p.events.clear()
                embedding.events.clear()
                recorded.errors.clear()
                rewriter.fallback_calls = 0
                pipeline.reset()

                def agent_provider(model, arguments, observer=capture):
                    return original_provider(model, arguments).model_copy(update={"callbacks": [observer]})

                with patch.object(runner, "Sandbox", LiveSandbox), patch.object(runner, "provider", agent_provider):
                    row = await runner.evaluate(case, MODELS[key], args, runner.build_graph)
                row.update({"agent_model": MODELS[key], "configuration_key": key,
                            "live": {"agent": capture.events, "rewrite": list(rewrite.events), "generation": list(generate.events),
                                     "embedding": list(embedding.events), "rag": list(pipeline.events), "retrieval_errors": list(recorded.errors),
                                     "dense_disabled": hybrid._dense_disabled, "rewrite_fallback_calls": rewriter.fallback_calls}})
                row["configuration_gate"] = analyze(row)
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                stream.flush()
                writer.writerow([case["id"], "", "", "", "", ""])
                review.flush()
                print(f"[{key} {index}/{len(IDS)}] {case['id']} {'PASS' if row['configuration_gate']['technical_pass'] else 'FAIL'}", flush=True)
                if not row["configuration_gate"]["technical_pass"]:
                    break
                await asyncio.sleep(3)
        after = corpus_snapshot(store)
        common.write(directory / "corpus_after.json", after | {"unchanged": after == before})
        if after != before:
            raise RuntimeError("Live corpus mutated during pilot")
    except Exception as exc:  # noqa: BLE001 -- preserve provider/preflight failure as a closed run
        preflight_error = f"{type(exc).__name__}: {exc}"
    finally:
        for p in providers:
            await p.inner._client.close()
        if store:
            store.client.close()
    result = metrics(rows, preflight_error)
    common.write(directory / "metrics.json", result)
    common.write(directory / "preservation.json", preservation())
    common.write(directory / "closed_run_hashes.json", common.hashes([directory]))
    print(json.dumps(result), flush=True)
    return 0 if result["complete"] and result["technical_pass"] == len(IDS) and not preflight_error else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "run"])
    parser.add_argument("configuration", nargs="?", choices=list(MODELS))
    args = parser.parse_args()
    logging.disable(logging.WARNING)
    if args.phase == "prepare":
        prepare()
    elif args.configuration:
        raise SystemExit(asyncio.run(run(args.configuration)))
    else:
        parser.error("configuration required")
