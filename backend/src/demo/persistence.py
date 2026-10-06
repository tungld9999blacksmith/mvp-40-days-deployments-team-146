"""Local registration snapshots; booking and chat data remain in memory."""

import json
import os
from pathlib import Path

FIELDS = ("users", "workshop_owners", "vehicles", "workshops", "onboarding")


def save_registration(store):
    if store.registration_path is None:
        return
    with store.registration_lock:
        payload = {"version": 1, **{key: getattr(store, key) for key in FIELDS}}
        payload["operations"] = [
            [key, token, body, result] for (key, token), (body, result) in store.onboarding_operations.items()
        ]
        encoded = json.dumps(payload, ensure_ascii=False, indent=2)
        path = store.registration_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(encoded, encoding="utf-8")
        os.replace(temporary, path)


def load_registration(store, path: Path):
    store.registration_path = path
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or any(not isinstance(payload.get(key), dict) for key in FIELDS):
        raise ValueError("Invalid demo registration snapshot")
    for key in FIELDS:
        getattr(store, key).update(payload[key])
    store.onboarding_operations.update(
        {(key, token): (body, result) for key, token, body, result in payload.get("operations", [])}
    )
