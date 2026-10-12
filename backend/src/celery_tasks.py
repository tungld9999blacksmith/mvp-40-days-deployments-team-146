from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging, worker_init, worker_process_init, worker_process_shutdown, worker_shutdown

from src.config import get_settings
from src.infrastructure.logging import configure_logging
from src.infrastructure.observability import (
    WORKER_SERVICE,
    configure_langsmith,
    jobs_project,
    setup_telemetry,
    shutdown_telemetry,
)

celery = Celery(
    "worker",
    broker=get_settings().celery_broker_url,
    backend=get_settings().celery_backend_url,
    include=[
        "src.infrastructure.celery.tasks.auth_tasks",
        "src.infrastructure.celery.tasks.workshop_tasks",
        "src.infrastructure.celery.tasks.workshop_auth_tasks",
        "src.infrastructure.celery.tasks.oem_sync_tasks",
        "src.infrastructure.celery.tasks.reminder_tasks",
        "src.infrastructure.celery.tasks.embedding_tasks",
        "src.infrastructure.celery.tasks.booking_tasks",
        "src.infrastructure.celery.tasks.crm_tasks",
        "src.infrastructure.celery.tasks.memory_tasks",
        "src.infrastructure.celery.tasks.demo_tasks",
        "src.infrastructure.celery.tasks.outbox_tasks",
    ],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    beat_schedule={
        "agent-memory-cleanup": {"task": "agent_memory.cleanup", "schedule": 60.0},
        "agent-memory-retention": {"task": "agent_memory.retention", "schedule": crontab(hour=3, minute=45)},
        # FEAT-AUTH-003: re-enqueue workshop verifications whose retry was lost.
        "workshop-reconcile-verifications": {
            "task": "workshop.reconcile_verifications",
            "schedule": 300.0,
        },
        # FEAT-AUTH-003 BR-208: purge unfinished workshop onboardings daily 02:00.
        "workshop-purge-expired-onboarding": {
            "task": "workshop.purge_expired_onboarding",
            "schedule": crontab(hour=2, minute=0),
        },
        # FEAT-NOTI-001 JOB-NOTI-001: daily maintenance reminders (Asia/Ho_Chi_Minh).
        "maintenance-reminders": {
            "task": "reminder.send_all",
            "schedule": crontab(hour=get_settings().reminder_job_hour, minute=0),
        },
        "maintenance-email-retries": {"task": "reminder.retry_emails", "schedule": 60.0},
        "maintenance-delivery-dispatch": {"task": "reminder.dispatch_due", "schedule": 900.0},
        "maintenance-email-payload-retention": {
            "task": "reminder.purge_email_payloads",
            "schedule": crontab(hour=3, minute=15),
        },
        # FEAT-AUTH-004: purge workshop-owner auth audit older than 60 days.
        "workshop-auth-purge-events": {
            "task": "workshop_auth.purge_events",
            "schedule": crontab(hour=2, minute=30),
        },
        # FEAT-BOOK-001 BR-015: cancel holds the workshop never confirmed.
        "booking-cancel-unconfirmed": {
            "task": "booking.cancel_unconfirmed",
            "schedule": 300.0,
        },
        # FEAT-NOTI-002 JOB-BR-001 (us-033): 24h appointment reminders.
        "booking-reminder-send-due": {
            "task": "booking_reminder.send_due",
            "schedule": 60.0 * get_settings().booking_reminder_job_interval_minutes,
        },
        # us-041 JOB-FU-001: send due post-service follow-ups every 15 minutes.
        "follow-up-send-due": {
            "task": "follow_up.send_due",
            "schedule": 900.0,
        },
        # us-041 JOB-FU-002: close follow-ups unanswered for 72h, hourly.
        "follow-up-close-expired": {
            "task": "follow_up.close_expired",
            "schedule": crontab(minute=5),
        },
        # us-049 JOB-QT-01: purge stale quote drafts daily 03:00 (VN).
        "quote-purge-stale-drafts": {
            "task": "quote.purge_stale_drafts",
            "schedule": crontab(hour=3, minute=0),
        },
        # bao-gia-hai-tang OV5: photos uploaded for an extra that was never sent, hourly.
        "booking-line-purge-pending-photos": {
            "task": "booking_line.purge_pending_photos",
            "schedule": crontab(minute=20),
        },
        # Owner reply SLA: email the workshop once a line waits > 10 min for the owner.
        "booking-line-alert-overdue-replies": {
            "task": "booking_line.alert_overdue_replies",
            "schedule": 60.0,
        },
        # Transactional outbox: safety-net scan (commits also wake the dispatcher).
        "outbox-dispatch": {
            "task": "outbox.dispatch",
            "schedule": float(get_settings().outbox_dispatch_interval_seconds),
        },
        "outbox-purge": {
            "task": "outbox.purge",
            "schedule": crontab(hour=3, minute=30),
        },
    },
)

# apply_async options for enqueues made inside an HTTP request (e.g. the logout
# revoke). Without them a down Redis blocks the request for ~2 minutes: the
# result backend retries its pub/sub reconnect 20 times before giving up. Fire-
# and-forget tasks need no result subscription, and the publish gets one retry.
FAIL_FAST_PUBLISH: dict = {
    "ignore_result": True,
    "retry": True,
    "retry_policy": {"max_retries": 1, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.2},
}

if not get_settings().uses_static_odometer():
    # FEAT-VEH-001 JOB-VEH-001: pull odometer + service history of every vehicle.
    celery.conf.beat_schedule["oem-sync-all-vehicles"] = {
        "task": "oem.sync_all_vehicles",
        "schedule": float(get_settings().oem_sync_interval_seconds),
    }

if get_settings().demo_login_enabled:
    # Shared demo account: reset every DEMO_RESET_INTERVAL_HOURS (checked hourly).
    celery.conf.beat_schedule["demo-account-reset"] = {
        "task": "demo_account.reset_if_due",
        "schedule": crontab(minute=10),
    }

# --------------------------------------------------------------------------
# Logging + observability of the worker process
# --------------------------------------------------------------------------
# Module level runs in the API process too (it imports this to enqueue): chat project.
# Worker processes switch to the jobs project in the signals below.
configure_langsmith(get_settings())


def _use_jobs_langsmith_project() -> None:
    """Worker LLM runs (summaries, follow-ups...) are traced into their own project."""
    settings = get_settings()
    configure_langsmith(settings, project=jobs_project(settings))


def configure_worker_logging(otel_logger_provider=None) -> None:
    """Worker logs: JSON lines on stdout (always), PII-redacted, own file name."""
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        json_logs=True,
        redact_pii=settings.log_redact_pii,
        file_formats=settings.log_file_formats,
        log_dir=settings.log_dir,
        file_name="worker",
        max_bytes=settings.log_file_max_bytes,
        backup_count=settings.log_file_backup_count,
        otel_logger_provider=otel_logger_provider,
    )


@setup_logging.connect
def _setup_worker_logging(**_kwargs) -> None:
    # Connecting this signal stops Celery from installing its own log handlers.
    configure_worker_logging()


def _start_worker_telemetry() -> None:
    telemetry = setup_telemetry(WORKER_SERVICE)
    if telemetry is not None:
        configure_worker_logging(telemetry.logger_provider)


def is_prefork_pool(pool_cls) -> bool:
    """True for the forking pool (Railway default); False for solo / threads (local Windows)."""
    if isinstance(pool_cls, str):
        return pool_cls == "prefork"
    return getattr(pool_cls, "__module__", "") == "celery.concurrency.prefork"


@worker_init.connect
def _init_worker_telemetry(sender=None, **_kwargs) -> None:
    _use_jobs_langsmith_project()
    # Pools that never fork run tasks in this process: set up here.
    if not is_prefork_pool(getattr(sender, "pool_cls", None)):
        _start_worker_telemetry()


@worker_process_init.connect
def _init_worker_child_telemetry(**_kwargs) -> None:
    # Prefork: per pool child, after fork - the SDK's exporter threads do not survive a fork.
    _use_jobs_langsmith_project()
    _start_worker_telemetry()


@worker_process_shutdown.connect
@worker_shutdown.connect
def _shutdown_worker_telemetry(**_kwargs) -> None:
    shutdown_telemetry()
