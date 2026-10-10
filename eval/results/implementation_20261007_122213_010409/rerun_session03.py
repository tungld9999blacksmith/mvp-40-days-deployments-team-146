"""Live regression for the observed bare-ok failure, with isolated services."""
from __future__ import annotations

import asyncio
import json
import sys
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from src.agents.graph import build_graph
from tests.evaluation_v2.artifacts import (
    create_run,
    digest,
    verify_history,
    write_new,
)
from tests.evaluation_v2.dataset import DATASET, load_dataset
from tests.evaluation_v2.runner import evaluate_session


async def main():
    model = "mistralai/mistral-small-2603"
    args = Namespace(endpoint_order=["mistral/us", "mistral/eu"], max_tokens=1536, timeout=60)
    session = next(item for item in load_dataset()["sessions"] if item["id"] == "SESSION-03")
    directory, manifest = create_run("session_regression", {"model": model, "endpoint_order": args.endpoint_order, "max_tokens": args.max_tokens,
                                                          "temperature": .2, "session": session, "dataset_sha256": digest(DATASET), "runner_sha256": digest(Path(__file__)),
                                                          "business_services": "isolated SQLite/FakeRedis", "purpose": "DEVELOPMENT bare-ok regression; not acceptance"},
                                     "agent_v2_session03_mistral_fixed_20261007_01")
    print(f"Run: {directory}", flush=True)
    result = await evaluate_session(session, model, args, build_graph)
    final = result["turns"][-1] if result["turns"] else {}
    passed = not result["error"] and result["write_safety_passed"] and len(result["turns"]) == 4 and final.get("proposal_count") == 0 and "chọn rõ khung giờ" in final.get("answer", "")
    write_new(directory / "session_result.json", {"result": result, "regression_passed": passed, "semantic_acceptance": "NOT_MEASURED"})
    verify_history(directory, manifest)
    with (directory / "report.md").open("x", encoding="utf-8") as stream:
        stream.write(f"# Mistral SESSION-03 regression\n\nRegression: {'PASS' if passed else 'FAIL'}; not production acceptance.\n\nFinal answer:\n\n{final.get('answer', '')}\n\nProvider/runtime error: {result['error']}\n")
    print(json.dumps({"passed": passed, "error": result["error"], "report": str(directory / "report.md")}), flush=True)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
