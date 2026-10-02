# Redis toolkit — `src/infrastructure/redis/`

Bộ tiện ích Redis dùng chung, toàn bộ là **async** (`redis.asyncio`). Chỉ package này được import `redis`; phần còn lại của code dùng các class export từ `src.infrastructure.redis`.

```python
from src.infrastructure.redis import get_redis_toolkit

toolkit = get_redis_toolkit()  # singleton, an toàn khi gọi lúc import (chưa kết nối cho tới lần dùng đầu)
toolkit.cache  # CacheFacade    — cache strategies + decorators
toolkit.locks  # LockManager    — distributed lock
toolkit.pubsub  # PubSubBroker   — pub/sub có kiểu
toolkit.queue(...)  # DistributedQueue[T]
toolkit.bloom_filter(...), toolkit.sorted_set(...), toolkit.geo(...)
```

Cấu hình (`.env`): `REDIS_URL` hoặc `REDIS_HOST/PORT/DB/PASSWORD`, `REDIS_KEY_PREFIX` (mọi key đều có prefix này), `REDIS_DEFAULT_CACHE_TTL`.
App lifespan (`src/main.py`) gọi `toolkit.start()` (write-back flusher, pub/sub handlers) và `toolkit.close()`.

| File | Nội dung |
|---|---|
| `toolkit.py` | `RedisToolkit` — facade tổng |
| `cache/` | `options.py` (CacheOptions), `store.py`, `strategies.py` (Strategy pattern), `write_back.py`, `facade.py` (Facade + decorators) |
| `lock/` | `LockKey`, `DistributedLock`, `TransactionLock`, `LockManager` |
| `pubsub.py`, `queue.py`, `bloom.py`, `sorted_set.py`, `geo.py` | các cấu trúc dữ liệu |
| `serializers.py` | `TypeAdapterSerializer`, `JsonSerializer`, `PickleSerializer`, `StrSerializer` |

---

## 1. Cache

### Strategies

| strategy | Đọc khi miss | Ghi |
|---|---|---|
| `cache_aside` | loader do caller truyền vào, rồi ghi cache | ghi DB → xoá key (tuỳ chọn xoá lần 2 sau `double_delete_delay`) |
| `read_through` | loader gắn sẵn trong cache, luôn chống stampede | ghi DB → xoá key |
| `write_through` | như trên | ghi DB → set cache giá trị mới (đồng bộ) |
| `write_around` | như trên | chỉ ghi DB; cache tự hết hạn theo TTL |
| `write_back` | đọc buffer pending trước, rồi loader | set cache ngay, DB được ghi sau theo batch (`WriteBackBuffer`) |

Tự thêm strategy: kế thừa `CacheStrategy`, rồi `toolkit.cache.register_strategy(MyStrategy(store, locks))`.

### Options (`CacheOptions`, truyền dưới dạng kwargs)

`ttl` (0 = không hết hạn), `serializer`, `namespace`, `ttl_jitter` (chống avalanche), `cache_none` + `none_ttl` (chống penetration), `stampede_lock` + `stampede_lock_ttl` + `stampede_wait` (chống breakdown), `tags`, `cache_if`, `cache_writer_result`, `write_back_queue`, `double_delete_delay`.

### Decorators cho repository (ví dụ Supabase)

```python
from src.infrastructure.redis import get_cache

cache = get_cache()


class VehicleRepository:
    @cache.cached("vehicle:{vehicle_id}", ttl=600, tags=["vehicles"], stampede_lock=True)
    async def get(self, vehicle_id: int) -> Vehicle | None:  # kiểu trả về -> serializer tự suy ra
        ...

    @cache.cached("user:{user_id}:vehicles", tags=["vehicles"], ttl_jitter=0.1)
    async def list_by_user(self, user_id: int) -> list[Vehicle]: ...

    @cache.cache_write("vehicle:{vehicle.id}", strategy="write_through", cache_writer_result=True)
    async def save(self, vehicle: Vehicle) -> Vehicle:  # cache giá trị DB trả về
        ...

    @cache.cache_evict("vehicle:{vehicle_id}", tags=["vehicles"])
    async def delete(self, vehicle_id: int) -> None: ...


await repo.get.invalidate(repo, 42)  # helper của @cached: invalidate / refresh / key_for
```

- Template key là `str.format` trên tham số: `"{vehicle.id}"`, `"{filters[page]}"`. Có thể truyền `key=callable`, hoặc bỏ trống để tự sinh từ tham số (bỏ qua `self`, `session`, `db`).
- `condition=lambda *a, **kw: ...` để bỏ qua cache cho một lời gọi.
- Decorator chỉ nhận **async function**. Với truy vấn SQLModel đồng bộ, bọc bằng `await run_in_threadpool(...)`.
- Write-back: `@cache.cache_write(..., strategy="write_back", queue="vehicles")` — lời gọi trả về `None` ngay; hàm được gọi sau trong lần flush dưới dạng `func(<value_arg>=value)`, nên các tham số khác phải có default. Buffer nằm trong Redis nên không mất khi restart.

### Gọi trực tiếp

```python
v = await cache.read("vehicle:42", lambda: repo.get(42), strategy="cache_aside", ttl=600)
await cache.write("vehicle:42", v, repo.save, strategy="write_through")
vehicles = cache.read_through(lambda key: repo.get(int(key)), Vehicle | None, namespace="vehicle")
await vehicles.get("42")
await cache.invalidate_tags("vehicles")
await cache.invalidate_pattern("user:7:*")
```

## 2. Distributed lock

Acquire nhiều key trong **một Lua script** (all-or-nothing, không deadlock do thứ tự), token ngẫu nhiên (không xoá nhầm lock của người khác), **fencing token** tăng dần, `auto_renew` (watchdog gia hạn TTL). Không re-entrant.

```python
from src.infrastructure.redis import LockKey, get_lock_manager
locks = get_lock_manager()

# Khoá theo data
async with locks.lock_data(LockKey(data_type="vehicle", data_id=42)) as lock:
    ...  # lock.fencing_token có thể dùng để chặn ghi muộn ở DB
LockKey.of(vehicle)  # từ entity: data_type = __tablename__

@locks.data_locked("vehicle", "{vehicle_id}")
async def update_vehicle(vehicle_id: int, ...): ...

# Khoá theo đoạn găng (critical section)
async with locks.critical_section("rebuild-leaderboard", ttl=60, wait_timeout=0): ...

@locks.synchronized("sync-user:{user_id}")
async def sync_user(user_id: int): ...

# Khoá theo transaction hệ thống: khoá mọi tài nguyên của 1 transaction cùng lúc
async with locks.transaction(LockKey(data_type="wallet", data_id=a),
                             LockKey(data_type="wallet", data_id=b), "billing") as tx:
    tx.after_commit(lambda: cache.invalidate_tags("wallets"))   # chạy khi vẫn giữ lock
    ...
await locks.holder(LockKey(data_type="wallet", data_id=a))       # -> tx.transaction_id
```

`wait_timeout`: `0` = thử 1 lần, `None` = chờ mãi. Hết giờ → `LockAcquireError`. Lock hết hạn trước khi release → `LockNotOwnedError`.

## 3. Pub/Sub (generic)

```python
events = toolkit.pubsub.topic("vehicle.updated", VehicleEvent)  # Topic[VehicleEvent]
await events.publish(VehicleEvent(...), headers={"trace": "..."})

async for msg in events.subscribe():  # msg: Message[VehicleEvent], msg.data đã decode
    ...


@events.on  # handler nền, chạy sau toolkit.start()
async def on_update(msg: Message[VehicleEvent]): ...


all_vehicle = toolkit.pubsub.topic("vehicle.*", VehicleEvent, pattern=True)
```

Pub/Sub của Redis là fire-and-forget: subscriber offline sẽ mất message. Cần đảm bảo xử lý → dùng queue.

## 4. Queue phân tán (Redis Streams + consumer group)

At-least-once, tự reclaim message của worker chết (`visibility_timeout`), retry/`nack` có delay, dead-letter sau `max_attempts`, delayed message.

```python
jobs = toolkit.queue("vehicle-sync", VehicleEvent, max_attempts=5, visibility_timeout=60)
await jobs.enqueue(event)
await jobs.enqueue(event, delay=30)


async def handle(msg: QueueMessage[VehicleEvent]): ...  # phải idempotent


await jobs.consume(handle, concurrency=4, retry_delay=exponential_backoff(1, 300))
# hoặc: async with running_consumer(jobs, handle): ...

await jobs.dead_letters()
await jobs.requeue_dead()
```

## 5. Bloom filter

Bitmap trên Redis thường (không cần module RedisBloom). `contains` = False → chắc chắn chưa có.

```python
seen = toolkit.bloom_filter("vehicle-ids", capacity=1_000_000, error_rate=0.01)
await seen.add(42)
await seen.contains(42)
await seen.add_many(ids)
```

## 6. Sorted set

```python
board = toolkit.sorted_set("leaderboard:weekly", member_type=int)
await board.incr(user_id, 10)
await board.top(10)
await board.rank(user_id, reverse=True)
await board.around(user_id, 2)
await board.range_by_score(100, "+inf", limit=20)
await board.trim(1000)
```

## 7. Geospatial

```python
stations = toolkit.geo("charging-stations", member_type=int)
await stations.add(17, GeoPoint(longitude=105.8342, latitude=21.0278))
await stations.nearby(GeoPoint(longitude=105.85, latitude=21.03), radius=5, unit=GeoUnit.KM, limit=10)
await stations.within_box(center, width=10, height=10)
await stations.distance(1, 2)
```

## Test

`tests/test_infrastructure/test_redis/` dùng `fakeredis[lua]`, không cần Redis thật. `within_box` (GEOSEARCH BYBOX) chưa được fakeredis hỗ trợ nên chỉ chạy được trên Redis thật.
