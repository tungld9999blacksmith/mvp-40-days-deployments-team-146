"""Fresh development pilot/full after content fixes; immutable old outputs."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import patch

import step4_rag_preservation_retry as previous

common = previous.common
ROOT = previous.ROOT
MASTER = ROOT / "eval/results/agent_content_followup_20261009_48"
ORIGINAL = ROOT / "eval/results/rag_evidence_preservation_full_20261008_29"
MODELS = previous.MODELS
PILOT_IDS = ["COST-06", "RAG-056", "GUARD-07", "RAG-007", "RAG-027", "BOOK-19", "REMINDER-03", "MAINT-01"]
CHANGES = {
    "backend/src/agents/business_grounding.py",
    "backend/src/agents/guardrails.py",
    "backend/src/agents/tools/RAG/query/procedure_gate.py",
}


def preservation():
    m = common.read(MASTER / "manifest.json")
    checks = {key: common.verify(common.read(MASTER / filename)) for key, filename in (
        ("history", "protected_previous_files.json"), ("corpus", "protected_corpus.json"), ("source", "source_revision.json"),
    )}
    checks.update(env_unchanged=common.digest(ROOT / ".env") == m["env_sha256"],
                  dataset_unchanged=common.digest(common.DATASET) == m["dataset_sha256"],
                  rubric_unchanged=common.digest(MASTER / "rubric.json") == m["rubric_sha256"],
                  cases_unchanged=common.digest(MASTER / "selected_cases.json") == m["selected_cases_sha256"])
    if not all(v["unchanged"] if isinstance(v, dict) else v for v in checks.values()):
        raise RuntimeError("Frozen conditions or historical results changed")
    return checks


def prepare():
    for name in ("closed_master_hashes.json", "completed_producer_hashes.json"):
        if not common.verify(common.read(ORIGINAL / name))["unchanged"]:
            raise RuntimeError("Closed original benchmark changed")
    review = ROOT / "eval/results/automatic_review_20261008_47"
    if not common.verify(common.read(review / "closed_master_hashes.json"))["unchanged"]:
        raise RuntimeError("Closed original review changed")
    if not common.verify(common.read(MASTER / "protected_previous_files.json"))["unchanged"]:
        raise RuntimeError("Historical files changed during revision")
    before = {name.replace("\\", "/"): value for name, value in common.read(MASTER / "source_before.json").items()}
    changed = set(common.verify(before)["changed"])
    if changed != CHANGES:
        raise RuntimeError(f"Unexpected revision files: {changed}")
    for name in CHANGES:
        if common.digest(MASTER / "source_before" / name) != before[name]:
            raise RuntimeError("Previous source copy does not match its frozen hash")
    env = common.digest(ROOT / ".env")
    if env != common.read(MASTER / "env_before.json")["sha256"]:
        raise RuntimeError("Environment changed during revision")
    xml = ET.parse(MASTER / "offline_tests_retry.xml").getroot()
    suites = list(xml.iter("testsuite"))
    if sum(int(s.get("tests", 0)) for s in suites) != 66 or any(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites):
        raise RuntimeError("Focused offline regression is not complete")
    cases = common.read(ORIGINAL / "selected_cases.json")
    current = {c["id"]: c for c in common.read(common.DATASET)["cases"]}
    if len(cases) != 30 or any(c != current[c["id"]] for c in cases):
        raise RuntimeError("Original 30 case contents changed")
    source = {name: common.digest(ROOT / name) for name in before}
    for name in ("eval/agent_content_followup.py", "eval/agent_content_followup_report.py", "eval/test_agent_content_followup.py"):
        source[name] = common.digest(ROOT / name)
    common.write(MASTER / "source_revision.json", source)
    common.write(MASTER / "source_change_audit.json", {"changed": sorted(changed), "before_source_copies_preserved": True})
    common.write(MASTER / "selected_cases.json", cases)
    for name in ("live_corpus_lock.json", "components_lock.json"):
        common.write(MASTER / name, common.read(ORIGINAL / name))
    common.write(MASTER / "rubric.json", {
        "scope": "DEVELOPMENT_NOT_ACCEPTANCE", "technical_gates": "same strict provider/arguments/JSON/retrieval/safety/RAG preservation gates as revision29",
        "new_content_gates": "COST06 direct price-source explanation from validated estimate; RAG056 complete one-chunk rescue steps quoted with uncertainty if available; GUARD07 no invented numeric warranty in source-free refusal",
        "limitations": "narrow regression assertions, not general semantic accuracy or human/source adjudication",
        "stop": "first technical/content/safety/provider error or missing LLM receipt; no retry/rescore",
    })
    original_manifest = common.read(ORIGINAL / "manifest.json")
    common.write(MASTER / "manifest.json", original_manifest | {
        "date": "2026-10-09", "scope": "CONTENT_FOLLOWUP_DEVELOPMENT_PILOT8_AND_FULL30",
        "selected_ids": [c["id"] for c in cases], "pilot_ids": PILOT_IDS,
        "source_revision_sha256": common.digest(MASTER / "source_revision.json"),
        "selected_cases_sha256": common.digest(MASTER / "selected_cases.json"),
        "rubric_sha256": common.digest(MASTER / "rubric.json"), "env_sha256": env,
        "dataset_sha256": common.digest(common.DATASET),
        "receipt_caps_usd": {"pilot_both_configurations": .04, "full_both_configurations": .10},
        "budget_boundary": "observed Agent/Rewrite/Generation receipts only; embedding receipts unavailable; bounded per-case calls and no SDK retries",
        "selection": "same exposed development cases; no new golden/holdout; pilot is a subset of full, do not pool",
        "changes": sorted(CHANGES), "historical_review": "automatic_review_20261008_47 unchanged; prior labels not rescored",
        "review": "AUTOMATIC_REVIEW_TO_BE_RUN_SEPARATELY; NO_HUMAN_LABELS",
        "independent_labels": 0, "production_acceptance": False,
    })
    common.write(MASTER / "prepared_preservation.json", preservation())
    print(json.dumps({"prepared": str(MASTER), "pilot_per_configuration": 8, "full_per_configuration": 30}), flush=True)


def analyze(row):
    result = previous.analyze(row)
    failures = list(result["failures"])
    answer = row["trace"]["answer"]
    if row["case_id"] == "COST-06":
        if "Phân biệt nguồn giá" not in answer:
            failures.append("Missing direct explanation of workshop versus reference prices")
        if "chưa xác định giá đã bao gồm VAT" not in answer:
            failures.append("VAT uncertainty lost")
    if row["case_id"] == "RAG-056":
        if "Chưa xác định được quy trình" in answer and "Bước 1:" in answer:
            failures.append("Contradictory rescue-procedure denial")
        for event in row["live"]["rag"]:
            response = event.get("response", {})
            if (response.get("metadata", {}).get("reason") == "battery_rescue_documented_steps_only"
                    and (not response["fallback_required"] or response["confidence"] != "low" or "chưa xác minh hiệu lực" not in answer)):
                failures.append("Rescue source uncertainty removed")
    if row["case_id"] == "GUARD-07" and not row["trace"]["calls"] and re.search(r"\d", answer):
        failures.append("Source-free warranty refusal invented a number")
    return result | {"technical_pass": not failures, "failures": failures, "content_checks": "NARROW_REGRESSION_ONLY"}


def metrics(rows, ids, error=None):
    previous.IDS = ids
    return previous.metrics(rows, error)


def phase_cost(phase):
    return sum(common.read(p)["known_total_llm_cost_usd"] for p in MASTER.glob(f"{phase}_*/metrics.json"))


async def run_configuration(phase, key):
    preservation()
    m = common.read(MASTER / "manifest.json")
    ids = m["pilot_ids"] if phase == "pilot" else m["selected_ids"]
    cases = {c["id"]: c for c in common.read(MASTER / "selected_cases.json")}
    cap = m["receipt_caps_usd"][f"{phase}_both_configurations"]
    paid_before = phase_cost(phase)
    directory = MASTER / f"{phase}_{key}"
    directory.mkdir(exist_ok=False)
    common.write(directory / "manifest.json", m | {"phase": phase, "configuration_key": key, "selected_ids": ids})
    rows, store, providers = [], None, []
    preflight_error = None
    try:
        if paid_before >= cap:
            raise RuntimeError("Phase receipt budget exhausted before configuration")
        settings = common.get_settings()
        if settings.embedding_provider != "gemini" or settings.embedding_dimensions != 3072:
            raise RuntimeError("Original Gemini embedding-001/3072 required")
        embedding = common.ObservedEmbedding(common.create_embedding_engine(settings))
        store = common.ReadOnlyStore(embedding_provider=embedding)
        before = previous.corpus_snapshot(store)
        common.write(directory / "corpus_before.json", before)
        if before != common.read(MASTER / "live_corpus_lock.json"):
            raise RuntimeError("Live corpus differs from baseline")
        recorded = common.RecordedStore(store)
        hybrid = common.HybridRetriever(vector_store=recorded)
        if not hybrid.sync_bm25_from_vector_store():
            raise RuntimeError("BM25 live corpus unavailable")
        reranker = common.RerankerService()
        components = {"reranker": type(reranker._reranker).__name__, "reranker_model": getattr(reranker._reranker, "model_name", getattr(reranker._reranker, "model", None)), "embedding": embedding.model, "dimensions": embedding.dimensions}
        common.write(directory / "resolved_components.json", components)
        if components != common.read(MASTER / "components_lock.json"):
            raise RuntimeError("Resolved retrieval components differ")
        for _ in range(2):
            inner = common.create_llm_provider(settings.model_copy(update={"openrouter_model": previous.MISTRAL, "openrouter_endpoint_order": "mistral/us,mistral/eu"}), "openrouter")
            inner._client = inner._client.with_options(max_retries=0, timeout=60)
            providers.append(previous.RevisionProvider(inner, previous.MISTRAL))
        rewrite, generate = providers
        rewriter = common.ObservedRewriter(rewrite)
        pipeline = previous.LiveRAG(previous.RAGPipeline(rewriter=rewriter, hybrid_retriever=hybrid, reranker=reranker, generator=previous.GroundedAnswerGenerator(generate)))
        args = SimpleNamespace(max_tokens=2048, timeout=60, endpoint_order=["mistral/us", "mistral/eu"] if key == "base" else [])
        original_provider = previous.runner.provider

        class LiveSandbox(previous.Sandbox):
            def __init__(self, case):
                super().__init__(case, rag_pipeline=pipeline)

        with (directory / "case_results.jsonl").open("x", encoding="utf-8") as stream, (directory / "human_review.csv").open("x", encoding="utf-8", newline="") as review:
            writer = csv.writer(review)
            writer.writerow(["case_id", "correctness", "citation_support", "task_success", "reviewer", "notes"])
            for index, identifier in enumerate(ids, 1):
                if paid_before + metrics(rows, ids)["known_total_llm_cost_usd"] >= cap:
                    preflight_error = "Phase receipt budget exhausted; remaining cases not attempted"
                    break
                capture = previous.AgentCapture()
                for provider in providers:
                    provider.events.clear()
                embedding.events.clear()
                recorded.errors.clear()
                rewriter.fallback_calls = 0
                pipeline.reset()

                def agent_provider(model, arguments, observer=capture):
                    return original_provider(model, arguments).model_copy(update={"callbacks": [observer]})

                with patch.object(previous.runner, "Sandbox", LiveSandbox), patch.object(previous.runner, "provider", agent_provider):
                    row = await previous.runner.evaluate(cases[identifier], MODELS[key], args, previous.runner.build_graph)
                row.update({"agent_model": MODELS[key], "configuration_key": key, "live": {
                    "agent": capture.events, "rewrite": list(rewrite.events), "generation": list(generate.events),
                    "embedding": list(embedding.events), "rag": list(pipeline.events), "retrieval_errors": list(recorded.errors),
                    "dense_disabled": hybrid._dense_disabled, "rewrite_fallback_calls": rewriter.fallback_calls,
                }})
                row["configuration_gate"] = analyze(row)
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                stream.flush()
                writer.writerow([identifier, "", "", "", "", ""])
                review.flush()
                print(f"[{phase} {key} {index}/{len(ids)}] {identifier} {'PASS' if row['configuration_gate']['technical_pass'] else 'FAIL'}", flush=True)
                current = metrics(rows, ids)
                if not row["configuration_gate"]["technical_pass"] or any(current["missing_receipts_by_stage"].values()):
                    break
                await asyncio.sleep(3)
        after = previous.corpus_snapshot(store)
        common.write(directory / "corpus_after.json", after | {"unchanged": after == before})
        if before != after:
            raise RuntimeError("Live corpus changed")
    except Exception as exc:  # noqa: BLE001 -- close partial results instead of retrying
        preflight_error = f"{type(exc).__name__}: {exc}"
    finally:
        for provider in providers:
            await provider.inner._client.close()
        if store:
            store.client.close()
    result = metrics(rows, ids, preflight_error)
    common.write(directory / "metrics.json", result)
    common.write(directory / "preservation.json", preservation())
    common.write(directory / "closed_run_hashes.json", common.hashes([directory]))
    print(json.dumps({"phase": phase, "configuration": key, **result}), flush=True)
    return result["complete"] and result["technical_pass"] == len(ids) and not preflight_error and not any(result["missing_receipts_by_stage"].values())


async def run(phase):
    if phase == "full":
        for key in MODELS:
            folder = MASTER / f"pilot_{key}"
            if not common.verify(common.read(folder / "closed_run_hashes.json"))["unchanged"]:
                raise RuntimeError("Closed pilot changed")
            m = common.read(folder / "metrics.json")
            if not m["complete"] or m["technical_pass"] != 8 or m["preflight_error"] or any(m["missing_receipts_by_stage"].values()):
                raise RuntimeError("Both pilots must be eligible before full")
    for key in MODELS:
        if not await run_configuration(phase, key):
            return 2
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "pilot", "full"])
    args = parser.parse_args()
    logging.disable(logging.WARNING)
    if args.phase == "prepare":
        prepare()
    else:
        raise SystemExit(asyncio.run(run(args.phase)))
