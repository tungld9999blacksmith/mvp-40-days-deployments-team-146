"""Add GPT-4o to a frozen Agent smoke without changing old artifacts."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
from collections import Counter

from step4_smoke import ROOT, digest, hashes, load_rows, percentile, verify

MASTER = ROOT / "eval/results/step4_agent_gpt4o_followup_20261008_15"
PREVIOUS = ROOT / "eval/results/step4_smoke_30_20261008_14"
RUNS = {"preflight": "step4_preflight_gpt4o_20261008_15", "full": "step4_agent_gpt4o_20261008_15"}
MODEL = "openai/gpt-4o"
BASELINES = {
    "mistral": ROOT / "eval/results/step4_agent_mistral_20261008_14",
    "gemma": ROOT / "eval/results/step4_agent_gemma_20261008_14",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(name, value):
    with (MASTER / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def frozen_source():
    # Preserve revision 01; use the final controller freeze before live calls.
    revised = MASTER / "source_revision_02.json"
    return read(revised if revised.exists() else MASTER / "source_revision.json")


def prepare():
    previous = read(PREVIOUS / "manifest.json")
    checks = {name: verify(read(PREVIOUS / name)) for name in
              ("source_revision.json", "closed_master_hashes.json", "completed_producer_hashes.json")}
    if not all(v["unchanged"] for v in checks.values()):
        raise RuntimeError("Previous conditions changed; cannot reuse old smoke")
    if digest(ROOT / ".env") != previous["env_sha256"]:
        raise RuntimeError("Environment changed; compare effective settings before new live run")
    protected = hashes([ROOT / "eval/results", ROOT / "eval/datasets",
                        ROOT / "backend/tests/test_agents/evaluationLLM/results",
                        ROOT / "backend/tests/test_agents/test_rag/evaluation", ROOT / "backend/tests/evaluation"])
    MASTER.mkdir(exist_ok=False)
    write("protected_previous_files.json", protected)
    write("protected_corpus.json", hashes([ROOT / "data/knowledge/raw", ROOT / "data/knowledge/processed"]))
    source = read(PREVIOUS / "source_revision.json") | {"eval/step4_gpt4o_followup.py": digest(ROOT / "eval/step4_gpt4o_followup.py")}
    write("source_revision.json", source)
    commands = {}
    for key, run_name in RUNS.items():
        old_key = "preflight_gemma" if key == "preflight" else "agent_gemma"
        command = list(previous["commands"][old_key])
        command[command.index("--model") + 1] = MODEL
        command[command.index("--run-name") + 1] = run_name
        commands[key] = command
    write("selected_cases.json", read(PREVIOUS / "selected_cases.json"))
    write("manifest.json", {
        "scope": "development_agent_smoke_gpt4o_extension", "date_asia_saigon": "2026-10-08",
        "model": MODEL, "selected_ids": previous["selected_ids"], "conditions": previous["agent_conditions"],
        "env_sha256": digest(ROOT / ".env"), "previous_manifest_sha256": digest(PREVIOUS / "manifest.json"),
        "reuse_checks": checks, "commands": commands,
        "baseline_runs": {key: str(path.relative_to(ROOT)) for key, path in BASELINES.items()},
        "offline_validation": {"reference": str((PREVIOUS / "offline_validation.json").relative_to(ROOT)),
                               "reference_sha256": digest(PREVIOUS / "offline_validation.json"), "passed": 45,
                               "runtime_source_unchanged": True, "new_pytest_run": False},
        "differences": ["GPT-4o/Gemma automatic endpoint routing; Mistral prefers mistral/us,mistral/eu",
                        "Sequential runs at different times; provider load/region not controlled",
                        "Fixture UUIDs generated independently; equivalent placeholder roles, not byte-identical requests"],
        "semantic_review": "DEFERRED_BY_USER", "production_acceptance": False,
        "side_effects": {"real_email": False, "production_db": False, "corpus_mutation": False,
                         "env_write": False, "app_restart": False, "write_reviewer": False,
                         "live_rag_generation": False},
    })
    print(f"Prepared {MASTER}; prior 45-test evidence reused, source frozen before API", flush=True)


def execute(key):
    manifest = read(MASTER / "manifest.json")
    checks = [verify(frozen_source()), verify(read(MASTER / "protected_previous_files.json")), verify(read(MASTER / "protected_corpus.json"))]
    if not all(v["unchanged"] for v in checks) or digest(ROOT / ".env") != manifest["env_sha256"]:
        raise RuntimeError("Frozen conditions changed")
    if key == "full":
        rows = load_rows(ROOT / "eval/results" / RUNS["preflight"])
        if len(rows) != 1 or rows[0]["trace"]["error"] or not rows[0]["metrics"]["task_passed"] or rows[0]["trace"]["provider_models"] != [MODEL]:
            raise RuntimeError("Preflight not eligible; do not start batch")
        write("preflight_budget_projection.json", {
            "case_id": rows[0]["case_id"], "receipt_usd": rows[0]["trace"].get("provider_cost_usd"),
            "thirty_times_booking_preflight_usd": 30 * rows[0]["trace"]["provider_cost_usd"] if rows[0]["trace"].get("provider_cost_usd") is not None else None,
            "note": "Rough workload-specific projection, not guaranteed cost/account quota; Booking may require more calls than other cases.",
        })
    with (MASTER / f"{key}_stdout.log").open("x", encoding="utf-8") as log:
        proc = subprocess.Popen(manifest["commands"][key], cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
        exit_code = proc.wait()
    write(f"{key}_execution.json", {"exit_code": exit_code, "run_name": RUNS[key]})
    print(f"Recorded {key}: producer exit {exit_code}", flush=True)


def raw_audit(rows):
    audit = []
    for row in rows:
        verified = []
        total = premature = 0
        for message in row["trace"].get("messages", []):
            if message.get("type") == "tool" and message.get("name") == "get_available_slots":
                verified.append(json.loads(message["content"]))
            if message.get("type") != "ai":
                continue
            metadata = message.get("response_metadata", {})
            raw = metadata.get("requested_tool_calls", metadata.get("rejected_tool_calls", message.get("tool_calls", [])))
            for call in raw:
                if call["name"] != "propose_booking":
                    continue
                total += 1
                args = call.get("args", {})
                matching = any(str(v.get("workshop_id")) == str(args.get("workshop_id")) and v.get("date") == args.get("booking_date")
                               and any(s.get("available") is True and str(s.get("time_slot", ""))[:5] == str(args.get("time_slot", ""))[:5] for s in v.get("slots", []))
                               for v in verified)
                premature += not matching
        audit.append({"case_id": row["case_id"], "proposal_requests": total, "before_verified_availability": premature,
                      "raw_argument_errors": row["metrics"]["raw_argument_errors"],
                      "extra_read_calls": row["metrics"]["extra_read_calls"], "duplicate_calls": row["metrics"]["duplicate_calls"]})
    return audit


def summarize(folder):
    rows = load_rows(folder)
    costs = [r["trace"].get("provider_cost_usd") for r in rows]
    times = [r["trace"]["latency_seconds"] for r in rows]
    audit = raw_audit(rows)
    return {
        "attempted": len(rows), "selected": 30, "complete": len(rows) == 30,
        "passed": sum(r["metrics"]["task_passed"] for r in rows),
        "errors": sum(bool(r["trace"].get("error")) for r in rows),
        "safety_violations": sum(len(r["metrics"]["safety_violations"]) for r in rows),
        "raw_argument_error_cases": sum(bool(r["metrics"]["raw_argument_errors"]) for r in rows),
        "truncated_cases": sum(bool(r["trace"]["truncated"]) for r in rows),
        "actual_models": sorted({m for r in rows for m in r["trace"]["provider_models"]}),
        "mean_seconds": statistics.fmean(times) if times else None, "p90_seconds": percentile(times, .9),
        "known_cost_usd": sum(c for c in costs if isinstance(c, (int, float))),
        "missing_cost_cases": sum(c is None for c in costs),
        "categories": {category: {"passed": sum(r["metrics"]["task_passed"] for r in rows if r["category"] == category), "attempted": total}
                       for category, total in Counter(r["category"] for r in rows).items()},
        "raw_proposal_requests": sum(r["proposal_requests"] for r in audit),
        "raw_proposals_before_verified_availability": sum(r["before_verified_availability"] for r in audit),
        "extra_read_calls": sum(r["extra_read_calls"] for r in audit), "duplicate_calls": sum(r["duplicate_calls"] for r in audit),
    }, audit


def finish():
    manifest = read(MASTER / "manifest.json")
    folders = BASELINES | {"gpt4o": ROOT / "eval/results" / RUNS["full"]}
    results = {}
    audits = {}
    comparison_checks = {}
    common = ("max_tokens", "temperature", "repeats", "timeout", "clock", "dataset_sha256", "selected_ids",
              "rag_mode", "business_services", "baseline_runtime", "scorer_version")
    baseline_config = read(BASELINES["mistral"] / "manifest.json")["configuration"]
    baseline_schema = digest(BASELINES["mistral"] / "schema_snapshot.json")
    for key, folder in folders.items():
        results[key], audits[key] = summarize(folder)
        path = folder / "manifest.json"
        if path.exists():
            config = read(path)["configuration"]
            comparison_checks[key] = {field: config[field] == baseline_config[field] for field in common}
            comparison_checks[key]["schema_identical"] = digest(folder / "schema_snapshot.json") == baseline_schema
    if any(not all(v.values()) for v in comparison_checks.values()):
        raise RuntimeError("Comparison conditions differ")
    failures = [{"model": key, "case_id": r["case_id"], "user": r["user"], "answer": r["trace"]["answer"],
                 "error": r["trace"].get("error"), "metrics": r["metrics"]}
                for key, folder in folders.items() for r in load_rows(folder)
                if not r["metrics"]["task_passed"] or r["metrics"]["raw_argument_errors"]]
    preflight = load_rows(ROOT / "eval/results" / RUNS["preflight"])
    preflight_cost = sum(r["trace"].get("provider_cost_usd") or 0 for r in preflight)
    write("comparison_conditions.json", {"common_conditions": comparison_checks, "differences": manifest["differences"],
                                         "baseline_files_reused_without_rescoring": True})
    write("observed_failures.json", failures)
    write("raw_model_audit.json", audits)
    write("result.json", {"scope": "DEVELOPMENT_ONLY", "models": results, "new_model": MODEL,
                          "review_deferred": True, "independent_labels": 0, "production_acceptance": False,
                          "new_preflight_known_cost_usd": preflight_cost,
                          "new_total_known_cost_usd": results["gpt4o"]["known_cost_usd"] + preflight_cost,
                          "cost_missing_cases": results["gpt4o"]["missing_cost_cases"] + sum(r["trace"].get("provider_cost_usd") is None for r in preflight)})
    with (MASTER / "model_comparison.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["model_key", "passed", "attempted", "selected", "errors", "safety_violations", "raw_argument_error_cases", "mean_seconds", "p90_seconds", "known_cost_usd", "missing_cost_cases", "semantic_review"])
        for key, v in results.items():
            writer.writerow([key, *[v[field] for field in ("passed", "attempted", "selected", "errors", "safety_violations", "raw_argument_error_cases", "mean_seconds", "p90_seconds", "known_cost_usd", "missing_cost_cases")], "DEFERRED"])
    checks = {"previous": verify(read(MASTER / "protected_previous_files.json")), "corpus": verify(read(MASTER / "protected_corpus.json")),
              "source": verify(frozen_source()), "env_unchanged": digest(ROOT / ".env") == manifest["env_sha256"]}
    write("preservation.json", checks)
    if not checks["env_unchanged"] or not all(checks[k]["unchanged"] for k in ("previous", "corpus", "source")):
        raise RuntimeError("Preservation failed")
    print(json.dumps(results, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "preflight", "full", "finish"])
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare()
    elif args.phase in RUNS:
        execute(args.phase)
    else:
        finish()
