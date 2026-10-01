import asyncio

import pytest
from pydantic import BaseModel

from src.infrastructure.redis import CacheError, RedisToolkit

pytestmark = pytest.mark.asyncio


class Vehicle(BaseModel):
    id: int
    plate: str


class FakeRepo:
    """Stands in for a Supabase repository; counts DB hits."""

    def __init__(self) -> None:
        self.rows: dict[int, Vehicle] = {1: Vehicle(id=1, plate="29A-001")}
        self.reads = 0
        self.writes = 0

    async def get(self, vehicle_id: int) -> Vehicle | None:
        self.reads += 1
        return self.rows.get(vehicle_id)

    async def save(self, vehicle: Vehicle) -> Vehicle:
        self.writes += 1
        self.rows[vehicle.id] = vehicle
        return vehicle


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo()


# ------------------------------------------------------------------ decorators
async def test_cached_decorator_hits_db_once_and_returns_typed_model(toolkit: RedisToolkit, repo: FakeRepo):
    @toolkit.cache.cached("vehicle:{vehicle_id}", ttl=30)
    async def get_vehicle(vehicle_id: int) -> Vehicle | None:
        return await repo.get(vehicle_id)

    first = await get_vehicle(1)
    second = await get_vehicle(vehicle_id=1)

    assert first == second == Vehicle(id=1, plate="29A-001")
    assert isinstance(second, Vehicle)
    assert repo.reads == 1
    assert get_vehicle.key_for(1) == "vehicle:1"


async def test_cached_decorator_caches_not_found(toolkit: RedisToolkit, repo: FakeRepo):
    @toolkit.cache.cached("vehicle:{vehicle_id}")
    async def get_vehicle(vehicle_id: int) -> Vehicle | None:
        return await repo.get(vehicle_id)

    assert await get_vehicle(999) is None
    assert await get_vehicle(999) is None
    assert repo.reads == 1


async def test_cached_decorator_cache_none_false_and_cache_if(toolkit: RedisToolkit, repo: FakeRepo):
    @toolkit.cache.cached("vehicle:{vehicle_id}", cache_none=False)
    async def get_vehicle(vehicle_id: int) -> Vehicle | None:
        return await repo.get(vehicle_id)

    @toolkit.cache.cached("plates", cache_if=lambda rows: len(rows) > 5)
    async def list_plates() -> list[str]:
        repo.reads += 1
        return ["a"]

    await get_vehicle(999)
    await get_vehicle(999)
    await list_plates()
    await list_plates()
    assert repo.reads == 4


async def test_cached_invalidate_and_refresh_helpers(toolkit: RedisToolkit, repo: FakeRepo):
    @toolkit.cache.cached("vehicle:{vehicle_id}")
    async def get_vehicle(vehicle_id: int) -> Vehicle | None:
        return await repo.get(vehicle_id)

    await get_vehicle(1)
    repo.rows[1] = Vehicle(id=1, plate="NEW")
    assert (await get_vehicle(1)).plate == "29A-001"

    await get_vehicle.invalidate(1)
    assert (await get_vehicle(1)).plate == "NEW"

    repo.rows[1] = Vehicle(id=1, plate="NEWER")
    assert (await get_vehicle.refresh(1)).plate == "NEWER"
    assert (await get_vehicle(1)).plate == "NEWER"


async def test_cached_condition_bypasses_cache(toolkit: RedisToolkit, repo: FakeRepo):
    @toolkit.cache.cached("vehicle:{vehicle_id}", condition=lambda vehicle_id, fresh=False: not fresh)
    async def get_vehicle(vehicle_id: int, fresh: bool = False) -> Vehicle | None:
        return await repo.get(vehicle_id)

    await get_vehicle(1)
    await get_vehicle(1, fresh=True)
    await get_vehicle(1)
    assert repo.reads == 2


async def test_cached_on_method_and_auto_key(toolkit: RedisToolkit, repo: FakeRepo):
    class Service:
        @toolkit.cache.cached(namespace="svc")
        async def find(self, vehicle_id: int) -> Vehicle | None:
            return await repo.get(vehicle_id)

    a, b = Service(), Service()
    await a.find(1)
    await b.find(1)  # `self` is excluded from the auto key -> shared entry
    assert repo.reads == 1

    await a.find.invalidate(a, 1)
    await a.find(1)
    assert repo.reads == 2


async def test_tags_invalidate_list_queries(toolkit: RedisToolkit, repo: FakeRepo):
    @toolkit.cache.cached("vehicles:all", tags=["vehicles"])
    async def list_vehicles() -> list[Vehicle]:
        repo.reads += 1
        return list(repo.rows.values())

    @toolkit.cache.cache_evict(tags=["vehicles"])
    async def add_vehicle(vehicle: Vehicle) -> None:
        repo.rows[vehicle.id] = vehicle

    assert len(await list_vehicles()) == 1
    await add_vehicle(Vehicle(id=2, plate="B"))
    assert len(await list_vehicles()) == 2
    assert repo.reads == 2


async def test_cache_evict_key_template_and_pattern(toolkit: RedisToolkit):
    cache = toolkit.cache
    await cache.set("vehicle:1", {"a": 1})
    await cache.set("user:7:page:1", [1])
    await cache.set("user:7:page:2", [2])

    @cache.cache_evict("vehicle:{vehicle_id}", pattern="user:{user_id}:page:*")
    async def touch(vehicle_id: int, user_id: int) -> str:
        return "ok"

    assert await touch(1, 7) == "ok"
    assert not await cache.exists("vehicle:1")
    assert not await cache.exists("user:7:page:1")
    assert not await cache.exists("user:7:page:2")


async def test_decorator_rejects_sync_function(toolkit: RedisToolkit):
    with pytest.raises(TypeError):

        @toolkit.cache.cached("x")
        def sync_fn() -> int:
            return 1


# ------------------------------------------------------------------ strategies
async def test_cache_aside_write_invalidates(toolkit: RedisToolkit, repo: FakeRepo):
    cache = toolkit.cache
    await cache.read("vehicle:1", lambda: repo.get(1), strategy="cache_aside")
    await cache.write("vehicle:1", Vehicle(id=1, plate="X"), repo.save, strategy="cache_aside")

    assert not await cache.exists("vehicle:1")
    assert repo.rows[1].plate == "X"


async def test_cache_aside_double_delete(toolkit: RedisToolkit, repo: FakeRepo):
    cache = toolkit.cache
    await cache.write(
        "vehicle:1", Vehicle(id=1, plate="X"), repo.save, strategy="cache_aside", double_delete_delay=0.05
    )
    await cache.set("vehicle:1", {"stale": True})  # a racing reader re-caches the old row
    await asyncio.sleep(0.1)
    assert not await cache.exists("vehicle:1")


async def test_read_through_bound_loader_and_single_flight(toolkit: RedisToolkit, repo: FakeRepo):
    async def slow_load(key: str) -> Vehicle | None:
        await asyncio.sleep(0.05)
        return await repo.get(int(key))

    vehicles = toolkit.cache.read_through(slow_load, Vehicle | None, namespace="vehicle", stampede_lock_ttl=5)
    results = await asyncio.gather(*(vehicles.get("1") for _ in range(10)))

    assert all(r == Vehicle(id=1, plate="29A-001") for r in results)
    assert repo.reads == 1


async def test_read_through_without_loader_errors(toolkit: RedisToolkit):
    with pytest.raises(CacheError):
        await toolkit.cache.read("missing", strategy="read_through")


async def test_write_through_populates_cache(toolkit: RedisToolkit, repo: FakeRepo):
    @toolkit.cache.cache_write("vehicle:{vehicle.id}", strategy="write_through")
    async def save_vehicle(vehicle: Vehicle) -> Vehicle:
        return await repo.save(vehicle)

    @toolkit.cache.cached("vehicle:{vehicle_id}")
    async def get_vehicle(vehicle_id: int) -> Vehicle | None:
        return await repo.get(vehicle_id)

    await save_vehicle(Vehicle(id=5, plate="WT"))
    assert await get_vehicle(5) == Vehicle(id=5, plate="WT")
    assert repo.reads == 0 and repo.writes == 1


async def test_write_through_cache_writer_result(toolkit: RedisToolkit):
    @toolkit.cache.cache_write("vehicle:{vehicle.id}", cache_writer_result=True)
    async def save_vehicle(vehicle: Vehicle) -> Vehicle:
        return vehicle.model_copy(update={"plate": vehicle.plate.upper()})

    await save_vehicle(Vehicle(id=5, plate="abc"))
    assert await toolkit.cache.get("vehicle:5") == {"id": 5, "plate": "ABC"}


async def test_write_through_db_failure_leaves_cache_untouched(toolkit: RedisToolkit):
    cache = toolkit.cache
    await cache.set("vehicle:1", {"id": 1, "plate": "OLD"})

    async def failing_writer(_):
        raise RuntimeError("db down")

    with pytest.raises(RuntimeError):
        await cache.write("vehicle:1", {"id": 1, "plate": "NEW"}, failing_writer, strategy="write_through")
    assert await cache.get("vehicle:1") == {"id": 1, "plate": "OLD"}


async def test_write_around_does_not_touch_cache(toolkit: RedisToolkit, repo: FakeRepo):
    cache = toolkit.cache
    await cache.set("vehicle:1", {"id": 1, "plate": "OLD"})
    await cache.write("vehicle:1", Vehicle(id=1, plate="NEW"), repo.save, strategy="write_around")

    assert repo.rows[1].plate == "NEW"
    assert await cache.get("vehicle:1") == {"id": 1, "plate": "OLD"}


async def test_write_back_defers_db_write_until_flush(toolkit: RedisToolkit, repo: FakeRepo):
    @toolkit.cache.cache_write("vehicle:{vehicle.id}", strategy="write_back", queue="vehicles")
    async def save_vehicle(vehicle: Vehicle) -> Vehicle:
        return await repo.save(vehicle)

    assert await save_vehicle(Vehicle(id=9, plate="WB1")) is None
    await save_vehicle(Vehicle(id=9, plate="WB2"))  # coalesced with the first write
    await save_vehicle(Vehicle(id=10, plate="WB3"))

    assert repo.writes == 0
    assert await toolkit.cache.get("vehicle:9") == {"id": 9, "plate": "WB2"}
    assert await toolkit.cache.write_back_buffer.pending_count("vehicles") == 2

    result = await toolkit.cache.write_back_buffer.flush("vehicles")

    assert result.flushed == 2 and result.failed == 0
    assert repo.writes == 2
    assert repo.rows[9] == Vehicle(id=9, plate="WB2")
    assert await toolkit.cache.write_back_buffer.pending_count("vehicles") == 0


async def test_write_back_failed_flush_stays_pending(toolkit: RedisToolkit):
    calls = 0

    async def flaky_writer(value):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("db down")

    cache = toolkit.cache
    cache.register_write_back("flaky", flaky_writer)
    await cache.write("k", {"v": 1}, strategy="write_back", write_back_queue="flaky")

    first = await cache.write_back_buffer.flush("flaky")
    second = await cache.write_back_buffer.flush("flaky")
    assert (first.failed, second.flushed) == (1, 1)


async def test_write_back_read_falls_back_to_pending_after_eviction(toolkit: RedisToolkit):
    cache = toolkit.cache
    cache.register_write_back("q", lambda v: asyncio.sleep(0))
    await cache.write("k", {"v": 1}, strategy="write_back", write_back_queue="q")
    await cache.delete("k")  # simulate TTL eviction before flush

    assert await cache.read("k", strategy="write_back", write_back_queue="q") == {"v": 1}


async def test_unknown_strategy(toolkit: RedisToolkit):
    with pytest.raises(CacheError):
        toolkit.cache.strategy("nope")


async def test_ttl_and_jitter(toolkit: RedisToolkit):
    await toolkit.cache.set("k", 1, ttl=100, ttl_jitter=0.5)
    remaining = await toolkit.cache.ttl("k")
    assert 99 <= remaining <= 150
    await toolkit.cache.set("forever", 1, ttl=0)
    assert await toolkit.cache.ttl("forever") is None
    assert await toolkit.cache.get("forever") == 1
