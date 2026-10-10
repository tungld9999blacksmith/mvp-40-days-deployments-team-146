"""Bounded local polling, then isolated development evaluations; never change keys.

Run directories and event logs are append-only. A completed controller is never
resumed in place. Keep the machine awake; no remote scheduler is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
RESULTS = ROOT / "eval/results"
MODEL = "mistralai/mistral-small-2603"
CLOCK = timezone(timedelta(hours=7))


def read_comparison(directory: Path) -> list[dict]:
    return json.loads((directory / "comparison.json").read_text(encoding="utf-8"))


def cases_succeeded(rows: list[dict], *, repeats: int, selected: int) -> bool:
    return len(rows) == repeats and all(
        row["model"] == MODEL and row["complete"] and row["selected"] == selected
        and row["attempted"] == selected and row["passed"] == selected
        and row["errors"] == 0 and row["safety_violations"] == 0
        for row in rows
    )


def retryable_preflight(rows: list[dict]) -> bool:
    if len(rows) != 1:
        return False
    error = rows[0].get("provider_stop", {}).get("error", "")
    return "429" in error and not any(marker in error for marker in ("AuthenticationError", "401", "402"))


def sessions_succeeded(rows: list[dict]) -> bool:
    return cases_succeeded(rows, repeats=1, selected=1) and len(rows[0]["sessions"]) == 20 and all(
        not session["error"] and session["write_safety_passed"] and len(session["turns"]) > 0
        for session in rows[0]["sessions"]
    )


class Controller:
    def __init__(self, directory: Path, *, interval: int, attempts: int):
        self.directory = directory.resolve()
        if self.directory.parent != RESULTS.resolve() or not (self.directory / "manifest.json").is_file():
            raise ValueError("Controller must use a newly prepared run under eval/results")
        self.interval, self.attempts = interval, attempts
        self.runs: list[str] = []

    def event(self, kind: str, **details) -> None:
        row = {"time": datetime.now(CLOCK).isoformat(), "event": kind, **details}
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()

    def evaluate(self, stage: str, extra: list[str]) -> list[dict]:
        name = self.directory.name + "_" + stage
        self.event("evaluation_started", stage=stage, run=name)
        with (self.directory / (stage + ".log")).open("x", encoding="utf-8") as stream:
            process = subprocess.run(
                [sys.executable, "tests/test_agents/evaluate_agent.py", "--dataset", "../eval/test_cases/agent_cases_v2_1.json",
                 "--model", MODEL, "--delay", "4", "--run-name", name, *extra],
                cwd=BACKEND, stdout=stream, stderr=subprocess.STDOUT, check=False,
                timeout=3600, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        self.runs.append(name)
        rows = read_comparison(RESULTS / name)
        self.event("evaluation_finished", stage=stage, run=name, exit_code=process.returncode,
                   attempted=sum(row["attempted"] for row in rows), passed=sum(row["passed"] for row in rows),
                   errors=sum(row["errors"] for row in rows), sessions_attempted=sum(len(row["sessions"]) for row in rows))
        return rows

    def finish(self, status: str, **details) -> int:
        before = json.loads((self.directory / "protected_previous_artifacts.json").read_text(encoding="utf-8"))
        changed = [name for name, value in before.items() if not (ROOT / name).is_file()
                   or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != value]
        payload = {"status": status, "development_only": True, "model": MODEL, "runs": self.runs,
                   "independent_review_labels": 0, "semantic_task_success": "NEEDS_HUMAN_REVIEW",
                   "protected_files_verified": len(before), "protected_files_unchanged": not changed,
                   "changed": changed, **details}
        with (self.directory / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        report = ["# Mistral local automatic resume", "", f"Status: **{status}** (development only).", "",
                  "Model: `mistralai/mistral-small-2603`. Dataset v2.1, scorer 2.2.", "",
                  "Completed case gates and session write-safety checks do not establish semantic task success.", "",
                  f"Historical artifacts checked: {len(before)}; unchanged: {not changed}.", "",
                  "See [result.json](result.json) and [events.jsonl](events.jsonl).", ""]
        report.extend(f"- [{name}](../{name}/report.md)" for name in self.runs)
        with (self.directory / "report.md").open("x", encoding="utf-8") as stream:
            stream.write("\n".join(report) + "\n")
        self.event("controller_finished", status=status, protected_files_unchanged=not changed)
        return 0 if status == "EVALUATIONS_COMPLETED_PENDING_HUMAN_REVIEW" and not changed else 2

    def run(self) -> int:
        # Exclusive start prevents launching two controllers against one directory.
        with (self.directory / "started.json").open("x", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "interval_seconds": self.interval, "max_preflights": self.attempts}, stream)
        self.event("controller_started", pid=os.getpid())
        try:
            for attempt in range(1, self.attempts + 1):
                self.event("waiting", seconds=self.interval, next_preflight=attempt)
                time.sleep(self.interval)
                rows = self.evaluate(f"preflight_{attempt:02}", ["--case", "REMINDER-12"])
                if cases_succeeded(rows, repeats=1, selected=1):
                    break
                if not retryable_preflight(rows):
                    return self.finish("STOPPED_PREFLIGHT_ERROR_OR_FAILED_CASE")
            else:
                return self.finish("POLL_LIMIT_REACHED_PROVIDER_STILL_UNAVAILABLE")
            rows = self.evaluate("reminder_60", ["--category", "reminder", "--repeats", "3"])
            if not cases_succeeded(rows, repeats=3, selected=20):
                return self.finish("STOPPED_REMINDER_BATCH_INCOMPLETE_OR_FAILED")
            rows = self.evaluate("sessions_20", ["--case", "REMINDER-12", "--sessions"])
            if not sessions_succeeded(rows):
                return self.finish("STOPPED_SESSIONS_INCOMPLETE_OR_FAILED")
            return self.finish("EVALUATIONS_COMPLETED_PENDING_HUMAN_REVIEW")
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            self.event("controller_error", error=f"{type(exc).__name__}: {exc}")
            return self.finish("STOPPED_CONTROLLER_ERROR", error=f"{type(exc).__name__}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller-dir", required=True, type=Path)
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--attempts", type=int, default=12)
    args = parser.parse_args()
    if args.interval < 300 or not 1 <= args.attempts <= 12:
        parser.error("Poll no more than once per 5 minutes, at most 12 preflights")
    return Controller(args.controller_dir, interval=args.interval, attempts=args.attempts).run()


if __name__ == "__main__":
    raise SystemExit(main())
