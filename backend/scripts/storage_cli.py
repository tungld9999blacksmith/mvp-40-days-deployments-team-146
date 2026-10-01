"""
CLI for the file storage bucket (infrastructure/storage — Supabase Storage by default).

Run from backend/ (reads the root .env):
    python scripts/storage_cli.py upload data/knowledge/raw --prefix manuals/vinfast
    python scripts/storage_cli.py upload a.pdf b.pdf --prefix manuals --overwrite
    python scripts/storage_cli.py list manuals -r
    python scripts/storage_cli.py info manuals/a.pdf
    python scripts/storage_cli.py url manuals/a.pdf --expires 600
    python scripts/storage_cli.py download manuals/a.pdf -o ./tmp
    python scripts/storage_cli.py delete manuals/a.pdf
    python scripts/storage_cli.py delete manuals --prefix --yes

Keys are made ASCII-safe by default ("Sổ tay VF8.pdf" -> "So-tay-VF8.pdf"); the
original file name is kept in the object's metadata as `original_name`.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

from src.config import get_settings  # noqa: E402
from src.infrastructure.storage import (  # noqa: E402
    FileStorage,
    StorageConflictError,
    StorageError,
    create_file_storage,
    join_key,
    normalize_key,
    safe_key,
)


def _human_size(size: int | None) -> str:
    if size is None:
        return "-"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _collect_files(paths: list[str], recursive: bool, include: list[str]) -> list[tuple[Path, str]]:
    """Return (local file, key relative to --prefix) pairs."""
    found: list[tuple[Path, str]] = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append((path, path.name))
        elif path.is_dir():
            pattern = "**/*" if recursive else "*"
            for file in sorted(path.glob(pattern)):
                if file.is_file():
                    found.append((file, file.relative_to(path).as_posix()))
        else:
            print(f"  ! not found: {raw}", file=sys.stderr)
    if include:
        found = [(f, k) for f, k in found if any(fnmatch.fnmatch(f.name.lower(), p.lower()) for p in include)]
    return found


# -- commands ---------------------------------------------------------------
def cmd_upload(storage: FileStorage, args: argparse.Namespace) -> int:
    files = _collect_files(args.paths, args.recursive, args.include)
    if not files:
        print("No files to upload.")
        return 1

    uploaded = skipped = failed = 0
    total_bytes = 0
    for local, rel_key in files:
        key = join_key(args.prefix or "", rel_key)
        if not args.keep_names:
            key = safe_key(key)
        label = f"{local} -> {storage.bucket}/{key}"

        if args.dry_run:
            print(f"  [dry-run] {label}")
            continue
        if args.skip_existing and storage.exists(key):
            print(f"  [skip]    {label} (exists)")
            skipped += 1
            continue
        try:
            obj = storage.upload_file(
                local,
                key,
                content_type=args.content_type,
                overwrite=args.overwrite,
                metadata={"original_name": local.name},
            )
            uploaded += 1
            total_bytes += obj.size or 0
            print(f"  [ok]      {label} ({_human_size(obj.size)})")
        except StorageConflictError:
            failed += 1
            print(f"  [exists]  {label} — use --overwrite or --skip-existing", file=sys.stderr)
        except (StorageError, OSError) as exc:
            failed += 1
            print(f"  [fail]    {label}: {exc}", file=sys.stderr)

    if args.dry_run:
        print(f"\n{len(files)} file(s) would be uploaded.")
        return 0
    print(f"\nUploaded {uploaded} ({_human_size(total_bytes)}), skipped {skipped}, failed {failed}.")
    return 1 if failed else 0


def cmd_list(storage: FileStorage, args: argparse.Namespace) -> int:
    if args.recursive:
        objects = list(storage.iter_objects(args.prefix, recursive=True))
    else:
        objects = storage.list(args.prefix, limit=args.limit)
    for obj in objects:
        if obj.is_folder:
            print(f"  {'<dir>':>10}  {'':19}  {obj.key}/")
        else:
            updated = obj.updated_at.strftime("%Y-%m-%d %H:%M:%S") if obj.updated_at else "-"
            print(f"  {_human_size(obj.size):>10}  {updated:19}  {obj.key}")
    print(f"\n{len(objects)} item(s) in {storage.bucket}/{args.prefix or ''}")
    return 0


def cmd_info(storage: FileStorage, args: argparse.Namespace) -> int:
    obj = storage.info(args.key)
    for field, value in obj.model_dump(exclude={"is_folder"}).items():
        print(f"  {field:13} {value}")
    return 0


def cmd_url(storage: FileStorage, args: argparse.Namespace) -> int:
    print(storage.signed_url(args.key, args.expires, download=args.download))
    return 0


def cmd_download(storage: FileStorage, args: argparse.Namespace) -> int:
    target = storage.download_to(args.key, args.output)
    print(f"Saved {storage.bucket}/{normalize_key(args.key)} -> {target}")
    return 0


def cmd_delete(storage: FileStorage, args: argparse.Namespace) -> int:
    if args.prefix:
        keys = [obj.key for key in args.keys for obj in storage.iter_objects(key, recursive=True)]
    else:
        keys = [normalize_key(k) for k in args.keys]
    if not keys:
        print("Nothing to delete.")
        return 0
    if not args.yes:
        for key in keys:
            print(f"  {key}")
        if input(f"Delete {len(keys)} object(s) from '{storage.bucket}'? [y/N] ").strip().lower() != "y":
            print("Aborted.")
            return 1
    deleted: list[str] = []
    for start in range(0, len(keys), 100):
        deleted.extend(storage.delete(keys[start : start + 100]))
    print(f"Deleted {len(deleted)} object(s).")
    return 0


# -- parser -----------------------------------------------------------------
def build_parser(default_ttl: int) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="storage_cli", description="Manage files in the storage bucket.")
    parser.add_argument("--bucket", help="Bucket name (default: SUPABASE_STORAGE_BUCKET)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("upload", help="Upload files or folders")
    p.add_argument("paths", nargs="+", help="Local files and/or folders")
    p.add_argument("--prefix", default="", help="Destination folder inside the bucket")
    p.add_argument("-r", "--recursive", action="store_true", help="Include sub-folders (keeps the structure)")
    p.add_argument("--include", action="append", default=[], help="Glob filter on file name, e.g. '*.pdf' (repeatable)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--overwrite", action="store_true", help="Replace existing objects")
    group.add_argument("--skip-existing", action="store_true", help="Skip keys that already exist")
    p.add_argument("--content-type", help="Force a content type (default: guessed from extension)")
    p.add_argument("--keep-names", action="store_true", help="Do not transliterate keys to ASCII-safe names")
    p.add_argument("--dry-run", action="store_true", help="Show what would be uploaded")
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser("list", aliases=["ls"], help="List objects under a prefix")
    p.add_argument("prefix", nargs="?", default="")
    p.add_argument("-r", "--recursive", action="store_true")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("info", help="Show object metadata")
    p.add_argument("key")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("url", help="Create a signed URL for a private object")
    p.add_argument("key")
    p.add_argument("--expires", type=int, default=default_ttl, help=f"Seconds (default: {default_ttl})")
    p.add_argument("--download", action="store_true", help="Force download instead of inline view")
    p.set_defaults(func=cmd_url)

    p = sub.add_parser("download", help="Download an object")
    p.add_argument("key")
    p.add_argument("-o", "--output", default=".", help="Target file or existing folder (default: .)")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("delete", aliases=["rm"], help="Delete objects")
    p.add_argument("keys", nargs="+")
    p.add_argument("--prefix", action="store_true", help="Treat keys as folders and delete everything under them")
    p.add_argument("-y", "--yes", action="store_true", help="Do not ask for confirmation")
    p.set_defaults(func=cmd_delete)
    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    args = build_parser(settings.storage_signed_url_ttl_seconds).parse_args(argv)
    try:
        storage = create_file_storage(settings, bucket=args.bucket)
        return args.func(storage, args)
    except (StorageError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
