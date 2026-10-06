"""The OEM pull is scheduled only when the backend is not in demo (static ODO) mode."""

import importlib

import pytest

from src.config import get_settings


@pytest.fixture
def reload_beat(monkeypatch):
    import src.celery_tasks as celery_tasks

    def load(app_env: str, mode: str):
        monkeypatch.setenv("APP_ENV", app_env)
        monkeypatch.setenv("OEM_SYNC_MODE", mode)
        get_settings.cache_clear()
        return importlib.reload(celery_tasks).celery.conf.beat_schedule

    yield load
    monkeypatch.undo()
    get_settings.cache_clear()
    importlib.reload(celery_tasks)


@pytest.mark.parametrize(
    ("app_env", "mode", "scheduled"),
    [("production", "", True), ("development", "", False), ("development", "oem", True)],
)
def test_oem_sync_beat_follows_the_sync_mode(reload_beat, app_env, mode, scheduled):
    assert ("oem-sync-all-vehicles" in reload_beat(app_env, mode)) is scheduled
