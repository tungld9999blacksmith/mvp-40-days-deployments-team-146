"""Run/report a preserved development shortlist smoke without application edits."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "eval/results/step4_smoke_30_20261008_14"
DATASET = ROOT / "eval/test_cases/agent_cases_v2_1.json"
BASELINE = "eval/results/rag_v2_full_100_mistral_routed_20261007_01"
MODELS = {"mistral": "mistralai/mistral-small-2603", "gemma": "google/gemma-4-26b-a4b-it"}
IDS = ["RAG-001", "RAG-007", "RAG-027", "RAG-056", "RAG-061", "RAG-083",
       "GUARD-01", "GUARD-05", "GUARD-07", "GUARD-09", "GUARD-19",
       "BOOK-03", "BOOK-05", "BOOK-15", "BOOK-18", "BOOK-19", "BOOK-22", "BOOK-25", "BOOK-33",
       "MAINT-01", "MAINT-07", "MAINT-11", "COST-01", "COST-06", "COST-11",
       "REMINDER-03", "REMINDER-05", "REMINDER-10", "REMINDER-12", "REMINDER-16"]
RAG_IDS = ["M01", "M07", "W02", "B11", "B16", "PR03"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    with (MASTER / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def hashes(folders):
    return {str(p.relative_to(ROOT)): digest(p) for folder in folders if folder.exists()
            for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def verify(mapping):
    changed = [name for name, sha in mapping.items() if not (ROOT / name).is_file() or digest(ROOT / name) != sha]
    return {"files_verified": len(mapping), "unchanged": not changed, "changed": changed}


def read(name):
    return json.loads((MASTER / name).read_text(encoding="utf-8"))


def run_name(key):
    return f"step4_{key}_20261008_14"


def command(key):
    kind, model_key = key.rsplit("_", 1)
    result = [str(ROOT / ".venv/Scripts/python.exe")]
    if kind in {"preflight", "agent"}:
        result += ["backend/tests/test_agents/evaluate_agent.py", "--dataset", str(DATASET),
                   "--model", MODELS[model_key], "--max-tokens", "2048", "--repeats", "1", "--delay", "1"]
        for identifier in (["BOOK-05"] if kind == "preflight" else IDS):
            result += ["--case", identifier]
    elif kind == "generation":
        result += ["backend/tests/test_agents/test_rag/evaluation/evaluate_generation.py", "--baseline", BASELINE,
                   "--model", MODELS[model_key], "--allow-prompt-change", "--delay", "1"]
        for identifier in RAG_IDS:
            result += ["--case", identifier]
    else:
        raise ValueError(key)
    if model_key == "mistral":
        result += ["--endpoint-order", "mistral/us", "--endpoint-order", "mistral/eu"]
    return result + ["--run-name", run_name(key)]


def prepare():
    # Capture every existing evaluation artifact before creating a new run.
    protected = hashes([ROOT / "eval/results", ROOT / "eval/test_cases",
                        ROOT / "backend/tests/test_agents/evaluationLLM/results",
                        ROOT / "backend/tests/test_agents/test_rag/evaluation", ROOT / "backend/tests/evaluation"])
    MASTER.mkdir(exist_ok=False)
    write("protected_previous_files.json", protected)
    write("protected_corpus.json", hashes([ROOT / "data/knowledge/raw", ROOT / "data/knowledge/processed"]))
    source = hashes([ROOT / "backend/src/agents", ROOT / "backend/src/infrastructure/llm",
                     ROOT / "backend/tests/evaluation_v2", ROOT / "eval/test_cases"])
    for name in ["backend/src/config.py", "backend/tests/test_agents/evaluate_agent.py",
                 "backend/tests/test_agents/test_rag/evaluation/evaluate_generation.py", "eval/step4_smoke.py"]:
        source[name] = digest(ROOT / name)
    write("source_revision.json", source)
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = [c for c in dataset["cases"] if c["id"] in IDS]
    assert len(cases) == 30 and [c["id"] for c in cases] == IDS
    assert [c["golden"]["id"] for c in cases if c["category"] == "rag"] == RAG_IDS
    write("selected_cases.json", cases)
    keys = [f"{kind}_{model}" for kind in ("preflight", "agent", "generation") for model in MODELS]
    write("manifest.json", {
        "scope": "development_shortlist_smoke_only", "date_asia_saigon": "2026-10-08",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        "env_sha256": digest(ROOT / ".env"), "dataset_sha256": digest(DATASET),
        "models": MODELS, "selected_ids": IDS, "category_counts": dict(Counter(c["category"] for c in cases)),
        "generation_ids": RAG_IDS, "review_status": "DEFERRED_BY_USER", "independent_labels": 0,
        "agent_conditions": {"max_tokens": 2048, "temperature": .2, "repeats": 1, "timeout": 60,
                             "clock": dataset["clock"], "scorer_version": "2.2", "rag": "fixture_orchestration_only",
                             "services": "isolated SQLite/FakeAsyncRedis", "seed": "not set/supported"},
        "generation_conditions": {"max_tokens": 3000, "temperature": .1, "response_format": "json_schema",
                                  "evidence": BASELINE, "retrieval_calls": 0},
        "differences": ["Mistral endpoint preference mistral/us,mistral/eu; Gemma automatic routing",
                        "Fixture UUIDs are generated separately; compare placeholder roles/workshop/date/time, not literal UUID equality",
                        "Sequential model runs; one repeat does not measure variance or control time-dependent provider load"],
        "selection": "Purposive coverage including known development failures; not random or held-out",
        "commands": {key: command(key) for key in keys},
        "side_effects": {"production_db": False, "real_email": False, "corpus_mutation": False,
                         "env_write": False, "app_restart": False, "write_reviewer": False},
    })
    print(f"Prepared {MASTER}; 30 cases/model, six additional generation checks/model", flush=True)


def execute(key):
    manifest = read("manifest.json")
    if key not in manifest["commands"]:
        raise ValueError("Unknown run key")
    checks = {"source": verify(read("source_revision.json")), "previous": verify(read("protected_previous_files.json")),
              "env_unchanged": digest(ROOT / ".env") == manifest["env_sha256"]}
    if not checks["source"]["unchanged"] or not checks["previous"]["unchanged"] or not checks["env_unchanged"]:
        raise RuntimeError("Frozen conditions changed")
    if not key.startswith("preflight_"):
        model = key.rsplit("_", 1)[1]
        preflight = ROOT / "eval/results" / run_name("preflight_" + model)
        rows = load_rows(preflight)
        if len(rows) != 1 or rows[0]["trace"].get("error") or not rows[0]["metrics"]["task_passed"]:
            raise RuntimeError("Preflight did not pass; preserve failure and do not start batch")
    # Opening exclusively also prevents accidentally rerunning a completed key.
    with (MASTER / f"{key}_stdout.log").open("x", encoding="utf-8") as log:
        proc = subprocess.Popen(manifest["commands"][key], cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
        exit_code = proc.wait()
    write(f"{key}_execution.json", {"exit_code": exit_code, "run_name": run_name(key)})
    print(f"Recorded {key}: exit {exit_code}", flush=True)


def load_rows(folder):
    path = folder / "case_results.jsonl"
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()] if path.exists() else []


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)] if values else None


def finish():
    manifest = read("manifest.json")
    models = {}
    failures = []
    for key, model in MODELS.items():
        agent_folder = ROOT / "eval/results" / run_name("agent_" + key)
        agent = load_rows(agent_folder)
        generation_folder = ROOT / "eval/results" / run_name("generation_" + key)
        generation = load_rows(generation_folder)
        categories = {}
        for category, selected in manifest["category_counts"].items():
            rows = [r for r in agent if r["category"] == category]
            categories[category] = {"passed": sum(r["metrics"]["task_passed"] for r in rows),
                                    "attempted": len(rows), "selected": selected}
        for row in agent:
            if not row["metrics"]["task_passed"] or row["metrics"]["raw_argument_errors"]:
                failures.append({"model": model, "scope": "agent", "case_id": row["case_id"],
                                 "metrics": row["metrics"], "error": row["trace"].get("error"), "answer": row["trace"]["answer"]})
        for row in generation:
            if row["error"]:
                failures.append({"model": model, "scope": "generation", "case_id": row["case_id"], "error": row["error"], "answer": row["answer"]})
        latencies = [r["trace"]["latency_seconds"] for r in agent]
        agent_costs = [r["trace"].get("provider_cost_usd") for r in agent]
        events = [e for r in generation for e in r["provider_events"]]
        gen_costs = [e.get("usage", {}).get("cost_usd") for e in events]
        costs = agent_costs + gen_costs
        known = [c for c in costs if isinstance(c, (int, float))]
        models[key] = {
            "model": model, "agent": {
                "attempted": len(agent), "selected": 30, "complete": len(agent) == 30,
                "passed": sum(r["metrics"]["task_passed"] for r in agent),
                "errors": sum(bool(r["trace"].get("error")) for r in agent),
                "safety_violations": sum(len(r["metrics"]["safety_violations"]) for r in agent),
                "raw_argument_error_cases": sum(bool(r["metrics"]["raw_argument_errors"]) for r in agent),
                "raw_argument_errors": sum(len(r["metrics"]["raw_argument_errors"]) for r in agent),
                "truncated_cases": sum(bool(r["trace"]["truncated"]) for r in agent),
                "actual_models": sorted({m for r in agent for m in r["trace"]["provider_models"]}),
                "categories": categories, "average_latency_seconds": statistics.fmean(latencies) if latencies else None,
                "p90_latency_seconds": percentile(latencies, .9),
                "known_cost_usd": sum(c for c in agent_costs if isinstance(c, (int, float))),
                "cost_missing_cases": sum(c is None for c in agent_costs)},
            "generation": {
                "attempted": len(generation), "selected": 6, "complete": len(generation) == 6,
                "errors": sum(bool(r["error"]) for r in generation),
                "provider_errors": sum(bool(e.get("error")) for e in events), "provider_calls": len(events),
                "raw_json_valid_cases": sum(r["raw_json_schema_valid"] is True for r in generation),
                "preprovider_cases": sum(not r["provider_events"] for r in generation),
                "citation_membership_valid": sum(r["citation_id_membership_valid"] for r in generation),
                "fallback_cases": sum(r["response"]["fallback_required"] for r in generation),
                "actual_models": sorted({m for r in generation for m in r["provider_models"]}),
                "average_provider_seconds": statistics.fmean([r["generation_latency_seconds"] for r in generation if r["generation_latency_seconds"] is not None]) if events else None,
                "known_cost_usd": sum(c for c in gen_costs if isinstance(c, (int, float))),
                "cost_missing_receipts": sum(c is None for c in gen_costs)},
            "known_cost_usd_excluding_preflight": sum(known), "cost_missing_receipts": len(costs) - len(known),
            "semantic_correctness": "NOT_EVALUATED_REVIEW_DEFERRED", "citation_claim_support": "NOT_EVALUATED_REVIEW_DEFERRED",
        }
    inputs = {}
    for key in MODELS:
        path = ROOT / "eval/results" / run_name("generation_" + key) / "fixed_inputs.jsonl"
        inputs[key] = ({r["case_id"]: r for r in (json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s)}
                       if path.exists() else {})
    paired = [{"case_id": identifier, **{field: inputs["mistral"].get(identifier, {}).get(field) == inputs["gemma"].get(identifier, {}).get(field)
               and field in inputs["mistral"].get(identifier, {}) for field in ("sha256", "evidence_sha256", "request_messages_sha256")}} for identifier in RAG_IDS]
    write("comparison_conditions.json", {"fixed_generation_pairs": paired, "all_six_inputs_identical": all(all(r[f] for f in ("sha256", "evidence_sha256", "request_messages_sha256")) for r in paired),
                                          "differences": manifest["differences"]})
    write("observed_failures.json", failures)
    write("result.json", {"status": "DEVELOPMENT_SMOKE_RECORDED", "production_acceptance": False,
                          "review_deferred": True, "independent_labels": 0, "models": models,
                          "all_agent_batches_complete": all(v["agent"]["complete"] for v in models.values()),
                          "all_generation_batches_complete": all(v["generation"]["complete"] for v in models.values())})
    with (MASTER / "model_comparison.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["model", "agent_passed", "agent_attempted", "agent_selected", "agent_errors", "safety_violations", "raw_argument_error_cases", "mean_agent_seconds", "generation_json_valid", "generation_provider_calls", "generation_errors", "known_cost_usd_excluding_preflight", "semantic_correctness"])
        for v in models.values():
            a, g = v["agent"], v["generation"]
            writer.writerow([v["model"], a["passed"], a["attempted"], 30, a["errors"], a["safety_violations"], a["raw_argument_error_cases"], a["average_latency_seconds"], g["raw_json_valid_cases"], g["provider_calls"], g["errors"], v["known_cost_usd_excluding_preflight"], v["semantic_correctness"]])
    preservation = {"previous_files": verify(read("protected_previous_files.json")), "corpus": verify(read("protected_corpus.json")),
                    "source": verify(read("source_revision.json")), "env_unchanged": digest(ROOT / ".env") == manifest["env_sha256"]}
    write("preservation.json", preservation)
    if not all(preservation[k]["unchanged"] for k in ("previous_files", "corpus", "source")) or not preservation["env_unchanged"]:
        raise RuntimeError("Preservation failed")
    print(json.dumps(models, ensure_ascii=True, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "execute", "finish"])
    parser.add_argument("--key")
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare()
    elif args.phase == "execute":
        execute(args.key)
    else:
        finish()
