"""api_sync — sync backend API schemas to TypeScript and generate sample data.

Run ``python tools/api_sync/api_sync.py --help``; see README.md for usage.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff import compare_specs, format_report  # noqa: E402
from hints import build_hints  # noqa: E402
from llm import LLMConfig, LLMError  # noqa: E402
from mockdata import MockGenerator  # noqa: E402
from openapi import find_model, index_spec, load_spec, select_models  # noqa: E402
from settings import ENV_EXAMPLE_FILE, load_settings  # noqa: E402
from store import Store, new_version  # noqa: E402
from typescript import property_signatures, render_file  # noqa: E402

SETTINGS = load_settings()
DEFAULT_FILE = "api-models.ts"
BACKEND_START_HINT = (
    "Start the backend first so the tool can read its schema:\n"
    "  cd backend && uv run uvicorn src.main:app --reload --port 8000\n"
    "Or read the schema without a running server: --source app"
)


def _split(values: list[str] | None) -> list[str]:
    """Accept both ``--models A B`` and ``--models A,B``."""
    return [v.strip() for item in values or [] for v in item.split(",") if v.strip()]


def _load(args: argparse.Namespace) -> dict[str, Any]:
    try:
        return load_spec(args.source)
    except urllib.error.URLError as exc:
        sys.exit(f"error: cannot fetch {args.source} ({exc.reason}).\nThe backend API is not running.\n{BACKEND_START_HINT}")
    except subprocess.CalledProcessError:
        sys.exit("error: could not import the backend app (uv run python in backend/).")
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"error: cannot read OpenAPI from {args.source}: {exc}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
def cmd_list(args: argparse.Namespace) -> int:
    spec = _load(args)
    models, endpoints = index_spec(spec)
    ts_names = {n: m.ts_name for n, m in models.items()}

    if args.fields:
        model = find_model(models, args.fields)
        if model is None:
            sys.exit(f"error: model '{args.fields}' not found")
        print(f"{model.ts_name}  ({model.name}, {model.kind})")
        if model.description:
            print(f"  {model.description.splitlines()[0]}")
        for name, (ts, required) in property_signatures(model.schema, ts_names).items():
            desc = (model.schema["properties"][name].get("description") or "").split("\n")[0]
            print(f"  {name}{'' if required else '?'}: {ts}" + (f"    // {desc}" if desc else ""))
        for key, role in sorted(set(model.used_by)):
            print(f"  used by {key} ({role})")
        return 0

    if args.endpoints:
        tags = {t.lower() for t in _split(args.tag)}
        for ep in endpoints:
            if tags and not tags & {t.lower() for t in ep.tags}:
                continue
            fmt = lambda names: ", ".join(ts_names[n] for n in sorted(names)) or "-"  # noqa: E731
            print(f"{ep.key:60} in: {fmt(ep.inputs):30} out: {fmt(ep.outputs)}")
        return 0

    manifest = Store(args.out).manifest()
    synced = set(manifest["models"]) if manifest else set()
    selected, _ = select_models(models, endpoints, tags=_split(args.tag) or None, kind=args.kind)
    if args.tag or args.kind != "all":
        # For a listing, show only what matched — not the dependencies pulled in.
        selected = {n for n in selected if args.kind == "all" or args.kind in models[n].roles}
    print(f"{'MODEL':45} {'KIND':7} {'FIELDS':>6} {'ENDPOINTS':>9}  SYNCED")
    for name in sorted(selected, key=lambda n: models[n].ts_name):
        m = models[name]
        fields = len(m.schema.get("properties", {}))
        eps = len({k for k, _ in m.used_by})
        print(f"{m.ts_name:45} {m.kind:7} {fields:>6} {eps:>9}  {'yes' if name in synced else ''}")
    print(f"\n{len(selected)} model(s). Source: {args.source}")
    return 0


# ---------------------------------------------------------------------------
# check / sync / history
# ---------------------------------------------------------------------------
def cmd_check(args: argparse.Namespace) -> int:
    store = Store(args.out)
    manifest = store.manifest()
    if manifest is None:
        print("No sync yet — run `sync` first.")
        return 1
    version = args.against or manifest["version"]
    old = store.snapshot(version)
    if old is None:
        sys.exit(f"error: snapshot {version} not found in {store.snapshots_dir}")
    report = compare_specs(old, _load(args))
    print(f"Comparing {args.source} against sync {version}:\n")
    print("\n".join(format_report(report, set(manifest["models"]))))
    if report.has_changes:
        print("\nRun `sync` to regenerate the TypeScript file.")
    return 1 if report.has_changes else 0


def cmd_sync(args: argparse.Namespace) -> int:
    store = Store(args.out)
    manifest = store.manifest()
    spec = _load(args)
    models, endpoints = index_spec(spec)

    # A new model selection replaces the saved one; otherwise re-sync the saved one.
    previous = (manifest or {}).get("selection", {})
    if args.all or args.models or args.tag or args.kind:
        models_sel, tags_sel, kind_sel = _split(args.models), _split(args.tag), args.kind or "all"
    else:
        models_sel, tags_sel, kind_sel = previous.get("models", []), previous.get("tags", []), previous.get("kind", "all")
    selection = {
        "models": models_sel,
        "tags": tags_sel,
        "kind": kind_sel,
        "style": args.style or previous.get("style", "interface"),
        "file": args.file or previous.get("file", DEFAULT_FILE),
    }
    selected, unmatched = select_models(
        models, endpoints, patterns=selection["models"] or None, tags=selection["tags"] or None, kind=selection["kind"]
    )
    if unmatched:
        sys.exit(f"error: no model matches: {', '.join(unmatched)} (see `list`)")
    if not selected:
        sys.exit("error: the selection is empty")

    out_file = args.out / selection["file"]
    old = store.latest_snapshot()
    report = compare_specs(old, spec) if old else None
    same_selection = manifest is not None and manifest.get("selection") == selection
    if report and not report.has_changes and same_selection and out_file.exists() and not args.force:
        print(f"Up to date (version {manifest['version']}). Use --force to regenerate anyway.")
        return 0

    if report:
        print(f"Changes since {manifest['version']}:")
        print("\n".join("  " + line for line in format_report(report, set(manifest["models"]))))
        print()

    version, synced_at = new_version()
    info = spec.get("info", {})
    header = [
        "AUTO-GENERATED by tools/api_sync — do not edit by hand; run `api_sync.py sync`.",
        f"Sync version: {version}",
        f"Synced at:    {synced_at}",
        f"Source:       {args.source}",
        f"API:          {info.get('title', '')} {info.get('version', '')}".rstrip(),
    ]
    ts_names = {n: m.ts_name for n, m in models.items()}
    content = render_file([models[n] for n in selected], ts_names, header, selection["style"])

    if args.dry_run:
        print(content if args.print else f"[dry-run] would write {len(selected)} model(s) to {out_file}")
        return 0

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(content, encoding="utf-8")
    new_manifest = {
        "version": version,
        "syncedAt": synced_at,
        "source": args.source,
        "apiVersion": info.get("version"),
        "file": selection["file"],
        "selection": selection,
        "models": sorted(selected),
    }
    store.record_sync(
        spec,
        new_manifest,
        {
            "version": version,
            "syncedAt": synced_at,
            "source": args.source,
            "file": selection["file"],
            "modelCount": len(selected),
            "previousVersion": manifest["version"] if manifest else None,
            "changes": report.summary() if report else "initial sync",
            "addedModels": report.models_added if report else [],
            "removedModels": report.models_removed if report else [],
            "changedModels": sorted(report.models_changed) if report else [],
            "changedEndpoints": sorted(report.endpoints_changed) if report else [],
        },
    )
    print(f"Synced {len(selected)} model(s) -> {out_file}")
    print(f"Version {version}; snapshot saved in {store.snapshots_dir}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    entries = Store(args.out).history()
    if not entries:
        print("No sync history yet.")
        return 0
    for e in entries[-args.limit :][::-1]:
        changes = e["changes"]
        if isinstance(changes, dict):
            changes = ", ".join(f"{k}={v}" for k, v in changes.items() if v) or "no schema changes"
        print(f"{e['version']}  {e['syncedAt']}  {e['modelCount']:>3} models  {changes}")
        for label, key in (("added", "addedModels"), ("removed", "removedModels"), ("changed", "changedModels")):
            if e.get(key):
                print(f"    {label + ' models:':16} {', '.join(e[key])}")
        if e.get("changedEndpoints"):
            print(f"    {'endpoints:':16} {', '.join(e['changedEndpoints'])}")
    return 0


# ---------------------------------------------------------------------------
# mock
# ---------------------------------------------------------------------------
def cmd_mock(args: argparse.Namespace) -> int:
    spec = _load(args)
    models, endpoints = index_spec(spec)
    hints: dict[str, str] = {}
    hints_path = Path(args.hints) if args.hints else SETTINGS.hints_file
    if args.hints or hints_path.exists():
        hints = json.loads(hints_path.read_text(encoding="utf-8"))
        print(f"Using hints: {hints_path}", file=sys.stderr)
    overrides: dict[str, Any] = {}
    for item in args.set or []:
        field, sep, raw = item.partition("=")
        if not sep:
            sys.exit(f"error: --set expects FIELD=VALUE, got '{item}'")
        try:
            overrides[field.strip()] = json.loads(raw)  # numbers, true/false, lists, objects
        except json.JSONDecodeError:
            overrides[field.strip()] = raw  # plain string

    targets = []
    for name in args.model:
        model = find_model(models, name)
        if model is None:
            sys.exit(f"error: model '{name}' not found (see `list`)")
        targets.append(model)

    gen = MockGenerator(
        models,
        {ep.key: ep.summary for ep in endpoints},
        seed=args.seed,
        locale=args.locale,
        llm_fields=_split(args.llm_fields),
        hints=hints,
        overrides=overrides,
        auto_long_text=not args.no_auto_long_text,
    )
    results = {m.ts_name: gen.generate(m, args.count) for m in targets}

    if gen.slots:
        if args.llm:
            try:
                config = LLMConfig.resolve(SETTINGS, args.llm_provider, args.llm_model)
            except LLMError as exc:
                sys.exit(f"error: {exc}")
            print(f"Filling {len(gen.slots)} long-text field(s) with {config.provider}/{config.model} ...", file=sys.stderr)
            filled = gen.fill_with_llm(config, args.lang, log=lambda m: print(m, file=sys.stderr))
            print(f"LLM filled {filled}/{len(gen.slots)} field(s).", file=sys.stderr)
        else:
            fields = sorted({f"{models[s.owner].ts_name}.{s.field}" for s in gen.slots if s.owner in models})
            print(f"note: {len(gen.slots)} long-text value(s) use placeholders ({', '.join(fields)}); add --llm for meaningful text.", file=sys.stderr)

    if args.stdout:
        data = results[targets[0].ts_name] if len(targets) == 1 else results
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    args.mock_out.mkdir(parents=True, exist_ok=True)
    for ts_name, records in results.items():
        path = args.mock_out / f"{ts_name}.json"
        path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {len(records)} record(s) -> {path}")
    return 0


# ---------------------------------------------------------------------------
# hints
# ---------------------------------------------------------------------------
def cmd_hints(args: argparse.Namespace) -> int:
    spec = _load(args)
    models, endpoints = index_spec(spec)
    if args.model:
        selected = []
        for name in args.model:
            model = find_model(models, name)
            if model is None:
                sys.exit(f"error: model '{name}' not found (see `list`)")
            selected.append(model)
    else:
        selected = list(models.values())

    path: Path = args.hints_file
    existing: dict[str, str] = {}
    if path.exists() and not args.stdout:
        existing = json.loads(path.read_text(encoding="utf-8"))

    llm = None
    if args.llm:
        try:
            llm = LLMConfig.resolve(SETTINGS, args.llm_provider, args.llm_model)
        except LLMError as exc:
            sys.exit(f"error: {exc}")
        print(f"Drafting hints with {llm.provider}/{llm.model} ...", file=sys.stderr)

    gen = MockGenerator(models, {}, llm_fields=_split(args.llm_fields), auto_long_text=not args.no_auto_long_text)
    try:
        hints, changed = build_hints(
            gen,
            models,
            selected,
            {ep.key: ep.summary for ep in endpoints},
            existing,
            force=args.force,
            llm=llm,
            language=args.lang,
        )
    except LLMError as exc:
        sys.exit(f"error: LLM failed, nothing written: {exc}")

    content = json.dumps(hints, indent=2, ensure_ascii=False) + "\n"
    if args.stdout:
        print(content, end="")
        return 0
    if not changed:
        print(f"No new long-text field; {path} is up to date. Use --force to rewrite the drafts.")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"Wrote {len(changed)} hint(s) -> {path}")
    for key in changed:
        print(f"  {key}: {hints[key]}")
    print("Review and edit the file; `mock --llm` uses it automatically.")
    return 0


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------
def _mask(secret: str) -> str:
    if not secret:
        return "(not set)"
    return f"{secret[:4]}...{secret[-4:]}" if len(secret) > 12 else "***"


def cmd_config(args: argparse.Namespace) -> int:
    s = SETTINGS
    print(f"Env file:      {s.env_file} ({'found' if s.env_file_found else 'MISSING'})")
    print(f"Source:        {args.source}")
    print(f"Sync out:      {args.out}")
    print(f"Mock out:      {s.mock_out}")
    print(f"Hints file:    {s.hints_file} ({'found' if s.hints_file.exists() else 'not created yet'})")
    try:
        llm = LLMConfig.resolve(s)
        print(f"LLM:           {llm.provider} / {llm.model} @ {llm.base_url}")
    except LLMError as exc:
        print(f"LLM:           not usable - {exc}")
    print(f"LLM API key:   {_mask(s.llm_api_key)}")

    if args.source.startswith(("http://", "https://")):
        try:
            spec = load_spec(args.source)
        except (OSError, json.JSONDecodeError) as exc:  # URLError is an OSError
            print(f"\nBackend:       DOWN ({getattr(exc, 'reason', exc)})\n{BACKEND_START_HINT}")
            return 1
        models, endpoints = index_spec(spec)
        print(f"\nBackend:       UP - {len(models)} model(s), {len(endpoints)} endpoint(s)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--source", default=SETTINGS.source, help="OpenAPI URL, JSON file, or 'app' (import backend). Default: %(default)s")
    common.add_argument("--out", type=Path, default=SETTINGS.out, help="Output dir for TypeScript + sync state. Default: %(default)s")

    parser = argparse.ArgumentParser(prog="api_sync", description="Sync backend API schemas to TypeScript; generate sample data.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("config", parents=[common], help="Show the active settings and check the backend is running")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("list", parents=[common], help="List models (or endpoints, or one model's fields)")
    p.add_argument("--kind", choices=["input", "output", "all"], default="all")
    p.add_argument("--tag", nargs="+", help="Only models used by endpoints with these tags")
    p.add_argument("--endpoints", action="store_true", help="List endpoints with their input/output models")
    p.add_argument("--fields", metavar="MODEL", help="Show the fields of one model")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("check", parents=[common], help="Show schema changes since the last sync (exit 1 if any)")
    p.add_argument("--against", metavar="VERSION", help="Compare with this sync version instead of the latest")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("sync", parents=[common], help="Generate TypeScript and record a new sync version")
    p.add_argument("--models", nargs="+", help="Model names or globs (e.g. '*Request'); dependencies are added")
    p.add_argument("--tag", nargs="+", help="Only models used by endpoints with these tags")
    p.add_argument("--kind", choices=["input", "output", "all"], help="Only input or output models")
    p.add_argument("--all", action="store_true", help="Reset the saved selection: every model")
    p.add_argument("--style", choices=["interface", "type"], help="interface (default) or type aliases")
    p.add_argument("--file", help=f"Output file name inside --out (default {DEFAULT_FILE})")
    p.add_argument("--force", action="store_true", help="Regenerate even if nothing changed")
    p.add_argument("--dry-run", action="store_true", help="Do not write anything")
    p.add_argument("--print", action="store_true", help="With --dry-run: print the TypeScript")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("history", parents=[common], help="Show previous syncs")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("mock", parents=[common], help="Generate JSON sample records for models")
    p.add_argument("model", nargs="+", help="Model name(s)")
    p.add_argument("-n", "--count", type=int, default=5, help="Records per model (default %(default)s)")
    p.add_argument("--mock-out", type=Path, default=SETTINGS.mock_out, help="Output dir. Default: %(default)s")
    p.add_argument("--stdout", action="store_true", help="Print JSON instead of writing files")
    p.add_argument("--seed", type=int, help="Seed for reproducible data")
    p.add_argument("--locale", default="vi_VN", help="Faker locale if Faker is installed (default %(default)s)")
    p.add_argument("--llm", action="store_true", help="Fill long-text fields with an LLM")
    p.add_argument("--llm-provider", help="openai | anthropic | gemini | grok | deepseek (default: LLM_PROVIDER in .env)")
    p.add_argument("--llm-model", help="Override the model name (default: LLM_MODEL in .env)")
    p.add_argument("--llm-fields", nargs="+", help="Extra fields to treat as long text: 'field' or 'Model.field'")
    p.add_argument("--no-auto-long-text", action="store_true", help="Only use --llm-fields, skip auto-detection")
    p.add_argument("--set", action="append", metavar="FIELD=VALUE", help="Fix a value: 'field=value' or 'Model.field=value'; VALUE may be JSON. Repeatable")
    p.add_argument("--hints", help="JSON file: {'Model': 'purpose', 'Model.field': 'meaning', 'field': 'meaning'} (default: API_SYNC_HINTS_FILE if it exists)")
    p.add_argument("--lang", default="vi", help="Language of LLM text: vi | en | any name (default %(default)s)")
    p.set_defaults(func=cmd_mock)

    p = sub.add_parser("hints", parents=[common], help="Generate the hints file (Model / Model.field meanings) for `mock --llm`")
    p.add_argument("model", nargs="*", help="Model name(s); default: every model with a long-text field")
    p.add_argument("--hints-file", type=Path, default=SETTINGS.hints_file, help="Output file. Default: %(default)s")
    p.add_argument("--force", action="store_true", help="Replace existing values with fresh drafts")
    p.add_argument("--stdout", action="store_true", help="Print the JSON instead of writing the file")
    p.add_argument("--llm", action="store_true", help="Let the LLM write the drafts (uses the .env LLM settings)")
    p.add_argument("--llm-provider", help="Override LLM_PROVIDER")
    p.add_argument("--llm-model", help="Override LLM_MODEL")
    p.add_argument("--llm-fields", nargs="+", help="Extra fields to treat as long text: 'field' or 'Model.field'")
    p.add_argument("--no-auto-long-text", action="store_true", help="Only use --llm-fields, skip auto-detection")
    p.add_argument("--lang", default="en", help="Language of the hints (default %(default)s)")
    p.set_defaults(func=cmd_hints)
    return parser


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    if not SETTINGS.env_file_found:
        print(
            f"note: {SETTINGS.env_file} not found; using defaults. Copy {ENV_EXAMPLE_FILE.name} to .env to configure the tool.",
            file=sys.stderr,
        )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
