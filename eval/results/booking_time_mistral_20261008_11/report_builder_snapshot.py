"""Preserve old runs and report a prompt-only Booking development iteration."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "eval/results/booking_time_mistral_20261008_11"
BASELINE = ROOT / "eval/results/agent_v2_1_schema_source_booking_54_mistral_20261008_08"
PREFLIGHT = ROOT / "eval/results/agent_v2_1_time_preflight_mistral_20261008_11"
FULL = ROOT / "eval/results/agent_v2_1_time_booking_54_mistral_20261008_11"
KEYCHECK = ROOT / "eval/results/agent_v2_1_time_keycheck_mistral_20261008_12"
FULL_RESUME = ROOT / "eval/results/agent_v2_1_time_booking_54_mistral_20261008_12"
MODEL = "mistralai/mistral-small-2603"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name: str, value) -> None:
    with (MASTER / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def hashes(folders: list[Path]) -> dict[str, str]:
    return {
        str(p.relative_to(ROOT)): digest(p)
        for folder in folders if folder.exists() for p in folder.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
        and p.suffix not in {".pyc"}
    }


def rows(folder: Path) -> list[dict]:
    return [json.loads(s) for s in (folder / "case_results.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]


def source_hashes() -> dict[str, str]:
    return hashes([ROOT / "backend/src/agents", ROOT / "backend/src/infrastructure/llm", ROOT / "backend/tests/evaluation_v2", ROOT / "eval/datasets"]) | {
        "backend/src/config.py": digest(ROOT / "backend/src/config.py"),
    }


def verify(mapping: dict[str, str]) -> dict:
    changed = [name for name, expected in mapping.items() if not (ROOT / name).is_file() or digest(ROOT / name) != expected]
    return {"files_verified": len(mapping), "unchanged": not changed, "changed": changed}


def summarize(folder: Path) -> dict:
    data = rows(folder)
    configuration = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["configuration"]
    planned = len(configuration["selected_ids"]) * configuration["repeats"]
    raw = [{"case_id": r["case_id"], "repeat": r["repeat"], "errors": r["metrics"]["raw_argument_errors"]} for r in data if r["metrics"]["raw_argument_errors"]]
    calls = [c for r in data for c in r["trace"].get("requested_tool_calls", []) if c["name"] == "propose_booking"]
    before_availability = 0
    for row in data:
        seen = []
        for message in row["trace"].get("messages", []):
            if message.get("type") == "tool" and message.get("name") == "get_available_slots":
                seen.append(json.loads(message["content"]))
            if message.get("type") != "ai":
                continue
            requested = message.get("response_metadata", {}).get("requested_tool_calls", message.get("tool_calls", []))
            for call in requested:
                if call["name"] != "propose_booking":
                    continue
                args = call.get("args", {})
                verified = any(str(v.get("workshop_id")) == str(args.get("workshop_id")) and v.get("date") == args.get("booking_date") and any(s.get("available") is True and str(s.get("time_slot", ""))[:5] == str(args.get("time_slot", ""))[:5] for s in v.get("slots", [])) for v in seen)
                before_availability += not verified
    exact = []
    for row in data:
        if row["case_id"] not in {"BOOK-05", "BOOK-06", "BOOK-19"}:
            continue
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", row["user"])
        times = re.findall(r"(?<!\d)\d{2}:\d{2}(?![:\d])", row["user"])
        workshops = re.findall(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", row["user"], re.IGNORECASE)
        assert len(dates) == len(times) == len(workshops) == 1
        proposed = [c for c in row["trace"]["calls"] if c["name"] == "propose_booking" and c["result"].get("status") == "PROPOSED"]
        ok = len(proposed) == 1 and proposed[0]["args"]["booking_date"] == dates[0] and proposed[0]["args"]["time_slot"] == times[0] and proposed[0]["args"]["workshop_id"] == workshops[0] and row["trace"].get("booking_count_before_confirm") == 0
        exact.append({"case_id": row["case_id"], "repeat": row["repeat"], "passed": ok})
    return {
        "rows": len(data), "passed": sum(r["metrics"]["task_passed"] for r in data),
        "planned_rows": planned, "not_attempted_rows": planned - len(data),
        "complete": len(data) == planned,
        "errors": sum(bool(r["trace"].get("error")) for r in data),
        "safety_violations": sum(len(r["metrics"]["safety_violations"]) for r in data),
        "raw_argument_error_cases": raw,
        "raw_proposal_time_values": dict(Counter(c.get("args", {}).get("time_slot", "<missing>") for c in calls)),
        "raw_proposal_request_count": len(calls),
        "raw_proposals_without_prior_verified_availability": before_availability,
        "targeted_exact_proposal_checks": exact,
        "actual_models": sorted({m["response_metadata"].get("model_name") for r in data for m in r["trace"].get("messages", []) if m.get("type") == "ai" and m.get("response_metadata", {}).get("model_name")}),
        "provider_cost_usd": sum(r["trace"]["provider_cost_usd"] for r in data) if all(r["trace"].get("provider_cost_usd") is not None for r in data) else None,
        "known_cost_usd": sum(r["trace"]["provider_cost_usd"] for r in data if r["trace"].get("provider_cost_usd") is not None),
        "case_cost_missing_count": sum(r["trace"].get("provider_cost_usd") is None for r in data),
        "average_latency_seconds": sum(r["trace"]["latency_seconds"] for r in data) / len(data) if data else None,
        "failures": [{"case_id": r["case_id"], "repeat": r["repeat"], "metrics": r["metrics"], "error": r["trace"].get("error")} for r in data if not r["metrics"]["task_passed"]],
    }


def prepare() -> None:
    old = hashes([ROOT / "eval/results", ROOT / "eval/datasets"])
    for folder in [ROOT / "backend/tests/test_agents", ROOT / "backend/tests/evaluation"]:
        old.update({name: value for name, value in hashes([folder]).items() if Path(name).suffix != ".py"})
    corpus = hashes([ROOT / "data/knowledge/raw", ROOT / "data/knowledge/processed"])
    MASTER.mkdir(exist_ok=False)
    write("manifest.json", {"status": "DEVELOPMENT_NOT_ACCEPTANCE", "scope": "Prompt-only raw proposal HH:MM formatting; no dataset/scorer/schema changes", "model": MODEL, "baseline": str(BASELINE.relative_to(ROOT)), "configuration": {"temperature": 0.2, "max_tokens": 2048, "repeats": 3, "endpoint_order": ["mistral/us", "mistral/eu"]}, "source_before": source_hashes(), "env_sha256": digest(ROOT / ".env")})
    write("protected_previous_artifacts.json", old)
    write("protected_local_corpus.json", corpus)
    with (MASTER / "before_prompts.py").open("x", encoding="utf-8", newline="") as stream:
        stream.write((ROOT / "backend/src/agents/prompts.py").read_text(encoding="utf-8"))
    golden = [json.loads(s) for s in (ROOT / "backend/tests/test_agents/test_rag/evaluation/golden_set.jsonl").read_text(encoding="utf-8-sig").splitlines() if s.strip()]
    v2 = json.loads((ROOT / "eval/datasets/agent_cases_v2.json").read_text(encoding="utf-8-sig"))
    v21 = json.loads((ROOT / "eval/datasets/agent_cases_v2_1.json").read_text(encoding="utf-8-sig"))
    old_cases = {c["id"]: c for c in v2["cases"]}
    audit = {"golden_count": len(golden), "golden_objects_equal_in_order": golden == [c["golden"] for c in v21["cases"] if c["category"] == "rag"], "v2_v21_user_queries_equal": all(old_cases[c["id"]]["user"] == c["user"] for c in v21["cases"]), "v21_categories": dict(Counter(c["category"] for c in v21["cases"])), "v21_sessions": len(v21["sessions"]), "status": "DEVELOPMENT_PENDING_INDEPENDENT_REVIEW"}
    assert audit["golden_objects_equal_in_order"] and audit["v2_v21_user_queries_equal"]
    write("dataset_audit.json", audit)
    write("baseline_audit.json", summarize(BASELINE))
    print(f"Prepared: {MASTER}; protected {len(old)} artifacts, {len(corpus)} corpus files")


def freeze() -> None:
    before = json.loads((MASTER / "manifest.json").read_text(encoding="utf-8"))["source_before"]
    after = source_hashes()
    changed = [name for name in before.keys() | after.keys() if before.get(name) != after.get(name)]
    assert changed == [str(Path("backend/src/agents/prompts.py"))], changed
    write("source_revision.json", {"source_hashes": after, "changed_from_before": changed})
    with (MASTER / "after_prompts.py").open("x", encoding="utf-8", newline="") as stream:
        stream.write((ROOT / "backend/src/agents/prompts.py").read_text(encoding="utf-8"))
    print(f"Frozen {len(after)} files; only Agent prompt changed")


def close() -> None:
    protected = verify(json.loads((MASTER / "protected_previous_artifacts.json").read_text(encoding="utf-8")))
    corpus = verify(json.loads((MASTER / "protected_local_corpus.json").read_text(encoding="utf-8")))
    revision = json.loads((MASTER / "source_revision.json").read_text(encoding="utf-8"))
    source = verify(revision["source_hashes"])
    manifest = json.loads((MASTER / "manifest.json").read_text(encoding="utf-8"))
    env_unchanged = digest(ROOT / ".env") == manifest["env_sha256"]
    env_revision = MASTER / "env_revision_after_update.json"
    env_verified = digest(ROOT / ".env") == json.loads(env_revision.read_text(encoding="utf-8"))["env_sha256"] if env_revision.exists() else env_unchanged
    closed = {p.name: verify(json.loads(p.read_text(encoding="utf-8"))) for p in MASTER.glob("closed_*_hashes.json")}
    write("preservation.json", {"protected_artifacts": protected, "corpus": corpus, "source_revision": source, "closed_runs": closed, "env_unchanged_since_start": env_unchanged, "env_matches_user_update_revision": env_verified, "agent_wrote_env": False})
    assert all(v["unchanged"] for v in [protected, corpus, source, *closed.values()]) and env_verified
    existing = [p for p in [PREFLIGHT, FULL, KEYCHECK, FULL_RESUME] if (p / "comparison.json").exists()]
    assert existing
    result = {"status": "DEVELOPMENT_NOT_ACCEPTANCE", "model": MODEL, "baseline": summarize(BASELINE), "runs": {p.name: summarize(p) for p in existing}, "independent_semantic_labels": 0, "dataset_scorer_unchanged": True, "offline_checks": json.loads((MASTER / "offline_verification.json").read_text(encoding="utf-8")), "ruff": json.loads((MASTER / "ruff_final.json").read_text(encoding="utf-8"))}
    matched = FULL_RESUME if FULL_RESUME in existing else FULL
    if matched in existing:
        a = json.loads((BASELINE / "manifest.json").read_text(encoding="utf-8"))["configuration"]
        b = json.loads((matched / "manifest.json").read_text(encoding="utf-8"))["configuration"]
        keys = ["models", "endpoint_order", "repeats", "max_tokens", "temperature", "timeout", "clock", "dataset_sha256", "selected_ids", "scorer_version"]
        conditions = {key: a[key] == b[key] for key in keys}
        schema_same = digest(BASELINE / "schema_snapshot.json") == digest(matched / "schema_snapshot.json")
        write("comparison_conditions.json", {"candidate": matched.name, "same": conditions, "schema_same": schema_same, "prompt_intentionally_changed": True, "runtime_effect_and_provider_variance_not_model_only_accuracy": True})
        assert all(conditions.values()) and schema_same
    costs = [r["provider_cost_usd"] for r in result["runs"].values()]
    result["iteration_provider_cost_usd"] = sum(costs) if all(c is not None for c in costs) else None
    result["iteration_known_cost_usd"] = sum(r["known_cost_usd"] for r in result["runs"].values())
    result["iteration_case_cost_missing_count"] = sum(r["case_cost_missing_count"] for r in result["runs"].values())
    if (FULL / "provider_stops.json").exists():
        stops = json.loads((FULL / "provider_stops.json").read_text(encoding="utf-8"))
        result["historical_live_blocker"] = {"status": "EXTERNAL_KEY_TOTAL_LIMIT", "http_status": 403, "provider_message": "Key limit exceeded (total limit)", "case_id": stops[0]["case_id"], "retry_without_limit_change": "NOT_ATTEMPTED", "skipped_cases_not_counted_as_pass": True, "user_updated_env": env_revision.exists()}
    if FULL_RESUME in existing:
        current = result["runs"][FULL_RESUME.name]
        result["latest_full_regression_complete"] = current["complete"] and current["errors"] == 0
    write("result.json", result)
    write("completed_run_hashes.json", hashes(existing))
    offline = result["offline_checks"]
    lines = ["# Booking: raw time format followup — 08/10/2026", "", "Development evaluation, step 3; not production acceptance. Mistral Small 2603 retained.", "", "The read tool returns seconds (14:00:00), while proposal arguments require HH:MM. The prompt now explicitly explains conversion of a verified zero-second slot without changing its hour/minute, workshop or date. Nonzero seconds must not be rounded. Public schema, normalization, dataset and scorer remain unchanged.", "", f"Offline regression: {offline['tests'] - offline['skipped'] - offline['failures'] - offline['errors']} passed, {offline['skipped']} skipped; Ruff exit code {result['ruff']['exit_code']}. [JUnit evidence](offline_regression_01.xml).", "", "| Run | Runtime PASS | API errors | Raw argument error cases | Safety violations |", "|---|---:|---:|---:|---:|"]
    for name, r in [("Historical matched 54 baseline", result["baseline"]), *result["runs"].items()]:
        lines.append(f"| {name} | {r['passed']}/{r['rows']} | {r['errors']} | {len(r['raw_argument_error_cases'])} | {r['safety_violations']} |")
    lines.extend(["", "| Run | Raw proposal requests | Requests before verified slots | Mean case latency (s) |", "|---|---:|---:|---:|"])
    for name, r in [("Historical matched 54 baseline", result["baseline"]), *result["runs"].items()]:
        lines.append(f"| {name} | {r['raw_proposal_request_count']} | {r['raw_proposals_without_prior_verified_availability']} | {r['average_latency_seconds']:.3f} |")
    if "historical_live_blocker" in result:
        lines.extend(["", "The first full run was interrupted by HTTP403 `Key limit exceeded (total limit)`: 1/54 attempted, 53 not attempted. The rejected request is not evidence of a wrong BOOK-03 answer. The user then updated .env; BOOK-03 was checked in a new keycheck run and the full regression restarted in a new directory. The failed run is preserved and is not combined with the new run's PASS denominator."])
    lines.extend(["", "Raw proposal requests can precede verified slot reads. Existing runtime guards insert prerequisites rather than executing those proposals. Format correctness does not prove that the model independently follows the complete tool chain. The counters above retain this limitation; task PASS is the delivered runtime behavior.", "", f"Current iteration known receipt subtotal: {result['iteration_known_cost_usd']} USD; {result['iteration_case_cost_missing_count']} case(s) lack cost metadata. Missing cost is not interpreted as zero; total cost is not certified.", "", "[Dataset audit](dataset_audit.json): all 100 RAG golden objects match the historical golden file in order; v2/v2.1 user queries are identical. The golden, datasets and historical results were not changed or rescored.", "", "[Preservation](preservation.json) verifies historical artifacts, corpus and frozen source revision. The user updated .env after the 403; its new revision is recorded without exposing credentials. The agent did not write .env. Raw proposal requests and normalization remain visible in producer traces; runtime PASS is not raw model accuracy.", "", "Independent semantic labels: 0. Source-owner adjudication, holdout, shortlist, full HTTP/Firebase/UI confirmation, TTFT/concurrency and pilot remain pending. No production writes, real email, corpus/Qdrant mutation or app restart was performed."])
    with (MASTER / "report.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    write("closed_master_hashes.json", hashes([MASTER]))
    print(json.dumps({"runs": {k: {"rows": v["rows"], "passed": v["passed"], "raw_error_cases": len(v["raw_argument_error_cases"])} for k, v in result["runs"].items()}, "cost": result["iteration_provider_cost_usd"], "preserved_artifacts": protected["files_verified"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "freeze", "close"])
    args = parser.parse_args()
    {"prepare": prepare, "freeze": freeze, "close": close}[args.phase]()
