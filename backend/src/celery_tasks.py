from celery import Celery
from celery.schedules import crontab

from src.config import get_settings

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
    ],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    beat_schedule={
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
    },
)

if not get_settings().uses_static_odometer():
    # FEAT-VEH-001 JOB-VEH-001: pull odometer + service history of every vehicle.
    celery.conf.beat_schedule["oem-sync-all-vehicles"] = {
        "task": "oem.sync_all_vehicles",
        "schedule": float(get_settings().oem_sync_interval_seconds),
    }
