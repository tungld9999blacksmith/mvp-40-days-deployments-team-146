"""
Typed Sorted Set — members of type T ordered by a float score.

Good for leaderboards, rankings, priority lists, time-ordered indexes (score = timestamp),
sliding-window rate limits, "top N" queries.

    board = toolkit.sorted_set("leaderboard:weekly", member_type=int)
    await board.incr(user_id, 10)
    top10 = await board.top(10)                 # [ScoredMember(member=7, score=120.0, rank=0), ...]
    me = await board.rank(user_id, reverse=True)

Members are serialized, so two members are "the same" only if their serialized bytes match:
use ids or small immutable models as members, not large mutable objects.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from redis.asyncio import Redis

from .serializers import Serializer, serializer_for

T = TypeVar("T")

Bound = float | str  # numbers, "-inf" / "+inf", or exclusive "(10"


@dataclass(frozen=True)
class ScoredMember(Generic[T]):
    member: T
    score: float
    rank: int | None = None


class SortedSet(Generic[T]):
    def __init__(
        self,
        redis: Redis,
        key: str,
        member_type: Any = str,
        *,
        serializer: Serializer[T] | None = None,
        ttl: float | None = None,
    ) -> None:
        """*ttl*: optional expiry (seconds) of the whole set, refreshed on every write."""
        self._redis = redis
        self.key = key
        self.ttl = ttl
        self.serializer: Serializer[T] = serializer or serializer_for(member_type)

    def _enc(self, member: T) -> bytes:
        return self.serializer.dumps(member)

    def _dec(self, raw: bytes) -> T:
        return self.serializer.loads(raw)

    async def _touch(self) -> None:
        if self.ttl:
            await self._redis.expire(self.key, int(self.ttl))

    def _scored(self, rows: list[tuple[bytes, float]], first_rank: int | None = None) -> list[ScoredMember[T]]:
        return [
            ScoredMember(self._dec(raw), float(score), None if first_rank is None else first_rank + i)
            for i, (raw, score) in enumerate(rows)
        ]

    # ------------------------------------------------------------------ write
    async def add(
        self,
        member: T,
        score: float,
        *,
        nx: bool = False,
        xx: bool = False,
        gt: bool = False,
        lt: bool = False,
    ) -> bool:
        """Add or update. nx: only add new; xx: only update existing; gt/lt: only if the new score is higher/lower."""
        changed = await self._redis.zadd(self.key, {self._enc(member): score}, nx=nx, xx=xx, gt=gt, lt=lt, ch=True)
        await self._touch()
        return bool(changed)

    async def add_many(self, members: Mapping[T, float] | Iterable[tuple[T, float]]) -> int:
        items = members.items() if isinstance(members, Mapping) else members
        mapping = {self._enc(m): s for m, s in items}
        if not mapping:
            return 0
        added = await self._redis.zadd(self.key, mapping)
        await self._touch()
        return int(added)

    async def incr(self, member: T, amount: float = 1.0) -> float:
        score = await self._redis.zincrby(self.key, amount, self._enc(member))
        await self._touch()
        return float(score)

    async def remove(self, *members: T) -> int:
        if not members:
            return 0
        return int(await self._redis.zrem(self.key, *(self._enc(m) for m in members)))

    async def remove_by_rank(self, start: int, stop: int) -> int:
        return int(await self._redis.zremrangebyrank(self.key, start, stop))

    async def remove_by_score(self, min_score: Bound, max_score: Bound) -> int:
        return int(await self._redis.zremrangebyscore(self.key, min_score, max_score))

    async def trim(self, keep: int, *, keep_highest: bool = True) -> int:
        """Keep only the *keep* highest (or lowest) scored members, e.g. a capped leaderboard."""
        if keep <= 0:
            return int(await self._redis.zremrangebyrank(self.key, 0, -1))
        if keep_highest:
            return int(await self._redis.zremrangebyrank(self.key, 0, -keep - 1))
        return int(await self._redis.zremrangebyrank(self.key, keep, -1))

    async def pop_min(self, count: int = 1) -> list[ScoredMember[T]]:
        return self._scored(await self._redis.zpopmin(self.key, count))

    async def pop_max(self, count: int = 1) -> list[ScoredMember[T]]:
        return self._scored(await self._redis.zpopmax(self.key, count))

    async def clear(self) -> None:
        await self._redis.delete(self.key)

    # ------------------------------------------------------------------- read
    async def score(self, member: T) -> float | None:
        value = await self._redis.zscore(self.key, self._enc(member))
        return None if value is None else float(value)

    async def scores(self, members: Iterable[T]) -> list[float | None]:
        encoded = [self._enc(m) for m in members]
        if not encoded:
            return []
        return [None if v is None else float(v) for v in await self._redis.zmscore(self.key, encoded)]

    async def rank(self, member: T, *, reverse: bool = False) -> int | None:
        """0-based position; reverse=True ranks highest score first (leaderboard order)."""
        encoded = self._enc(member)
        value = await (self._redis.zrevrank(self.key, encoded) if reverse else self._redis.zrank(self.key, encoded))
        return None if value is None else int(value)

    async def contains(self, member: T) -> bool:
        return await self.score(member) is not None

    async def size(self) -> int:
        return int(await self._redis.zcard(self.key))

    async def count(self, min_score: Bound = "-inf", max_score: Bound = "+inf") -> int:
        return int(await self._redis.zcount(self.key, min_score, max_score))

    async def range(self, start: int = 0, stop: int = -1, *, reverse: bool = False) -> list[ScoredMember[T]]:
        """Members by rank (inclusive *stop*), with scores and ranks."""
        rows = await self._redis.zrange(self.key, start, stop, desc=reverse, withscores=True)
        first = start if start >= 0 else max(0, await self.size() + start)
        return self._scored(rows, first_rank=first)

    async def top(self, n: int = 10) -> list[ScoredMember[T]]:
        """The *n* highest scores, best first."""
        return await self.range(0, n - 1, reverse=True)

    async def bottom(self, n: int = 10) -> list[ScoredMember[T]]:
        return await self.range(0, n - 1)

    async def range_by_score(
        self,
        min_score: Bound = "-inf",
        max_score: Bound = "+inf",
        *,
        reverse: bool = False,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[ScoredMember[T]]:
        """Members with min ≤ score ≤ max (use "(x" for exclusive bounds), optionally paginated."""
        if reverse:
            rows = await self._redis.zrevrangebyscore(
                self.key, max_score, min_score, start=offset, num=limit, withscores=True
            )
        else:
            rows = await self._redis.zrangebyscore(
                self.key, min_score, max_score, start=offset, num=limit, withscores=True
            )
        return self._scored(rows)

    async def around(self, member: T, radius: int = 2, *, reverse: bool = True) -> list[ScoredMember[T]]:
        """*member* and up to *radius* neighbours on each side ("you are #57, here are #55–#59")."""
        position = await self.rank(member, reverse=reverse)
        if position is None:
            return []
        start = max(0, position - radius)
        return await self.range(start, position + radius, reverse=reverse)

    async def scan(self, match: str | None = None, batch: int = 500) -> AsyncIterator[ScoredMember[T]]:
        """Iterate every member without blocking Redis (ZSCAN); order is not guaranteed."""
        async for raw, score in self._redis.zscan_iter(self.key, match=match, count=batch):
            yield ScoredMember(self._dec(raw), float(score))
