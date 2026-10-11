# Vận hành memory của Agent EV Care

Code triển khai P0–P2 ở nhánh `thaidinh-eval`. Backend thật dùng PostgreSQL cho
checkpoint theo thread, summary theo conversation và preference xuyên thread.
Không backfill sở thích từ lịch sử, không bật embedding chat hoặc thêm vector DB.

## Chuẩn bị và migration

Từ `backend/`, dùng môi trường dependency của dự án:

```powershell
uv sync --all-packages
uv run alembic heads
uv run alembic upgrade head
```

Migration mới `e7c1a9b2d4f6`, parent `c6f2a8d4e9b1`, tạo năm bảng:
`conversation_summary`, `agent_memory_cleanup`, `agent_memory_setting`,
`agent_user_memory`, `agent_memory_source`. Trigger PostgreSQL ghi cleanup task
trước khi conversation bị xóa, kể cả cascade từ user/vehicle. Áp migration trước
khi chạy code mới, bao gồm API quản lý và worker cleanup.

Năm bảng memory bật RLS và không có public policy; backend dùng DB role tin cậy.
Merge revision `f8b2d6a4c1e9` kết hợp memory với nhánh booking phone
`a7e3c1f9d4b2`. Kiểm tra head hiện tại trước upgrade; migration booking đã áp
không cần chạy lại hoặc stamp lùi revision.

Nhánh develop có migration riêng; khi tích hợp nhánh này phải kiểm tra/reconcile
Alembic heads trước khi triển khai. Không tự sửa revision đã được áp trên môi trường khác.
`AsyncPostgresSaver.setup()` tiếp tục quản lý schema checkpoint bằng API thư viện.
Phiên bản saver đã kiểm chứng: `langgraph-checkpoint-postgres==3.1.2`.

## Bật thử nghiệm

Các flags mặc định là `off`/`false`. Ví dụ đặt trong terminal backend trước khi
khởi động; dùng cấu hình `.env` đang có, không thay database hoặc key:

```powershell
$env:AGENT_MEMORY_CONTEXT_MODE = 'shadow'
$env:AGENT_MEMORY_READ_ENABLED = 'false'
$env:AGENT_MEMORY_WRITE_ENABLED = 'false'
```

`shadow` tạo summary và đo context, nhưng giữ input model như baseline ở những
thread chưa compact và chưa recall preference. Sau khi đánh giá đạt, đổi sang:

```powershell
$env:AGENT_MEMORY_CONTEXT_MODE = 'on'
$env:AGENT_MEMORY_READ_ENABLED = 'true'
$env:AGENT_MEMORY_WRITE_ENABLED = 'true'
$env:AGENT_MEMORY_CANARY_USER_IDS = '[11]' # Owner ID kiểm thử; thay đúng môi trường.
```

Khởi động lại backend để nạp Settings. `AGENT_MEMORY_CANARY_USER_IDS` là JSON
list owner IDs từ backend: danh sách không rỗng giới hạn read/write theo tài
khoản; `[]` giữ hành vi global flags. Toggle tài khoản chỉ có thể tắt thêm.
Context mode vẫn áp dụng toàn instance; canary nên chạy ở instance riêng.
Kết quả canary local thực tế nằm trong
[báo cáo rollout](../../docs/plans/AGENT_MEMORY_CANARY_ROLLOUT_20261010.md).

Ngân sách input mặc định **12.000 token ước tính**, bao gồm tool schemas và prompt.
Summary tối đa 1.000, recall tối đa 500; giữ mục tiêu sáu lượt gần nhất, sau đó cắt
theo ngân sách. `AGENT_MEMORY_CONTEXT_WINDOW=32768` và
`AGENT_MEMORY_OUTPUT_RESERVE=2048` phải phù hợp model đang dùng; tăng output reserve
nếu provider được cấu hình sinh nhiều hơn. Counter `cl100k_base` là estimate cho
model không dùng tokenizer đó; provider usage mới là số liệu chính thức. Nếu
tokenizer không tải được, dùng byte UTF-8 làm estimate bảo thủ. Lượt hiện tại quá
lớn bị từ chối rõ ràng, không cắt rời tool-call/tool-result.

## Sử dụng và quản lý preference

Trong chat thật, thử “Hãy nhớ tôi thích đặt lịch chiều thứ Bảy”, rồi mở hội thoại
mới với cùng tài khoản/xe. MVP chỉ hỗ trợ:

- Ngày và buổi bảo dưỡng ưu tiên.
- Xưởng ưu tiên có ID hợp lệ và đang hoạt động.
- Hiển thị chi phí từng hạng mục hoặc tổng tiền.

Yêu cầu ghi nhớ phải bắt đầu rõ ràng bằng “Hãy nhớ”, “Ghi nhớ”, “Nhớ giúp”, hoặc
cụm tương đương được allowlist. Câu hỏi, phủ định và lựa chọn chỉ cho lần này
không tự tạo preference. Server kiểm tra giá trị tool đề xuất khớp lời yêu cầu.
Preference mặc định hết hiệu lực sau 180 ngày; recall không tự gia hạn.
Thông tin ODO/giá/slot/booking được đọc lại bằng tool nghiệp vụ.

Nút **Ghi nhớ** trên màn hình trợ lý dùng HTTP mở UI xem/sửa/xóa và toggle. Tắt
toggle dừng ghi/recall; xóa dữ liệu là thao tác riêng. Sửa ở UI là consent mới,
kiểm tra `version`; sửa cùng phiên bản cũ trả `409 MEMORY_CONFLICT`.

API `/api/v1/agent-memory` bắt buộc Firebase Bearer token; không dùng `X-User-Id`:

| Endpoint | Chức năng |
| --- | --- |
| `GET /agent-memory?vehicle_id=<UUID>` | Danh sách còn hiệu lực, đúng account/xe |
| `GET /agent-memory/workshops` | Xưởng active cho lựa chọn sửa |
| `PATCH /agent-memory/settings` | `{ "enabled": false }` |
| `PATCH /agent-memory/<id>` | `{ "value": { ... }, "version": 1 }` |
| `DELETE /agent-memory/<id>` | Xóa một mục |
| `DELETE /agent-memory` | Xóa tất cả preference của tài khoản, kể cả xe khác |

Không có API nhận `user_id` từ client. Xóa hội thoại nguồn sẽ xóa preference phụ
thuộc nguồn đó; UI edit vẫn giữ liên kết nguồn ban đầu. Xe hết liên kết hoặc đổi
chủ không được recall memory theo xe.

## Cleanup và retention

Xóa hội thoại lấy Redis `conversation-run` lock; đang chạy turn thì trả busy.
Transaction xóa nguồn và ghi outbox; cleanup checkpoint/vector lỗi thì task còn
lại để retry. Inventory gồm mọi message ID để dọn cả vector đã ghi nhưng chưa kịp
commit cờ `embedded`. Cleanup chạy ngay sau delete, hoặc worker/CLI chạy lại.
Worker cleanup cũng lấy run lock để tránh xóa checkpoint trong lúc turn còn ghi.

Từ `backend/`:

```powershell
# Retry cleanup đã được enqueue; thực hiện xóa checkpoint/vectors.
uv run python scripts/agent_memory_maintenance.py cleanup

# Chỉ liệt kê ID hội thoại quá hạn, chưa xóa dữ liệu.
uv run python scripts/agent_memory_maintenance.py purge

# Áp purge sau khi đã đối chiếu dry-run.
uv run python scripts/agent_memory_maintenance.py purge --apply
```

`CHAT_RETENTION_DAYS=180`, `CHAT_PURGE_BATCH=200`; retention dựa vào
`last_message_at`, recheck cutoff trong transaction và bỏ qua thread busy.
Celery Beat enqueue cleanup mỗi 60 giây; purge lúc 03:45 giờ Việt Nam chỉ chạy
khi `AGENT_MEMORY_RETENTION_ENABLED=true`. Chỉ khởi động worker khi cần vận hành
job; yêu cầu “chạy dự án” mặc định không tự bật Celery. CLI cleanup cần kết nối
PostgreSQL, Redis và vector adapter theo cấu hình thật.

Theo dõi kết quả `selected/completed/pending/busy/oldest_selected_seconds` cùng
`attempts/last_error` trong outbox. Lỗi external cleanup không khôi phục row nguồn;
API không thể truy cập lại conversation đã xóa. Không có worker/CLI thì outbox
sẽ chờ, không tự biến mất. Logs memory chỉ ghi IDs, counts và error class.

Preference hết hạn bị loại khỏi recall/list ngay; cleanup job đánh dấu `expired`.
Row hết hạn hiện vẫn lưu trong
DB đến khi người dùng xóa hoặc nguồn bị purge. Đây không phải job xóa vật lý
preference độc lập. Snapshot checkpoint cũ cũng chỉ được xóa theo lifecycle thread,
không bị xóa chỉ vì checkpoint hiện tại đã compact.

## Rollback và kiểm chứng

Không chạy Celery thì có thể dùng runner riêng chỉ cleanup, từ `backend/`:
`python scripts/agent_memory_maintenance.py cleanup --watch --interval 60`.
Runner không chạy retention purge; `purge --watch` bị từ chối. Dùng supervisor
hoặc scheduler ở môi trường hosting để runner tự khởi động lại.

Tắt read/write để dừng preference, vẫn cho người dùng xóa. Đặt context mode `off`
ngừng tạo summary mới. Thread đã compact vẫn đọc summary đã lưu và lịch sử sau
cursor; không downgrade bảng memory vì sẽ mất khả năng recovery và cleanup.

Summary MVP là extractive user quotes có provenance, lọc PII thông dụng, không
gọi LLM để tạo thêm dữ kiện. Nó không giữ toàn bộ quyết định hay toàn bộ tool state
cũ. Pending/interrupt state không compact; recovery không phát lại tool ghi.

Chạy regression bằng `pytest`; test PostgreSQL staging chỉ dùng database local
riêng `memory_test` ở cổng `65432`, biến `MEMORY_TEST_DATABASE_URL`, và
`--run-staging`. Fixture tạo/dọn schema ngẫu nhiên, không đọc DB URL trong `.env`.
Benchmark offline:

```powershell
uv run python scripts/benchmark_agent_memory.py --output ../docs/plans/agent-memory-benchmark.json
```

Thêm `--live` để đo 20 câu recall/override tổng hợp bằng provider đang cấu hình.
Không gọi nghiệp vụ hoặc ghi database. Lỗi authentication dừng sớm và không
được tính thành accuracy. Chi tiết kết quả ngày 10/10 nằm trong
[báo cáo triển khai](../../docs/plans/AGENT_MEMORY_IMPLEMENTATION_REPORT.md).

Endpoint `mistral/us` đã kiểm chứng trả lời được khi pool mặc định gặp 429:

```powershell
uv run python scripts/benchmark_agent_memory.py --live --endpoint mistral/us --json-output --output ../docs/plans/agent-memory-us.json
```

`--endpoint` pin `provider.only` và không fallback trong benchmark; kiểm tra giá
endpoint trước khi gọi. `--json-output` yêu cầu JSON cho máy chấm, chỉ áp dụng
benchmark. Bỏ flag này để giữ định dạng text baseline. Có thể chạy probe nhỏ bằng
`uv run python scripts/probe_memory_endpoints.py` trước; script dùng tối đa ba
endpoint khác, mỗi request tối đa 64 output token và chỉ dùng dữ liệu tổng hợp.

Khi muốn ưu tiên cùng endpoint cho backend thật, đặt trong terminal backend
trước khi khởi động:

```powershell
$env:OPENROUTER_AGENT_ENDPOINT_ORDER = 'mistral/us'
```

Runtime hiện dùng `provider.order`, vẫn cho phép fallback; khác routing cố định
của benchmark. Cấu hình này áp dụng agent/orchestrator, không thay routing RAG
hoặc rewrite. Không áp JSON response format của benchmark vào chat nghiệp vụ.
