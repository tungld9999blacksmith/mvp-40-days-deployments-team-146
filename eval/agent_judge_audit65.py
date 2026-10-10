"""Offline evidence audit, never a replacement judge or a paid runner."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / "eval/results/agent_judge_resume_20261009_64"
OUTPUT = ROOT / "eval/results/agent_judge_audit_20261009_65"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def verify(mapping: dict[str, str]) -> dict:
    changed = [name for name, sha in mapping.items()
               if not (ROOT / name).is_file() or digest(ROOT / name) != sha]
    return {"files_verified": len(mapping), "unchanged": not changed, "changed": changed}


def protection() -> dict:
    checks = {name: verify(read(PRIOR / manifest)) for name, manifest in (
        ("closed64", "closed_master_hashes.json"),
        ("history", "protected_previous_files.json"),
        ("source", "source_revision.json"))}
    if not all(check["unchanged"] for check in checks.values()):
        raise RuntimeError("Previously closed evidence or source changed; audit cannot proceed")
    return checks


def slot_claim_check(sample: dict) -> dict:
    """Compare an explicit full-list count and each remaining value, not all semantics."""
    lists = [call["result"] for call in sample["tool_calls"]
             if call["name"] == "get_available_slots" and isinstance(call.get("result"), dict)
             and isinstance(call["result"].get("slots"), list)]
    answer = fold(sample["answer"])
    stated = re.findall(r"\bco\s+(\d+)\s+khung gio\s+kha dung\b", answer)
    listed = re.findall(r"^\s*-\s*(\d{2}:\d{2}):\s*con\s+(\d+)\s+cho", answer, re.MULTILINE)
    if len(lists) != 1 or len(stated) != 1 or not listed:
        return {"applicable": False, "reason": "Requires one tool list and an explicit count/list"}
    data = lists[0]
    available = [slot for slot in data["slots"] if slot.get("available") is True]
    expected = [(slot["time_slot"][:5], slot["remaining"]) for slot in available]
    actual = [(time, int(remaining)) for time, remaining in listed]
    scope_matches = data["workshop_id"] in sample["answer"] and (
        "/".join(reversed(data["date"].split("-"))) in sample["answer"])
    return {"applicable": True, "tool_count": len(expected), "stated_count": int(stated[0]),
            "listed_count": len(actual), "scope_matches": scope_matches,
            "times_and_remaining_match": Counter(actual) == Counter(expected),
            "count_matches": int(stated[0]) == len(expected) == len(actual),
            "claim_matches": scope_matches and Counter(actual) == Counter(expected)
                             and int(stated[0]) == len(expected) == len(actual),
            "scope": "Availability count/time/remaining/workshop/date only; not an overall label"}


def numbered_steps(text: str) -> list[str]:
    """Keep wrapped lines with their step, and stop before a new source heading."""
    matches = list(re.finditer(r"^\s*([1-9]\d*)[.)]\s+(.+)", text, re.MULTILINE))
    steps = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.start():end].split("\n[", 1)[0].strip()
        steps.append(body)
    return steps


def procedure_check(sample: dict, producer: dict) -> dict:
    query = fold(sample["question"])
    if "tim" not in query or "sac" not in query or "ung dung" not in query:
        return {"applicable": False}
    findings = []
    for source in sample["sources"]:
        steps = numbered_steps(source["text"]) if source["kind"] == "rag_chunk" else []
        if not steps or "ban do" not in fold(steps[0]):
            continue
        requests = [entry["request"] for entry in producer["live"]["generation"]]
        messages = [str(message.get("content", "")) for request in requests
                    for message in request.get("messages", [])]
        findings.append({"source_id": source["source_id"], "chunk_id": source["chunk_id"],
                         "source_sha256": hashlib.sha256(source["text"].encode()).hexdigest(),
                         "steps": steps,
                         "full_chunk_present_in_generation_request": any(
                             source["text"] in message for message in messages)})
    answer = fold(sample["answer"])
    denies = any(term in answer for term in ("chua xac dinh", "khong cung cap quy trinh"))
    return {"applicable": True, "sources_with_steps": findings,
            "answer_numbered_steps": numbered_steps(sample["answer"]),
            "answer_denies_or_abstains": denies,
            "omission_candidate": bool(findings) and denies and not numbered_steps(sample["answer"]),
            "generation_models": sorted({entry["model"] for entry in producer["live"]["generation"]}),
            "scope": "Evidence omission diagnostic, not source authority or independent quality label"}


def uncertainty_trace(producer: dict) -> list[dict]:
    traces = []
    for entry in producer["live"]["rag"]:
        response = entry.get("response") or {}
        metadata = response.get("metadata") or {}
        traces.append({"fallback_required": response.get("fallback_required"),
                       "source_rule_verified": metadata.get("source_rule_verified"),
                       "source_rule_verified_field_present": "source_rule_verified" in metadata,
                       "reason": metadata.get("reason"), "confidence": response.get("confidence")})
    return traces


def cost_estimate(technical: dict, judgments: list[dict], ledger: dict) -> dict:
    if len(judgments) != 60 or any(row["error"] or row["cost_usd"] is None for row in judgments):
        raise ValueError("Requires sixty valid unique paid labels")
    if len({row["sample_id"] for row in judgments}) != 60:
        raise ValueError("Duplicate judge labels would double-count costs")
    producer_count = sum(model["observations"] for model in technical["models"].values())
    pipeline_rate = technical["full180_llm_cost_usd"] / producer_count
    judge_cost = sum(row["cost_usd"] for row in judgments)
    judge_rate = judge_cost / len(judgments)
    rate = pipeline_rate + judge_rate
    scenarios = {}
    for configs in (2, 3):
        # 220 single turns plus 20 sessions of 3-6 turns. A session is not one question.
        low_turns = configs * 3 * (220 + 20 * 3)
        high_turns = configs * 3 * (220 + 20 * 6)
        low = low_turns * rate
        high = high_turns * rate
        scenarios[str(configs)] = {
            "single_questions": 220, "sessions": 20, "turns_per_session": [3, 6],
            "repeats_per_config": 3, "estimated_answer_count": [low_turns, high_turns],
            "generation_plus_judge_before_reserve_usd": [low, high],
            "planning_remaining_llm_usd": [low * 1.3 + .9, high * 2 + 1.1],
            "reserve_assumption": "30%-100% workload variance plus $0.90-$1.10 development/pilot/staging allowance",
            "third_config": "Unpriced candidate; assumes same mean turn cost as current two, not measured" if configs == 3 else None}
    return {"basis": "Measured receipts, not list-price billing prediction",
            "pipeline_usd_per_answer": pipeline_rate, "judge_usd_per_answer": judge_rate,
            "sixty_unique_judge_cost_usd": judge_cost,
            "known55_through64_usd": ledger["all"],
            "existing_shared_cap_usd": .75, "known_cap_headroom_usd": .75 - ledger["all"],
            "offline_audit_new_provider_cost_usd": 0,
            "optional_remaining120_judge_before_pilot_usd": 120 * judge_rate,
            "fresh30_by2_by3_generation_and_judge_usd": 180 * rate,
            "fresh30_by2_by3_planning_llm_usd": [.85, 1.4],
            "full_remaining_plan_scenarios": scenarios,
            "assumptions": ["Keep Agent Mistral/Gemma, Rewrite and generation Mistral; no GPT-4o",
                            "Same average payload mix as 30-case run, every answer judged once",
                            "Reserve is a planning assumption, not a guaranteed upper bound",
                            "At most one development regression cycle before one locked acceptance campaign"],
            "excluded_unknown_costs": ["Embedding fees including prior69 calls", "Missing403 receipt",
                                       "Interrupted60 request", "Additional optimization cycles",
                                       "Infrastructure, Resend, top-up fees/tax, independent review/user recruitment"],
            "new_budget_authorized": False, "paid_calls_performed": 0}


def run() -> None:
    before = protection()
    samples = {sample["sample_id"]: sample for sample in read(PRIOR / "all_selected_samples.json")}
    indexes = {origin["sample_id"]: origin for origin in read(PRIOR / "judge_private_index.json")}
    judgments = read(PRIOR / "combined_assessments.json")
    if len(samples) != 60 or len(indexes) != 60 or len(judgments) != 60:
        raise RuntimeError("Original sixty-case audit coverage changed")
    producer_cache = {}
    flags = []
    for judgment in judgments:
        if judgment["automated_status"] == "PASS":
            continue
        sid = judgment["sample_id"]
        sample, origin = samples[sid], indexes[sid]
        folder = ROOT / origin["producer"]
        if folder not in producer_cache:
            producer_cache[folder] = {row["case_id"]: row for row in (
                json.loads(line) for line in (folder / "case_results.jsonl").read_text(encoding="utf-8").splitlines())}
        row = producer_cache[folder][origin["case_id"]]
        if content_hash(row) != origin["original_row_sha256"] or row["trace"]["answer"] != sample["answer"]:
            raise RuntimeError("Producer answer or hash changed")
        slots = slot_claim_check(sample)
        procedure = procedure_check(sample, row)
        retained = judgment["automated_status"]
        classification = "SOURCE_AND_ABSTENTION_BOUNDARY_REVIEW_REQUIRED"
        if slots.get("claim_matches"):
            classification = "BOOKING_JUDGE_SLOT_OBJECTION_CONTRADICTED"
        elif procedure.get("omission_candidate"):
            classification = "PROCEDURE_OMISSION_AND_JUDGE_RELIABILITY_REVIEW"
        elif retained == "UNVERIFIABLE":
            classification = "SOURCE_UNCERTAINTY_PROPAGATED_FROM_RAG_TRACE"
        flags.append({"origin": origin, "original_label_retained": retained,
                      "original_judge_components": {key: judgment["judge"][key] for key in (
                          "correctness_from_available_evidence", "faithfulness", "task_success", "citation_support")},
                      "classification": classification, "slot_claim_check": slots,
                      "procedure_check": procedure, "uncertainty_trace": uncertainty_trace(row),
                      "source_uncertainty_input": sample["source_uncertainty"],
                      "delivered_citation_count": len(sample["citations"]),
                      "rag_tool_answer_equals_final": any(
                          source["kind"] == "tool_result" and json.loads(source["text"]).get("text") == sample["answer"]
                          for source in sample["sources"] if source["kind"] == "tool_result"),
                      "replacement_label": None, "independent_source_verification": False})
    estimate = cost_estimate(read(ROOT / "eval/results/agent_regression_resume_20261009_61/technical_comparison.json"),
                             judgments, read(PRIOR / "all_attempts_cost.json"))
    OUTPUT.mkdir(exist_ok=False)
    write(OUTPUT / "before_preservation.json", before)
    write(OUTPUT / "audit.json", {"flag_count": len(flags), "flags": flags,
                                  "original_counts_retained": dict(Counter(j["automated_status"] for j in judgments)),
                                  "raw_judgments_modified": False, "independent_labels": 0,
                                  "new_provider_calls": 0, "production_acceptance": False})
    write(OUTPUT / "cost_estimate.json", estimate)
    write(OUTPUT / "after_preservation.json", protection())
    print(json.dumps({"audited_flags": len(flags), "classes": dict(Counter(f["classification"] for f in flags)),
                      "new_provider_cost_usd": 0, "full_remaining_estimates": estimate["full_remaining_plan_scenarios"]}))


if __name__ == "__main__":
    run()
