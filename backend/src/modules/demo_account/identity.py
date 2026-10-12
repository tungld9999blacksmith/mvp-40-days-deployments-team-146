"""Who the demo account is (no I/O, safe to import from any module)."""

from __future__ import annotations

DEMO_UID = "demo-shared"
DEMO_CLAIM = "demo"
DEMO_NATIONAL_ID = "079299990001"  # mock-ev-system demo_account.NATIONAL_ID


def is_demo_claims(claims: dict) -> bool:
    """A custom-token session of the demo uid minted by this backend (the claim cannot be forged)."""
    provider = (claims.get("firebase") or {}).get("sign_in_provider")
    return provider == "custom" and claims.get("uid") == DEMO_UID and claims.get(DEMO_CLAIM) is True
