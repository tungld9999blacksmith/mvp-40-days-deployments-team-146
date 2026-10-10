from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "eval" / "results"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historical_hashes() -> dict[str, str]:
    roots = [ROOT / "backend/tests/test_agents/evaluationLLM/results", ROOT / "backend/tests/test_agents/test_rag/evaluation", ROOT / "backend/tests/evaluation"]
    return {
        str(path.relative_to(ROOT)): digest(path)
        for folder in roots if folder.exists() for path in folder.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".py", ".pyc"}
    }


def write_new(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, default=str)


def create_run(kind: str, configuration: dict, run_name: str | None = None) -> tuple[Path, dict]:
    stamp = datetime.now(timezone(timedelta(hours=7))).strftime("%Y%m%d_%H%M%S")
    name = run_name or f"{kind}_{stamp}_{uuid4().hex[:8]}"
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for c in name) or name in {".", ".."}:
        raise ValueError("Invalid run name")
    path = (RESULTS / name).resolve()
    if path.parent != RESULTS.resolve():
        raise ValueError("Results must stay under eval/results")
    path.mkdir(parents=True, exist_ok=False)
    manifest = {
        "version": 2, "kind": kind, "configuration": configuration,
        "created_at": datetime.now(timezone(timedelta(hours=7))).isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        "working_tree_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL)).hexdigest(),
        "source_hashes": {str(p.relative_to(ROOT)): digest(p) for folder in [ROOT / "backend/src/agents", ROOT / "backend/src/infrastructure/llm", ROOT / "backend/tests/evaluation_v2", ROOT / "eval/test_cases"] for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts} | {"backend/src/config.py": digest(ROOT / "backend/src/config.py")},
        "historical_files_before": historical_hashes(),
    }
    write_new(path / "manifest.json", manifest)
    return path, manifest


def verify_history(run: Path, manifest: dict) -> dict:
    before = manifest["historical_files_before"]
    after = {name: digest(ROOT / name) if (ROOT / name).is_file() else None for name in before}
    changed = [name for name in before if after[name] != before[name]]
    result = {"unchanged": not changed, "files_verified": len(before), "changed": changed, "historical_files_after": after}
    write_new(run / "preservation.json", result)
    if changed:
        raise RuntimeError("Historical evaluation artifacts changed")
    return result
