import asyncio

import pytest

from src.infrastructure.redis import LockAcquireError, LockKey, LockNotOwnedError, RedisToolkit

pytestmark = pytest.mark.asyncio


async def test_lock_key_model():
    key = LockKey(data_type=" Vehicle ", data_id=42)
    assert key.resource == "vehicle:42"
    assert key == LockKey(data_type="vehicle", data_id=42)

    class Row:
        __tablename__ = "user_vehicle"
        id = 7

    assert LockKey.of(Row()).resource == "user_vehicle:7"
    with pytest.raises(ValueError):
        LockKey(data_type="", data_id=1)


async def test_data_lock_excludes_second_holder(toolkit: RedisToolkit):
    locks = toolkit.locks
    key = LockKey(data_type="vehicle", data_id=1)

    async with locks.lock_data(key) as held:
        assert held.fencing_token is not None
        assert await locks.is_locked(key)
        assert await locks.holder(key) == held.token
        assert not await locks.lock_data(key, wait_timeout=0).acquire()
        with pytest.raises(LockAcquireError):
            async with locks.lock_data(key, wait_timeout=0.1):
                pass

    assert not await locks.is_locked(key)


async def test_fencing_tokens_increase(toolkit: RedisToolkit):
    locks = toolkit.locks
    tokens = []
    for _ in range(3):
        async with locks.critical_section("job") as lock:
            tokens.append(lock.fencing_token)
    assert tokens == sorted(tokens) and len(set(tokens)) == 3


async def test_critical_section_serializes_concurrent_tasks(toolkit: RedisToolkit):
    inside = 0
    max_inside = 0

    @toolkit.locks.synchronized("counter", wait_timeout=5)
    async def work():
        nonlocal inside, max_inside
        inside += 1
        max_inside = max(max_inside, inside)
        await asyncio.sleep(0.01)
        inside -= 1

    await asyncio.gather(*(work() for _ in range(5)))
    assert max_inside == 1


async def test_synchronized_name_template(toolkit: RedisToolkit):
    seen = []

    @toolkit.locks.synchronized("user:{user_id}")
    async def work(user_id: int):
        seen.append(await toolkit.locks.is_locked(f"user:{user_id}"))

    await work(3)
    assert seen == [True]


async def test_data_locked_decorator(toolkit: RedisToolkit):
    @toolkit.locks.data_locked("vehicle", "{vehicle_id}")
    async def update(vehicle_id: int):
        return await toolkit.locks.is_locked(LockKey(data_type="vehicle", data_id=vehicle_id))

    @toolkit.locks.data_locked(
        key=lambda src, dst: [LockKey(data_type="wallet", data_id=src), LockKey(data_type="wallet", data_id=dst)]
    )
    async def transfer(src: int, dst: int):
        return [await toolkit.locks.is_locked(LockKey(data_type="wallet", data_id=i)) for i in (src, dst)]

    assert await update(5) is True
    assert await transfer(1, 2) == [True, True]


async def test_expired_lock_is_not_released_by_old_holder(toolkit: RedisToolkit):
    locks = toolkit.locks
    first = locks.critical_section("x", ttl=0.05)
    assert await first.acquire()
    await asyncio.sleep(0.1)  # TTL passes; someone else takes over
    second = locks.critical_section("x")
    assert await second.acquire()

    with pytest.raises(LockNotOwnedError):
        await first.release()
    assert await locks.holder("x") == second.token
    await second.release()


async def test_extend_and_auto_renew(toolkit: RedisToolkit):
    locks = toolkit.locks
    lock = locks.critical_section("renew", ttl=0.15, auto_renew=True)
    async with lock:
        await asyncio.sleep(0.4)  # well past the original TTL
        assert await lock.is_owned()
        await lock.extend(1)
    assert not await locks.is_locked("renew")


async def test_transaction_lock_is_all_or_nothing(toolkit: RedisToolkit):
    locks = toolkit.locks
    a = LockKey(data_type="account", data_id=1)
    b = LockKey(data_type="account", data_id=2)

    async with locks.lock_data(b):
        tx = locks.transaction(a, b, wait_timeout=0)
        assert not await tx.acquire()
        # the free key must not have been left locked by the failed attempt
        assert not await locks.is_locked(a)

    async with locks.transaction(a, b, "billing") as tx:
        assert await locks.holder(a) == tx.transaction_id
        assert await locks.holder("billing") == tx.transaction_id


async def test_transaction_hooks(toolkit: RedisToolkit):
    locks = toolkit.locks
    key = LockKey(data_type="order", data_id=1)
    events = []

    async with locks.transaction(key) as tx:
        tx.after_commit(lambda: events.append("commit"))
        tx.after_rollback(lambda: events.append("rollback"))

    with pytest.raises(ValueError):
        async with locks.transaction(key) as tx:

            async def still_locked():
                events.append(("rollback-locked", await locks.is_locked(key)))

            tx.after_rollback(still_locked)
            raise ValueError("boom")

    assert events == ["commit", ("rollback-locked", True)]
    assert not await locks.is_locked(key)
