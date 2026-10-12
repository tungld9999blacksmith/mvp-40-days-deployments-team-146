"""Versioned LLM prompt texts.

Each prompt is a plain UTF-8 file in ``texts/<name>.txt``; git keeps the history of the
text itself. ``texts/versions.lock.json`` maps every prompt to an integer ``version``
and the ``sha256`` of the text that version describes. ``refresh_lock`` (run by
``backend/scripts/prompt_sync.py lock``) bumps the version of every changed text, and
``stale_prompts`` lists the texts that changed without a lock refresh, which the test
suite rejects.

The Hub fields (``pushed_sha256``, ``hub_commit``) are written by the push / pull
commands in ``hub.py``; they say which version LangSmith Prompt Hub already holds.
"""

from __future__ import annotations

import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any

TEXTS_DIR = Path(__file__).resolve().parent / "texts"
LOCK_PATH = TEXTS_DIR / "versions.lock.json"

Lock = dict[str, dict[str, Any]]


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(name: str, texts_dir: Path = TEXTS_DIR) -> str:
    # Bytes, not text mode: no newline translation, so the hash matches the file exactly.
    return (texts_dir / f"{name}.txt").read_bytes().decode("utf-8")


def read_lock(lock_path: Path = LOCK_PATH) -> Lock:
    if not lock_path.exists():
        return {}
    return json.loads(lock_path.read_bytes().decode("utf-8"))


def write_lock(lock: Lock, lock_path: Path = LOCK_PATH) -> None:
    payload = json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    lock_path.write_bytes(payload.encode("utf-8"))


def prompt_names(texts_dir: Path = TEXTS_DIR) -> list[str]:
    return sorted(path.stem for path in texts_dir.glob("*.txt"))


def refresh_lock(texts_dir: Path = TEXTS_DIR, lock_path: Path = LOCK_PATH) -> Lock:
    """Lock every text file: new prompts start at version 1, changed ones get the next version."""
    lock = read_lock(lock_path)
    names = prompt_names(texts_dir)
    for name in names:
        digest = sha256_of(read_text(name, texts_dir))
        entry = lock.get(name)
        if entry is None:
            lock[name] = {"version": 1, "sha256": digest, "pushed_sha256": None, "hub_commit": None}
        elif entry["sha256"] != digest:
            entry["version"] = int(entry["version"]) + 1
            entry["sha256"] = digest
    for name in sorted(set(lock) - set(names)):  # file removed: drop its entry
        del lock[name]
    lock = {name: lock[name] for name in names}
    write_lock(lock, lock_path)
    return lock


def stale_prompts(texts_dir: Path = TEXTS_DIR, lock_path: Path = LOCK_PATH) -> list[str]:
    """Names whose text differs from the locked sha256, or that have no lock entry."""
    lock = read_lock(lock_path)
    return [
        name
        for name in prompt_names(texts_dir)
        if name not in lock or lock[name]["sha256"] != sha256_of(read_text(name, texts_dir))
    ]


@cache
def load_prompt(name: str) -> str:
    """Text of prompt ``name`` as shipped in the repository."""
    return read_text(name)


@cache
def prompt_version(name: str) -> int:
    """Locked version of prompt ``name``; attached to traces so a run names its prompt."""
    return int(read_lock()[name]["version"])
