"""Read-only aggregate JSON/HTML dashboard; no LLM, OEM or mail provider calls."""

import argparse
import json
import sys
from datetime import UTC, datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine  # noqa: E402
from sqlmodel import Session  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.modules.notification.metrics_service import aggregate_metrics  # noqa: E402


def dashboard_html(report: dict) -> str:
    rows = "".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(json.dumps(value, ensure_ascii=False))}</td></tr>"
        for key, value in report.items()
        if key != "notes"
    )
    notes = "".join(f"<li>{escape(note)}</li>" for note in report["notes"])
    return f"""<!doctype html><html lang="vi"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>EV Care — Reminder metrics</title>
<style>body{{font:16px system-ui;margin:24px;max-width:1100px;color:#17221e;background:#f5faf7}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{border:1px solid #b4c7bd;padding:12px;text-align:left;overflow-wrap:anywhere}}td{{max-width:600px}}h1{{font-size:24px}}</style>
<h1>EV Care — Nhắc theo mức sử dụng xe</h1><p>Báo cáo tổng hợp; không chứa danh tính, ODO trace hoặc nội dung chat.</p>
<table><caption>Chất lượng forecast, shadow, booking và giao nhận</caption>{rows}</table><ul>{notes}</ul></html>"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30, choices=range(1, 91))
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    args = parser.parse_args()
    engine = create_engine(get_settings().sqlalchemy_database_url)
    try:
        with Session(engine) as db:
            if engine.dialect.name == "postgresql":
                db.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
                db.connection().exec_driver_sql("SET LOCAL statement_timeout = 10000")
            report = aggregate_metrics(db, now=datetime.now(UTC), days=args.days)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        args.html.write_text(dashboard_html(report), encoding="utf-8")
        print(json.dumps({"status": "passed", "evaluationCount": report["evaluationCount"]}))
    finally:
        engine.dispose()
