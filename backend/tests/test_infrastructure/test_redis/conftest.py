import pytest_asyncio
from fakeredis import FakeAsyncRedis

from src.infrastructure.redis import RedisToolkit


@pytest_asyncio.fixture
async def redis():
    client = FakeAsyncRedis()
    yield client
    await client.flushall()
    await client.aclose()


@pytest_asyncio.fixture
async def toolkit(redis) -> RedisToolkit:
    tk = RedisToolkit(redis, key_prefix="test", default_cache_ttl=60)
    yield tk
    await tk.pubsub.stop()
    await tk.cache.write_back_buffer.stop(final_flush=False)
