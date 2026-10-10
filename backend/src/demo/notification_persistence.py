"""Atomic snapshots for demo reminders, independent of booking/chat memory."""

import json
import os
from pathlib import Path

FIELDS = (
    "notification_preferences",
    "reminders",
    "email_deliveries",
    "email_cooldowns",
    "email_suppressions",
    "email_events",
)


def save_notifications(store):
    if store.notifications_path is None:
        return
    with store.registration_lock:
        path = store.notifications_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, **{key: getattr(store, key) for key in FIELDS}}
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)


def load_notifications(store, path: Path):
    store.notifications_path = path
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or any(not isinstance(payload.get(key), dict) for key in FIELDS):
        raise ValueError("Invalid demo notification snapshot")
    for key in FIELDS:
        getattr(store, key).update(payload[key])
