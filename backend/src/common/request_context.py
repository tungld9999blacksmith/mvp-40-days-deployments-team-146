"""Request metadata recorded on audit events (IP, user agent, trace id)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    ip_address: str | None = None
    user_agent: str | None = None
    trace_id: str | None = None
    auth_provider: str = "google.com"

    def clipped(self) -> RequestContext:
        """Trim values to the audit column sizes."""
        return RequestContext(
            ip_address=self.ip_address[:64] if self.ip_address else None,
            user_agent=self.user_agent[:512] if self.user_agent else None,
            trace_id=self.trace_id[:64] if self.trace_id else None,
            auth_provider=(self.auth_provider or "google.com")[:32],
        )
