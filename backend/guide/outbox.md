# Transactional outbox — `src/infrastructure/outbox/`

Dùng khi một thay đổi nghiệp vụ cần kéo theo một việc phụ (gửi thông báo, gọi dịch vụ ngoài, đồng bộ dữ liệu…) mà:

- việc phụ **không được mất** khi worker hoặc Redis lỗi, và
- request **không phải chờ** việc phụ chạy xong.

Event được lưu vào bảng `outbox_event` (Supabase Postgres) **trong cùng transaction** với dữ liệu nghiệp vụ. Worker đọc event, tra `event_type` để tìm handler rồi gọi handler xử lý.

```
Request ──┬─ ghi dữ liệu nghiệp vụ
          └─ publish(session, Event)        ← chưa commit
             session.commit()                ← dữ liệu + event cùng lưu, hoặc cùng huỷ
             └─ đánh thức outbox.dispatch    ← sau commit, lỗi cũng không sao

Worker: outbox.dispatch (beat mỗi 10 s + mỗi lần được đánh thức)
   lặp tối đa OUTBOX_BATCH_SIZE lần:
     claim 1 event đến hạn (FOR UPDATE SKIP LOCKED, đặt lease) → commit
     registry[event_type] → giải mã payload → handler.handle(event, ctx)
     thành công → succeeded | lỗi → pending + backoff | hết lượt / PermanentError → dead
```

Event được xử lý **tuần tự** trong một lần chạy `outbox.dispatch`. Nhiều lần chạy song song (beat và wakeup trùng nhau) vẫn an toàn nhờ `SKIP LOCKED`.

---

## 1. Định nghĩa event

```python
from uuid import UUID
from src.infrastructure.outbox import OutboxEvent

class BookingConfirmed(OutboxEvent):
    event_type = "booking.confirmed"   # duy nhất, không đổi sau khi đã có dữ liệu
    schema_version = 1
    booking_id: UUID
    user_id: int
```

- Payload là `model_dump(mode="json")` của event, nên chỉ chứa **id và dữ liệu tối thiểu**. Handler tự đọc lại dữ liệu mới nhất từ DB.
- **Không** đưa SĐT, email, VIN hay nội dung chat vào payload.
- Đổi cấu trúc payload thì tăng `schema_version` và override `upcast(payload, from_version)` để đọc được các dòng cũ. Nếu worker gặp event có version **mới hơn** code của nó, event được retry cho tới khi worker được deploy bản mới.

## 2. Viết handler

```python
from src.infrastructure.outbox import OutboxHandler, OutboxContext, PermanentError, RetryableError, register_handler

class NotifyOwnerOnBookingConfirmed(OutboxHandler[BookingConfirmed]):
    event = BookingConfirmed
    timeout_seconds = 20          # tuỳ chọn; mặc định OUTBOX_HANDLER_TIMEOUT_SECONDS

    async def handle(self, event: BookingConfirmed, ctx: OutboxContext) -> None:
        booking = load_booking(event.booking_id)
        if booking is None:
            raise PermanentError("booking deleted")      # → dead ngay, không retry
        try:
            await send(...)
        except RateLimited as exc:
            raise RetryableError(retry_after=60) from exc  # tự chọn thời gian chờ

register_handler(NotifyOwnerOnBookingConfirmed())
```

Rồi thêm module chứa handler vào `OUTBOX_HANDLER_MODULES` trong [`celery/tasks/outbox_tasks.py`](../src/infrastructure/celery/tasks/outbox_tasks.py) để worker import nó.

| Handler làm gì | Kết quả |
|---|---|
| return bình thường | `succeeded` |
| raise `PermanentError` | `dead` ngay |
| raise `RetryableError(retry_after=…)` | `pending`, chờ `retry_after` giây |
| raise lỗi khác hoặc quá timeout | `pending`, backoff lũy thừa |
| hết `max_attempts` | `dead` |

**Handler phải idempotent** (chạy lặp không gây hậu quả). Outbox chỉ bảo đảm *at-least-once*: worker chết sau khi đã gửi nhưng trước khi đánh dấu xong, hoặc lease hết hạn, thì event chạy lại. Dùng `ctx.event_id` làm khóa chống trùng khi gọi dịch vụ ngoài, hoặc kiểm tra trạng thái trong DB trước khi làm.

Mỗi event có một handler duy nhất. Cần nhiều phản ứng cho cùng một sự việc thì publish nhiều event, hoặc cho một handler gọi lần lượt các bước idempotent.

## 3. Publish

```python
from src.infrastructure.outbox import publish

booking.status = BookingStatus.CONFIRMED
publish(
    session,
    BookingConfirmed(booking_id=booking.id, user_id=booking.user_id),
    aggregate_type="booking",
    aggregate_id=str(booking.id),
    dedup_key=f"booking:{booking.id}:confirmed",  # tuỳ chọn: publish lần 2 với cùng key thì bỏ qua
    # delay=timedelta(minutes=30),                # tuỳ chọn: chưa xử lý trước thời điểm này
)
session.commit()
```

- `publish` **không commit**. Nếu transaction rollback thì event cũng mất theo, đúng như mong muốn.
- Không publish rồi commit ở một session khác: như vậy mất tính nguyên tử, outbox không còn tác dụng.
- Sau commit, wakeup đẩy `outbox.dispatch` vào Celery (tắt bằng `OUTBOX_WAKEUP_ENABLED=false`). Wakeup lỗi chỉ làm event chờ tới lượt quét beat tiếp theo.

## 4. Vận hành

| Việc | Cách làm |
|---|---|
| Xem event lỗi | `SELECT id, event_type, attempts, last_error, created_at FROM outbox_event WHERE status = 'dead' ORDER BY created_at DESC;` |
| Chạy lại event dead (sau khi sửa nguyên nhân) | `build_outbox_dispatcher().requeue_dead(event_id)` |
| Dọn dẹp | `outbox.purge` (03:30 hằng ngày) xoá event `succeeded` cũ hơn `OUTBOX_RETENTION_DAYS`. Event `dead` được giữ lại để điều tra. |
| Log | `outbox.event.succeeded` / `outbox.event.retry` / `outbox.event.dead` / `outbox.lease_lost`, kèm `event_id`, `event_type`, `attempt`. Span OTel `outbox.handle` mang `outbox.producer_trace_id` để nối về request đã publish. |

`last_error` chỉ lưu tên lớp lỗi, không lưu message, vì message có thể chứa PII hoặc credential. Chi tiết lỗi xem trong log của worker.

### Cấu hình

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `OUTBOX_DISPATCH_INTERVAL_SECONDS` | 10 | Chu kỳ quét của beat (lưới an toàn) |
| `OUTBOX_WAKEUP_ENABLED` | true | Đẩy `outbox.dispatch` ngay sau commit |
| `OUTBOX_BATCH_SIZE` | 50 | Số event tối đa mỗi lần dispatch |
| `OUTBOX_HANDLER_TIMEOUT_SECONDS` | 30 | Timeout mặc định của handler |
| `OUTBOX_LEASE_SECONDS` | 120 | Event đang xử lý mà worker chết sẽ được claim lại sau thời gian này. Phải lớn hơn timeout của handler. |
| `OUTBOX_MAX_ATTEMPTS` | 10 | Số lần thử mặc định của một event |
| `OUTBOX_BACKOFF_BASE_SECONDS` / `OUTBOX_BACKOFF_MAX_SECONDS` | 5 / 3600 | Chờ `base·2^(lần-1)`, tối đa `max`, nhân jitter 50–100 % |
| `OUTBOX_RETENTION_DAYS` | 7 | Giữ event `succeeded` bao lâu |

## 5. Test

Test handler trực tiếp bằng cách gọi `await handler.handle(event, ctx)`. Test luồng đầy đủ thì dùng `OutboxPublisher(wakeup=fake)` và `OutboxDispatcher(engine, registry, clock=…)` trên SQLite; xem mẫu trong [`tests/test_infrastructure/test_outbox.py`](../tests/test_infrastructure/test_outbox.py).
