"""Versioned prompts: the code is the source of truth; lock consistency, version bumps, Hub manifest round trip."""

from __future__ import annotations

import json

from src.infrastructure.prompts import prompt_version
from src.infrastructure.prompts.hub import build_template, hub_repo_name, manifest_of, text_from_manifest
from src.infrastructure.prompts.registry import (
    LOCK_PATH,
    PROMPT_SOURCES,
    TEXTS_DIR,
    drifted_prompts,
    export_texts,
    prompt_names,
    read_lock,
    refresh_lock,
    source_text,
    stale_prompts,
)


def test_every_prompt_file_is_locked_and_unchanged() -> None:
    # Fails when a prompt was edited without `python scripts/prompt_sync.py lock`.
    assert drifted_prompts() == []
    assert stale_prompts() == []
    assert sorted(read_lock()) == prompt_names() == sorted(PROMPT_SOURCES)


def test_code_constants_are_the_source_of_truth() -> None:
    from src.agents.conversation_guards.input_guard import INJECTION_SYSTEM_NOTE
    from src.agents.prompts import EV_CARE_BASE_PROMPT
    from src.agents.tool_review import REVIEW_PROMPT

    assert EV_CARE_BASE_PROMPT == source_text("ev_care_base")
    assert REVIEW_PROMPT == source_text("tool_review")
    assert INJECTION_SYSTEM_NOTE == source_text("injection_note")
    for name in PROMPT_SOURCES:
        assert source_text(name).strip(), name


def test_export_writes_the_texts_from_the_code(tmp_path) -> None:
    changed = export_texts(tmp_path)

    assert changed == sorted(PROMPT_SOURCES)
    assert drifted_prompts(tmp_path) == []
    assert export_texts(tmp_path) == []  # second run: nothing to rewrite


def test_edited_copy_is_reported_as_drift(tmp_path) -> None:
    export_texts(tmp_path)
    (tmp_path / "tool_review.txt").write_bytes(b"edited by hand")
    (tmp_path / "orphan.txt").write_bytes(b"no code behind it")

    assert drifted_prompts(tmp_path) == ["orphan", "tool_review"]
    assert sorted(export_texts(tmp_path)) == ["orphan", "tool_review"]
    assert drifted_prompts(tmp_path) == []


def test_prompt_version_reads_the_lock() -> None:
    assert prompt_version("ev_care_base") == read_lock()["ev_care_base"]["version"]
    assert isinstance(prompt_version("ev_care_base"), int)


def test_new_prompt_starts_at_version_one(tmp_path) -> None:
    (tmp_path / "greeting.txt").write_bytes("Xin chào".encode())
    lock_path = tmp_path / "versions.lock.json"

    lock = refresh_lock(tmp_path, lock_path)

    assert lock["greeting"]["version"] == 1
    assert read_lock(lock_path) == lock


def test_refresh_bumps_version_only_when_text_changes(tmp_path) -> None:
    (tmp_path / "greeting.txt").write_bytes(b"v one")
    lock_path = tmp_path / "versions.lock.json"
    refresh_lock(tmp_path, lock_path)

    unchanged = refresh_lock(tmp_path, lock_path)
    assert unchanged["greeting"]["version"] == 1

    (tmp_path / "greeting.txt").write_bytes(b"v two")
    assert stale_prompts(tmp_path, lock_path) == ["greeting"]

    changed = refresh_lock(tmp_path, lock_path)
    assert changed["greeting"]["version"] == 2
    assert stale_prompts(tmp_path, lock_path) == []


def test_refresh_drops_entries_of_removed_files(tmp_path) -> None:
    (tmp_path / "a.txt").write_bytes(b"a")
    (tmp_path / "b.txt").write_bytes(b"b")
    lock_path = tmp_path / "versions.lock.json"
    refresh_lock(tmp_path, lock_path)

    (tmp_path / "b.txt").unlink()

    assert sorted(refresh_lock(tmp_path, lock_path)) == ["a"]


def test_manifest_round_trip_keeps_text_exactly() -> None:
    # Braces and JSON-like text must survive: the message is not a template string.
    text = 'Xin chào {name}, mã {"code": 1}\r\n  Dòng 2 — đã kiểm tra'

    assert text_from_manifest(manifest_of(text)) == text
    assert text_from_manifest(json.loads(json.dumps(manifest_of(text)))) == text


def test_manifest_with_two_messages_is_rejected() -> None:
    manifest = manifest_of("một")
    manifest["kwargs"]["messages"] = manifest["kwargs"]["messages"] * 2

    try:
        text_from_manifest(manifest)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_build_template_has_one_system_message() -> None:
    template = build_template("hệ thống")

    assert [type(m).__name__ for m in template.messages] == ["SystemMessage"]


def test_hub_repo_name_uses_hyphens() -> None:
    assert hub_repo_name("follow_up_classifier", "ev-care-") == "ev-care-follow-up-classifier"


def test_lock_file_lives_with_the_texts() -> None:
    assert LOCK_PATH == TEXTS_DIR / "versions.lock.json"
    assert LOCK_PATH.exists()
