"""Probe the local demo API; --send permits one new [DEMO] email to DEMO_EMAIL_TEST_TO.

Firebase identity and vehicle/profile are synthetic. No service-account credentials,
tokens, email addresses or API keys are printed or exported to the report.
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send",
        action="store_true",
        help="Explicitly request at most one new real test email",
    )
    args = parser.parse_args()
    output = ROOT / ".cache" / "demo-resend-test-20261007" / "live-report.json"
    report = {
        "testedAt": datetime.now(UTC).isoformat(),
        "sendRequested": args.send,
        "inboxReceiptConfirmed": False,
    }
    token = None

    def api(client, path, method="GET", body=None):
        response = client.request(
            method,
            f"http://127.0.0.1:8000/api/v1{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": str(uuid4()),
            },
            **({"json": body} if body is not None else {}),
        )
        payload = response.json()
        if not response.is_success:
            code = payload.get("error", {}).get("code", "UNKNOWN")
            raise RuntimeError(f"Demo API {path}: HTTP {response.status_code} ({code})")
        return payload["data"]

    try:
        with httpx.Client(timeout=25, trust_env=False) as client:
            health = client.get("http://127.0.0.1:8000/health").json()
            if health.get("mode") != "demo" or health.get("emailMode") != "resend_test":
                raise RuntimeError(
                    "Refuse to probe anything except the local resend_test demo"
                )
            report.update(
                backend="src.demo.main:app",
                auth="Firebase Auth Emulator",
                emailMode="resend_test",
            )
            if not args.send:
                report["status"] = "ready; no email requested"
                return
            values = dotenv_values(ROOT / ".env")
            recipient = (values.get("DEMO_EMAIL_TEST_TO") or "").strip()
            if not recipient:
                raise RuntimeError("DEMO_EMAIL_TEST_TO is missing")
            identity = json.dumps(
                {
                    "sub": "demo-resend-test-"
                    + hashlib.sha256(recipient.casefold().encode()).hexdigest()[:16],
                    "email": recipient,
                    "email_verified": True,
                    "name": "Chủ xe demo Resend",
                }
            )
            signed_in = client.post(
                "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=demo-api-key",
                json={
                    "postBody": urlencode(
                        {"id_token": identity, "providerId": "google.com"}
                    ),
                    "requestUri": "http://127.0.0.1:5173",
                    "returnSecureToken": True,
                },
            )
            if not signed_in.is_success:
                raise RuntimeError(f"Auth Emulator: HTTP {signed_in.status_code}")
            token = signed_in.json()["idToken"]
            onboarding = api(client, "/onboarding")
            if onboarding["onboarding"]["status"] != "ACTIVE":
                if not onboarding["onboarding"]["profileCompleted"]:
                    api(
                        client,
                        "/onboarding/profile",
                        "PUT",
                        {
                            "fullName": "Chủ xe demo Resend",
                            "phoneNumber": "0901234567",
                            "nationalId": "000000001234",
                            "dateOfBirth": None,
                            "location": {
                                "addressLine": "123 Đường Demo",
                                "province": "Hà Nội",
                                "source": "MANUAL",
                            },
                            "personalDataConsent": {
                                "granted": True,
                                "policyVersion": "2026-09",
                            },
                        },
                    )
                api(
                    client,
                    "/onboarding/vehicle-verification",
                    "POST",
                    {
                        "vin": "VF6ECO20240000001",
                        "licensePlate": "51A-11111",
                        "modelId": "MDL-02",
                        "manufactureYear": 2024,
                        "oemDataSharingConsent": {
                            "granted": True,
                            "policyVersion": "2026-09",
                        },
                    },
                )
            settings = api(client, "/notification-settings")
            if not settings.get("emailTestRecipientMatched"):
                raise RuntimeError(
                    "Demo recipient does not match the server-configured test mailbox"
                )
            api(
                client,
                "/notification-settings",
                "PUT",
                {
                    "remindersEnabled": True,
                    "channels": [{"channel": "EMAIL", "enabled": True}],
                },
            )
            before = api(client, "/notifications/email-outbox")["items"]
            api(client, "/demo/email-test/send", "POST", {})
            after = api(client, "/notifications/email-outbox")["items"]
            if not after:
                raise RuntimeError(
                    "No email created: check reminder eligibility, booking and cooldown"
                )
            delivery = after[0]
            report.update(
                {
                    key: delivery.get(key)
                    for key in (
                        "status",
                        "deliveryState",
                        "attempts",
                        "errorCode",
                    )
                }
            )
            report["deliveryId"] = delivery["id"]
            report["newDeliveries"] = len(after) - len(before)
            if delivery["status"] != "SENT":
                raise RuntimeError(
                    f"Resend test was not accepted ({delivery.get('errorCode')})"
                )
            # Only repeat after success: this tests dedup without retrying an uncertain provider result.
            api(client, "/demo/email-test/send", "POST", {})
            replay = api(client, "/notifications/email-outbox")["items"]
            if (
                len(replay) != len(after)
                or replay[0]["attempts"] != delivery["attempts"]
            ):
                raise RuntimeError("Duplicate click changed delivery count/attempts")
            report["repeatClickDeduplicated"] = True
    except Exception as exc:  # noqa: BLE001 -- report failures without exposing network credentials
        # Do not serialize provider/network exceptions: they can include token/recipient values.
        report["failure"] = (
            str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        )
        raise SystemExit(1) from None
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
