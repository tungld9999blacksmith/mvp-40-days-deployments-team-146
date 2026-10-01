"""Pub/Sub, queue, bloom filter, sorted set and geo index."""

import asyncio

import pytest
from pydantic import BaseModel

from src.infrastructure.redis import (
    GeoPoint,
    GeoUnit,
    Message,
    QueueMessage,
    RedisToolkit,
    running_consumer,
)

pytestmark = pytest.mark.asyncio


class VehicleEvent(BaseModel):
    vehicle_id: int
    status: str


# ---------------------------------------------------------------------- pub/sub
async def _next(iterator, timeout=2.0):
    return await asyncio.wait_for(anext(iterator), timeout)


async def test_pubsub_typed_topic_roundtrip(toolkit: RedisToolkit):
    topic = toolkit.pubsub.topic("vehicle.updated", VehicleEvent)
    stream = topic.subscribe()
    receive = asyncio.create_task(_next(stream))
    await asyncio.sleep(0.05)  # let the subscription register

    receivers = await topic.publish(VehicleEvent(vehicle_id=1, status="parked"), headers={"source": "test"})
    message = await receive
    await stream.aclose()

    assert receivers == 1
    assert isinstance(message.data, VehicleEvent)
    assert message.data.status == "parked"
    assert message.channel == "vehicle.updated"
    assert message.headers == {"source": "test"}


async def test_pubsub_pattern_topic(toolkit: RedisToolkit):
    all_vehicles = toolkit.pubsub.topic("vehicle.*", VehicleEvent, pattern=True)
    stream = all_vehicles.subscribe()
    receive = asyncio.create_task(_next(stream))
    await asyncio.sleep(0.05)

    await all_vehicles.publish(VehicleEvent(vehicle_id=2, status="moving"), channel="vehicle.moved")
    message = await receive
    await stream.aclose()

    assert message.channel == "vehicle.moved"
    assert message.data.vehicle_id == 2
    with pytest.raises(ValueError):
        await all_vehicles.publish(VehicleEvent(vehicle_id=2, status="x"))


async def test_pubsub_background_handlers(toolkit: RedisToolkit):
    topic = toolkit.pubsub.topic("counter", int)
    got: list[int] = []
    done = asyncio.Event()

    @topic.on
    async def handle(message: Message[int]) -> None:
        got.append(message.data)
        if len(got) == 2:
            done.set()

    await toolkit.pubsub.start()
    await asyncio.sleep(0.1)
    await topic.publish(1)
    await topic.publish(2)
    await asyncio.wait_for(done.wait(), 2)
    assert got == [1, 2]


# ------------------------------------------------------------------------ queue
async def test_queue_enqueue_receive_ack(toolkit: RedisToolkit):
    queue = toolkit.queue("jobs", VehicleEvent)
    await queue.enqueue(VehicleEvent(vehicle_id=1, status="a"), headers={"trace": "t1"})
    await queue.enqueue_many([VehicleEvent(vehicle_id=2, status="b")])

    messages = await queue.receive(count=10, block=None)
    assert [m.data.vehicle_id for m in messages] == [1, 2]
    assert messages[0].attempt == 1 and messages[0].headers == {"trace": "t1"}
    assert await queue.pending_count() == 2

    await queue.ack(*messages)
    assert await queue.pending_count() == 0
    assert await queue.size() == 0


async def test_queue_each_message_goes_to_one_consumer(redis, toolkit: RedisToolkit):
    worker_a = toolkit.queue("shared", int, consumer="a")
    worker_b = toolkit.queue("shared", int, consumer="b")
    for i in range(6):
        await worker_a.enqueue(i)

    got_a = await worker_a.receive(count=3, block=None)
    got_b = await worker_b.receive(count=10, block=None)
    assert sorted(m.data for m in got_a + got_b) == list(range(6))
    assert not {m.id for m in got_a} & {m.id for m in got_b}


async def test_queue_nack_retries_then_dead_letters(toolkit: RedisToolkit):
    queue = toolkit.queue("retry", str, max_attempts=2)
    await queue.enqueue("payload")

    (first,) = await queue.receive(block=None)
    await queue.nack(first, error="boom")
    (second,) = await queue.receive(block=None)
    assert second.attempt == 2 and second.last_error == "boom"

    await queue.nack(second, error="boom again")
    assert await queue.receive(block=None) == []
    assert await queue.dead_count() == 1
    (dead,) = await queue.dead_letters()
    assert dead.data == "payload" and dead.last_error == "boom again"

    assert await queue.requeue_dead() == 1
    (revived,) = await queue.receive(block=None)
    assert revived.attempt == 1


async def test_queue_reclaims_messages_of_crashed_worker(toolkit: RedisToolkit):
    crashed = toolkit.queue("reclaim", int, consumer="crashed", visibility_timeout=0.05)
    healthy = toolkit.queue("reclaim", int, consumer="healthy", visibility_timeout=0.05)
    await crashed.enqueue(7)

    (taken,) = await crashed.receive(block=None)  # ... and never acked
    assert await healthy.receive(block=None) == []
    await asyncio.sleep(0.1)

    (reclaimed,) = await healthy.receive(block=None)
    assert reclaimed.id == taken.id and reclaimed.data == 7 and reclaimed.attempt == 2


async def test_queue_delayed_messages(toolkit: RedisToolkit):
    queue = toolkit.queue("delayed", int)
    msg_id = await queue.enqueue(1, delay=0.2)
    assert msg_id.startswith("delayed:")
    assert await queue.delayed_count() == 1
    assert await queue.receive(block=None) == []

    await asyncio.sleep(0.25)
    (message,) = await queue.receive(block=None)
    assert message.data == 1 and await queue.delayed_count() == 0


async def test_queue_consume_loop_acks_and_retries(toolkit: RedisToolkit):
    queue = toolkit.queue("worker", int, max_attempts=3)
    seen: list[tuple[int, int]] = []
    done = asyncio.Event()

    async def handler(message: QueueMessage[int]) -> None:
        seen.append((message.data, message.attempt))
        if message.data == 2 and message.attempt == 1:
            raise RuntimeError("transient")
        if len(seen) == 3:
            done.set()

    await queue.enqueue_many([1, 2])
    async with running_consumer(queue, handler, block=0.05):
        await asyncio.wait_for(done.wait(), 3)

    assert sorted(seen) == [(1, 1), (2, 1), (2, 2)]
    assert await queue.pending_count() == 0 and await queue.dead_count() == 0


# ------------------------------------------------------------------------ bloom
async def test_bloom_filter(toolkit: RedisToolkit):
    bloom = toolkit.bloom_filter("emails", capacity=1000, error_rate=0.01)
    assert bloom.num_hashes >= 1 and bloom.num_bits > 1000

    assert await bloom.add("a@x.com") is True
    assert await bloom.add("a@x.com") is False
    assert await bloom.contains("a@x.com")
    assert not await bloom.contains("b@x.com")

    added = await bloom.add_many([f"user{i}" for i in range(200)])
    assert sum(added) >= 195
    assert all(await bloom.contains_many([f"user{i}" for i in range(200)]))
    assert 180 <= await bloom.approximate_count() <= 220

    false_positives = sum(await bloom.contains_many([f"other{i}" for i in range(1000)]))
    assert false_positives < 30  # ~1% expected

    await bloom.clear()
    assert not await bloom.contains("a@x.com")


async def test_bloom_filter_structured_items(toolkit: RedisToolkit):
    bloom = toolkit.bloom_filter("events", capacity=100)
    await bloom.add({"b": 2, "a": 1})
    assert await bloom.contains({"a": 1, "b": 2})  # key order doesn't matter


# ------------------------------------------------------------------- sorted set
async def test_sorted_set_leaderboard(toolkit: RedisToolkit):
    board = toolkit.sorted_set("leaderboard", member_type=int)
    await board.add_many({1: 10, 2: 30, 3: 20})
    await board.incr(1, 25)  # user 1 -> 35

    top = await board.top(2)
    assert [(m.member, m.score, m.rank) for m in top] == [(1, 35.0, 0), (2, 30.0, 1)]
    assert await board.rank(3, reverse=True) == 2
    assert await board.score(2) == 30.0
    assert await board.scores([1, 99]) == [35.0, None]
    assert await board.count(15, 31) == 2
    assert [m.member for m in await board.range_by_score(15, "+inf")] == [3, 2, 1]
    assert [m.member for m in await board.range_by_score(reverse=True, limit=1, offset=0)] == [1]
    assert [m.member for m in await board.around(2, radius=1)] == [1, 2, 3]

    assert await board.add(2, 5, gt=True) is False  # lower score ignored with gt
    assert await board.trim(2) == 1
    assert await board.size() == 2
    assert [m.member for m in await board.pop_min()] == [2]
    assert await board.remove(1) == 1


async def test_sorted_set_model_members(toolkit: RedisToolkit):
    zset = toolkit.sorted_set("events", member_type=VehicleEvent, ttl=100)
    event = VehicleEvent(vehicle_id=1, status="x")
    await zset.add(event, 1.5)
    assert (await zset.bottom(1))[0].member == event
    assert await zset.contains(event)
    assert [m.member async for m in zset.scan()] == [event]


# -------------------------------------------------------------------------- geo
HANOI = GeoPoint(longitude=105.8342, latitude=21.0278)
HO_GUOM = GeoPoint(longitude=105.8523, latitude=21.0288)
HCMC = GeoPoint(longitude=106.6297, latitude=10.8231)


async def test_geo_index(toolkit: RedisToolkit):
    stations = toolkit.geo("stations", member_type=int)
    await stations.add_many({1: HANOI, 2: HO_GUOM, 3: HCMC})

    assert await stations.size() == 3
    pos = await stations.position(1)
    assert abs(pos.longitude - HANOI.longitude) < 1e-4 and abs(pos.latitude - HANOI.latitude) < 1e-4
    assert await stations.position(99) is None

    distance = await stations.distance(1, 2, GeoUnit.KM)
    assert 1.5 < distance < 2.5
    assert 1100 < await stations.distance(1, 3) < 1200

    near = await stations.nearby(HANOI, radius=10, unit=GeoUnit.KM)
    assert [r.member for r in near] == [1, 2]
    assert near[0].distance < near[1].distance and near[1].point is not None

    around_member = await stations.search(2, radius=5, with_point=False, with_distance=False)
    assert sorted(r.member for r in around_member) == [1, 2]

    # within_box (GEOSEARCH BYBOX) is not implemented by fakeredis; covered by real Redis only
    assert (await stations.geohash(1)).startswith("w7")

    with pytest.raises(ValueError):
        await stations.search(HANOI)
    with pytest.raises(ValueError):
        GeoPoint(longitude=0, latitude=89)

    assert await stations.remove(3) == 1
    assert not await stations.contains(3)
