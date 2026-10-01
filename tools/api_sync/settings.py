"""Tool configuration, read from ``tools/api_sync/.env``.

Priority (highest first): CLI flags > process environment > ``.env`` file >
built-in defaults. The tool never reads ``backend/.env``, so its LLM key and
output folders stay independent from the backend.

Relative paths are resolved against the repository root, so the tool behaves
the same whatever directory it is launched from.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from openapi import REPO_ROOT

TOOL_DIR = Path(__file__).resolve().parent
ENV_FILE = TOOL_DIR / ".env"
ENV_EXAMPLE_FILE = TOOL_DIR / ".env.example"

DEFAULT_SOURCE = "http://localhost:8000/openapi.json"
DEFAULT_OUT = "frontend/src/shared/api/generated"
DEFAULT_MOCK_OUT = "frontend/src/mocks/generated"
DEFAULT_HINTS_FILE = "tools/api_sync/api_hints.json"


def read_env_file(path: Path) -> dict[str, str]:
    """Parse a simple ``KEY=VALUE`` file (comments, blank lines and quotes allowed)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif " #" in value:  # inline comment after an unquoted value
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def _resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.drive or (path.is_absolute() and len(path.parts) > 1 and Path(path.parts[0], path.parts[1]).exists()):
        return path  # a real absolute path (C:\..., //server/..., /home/...)
    # Relative, or "/backend/..." meaning "from the repo root" (on Windows a
    # drive-less "/x" would otherwise land on the root of the current drive).
    return REPO_ROOT / str(path).lstrip("/\\")


@dataclass(frozen=True)
class Settings:
    env_file: Path
    env_file_found: bool
    source: str
    out: Path
    mock_out: Path
    hints_file: Path
    llm_provider: str
    llm_api_key: str
    llm_model: str
    llm_base_url: str


def load_settings(env_file: Path = ENV_FILE) -> Settings:
    file_env = read_env_file(env_file)

    def get(name: str, default: str = "") -> str:
        return os.environ.get(name) or file_env.get(name) or default

    return Settings(
        env_file=env_file,
        env_file_found=env_file.exists(),
        source=get("API_SYNC_SOURCE", DEFAULT_SOURCE),
        out=_resolve_path(get("API_SYNC_OUT", DEFAULT_OUT)),
        mock_out=_resolve_path(get("API_SYNC_MOCK_OUT", DEFAULT_MOCK_OUT)),
        hints_file=_resolve_path(get("API_SYNC_HINTS_FILE", DEFAULT_HINTS_FILE)),
        llm_provider=get("LLM_PROVIDER", "openai").lower(),
        llm_api_key=get("LLM_API_KEY"),
        llm_model=get("LLM_MODEL"),
        llm_base_url=get("LLM_BASE_URL"),
    )
