"""Token prices for cost estimates (``model_prices.json``, USD per 1M tokens)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PRICES_FILE = Path(__file__).with_name("model_prices.json")


@lru_cache(maxsize=1)
def _prices() -> dict[str, tuple[float, float]]:
    raw = json.loads(PRICES_FILE.read_text(encoding="utf-8"))
    return {
        model.lower(): (float(entry["input_per_1m"]), float(entry["output_per_1m"]))
        for model, entry in raw.items()
        if not model.startswith("_")
    }


def _lookup(model: str) -> tuple[float, float] | None:
    prices = _prices()
    key = model.lower()
    # "google/gemini-x" -> "gemini-x" when only the bare id is listed.
    return prices.get(key) or prices.get(key.rsplit("/", 1)[-1])


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """USD for one call, or ``None`` when the model has no listed price."""
    price = _lookup(model)
    if price is None:
        return None
    return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000
