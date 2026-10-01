# Debug Backend Local với hạ tầng trên Railway

Biến thể của **kịch bản 6** trong [RUN_LOCAL_BACKEND.md](RUN_LOCAL_BACKEND.md): core backend vẫn chạy
bằng terminal trên máy (breakpoint, hot-reload, attach debugger), nhưng **Redis** và
**mock-ev-system** chạy trên **Railway** thay vì Docker local.

Dùng khi:

- máy không chạy nổi / không muốn bật Docker Desktop;
- cả nhóm muốn dùng chung một bộ mock-ev-system + Redis có sẵn, không phải build lại image.

```text
 Máy local                                    Railway (project p146-dev-infra)
 ┌──────────────────────────┐   HTTPS        ┌──────────────────────────────┐
 │ uvicorn src.main:app     │ ─────────────▶ │ mock-ev-system               │
 │ (backend, port 8000)     │                │ https://<x>.up.railway.app   │
 │                          │   TCP (redis)  ├──────────────────────────────┤
 │ celery worker -B         │ ─────────────▶ │ Redis  <x>.proxy.rlwy.net:NN │
 └──────────▲───────────────┘                └──────────────┬───────────────┘
            │ webhook (tuỳ chọn, qua tunnel cloudflared/ngrok)│
            └─────────────────────────────────────────────────┘
```

| Thành phần      | Chạy ở đâu | Ghi chú |
|-----------------|------------|---------|
| Core backend    | Local (terminal) | `uv run uvicorn ...` từ `backend/` |
| Celery worker   | Local (terminal) | Tuỳ chọn — cần khi test đồng bộ ODO |
| mock-ev-system  | Railway | Build từ `backend/mock-ev-system/Dockerfile.railway` |
| Redis           | Railway | Template database Redis, truy cập qua TCP Proxy công khai |
| ChromaDB        | Local (tuỳ chọn) | Chỉ cần khi `VECTOR_STORE=chroma`; mặc định là `pgvector` |

File liên quan:

| File | Vai trò |
|------|---------|
| [scripts/railway-infra.ps1](../scripts/railway-infra.ps1) / [scripts/railway-infra.sh](../scripts/railway-infra.sh) | Tạo project, deploy, lấy biến môi trường |
| [backend/mock-ev-system/Dockerfile.railway](../backend/mock-ev-system/Dockerfile.railway) | Image mock cho Railway (không dùng cache mount, nghe cổng `$PORT`) |
| [.env.railway-debug.example](../.env.railway-debug.example) | Mẫu `.env` (gốc repo) trỏ về Railway |

---

## 1. Yêu cầu

- Tài khoản Railway (gói Hobby/Trial đều được).
- **Railway CLI ≥ 5.x**: `npm i -g @railway/cli`, kiểm tra bằng `railway --version`.
- Đăng nhập một lần: `railway login`.
- `uv` (hoặc venv/pip) để chạy backend như kịch bản 6.

> PowerShell chặn chạy script thì mở quyền cho phiên hiện tại:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

---

## 2. Dựng hạ tầng trên Railway (làm một lần)

> Chỉ **một người** trong nhóm làm mục này. Người khác bỏ qua, sang mục 3 và chạy
> `./scripts/railway-infra.ps1 link` để nối vào project đã có (cần được mời vào project/workspace).

Tất cả lệnh chạy từ **thư mục gốc repo**.

### Bước 1 — Tạo project và link repo

```powershell
./scripts/railway-infra.ps1 init                      # tạo project "p146-dev-infra"
# ./scripts/railway-infra.ps1 init -ProjectName khac  # đặt tên khác
```

### Bước 2 — Tạo Redis + service mock-ev-system

```powershell
./scripts/railway-infra.ps1 setup
```

Script sẽ:

1. thêm database **Redis** (template chính thức, tự sinh mật khẩu, bật sẵn TCP Proxy);
2. tạo service rỗng **`mock-ev-system`** với các biến:

| Biến | Giá trị | Ý nghĩa |
|------|---------|---------|
| `RAILWAY_DOCKERFILE_PATH` | `mock-ev-system/Dockerfile.railway` | Dockerfile dùng khi build (tính từ `backend/`) |
| `PORT` | `8100` | Cổng app lắng nghe, Railway route domain vào đây |
| `MOCK_WEBHOOK_SECRET` | secret HMAC | Lấy `OEM_WEBHOOK_SECRET` trong `.env` (gốc repo); nếu không có hoặc là `change-me` thì sinh ngẫu nhiên và in ra |
| `MOCK_WEBHOOK_USAGE_MIN_INTERVAL_SECONDS` | `300` | Như cấu hình local |

Muốn chỉ định secret: `./scripts/railway-infra.ps1 setup -WebhookSecret <hex>`.

### Bước 3 — Deploy mock-ev-system

```powershell
./scripts/railway-infra.ps1 deploy     # upload backend/ (bỏ qua file trong .gitignore) và build
./scripts/railway-infra.ps1 logs       # theo dõi log, Ctrl+C để thoát
```

Lệnh bên dưới là `railway up ./backend --path-as-root --service mock-ev-system`: build context là
`backend/` (workspace uv, cần `uv.lock` + `shared/ev-contracts`), giống hệt khi build Docker local.

> **Vì sao có `Dockerfile.railway` riêng?** `Dockerfile` gốc dùng `RUN --mount=type=cache`, còn
> builder của Railway từ chối cache mount không có id dạng `s/<service-id>-...`. Bản Railway bỏ
> cache mount và đọc cổng từ `$PORT`. Khi sửa dependency/cấu trúc image, nhớ sửa **cả hai** file.

### Bước 4 — Tạo domain công khai cho mock

```powershell
./scripts/railway-infra.ps1 domain
```

Nhận được URL dạng `https://mock-ev-system-production-xxxx.up.railway.app`. Kiểm tra:

```powershell
curl https://<domain>/health
# Swagger: https://<domain>/docs
```

### Bước 5 — Kiểm tra Redis có TCP Proxy

Trên dashboard Railway: **Redis → Variables** phải có `REDIS_PUBLIC_URL` dạng
`redis://default:<password>@<x>.proxy.rlwy.net:<port>`. Nếu trống: **Redis → Settings →
Networking → TCP Proxy → port 6379**.

> Backend chạy ở máy local **không** dùng được `REDIS_URL` / `redis.railway.internal` — đó là
> mạng private chỉ các service trong Railway thấy được. Luôn dùng host/port của TCP Proxy.

---

## 3. Cấu hình backend local trỏ về Railway

### Bước 1 — Tạo `.env` (gốc repo)

```powershell
Copy-Item .env.railway-debug.example .env    # nếu chưa có .env ở gốc repo
```

### Bước 2 — Lấy biến từ Railway

```powershell
./scripts/railway-infra.ps1 env -Slot 0
```

In ra các dòng để **dán đè** vào `.env` (gốc repo), ví dụ:

```text
OEM_API_BASE_URL=https://mock-ev-system-production-xxxx.up.railway.app
OEM_WEBHOOK_SECRET=3f9c...
REDIS_URL=
REDIS_HOST=roundhouse.proxy.rlwy.net
REDIS_PORT=41234
REDIS_PASSWORD='AbCd...'
REDIS_DB=2
CELERY_BROKER_DB=0
CELERY_BACKEND_DB=1
REDIS_KEY_PREFIX=p146-dev0
REDIS_BROKER_URL=
REDIS_BACKEND_URL=
```

Sau đó điền `OPENAI_API_KEY`, `DATABASE_*` như bình thường.

### Dùng chung Redis trong nhóm — mỗi người một **slot**

Redis có 16 DB (0–15). Backend dùng 3 DB: app cache (`REDIS_DB`), Celery broker
(`CELERY_BROKER_DB`), Celery result (`CELERY_BACKEND_DB`). Nếu hai người dùng chung DB broker,
**Celery worker của người này sẽ lấy task của người kia** — debug sẽ rất khó hiểu.

| Slot | Broker | Result | App cache | Key prefix |
|------|--------|--------|-----------|------------|
| 0 | 0 | 1 | 2 | `p146-dev0` |
| 1 | 3 | 4 | 5 | `p146-dev1` |
| 2 | 6 | 7 | 8 | `p146-dev2` |
| 3 | 9 | 10 | 11 | `p146-dev3` |
| 4 | 12 | 13 | 14 | `p146-dev4` |

Chốt slot cho từng người trong nhóm rồi chạy `env -Slot <n>` tương ứng.

---

## 4. Chạy core backend local

```powershell
cd backend
uv run alembic upgrade head                                          # khi có migration mới
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Hoặc venv/pip: `uvicorn src.main:app --reload --host 0.0.0.0 --port 8000`.

**Debug bằng VS Code** — thêm vào `.vscode/launch.json`:

```json
{
  "name": "Backend (Railway infra)",
  "type": "debugpy",
  "request": "launch",
  "module": "uvicorn",
  "args": ["src.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
  "cwd": "${workspaceFolder}/backend",
  "envFile": "${workspaceFolder}/.env",
  "justMyCode": false
}
```

(Chọn interpreter `backend/.venv` trong VS Code.)

**Celery worker** (terminal thứ hai, khi cần test đồng bộ ODO / job định kỳ):

```powershell
cd backend
uv run celery -A src.celery_tasks worker -B --loglevel=info --pool=solo   # --pool=solo cần trên Windows
```

Worker đọc cùng `.env` (gốc repo) nên tự trỏ vào Redis trên Railway với DB theo slot của bạn.

### Kiểm tra

| Kiểm tra | Lệnh / URL |
|----------|------------|
| Backend | http://localhost:8000/health, http://localhost:8000/docs |
| Mock EV | `https://<mock-domain>/health` |
| Redis từ máy local | `uv run python -c "import redis; from src.config import get_settings; print(redis.from_url(get_settings().redis_connection_url).ping())"` (chạy trong `backend/`) → `True` |

---

## 5. Webhook mock → backend local (tuỳ chọn)

Mock trên Railway **không gọi được** `localhost:8000` của bạn. Có hai lựa chọn:

**A. Không dùng webhook (mặc định)** — `MOCK_WEBHOOK_URL` để trống, mock không gửi gì.
Dữ liệu ODO/lịch sử bảo dưỡng vẫn được đồng bộ qua job poll định kỳ của Celery beat
(`OEM_SYNC_INTERVAL_SECONDS`; đặt `60` trong `.env` (gốc repo) khi debug cho nhanh).

**B. Mở tunnel cho backend local** rồi trỏ mock vào tunnel:

```powershell
# Terminal 3 — một trong hai:
cloudflared tunnel --url http://localhost:8000     # in ra https://<random>.trycloudflare.com
ngrok http 8000                                    # in ra https://<random>.ngrok-free.app

# Trỏ mock tới tunnel (Railway tự redeploy mock, ~1 phút):
./scripts/railway-infra.ps1 webhook -Url https://<random>.trycloudflare.com

# Bắn thử một sự kiện đã ký:
curl -X POST https://<mock-domain>/webhooks/test-events    # xem body mẫu trong Swagger của mock
```

Tắt webhook khi xong việc: `./scripts/railway-infra.ps1 webhook -Url ""`.

> - Mock dùng chung cho cả nhóm nên **tại một thời điểm chỉ một người** nhận được webhook.
> - Backend trả `401 WEBHOOK_SIGNATURE_INVALID` → `OEM_WEBHOOK_SECRET` trong `.env` (gốc repo) khác
>   `MOCK_WEBHOOK_SECRET` trên Railway. Chạy lại `env` để lấy đúng giá trị.
> - URL tunnel `trycloudflare`/ngrok free đổi mỗi lần chạy lại → phải chạy lại lệnh `webhook`.

---

## 6. Vận hành hằng ngày

```powershell
./scripts/railway-infra.ps1 status     # trạng thái project + 5 deployment gần nhất của mock
./scripts/railway-infra.ps1 logs       # log mock-ev-system
./scripts/railway-infra.ps1 deploy     # deploy lại mock sau khi sửa code mock / ev-contracts
```

Script bash tương đương (macOS / Linux / Git Bash) — tham số truyền theo vị trí:

```bash
chmod +x scripts/railway-infra.sh
./scripts/railway-infra.sh init [project-name]
./scripts/railway-infra.sh setup [secret]
./scripts/railway-infra.sh deploy
./scripts/railway-infra.sh domain
./scripts/railway-infra.sh env 0
./scripts/railway-infra.sh webhook https://<random>.trycloudflare.com
./scripts/railway-infra.sh webhook ""
```

---

## 7. Lưu ý

- **Dữ liệu mock là in-memory** (SQLite `sqlite://`) — mỗi lần redeploy/restart mock quay về dữ
  liệu seed. Xe/ODO bạn tạo qua API mock sẽ mất sau khi deploy lại.
- **Email quản lý xưởng**: đặt thêm biến `MOCK_<CENTER_ID>_MANAGER_EMAIL` (vd.
  `MOCK_SC01_MANAGER_EMAIL=you@gmail.com`) cho service mock trên Railway nếu cần đăng nhập Google thật.
- **Bảo mật**: Redis mở ra Internet qua TCP Proxy, chỉ được bảo vệ bằng mật khẩu (không TLS).
  Chỉ dùng cho dữ liệu dev, **không** commit `.env` (gốc repo), không dán mật khẩu vào chat/issue.
  Lộ mật khẩu → xoá và tạo lại service Redis.
- **Độ trễ**: mỗi lệnh Redis đi qua Internet (vài chục ms thay vì <1 ms local). Test hiệu năng,
  lock hoặc rate-limit thì dùng Redis local (kịch bản 6 gốc).
- **Chi phí**: 2 service chạy 24/7 tốn credit. Không dùng lâu thì vào dashboard **Remove** deployment
  của mock (Redis giữ lại), hoặc xoá hẳn project; lần sau chạy lại `deploy`.
- **Không trộn** với `docker-compose.infra.yaml`: nếu vẫn bật Redis/mock bằng Docker, backend chỉ
  dùng cái mà `.env` (gốc repo) đang trỏ tới — kiểm tra `OEM_API_BASE_URL` / `REDIS_HOST` khi thấy lạ.
- **Quay về hạ tầng Docker local**: copy lại `.env.local-debug.example` → `.env` (gốc repo) (hoặc sửa
  các dòng `OEM_*` / `REDIS_*` / `CELERY_*` về `localhost`).
