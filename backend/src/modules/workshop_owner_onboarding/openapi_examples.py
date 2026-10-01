"""Workshop-owner onboarding — Swagger request examples (API-203, API-204).

Rendered as the "Examples" dropdown in ``/docs``. Manager identities come from
the mock-ev-system seed (``mock-ev-system/src/mock_ev_system/seed.py``):

    SC-01  VinFast Thang Long  national id 001190000101  ha.tran.sc01@example.com
    SC-02  VinFast Quan 7      national id 079190000202  khoa.nguyen.sc02@example.com
    SC-03  VinFast Da Nang     national id 048190000303  lan.vo.sc03@example.com

The manufacturer matches the signed-in Firebase email against the manager
email. To test with a real Google account, start mock-ev-system with
``MOCK_SC01_MANAGER_EMAIL=<your gmail>`` (same for SC02 / SC03).
"""

from __future__ import annotations

from typing import Any

# Must be listed in ``settings.workshop_consent_policy_versions``.
_POLICY_VERSION = "WS-2026-09"

_CONSENT = {"granted": True, "policyVersion": _POLICY_VERSION}


def _week(open_time: str, close_time: str, *, sunday_closed: bool) -> list[dict[str, Any]]:
    """Seven ``operatingHours`` entries (ISO day 1 = Monday .. 7 = Sunday)."""
    days = []
    for day in range(1, 8):
        closed = sunday_closed and day == 7
        days.append(
            {
                "dayOfWeek": day,
                "isClosed": closed,
                "openTime": None if closed else open_time,
                "closeTime": None if closed else close_time,
            }
        )
    return days


PROFILE_UPDATE_EXAMPLES: dict[str, dict[str, Any]] = {
    "manager_sc01": {
        "summary": "Valid: manager of SC-01 (Ha Noi)",
        "value": {
            "fullName": "Tran Thu Ha",
            "phoneNumber": "0912345601",
            "nationalId": "001190000101",
            "personalDataConsent": _CONSENT,
        },
    },
    "manager_sc02": {
        "summary": "Valid: manager of SC-02 (TP. Ho Chi Minh)",
        "value": {
            "fullName": "Nguyen Dang Khoa",
            "phoneNumber": "0912345602",
            "nationalId": "079190000202",
            "personalDataConsent": _CONSENT,
        },
    },
    "manager_sc03": {
        "summary": "Valid: manager of SC-03 (Da Nang)",
        "value": {
            "fullName": "Vo Thi Lan",
            "phoneNumber": "0912345603",
            "nationalId": "048190000303",
            "personalDataConsent": _CONSENT,
        },
    },
    "invalid_national_id": {
        "summary": "Error: national id (CCCD) is not 12 digits",
        "value": {
            "fullName": "Tran Thu Ha",
            "phoneNumber": "0912345601",
            "nationalId": "00119000010A",
            "personalDataConsent": _CONSENT,
        },
    },
    "unknown_policy_version": {
        "summary": "Error: consent given for an unknown policy version",
        "value": {
            "fullName": "Tran Thu Ha",
            "phoneNumber": "0912345601",
            "nationalId": "001190000101",
            "personalDataConsent": {"granted": True, "policyVersion": "WS-2020-01"},
        },
    },
}

WORKSHOP_VERIFICATION_EXAMPLES: dict[str, dict[str, Any]] = {
    "sc01_mon_sat": {
        "summary": "Valid: SC-01, open Mon-Sat 08:00-17:30",
        "value": {
            "address": "Lo C1, Khu do thi Thang Long, Hoai Duc, Ha Noi",
            "latitude": 21.0285,
            "longitude": 105.8542,
            "hotline": "02438123456",
            "totalTechnicians": 12,
            "emergencySlotsReserved": 2,
            "operatingHours": _week("08:00", "17:30", sunday_closed=True),
            "oemDataSharingConsent": _CONSENT,
        },
    },
    "sc02_all_week": {
        "summary": "Valid: SC-02, open every day, 1900 hotline, no coordinates",
        "value": {
            "address": "1060 Nguyen Van Linh, Tan Phong, Quan 7, TP. Ho Chi Minh",
            "hotline": "19002345",
            "totalTechnicians": 20,
            "emergencySlotsReserved": 4,
            "operatingHours": _week("07:30", "20:00", sunday_closed=False),
            "oemDataSharingConsent": _CONSENT,
        },
    },
    "too_many_emergency_slots": {
        "summary": "Error: emergency slots exceed total technicians",
        "value": {
            "address": "Lo C1, Khu do thi Thang Long, Hoai Duc, Ha Noi",
            "hotline": "02438123456",
            "totalTechnicians": 3,
            "emergencySlotsReserved": 5,
            "operatingHours": _week("08:00", "17:30", sunday_closed=True),
            "oemDataSharingConsent": _CONSENT,
        },
    },
    "missing_days": {
        "summary": "Error: operating hours do not cover all 7 days",
        "value": {
            "address": "Lo C1, Khu do thi Thang Long, Hoai Duc, Ha Noi",
            "hotline": "02438123456",
            "totalTechnicians": 12,
            "operatingHours": _week("08:00", "17:30", sunday_closed=True)[:5],
            "oemDataSharingConsent": _CONSENT,
        },
    },
    "close_before_open": {
        "summary": "Error: closing time is before opening time",
        "value": {
            "address": "Lo C1, Khu do thi Thang Long, Hoai Duc, Ha Noi",
            "hotline": "02438123456",
            "totalTechnicians": 12,
            "operatingHours": _week("18:00", "08:00", sunday_closed=True),
            "oemDataSharingConsent": _CONSENT,
        },
    },
}

IDEMPOTENCY_KEY_EXAMPLES: dict[str, dict[str, Any]] = {
    "uuid": {
        "summary": "Any unique value — change it for every new submission",
        "value": "8b2d4e61-0f3a-4c7e-a1d9-5c6b7e8f9a20",
    },
}
