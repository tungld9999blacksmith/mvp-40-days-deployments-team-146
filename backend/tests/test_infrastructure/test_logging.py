"""structlog pipeline: PII redaction + log / json / csv file exports."""

import csv
import io
import json
import logging

import pytest
import structlog

from src.infrastructure.logging import (
    CSV_COLUMNS,
    REDACTED,
    PiiRedactor,
    configure_logging,
    get_logger,
    mask_phone,
    parse_file_formats,
    redact_text,
)

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.c2lnbmF0dXJlMTIz"


@pytest.fixture(autouse=True)
def _restore_logging():
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    yield
    for handler in root.handlers:
        if handler not in saved_handlers:
            handler.close()
    root.handlers, root.level = saved_handlers, saved_level
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


# ── redact_text ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Authorization: Bearer abc.def-123", f"Authorization: Bearer {REDACTED}"),
        ("auth Basic dXNlcjpwYXNz", f"auth Basic {REDACTED}"),
        (f"token {JWT} end", f"token {REDACTED} end"),
        ("key sk-ant-api03-abcdefghijklmnop1234", f"key {REDACTED}"),
        ("google AIzaSyA1234567890abcdefghijklmnopqrstuv", f"google {REDACTED}"),
        ("?api_key=s3cr3t&page=2", f"?api_key={REDACTED}&page=2"),
        ('{"password": "hunter2"}', f'{{"password": "{REDACTED}"}}'),
        ("mail tung.le@gmail.com now", "mail t***@gmail.com now"),
        ("call 0912345678", "call *******678"),
        ("call +84 912 345 678", "call ********678"),
        ("intl +1 415 555 2671", "intl ********671"),
    ],
)
def test_redact_text(raw, expected):
    assert redact_text(raw) == expected


@pytest.mark.parametrize(
    "safe",
    [
        "2026-09-30T03:54:18.918015Z",
        "order 12345 took 0.25s",
        "input_tokens=1532",
        "uuid 4bf92f3577b34da6a3ce929d0e0e4736",
    ],
)
def test_redact_text_leaves_normal_text(safe):
    assert redact_text(safe) == safe


def test_mask_phone_short():
    assert mask_phone("12") == "**"


# ── PiiRedactor (event dict) ────────────────────────────────────────────


def test_redactor_by_key_and_nested():
    payload = {"email": "a.b@x.io", "profile": {"phone": "0987654321", "full_name": "Le Tung"}}
    out = PiiRedactor()(
        None,
        "info",
        {
            "event": "signup",
            "password": "p",
            "discord_bot_token": "t",
            "api-key": "k",
            "Authorization": "Bearer xyz",
            "user": payload,
            "items": [{"access_token": "t"}, "mail a@b.co"],
            "input_tokens": 12,
            "cache_key": "user:1",
            "correlation_id": "0912345678",
        },
    )
    assert out["password"] == REDACTED
    assert out["discord_bot_token"] == REDACTED
    assert out["api-key"] == REDACTED
    assert out["Authorization"] == REDACTED
    assert out["user"] == {
        "email": "a***@x.io",
        "profile": {"phone": "*******321", "full_name": REDACTED},
    }
    assert out["items"] == [{"access_token": REDACTED}, "mail a***@b.co"]
    assert out["input_tokens"] == 12
    assert out["cache_key"] == "user:1"
    assert out["correlation_id"] == "0912345678"  # tracing fields are never touched
    # caller's objects are not mutated
    assert payload["profile"]["phone"] == "0987654321"


# ── outputs ─────────────────────────────────────────────────────────────


def _emit_sample():
    structlog.contextvars.bind_contextvars(correlation_id="cid-1", trace_id="tr-1")
    get_logger("app.native").info("user login", email="tung@gmail.com", attempts=2)
    logging.getLogger("app.stdlib").warning("sms to %s failed", "0912345678")
    try:
        raise ValueError("bad key sk-proj-abcdefghijklmnop1234")
    except ValueError:
        logging.getLogger("app.stdlib").exception("boom")


def test_stdout_json_is_redacted():
    buf = io.StringIO()
    configure_logging(stream=buf)
    _emit_sample()
    lines = [json.loads(line) for line in buf.getvalue().splitlines()]
    assert lines[0]["email"] == "t***@gmail.com"
    assert lines[0]["correlation_id"] == "cid-1"
    assert lines[1]["event"] == "sms to *******678 failed"
    exc = lines[2]["exception"][0]
    assert exc["exc_type"] == "ValueError"
    assert "sk-proj" not in json.dumps(exc)


def test_default_file_export_is_log_only(tmp_path):
    configure_logging(stream=io.StringIO(), file_formats="log", log_dir=tmp_path)
    _emit_sample()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app.log"]


def test_log_file_format(tmp_path):
    configure_logging(stream=io.StringIO(), file_formats=["log"], log_dir=tmp_path)
    _emit_sample()
    text = (tmp_path / "app.log").read_text(encoding="utf-8")
    first = text.splitlines()[0]
    assert "INFO" in first
    assert "[app.native] [cid=cid-1 trace=tr-1] user login" in first
    assert "email=t***@gmail.com" in first
    assert "attempts=2" in first
    assert "sms to *******678 failed" in text
    assert "Traceback (most recent call last)" in text
    assert "tung@gmail.com" not in text
    assert "sk-proj" not in text


def test_json_file_format(tmp_path):
    configure_logging(stream=io.StringIO(), file_formats="json", log_dir=tmp_path)
    _emit_sample()
    lines = (tmp_path / "app.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert [r["logger"] for r in records] == ["app.native", "app.stdlib", "app.stdlib"]
    assert records[0]["email"] == "t***@gmail.com"
    assert records[2]["exception"][0]["exc_type"] == "ValueError"


def test_csv_file_format(tmp_path):
    configure_logging(stream=io.StringIO(), file_formats="csv", log_dir=tmp_path)
    _emit_sample()
    with open(tmp_path / "app.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert tuple(rows[0].keys()) == CSV_COLUMNS
    assert rows[0]["event"] == "user login"
    assert rows[0]["correlation_id"] == "cid-1"
    assert json.loads(rows[0]["extra"]) == {"email": "t***@gmail.com", "attempts": 2}
    assert rows[1]["level"] == "warning"
    assert "ValueError" in rows[2]["exception"]
    assert "sk-proj" not in rows[2]["exception"]


def test_csv_header_written_once_across_reconfigure(tmp_path):
    for _ in range(2):
        configure_logging(stream=io.StringIO(), file_formats="csv", log_dir=tmp_path)
        get_logger("x").info("hello")
    lines = (tmp_path / "app.csv").read_text(encoding="utf-8").splitlines()
    assert lines.count(",".join(CSV_COLUMNS)) == 1
    assert len(lines) == 3


def test_redaction_can_be_disabled(tmp_path):
    buf = io.StringIO()
    configure_logging(stream=buf, redact_pii=False)
    get_logger("x").info("hi", email="tung@gmail.com")
    assert json.loads(buf.getvalue())["email"] == "tung@gmail.com"


def test_parse_file_formats():
    assert parse_file_formats("") == ()
    assert parse_file_formats(" log , CSV,log ") == ("log", "csv")
    with pytest.raises(ValueError):
        parse_file_formats("xml")
