"""Correct development expectations using saved state, never rescore v2 runs."""
from __future__ import annotations

import copy
from pathlib import Path

from .artifacts import ROOT, digest, write_new
from .dataset import DATASET, load_dataset

DESTINATION = ROOT / "eval/test_cases/agent_cases_v2_1.json"
STATE_FIELDS = ["reminders_enabled", "email_enabled", "reminder_lead_days"]


def build_reviewed_dataset(source: Path = DATASET) -> dict:
    dataset = copy.deepcopy(load_dataset(source))
    dataset.update(version="2.1", split="development", review_status="CODEX_DRAFT_PENDING_INDEPENDENT_REVIEW_NOT_ACCEPTANCE",
                   parent_dataset_sha256=digest(source), parent_dataset=str(source.relative_to(ROOT)),
                   review_changes=["MAINT-07 accepts the trusted ODO without a mandatory maintenance read",
                                   "REMINDER-10 requires range refusal and unchanged state, not an invalid update",
                                   "Reminder mutations check stored state and preserve unrequested fields",
                                   "REMINDER-17 starts with reminders off; connected Email does not mean enabled"])
    for case in dataset["cases"]:
        expected = case["expected"]
        if case["id"] == "MAINT-07":
            expected["required_tools"] = []
            expected["answer_any_groups"] = [["12.500", "12,500", "12500"]]
            case["review_note"] = "Trusted vehicle context supplies current_odo=12500; a fresh maintenance read is permitted, not required. Correctness remains subject to semantic review."
        if case["category"] != "reminder":
            continue
        initial = {"reminders_enabled": True, "email_enabled": False, "reminder_lead_days": 2}
        if case["id"] in {"REMINDER-03", "REMINDER-06", "REMINDER-12", "REMINDER-17"}:
            initial["reminders_enabled"] = False
        if case["id"] in {"REMINDER-04", "REMINDER-05", "REMINDER-13", "REMINDER-18"}:
            initial["email_enabled"] = True
        if case["id"] == "REMINDER-18":
            initial["reminder_lead_days"] = 5
        case["notification_fixture"] = initial
        if case["id"] == "REMINDER-10":
            expected.update(required_tools=[], allow_reminder_update=False, args={}, forbidden_tools=["update_reminder_settings"],
                            answer_any_groups=[["0"], ["30"], ["ngày"], ["chưa", "không"]])
        updates = expected.get("args", {}).get("update_reminder_settings", {})
        desired = {**initial, **updates}
        if updates.get("email_enabled") is True:
            desired["reminders_enabled"] = True
        expected["reminder_state"] = desired
        expected["unchanged_reminder_fields"] = [key for key in STATE_FIELDS if desired[key] == initial[key]]
        # The saved effect expresses the task; schema validation still checks
        # every public call. Avoid requiring a redundant field in the request.
        expected["args"] = {}
        case["review_note"] = "Fixture and before/after settings are explicit. Email enabled is separate from identity CONNECTED. Development label correction, not acceptance approval."
    return dataset


if __name__ == "__main__":
    write_new(DESTINATION, build_reviewed_dataset())
    print(DESTINATION)
