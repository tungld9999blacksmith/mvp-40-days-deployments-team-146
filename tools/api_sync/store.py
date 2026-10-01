"""Sync state kept next to the generated code, in ``<out>/.api-sync/``.

    manifest.json          last sync: version, date, source, selection, file
    history.jsonl          one JSON line per sync (append-only)
    snapshots/<version>.json   the OpenAPI document used by that sync
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

STATE_DIR = ".api-sync"


def new_version() -> tuple[str, str]:
    """``(version, ISO timestamp)`` — the version is the sync date/time."""
    now = datetime.now().astimezone()
    return now.strftime("%Y-%m-%d_%H%M%S"), now.isoformat(timespec="seconds")


class Store:
    def __init__(self, out_dir: Path) -> None:
        self.root = out_dir / STATE_DIR
        self.manifest_path = self.root / "manifest.json"
        self.history_path = self.root / "history.jsonl"
        self.snapshots_dir = self.root / "snapshots"

    def manifest(self) -> dict[str, Any] | None:
        if not self.manifest_path.exists():
            return None
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def snapshot(self, version: str) -> dict[str, Any] | None:
        path = self.snapshots_dir / f"{version}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def latest_snapshot(self) -> dict[str, Any] | None:
        manifest = self.manifest()
        return self.snapshot(manifest["version"]) if manifest else None

    def history(self) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        lines = self.history_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def record_sync(self, spec: dict[str, Any], manifest: dict[str, Any], history_entry: dict[str, Any]) -> None:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        snapshot = self.snapshots_dir / f"{manifest['version']}.json"
        snapshot.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
        self.manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        with self.history_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
