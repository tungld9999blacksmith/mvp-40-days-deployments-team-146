"""Exercise the full local retry controller with no network calls."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def controller(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[3] / "eval/resume_when_provider_ready.py"
    spec = importlib.util.spec_from_file_location("provider_resume_controller", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = tmp_path / "eval/results"
    directory = results / "controller"
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text("{}", encoding="utf-8")
    (directory / "protected_previous_artifacts.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "RESULTS", results)
    sleeps = []
    monkeypatch.setattr(module, "time", SimpleNamespace(sleep=sleeps.append))
    instance = module.Controller(directory, interval=300, attempts=3)
    return instance, module, sleeps


def success(module, selected=1, repeats=1, sessions=False):
    return [{"model": module.MODEL, "complete": True, "selected": selected, "attempted": selected,
             "passed": selected, "errors": 0, "safety_violations": 0,
             "sessions": [{"error": None, "write_safety_passed": True, "turns": [{"turn": 1}]} for _ in range(20)] if sessions else []}
            for _ in range(repeats)]


def unavailable(module, code):
    row = success(module)[0]
    row.update({"passed": 0, "errors": 1, "provider_stop": {"error": f"ProviderError: {code}"}})
    return [row]


def test_429_recovery_runs_exactly_60_reminders_and_20_sessions(controller, monkeypatch):
    instance, module, sleeps = controller
    selected = []

    def evaluate(stage, arguments):
        selected.append((stage, arguments))
        instance.runs.append(stage)
        return {
            "preflight_01": unavailable(module, "429"), "preflight_02": success(module),
            "reminder_60": success(module, selected=20, repeats=3),
            "sessions_20": success(module, sessions=True),
        }[stage]

    monkeypatch.setattr(instance, "evaluate", evaluate)
    assert instance.run() == 0
    assert sleeps == [300, 300]
    assert selected == [("preflight_01", ["--case", "REMINDER-12"]), ("preflight_02", ["--case", "REMINDER-12"]),
                        ("reminder_60", ["--category", "reminder", "--repeats", "3"]),
                        ("sessions_20", ["--case", "REMINDER-12", "--sessions"])]
    result = json.loads((instance.directory / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "EVALUATIONS_COMPLETED_PENDING_HUMAN_REVIEW"
    assert result["semantic_task_success"] == "NEEDS_HUMAN_REVIEW"


@pytest.mark.parametrize("code", ["401", "402", "500"])
def test_non_429_preflight_error_stops_without_retry_or_batch(controller, monkeypatch, code):
    instance, module, sleeps = controller
    calls = []
    monkeypatch.setattr(instance, "evaluate", lambda stage, _: calls.append(stage) or unavailable(module, code))
    assert instance.run() == 2
    assert calls == ["preflight_01"] and sleeps == [300]


def test_429_polling_is_bounded(controller, monkeypatch):
    instance, module, sleeps = controller
    calls = []
    monkeypatch.setattr(instance, "evaluate", lambda stage, _: calls.append(stage) or unavailable(module, "429"))
    assert instance.run() == 2
    assert len(calls) == len(sleeps) == 3
    assert json.loads((instance.directory / "result.json").read_text(encoding="utf-8"))["status"] == "POLL_LIMIT_REACHED_PROVIDER_STILL_UNAVAILABLE"


def test_incomplete_reminder_batch_does_not_run_sessions(controller, monkeypatch):
    instance, module, _ = controller
    calls = []

    def evaluate(stage, _):
        calls.append(stage)
        return success(module) if stage.startswith("preflight") else success(module, selected=20, repeats=1)

    monkeypatch.setattr(instance, "evaluate", evaluate)
    assert instance.run() == 2
    assert calls == ["preflight_01", "reminder_60"]


def test_session_error_is_not_success(controller, monkeypatch):
    instance, module, _ = controller

    def evaluate(stage, _):
        if stage == "reminder_60":
            return success(module, selected=20, repeats=3)
        rows = success(module, sessions=stage == "sessions_20")
        if stage == "sessions_20":
            rows[0]["sessions"][0]["error"] = "429"
        return rows

    monkeypatch.setattr(instance, "evaluate", evaluate)
    assert instance.run() == 2
    assert json.loads((instance.directory / "result.json").read_text(encoding="utf-8"))["status"] == "STOPPED_SESSIONS_INCOMPLETE_OR_FAILED"


def test_historical_change_is_reported_and_cannot_pass(controller):
    instance, _, _ = controller
    (instance.directory / "protected_previous_artifacts.json").write_text(json.dumps({"missing_old.json": "old_hash"}), encoding="utf-8")
    assert instance.finish("EVALUATIONS_COMPLETED_PENDING_HUMAN_REVIEW") == 2
    assert json.loads((instance.directory / "result.json").read_text(encoding="utf-8"))["changed"] == ["missing_old.json"]
