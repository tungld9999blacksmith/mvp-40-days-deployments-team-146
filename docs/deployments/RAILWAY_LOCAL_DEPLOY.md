# Deploy Backend lên Railway từ máy local (`railway-deploy`)

Script deploy `backend`, `worker`, `mock-ev-system` lên Railway (mặc định environment `staging`) **từ máy local**, chạy đúng các bước của job `deploy-backend` + `smoke-test` trong [CI/CD](../../.github/workflows/ci-cd.yml), có thêm bước **kiểm tra biến môi trường** trước khi deploy.

Dùng khi:

- deploy thử lần đầu trước khi giao cho CI ([Bước 9](RAILWAY_BACKEND_DEPLOYMENT.MD#bước-9--deploy-thử-từ-local));
- cần đẩy nhanh một bản sửa lên staging mà không chờ merge vào nhánh `staging`;
- đẩy / kiểm tra biến môi trường của `backend` và `worker`;
- kiểm tra staging đang khoẻ hay không (`smoke`).

> Cách deploy **chuẩn** vẫn là merge vào nhánh `staging` để CI chạy test → deploy. Deploy từ local **bỏ qua** lint + pytest, nên tự chạy test trước ([Bước 1](RAILWAY_BACKEND_DEPLOYMENT.MD#bước-1--chạy-test-ở-local)).

| File | Dùng trên |
|---|---|
| [scripts/railway-deploy.ps1](../../scripts/railway-deploy.ps1) | Windows (PowerShell 5.1+) |
| [scripts/railway-deploy.sh](../../scripts/railway-deploy.sh) | macOS / Linux / Git Bash |

Hai bản có cùng chức năng, chỉ khác cách truyền tham số (xem [mục 4](#4-tham-chiếu-lệnh)).

> Không nhầm với [`railway-infra`](../RUN_LOCAL_BACKEND_RAILWAY.md): script đó dựng Redis + mock trên Railway để **chạy backend ở máy local**. `railway-deploy` deploy **chính backend** lên Railway.

---

## Mục lục

1. [Yêu cầu](#1-yêu-cầu)
2. [Lần đầu sử dụng](#2-lần-đầu-sử-dụng)
3. [Quy trình hằng ngày](#3-quy-trình-hằng-ngày)
4. [Tham chiếu lệnh](#4-tham-chiếu-lệnh)
5. [Chi tiết từng lệnh](#5-chi-tiết-từng-lệnh)
6. [Xử lý sự cố](#6-xử-lý-sự-cố)
7. [Lưu ý bảo mật](#7-lưu-ý-bảo-mật)

---

## 1. Yêu cầu

- **Railway CLI ≥ 5.x**: `npm i -g @railway/cli`, kiểm tra bằng `railway --version`.
- **Python** (bản `.sh` dùng để đọc JSON từ Railway CLI; bản `.ps1` không cần).
- Đã được mời vào project Railway và có quyền với environment `staging`.
- Project Railway đã dựng theo [Bước 2 → Bước 5b](RAILWAY_BACKEND_DEPLOYMENT.MD#bước-2--tạo-project-và-environment-trên-railway): có các service `backend`, `worker`, `mock-ev-system`, `Redis` (đúng tên, phân biệt hoa thường).
- File `infrastructure/backend/railway/.railway.env` (chỉ cần cho lệnh `vars`, xem [Bước 6.1](RAILWAY_BACKEND_DEPLOYMENT.MD#61-chuẩn-bị-file-railwayenv)).

> PowerShell chặn chạy script thì mở quyền cho phiên hiện tại:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

Tất cả lệnh chạy từ **thư mục gốc repo**.

---

## 2. Lần đầu sử dụng

### 2.1. Đăng nhập và link project

```powershell
railway login                     # mở trình duyệt để đăng nhập
railway link                      # chọn project -> environment staging
railway status                    # kiểm tra đúng project + staging
```

Hoặc dùng token thay cho `railway login` (xem [Bước 7](RAILWAY_BACKEND_DEPLOYMENT.MD#bước-7--lấy-railway-token)):

```powershell
$env:RAILWAY_API_TOKEN = "<account-token>"
railway link --project <PROJECT_ID> --environment staging
```

### 2.2. Kiểm tra cấu hình

```powershell
./scripts/railway-deploy.ps1 check
```

Kết quả đúng:

```text
[INFO]  Checking variables (staging)...
[OK]    Variables look good.
```

Nếu có `[ERROR]` → sang 2.3.

### 2.3. Đẩy biến môi trường (khi `check` báo thiếu)

1. Rà lại `infrastructure/backend/railway/.railway.env` theo bảng ở [Bước 6.1](RAILWAY_BACKEND_DEPLOYMENT.MD#61-chuẩn-bị-file-railwayenv). Tối thiểu:
   - `APP_ENV=production`
   - `DATABASE_*` / `SUPABASE_*` của Supabase staging
   - `QDRANT_URL`, `QDRANT_API_KEY`
   - `FIREBASE_CREDENTIAL_JSON` (1 dòng, bọc trong `'...'`)
   - không còn giá trị `localhost`
2. Đẩy lên:

   ```powershell
   ./scripts/railway-deploy.ps1 vars
   ./scripts/railway-deploy.ps1 check     # phải hết [ERROR]
   ```

3. Deploy để áp dụng biến mới (`vars` **không** tự redeploy):

   ```powershell
   ./scripts/railway-deploy.ps1 deploy
   ```

---

## 3. Quy trình hằng ngày

```powershell
# 1. Test local (deploy từ local không chạy test)
$env:APP_ENV = "test"; $env:OPENAI_API_KEY = "test-key"
pytest backend/tests -v

# 2. Deploy backend + worker, tự smoke test sau khi xong
./scripts/railway-deploy.ps1 deploy

# 3. (khi có sửa mock-ev-system) deploy cả mock
./scripts/railway-deploy.ps1 deploy all
```

Bash:

```bash
./scripts/railway-deploy.sh deploy
./scripts/railway-deploy.sh deploy all
```

Chỉ muốn xem staging có khoẻ không:

```powershell
./scripts/railway-deploy.ps1 smoke
```

---

## 4. Tham chiếu lệnh

| Lệnh | Việc làm | Thay đổi Railway? |
|---|---|---|
| `check` | Kiểm tra CLI, đăng nhập, link project và biến môi trường của từng service | Không |
| `vars` | Đẩy `.railway.env` + biến tham chiếu Redis lên `backend` và `worker` | Có — ghi biến, **không** redeploy |
| `deploy [target]` | `check` → `railway up` → `smoke` | Có — build và deploy |
| `smoke` | `GET /health` + `GET /api/v1/health/dependencies` | Không |
| `status` | Trạng thái project + 3 deployment gần nhất của mỗi service | Không |
| `logs [service]` | Xem log realtime của 1 service (mặc định `backend`) | Không |

### Target của `deploy`

| Target | Deploy | Ghi chú |
|---|---|---|
| `app` (mặc định) | `backend` → `worker` | Dùng hằng ngày |
| `backend` | `backend` | |
| `worker` | `worker` | Không chạy smoke (worker không có HTTP) |
| `mock` | `mock-ev-system` | Upload `backend/` làm gốc (`--path-as-root`) |
| `all` | `mock-ev-system` → `backend` → `worker` | Giống hệt CI |

### Tham số

| | PowerShell | Bash |
|---|---|---|
| Environment (mặc định `staging`) | `-Environment <tên>` | `RAILWAY_ENV=<tên>` |
| URL backend cho `smoke` (mặc định lấy từ domain public của `backend`) | `-Url https://...` | `BACKEND_URL=https://...` |
| Deploy không qua `check` | `-SkipCheck` | `SKIP_CHECK=1` |
| Service cho `logs` | `-Service worker` | `logs worker` |

Ví dụ:

```powershell
./scripts/railway-deploy.ps1 deploy backend -SkipCheck
./scripts/railway-deploy.ps1 logs -Service worker
./scripts/railway-deploy.ps1 smoke -Url https://backend-staging-xxx.up.railway.app
```

```bash
SKIP_CHECK=1 ./scripts/railway-deploy.sh deploy backend
./scripts/railway-deploy.sh logs worker
BACKEND_URL=https://backend-staging-xxx.up.railway.app ./scripts/railway-deploy.sh smoke
```

---

## 5. Chi tiết từng lệnh

### 5.1. `check`

Đọc biến **đã resolve** của từng service (`railway variable list --json`, gồm cả Shared Variables đã gắn vào service) và kiểm tra:

| Kiểm tra | Service | Mức | Hậu quả nếu sai |
|---|---|---|---|
| Có `RAILWAY_DOCKERFILE_PATH` | backend, worker, mock | ERROR | Railway dùng Railpack → build lỗi |
| Có `PORT` | backend, mock | ERROR | Domain không trỏ đúng cổng |
| `REDIS_HOST` / `REDIS_URL` có và không phải `localhost` | backend, worker | ERROR | `Error 111 connecting to localhost:6379. Connection refused` |
| Có `DATABASE_URL` hoặc `DATABASE_PASSWORD` | backend, worker | ERROR | App dùng SQLite trong container, **mất dữ liệu mỗi lần redeploy** |
| `APP_ENV=production` | backend, worker | ERROR | Bật bypass header `X-User-Id` của dev |
| Có `QDRANT_URL` | backend, worker | WARN | Qdrant lưu local trong container |
| Có `FIREBASE_CREDENTIAL_JSON` | backend, worker | WARN | Lỗi `Firebase credential not found` |
| Biến khác còn chứa `localhost` | backend, worker | WARN | |

Có `[ERROR]` → script thoát mã `1`, `deploy` dừng lại trước khi upload.

### 5.2. `vars`

1. Đọc `infrastructure/backend/railway/.railway.env` (bỏ dòng trống, comment; bỏ 1 cặp nháy bao ngoài giá trị).
2. Dừng nếu `APP_ENV` khác `production`.
3. **Bỏ qua** các biến sau trong file:

   | Biến | Lý do |
   |---|---|
   | `REDIS_URL`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_BROKER_URL`, `REDIS_BACKEND_URL` | Thay bằng biến tham chiếu tới service `Redis` (private network) |
   | `OEM_API_BASE_URL` | Đặt riêng mức service, trỏ vào mock ([Bước 5b](RAILWAY_BACKEND_DEPLOYMENT.MD#bước-5b--tạo-service-mock-ev-system-mock-oem)) |
   | Biến có giá trị rỗng | Để app dùng giá trị mặc định |

4. Đặt cho **cả `backend` và `worker`** (biến mức service), thêm:

   ```text
   REDIS_HOST=${{Redis.REDISHOST}}
   REDIS_PORT=${{Redis.REDISPORT}}
   REDIS_PASSWORD=${{Redis.REDISPASSWORD}}
   ```

5. Xoá `REDIS_URL` trên service nếu còn — `config.py` ưu tiên `REDIS_URL` hơn `REDIS_HOST`.

Ghi chú:

- Giá trị truyền qua **stdin** (`railway variable set KEY --stdin`), không xuất hiện trên command line / lịch sử shell; JSON (`FIREBASE_CREDENTIAL_JSON`) giữ nguyên dấu nháy.
- Dùng `--skip-deploys`: không redeploy sau mỗi biến. Chạy `deploy` để áp dụng. (Riêng bước xoá `REDIS_URL` — nếu có — sẽ kích hoạt 1 lần redeploy.)
- Chạy lại nhiều lần được: biến đã có sẽ bị ghi đè bằng giá trị trong file. Biến **không có** trong file thì giữ nguyên trên Railway.
- Biến được đặt ở **mức service**, không phải Shared Variables. Nếu đặt cùng biến ở cả hai nơi, giá trị mức service thắng.

### 5.3. `deploy`

1. Chạy `check` (bỏ qua bằng `-SkipCheck` / `SKIP_CHECK=1`).
2. Với từng service theo thứ tự của target: `railway up --ci --service <svc> --environment <env> --message "local deploy <commit>"`.
   - `--ci`: stream log build rồi thoát; build lỗi → script dừng, **các service sau không deploy**.
   - `mock-ev-system`: `railway up ./backend --path-as-root ...` (build context là `backend/`).
   - `--message` ghi short hash commit hiện tại, xem được trên dashboard Railway.
3. Nếu target có `backend` → chạy `smoke`.

> `railway up` upload **thư mục làm việc hiện tại**, kể cả thay đổi chưa commit (file trong `.gitignore` bị bỏ qua). Commit hash trong message chỉ để tham khảo.

### 5.4. `smoke`

1. `GET <backend>/health`, thử lại tối đa 10 lần, cách nhau 10 giây (chờ deployment mới lên).
2. `GET <backend>/api/v1/health/dependencies` và in trạng thái từng dependency:

   ```text
   [OK]    /health OK
   [INFO]  GET https://backend-staging-xxx.up.railway.app/api/v1/health/dependencies
     redis     UP      184.3 ms
     qdrant    UP        0.7 ms
     database  UP        1.7 ms  dialect=postgresql
   [OK]    Dependencies OK
   ```

3. Thoát mã `1` nếu `/health` không lên hoặc dependencies `degraded`.
4. In `[WARN]` nếu database là `dialect=sqlite` (app đang dùng fallback, chưa nối Supabase) — dù probe vẫn `UP`.

---

## 6. Xử lý sự cố

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Railway CLI not found` | Chưa cài CLI | `npm i -g @railway/cli` |
| `Not logged in` | Chưa đăng nhập / token hết hạn | `railway login` hoặc đặt lại `RAILWAY_API_TOKEN` |
| `Repo root is not linked` | Chưa `railway link` ở thư mục gốc repo | `railway link` → chọn project + `staging` |
| `Cannot read variables of service 'X'` | Sai tên service hoặc không có quyền | Kiểm tra tên trên dashboard (phân biệt hoa thường) |
| `redis DOWN ... connecting to localhost:6379. Connection refused` | `backend` / `worker` không có `REDIS_HOST` | `vars` rồi `deploy` (hoặc chỉ đặt 3 biến tham chiếu Redis ở 5.2) |
| `redis DOWN ... Error -2 connecting to redis.railway.internal` | Service `Redis` khác project / environment, hoặc đổi tên | Tạo Redis trong cùng environment, giữ tên `Redis` |
| `database UP ... dialect=sqlite` | Thiếu `DATABASE_URL` / `DATABASE_PASSWORD` | Điền `DATABASE_*` trong `.railway.env` → `vars` → `deploy` |
| `APP_ENV must be 'production'` | `APP_ENV` trống hoặc là `staging`/`development` | Đặt `APP_ENV=production` trong `.railway.env` → `vars` |
| Log build có `Railpack could not determine how to build the app` | Thiếu `RAILWAY_DOCKERFILE_PATH` | Xem [Bước 6.4](RAILWAY_BACKEND_DEPLOYMENT.MD#bước-6--biến-môi-trường-trên-railway) |
| `/health did not return 200` | Container crash khi khởi động | `./scripts/railway-deploy.ps1 logs` để xem lỗi |
| `Backend has no public domain` | Chưa Generate Domain cho `backend` | Settings → Networking → Generate Domain, hoặc truyền `-Url` / `BACKEND_URL` |
| PowerShell báo `Missing closing '}'` / ký tự lạ | File script bị lưu kèm ký tự non-ASCII không có BOM | Giữ file `.ps1` chỉ chứa ASCII |

Xem thêm [Xử lý sự cố](RAILWAY_BACKEND_DEPLOYMENT.MD#xử-lý-sự-cố) của tài liệu deploy chính.

---

## 7. Lưu ý bảo mật

- `.railway.env` chứa secret, đã nằm trong `.gitignore` — **không commit**.
- `vars` ghi đè biến trên Railway bằng giá trị trong file local. Rà file trước khi chạy, nhất là khi nhiều người cùng quản lý staging.
- Script không in giá trị biến ra màn hình; khi cần soát biến trên Railway, tránh dán output `railway variable list` vào chat / issue.
- Deploy từ local dùng quyền tài khoản cá nhân. Account Token có **toàn quyền mọi project** — không lưu token vào file trong repo.
