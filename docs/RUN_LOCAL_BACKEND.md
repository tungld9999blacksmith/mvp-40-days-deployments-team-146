# Chạy Backend Local bằng Docker

Hướng dẫn dựng toàn bộ backend của P-146 trên máy local bằng Docker Compose.
Stack gồm **3 service**, tất cả chạy bằng Docker image:

| # | Service          | Vai trò                                   | Image / Build              | Cổng (host) |
|---|------------------|-------------------------------------------|----------------------------|-------------|
| 1 | `backend`        | FastAPI core — API chính của project      | build `dockerfiles/Dockerfile` | **8000** |
| 2 | `mock-ev-system` | FastAPI giả lập hệ thống hãng xe điện     | build `backend/mock-ev-system/Dockerfile` | **8100** |
| 3 | `redis`          | Cache / locks / pub-sub / queue (bản nhẹ) | `redis:7-alpine`           | **6379** |

> `backend` gọi 2 service kia qua **tên DNS nội bộ** của compose (`mock-ev-system`, `redis`),
> Vector store dùng Qdrant Cloud theo cấu hình `.env`; xem [hướng dẫn Qdrant](../backend/guide/qdrant.md).

---

## 1. Yêu cầu

- **Docker Desktop** đang chạy (Windows/macOS) hoặc Docker Engine + Compose v2 (Linux).
- File **`.env`** ở gốc repo (copy từ `.env.example` rồi điền giá trị — ít nhất là `OPENAI_API_KEY`
  và cấu hình `DATABASE_*` nếu dùng Supabase).
- Biến **`OEM_WEBHOOK_SECRET`** trong `.env` gốc: secret HMAC dùng chung giữa `backend` và
  `mock-ev-system` để ký/kiểm tra webhook (FEAT-VEH-001). Compose truyền **cùng một biến** cho cả hai
  service (`OEM_WEBHOOK_SECRET` → backend, `MOCK_WEBHOOK_SECRET` → mock), nên hai bên luôn khớp.
  Không đặt thì dùng mặc định `change-me` — chỉ chấp nhận ở local. Sinh giá trị ngẫu nhiên:

  ```powershell
  python -c "import secrets; print(secrets.token_hex(32))"
  ```

> Docker Compose đọc `.env` gốc cho cả `env_file` lẫn phép thay biến `${...}`. Nếu một giá trị trong
> `.env` chứa ký tự `$` (vd. mật khẩu), compose coi `$xxx` là biến, cảnh báo
> `The "xxx" variable is not set` và **cắt mất** phần từ `$` trở đi trong container. Bọc giá trị
> trong **dấu nháy đơn** (`DATABASE_PASSWORD='abc$xyz'`) — cách này đúng cho cả compose lẫn backend
> chạy terminal. Không dùng `$$`: backend chạy terminal sẽ đọc thành `$$` và sai mật khẩu.

Kiểm tra nhanh:

```powershell
docker version
docker compose version
```

---

## 2. Chạy nhanh (khuyến nghị dùng script)

### Windows (PowerShell)

```powershell
# Từ thư mục gốc repo
./scripts/dev-stack.ps1 up        # build + chạy nền cả 3 service
./scripts/dev-stack.ps1 ps        # xem trạng thái
./scripts/dev-stack.ps1 logs      # xem log realtime (Ctrl+C để thoát)
./scripts/dev-stack.ps1 down      # dừng + xoá container (giữ dữ liệu)
./scripts/dev-stack.ps1 clean     # dừng + xoá luôn volume (mất dữ liệu)
```

> Nếu PowerShell chặn chạy script, mở quyền cho phiên hiện tại:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

### macOS / Linux / Git Bash

```bash
chmod +x scripts/dev-stack.sh      # lần đầu
./scripts/dev-stack.sh up
./scripts/dev-stack.sh logs
./scripts/dev-stack.sh down
```

---

## 3. Chạy bằng lệnh docker compose trực tiếp

```powershell
# Build + chạy nền
docker compose -f docker-compose.dev.yaml up -d --build

# Xem trạng thái + log
docker compose -f docker-compose.dev.yaml ps
docker compose -f docker-compose.dev.yaml logs -f

# Dừng (giữ volume) / Dọn sạch (xoá volume)
docker compose -f docker-compose.dev.yaml down
docker compose -f docker-compose.dev.yaml down -v
```

---

## 4. Kiểm tra sau khi chạy

| Thành phần        | URL kiểm tra                                   |
|-------------------|------------------------------------------------|
| Backend health    | http://localhost:8000/health                   |
| Backend Swagger   | http://localhost:8000/docs                      |
| Mock EV health    | http://localhost:8100/health                    |
| Mock EV Swagger   | http://localhost:8100/docs                      |
| Redis             | `docker exec -it p146_redis redis-cli ping` → `PONG` |

Test nhanh bằng PowerShell:

```powershell
curl http://localhost:8000/health
curl http://localhost:8100/health
curl http://localhost:8001/api/v2/heartbeat
docker exec -it p146_redis redis-cli ping
```

---

## 5. Ghi chú

- **Database**: stack này **không** dựng Postgres local. Backend đọc `DATABASE_*` từ `.env`
  (mặc định trỏ Supabase). Nếu chưa cấu hình DB, backend fallback về SQLite tại `data/app.db`.
- **Thứ tự khởi động**: `backend` chờ `redis` healthy + `mock-ev-system` healthy trước khi lên
  (khai báo qua `depends_on`), nên lần `up` đầu có thể mất thêm ~20–30s.
- **Đổi cổng**: sửa phần `ports` trong `docker-compose.dev.yaml`. Nếu đổi cổng nội bộ của
  redis/mock-ev, nhớ cập nhật `environment` của service `backend` tương ứng.
- **Rebuild sau khi đổi code**: `./scripts/dev-stack.ps1 build` hoặc thêm `--build` khi `up`.
- **Migration**: stack không tự chạy Alembic. Sau khi kéo code có migration mới (vd. bảng đồng bộ
  ODO/lịch sử bảo dưỡng của US-017), chạy `cd backend && uv run alembic upgrade head`.
- **Webhook hãng xe → backend**: `mock-ev-system` tự gửi webhook có chữ ký tới
  `http://backend:8000/api/v1/integrations/oem/webhooks` khi ODO/lịch sử bảo dưỡng thay đổi.
  Bắn thử một sự kiện: `POST http://localhost:8100/webhooks/test-events` (xem Swagger của mock).
  Backend trả `401 WEBHOOK_SIGNATURE_INVALID` nghĩa là secret hai bên không khớp.
- **Celery worker chưa có trong stack**: webhook chỉ xếp task vào Redis, còn việc kéo dữ liệu từ
  hãng (và job đồng bộ định kỳ mỗi `OEM_SYNC_INTERVAL_SECONDS`) do Celery worker + beat chạy.
  Không có worker thì task nằm chờ trong Redis, ODO không được cập nhật. Chạy worker trên host
  (trỏ Redis đã expose ra `localhost:6379`):

  ```powershell
  cd backend
  uv run celery -A src.celery_tasks worker -B --loglevel=info --pool=solo   # --pool=solo cần trên Windows
  ```

  Worker lấy broker từ `REDIS_BROKER_URL` / `REDIS_BACKEND_URL`; để trống thì tự ghép từ
  `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` với DB `CELERY_BROKER_DB` (0) và
  `CELERY_BACKEND_DB` (1). Container `backend` đã được compose đặt `REDIS_HOST=redis`.

---

## 6. Chế độ Debug — backend chạy bằng terminal, hạ tầng vẫn chạy Docker

Dùng khi bạn cần breakpoint / hot-reload native / attach debugger (VS Code, PyCharm...)
cho backend, nhưng vẫn muốn Redis, mock-ev-system chạy sẵn qua Docker.

File riêng: **`docker-compose.infra.yaml`** — chỉ có 2 service (**không** có `backend`):

| Service          | Cổng host                     |
|------------------|--------------------------------|
| `mock-ev-system` | 8100                           |
| `redis`          | 6379                           |

### Bước 1 — Khởi động hạ tầng

```powershell
./scripts/infra-stack.ps1 up      # PowerShell
# hoặc
./scripts/infra-stack.sh up       # bash
# hoặc trực tiếp
docker compose -f docker-compose.infra.yaml up -d --build
```

### Bước 2 — Cấu hình backend trỏ về `localhost`

Copy `.env.local-debug.example` → `.env` ở **gốc repo** (backend, frontend và
docker compose chỉ đọc một file `.env` gốc; mẫu đầy đủ theo mục: `.env.example`).
File này đã set sẵn:

```text
OEM_API_BASE_URL=http://localhost:8100
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_BROKER_URL=  # trống → Celery dùng redis://localhost:6379/0 và /1
VECTOR_STORE=qdrant
QDRANT_URL=https://your-cluster.cloud.qdrant.io
QDRANT_API_KEY=your-qdrant-api-key
QDRANT_COLLECTION_NAME=ev_care_knowledge_base
EMBEDDING_PROVIDER=gemini
EMBEDDING_DIMENSIONS=3072
OEM_WEBHOOK_SECRET=change-me
```

> **Webhook ở chế độ debug**: `mock-ev-system` trong `docker-compose.infra.yaml` gửi webhook tới
> backend trên host qua `http://host.docker.internal:8000/...`. Secret của mock lấy từ
> `OEM_WEBHOOK_SECRET` trong `.env` **gốc** (mặc định `change-me`); backend chạy terminal cũng đọc
> chính file đó nên hai phía luôn dùng cùng một secret. Muốn chạy đồng bộ ODO thật thì mở thêm một
> terminal chạy Celery worker như ở mục 5.
>
> Redis và mock dùng `localhost` khi backend chạy trực tiếp. Qdrant Cloud đọc
> `QDRANT_URL` và `QDRANT_API_KEY` trong `.env`, không cần cổng local riêng.

### Bước 3 — Chạy backend bằng terminal (không Docker)

```bash
cd backend

# Cách A — uv
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Cách B — venv/pip thông thường
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Backend giờ chạy như một tiến trình Python bình thường trên host — đặt
breakpoint, attach debugger, hot-reload đều hoạt động — trong khi vẫn gọi
được Redis/mock-ev qua `localhost`.

### Build lại & thay container `mock-ev-system`

Chạy từ **gốc repo**. Chỉ đụng tới `mock-ev-system`, `redis` giữ nguyên.

```powershell
# Cách nhanh: build lại image p146-mock-ev:dev + tạo lại container nếu image/env đổi
docker compose -f docker-compose.infra.yaml up -d --build mock-ev-system

# Build sạch (cache lỗi / đổi dependency) + ép tạo container mới
docker compose -f docker-compose.infra.yaml build --no-cache mock-ev-system
docker compose -f docker-compose.infra.yaml up -d --force-recreate mock-ev-system

# Kiểm tra
docker compose -f docker-compose.infra.yaml ps
docker compose -f docker-compose.infra.yaml logs -f mock-ev-system
curl http://localhost:8100/health
```

Lưu ý:

- **Dữ liệu mock được lưu bền** trên volume `mock_ev_data` (file SQLite `/app/data/mock-ev.db`,
  bật bằng `MOCK_DB_PATH`). Dữ liệu import qua `/admin/import` và xe/chủ xe tạo từ
  `MOCK_DEV_OWNER_EMAILS` **còn nguyên** sau restart, build lại image và `--force-recreate`.
  Chỉ lần chạy đầu (volume trống) mới nạp seed dump.
- **Seed dump được bind mount** từ `backend/mock-ev-system/seed-data/` (read-only), nên dump mới
  tạo bằng `tools/ev_mock_data` **không cần build lại image**. Nhưng vì DB đã có dữ liệu, dump mới
  chỉ được nạp khi reset:

  ```powershell
  # Nạp lại dump vào DB hiện tại (xoá dữ liệu đang có)
  curl -X POST http://localhost:8100/admin/reset

  # Hoặc xoá hẳn volume DB → lần khởi động sau seed lại từ đầu
  docker compose -f docker-compose.infra.yaml stop mock-ev-system
  docker compose -f docker-compose.infra.yaml rm -f mock-ev-system
  docker volume rm p146-infra_mock_ev_data
  docker compose -f docker-compose.infra.yaml up -d mock-ev-system
  ```

- **Đổi model (thêm/sửa cột)**: bảng mới được tự tạo, nhưng cột mới trên bảng cũ thì **không** —
  khi đó chạy `/admin/reset` hoặc xoá volume như trên.
- `down` giữ volume; `down -v` (hoặc `./scripts/infra-stack.ps1 clean`) xoá luôn dữ liệu mock và Redis.
- **Biến môi trường** (`OEM_WEBHOOK_SECRET`, `MOCK_*_EMAIL`, `MOCK_DEV_OWNER_EMAILS`, …) được
  compose đọc từ `.env` gốc. Chỉ sửa `.env` (không đổi code) thì không cần build, nhưng phải
  chạy `up -d` (hoặc `--force-recreate`) để container nhận giá trị mới.
- **Dọn image cũ**: sau nhiều lần build sẽ còn image `<none>` → `docker image prune -f`.
- **Build không qua compose** (ít dùng) — phải chạy từ `backend/` vì build context là workspace
  uv:

  ```powershell
  cd backend
  docker build -f mock-ev-system/Dockerfile -t p146-mock-ev:dev .
  ```

  Sau đó vẫn cần `docker compose -f docker-compose.infra.yaml up -d mock-ev-system` để thay
  container.

### Dừng hạ tầng

```powershell
./scripts/infra-stack.ps1 down    # giữ volume
./scripts/infra-stack.ps1 clean   # xoá luôn volume
```

Không muốn chạy Docker? Đưa Redis + mock-ev-system lên **Railway** và vẫn debug backend
bằng terminal như trên — xem [RUN_LOCAL_BACKEND_RAILWAY.md](RUN_LOCAL_BACKEND_RAILWAY.md).

> Không chạy đồng thời `docker-compose.dev.yaml` (full stack, có backend) và
> `docker-compose.infra.yaml` (chỉ infra) — cả hai đều cố chiếm cổng 8100/6379/8001.
> Dừng cái đang chạy trước khi chuyển sang cái khác.
