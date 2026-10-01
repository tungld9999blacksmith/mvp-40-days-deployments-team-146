"""Onboarding module — Swagger request examples (API-003, API-005).

Rendered as the "Examples" dropdown in ``/docs``. Values are aligned with the
mock-ev-system seed (``mock-ev-system/src/mock_ev_system/seed.py``) so the
happy-path examples verify successfully against the local mock:

    OWN-001  national id 079200001001  email an.nguyen@example.com
      VEH-001  VIN VF5PLUS2024000001  plate 30A-12345  model MDL-01 (VF5 Plus)
      VEH-002  VIN VF8ECO20230000001  plate 30A-67890  model MDL-05 (VF8 Eco)

The manufacturer also matches the signed-in user's email, so ownership only
verifies when the Firebase account email equals the seed owner's email.
"""

from __future__ import annotations

from typing import Any

# Must match ``settings.consent_policy_version``.
_POLICY_VERSION = "2026-09"

_CONSENT = {"granted": True, "policyVersion": _POLICY_VERSION}

PROFILE_UPDATE_EXAMPLES: dict[str, dict[str, Any]] = {
    "manual_address": {
        "summary": "Valid: manual address (seed owner OWN-001)",
        "description": (
            "National id matches mock owner OWN-001, so the later vehicle "
            "verification can succeed."
        ),
        "value": {
            "fullName": "Nguyen Van An",
            "phoneNumber": "0901000001",
            "nationalId": "079200001001",
            "dateOfBirth": "1990-05-20",
            "location": {
                "addressLine": "12 Ly Thai To",
                "ward": "Hang Trong",
                "district": "Hoan Kiem",
                "province": "Ha Noi",
                "source": "MANUAL",
            },
            "personalDataConsent": _CONSENT,
        },
    },
    "map_pick": {
        "summary": "Valid: location picked on the map (with coordinates)",
        "value": {
            "fullName": "Nguyen Van An",
            "phoneNumber": "+84901000001",
            "nationalId": "079200001001",
            "location": {
                "addressLine": "72 Le Thanh Ton, Ben Nghe",
                "ward": "Ben Nghe",
                "district": "Quan 1",
                "province": "TP. Ho Chi Minh",
                "latitude": 10.7769,
                "longitude": 106.7009,
                "source": "MAP_PICK",
                "placeId": "ChIJ0T2NLikpdTERKxE8d61aX_E",
            },
            "personalDataConsent": _CONSENT,
        },
    },
    "invalid_phone": {
        "summary": "Error: invalid phone number",
        "value": {
            "fullName": "Nguyen Van An",
            "phoneNumber": "0123456789",
            "nationalId": "079200001001",
            "location": {
                "addressLine": "12 Ly Thai To",
                "province": "Ha Noi",
                "source": "MANUAL",
            },
            "personalDataConsent": _CONSENT,
        },
    },
    "consent_declined": {
        "summary": "Error: personal data consent not granted",
        "value": {
            "fullName": "Nguyen Van An",
            "phoneNumber": "0901000001",
            "nationalId": "079200001001",
            "location": {
                "addressLine": "12 Ly Thai To",
                "province": "Ha Noi",
                "source": "MANUAL",
            },
            "personalDataConsent": {"granted": False, "policyVersion": _POLICY_VERSION},
        },
    },
}

VEHICLE_VERIFICATION_EXAMPLES: dict[str, dict[str, Any]] = {
    "verified_vf5": {
        "summary": "Valid: VF5 Plus of OWN-001 (VEH-001)",
        "description": "Verifies when signed in as an.nguyen@example.com.",
        "value": {
            "vin": "VF5PLUS2024000001",
            "licensePlate": "30A-12345",
            "modelId": "MDL-01",
            "manufactureYear": 2024,
            "oemDataSharingConsent": _CONSENT,
        },
    },
    "verified_vf8": {
        "summary": "Valid: VF8 Eco of OWN-001 (VEH-002)",
        "value": {
            "vin": "VF8ECO20230000001",
            "licensePlate": "30A-67890",
            "modelId": "MDL-05",
            "manufactureYear": 2023,
            "oemDataSharingConsent": _CONSENT,
        },
    },
    "vin_not_found": {
        "summary": "Fail: VIN unknown to the manufacturer",
        "value": {
            "vin": "VF5PLUS2024999999",
            "licensePlate": "30A-12345",
            "modelId": "MDL-01",
            "oemDataSharingConsent": _CONSENT,
        },
    },
    "plate_mismatch": {
        "summary": "Fail: plate does not match the VIN",
        "value": {
            "vin": "VF5PLUS2024000001",
            "licensePlate": "30A-99999",
            "modelId": "MDL-01",
            "oemDataSharingConsent": _CONSENT,
        },
    },
    "model_mismatch": {
        "summary": "Fail: declared model does not match the VIN",
        "value": {
            "vin": "VF5PLUS2024000001",
            "licensePlate": "30A-12345",
            "modelId": "MDL-07",
            "oemDataSharingConsent": _CONSENT,
        },
    },
    "invalid_vin_format": {
        "summary": "Error: VIN is not 17 alphanumeric characters",
        "value": {
            "vin": "VF5-123",
            "licensePlate": "30A-12345",
            "modelId": "MDL-01",
            "oemDataSharingConsent": _CONSENT,
        },
    },
}

IDEMPOTENCY_KEY_EXAMPLES: dict[str, dict[str, Any]] = {
    "uuid": {
        "summary": "Any unique value — change it for every new submission",
        "value": "3f0c9a52-6d1e-4b8a-9c7f-2e5b1d0a4c11",
    },
}
