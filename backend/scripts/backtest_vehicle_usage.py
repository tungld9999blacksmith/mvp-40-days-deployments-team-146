"""Offline temporal backtest: explicit anonymous JSON input or synthetic fixtures.

Input: {"series": [{"name": "...", "milestoneKm": 12000,
"officialDueDate": "2027-01-01", "cutoffs": ["2026-09-29T02:00:00+00:00"],
"readings": [{"odoKm": 10000, "recordedAt": "2026-09-01T02:00:00+00:00"}]}]}.
No database, LLM, OEM or provider calls. No model parameters are fitted here.
"""

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from src.modules.vehicle_usage.backtest import evaluate_series  # noqa: E402
from src.modules.vehicle_usage.domain import Reading  # noqa: E402


def fixtures():
    start = datetime(2026, 8, 1, 2, tzinfo=UTC)
    scenarios = {
        "steady-high": lambda day: 200,
        "steady-low": lambda day: 20,
        "weekend": lambda day: 280 if (start + timedelta(days=day)).weekday() >= 5 else 0,
        "stopped": lambda day: 0,
        "changing-usage": lambda day: 200 if day < 15 else 10,
        "sparse": lambda day: 200,
    }
    series = []
    for name, speed in scenarios.items():
        odo, readings = 1000, []
        for day in range(91):
            if day:
                odo += speed(day)
            if name == "sparse" and day % 10:
                continue
            readings.append(Reading(odo, start + timedelta(days=day)))
        milestone = 1000 + (speed(1) * 28 if name not in {"weekend", "changing-usage", "stopped"} else 2240) + 1200
        series.append(
            (
                name,
                evaluate_series(
                    readings,
                    milestone_km=milestone,
                    official_due_date=date(2027, 1, 1),
                    cutoffs=[start + timedelta(days=day) for day in (21, 28)],
                ),
            )
        )
    return dict(series)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", action="store_true")
    source.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.fixture:
        series = fixtures()
    else:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        series = {
            row["name"]: evaluate_series(
                [Reading(point["odoKm"], datetime.fromisoformat(point["recordedAt"])) for point in row["readings"]],
                milestone_km=row["milestoneKm"],
                official_due_date=date.fromisoformat(row["officialDueDate"]),
                cutoffs=[datetime.fromisoformat(at) for at in row["cutoffs"]],
            )
            for row in data["series"]
        }
    report = {
        "dataset": "synthetic-fixture" if args.fixture else "provided-anonymous-series",
        "providerCalls": 0,
        "productionAccuracyValidated": False,
        "label": "First observed daily crossing; unobserved crossings remain unscored.",
        "series": series,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"series": len(series), "providerCalls": 0, "dataset": report["dataset"]}))


if __name__ == "__main__":
    main()
