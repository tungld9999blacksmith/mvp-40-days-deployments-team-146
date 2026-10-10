"""External notification channel adapters (us-021 BR-506).

Email is ``email_service.MaintenanceEmailAdapter`` (Resend); this package holds SMS.
"""

from .sms import EsmsConfig, EsmsSmsAdapter

__all__ = ["EsmsConfig", "EsmsSmsAdapter"]
