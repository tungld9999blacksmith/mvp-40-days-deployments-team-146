"""New diagnostics with separate evidence/authority axes; no historic relabeling."""
from __future__ import annotations

import re

from agent_judge_audit65 import slot_claim_check
from src.agents.tools.RAG.query.answer_scope import is_evidence_limitation


def evidence_axes(producer: dict) -> dict:
    observations = []
    for entry in producer.get("live", {}).get("rag", []):
        response = entry.get("response") or {}
        metadata = response.get("metadata") or {}
        rule = metadata.get("source_rule_verified")
        authority = ("EXPLICITLY_UNVERIFIED" if rule is False else
                     "RULE_CHECK_ONLY" if rule is True else "NOT_ASSESSED")
        observations.append({"answerability_reported_by_runtime": "LIMITED" if response.get("fallback_required") else "REPORTED_COMPLETE",
                             "source_authority": authority, "independent_source_verified": False,
                             "reason": metadata.get("reason")})
    return {"rag_observations": observations, "content_correctness": "NOT_EVALUATED",
            "source_authority_rollup": "NOT_APPLICABLE" if not observations else
                                      "EXPLICITLY_UNVERIFIED" if any(o["source_authority"] == "EXPLICITLY_UNVERIFIED" for o in observations) else "NOT_INDEPENDENTLY_VERIFIED"}


def citation_obligations(sample: dict) -> dict:
    limitation = is_evidence_limitation(sample["answer"])
    inline = {int(index) for index in re.findall(r"\[Tài liệu\s+(\d+)\]", sample["answer"], re.IGNORECASE)}
    supplied = {citation["index"] for citation in sample.get("citations", [])}
    return {"answer_scope": "EVIDENCE_LIMITATION_CANDIDATE" if limitation else "CONTENT_REVIEW_REQUIRED",
            "missing_inline_indexes": sorted(inline - supplied),
            "missing_citation_requires_review": bool(sample.get("has_rag") and not limitation and not supplied),
            "claim_support": "NOT_EVALUATED", "abstention_truth_and_completeness": "NOT_EVALUATED",
            "scope": "No missing-citation FAIL solely for scoped abstention; this does not certify that abstention is justified"}


def diagnose(sample: dict, producer: dict, original_status: str) -> dict:
    return {"sample_id": sample["sample_id"], "original_status_retained": original_status,
            "slots": slot_claim_check(sample), "evidence": evidence_axes(producer),
            "citation_obligations": citation_obligations(sample),
            "replacement_status": None, "production_acceptance": False}
