from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..serializers import Serializer


@dataclass(frozen=True)
class CacheOptions:
    """
    Per-call cache options. Any field left at its default falls back to the facade's defaults
    (see `CacheFacade(default_options=...)`); override per call / per decorator with kwargs.

    Attributes:
        ttl: seconds to keep an entry. None -> facade default; 0 -> never expire.
        serializer: value <-> bytes codec. None -> JSON (or inferred from the return type in decorators).
        namespace: extra key segment, e.g. "vehicle" -> <prefix>:cache:vehicle:<key>.
        ttl_jitter: random extra TTL as a fraction (0.1 = up to +10%) so keys written together
            don't all expire together (cache avalanche).
        cache_none: cache "not found" results too (short `none_ttl`) so repeated lookups of
            missing rows don't all hit the database (cache penetration).
        none_ttl: TTL in seconds for cached "not found" results.
        stampede_lock: on a miss, let only one caller cluster-wide load the value while the
            others wait for it (hot-key stampede / cache breakdown protection).
        stampede_lock_ttl / stampede_wait: lifetime of that lock, and how long other callers
            wait before giving up and loading themselves.
        tags: tags attached to written entries; `invalidate_tags("vehicles")` drops them all.
        write_back_queue: which write-back buffer (registered writer) a write-back write goes to.
        cache_if: predicate on a loaded/written value; entries it rejects are not cached
            (e.g. `cache_if=lambda rows: len(rows) < 1000`).
        cache_writer_result: write-through only — cache what the writer returned (e.g. the row
            with DB-generated fields) instead of the value passed in.
        double_delete_delay: cache-aside only — delete the key again this many seconds after the
            write, closing the race where a concurrent read re-caches the old value.
    """

    ttl: float | None = None
    serializer: Serializer[Any] | None = None
    namespace: str | None = None
    ttl_jitter: float = 0.0
    cache_none: bool = True
    none_ttl: float = 60.0
    stampede_lock: bool = False
    stampede_lock_ttl: float = 10.0
    stampede_wait: float = 5.0
    tags: tuple[str, ...] = field(default_factory=tuple)
    write_back_queue: str = "default"
    cache_if: Callable[[Any], bool] | None = None
    cache_writer_result: bool = False
    double_delete_delay: float | None = None

    def merge(self, **overrides: Any) -> CacheOptions:
        """Copy with the non-None overrides applied (unknown names raise TypeError)."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        if "tags" in clean:
            clean["tags"] = tuple(clean["tags"])
        return dataclasses.replace(self, **clean)
