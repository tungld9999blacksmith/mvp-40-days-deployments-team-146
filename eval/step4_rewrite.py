"""Preserved Rewrite development comparison with read-only live retrieval."""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from src.agents.tools.RAG.ingestion.metadata import (
    canonicalize_vehicle_model,
)
from src.agents.tools.RAG.query.hybrid import HybridRetriever
from src.agents.tools.RAG.query.reranker import RerankerService
from src.agents.tools.RAG.query.rewriter import (
    SYSTEM_PROMPT,
    QueryRewriter,
)
from src.agents.tools.RAG.query.schemas import UserVehicleContext
from src.config import get_settings
from src.infrastructure.embedding.factory import create_embedding_engine
from src.infrastructure.llm.factory import create_llm_provider
from step4_smoke import digest, hashes, percentile, verify
from tests.evaluation_v2.rag_runner import ReadOnlyStore, RecordedStore
from tests.evaluation_v2.scoring import retrieval_metrics

MASTER = ROOT / "eval/results/step4_rewrite_comparison_20261008_17"
GOLDEN = ROOT / "backend/tests/test_agents/test_rag/evaluation/golden_set.jsonl"
DATASET = ROOT / "eval/test_cases/agent_cases_v2_1.json"
MODELS = {"mistral": "mistralai/mistral-small-2603", "gemma": "google/gemma-4-26b-a4b-it",
          "gemini_lite": "google/gemini-3.5-flash-lite"}
GOLDEN_IDS = ["M01", "M02", "M03", "M07", "M18", "M23", "W01", "W02", "W04", "W12", "W20",
              "B01", "B11", "B16", "B20", "P01", "P05", "PR01", "PR03", "PR07", "PR10", "G01", "G03", "G05"]
V2_IDS = ["MAINT-01", "MAINT-10", "MAINT-13", "BOOK-11", "BOOK-22", "GUARD-13"]
PILOT_IDS = ["M01", "W02", "G01", "MAINT-10", "GUARD-13"]
FIELDS = {"rewritten_query", "keywords", "model", "category", "milestone_km", "subsystem", "is_out_of_scope"}
CATEGORIES = {"maintenance", "warranty", "pricing", "battery", "procedure", "safety", "general"}
SUBSYSTEMS = {"battery", "charging", "motor", "brake", "hvac", "software", "chassis"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, default=str)


def content_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def raw_contract(text):
    """Do not turn runtime extraction/coercion into raw model contract success."""
    try:
        payload = json.loads(text, object_pairs_hook=reject_duplicates)
        if not isinstance(payload, dict) or set(payload) != FIELDS:
            raise ValueError("expected exactly seven Rewrite fields")
        if not isinstance(payload["rewritten_query"], str) or not payload["rewritten_query"].strip():
            raise ValueError("rewritten_query must be a nonempty string")
        if not isinstance(payload["keywords"], list) or not payload["keywords"] or any(not isinstance(k, str) or not k.strip() for k in payload["keywords"]):
            raise ValueError("keywords must be a nonempty list of strings")
        if payload["model"] is not None and (not isinstance(payload["model"], str) or canonicalize_vehicle_model(payload["model"]) not in {"ALL", "VF3", "VF5", "VF6", "VF7", "VF8", "VF9", "VFe34", "VFMPV7", "Evo200", "Feliz", "Klara", "Vento", "Theon"}):
            raise ValueError("unsupported model")
        for field, allowed in (("category", CATEGORIES), ("subsystem", SUBSYSTEMS)):
            if payload[field] is not None and (not isinstance(payload[field], str) or payload[field] not in allowed):
                raise ValueError(f"unsupported {field}")
        if payload["milestone_km"] is not None and (type(payload["milestone_km"]) is not int or payload["milestone_km"] < 0):
            raise ValueError("milestone_km must be a nonnegative integer or null")
        if type(payload["is_out_of_scope"]) is not bool:
            raise ValueError("is_out_of_scope must be a boolean")
        return payload, None
    except (ValueError, TypeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def anchor_checks(case, analysis):
    expected = case["anchors"]
    return {"model_matches_declared_input": (canonicalize_vehicle_model(analysis.model) or "ALL") == expected["model"],
            "milestone_matches_literal_query": analysis.milestone_km == expected["milestone_km"],
            "scope_matches_declared_input": analysis.is_out_of_scope == expected["is_out_of_scope"]}


class ObservedRewriter(QueryRewriter):
    def __init__(self, provider):
        super().__init__(provider)
        self.fallback_calls = 0

    def _heuristic_fallback(self, *args, **kwargs):
        self.fallback_calls += 1
        return super()._heuristic_fallback(*args, **kwargs)


class CapturedProvider:
    def __init__(self, inner, model):
        self.inner = inner
        self.model = model
        self.events = []

    async def chat(self, messages, config):
        request = self.inner._build_kwargs(messages, config) if hasattr(self.inner, "_build_kwargs") else {
            "model": self.model, "messages": [m.model_dump() for m in messages], **config.model_dump()}
        started = time.perf_counter()
        try:
            response = await self.inner.chat(messages=messages, config=config)
            self.events.append({"request": request, "request_sha256": content_hash(request),
                                "raw_text": response.text, "model": response.model, "stop_reason": response.stop_reason,
                                "usage": response.usage.model_dump(), "latency_seconds": time.perf_counter() - started,
                                "error": "provider finish_reason=error" if response.stop_reason == "error" else None})
            return response
        except Exception as exc:
            self.events.append({"request": request, "request_sha256": content_hash(request),
                                "latency_seconds": time.perf_counter() - started, "error": f"{type(exc).__name__}: {exc}"})
            raise


class ObservedEmbedding:
    def __init__(self, inner):
        self.inner = inner
        self.events = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def embed_query(self, query):
        started = time.perf_counter()
        event = {"query": query, "model": self.inner.model, "cost_usd": None}
        try:
            vector = self.inner.embed_query(query)
            event["dimensions"] = len(vector)
            return vector
        except Exception as exc:
            event["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            event["latency_seconds"] = time.perf_counter() - started
            self.events.append(event)


def prepare():
    previous = ROOT / "eval/results/step4_agent_gpt4o_followup_20261008_15"
    if not verify(read(previous / "closed_master_hashes.json"))["unchanged"]:
        raise RuntimeError("Previous GPT-4o master changed")
    protected = hashes([ROOT / "eval/results", ROOT / "eval/test_cases", ROOT / "backend/tests/test_agents",
                        ROOT / "backend/tests/evaluation"])
    golden = {c["id"]: c for c in [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines()]}
    cases = {c["id"]: c for c in read(DATASET)["cases"]}
    selected = []
    for identifier in GOLDEN_IDS + V2_IDS:
        source = golden[identifier] if identifier in golden else cases[identifier]
        query = source.get("query", source.get("user"))
        vehicle = {"model": "VF8", "current_odometer_km": 14900} if identifier in ("G01", "MAINT-01", "MAINT-10", "MAINT-13") else {"model": source.get("model")}
        model = canonicalize_vehicle_model(source.get("model") or vehicle["model"]) or "ALL"
        selected.append({"id": identifier, "query": query, "vehicle_context": vehicle,
                         "source_file": str((GOLDEN if identifier in golden else DATASET).relative_to(ROOT)),
                         "source_case_sha256": content_hash(source), "relevant_doc_ids": source.get("relevant_doc_ids", []),
                         "category_draft": source.get("category") if identifier in golden else None,
                         "anchors": {"model": model, "milestone_km": {"M01": 15000, "M23": 40000, "MAINT-13": 12000}.get(identifier),
                                     "is_out_of_scope": identifier == "GUARD-13"},
                         "context_origin": "DECLARED_SYNTHETIC_SCENARIO" if identifier in ("G01", "MAINT-01", "MAINT-10", "MAINT-13") else "golden_model_or_none",
                         "semantic_labels": "DRAFT_UNREVIEWED"})
    MASTER.mkdir(exist_ok=False)
    write(MASTER / "protected_previous_files.json", protected)
    write(MASTER / "protected_corpus.json", hashes([ROOT / "data/knowledge/raw", ROOT / "data/knowledge/processed"]))
    source = read(previous / "source_revision_02.json") | hashes([ROOT / "backend/src/infrastructure/embedding"])
    source.update({"eval/step4_rewrite.py": digest(Path(__file__)), "eval/test_step4_rewrite.py": digest(ROOT / "eval/test_step4_rewrite.py")})
    write(MASTER / "source_revision.json", source)
    write(MASTER / "selected_cases.json", selected)
    write(MASTER / "rewrite_rubric.json", {
        "status": "DEVELOPMENT_DRAFT_NOT_ACCEPTANCE", "raw_contract": "exact seven prompt fields, strict JSON/types/enums, no duplicate keys or Markdown",
        "pilot_gate": "all 5 attempted, exact requested model, no provider/retrieval errors, no truncation, strict raw contract, no runtime fallback, 3 declared input anchors matched",
        "anchor_scope": "literal model/context resolution, literal milestone and explicit out-of-scope only; not semantic preservation accuracy",
        "category": "golden draft agreement only, no category supplied to retriever; subsystem not semantically scored",
        "retrieval": "existing unverified document IDs on 24 golden cases only; hit@1/3/5 and MRR over top-5 selected anchor chunks before expansion; chunk recall unmeasured",
        "full_run": "one fresh 30-query development run per pilot-eligible model; pilot repeats not pooled as independent cases",
        "stop": "first provider/model/retrieval error, first truncation, or changed corpus/source/env; no hidden retries",
        "review": "DEFERRED_BY_USER; keep human labels blank", "acceptance_thresholds": "NOT_APPROVED",
    })
    settings = get_settings()
    write(MASTER / "manifest.json", {
        "scope": "step4_rewrite_development", "models": MODELS, "selected_ids": GOLDEN_IDS + V2_IDS, "pilot_ids": PILOT_IDS,
        "golden_sha256": digest(GOLDEN), "dataset_sha256": digest(DATASET), "env_sha256": digest(ROOT / ".env"),
        "source_revision_sha256": digest(MASTER / "source_revision.json"), "selected_cases_sha256": digest(MASTER / "selected_cases.json"),
        "rubric_sha256": digest(MASTER / "rewrite_rubric.json"), "prompt_sha256": content_hash(SYSTEM_PROMPT),
        "configuration": {"temperature": 0, "max_tokens": 500, "timeout": 60, "sdk_retries": 0, "delay_seconds": 3,
                          "top_k": 5, "top_candidates": 20, "category_override": None, "neighbors": "rank metrics before expansion",
                          "embedding_provider": settings.embedding_provider, "embedding_model": settings.embedding_gemini_model,
                          "embedding_dimensions": settings.embedding_dimensions, "collection": settings.qdrant_collection_name,
                          "routing": {"mistral": ["mistral/us", "mistral/eu"], "gemma": [], "gemini_lite": []}},
        "semantic_review": "DEFERRED", "production_acceptance": False,
        "side_effects": {"email": False, "production_db_write": False, "corpus_write": False, "env_write": False,
                         "generation_calls": False, "write_reviewer": False},
    })
    print("Prepared 30 unchanged queries (24 golden + 6 v2.1); 5-case pilot gate frozen", flush=True)


def preservation():
    manifest = read(MASTER / "manifest.json")
    checks = {name: verify(read(MASTER / filename)) for name, filename in
              (("history", "protected_previous_files.json"), ("corpus", "protected_corpus.json"), ("source", "source_revision.json"))}
    checks["env_unchanged"] = digest(ROOT / ".env") == manifest["env_sha256"]
    checks["selected_cases_unchanged"] = digest(MASTER / "selected_cases.json") == manifest["selected_cases_sha256"]
    checks["rubric_unchanged"] = digest(MASTER / "rewrite_rubric.json") == manifest["rubric_sha256"]
    if not all(checks[k]["unchanged"] for k in ("history", "corpus", "source")) or not all(checks[k] for k in ("env_unchanged", "selected_cases_unchanged", "rubric_unchanged")):
        raise RuntimeError("Frozen files changed")
    return checks


def run_name(phase, model_key):
    return f"step4_rewrite_{phase}_{model_key}_20261008_17"


def summarize(rows, selected):
    golden_rows = [r for r in rows if r["expected_doc_ids"]]
    scored_retrieval = retrieval_metrics(golden_rows)
    costs = [e.get("usage", {}).get("cost_usd") for r in rows for e in r["provider_events"]]
    times = [r["rewrite_seconds"] for r in rows]
    totals = [r["total_seconds"] for r in rows]
    return {"selected": selected, "attempted": len(rows), "complete": len(rows) == selected,
            "raw_contract_pass": sum(r["raw_contract_pass"] for r in rows),
            "provider_errors": sum(any(e.get("error") for e in r["provider_events"]) for r in rows),
            "truncated_cases": sum(r["truncated"] for r in rows), "errors": sum(bool(r["error"]) for r in rows),
            "runtime_fallback_cases": sum(r["runtime_fallback"] for r in rows),
            "anchor_all_match": sum(all(r["anchor_checks"].values()) for r in rows),
            "category_draft_agreement": {"matched": sum(r["category_draft_agrees"] is True for r in rows),
                                         "scored": sum(r["category_draft_agrees"] is not None for r in rows)},
            "actual_models": sorted({e["model"] for r in rows for e in r["provider_events"] if e.get("model")}),
            "rewrite_mean_seconds": statistics.fmean(times) if times else None, "rewrite_p90_seconds": percentile(times, .9),
            "total_mean_seconds": statistics.fmean(totals) if totals else None,
            "known_rewrite_cost_usd": sum(c for c in costs if isinstance(c, (int, float))),
            "missing_rewrite_receipts": sum(c is None for c in costs),
            "embedding_calls": sum(len(r["embedding_events"]) for r in rows), "embedding_cost_usd": None,
            "reranker_cost_usd": "NOT_MEASURED_IF_REMOTE", "retrieval": {"scored_golden_cases": len(golden_rows), **scored_retrieval},
            "semantic_preservation": "NOT_MEASURED", "independent_labels": 0, "production_acceptance": False}


async def run(phase, model_key):
    manifest = read(MASTER / "manifest.json")
    preservation()
    if phase == "full":
        pilot = read(ROOT / "eval/results" / run_name("pilot", model_key) / "metrics.json")
        if not pilot["pilot_eligible"]:
            raise RuntimeError("Pilot not eligible; do not spend on full run")
    cases = read(MASTER / "selected_cases.json")
    if phase == "pilot":
        by_id = {c["id"]: c for c in cases}
        cases = [by_id[i] for i in PILOT_IDS]
    directory = ROOT / "eval/results" / run_name(phase, model_key)
    directory.mkdir(exist_ok=False)
    write(directory / "manifest.json", {"phase": phase, "model": MODELS[model_key], "selected_ids": [c["id"] for c in cases],
                                        "master_manifest_sha256": digest(MASTER / "manifest.json"), "configuration": manifest["configuration"]})
    print(f"Run: {directory.name}", flush=True)
    rows = []
    store = None
    preflight_error = None
    snapshot_after = None
    try:
        settings = get_settings()
        if not settings.qdrant_url or settings.embedding_provider != "gemini" or settings.embedding_gemini_model.removeprefix("models/") != "gemini-embedding-001":
            raise RuntimeError("Configured Qdrant and Gemini embedding-001 required; no substitute")
        embedding = ObservedEmbedding(create_embedding_engine(settings))
        store = ReadOnlyStore(embedding_provider=embedding)
        recorded_store = RecordedStore(store)
        hybrid = HybridRetriever(vector_store=recorded_store)
        if not hybrid.sync_bm25_from_vector_store():
            raise RuntimeError("Qdrant corpus empty or unreadable")
        corpus = sorted(hybrid.bm25_searcher.corpus_chunks, key=lambda c: c["chunk_id"])
        snapshot = {"chunk_count": len(corpus), "content_sha256": content_hash(corpus), "documents": sorted({c["doc_id"] for c in corpus})}
        write(directory / "corpus_before.json", snapshot)
        snapshot_path = MASTER / "live_corpus_lock.json"
        if snapshot_path.exists():
            if snapshot != read(snapshot_path):
                raise RuntimeError("Live corpus differs from first pilot")
        else:
            write(snapshot_path, snapshot)
        reranker = RerankerService()
        resolved = {"reranker": type(reranker._reranker).__name__, "reranker_model": getattr(reranker._reranker, "model_name", getattr(reranker._reranker, "model", None)),
                    "embedding": embedding.model, "dimensions": embedding.dimensions}
        write(directory / "resolved_components.json", resolved)
        if (MASTER / "components_lock.json").exists():
            if resolved != read(MASTER / "components_lock.json"):
                raise RuntimeError("Resolved retrieval components differ")
        else:
            write(MASTER / "components_lock.json", resolved)
        route = manifest["configuration"]["routing"][model_key]
        llm = create_llm_provider(settings.model_copy(update={"openrouter_model": MODELS[model_key], "openrouter_endpoint_order": ",".join(route)}), "openrouter")
        llm._client = llm._client.with_options(max_retries=0, timeout=60)
        provider = CapturedProvider(llm, MODELS[model_key])
        rewriter = ObservedRewriter(provider)
        with (directory / "case_results.jsonl").open("x", encoding="utf-8") as stream, (directory / "human_review.csv").open("x", encoding="utf-8", newline="") as review:
            writer = csv.writer(review)
            writer.writerow(["case_id", "query", "rewritten_query", "correctness", "metadata_correctness", "reviewer", "notes"])
            for index, case in enumerate(cases, 1):
                provider.events.clear()
                embedding.events.clear()
                recorded_store.errors.clear()
                rewriter.fallback_calls = 0
                started = time.perf_counter()
                analysis = await rewriter.analyze(case["query"], UserVehicleContext.model_validate(case["vehicle_context"]))
                rewrite_seconds = time.perf_counter() - started
                event = provider.events[0] if provider.events else {}
                payload, contract_error = raw_contract(event.get("raw_text", ""))
                error = event.get("error")
                truncated = event.get("stop_reason") == "length"
                model_matches = event.get("model") == MODELS[model_key]
                if not model_matches and not error:
                    error = "actual provider model differs or missing call"
                raw_contract_pass = bool(payload and not error and not truncated)
                ranked = []
                retrieval_status = "SKIPPED_OUT_OF_SCOPE"
                if not analysis.is_out_of_scope and not error and not truncated:
                    try:
                        fused = hybrid.retrieve(analysis=analysis, top_candidates=20)
                        candidates = reranker.rerank(query=analysis.rewritten_query, candidates=fused, top_k=15)
                        ranked = [c.model_dump(mode="json") for c in hybrid.select_context(candidates=candidates, analysis=analysis, top_k=5)]
                        retrieval_status = "LIVE_HYBRID"
                    except Exception as exc:  # noqa: BLE001 - Persist runtime failures as evaluation evidence.
                        logging.getLogger(__name__).warning("Retrieval failure recorded: %s", type(exc).__name__)
                        error = f"{type(exc).__name__}: {exc}"
                    if recorded_store.errors or hybrid._dense_disabled:
                        error = " | ".join(recorded_store.errors) or "dense disabled"
                        retrieval_status = "ERROR_OR_DENSE_FALLBACK"
                elif error or truncated:
                    retrieval_status = "SKIPPED_PROVIDER_FAILURE"
                if truncated:
                    error = error or "provider output truncated"
                row = {"case_id": case["id"], "query": case["query"], "vehicle_context": case["vehicle_context"],
                       "input_sha256": content_hash({"query": case["query"], "vehicle_context": case["vehicle_context"]}),
                       "analysis": analysis.model_dump(mode="json"), "raw_payload": payload, "raw_contract_error": contract_error,
                       "raw_contract_pass": raw_contract_pass, "runtime_fallback": bool(rewriter.fallback_calls),
                       "truncated": truncated, "anchor_checks": anchor_checks(case, analysis),
                       "category_draft_agrees": analysis.category == case["category_draft"] if case["category_draft"] else None,
                       "expected_doc_ids": case["relevant_doc_ids"], "ranked_doc_ids": [c["doc_id"] for c in ranked], "ranked_chunks": ranked,
                       "retrieval_status": retrieval_status, "provider_events": list(provider.events), "embedding_events": list(embedding.events),
                       "rewrite_seconds": rewrite_seconds, "total_seconds": time.perf_counter() - started, "error": error,
                       "semantic_preservation": "NOT_MEASURED", "metadata_semantic_correctness": "DRAFT_UNREVIEWED"}
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                writer.writerow([case["id"], case["query"], analysis.rewritten_query, "", "", "", ""])
                review.flush()
                print(f"[{model_key} {phase} {index}/{len(cases)}] {case['id']} raw={'PASS' if row['raw_contract_pass'] else 'FAIL'} anchors={'MATCH' if all(row['anchor_checks'].values()) else 'FLAG'} {'ERROR' if error else 'RECORDED'}", flush=True)
                if error:
                    break
                if index < len(cases):
                    await asyncio.sleep(3)
        after_corpus = sorted(store.get_all_chunks(), key=lambda c: c["chunk_id"])
        snapshot_after = content_hash(after_corpus)
        write(directory / "corpus_after.json", {"content_sha256": snapshot_after, "unchanged": snapshot_after == snapshot["content_sha256"]})
        if snapshot_after != snapshot["content_sha256"]:
            raise RuntimeError("Live corpus changed during run")
        await llm._client.close()
    except Exception as exc:  # noqa: BLE001 - Close partial runs without losing failure artifacts.
        logging.getLogger(__name__).warning("Run failure recorded: %s", type(exc).__name__)
        preflight_error = f"{type(exc).__name__}: {exc}"
    finally:
        if store is not None:
            store.client.close()
    metrics = summarize(rows, len(cases))
    metrics["preflight_error"] = preflight_error
    metrics["corpus_verified_after"] = bool(snapshot_after and not preflight_error)
    metrics["pilot_eligible"] = bool(phase == "pilot" and metrics["complete"] and not preflight_error and not metrics["errors"] and metrics["raw_contract_pass"] == len(cases) and not metrics["runtime_fallback_cases"] and metrics["anchor_all_match"] == len(cases) and metrics["actual_models"] == [MODELS[model_key]])
    write(directory / "metrics.json", metrics)
    write(directory / "preservation.json", preservation())
    with (directory / "report.md").open("x", encoding="utf-8") as report:
        report.write("# Rewrite development evaluation\n\nSemantic review deferred; draft anchor/category checks are not semantic accuracy. Retrieval uses unverified golden document IDs.\n\n```json\n" + json.dumps(metrics, ensure_ascii=False, indent=2) + "\n```\n")
    print(json.dumps(metrics, ensure_ascii=True), flush=True)
    return 2 if preflight_error or metrics["errors"] or not metrics["complete"] or metrics["raw_contract_pass"] != len(cases) or (phase == "pilot" and not metrics["pilot_eligible"]) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "pilot", "full"])
    parser.add_argument("model", nargs="?", choices=list(MODELS))
    args = parser.parse_args()
    logging.getLogger().setLevel(logging.WARNING)
    if args.phase == "prepare":
        prepare()
    elif args.model:
        raise SystemExit(asyncio.run(run(args.phase, args.model)))
    else:
        parser.error("model required for live phase")
