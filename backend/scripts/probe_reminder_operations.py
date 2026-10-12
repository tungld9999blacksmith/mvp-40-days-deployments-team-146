"""Read-only DB/Redis/worker/provider diagnostics; never sends or enables a cohort."""

import json
import sys
from datetime import UTC, datetime
from email.utils import parseaddr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import httpx  # noqa: E402
import redis  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.modules.notification.email_service import email_configuration_ready  # noqa: E402


def probe():
    cfg = get_settings()
    report = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "readOnly": True,
        "emailMode": cfg.email_mode,
        "personalizationMode": cfg.personalized_reminders_mode,
        "oemMode": cfg.oem_sync_mode,
        "providerSendCalls": 0,
    }
    engine = create_engine(cfg.sqlalchemy_database_url, connect_args={"connect_timeout": 10})
    try:
        with engine.connect() as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            db.execute(text("SET LOCAL statement_timeout = '10s'"))
            report["database"] = {
                "connected": db.execute(text("SELECT 1")).scalar() == 1,
                "revisions": db.execute(text("SELECT version_num FROM alembic_version")).scalars().all(),
            }
    except Exception as exc:
        report["database"] = {"connected": False, "errorType": type(exc).__name__}
    finally:
        engine.dispose()
    for name, url in (
        ("redis", cfg.redis_connection_url),
        ("broker", cfg.celery_broker_url),
        ("resultBackend", cfg.celery_backend_url),
    ):
        client = redis.Redis.from_url(url, socket_connect_timeout=4, socket_timeout=4)
        try:
            report[name] = {"connected": bool(client.ping())}
        except Exception as exc:
            report[name] = {"connected": False, "errorType": type(exc).__name__}
        finally:
            client.close()
    if report["broker"]["connected"]:
        from src.celery_tasks import celery

        try:
            inspector = celery.control.inspect(timeout=3)
            replies = inspector.ping() or {}
            registered = inspector.registered() or {}
            expected = {"reminder.dispatch_due", "reminder.dispatch_delivery", "reminder.retry_emails"}
            report["workers"] = {
                "responding": len(replies),
                "scheduleTasksRegistered": bool(replies)
                and all(expected <= set(registered.get(name, [])) for name in replies),
            }
        except Exception as exc:
            report["workers"] = {"responding": 0, "errorType": type(exc).__name__}
    else:
        report["workers"] = {"responding": 0, "status": "broker_unreachable"}
    report["provider"] = {"configurationReady": email_configuration_ready(cfg), "deliveryVerified": False}
    if cfg.email_mode == "resend" and cfg.resend_api_key:
        # Official GET /domains checks key scope and sending-domain state without mail.
        try:
            response = httpx.get(
                "https://api.resend.com/domains", headers={"Authorization": f"Bearer {cfg.resend_api_key}"}, timeout=12
            )
            report["provider"]["domainsHttpStatus"] = response.status_code
            if response.status_code == 200:
                sender_domain = parseaddr(cfg.email_from)[1].rpartition("@")[2].lower()
                report["provider"]["senderDomainVerified"] = any(
                    row.get("name", "").lower() == sender_domain and row.get("status") == "verified"
                    for row in response.json().get("data", [])
                )
            else:
                report["provider"]["domainCheck"] = "unavailable_or_key_scope_restricted"
        except Exception as exc:
            report["provider"]["errorType"] = type(exc).__name__
    path = ROOT / "data/verification/driving-habit/latest/operations-probe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    probe()
