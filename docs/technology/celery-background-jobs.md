# Celery: tác vụ nền

> Cập nhật: 2026-10-12. Cấu hình ở `backend/src/celery_tasks.py`, tác vụ ở `backend/src/infrastructure/celery/tasks/`. Bảng lịch đầy đủ: [architecture.md §6](../architecture.md#6-tác-vụ-nền-celery).

## 1. Vai trò

Celery worker + beat chạy cùng mã nguồn và cùng DB với API. Broker/backend là Redis (DB 0/1). Việc nặng, có lịch, hoặc không được chặn request đều đi qua đây.

| Nhóm | File tasks | Ví dụ |
| --- | --- | --- |
| OEM | `oem_sync_tasks.py` | `oem.sync_all_vehicles`, `oem.sync_vehicle` (retry 30 → 120 → 600 giây) |
| Nhắc bảo dưỡng | `reminder_tasks.py` | `reminder.send_all` 08:00, `reminder.dispatch_due`, `reminder.retry_emails` |
| Lịch hẹn, dòng giá | `booking_tasks.py` | `booking.cancel_unconfirmed`, `booking_reminder.send_due`, `booking_line.*` |
| CRM | `crm_tasks.py` | `follow_up.send_due`, `follow_up.close_expired` |
| Xưởng, đăng nhập | `workshop_tasks.py`, `workshop_auth_tasks.py`, `auth_tasks.py` | verify retry, reconcile, thu hồi phiên Firebase |
| Embedding | `embedding_tasks.py` | `embedding.index_message` |
| Agent memory | `memory_tasks.py` | `agent_memory.cleanup`, `agent_memory.retention` |
| Outbox | `outbox_tasks.py` | `outbox.dispatch`, `outbox.purge` |
| Demo | `demo_tasks.py` | `demo_account.reset_if_due` (chỉ khi `DEMO_LOGIN_ENABLED`) |

Lịch `oem.sync_all_vehicles` chỉ đăng ký khi ODO không ở chế độ giả lập tĩnh (`uses_static_odometer()` là false).

## 2. Thêm tác vụ

1. Viết task trong file phù hợp, tên dạng `<nhóm>.<việc>`, dùng `acks_late=True` và `max_retries` hữu hạn nếu việc có side effect.
2. Lịch định kỳ thì thêm vào `beat_schedule` ở `celery_tasks.py` (đã đặt múi giờ `Asia/Ho_Chi_Minh`).
3. Task phải **idempotent**: chạy lại không gây hậu quả (hàng đợi at-least-once; hai beat chạy cùng lúc sẽ gửi trùng nên chỉ chạy **một** beat).
4. Việc phụ gắn với một thay đổi nghiệp vụ và không được mất → dùng [outbox](../../backend/guide/outbox.md) thay vì enqueue trực tiếp sau commit.

## 3. Enqueue từ trong request

`FAIL_FAST_PUBLISH` (`celery_tasks.py`) ép retry 1 lần với backoff ngắn: nếu không, Redis chết làm request treo ~2 phút do result backend thử kết nối lại 20 lần. Task fire-and-forget (ví dụ thu hồi phiên khi đăng xuất) dùng tuỳ chọn này.

## 4. Pool và Windows

Trên Railway worker dùng pool `prefork`. Local Windows dùng `solo`/`threads` (không chạy được `-B`, chạy beat riêng nếu cần). Telemetry của worker khởi tạo trong từng tiến trình con sau khi fork (`worker_process_init`) vì thread của exporter OTel không sống qua fork; pool không fork thì khởi tạo ngay ở `worker_init`.

## 5. Log và quan sát

Worker log JSON ra stdout (đã che PII), file `worker`, gắn `trace_id`. Trace OTel đi theo message Celery (`traceparent`). Run LLM của worker ghi vào project LangSmith `<project>-jobs`. Xem [observability.md](observability.md).

## 6. Biến cấu hình thường dùng

`OEM_SYNC_INTERVAL_SECONDS`, `REMINDER_JOB_HOUR`, `BOOKING_REMINDER_JOB_INTERVAL_MINUTES`, `OUTBOX_*`, `DEMO_LOGIN_ENABLED`, `AGENT_MEMORY_RETENTION_ENABLED`.
