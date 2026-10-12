"""Demo account module — the shared "Dùng thử ngay" vehicle-owner account.

One Firebase user (``demo-shared``) behind the login button, with VF3, VF8 and VF Wild
already linked. Everyone who presses the button signs in to the same account; it is
read-only where it matters (profile, vehicles, notification channels), never sends
email / SMS, and is wiped and re-seeded every ``DEMO_RESET_INTERVAL_HOURS``.
"""

from .errors import DemoAccountError, status_for

__all__ = ["DemoAccountError", "status_for"]
