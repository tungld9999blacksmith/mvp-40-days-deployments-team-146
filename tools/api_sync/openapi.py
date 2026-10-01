"""Load an OpenAPI document and index its component schemas as API models.

A "model" is an entry of ``components.schemas``. Each model gets a role:
``input`` if it is reachable from a request body, ``output`` if it is
reachable from a response body (both is possible), ``unused`` otherwise.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
HTTP_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")
# FastAPI adds a 422 HTTPValidationError response to every endpoint; it is not
# part of the endpoint's real output contract.
IGNORED_RESPONSE_CODES = {"422"}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_spec(source: str) -> dict[str, Any]:
    """``source`` is a URL, a JSON file path, or ``app`` (import the backend)."""
    if source == "app":
        return _load_from_app()
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=15) as resp:
            return json.load(resp)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def _load_from_app() -> dict[str, Any]:
    """Build the spec offline by importing ``src.main:app`` with the backend's uv env."""
    code = (
        "import json, sys; from src.main import app; "
        "open(sys.argv[1], 'w', encoding='utf-8').write(json.dumps(app.openapi()))"
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "openapi.json"
        subprocess.run(
            ["uv", "run", "python", "-c", code, str(out)],
            cwd=BACKEND_DIR,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return json.loads(out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------
@dataclass
class Endpoint:
    method: str
    path: str
    summary: str
    tags: list[str]
    inputs: set[str] = field(default_factory=set)  # models used directly by the request body
    outputs: set[str] = field(default_factory=set)  # models used directly by response bodies
    parameters: list[dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.method.upper()} {self.path}"


@dataclass
class Model:
    name: str  # component name in the spec
    ts_name: str  # identifier used in generated TypeScript
    schema: dict[str, Any]
    roles: set[str] = field(default_factory=set)  # {"input", "output"}
    used_by: list[tuple[str, str]] = field(default_factory=list)  # (endpoint key, role)

    @property
    def kind(self) -> str:
        if not self.roles:
            return "unused"
        return "both" if len(self.roles) == 2 else next(iter(self.roles))

    @property
    def description(self) -> str:
        # Pydantic's `title` is just the class name, so only `description` counts.
        return (self.schema.get("description") or "").strip()


def ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def direct_refs(node: Any) -> set[str]:
    """Names of every component referenced anywhere inside ``node``."""
    found: set[str] = set()
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            ref = cur.get("$ref")
            if isinstance(ref, str):
                found.add(ref_name(ref))
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return found


def closure(names: set[str], schemas: dict[str, Any]) -> set[str]:
    """``names`` plus every component they reference, transitively."""
    result: set[str] = set()
    todo = list(names)
    while todo:
        name = todo.pop()
        if name in result or name not in schemas:
            continue
        result.add(name)
        todo.extend(direct_refs(schemas[name]) - result)
    return result


# Path segments FastAPI puts in qualified names that carry no meaning.
_GENERIC_SEGMENTS = {"src", "app", "modules", "schemas", "schema", "models", "model", "domain", "api"}


def ts_identifier(name: str) -> str:
    """``Model-Input`` / ``Body_sign_in`` -> ``ModelInput`` / ``BodySignIn``.

    FastAPI qualifies clashing class names with their module path
    (``src__modules__vehicle_owner_onboarding__schemas__SignInData``); keep only
    the meaningful module segment: ``VehicleOwnerOnboardingSignInData``.
    """
    if "__" in name:
        segments = name.split("__")
        meaningful = [s for s in segments[:-1] if s.lower() not in _GENERIC_SEGMENTS]
        name = "_".join(meaningful[-1:] + segments[-1:])
    parts = [p for p in re.split(r"[^0-9A-Za-z]+", name) if p]
    ident = "".join(p[:1].upper() + p[1:] for p in parts) or "Model"
    return f"_{ident}" if ident[0].isdigit() else ident


def _content_refs(content: dict[str, Any] | None) -> set[str]:
    refs: set[str] = set()
    for media in (content or {}).values():
        refs |= direct_refs(media.get("schema", {}))
    return refs


def index_spec(spec: dict[str, Any]) -> tuple[dict[str, Model], list[Endpoint]]:
    schemas: dict[str, Any] = spec.get("components", {}).get("schemas", {})

    models: dict[str, Model] = {}
    used_ts: set[str] = set()
    for name in sorted(schemas):
        ts = base = ts_identifier(name)
        n = 2
        while ts in used_ts:
            ts, n = f"{base}{n}", n + 1
        used_ts.add(ts)
        models[name] = Model(name=name, ts_name=ts, schema=schemas[name])

    endpoints: list[Endpoint] = []
    for path, item in spec.get("paths", {}).items():
        shared_params = item.get("parameters", [])
        for method in HTTP_METHODS:
            op = item.get(method)
            if op is None:
                continue
            ep = Endpoint(
                method=method,
                path=path,
                summary=(op.get("summary") or "").strip(),
                tags=op.get("tags", []),
                parameters=shared_params + op.get("parameters", []),
            )
            ep.inputs = _content_refs(op.get("requestBody", {}).get("content"))
            for code, resp in op.get("responses", {}).items():
                if code not in IGNORED_RESPONSE_CODES:
                    ep.outputs |= _content_refs(resp.get("content"))
            endpoints.append(ep)

            for role, roots in (("input", ep.inputs), ("output", ep.outputs)):
                for name in closure(roots, schemas):
                    models[name].roles.add(role)
                    models[name].used_by.append((ep.key, role))
    return models, endpoints


def select_models(
    models: dict[str, Model],
    endpoints: list[Endpoint],
    *,
    patterns: list[str] | None = None,
    tags: list[str] | None = None,
    kind: str = "all",
) -> tuple[set[str], list[str]]:
    """Pick models, then add their dependencies so the output always compiles.

    Returns ``(selected names, patterns that matched nothing)``.
    """
    candidates = set(models)
    if kind in ("input", "output"):
        candidates = {n for n in candidates if kind in models[n].roles}
    if tags:
        wanted = {t.lower() for t in tags}
        tagged: set[str] = set()
        for ep in endpoints:
            if wanted & {t.lower() for t in ep.tags}:
                tagged |= ep.inputs | ep.outputs
        schemas = {n: m.schema for n, m in models.items()}
        candidates &= closure(tagged, schemas)

    unmatched: list[str] = []
    if patterns:
        picked: set[str] = set()
        for pat in patterns:
            hits = {
                n
                for n in candidates
                if fnmatch.fnmatch(n.lower(), pat.lower())
                or fnmatch.fnmatch(models[n].ts_name.lower(), pat.lower())
            }
            if not hits:
                unmatched.append(pat)
            picked |= hits
        candidates = picked

    schemas = {n: m.schema for n, m in models.items()}
    return closure(candidates, schemas), unmatched


def find_model(models: dict[str, Model], name: str) -> Model | None:
    lowered = name.lower()
    for m in models.values():
        if lowered in (m.name.lower(), m.ts_name.lower()):
            return m
    return None
