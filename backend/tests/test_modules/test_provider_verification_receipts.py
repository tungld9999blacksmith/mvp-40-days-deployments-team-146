import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from scripts import verify_reminder_provider as probe
from src.modules.notification.channels import DeliveryResult
from src.modules.notification.email_transport import address_hash


def arguments(monkeypatch, recipient, output):
    monkeypatch.setattr(sys, "argv", ["probe", "--recipient", recipient, "--output", str(output)])


@pytest.mark.asyncio
async def test_archived_recipient_receipt_blocks_different_output(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    recipient = "fixture@example.com"
    registry = tmp_path / "data/verification/driving-habit/provider-receipts" / f"{address_hash(recipient)}.json"
    registry.parent.mkdir(parents=True)
    registry.write_text('{"accepted": true}', encoding="utf-8")
    cfg = Mock(side_effect=AssertionError("Receipt must block before settings or transport"))
    monkeypatch.setattr(probe, "get_settings", cfg)
    output = tmp_path / "different-output.json"
    arguments(monkeypatch, recipient, output)
    await probe.main()
    cfg.assert_not_called()
    assert not output.exists()


@pytest.mark.asyncio
async def test_existing_output_still_blocks_test_email(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    output = tmp_path / "old-receipt.json"
    output.write_text("{}", encoding="utf-8")
    cfg = Mock(side_effect=AssertionError("No real configuration needed"))
    monkeypatch.setattr(probe, "get_settings", cfg)
    arguments(monkeypatch, "fixture@example.com", output)
    await probe.main()
    cfg.assert_not_called()


@pytest.mark.asyncio
async def test_mocked_send_reserves_recipient_and_prevents_replay(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    monkeypatch.setattr(
        probe,
        "get_settings",
        lambda: SimpleNamespace(email_mode="resend", resend_api_key="fixture", email_from="fixture@example.com"),
    )
    transport = SimpleNamespace(send=AsyncMock(return_value=DeliveryResult.sent("fixture-message")))
    monkeypatch.setattr(probe, "ResendEmailTransport", lambda *args, **kwargs: transport)
    recipient = "recipient@example.com"
    output = tmp_path / "nested/output.json"
    arguments(monkeypatch, recipient, output)
    await probe.main()
    registry = tmp_path / "data/verification/driving-habit/provider-receipts" / f"{address_hash(recipient)}.json"
    assert json.loads(registry.read_text(encoding="utf-8")) == json.loads(output.read_text(encoding="utf-8"))
    assert json.loads(output.read_text(encoding="utf-8"))["accepted"]
    arguments(monkeypatch, recipient, tmp_path / "replay.json")
    await probe.main()
    transport.send.assert_awaited_once()
    assert not (tmp_path / "replay.json").exists()
