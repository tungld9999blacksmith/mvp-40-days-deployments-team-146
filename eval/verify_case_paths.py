"""Check historical SHA-256 manifests after the test_cases directory migration.

Reports current matches separately from relocated files and archived pre-rename
source. Archived source is not evidence that the current source is unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "eval/results/test_cases_folder_rename_20261009_68"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_entry(name, expected):
    name = name.replace("\\", "/")
    current = (ROOT / name).resolve()
    if not current.is_relative_to(ROOT):
        raise ValueError("Manifest path outside repository")
    if current.is_file() and digest(current) == expected:
        return "CURRENT_MATCH"
    if name.startswith("eval/datasets/"):
        relocated = ROOT / name.replace("eval/datasets/", "eval/test_cases/", 1)
        if relocated.is_file() and digest(relocated) == expected:
            return "RELOCATED_BYTES_MATCH"
    archived = MIGRATION / "before_sources" / name
    if archived.is_file() and digest(archived) == expected:
        return "ARCHIVED_ORIGINAL_MATCH_CURRENT_SOURCE_DIFFERS"
    return "MISSING_OR_HASH_MISMATCH"


def verify(mapping):
    checks = {name: resolve_entry(name, expected) for name, expected in mapping.items()}
    return {"files_verified": len(checks), "counts": dict(Counter(checks.values())),
            "mismatches": [name for name, status in checks.items() if status == "MISSING_OR_HASH_MISMATCH"],
            "archived_originals": [name for name, status in checks.items() if status.startswith("ARCHIVED_")],
            "boundary": "Archived originals preserve the previous revision; current evaluator paths have changed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--key", help="Select a nested SHA-256 mapping, e.g. source_hashes")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    mapping = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.key:
        mapping = mapping[args.key]
    if not isinstance(mapping, dict) or not all(isinstance(value, str) and len(value) == 64 for value in mapping.values()):
        raise ValueError("Expected a path-to-SHA256 mapping")
    result = verify(mapping)
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result))
    raise SystemExit(bool(result["mismatches"]))
