"""Bound to dedicated local synthetic services; never falls back to .env URLs."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BACKEND = ROOT / "backend"
DATABASE_URL = "postgresql+psycopg://p146_eval:p146_eval_local@127.0.0.1:35432/p146_eval_booking"
REDIS_URL = "redis://127.0.0.1:36379/0"

parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=("migration", "tests"))
parser.add_argument("--attempt", type=int, default=1)
args = parser.parse_args()
assert args.attempt >= 1
attempt = f"{args.attempt:02d}"
os.environ.update({
    "DATABASE_URL": DATABASE_URL,
    "DATABASE_HOST": "127.0.0.1", "DATABASE_PORT": "35432",
    "DATABASE_NAME": "p146_eval_booking", "DATABASE_USER": "p146_eval",
    "DATABASE_PASSWORD": "p146_eval_local",
    "EVAL_DATABASE_URL": DATABASE_URL, "EVAL_REDIS_URL": REDIS_URL,
})
sys.path.insert(0, str(BACKEND))
from src.config import get_settings  # noqa: E402
from sqlalchemy import create_engine, make_url, text  # noqa: E402

resolved = get_settings().sqlalchemy_database_url
assert resolved == DATABASE_URL, "Settings must resolve exclusively to the dedicated staging URL"
parsed = make_url(resolved)
assert (parsed.host, parsed.port, parsed.database, parsed.username) == ("127.0.0.1", 35432, "p146_eval_booking", "p146_eval")
engine = create_engine(resolved)
with engine.connect() as connection:
    identity = connection.execute(text("SELECT current_database(), current_user")).one()
    assert tuple(identity) == ("p146_eval_booking", "p146_eval")

command = [sys.executable, "-m", "alembic", "upgrade", "head"] if args.mode == "migration" else [
    sys.executable, "-m", "pytest", "tests/test_agents/test_evaluation_persistence.py",
    "--run-staging", "-q", "--junitxml=" + str(HERE / f"staging_persistence_{attempt}.xml"),
]
with (HERE / f"staging_{args.mode}_{attempt}.log").open("x", encoding="utf-8") as log:
    completed = subprocess.run(command, cwd=BACKEND, env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT)
receipt = {
    "scope": "DEDICATED_SYNTHETIC_DATABASE_ONLY", "mode": args.mode,
    "database": {"host": parsed.host, "port": parsed.port, "name": parsed.database, "user": parsed.username},
    "redis": {"host": "127.0.0.1", "port": 36379, "database": 0},
    "production_settings_used": False, "env_file_modified": False,
    "exit_code": completed.returncode,
    "limitations": ["Service fixtures replace chat/message transport and email.", "Persistence test reopens SQL engines; it does not restart an application worker or test browser streaming.", "Schema-isolated fixture creates its own SQLModel tables; successful public-schema migration is separate evidence."],
}
if args.mode == "migration" and completed.returncode == 0:
    with engine.connect() as connection:
        receipt["alembic_revisions"] = list(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
        receipt["extensions"] = list(connection.execute(text("SELECT extname FROM pg_extension ORDER BY extname")).scalars())
        receipt["public_table_count"] = connection.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")).scalar_one()
engine.dispose()
with (HERE / f"staging_{args.mode}_receipt_{attempt}.json").open("x", encoding="utf-8") as stream:
    json.dump(receipt, stream, indent=2)
print(json.dumps(receipt))
raise SystemExit(completed.returncode)
