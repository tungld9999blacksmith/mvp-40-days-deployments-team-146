"""Send exactly one explicitly requested test email; never retries an existing receipt.

Uses the configured real transport, without creating business reminders or bookings.
An accepted message is not proof of inbox delivery. No credentials are exported.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from src.config import get_settings  # noqa: E402
from src.modules.notification.channels import NotificationMessage  # noqa: E402
from src.modules.notification.email_transport import ResendEmailTransport, address_hash  # noqa: E402


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registry = ROOT / "data/verification/driving-habit/provider-receipts" / f"{address_hash(args.recipient)}.json"
    if args.output.exists() or registry.exists():
        print("Receipt already exists; no email attempted.")
        return
    cfg = get_settings()
    if cfg.email_mode != "resend" or not cfg.resend_api_key or not cfg.email_from:
        raise SystemExit("Real Resend configuration is incomplete; no email attempted.")
    report = {
        "checkedAt": datetime.now(UTC).isoformat(),
        "status": "attempt_in_progress",
        "recipientHash": address_hash(args.recipient),
        "testMessageOnly": True,
        "providerSendCalls": 1,
        "businessRemindersCreated": 0,
        "automaticRetries": 0,
        "accepted": False,
        "inboxDeliveryVerified": False,
    }
    # Recipient receipt survives report consolidation or a different output path.
    # Exclusive reservation also prevents two processes from sending this test.
    registry.parent.mkdir(parents=True, exist_ok=True)
    try:
        with registry.open("x", encoding="utf-8") as receipt:
            receipt.write(json.dumps(report, indent=2) + "\n")
    except FileExistsError:
        print("Receipt already exists; no email attempted.")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.resolve() != registry.resolve():
        with args.output.open("x", encoding="utf-8") as receipt:
            receipt.write(json.dumps(report, indent=2) + "\n")

    class ObservedClient(httpx.AsyncClient):
        async def post(self, *args, **kwargs):
            response = await super().post(*args, **kwargs)
            report["httpStatus"] = response.status_code
            return response

    result = await ResendEmailTransport(cfg.resend_api_key, client_factory=ObservedClient).send(
        args.recipient,
        NotificationMessage(
            subject="[TEST EV Care] Kiểm tra giao nhận nhắc bảo dưỡng",
            body="Đây là email kiểm tra kết nối theo yêu cầu của bạn. Không phải thông báo đến hạn của một xe và không tạo lịch hẹn.",
            kind="MAINTENANCE_REMINDER",
            delivery_id=str(uuid4()),
            sender=cfg.email_from,
        ),
    )
    report.update(
        status=result.status.value,
        errorCode=result.error_code,
        providerMessageId=result.provider_message_id,
        accepted=result.provider_message_id is not None,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    registry.write_text(rendered, encoding="utf-8")
    args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
