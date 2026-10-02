"""Metadata policy + builder for vector records (ENT-423 §6, BR-ENT-474).

A ``VectorRecord``'s ``metadata`` is never assembled ad-hoc from a source row.
Every record goes through ``VectorRecordBuilder``, which applies a per-collection
``VectorMetadataPolicy``:

- system keys (``source``, ``sourceCreatedAt``) and the collection's filter keys
  (e.g. ``conversationId``, ``role``) are set at top level *from the source row* —
  so the source can never overwrite the authz filter keys (the ``{**meta}``
  spread bug), and
- the source's own metadata is masked/whitelisted into a single nested
  ``sourceMeta`` field, so citations / tool args / PII never leak into the store.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .base import VectorRecord

if TYPE_CHECKING:  # avoid a hard import cycle with the conversation domain
    from src.common.core.conversation import ChatMessage

# Collection names (logical namespaces in ``vector_embedding``).
CONVERSATION_MESSAGES = "conversation_messages"

# PII masking — VIN, Vietnamese phone, email, national id (CCCD). Kept simple on
# purpose (Q-607); tighten later without touching call sites.
_PII_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"), "[VIN]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?84|0)\d{9}(?!\d)"), "[PHONE]"),
    (re.compile(r"(?<!\d)\d{12}(?!\d)"), "[ID]"),
)


def mask_pii(value: str) -> str:
    """Replace VIN / email / phone / national-id patterns in free text."""
    for pattern, repl in _PII_PATTERNS:
        value = pattern.sub(repl, value)
    return value


def _mask_value(value: Any, *, mask: bool) -> Any:
    if not mask:
        return value
    if isinstance(value, str):
        return mask_pii(value)
    if isinstance(value, Mapping):
        return {k: _mask_value(v, mask=mask) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_value(v, mask=mask) for v in value]
    return value


@dataclass(frozen=True)
class VectorMetadataPolicy:
    """What a collection is allowed to store, and how it is de-identified."""

    source: str
    # Keys copied to top-level metadata straight from the source row (filters).
    filter_keys: tuple[str, ...] = ()
    # Whitelist of source-meta keys kept inside the nested ``sourceMeta``.
    keep_source_meta: tuple[str, ...] = ()
    mask: bool = True


# One policy per collection. ``conversation_messages`` keeps NO source meta by
# default (Q-604 default-off design): citations / tool_calls carry the most leak
# risk and are not needed for semantic recall.
_POLICIES: dict[str, VectorMetadataPolicy] = {
    CONVERSATION_MESSAGES: VectorMetadataPolicy(
        source="conversation_message",
        filter_keys=("conversationId", "role"),
        keep_source_meta=(),
        mask=True,
    ),
}


def policy_for(collection: str) -> VectorMetadataPolicy:
    """Policy for *collection*; a strict default (mask, no source meta) if unset."""
    return _POLICIES.get(collection, VectorMetadataPolicy(source=collection, mask=True))


@dataclass
class VectorRecordBuilder:
    """The single place that constructs ``VectorRecord`` metadata (BR-ENT-474)."""

    @staticmethod
    def _base_metadata(
        policy: VectorMetadataPolicy,
        *,
        source_created_at: str,
        filters: Mapping[str, Any],
        source_meta: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        kept: dict[str, Any] = {}
        if source_meta and policy.keep_source_meta:
            for key in policy.keep_source_meta:
                if key in source_meta:
                    kept[key] = _mask_value(source_meta[key], mask=policy.mask)
        # System keys set last is fine: they are our own literals, and filters
        # come from the source row, never from source_meta — so nothing here can
        # overwrite the authz filter keys.
        return {
            "source": policy.source,
            "sourceCreatedAt": source_created_at,
            **{k: filters[k] for k in policy.filter_keys if k in filters},
            "sourceMeta": kept,
        }

    @classmethod
    def from_message(cls, message: ChatMessage, policy: VectorMetadataPolicy | None = None) -> VectorRecord:
        policy = policy or policy_for(CONVERSATION_MESSAGES)
        content = mask_pii(message.content) if policy.mask else message.content
        metadata = cls._base_metadata(
            policy,
            source_created_at=message.created_at.isoformat(),
            filters={
                "conversationId": str(message.conversation_id),
                "role": message.role.value,
            },
            source_meta=None,
        )
        return VectorRecord(id=str(message.id), content=content, metadata=metadata)
