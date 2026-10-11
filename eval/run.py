"""Agent-level evaluation runner (D4).

Scores a golden dataset against a predictions file and writes a report with
confidence intervals. Predictions are produced by running the real agent (see
``eval/README.md`` for the adapter), so this runner stays offline and
dependency-light and can be unit-tested.

Usage:
    python -m eval.run --suite tool_calling \
        --dataset eval/datasets/tool_calling_golden.jsonl \
        --predictions path/to/predictions.jsonl

Predictions JSONL rows:
    tool_calling : {"id": "TC01", "actual_calls": [{"tool": "...", "args": {...}}]}
    trajectory   : {"id": "TR01", "actual_sequence": ["tool_a", "tool_b"]}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval.metrics import stats, tool_calling, trajectory

KNOWN_TOOLS = {
    "get_due_maintenance",
    "estimate_service_cost",
    "find_workshops",
    "get_available_slots",
    "propose_booking",
    "search_ev_knowledge",
}

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def _index(rows: list[dict], key: str = "id") -> dict[str, dict]:
    return {row[key]: row for row in rows}


def score_tool_calling_suite(dataset: list[dict], predictions: list[dict]) -> dict[str, Any]:
    preds = _index(predictions)
    selected, first, invalid, over = 0, 0, 0, 0
    arg_f1_samples: list[float] = []
    per_row: list[dict] = []
    scored = 0
    for case in dataset:
        pred = preds.get(case["id"])
        if pred is None:
            continue
        scored += 1
        score = tool_calling.score_tool_call(
            expected_tool=case.get("expected_tool"),
            expected_args=case.get("expected_args"),
            actual_calls=pred.get("actual_calls", []),
            known_tools=KNOWN_TOOLS,
        )
        selected += int(score.selected_correct)
        first += int(score.first_call_correct)
        invalid += int(score.invalid_call)
        over += int(score.over_called)
        arg_f1_samples.append(score.arg_f1)
        per_row.append({"id": case["id"], **vars(score)})

    return {
        "suite": "tool_calling",
        "scored": scored,
        "tool_selection_accuracy": str(stats.wilson_interval(selected, scored)),
        "first_call_accuracy": str(stats.wilson_interval(first, scored)),
        "invalid_call_rate": str(stats.wilson_interval(invalid, scored)),
        "over_calling_rate": str(stats.wilson_interval(over, scored)),
        "arg_f1_mean": str(stats.bootstrap_ci(arg_f1_samples)) if arg_f1_samples else "n/a",
        "per_row": per_row,
    }


def score_trajectory_suite(dataset: list[dict], predictions: list[dict]) -> dict[str, Any]:
    preds = _index(predictions)
    exact = 0
    recall_samples: list[float] = []
    redundancy_samples: list[float] = []
    efficiency_samples: list[float] = []
    overran = 0
    per_row: list[dict] = []
    scored = 0
    for case in dataset:
        pred = preds.get(case["id"])
        if pred is None:
            continue
        scored += 1
        score = trajectory.score_trajectory(
            expected_sequence=case.get("expected_sequence", []),
            actual_sequence=pred.get("actual_sequence", []),
            optimal_steps=case.get("optimal_steps"),
            max_steps=case.get("max_steps"),
        )
        exact += int(score.exact_match)
        recall_samples.append(score.in_order_recall)
        redundancy_samples.append(score.redundant_step_rate)
        efficiency_samples.append(score.step_efficiency)
        overran += int(score.overran)
        per_row.append({"id": case["id"], **vars(score)})

    return {
        "suite": "trajectory",
        "scored": scored,
        "exact_match_rate": str(stats.wilson_interval(exact, scored)),
        "in_order_recall_mean": str(stats.bootstrap_ci(recall_samples)) if recall_samples else "n/a",
        "redundant_step_rate_mean": str(stats.bootstrap_ci(redundancy_samples)) if redundancy_samples else "n/a",
        "step_efficiency_mean": str(stats.bootstrap_ci(efficiency_samples)) if efficiency_samples else "n/a",
        "overrun_rate": str(stats.wilson_interval(overran, scored)),
        "per_row": per_row,
    }


_SCORERS = {
    "tool_calling": score_tool_calling_suite,
    "trajectory": score_trajectory_suite,
}


def write_report(report: dict[str, Any], out_stem: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / f"{out_stem}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="EV Care agent evaluation runner")
    parser.add_argument("--suite", required=True, choices=sorted(_SCORERS))
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--predictions", required=True, help="JSONL of actual agent outputs")
    parser.add_argument("--out", default=None, help="Output stem under eval/results/")
    args = parser.parse_args()

    dataset = load_jsonl(args.dataset)
    predictions = load_jsonl(args.predictions)
    report = _SCORERS[args.suite](dataset, predictions)

    out_stem = args.out or f"{args.suite}_report"
    path = write_report(report, out_stem)

    summary = {k: v for k, v in report.items() if k != "per_row"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nReport written to {path}")
    if report["scored"] == 0:
        print("WARNING: no predictions matched the dataset ids.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
