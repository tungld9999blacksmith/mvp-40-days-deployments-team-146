"""Celery-backed session revokers must enqueue fail-fast (API-101 / API-301).

The enqueue runs inside the logout request. With the default ``delay()`` a down
Redis held the request ~110 s (result-backend reconnect loop), the FE gave up
after 5 s and the DB connection dropped, turning the 503 into a 500.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.celery_tasks import FAIL_FAST_PUBLISH
from src.infrastructure.celery.tasks.auth_tasks import revoke_session_task
from src.infrastructure.celery.tasks.workshop_auth_tasks import revoke_workshop_session_task
from src.modules.auth.ports import RevokeEnqueueError as VehicleRevokeEnqueueError
from src.modules.auth.revoker import CelerySessionRevoker
from src.modules.workshop_owner_auth.ports import RevokeEnqueueError as WorkshopRevokeEnqueueError
from src.modules.workshop_owner_auth.revoker import CeleryWorkshopSessionRevoker


class _RecordingApplyAsync:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, args=None, kwargs=None, **options):
        self.calls.append((args, options))
        if self.fail:
            raise ConnectionError("Error 10061 connecting to localhost:6379")


def test_fail_fast_publish_skips_result_backend_and_bounds_retries():
    assert FAIL_FAST_PUBLISH["ignore_result"] is True
    assert FAIL_FAST_PUBLISH["retry_policy"]["max_retries"] <= 1


def test_workshop_revoker_enqueues_fail_fast(monkeypatch):
    recorder = _RecordingApplyAsync()
    monkeypatch.setattr(revoke_workshop_session_task, "apply_async", recorder)
    owner_id = uuid4()

    CeleryWorkshopSessionRevoker().enqueue_revoke(uid="u-1", owner_id=owner_id, trace_id="req-1")

    assert recorder.calls == [(("u-1", str(owner_id), "req-1"), FAIL_FAST_PUBLISH)]


def test_vehicle_revoker_enqueues_fail_fast(monkeypatch):
    recorder = _RecordingApplyAsync()
    monkeypatch.setattr(revoke_session_task, "apply_async", recorder)

    CelerySessionRevoker().enqueue_revoke(uid="u-1", user_id=7, trace_id="req-1")

    assert recorder.calls == [(("u-1", 7, "req-1"), FAIL_FAST_PUBLISH)]


@pytest.mark.parametrize(
    ("task", "enqueue", "expected"),
    [
        (
            revoke_workshop_session_task,
            lambda: CeleryWorkshopSessionRevoker().enqueue_revoke(uid="u-1", owner_id=None),
            WorkshopRevokeEnqueueError,
        ),
        (
            revoke_session_task,
            lambda: CelerySessionRevoker().enqueue_revoke(uid="u-1", user_id=7),
            VehicleRevokeEnqueueError,
        ),
    ],
)
def test_broker_failure_maps_to_revoke_enqueue_error(monkeypatch, task, enqueue, expected):
    monkeypatch.setattr(task, "apply_async", _RecordingApplyAsync(fail=True))

    with pytest.raises(expected):
        enqueue()
