"""Versioned prompts: show status, lock versions, push to and diff against LangSmith Prompt Hub.

Each prompt is a string constant in the Python module that uses it (see ``PROMPT_SOURCES`` in
``src/infrastructure/prompts/registry.py``); that constant is the source of truth.
``texts/<name>.txt`` is a generated copy and git holds its history. ``lock`` regenerates the
copies from the code and bumps the version of every changed prompt; ``push`` uploads locked
prompts to the Hub (one repository per prompt, tagged ``v<version>``); ``pull`` shows how the
latest Hub commit (or ``--commit``) differs from the code, so you can copy the change into the
Python constant by hand.

Run from ``backend/``:
    uv run python scripts/prompt_sync.py status
    uv run python scripts/prompt_sync.py lock
    uv run python scripts/prompt_sync.py push [NAME ...]
    uv run python scripts/prompt_sync.py pull [NAME ...] [--commit HASH] [--out DIR]
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from langsmith import Client

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from src.config import get_settings  # noqa: E402
from src.infrastructure.prompts.hub import build_template, hub_repo_name, text_from_manifest  # noqa: E402
from src.infrastructure.prompts.registry import (  # noqa: E402
    PROMPT_SOURCES,
    drifted_prompts,
    export_texts,
    prompt_names,
    read_lock,
    read_text,
    refresh_lock,
    source_text,
    stale_prompts,
    write_lock,
)

DEFAULT_PREFIX = "ev-care-"


def _client() -> Client:
    settings = get_settings()
    if not settings.langchain_api_key:
        sys.exit("LANGCHAIN_API_KEY is not set in the root .env")
    return Client(
        api_key=settings.langchain_api_key,
        api_url=settings.langchain_endpoint or None,
        workspace_id=settings.langchain_workspace_id or None,
    )


def _selected(names: list[str]) -> list[str]:
    known = sorted(PROMPT_SOURCES)
    unknown = sorted(set(names) - set(known))
    if unknown:
        sys.exit(f"Unknown prompt(s): {', '.join(unknown)}. Known: {', '.join(known)}")
    return names or known


def cmd_status(_: argparse.Namespace) -> None:
    lock = read_lock()
    stale = set(stale_prompts()) | set(drifted_prompts())
    for name in sorted(PROMPT_SOURCES):
        entry = lock.get(name, {})
        if name in stale:
            file_state = "CHANGED, run `lock`"
        else:
            file_state = "locked"
        if entry.get("pushed_sha256") is None:
            hub_state = "never pushed"
        elif entry["pushed_sha256"] == entry.get("sha256"):
            hub_state = f"in sync (commit {entry.get('hub_commit')})"
        else:
            hub_state = "unpushed changes"
        version = f"v{entry['version']}" if entry else "-"
        print(f"{name:24} {version:6} {file_state:22} hub: {hub_state}")


def cmd_lock(_: argparse.Namespace) -> None:
    before = read_lock()
    for name in export_texts():
        print(f"{name}: texts/{name}.txt regenerated from the code")
    after = refresh_lock()
    for name, entry in after.items():
        old = before.get(name, {}).get("version")
        if old is None:
            print(f"{name}: new, v{entry['version']}")
        elif old != entry["version"]:
            print(f"{name}: v{old} -> v{entry['version']}")
    if before == after:
        print("No changes; lock is up to date.")


def cmd_push(args: argparse.Namespace) -> None:
    stale = sorted(set(stale_prompts()) | set(drifted_prompts()))
    if stale:
        sys.exit(f"Prompts changed without a lock refresh: {', '.join(stale)}. Run `lock` first.")
    lock = read_lock()
    client = None
    for name in _selected(args.names):
        entry = lock[name]
        if entry["pushed_sha256"] == entry["sha256"]:
            print(f"{name}: in sync with the Hub, skipped")
            continue
        client = client or _client()
        repo = hub_repo_name(name, args.prefix)
        client.push_prompt(
            repo,
            object=build_template(read_text(name)),
            description=f"EV Care prompt {name}",
            commit_tags=[f"v{entry['version']}"],
        )
        # The Hub answers with the URL only; the latest commit is the one just created.
        latest = client.pull_prompt_commit(repo, skip_cache=True)
        entry["pushed_sha256"] = entry["sha256"]
        entry["hub_commit"] = latest.commit_hash
        write_lock(lock)
        print(f"{name}: pushed v{entry['version']} to {repo} (commit {latest.commit_hash[:8]})")


def cmd_pull(args: argparse.Namespace) -> None:
    """Show Hub vs code. The code is the source of truth, so nothing is written back to it."""
    names = _selected(args.names)
    if args.commit and len(names) != 1:
        sys.exit("--commit needs exactly one prompt name")
    client = None
    for name in names:
        client = client or _client()
        repo = hub_repo_name(name, args.prefix)
        identifier = f"{repo}:{args.commit}" if args.commit else repo
        commit = client.pull_prompt_commit(identifier, skip_cache=True)
        hub_text = text_from_manifest(commit.manifest)
        local = source_text(name)
        if hub_text == local:
            print(f"{name}: the code already matches commit {commit.commit_hash[:8]}")
            continue
        module, attr = PROMPT_SOURCES[name]
        print(f"{name}: commit {commit.commit_hash[:8]} differs from {module}.{attr}")
        diff = difflib.unified_diff(
            local.splitlines(), hub_text.splitlines(), "code", f"hub@{commit.commit_hash[:8]}", lineterm=""
        )
        print("\n".join(diff))
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / f"{name}.txt").write_bytes(hub_text.encode("utf-8"))
            print(f"{name}: Hub text saved to {args.out / (name + '.txt')}")
    print("Nothing in the code was changed. Copy what you want into the Python constant, then run `lock`.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="show versions and Hub state").set_defaults(func=cmd_status)
    sub.add_parser("lock", help="bump versions of changed prompts").set_defaults(func=cmd_lock)

    push = sub.add_parser("push", help="upload locked prompts to the Hub")
    push.add_argument("names", nargs="*")
    push.set_defaults(func=cmd_push)

    pull = sub.add_parser("pull", help="show how the Hub prompts differ from the code")
    pull.add_argument("names", nargs="*")
    pull.add_argument("--commit", help="Hub commit hash (one prompt only); default: latest")
    pull.add_argument("--out", type=Path, help="also save the Hub texts into this folder")
    pull.set_defaults(func=cmd_pull)

    for command in (push, pull):
        command.add_argument("--prefix", default=DEFAULT_PREFIX, help="Hub repository name prefix")

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
