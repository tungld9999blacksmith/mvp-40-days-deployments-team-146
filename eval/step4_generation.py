"""Fixed-evidence generation screening; preserve every historical result."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import re

import step4_rewrite as common
from src.agents.tools.RAG.query.generator import (
    SYSTEM_PROMPT,
    GroundedAnswerGenerator,
)
from src.agents.tools.RAG.query.maintenance_gate import maintenance_evidence_gate
from src.agents.tools.RAG.query.policy_gate import vehicle_expiry_gate
from src.agents.tools.RAG.query.procedure_gate import procedure_evidence_gate
from src.agents.tools.RAG.query.schemas import GroundedAnswerPayload
from src.agents.tools.RAG.query.source_gate import source_evidence_gate
from src.infrastructure.llm.factory import create_llm_provider
from step4_rewrite_contract_revision import RevisionProvider
from tests.evaluation_v2 import generation_replay as replay

ROOT = common.ROOT
MASTER = ROOT / "eval/results/step4_generation_comparison_20261008_23"
BASELINE = ROOT / "eval/results/rag_v2_full_100_mistral_routed_20261007_01"
MODELS = {"mistral": "mistralai/mistral-small-2603", "gemma": "google/gemma-4-26b-a4b-it"}
IDS = common.GOLDEN_IDS + ["M10", "M25", "W08", "B05", "P11", "PR11"]
PILOT_IDS = ["M01", "M07", "W02", "B11", "B16", "PR03"]


def run_name(phase, key):
    return f"step4_generation_{phase}_{key}_20261008_23"


def raw_contract(text):
    try:
        payload = json.loads(text, object_pairs_hook=common.reject_duplicates)
        payload = GroundedAnswerPayload.model_validate(payload, strict=True).model_dump()
        if not payload["answer"].strip():
            raise ValueError("Empty raw answer")
        return payload, None
    except (ValueError, TypeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def citation_structure(payload, count):
    if payload is None:
        return None
    declared = set(payload["cited_doc_indexes"])
    normalized = GroundedAnswerGenerator._normalize_citation_tags(payload["answer"])
    referenced = {int(i) for i in re.findall(r"\[Tài liệu\s+(\d+)\]", normalized, re.IGNORECASE)}
    return {"out_of_range_indexes": sorted(i for i in declared | referenced if i < 1 or i > count),
            "declared_and_answer_tags_match": declared == referenced,
            "scope": "STRUCTURAL_ONLY_NOT_CLAIM_SUPPORT"}


def expected_gate(item):
    args = (item["analysis"], item["context"], item["citations"])
    response = source_evidence_gate(*args) or procedure_evidence_gate(*args) or maintenance_evidence_gate(*args) or vehicle_expiry_gate(*args)
    return response.metadata.get("reason", "unspecified") if response else None


def inputs():
    _, rows, golden = replay.validate_baseline(BASELINE, common.GOLDEN, allow_prompt_change=True)
    by_id = {r["case_id"]: r for r in rows}
    return {identifier: replay.fixed_input(by_id[identifier], golden[identifier]) for identifier in IDS}


def preservation():
    manifest = common.read(MASTER / "manifest.json")
    checks = {name: common.verify(common.read(MASTER / filename)) for name, filename in (
        ("history", "protected_previous_files.json"), ("corpus", "protected_corpus.json"),
        ("source", "source_revision.json"),
    )}
    checks["env_unchanged"] = common.digest(ROOT / ".env") == manifest["env_sha256"]
    checks["subset_unchanged"] = common.digest(MASTER / "selected_cases.json") == manifest["selected_cases_sha256"]
    checks["rubric_unchanged"] = common.digest(MASTER / "generation_rubric.json") == manifest["rubric_sha256"]
    checks["inputs_unchanged"] = common.digest(MASTER / "fixed_inputs.json") == manifest["fixed_inputs_sha256"]
    if not all(c["unchanged"] for c in (checks["history"], checks["corpus"], checks["source"])) or not all(checks[k] for k in ("env_unchanged", "subset_unchanged", "rubric_unchanged", "inputs_unchanged")):
        raise RuntimeError("Frozen evidence/source/env changed")
    return checks


def prepare():
    before = common.read(MASTER / "source_before.json")
    changed = common.verify(before)["changed"]
    if {p.replace("\\", "/") for p in changed} != {"backend/src/agents/tools/RAG/query/generator.py"}:
        raise RuntimeError(f"Unexpected source change: {changed}")
    source = {name: common.digest(ROOT / name) for name in before}
    for name in ("eval/step4_generation.py", "eval/step4_generation_report.py", "eval/test_step4_generation.py"):
        source[name] = common.digest(ROOT / name)
    common.write(MASTER / "source_revision.json", source)
    fixed = inputs()
    selected = []
    frozen = {}
    for identifier, item in fixed.items():
        selected.append({"id": identifier, "query": item["question"], "source_file": str(common.GOLDEN.relative_to(ROOT)),
                         "expected_preprovider_gate": expected_gate(item), "golden_labels": "UNREVIEWED_DRAFT"})
        frozen[identifier] = {"input": item["frozen"], "fixed_input_sha256": item["fixed_input_sha256"],
                              "evidence_sha256": common.content_hash({k: v for k, v in item["frozen"].items() if k != "system_prompt"}),
                              "messages": [m.model_dump() for m in GroundedAnswerGenerator.build_messages(item["analysis"], item["context"], item["vehicle"])]}
    common.write(MASTER / "selected_cases.json", selected)
    common.write(MASTER / "fixed_inputs.json", frozen)
    common.write(MASTER / "generation_rubric.json", {
        "status": "DEVELOPMENT_NOT_ACCEPTANCE", "pilot_ids": PILOT_IDS,
        "pilot_gate": "6 complete, zero provider/truncation/offline-summary/strict-raw-contract failures, exact requested model on every call, expected deterministic preprovider gates and citation ID membership",
        "raw_contract": "exact four existing GroundedAnswerPayload fields, strict JSON/types/enums, no duplicate keys/Markdown, nonempty answer; original outputs never corrected for scoring",
        "citation_structure": "range/tag declaration diagnostics only; citation identity membership is not claim support",
        "full": "one fresh 30-original-golden-question run per eligible model; don't pool pilot/full as independent cases",
        "stop": "first provider/model/retrieval-independent execution error or truncation; raw contract failures recorded, no hidden retries",
        "semantic_review": "DEFERRED_BY_USER; blank labels; correctness/claim support not measured",
    })
    env_hash = common.digest(ROOT / ".env")
    if env_hash != common.read(MASTER / "env_before.json")["sha256"]:
        raise RuntimeError("Env changed during preparation")
    old_pilot = ROOT / "eval/results/step4_generation_gemma_20261008_14"
    old_rows = [json.loads(line) for line in (old_pilot / "case_results.jsonl").read_text(encoding="utf-8").splitlines()]
    old_m01 = next(r for r in old_rows if r["case_id"] == "M01")
    old_fixed = {r["case_id"]: r for r in (json.loads(line) for line in (old_pilot / "fixed_inputs.jsonl").read_text(encoding="utf-8").splitlines())}
    same_evidence = all(old_fixed[i]["evidence_sha256"] == frozen[i]["evidence_sha256"] for i in PILOT_IDS)
    if not same_evidence:
        raise RuntimeError("Old pilot evidence differs")
    common.write(MASTER / "old_gemma_m01_diagnosis.json", {
        "original_run": str(old_pilot.relative_to(ROOT)), "case_id": "M01",
        "provider_error": old_m01["provider_events"][0]["error"],
        "raw_markdown": old_m01["provider_events"][0]["raw_text"].startswith("```"),
        "schema_request_already_present": bool(old_m01["provider_events"][0]["request_parameters"]["extra"].get("response_format")),
        "runtime_salvaged_payload": True, "original_verdict_preserved": True,
        "same_six_evidence_hashes": same_evidence,
        "revision": "only production generator output-format prompt clarified; schema/runtime/parser/scoring labels unchanged",
    })
    common.write(MASTER / "manifest.json", {
        "scope": "STEP4_GENERATION_FIXED_EVIDENCE_DEVELOPMENT", "models": MODELS, "selected_ids": IDS,
        "pilot_ids": PILOT_IDS, "selected_cases_sha256": common.digest(MASTER / "selected_cases.json"),
        "fixed_inputs_sha256": common.digest(MASTER / "fixed_inputs.json"), "rubric_sha256": common.digest(MASTER / "generation_rubric.json"),
        "env_sha256": env_hash, "source_revision_sha256": common.digest(MASTER / "source_revision.json"),
        "changed_runtime_paths": changed, "baseline": str(BASELINE.relative_to(ROOT)),
        "baseline_manifest_sha256": common.digest(BASELINE / "manifest.json"),
        "baseline_results_sha256": common.digest(BASELINE / "case_results.jsonl"),
        "golden_sha256": common.digest(common.GOLDEN), "prompt_sha256": common.content_hash(SYSTEM_PROMPT),
        "configuration": {"temperature": .1, "max_tokens": 3000, "timeout": 60, "sdk_retries": 0, "delay_seconds": 3,
                          "response_format": "json_schema", "require_parameters": True, "retrieval_calls": 0,
                          "embedding_calls": 0, "routing": {"mistral": ["mistral/us", "mistral/eu"], "gemma": []}},
        "subset": "same 24 golden questions as Rewrite +6 existing golden questions; not v2.1 replacement or holdout",
        "review": "DEFERRED_BY_USER", "production_model_change": False, "gpt4o": "EXCLUDED_ALL_STAGES", "write": "INACTIVE",
        "network_payload": "same 1-5 saved Qdrant evidence blocks per question previously authorized for full RAG; no new retrieval",
    })
    print(json.dumps({"prepared_original_queries": len(fixed), "pilot_queries": len(PILOT_IDS),
                      "expected_gates": {r["id"]: r["expected_preprovider_gate"] for r in selected if r["expected_preprovider_gate"]}}, ensure_ascii=True), flush=True)


def technical_pass(row):
    return not row["error"] and row["gate_matches_expected"] and row["citation_id_membership_valid"] and (row["preprovider_gate"] or row["raw_contract_pass"])


async def run(phase, key):
    preservation()
    if phase == "full":
        p = ROOT / "eval/results" / run_name("pilot", key)
        if not common.verify(common.read(p / "closed_run_hashes.json"))["unchanged"] or not common.read(p / "metrics.json")["pilot_eligible"]:
            raise RuntimeError("Pilot gate not eligible")
    manifest = common.read(MASTER / "manifest.json")
    expected = {r["id"]: r["expected_preprovider_gate"] for r in common.read(MASTER / "selected_cases.json")}
    frozen = common.read(MASTER / "fixed_inputs.json")
    fixed = inputs()
    if any(item["fixed_input_sha256"] != frozen[i]["fixed_input_sha256"] for i, item in fixed.items()):
        raise RuntimeError("Reconstructed evidence changed")
    selected = PILOT_IDS if phase == "pilot" else IDS
    folder = ROOT / "eval/results" / run_name(phase, key)
    folder.mkdir(exist_ok=False)
    common.write(folder / "manifest.json", {"phase": phase, "model": MODELS[key], "selected_ids": selected,
                                           "master_manifest_sha256": common.digest(MASTER / "manifest.json"), "configuration": manifest["configuration"]})
    common.write(folder / "fixed_inputs.json", {i: frozen[i] for i in selected})
    route = manifest["configuration"]["routing"][key]
    settings = common.get_settings().model_copy(update={"openrouter_model": MODELS[key], "openrouter_endpoint_order": ",".join(route)})
    llm = create_llm_provider(settings, "openrouter")
    llm._client = llm._client.with_options(max_retries=0, timeout=60)
    provider = RevisionProvider(llm, MODELS[key])
    rows = []
    print(f"Run: {folder.name}", flush=True)
    with (folder / "case_results.jsonl").open("x", encoding="utf-8") as stream, (folder / "human_review.csv").open("x", encoding="utf-8", newline="") as review:
        writer = csv.writer(review)
        writer.writerow(["case_id", "question", "answer", "correctness", "citation_support", "reviewer", "notes"])
        for index, identifier in enumerate(selected, 1):
            item = fixed[identifier]
            row = await replay.evaluate(item, provider)
            event = row["provider_events"][0] if row["provider_events"] else None
            payload, raw_error = raw_contract(event.get("raw_text", "")) if event else (None, None)
            row.update(raw_payload=payload, raw_contract_pass=bool(payload and event and not event.get("error") and event.get("stop_reason") != "length"),
                       raw_contract_error=raw_error, preprovider_gate=not bool(event),
                       gate_matches_expected=(not bool(event)) == (expected[identifier] is not None),
                       citation_structure=citation_structure(payload, len(item["citations"])))
            if event and payload is None and not row["error"]:
                row["error"] = "Raw output violates locked JSON contract"
            if row["provider_models"] and row["provider_models"] != [MODELS[key]]:
                row["error"] = (row["error"] or "") + " | Returned model differs"
            if not row["gate_matches_expected"]:
                row["error"] = (row["error"] or "") + " | Deterministic gate differs from lock"
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            writer.writerow([identifier, item["question"], row["answer"], "", "", "", ""])
            print(f"[{key} {phase} {index}/{len(selected)}] {identifier} {'GATE' if row['preprovider_gate'] else 'PROVIDER'} {'ERROR' if row['error'] else 'RECORDED'}", flush=True)
            preservation()
            if any(e.get("error") or e.get("stop_reason") == "length" for e in row["provider_events"]) or "Returned model differs" in (row["error"] or ""):
                break
            if index < len(selected):
                await asyncio.sleep(3)
    metrics = replay.summarize(rows)
    metrics.update(selected=len(selected), complete=len(rows) == len(selected),
                   preprovider_cases=sum(r["preprovider_gate"] for r in rows),
                   strict_raw_contract_pass=sum(r["raw_contract_pass"] for r in rows),
                   technical_pass=sum(technical_pass(r) for r in rows),
                   membership_valid=sum(r["citation_id_membership_valid"] for r in rows),
                   actual_models=sorted({m for r in rows for m in r["provider_models"]}),
                   missing_cost_receipts=metrics["provider_calls"] - metrics["cost_receipts"],
                   retrieval_calls=0, embedding_calls=0, independent_labels=0)
    metrics["pilot_eligible"] = bool(phase == "pilot" and metrics["complete"] and metrics["technical_pass"] == len(selected) and metrics["actual_models"] == [MODELS[key]])
    common.write(folder / "metrics.json", metrics)
    common.write(folder / "preservation.json", preservation())
    with (folder / "report.md").open("x", encoding="utf-8") as stream:
        stream.write("# Fixed-evidence generation development\n\nNo retrieval/embedding; raw JSON remains unmodified. Preprovider gates are runtime outputs, not model successes. Citation identity is not claim support. Semantic review deferred.\n\n```json\n" + json.dumps(metrics, indent=2) + "\n```\n")
    common.write(folder / "closed_run_hashes.json", common.hashes([folder]))
    print(json.dumps(metrics, ensure_ascii=True), flush=True)
    return 0 if metrics["complete"] and metrics["technical_pass"] == len(selected) else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "pilot", "full"])
    parser.add_argument("model", nargs="?", choices=list(MODELS))
    args = parser.parse_args()
    logging.disable(logging.INFO)
    if args.phase == "prepare":
        prepare()
    elif args.model:
        raise SystemExit(asyncio.run(run(args.phase, args.model)))
    else:
        parser.error("model required")
