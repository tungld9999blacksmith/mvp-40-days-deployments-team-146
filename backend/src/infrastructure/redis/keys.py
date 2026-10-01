from __future__ import annotations

from typing import Any

SEPARATOR = ":"


class KeyBuilder:
    """
    Builds namespaced Redis keys: `KeyBuilder("p146").build("cache", "vehicle", 42)` -> "p146:cache:vehicle:42".

    Every structure in this package goes through a KeyBuilder, so all keys of one app
    share a prefix (easy to SCAN, flush in tests, or split per environment).
    """

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix.strip(SEPARATOR)

    def build(self, *parts: Any) -> str:
        cleaned = [str(p).strip(SEPARATOR) for p in parts if p is not None and str(p) != ""]
        if self.prefix:
            cleaned.insert(0, self.prefix)
        return SEPARATOR.join(cleaned)

    def child(self, *parts: Any) -> KeyBuilder:
        """A KeyBuilder whose prefix is this one's prefix + *parts*."""
        return KeyBuilder(self.build(*parts))
