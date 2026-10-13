"""Versioned LLM prompt texts.

The Python module that uses a prompt holds its text as a string constant: that constant
is the source of truth (``PROMPT_SOURCES`` lists where each one lives). ``texts/<name>.txt``
is a generated copy (``export_texts``, run by ``backend/scripts/prompt_sync.py lock``) that
git keeps for history and that is pushed to LangSmith Prompt Hub; never edit it by hand.
``texts/versions.lock.json`` maps every prompt to an integer ``version`` and the ``sha256``
of the text that version describes. ``refresh_lock`` bumps the version of every changed
text, ``stale_prompts`` lists the texts that changed without a lock refresh and
``drifted_prompts`` lists the copies that no longer match the code; the test suite rejects both.

The Hub fields (``pushed_sha256``, ``hub_commit``) are written by the push command in
``scripts/prompt_sync.py``; they say which version LangSmith Prompt Hub already holds.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from functools import cache
from pathlib import Path
from typing import Any

TEXTS_DIR = Path(__file__).resolve().parent / "texts"
LOCK_PATH = TEXTS_DIR / "versions.lock.json"

Lock = dict[str, dict[str, Any]]

# prompt name -> (module, constant) holding its text. Add a row when adding a prompt.
PROMPT_SOURCES: dict[str, tuple[str, str]] = {
    "customer_chat": ("src.modules.conversation.service", "_SYSTEM_PROMPT"),
    "ev_care_base": ("src.agents.prompts", "EV_CARE_BASE_PROMPT"),
    "follow_up_classifier": ("src.modules.follow_up.classifier", "SYSTEM_PROMPT"),
    "injection_note": ("src.agents.conversation_guards.input_guard", "INJECTION_SYSTEM_NOTE"),
    "rag_generator": ("src.agents.tools.RAG.query.generator", "SYSTEM_PROMPT"),
    "rag_rewriter": ("src.agents.tools.RAG.query.rewriter", "SYSTEM_PROMPT"),
    "tool_review": ("src.agents.tool_review", "REVIEW_PROMPT"),
}


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


def source_text(name: str) -> str:
    """Text of prompt ``name`` as written in its Python module (the source of truth)."""
    module, attr = PROMPT_SOURCES[name]
    return getattr(importlib.import_module(module), attr)


def export_texts(texts_dir: Path = TEXTS_DIR) -> list[str]:
    """Write ``texts/<name>.txt`` from the code constants; return the names whose file changed."""
    changed = []
    for name in sorted(PROMPT_SOURCES):
        path = texts_dir / f"{name}.txt"
        data = source_text(name).encode("utf-8")
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)  # bytes: no newline translation, the hash stays exact
            changed.append(name)
    for path in texts_dir.glob("*.txt"):  # prompt removed from the code: drop its copy
        if path.stem not in PROMPT_SOURCES:
            path.unlink()
            changed.append(path.stem)
    return changed


def drifted_prompts(texts_dir: Path = TEXTS_DIR) -> list[str]:
    """Names whose ``.txt`` copy differs from the code constant, or that exist on only one side."""
    on_disk = set(prompt_names(texts_dir))
    drifted = sorted(on_disk ^ set(PROMPT_SOURCES))
    drifted += [
        name for name in sorted(on_disk & set(PROMPT_SOURCES)) if read_text(name, texts_dir) != source_text(name)
    ]
    return drifted


@cache
def prompt_version(name: str) -> int:
    """Locked version of prompt ``name``; attached to traces so a run names its prompt."""
    return int(read_lock()[name]["version"])
