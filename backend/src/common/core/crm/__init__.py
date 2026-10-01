"""CRM domain: AI customer profile and post-service care."""

from .customer_profile_cdp import CustomerProfileCDP, CustomerProfileCDPRepository
from .follow_up import FOLLOW_UP_DELAY, FollowUp, FollowUpRepository, FollowUpStatus
from .support_ticket import (
    SupportTicket,
    SupportTicketPriority,
    SupportTicketRepository,
    SupportTicketStatus,
)

__all__ = [
    "CustomerProfileCDP",
    "CustomerProfileCDPRepository",
    "FOLLOW_UP_DELAY",
    "FollowUp",
    "FollowUpRepository",
    "FollowUpStatus",
    "SupportTicket",
    "SupportTicketPriority",
    "SupportTicketRepository",
    "SupportTicketStatus",
]
