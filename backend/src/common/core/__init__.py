"""Core entity models, grouped by domain as in ``docs/specs/entity/``.

Importing this package registers every core table on ``SQLModel.metadata``
(used by Alembic and by foreign keys that point across domains).
"""

from . import (
    conversation,
    crm,
    identity,
    knowledge,
    maintenance,
    notification,
    vehicle,
    workshop,
)

__all__ = [
    "conversation",
    "crm",
    "identity",
    "knowledge",
    "maintenance",
    "notification",
    "vehicle",
    "workshop",
]
