"""workshop_crawl — crawl real car workshops in Vietnam (Amazon Location or Google Places) into mock-ev-system.

Run ``python tools/workshop_crawl/workshop_crawl.py --help``; see README.md for usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aws_places import AwsPlacesClient  # noqa: E402
from google_places import GooglePlacesClient  # noqa: E402
from places import PlacesError, SearchClient  # noqa: E402
from provinces import (  # noqa: E402
    PROVINCE_AREAS,
    PROVINCE_BBOX,
    PROVINCES,
    fold,
    normalize_province,
    province_in_address,
)

TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parents[1]
ENV_FILE = TOOL_DIR / ".env"

# (query template, brand) — {p} is the province. Brand queries keep places whose name contains
# the brand, plus any place categorized as car repair / dealer (providers often list a brand's
# showrooms without the brand in the name); generic ones (brand None) keep only the latter.
QUERY_PLAN: list[tuple[str, str | None]] = [
    ("xưởng dịch vụ VinFast {p}", "vinfast"),
    ("đại lý ô tô VinFast {p}", "vinfast"),
    ("gara sửa chữa ô tô {p}", None),
    ("trung tâm bảo dưỡng ô tô {p}", None),
    ("sửa chữa ô tô điện {p}", None),
]
# Extra generic queries per district ({a}) with ``--by-area``, for provinces in PROVINCE_AREAS.
AREA_QUERY_PLAN: list[tuple[str, str | None]] = [
    ("gara ô tô {a} {p}", None),
    ("sửa chữa bảo dưỡng ô tô {a} {p}", None),
]

SOURCES = ("aws", "google")
# center_id prefix per source, so the same shop crawled from two providers never collides.
CENTER_PREFIX = {"aws": "AL", "google": "GM"}


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
DEFAULT_SOURCE = _setting("WORKSHOP_CRAWL_SOURCE", "aws", ENV)
DEFAULT_KEYS = {
    "aws": _setting("AWS_LOCATION_API_KEY", "", ENV),
    "google": _setting("GOOGLE_MAPS_API_KEY", "", ENV),
}
DEFAULT_AWS_REGION = _setting("AWS_LOCATION_REGION", "ap-southeast-1", ENV)
DEFAULT_URL = _setting("EV_MOCK_URL", "http://localhost:8100", ENV)
DEFAULT_TOKEN = _setting("EV_MOCK_ADMIN_TOKEN", "", ENV)
DEFAULT_OUT = _setting("WORKSHOP_CRAWL_OUT", "tools/workshop_crawl/data/workshops.json", ENV)


# ---------------------------------------------------------------------------
# normalized place (see places.py) → service center record
# ---------------------------------------------------------------------------
def _is_vietnam(place: dict[str, Any]) -> bool:
    if place.get("country"):
        return place["country"] == "VN"
    address = fold(place.get("address"))
    return "viet nam" in address or "vietnam" in address


def resolve_region(place: dict[str, Any], searched_province: str) -> str:
    """Provider's province → current province; else scan the address; else the searched province."""
    return (
        normalize_province(place.get("admin_area"))
        or province_in_address(place.get("address"))
        or searched_province
    )


def _digest(place_id: str) -> str:
    return hashlib.sha1(place_id.encode("utf-8"), usedforsecurity=False).hexdigest()


def to_record(place: dict[str, Any], searched_province: str, query: str) -> dict[str, Any]:
    """Map a normalized place to a mock-ev-system service_center row (+ crawl metadata)."""
    place_id = place["id"]
    digest = _digest(place_id)
    center_id = f"{CENTER_PREFIX[place['source']]}-{digest[:10].upper()}"
    record: dict[str, Any] = {
        "center_id": center_id,
        "name": place["name"][:150],
        "region": resolve_region(place, searched_province),
        "type": "dealer" if place["dealer"] else "service_only",
        "address": place.get("address"),
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "place_id": place_id,
        # Synthetic manager identity: the mock requires a unique one per center.
        "manager_email": f"manager.{center_id.lower()}@workshop.example.com",
        "manager_national_id": f"{int(digest, 16) % 10**12:012d}",
        # Crawl metadata (not imported).
        "source": place["source"],
        "maps_uri": place.get("maps_uri"),
        "categories": place.get("categories") or [],
        "searched_province": searched_province,
        "query": query,
    }
    for key in ("phone", "rating", "rating_count"):
        if key in place:
            record[key] = place[key]
    return record


def keep_place(place: dict[str, Any], brand: str | None) -> bool:
    if not place.get("id") or place.get("latitude") is None or place.get("longitude") is None:
        return False
    if place.get("closed") or not place.get("name"):
        return False
    if not _is_vietnam(place):
        return False
    if brand and brand in fold(place["name"]):
        return True
    return bool(place.get("automotive"))


def _is_brand(record: dict[str, Any]) -> bool:
    return "vinfast" in fold(record["name"])


def district_of(record: dict[str, Any]) -> str:
    """District part of a "…, <district>, <province>, Việt Nam" address ("" if it has no such part)."""
    parts = [p.strip() for p in (record.get("address") or "").split(",")]
    return fold(parts[-3]) if len(parts) >= 3 else ""


def _interleave_districts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Round-robin over districts (first-seen order), so the first picks are not all in one district."""
    by_district: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        by_district[district_of(rec)].append(rec)
    groups = list(by_district.values())
    return [g[i] for i in range(max(map(len, groups), default=0)) for g in groups if i < len(g)]


def select_balanced(candidates: list[dict[str, Any]], target: int, provinces: list[str]) -> list[dict[str, Any]]:
    """Pick ``target`` records spread over provinces: round-robin, one per province per round.

    Within a province, brand (VinFast) centers come first, then the rest round-robin over districts.
    A province that runs out simply drops out of later rounds, so its share goes to the others.
    """
    by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in candidates:
        by_region[rec["region"]].append(rec)
    for region, recs in by_region.items():
        brand = [r for r in recs if _is_brand(r)]
        by_region[region] = _interleave_districts(brand) + _interleave_districts([r for r in recs if not _is_brand(r)])
    order = [p for p in provinces if p in by_region] + sorted(r for r in by_region if r not in provinces)

    picked: list[dict[str, Any]] = []
    depth = 0
    while len(picked) < target:
        progressed = False
        for region in order:
            recs = by_region[region]
            if depth < len(recs):
                picked.append(recs[depth])
                progressed = True
                if len(picked) == target:
                    break
        if not progressed:
            break
        depth += 1
    return picked


def province_queries(province: str, by_area: bool) -> list[tuple[str, str | None]]:
    """(query, brand) for one province: the province-wide plan, then per-district queries if asked."""
    queries = [(template.format(p=province), brand) for template, brand in QUERY_PLAN]
    if by_area:
        for area in PROVINCE_AREAS.get(province, []):
            queries += [(template.format(a=area, p=province), brand) for template, brand in AREA_QUERY_PLAN]
    return queries


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def _provinces(args: argparse.Namespace) -> list[str]:
    if not args.provinces:
        return PROVINCES
    chosen = []
    for raw in args.provinces.split(","):
        name = normalize_province(raw)
        if not name:
            sys.exit(f"Unknown province: {raw!r}")
        chosen.append(name)
    return chosen


def cmd_plan(args: argparse.Namespace) -> int:
    provinces = _provinces(args)
    quota = math.ceil(args.target / len(provinces))
    # Amazon returns all results (up to 100) in one request; Google needs one request per 20.
    per_query = 1 if args.source == "aws" else args.pages
    queries = sum(len(province_queries(p, args.by_area)) for p in provinces)
    calls = queries * per_query
    print(f"Source: {args.source} | results/query: up to {args.pages * 20}")
    print(f"Provinces: {len(provinces)} | target {args.target} → ~{quota}/province (stop at {args.stop_at}× quota)")
    print(f"Queries: {queries} | requests/query: {per_query}")
    print(f"Worst case: {calls} search requests (usually far fewer — early stop + cache)")
    print("Example queries:")
    for query, brand in province_queries(provinces[0], args.by_area)[: len(QUERY_PLAN) + len(AREA_QUERY_PLAN)]:
        extra = f" [name contains '{brand}' or car repair / dealer]" if brand else " [car repair / dealer only]"
        print(f"  {query}{extra}")
    return 0


def make_client(args: argparse.Namespace, cache_dir: Path) -> SearchClient:
    key = args.key or DEFAULT_KEYS[args.source]
    if args.source == "aws":
        if not key:
            sys.exit("Missing AWS_LOCATION_API_KEY (set it in tools/workshop_crawl/.env or pass --key).")
        return AwsPlacesClient(
            key,
            cache_dir / "aws",
            region=args.aws_region,
            intended_use=args.aws_intended_use,
            with_contact=args.with_contact,
        )
    if not key:
        sys.exit("Missing GOOGLE_MAPS_API_KEY (set it in tools/workshop_crawl/.env or pass --key).")
    return GooglePlacesClient(key, cache_dir / "google", with_contact=args.with_contact)


def cmd_crawl(args: argparse.Namespace) -> int:
    provinces = _provinces(args)
    out = _resolve_path(args.out)
    client = make_client(args, out.parent / "cache")
    quota = math.ceil(args.target / len(provinces))
    enough = math.ceil(quota * args.stop_at)

    candidates: dict[str, dict[str, Any]] = {}
    for index, province in enumerate(provinces, 1):
        found_here = 0
        for query, brand in province_queries(province, args.by_area):
            if found_here >= enough:
                break
            try:
                places = client.search(
                    query, repair_only=brand is None, max_pages=args.pages, bbox=PROVINCE_BBOX.get(province)
                )
            except PlacesError as exc:
                print(f"\n{exc}", file=sys.stderr)
                if exc.status in (400, 401, 403):
                    sys.exit(client.auth_hint)
                continue
            for place in places:
                if not keep_place(place, brand) or place["id"] in candidates:
                    continue
                record = to_record(place, province, query)
                candidates[place["id"]] = record
                if record["region"] == province:
                    found_here += 1
        print(
            f"[{index:2}/{len(provinces)}] {province:<16} {found_here:4} here | "
            f"total {len(candidates):5} | requests {client.requests_made}, cached {client.cache_hits}"
        )

    selected = select_balanced(list(candidates.values()), args.target, provinces)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": client.label,
        "target": args.target,
        "candidates": len(candidates),
        "count": len(selected),
        "workshops": selected,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(selected)} workshops (of {len(candidates)} candidates) → {out}")
    print(f"Search requests this run: {client.requests_made} (cache hits: {client.cache_hits})")
    _print_stats(selected)
    return 0


def _read_workshops(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        sys.exit(f"{path} not found — run `crawl` first.")
    return json.loads(path.read_text(encoding="utf-8"))["workshops"]


def _print_stats(workshops: list[dict[str, Any]]) -> None:
    per_region = Counter(w["region"] for w in workshops)
    brand = sum(1 for w in workshops if _is_brand(w))
    types = Counter(w["type"] for w in workshops)
    print(f"Total {len(workshops)} | VinFast {brand} | " + ", ".join(f"{k} {v}" for k, v in sorted(types.items())))
    for region in PROVINCES:
        print(f"  {region:<16} {per_region.pop(region, 0):4}")
    for region, count in sorted(per_region.items()):
        print(f"  {region:<16} {count:4}  (not a current province)")


def cmd_stats(args: argparse.Namespace) -> int:
    _print_stats(_read_workshops(_resolve_path(args.out)))
    return 0


IMPORT_FIELDS = (
    "center_id",
    "name",
    "region",
    "type",
    "manager_email",
    "manager_national_id",
    "address",
    "latitude",
    "longitude",
    "place_id",
)


def cmd_import(args: argparse.Namespace) -> int:
    workshops = _read_workshops(_resolve_path(args.out))
    rows = [{k: w.get(k) for k in IMPORT_FIELDS} for w in workshops]
    body = json.dumps({"mode": "upsert", "data": {"service_centers": rows}}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["X-Admin-Token"] = args.token
    request = urllib.request.Request(f"{args.url.rstrip('/')}/admin/import", data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            summary = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        sys.exit(f"Import failed: HTTP {exc.code} {exc.read().decode('utf-8', 'replace')[:500]}")
    except urllib.error.URLError as exc:
        sys.exit(
            f"Cannot reach mock-ev-system at {args.url}: {exc.reason}\n"
            "Start it: cd backend && uv run --package mock-ev-system uvicorn mock_ev_system.main:app --port 8100"
        )
    print(f"Imported {len(rows)} service centers into {args.url}: {json.dumps(summary, ensure_ascii=False)}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workshop_crawl", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def crawl_opts(p: argparse.ArgumentParser) -> None:
        p.add_argument("--target", type=int, default=1000, help="number of workshops to keep (default 1000)")
        p.add_argument("--pages", type=int, default=3, choices=[1, 2, 3], help="pages of 20 per query (max 3)")
        p.add_argument("--provinces", help="comma-separated subset, e.g. 'Hà Nội,Đà Nẵng' (default: all 34)")
        p.add_argument(
            "--stop-at", type=float, default=2.0, help="stop querying a province at this × its quota (default 2)"
        )
        p.add_argument(
            "--source",
            choices=SOURCES,
            default=DEFAULT_SOURCE,
            help="place provider (default: WORKSHOP_CRAWL_SOURCE, else aws)",
        )
        p.add_argument(
            "--by-area",
            action="store_true",
            help="also query each district of provinces listed in PROVINCE_AREAS (more workshops, more requests)",
        )

    p = sub.add_parser("plan", help="show the query plan and worst-case request count (no API calls)")
    crawl_opts(p)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("crawl", help="search the place provider and write the balanced workshop list")
    crawl_opts(p)
    p.add_argument("--key", help="API key (default: AWS_LOCATION_API_KEY or GOOGLE_MAPS_API_KEY, per --source)")
    p.add_argument(
        "--aws-region", default=DEFAULT_AWS_REGION, help="Amazon Location region (default: AWS_LOCATION_REGION)"
    )
    p.add_argument(
        "--aws-intended-use",
        choices=("Storage", "SingleUse"),
        default="Storage",
        help="Storage (default) is required to keep results in a database; SingleUse is cheaper",
    )
    p.add_argument("--with-contact", action="store_true", help="also fetch phone (+ rating on Google); pricier")
    p.add_argument("--out", default=DEFAULT_OUT)
    p.set_defaults(func=cmd_crawl)

    p = sub.add_parser("stats", help="count crawled workshops per province")
    p.add_argument("--out", default=DEFAULT_OUT)
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("import", help="upsert the crawled workshops into mock-ev-system service_centers")
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--url", default=DEFAULT_URL, help="mock-ev-system base URL (default: EV_MOCK_URL)")
    p.add_argument("--token", default=DEFAULT_TOKEN, help="admin token (default: EV_MOCK_ADMIN_TOKEN)")
    p.set_defaults(func=cmd_import)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Vietnamese names on Windows consoles
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
