"""ev_mock_data — generate EV data, import it into mock-ev-system and query it over the API.

Run ``python tools/ev_mock_data/ev_mock_data.py --help``; see README.md for usage.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import MockApiError, MockClient  # noqa: E402
from generator import DataGenerator, Options, Reference  # noqa: E402

TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parents[1]
ENV_FILE = TOOL_DIR / ".env"
START_HINT = (
    "Start mock-ev-system first:\n"
    "  cd backend && uv run --package mock-ev-system uvicorn mock_ev_system.main:app --reload --port 8100"
)


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------
def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _setting(name: str, default: str, env_file: dict[str, str]) -> str:
    """Priority: shell environment > .env file > default (CLI flags are applied later)."""
    return os.environ.get(name) or env_file.get(name) or default


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / str(value).lstrip("/\\")


ENV = _load_env_file(ENV_FILE)
DEFAULT_URL = _setting("EV_MOCK_URL", "http://localhost:8100", ENV)
DEFAULT_TOKEN = _setting("EV_MOCK_ADMIN_TOKEN", "", ENV)
DEFAULT_DATA_DIR = _setting("EV_MOCK_DATA_DIR", "tools/ev_mock_data/data", ENV)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _client(args: argparse.Namespace) -> MockClient:
    return MockClient(args.url, args.token)


def _call(fn: Any, *a: Any, **kw: Any) -> Any:
    """Run an API call and turn transport / HTTP errors into a clean exit."""
    try:
        return fn(*a, **kw)
    except MockApiError as exc:
        if exc.status == 401:
            sys.exit("error: 401 — set EV_MOCK_ADMIN_TOKEN (or --token) to the mock's MOCK_ADMIN_TOKEN.")
        if exc.status == 404 and "Not Found" == exc.detail:
            sys.exit("error: endpoint not found — is this mock version missing the /admin API?")
        sys.exit(f"error: HTTP {exc.status}: {json.dumps(exc.detail, ensure_ascii=False)}")
    except urllib.error.URLError as exc:
        sys.exit(f"error: cannot reach mock-ev-system ({getattr(exc, 'reason', exc)}).\n{START_HINT}")


def _parse_pairs(items: list[str] | None, flag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep:
            sys.exit(f"error: {flag} expects KEY=VALUE, got '{item}'")
        result[key.strip()] = value.strip()
    return result


def _counts(data: dict[str, list[dict]]) -> str:
    return ", ".join(f"{k}={len(v)}" for k, v in data.items() if v) or "nothing"


def _print_table(rows: list[dict], fields: list[str] | None, max_width: int) -> None:
    if not rows:
        print("(no records)")
        return
    cols = fields or list(rows[0].keys())

    def cell(v: Any) -> str:
        text = "" if v is None else str(v)
        return text if len(text) <= max_width else text[: max_width - 1] + "…"

    table = [[cell(r.get(c)) for c in cols] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in table)) for i, c in enumerate(cols)]
    print("  ".join(c.upper().ljust(w) for c, w in zip(cols, widths)))
    print("  ".join("-" * w for w in widths))
    for row in table:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)))


def _write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _default_file(prefix: str) -> Path:
    from datetime import datetime

    return _resolve_path(DEFAULT_DATA_DIR) / f"{prefix}-{datetime.now():%Y%m%d-%H%M%S}.json"


def _read_dataset(path: Path) -> dict[str, list[dict]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"error: cannot read {path}: {exc}")
    data = raw.get("data", raw) if isinstance(raw, dict) else None
    if not isinstance(data, dict) or not all(isinstance(v, list) for v in data.values()):
        sys.exit(f"error: {path} must be {{entity: [records]}} or {{'data': {{entity: [records]}}}}")
    return data


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_config(args: argparse.Namespace) -> int:
    print(f"Env file:     {ENV_FILE} ({'found' if ENV_FILE.exists() else 'not found, using defaults'})")
    print(f"Mock URL:     {args.url}")
    print(f"Admin token:  {'set' if args.token else '(not set)'}")
    print(f"Data dir:     {_resolve_path(DEFAULT_DATA_DIR)}")
    client = _client(args)
    try:
        client.get("/health")
    except (urllib.error.URLError, MockApiError) as exc:
        print(f"\nMock:         DOWN ({getattr(exc, 'reason', exc)})\n{START_HINT}")
        return 1
    print("\nMock:         UP")
    for e in _call(client.entities):
        print(f"  {e['entity']:24} {e['count']:>6} rows   pk={e['primary_key']}")
    return 0


def cmd_entities(args: argparse.Namespace) -> int:
    for e in _call(_client(args).entities):
        print(f"{e['entity']}  ({e['count']} rows, pk={e['primary_key']})")
        print(f"    {', '.join(e['fields'])}")
    return 0


def _generate(args: argparse.Namespace, client: MockClient) -> dict[str, list[dict]]:
    vmin, _, vmax = args.vehicles.partition("-")
    try:
        opts = Options(
            owners=args.owners,
            vehicles_min=int(vmin),
            vehicles_max=int(vmax or vmin),
            claim_rate=args.claim_rate,
            model_ids=[m.strip() for m in ",".join(args.models).split(",")] if args.models else None,
            email_domain=args.email_domain,
            today=date.fromisoformat(args.today) if args.today else date.today(),
        )
        ref = _call(Reference.load, client)
        return DataGenerator(ref, opts, seed=args.seed).generate()
    except ValueError as exc:
        sys.exit(f"error: {exc}")


def cmd_generate(args: argparse.Namespace) -> int:
    data = _generate(args, _client(args))
    if args.stdout:
        print(json.dumps({"data": data}, indent=2, ensure_ascii=False))
        return 0
    out = Path(args.out) if args.out else _default_file("generated")
    _write_json({"data": data}, out)
    print(f"Generated {_counts(data)}\n-> {out}")
    print(f"Import it with: ev_mock_data.py import {out}")
    return 0


def _do_import(client: MockClient, data: dict[str, list[dict]], mode: str) -> None:
    res = _call(client.import_data, data, mode)
    print(f"Imported ({res['mode']}):")
    for entity, c in res["imported"].items():
        print(f"  {entity:24} created={c['created']:<5} updated={c['updated']}")


def cmd_import(args: argparse.Namespace) -> int:
    data = _read_dataset(Path(args.file))
    print(f"File {args.file}: {_counts(data)}")
    _do_import(_client(args), data, args.mode)
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    client = _client(args)
    data = _generate(args, client)
    print(f"Generated {_counts(data)}")
    if not args.no_save:
        out = Path(args.out) if args.out else _default_file("seed")
        _write_json({"data": data}, out)
        print(f"Saved -> {out}")
    _do_import(client, data, "insert")
    print("Tip: the mock keeps data in memory — re-run `import <file>` after a mock restart.")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    filters = _parse_pairs(args.where, "--where")
    res = _call(_client(args).get, f"/admin/data/{args.entity}", {**filters, "limit": args.limit, "offset": args.offset})
    if args.json:
        print(json.dumps(res["items"], indent=2, ensure_ascii=False))
    else:
        fields = [f.strip() for f in args.fields.split(",")] if args.fields else None
        _print_table(res["items"], fields, args.max_width)
        shown = len(res["items"])
        print(f"\n{shown} of {res['total']} {args.entity} (offset {res['offset']})")
    return 0


# ---------------------------------------------------------------------------
# find — everything related to one identifier (email, VIN, plate, CCCD, ...)
# ---------------------------------------------------------------------------
# Related tables in output order. Owners / vehicles are resolved from the
# identifier; the other tables are loaded from the matched vehicles / models.
FIND_TABLES = [
    "owners", "vehicles", "vehicle_usage", "warranties", "warranty_claims", "service_history",
    "vehicle_models", "warranty_policies", "maintenance_schedules", "maintenance_items", "service_centers",
]
FIND_DEFAULT_TABLES = ["owners", "vehicles"]
# Short / singular / SQL table names accepted in --select.
FIND_ALIASES = {
    "owner": "owners", "vehicle": "vehicles", "usage": "vehicle_usage", "warranty": "warranties",
    "claims": "warranty_claims", "warranty_claim": "warranty_claims", "history": "service_history",
    "models": "vehicle_models", "vehicle_model": "vehicle_models", "model": "vehicle_models",
    "policies": "warranty_policies", "warranty_policy": "warranty_policies",
    "schedules": "maintenance_schedules", "maintenance_schedule": "maintenance_schedules",
    "items": "maintenance_items", "maintenance_item": "maintenance_items",
    "centers": "service_centers", "service_center": "service_centers",
}


def _norm_plate(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _norm_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    return "0" + digits[2:] if digits.startswith("84") else digits


def _parse_select(items: list[str] | None) -> dict[str, list[str] | None]:
    """``["owners.email,vehicles", "warranties.status"]`` → ``{"owners": ["email"], "vehicles": None, ...}``.

    ``None`` means every column of that table.
    """
    result: dict[str, list[str] | None] = {}
    for item in ",".join(items or []).split(","):
        item = item.strip()
        if not item:
            continue
        table, _, column = item.partition(".")
        table = FIND_ALIASES.get(table, table)
        if table not in FIND_TABLES:
            sys.exit(f"error: unknown table '{table}' in --select. Known: {', '.join(FIND_TABLES)}")
        if not column or column == "*":
            result[table] = None
        elif table not in result:
            result[table] = [column]
        elif result[table] is not None:
            result[table].append(column)
    return result


def _find_related(client: MockClient, args: argparse.Namespace, tables: set[str]) -> dict[str, list[dict]]:
    def get(entity: str, **filters: str) -> list[dict]:
        return _call(client.all_records, entity, filters or None)

    # 1) Resolve owners / vehicles from the identifier.
    if args.vehicle_id or args.vin or args.plate:
        if args.vehicle_id:
            vehicles = get("vehicles", vehicle_id=args.vehicle_id)
        elif args.vin:
            vehicles = get("vehicles", vin=args.vin.strip().upper())
        else:
            plate = _norm_plate(args.plate)
            vehicles = [v for v in get("vehicles") if _norm_plate(v["license_plate"]) == plate]
        owner_ids = {v["current_owner_id"] for v in vehicles}
        owners = [o for o in get("owners") if o["owner_id"] in owner_ids]
    else:
        if args.owner_id:
            owners = get("owners", owner_id=args.owner_id)
        elif args.email:
            email = args.email.strip().lower()
            owners = [o for o in get("owners") if o["email"].lower() == email]
        elif args.national_id:
            owners = get("owners", national_id="".join(ch for ch in args.national_id if ch.isdigit()))
        else:
            phone = _norm_phone(args.phone)
            owners = [o for o in get("owners") if _norm_phone(o["phone"]) == phone]
        owner_ids = {o["owner_id"] for o in owners}
        vehicles = [v for v in get("vehicles") if v["current_owner_id"] in owner_ids]

    out: dict[str, list[dict]] = {"owners": owners, "vehicles": vehicles}
    vehicle_ids = [v["vehicle_id"] for v in vehicles]
    model_ids = sorted({v["model_id"] for v in vehicles})

    def per_vehicle(entity: str) -> list[dict]:
        return [r for vid in vehicle_ids for r in get(entity, vehicle_id=vid)]

    def per_model(entity: str) -> list[dict]:
        return [r for mid in model_ids for r in get(entity, model_id=mid)]

    # 2) Load only the related tables that were asked for (plus what they depend on).
    for table in ("vehicle_usage", "warranties", "warranty_claims", "service_history"):
        if table in tables or (table == "service_history" and "service_centers" in tables):
            out[table] = per_vehicle(table)
    for table in ("vehicle_models", "warranty_policies"):
        if table in tables:
            out[table] = per_model(table)
    if tables & {"maintenance_schedules", "maintenance_items"}:
        out["maintenance_schedules"] = per_model("maintenance_schedules")
    if "maintenance_items" in tables:
        out["maintenance_items"] = [
            r for s in out["maintenance_schedules"] for r in get("maintenance_items", schedule_id=s["schedule_id"])
        ]
    if "service_centers" in tables:
        center_ids = sorted({h["service_center_id"] for h in out["service_history"]})
        out["service_centers"] = [r for cid in center_ids for r in get("service_centers", center_id=cid)]
    return {t: out[t] for t in FIND_TABLES if t in tables}


def cmd_find(args: argparse.Namespace) -> int:
    if args.all:
        selected: dict[str, list[str] | None] = {t: None for t in FIND_TABLES}
    else:
        selected = _parse_select(args.select) or {t: None for t in FIND_DEFAULT_TABLES}
    data = _find_related(_client(args), args, set(selected) | {"owners", "vehicles"})
    found = bool(data["owners"] or data["vehicles"])
    data = {t: data[t] for t in FIND_TABLES if t in selected}

    # Keep only the requested columns.
    for table, columns in selected.items():
        if columns and data[table]:
            unknown = [c for c in columns if c not in data[table][0]]
            if unknown:
                sys.exit(f"error: unknown column(s) {', '.join(unknown)} in {table}. Known: {', '.join(data[table][0])}")
            data[table] = [{c: row.get(c) for c in columns} for row in data[table]]

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif not found:
        print("No owner / vehicle matches this identifier.")
    else:
        for table, rows in data.items():
            print(f"\n== {table} ({len(rows)})")
            _print_table(rows, None, args.max_width)
    return 0 if found else 1


def _api_path(path: str) -> str:
    # Git Bash rewrites a leading "/vehicles" into "C:/Program Files/Git/vehicles".
    if ":" in path.split("/", 1)[0]:
        sys.exit(f"error: '{path}' looks like a path rewritten by Git Bash — write it without the leading slash, e.g. vehicles/VEH-001")
    return path


def cmd_get(args: argparse.Namespace) -> int:
    res = _call(_client(args).get, _api_path(args.path), _parse_pairs(args.param, "--param"))
    if args.table and isinstance(res, list):
        _print_table(res, None, 40)
    else:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def cmd_post(args: argparse.Namespace) -> int:
    body = json.loads(Path(args.body_file).read_text(encoding="utf-8")) if args.body_file else json.loads(args.body or "{}")
    print(json.dumps(_call(_client(args).post, _api_path(args.path), body), indent=2, ensure_ascii=False))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    client = _client(args)
    names = [e["entity"] for e in _call(client.entities)]
    if args.entities:
        wanted = [n.strip() for n in ",".join(args.entities).split(",")]
        unknown = set(wanted) - set(names)
        if unknown:
            sys.exit(f"error: unknown entity: {', '.join(sorted(unknown))}")
        names = [n for n in names if n in wanted]
    data = {n: _call(client.all_records, n) for n in names}
    out = Path(args.out) if args.out else _default_file("export")
    _write_json({"data": data}, out)
    print(f"Exported {_counts(data)}\n-> {out}")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    if args.file:
        raw = json.loads(Path(args.file).read_text(encoding="utf-8"))
    elif args.json:
        raw = json.loads(args.json)
    else:
        raw = {}
        for key, value in _parse_pairs(args.set, "--set").items():
            try:
                raw[key] = json.loads(value)  # numbers, true/false, null
            except json.JSONDecodeError:
                raw[key] = value
        if not raw:
            sys.exit("error: give the record(s) with --set FIELD=VALUE, --json or --file")
    records = raw if isinstance(raw, list) else [raw]
    path = f"/admin/data/{args.entity}" + ("?upsert=true" if args.upsert else "")
    res = _call(_client(args).post, path, records)
    print(f"{args.entity}: created={res['created']} updated={res['updated']}")
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    client = _client(args)
    if args.format == "json":
        content = json.dumps(_call(client.get, "/admin/dump", {"format": "json"}), indent=2, ensure_ascii=False) + "\n"
    else:
        content = _call(client.get_text, "/admin/dump", {"format": "sql"})
    out = Path(args.out) if args.out else _default_file("dump").with_suffix(f".{args.format}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"Dumped mock database ({args.format}) -> {out}")
    if args.format == "sql":
        print(f"Load it with: sqlite3 ev_mock.db < {out.name}")
    else:
        print(f"Load it with: ev_mock_data.py import {out.name}")
    return 0


ENTITY_DESCRIPTIONS = {
    "vehicle_models": "Mẫu xe (master data)",
    "owners": "Chủ sở hữu xe",
    "service_centers": "Đại lý / xưởng dịch vụ (kèm người quản lý dùng để xác thực)",
    "vehicles": "Xe cụ thể theo VIN",
    "vehicle_usage": "Snapshot ODO / pin hiện tại (1 xe : 1 dòng)",
    "warranty_policies": "Chính sách bảo hành theo mẫu xe + bộ phận",
    "warranties": "Hợp đồng bảo hành của từng xe",
    "warranty_claims": "Yêu cầu bảo hành (approved / rejected / pending)",
    "maintenance_schedules": "Lịch bảo dưỡng chuẩn theo mẫu xe",
    "maintenance_items": "Hạng mục trong một mốc bảo dưỡng",
    "service_history": "Lịch sử bảo dưỡng thực tế",
}


def _pick_samples(rows: list[dict], count: int) -> list[dict]:
    """Spread the picks over the table so both seed and generated rows show up;
    for a table with a status column, cover each status first."""
    picked: list[dict] = []
    if rows and "status" in rows[0]:
        for status in dict.fromkeys(r["status"] for r in rows):
            picked.append(next(r for r in rows if r["status"] == status))
    step = max(len(rows) // count, 1)
    for r in rows[::step]:
        if len(picked) >= count:
            break
        if r not in picked:
            picked.append(r)
    return picked[:count]


def cmd_samples(args: argparse.Namespace) -> int:
    client = _client(args)
    entities = _call(client.entities)

    def cell(v: Any) -> str:
        return "—" if v is None else str(v).replace("|", "\\|").replace("\n", " ")

    lines = [
        "# mock-ev-system — Dữ liệu mẫu",
        "",
        f"{args.count} dòng mẫu mỗi bảng, lấy từ mock-ev-system ({args.url}) lúc "
        f"{date.today().isoformat()}. Khi mock chạy bằng Docker, dữ liệu này đến từ bản dump dùng chung "
        "[`ev-mock-dump.sql`](ev-mock-dump.sql). Xem thêm hoặc truy vấn bằng "
        "[`tools/ev_mock_data`](../../../tools/ev_mock_data/README.md), ví dụ "
        "`python tools/ev_mock_data/ev_mock_data.py query vehicles`.",
        "",
        "> Dữ liệu giả lập, không phải thông tin thật. Tạo lại file: "
        "`python tools/ev_mock_data/ev_mock_data.py samples`.",
        "",
        "## Tổng quan",
        "",
        "| Bảng (entity) | Mô tả | Khoá chính | Số dòng |",
        "|---|---|---|---:|",
    ]
    for e in entities:
        name = e["entity"]
        lines.append(f"| [`{name}`](#{name}) | {ENTITY_DESCRIPTIONS.get(name, '')} | `{e['primary_key']}` | {e['count']} |")
    for e in entities:
        name, cols = e["entity"], e["fields"]
        rows = _pick_samples(_call(client.all_records, name), args.count)
        lines += ["", f"## {name}", "", f"{ENTITY_DESCRIPTIONS.get(name, '')} — {len(rows)}/{e['count']} dòng.", ""]
        lines += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        lines += ["| " + " | ".join(cell(r.get(c)) for c in cols) + " |" for r in rows]
    out = Path(args.out) if args.out else REPO_ROOT / "backend/mock-ev-system/seed-data/SAMPLES.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(entities)} table(s), up to {args.count} row(s) each -> {out}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    _call(_client(args).delete, f"/admin/data/{args.entity}/{args.key}")
    print(f"Deleted {args.entity} {args.key}")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    if not args.yes:
        answer = input(f"Reset ALL data on {args.url} to its startup data (dump or built-in seed)? [y/N] ")
        if answer.strip().lower() != "y":
            print("Cancelled.")
            return 1
    _call(_client(args).post, "/admin/reset")
    print("Mock data reset to its startup data (MOCK_SEED_DUMP if set, else the built-in seed).")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _add_generate_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("-n", "--owners", type=int, default=5, help="Number of owners (default %(default)s)")
    p.add_argument("--vehicles", default="1-2", help="Vehicles per owner: N or MIN-MAX (default %(default)s)")
    p.add_argument("--models", nargs="+", help="Only these vehicle model ids, e.g. MDL-01 MDL-05")
    p.add_argument("--claim-rate", type=float, default=0.3, help="Chance a vehicle has a warranty claim (default %(default)s)")
    p.add_argument("--email-domain", default="example.com", help="Owner email domain (default %(default)s)")
    p.add_argument("--today", help="Reference date YYYY-MM-DD for ages / km / statuses (default: today)")
    p.add_argument("--seed", type=int, help="Random seed for a reproducible data set")
    p.add_argument("--out", help="Output JSON file (default: <data dir>/<command>-<timestamp>.json)")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default=DEFAULT_URL, help="mock-ev-system base URL. Default: %(default)s")
    common.add_argument("--token", default=DEFAULT_TOKEN, help="Admin token (X-Admin-Token); default EV_MOCK_ADMIN_TOKEN")

    parser = argparse.ArgumentParser(prog="ev_mock_data", description="Generate, import and query data on mock-ev-system.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("config", parents=[common], help="Show settings, check the mock is up, count rows")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("entities", parents=[common], help="List entities and their fields")
    p.set_defaults(func=cmd_entities)

    p = sub.add_parser("generate", parents=[common], help="Generate a data set to a JSON file (does not import)")
    _add_generate_options(p)
    p.add_argument("--stdout", action="store_true", help="Print the JSON instead of writing a file")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("import", parents=[common], help="Import a JSON data set into the mock")
    p.add_argument("file", help="JSON file: {entity: [records]} or {'data': {...}}")
    p.add_argument("--mode", choices=["upsert", "insert"], default="upsert", help="upsert (default) replaces existing ids; insert fails on them")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("seed", parents=[common], help="Generate + import in one step (file is saved too)")
    _add_generate_options(p)
    p.add_argument("--no-save", action="store_true", help="Do not keep the generated JSON file")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("query", parents=[common], help="Query records of one entity (admin API)")
    p.add_argument("entity", help="e.g. owners, vehicles, warranties (see `entities`)")
    p.add_argument("-w", "--where", action="append", metavar="FIELD=VALUE", help="Exact-match filter. Repeatable")
    p.add_argument("--fields", help="Columns to show, comma separated")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    p.add_argument("--max-width", type=int, default=40, help="Truncate table cells (default %(default)s)")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser(
        "find", parents=[common],
        help="Find an owner / vehicle by email, VIN, plate, CCCD, phone or id and show related data",
    )
    ident = p.add_mutually_exclusive_group(required=True)
    ident.add_argument("--email", help="Owner email (case-insensitive)")
    ident.add_argument("--vin", help="Vehicle VIN")
    ident.add_argument("--plate", help="License plate; spaces, '-' and '.' are ignored")
    ident.add_argument("--national-id", "--cccd", dest="national_id", help="Owner national id (CCCD)")
    ident.add_argument("--phone", help="Owner phone; 0xxx and +84xxx both match")
    ident.add_argument("--owner-id", help="e.g. OWN-001")
    ident.add_argument("--vehicle-id", help="e.g. VEH-001")
    p.add_argument(
        "-s", "--select", action="append", metavar="TABLE[.COLUMN],...",
        help="Tables / columns to show, e.g. 'owners.full_name,vehicles.vin,warranties'. Repeatable. "
             "Default: owners,vehicles",
    )
    p.add_argument("--all", action="store_true", help="Show every related table with all columns")
    p.add_argument("--json", action="store_true", help="Print JSON {table: [rows]} instead of tables")
    p.add_argument("--max-width", type=int, default=40, help="Truncate table cells (default %(default)s)")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("get", parents=[common], help="GET any mock endpoint, e.g. /vehicles/VEH-001/next-maintenance")
    p.add_argument("path")
    p.add_argument("-p", "--param", action="append", metavar="KEY=VALUE", help="Query parameter. Repeatable")
    p.add_argument("--table", action="store_true", help="Show a list response as a table")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("post", parents=[common], help="POST JSON to any mock endpoint, e.g. /vehicles/verify-ownership")
    p.add_argument("path")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--body", help="JSON body as a string")
    group.add_argument("--body-file", help="JSON body from a file")
    p.set_defaults(func=cmd_post)

    p = sub.add_parser("export", parents=[common], help="Dump mock data to a JSON file (re-importable)")
    p.add_argument("--entities", nargs="+", help="Only these entities (default: all)")
    p.add_argument("--out", help="Output file (default: <data dir>/export-<timestamp>.json)")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("create", parents=[common], help="Create record(s) in one table")
    p.add_argument("entity", help="e.g. owners, vehicles, service_centers (see `entities`)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--set", action="append", metavar="FIELD=VALUE", help="One record, field by field. Repeatable")
    group.add_argument("--json", help="A record or a list of records as JSON")
    group.add_argument("--file", help="JSON file with a record or a list of records")
    p.add_argument("--upsert", action="store_true", help="Replace records whose primary key exists")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("dump", parents=[common], help="Dump the whole mock database to a file (sql or json)")
    p.add_argument("--format", choices=["sql", "json"], default="sql", help="sql = SQLite script (default); json = import format")
    p.add_argument("--out", help="Output file (default: <data dir>/dump-<timestamp>.<format>)")
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("samples", parents=[common], help="Write a Markdown file with sample rows of every table")
    p.add_argument("-n", "--count", type=int, default=3, help="Rows per table (default %(default)s)")
    p.add_argument("--out", help="Output file (default: backend/mock-ev-system/seed-data/SAMPLES.md)")
    p.set_defaults(func=cmd_samples)

    p = sub.add_parser("delete", parents=[common], help="Delete one record by primary key")
    p.add_argument("entity")
    p.add_argument("key")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("reset", parents=[common], help="Drop all data and reload the startup data (dump or built-in seed)")
    p.add_argument("-y", "--yes", action="store_true", help="Do not ask for confirmation")
    p.set_defaults(func=cmd_reset)
    return parser


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
