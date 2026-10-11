"""Move to the next configured OpenRouter endpoint after an HTTP 429."""

import logging
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)


def next_endpoint_kwargs(kwargs: dict[str, Any]) -> dict[str, Any] | None:
    """Preserve request constraints and exclude the endpoint just attempted.

    OpenRouter also performs server-side fallback. A client retry is bounded by
    the explicit order, and never relaxes caller-supplied provider restrictions.
    """
    body = kwargs.get("extra_body") or {}
    routing = body.get("provider") or {}
    order = routing.get("order") or []
    if len(order) < 2 or routing.get("allow_fallbacks") is False:
        return None
    retry = deepcopy(kwargs)
    routing = retry["extra_body"]["provider"]
    failed, *remaining = order
    routing["order"] = remaining
    routing["ignore"] = list(dict.fromkeys([*(routing.get("ignore") or []), failed]))
    logger.info("openrouter_endpoint_rate_limited switching_from=%s switching_to=%s", failed, remaining[0])
    return retry
