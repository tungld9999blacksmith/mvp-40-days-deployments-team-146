# Deploy Backend lên Railway (staging) bằng GitHub Actions

Hướng dẫn step-by-step để dựng CI/CD cho backend: **unit test → deploy lên Railway → smoke test**, chạy tự động khi merge vào nhánh `staging`.

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Các file liên quan](#2-các-file-liên-quan)
3. [Bước 1 — Chạy test ở local](#bước-1--chạy-test-ở-local)
4. [Bước 2 — Tạo Project và Environment trên Railway](#bước-2--tạo-project-và-environment-trên-railway)
5. [Bước 3 — Tạo Redis](#bước-3--tạo-redis)
6. [Bước 4 — Tạo service `backend`](#bước-4--tạo-service-backend)
7. [Bước 5 — Tạo service `worker`](#bước-5--tạo-service-worker)
   - [Bước 5b — Tạo service `mock-ev-system` (mock OEM)](#bước-5b--tạo-service-mock-ev-system-mock-oem)
8. [Bước 6 — Biến môi trường trên Railway](#bước-6--biến-môi-trường-trên-railway)
9. [Bước 7 — Lấy Railway token](#bước-7--lấy-railway-token)
10. [Bước 8 — Cấu hình GitHub Environment `staging`](#bước-8--cấu-hình-github-environment-staging)
11. [Bước 9 — Deploy thử từ local](#bước-9--deploy-thử-từ-local)
12. [Bước 10 — Push workflow và chạy CI/CD](#bước-10--push-workflow-và-chạy-cicd)
13. [Bước 11 — Branch protection](#bước-11--branch-protection)
14. [Bước 12 — Khoá environment `staging` theo branch](#bước-12--khoá-environment-staging-theo-branch)
15. [Bước 13 — Self-hosted runner (tuỳ chọn, hiện không dùng)](#bước-13--self-hosted-runner-tuỳ-chọn-hiện-không-dùng)
16. [Bước 14 — Luồng test → check → deploy theo branch](#bước-14--luồng-test--check--deploy-theo-branch)
17. [Lưu ý khi dùng GitHub-hosted runner](#lưu-ý-khi-dùng-github-hosted-runner)
18. [Xử lý sự cố](#xử-lý-sự-cố)
19. [Việc còn tồn đọng](#việc-còn-tồn-đọng)

---

## 1. Tổng quan

### Luồng CI/CD

```
PR / merge vào develop ──► backend-test (ruff + pytest)
PR vào staging         ──► backend-test
merge vào staging      ──► backend-test ──► deploy-backend ──► smoke-test
                                            (railway up      (GET /health)
                                             backend+worker)
```

| Sự kiện | `backend-test` | `deploy-backend` + `smoke-test` |
|---|---|---|
| PR mở vào `develop` | ✅ | ❌ |
| Merge (push) vào `develop` | ✅ | ❌ |
| PR mở vào `staging` | ✅ | ❌ |
| Merge (push) vào `staging` | ✅ | ✅ |
| Run workflow thủ công trên `staging` | ✅ | ✅ |

- Workflow **chỉ chạy** khi commit có thay đổi trong `backend/**`, `dockerfiles/**` hoặc `.github/workflows/ci-cd.yml`.
- Test fail thì **không deploy**.
- Runner: **chỉ dùng GitHub-hosted `ubuntu-latest`** cho cả chạy thử, test, check và deploy (miễn phí: repo public không giới hạn, repo private 2.000 phút/tháng). Không cài, không đăng ký self-hosted runner. Xem [Lưu ý khi dùng GitHub-hosted runner](#lưu-ý-khi-dùng-github-hosted-runner).

### Kiến trúc trên Railway (environment `staging`)

```
Railway project
└── environment: staging
    ├── backend         (FastAPI, dockerfiles/Dockerfile.railway, public domain, port 8000)
    ├── worker          (Celery worker + beat, cùng Dockerfile, không có domain)
    ├── mock-ev-system  (mock hệ thống hãng xe / OEM, port 8100,
    │                    private network mock-ev-system.railway.internal)
    └── Redis           (Railway database, private network redis.railway.internal)

Database Postgres: Supabase (bên ngoài Railway)
```

---

## 2. Các file liên quan

| File | Vai trò |
|---|---|
| [`.github/workflows/ci-cd.yml`](../../.github/workflows/ci-cd.yml) | Workflow CI/CD |
| [`dockerfiles/Dockerfile.railway`](../../dockerfiles/Dockerfile.railway) | Image deploy lên Railway, dùng chung cho `backend` và `worker` (không cache mount, nghe trên `$PORT`) |
| [`backend/mock-ev-system/Dockerfile.railway`](../../backend/mock-ev-system/Dockerfile.railway) | Image deploy `mock-ev-system` lên Railway (build context là `backend/`) |
| [`scripts/build-backend-railway.ps1`](../../scripts/build-backend-railway.ps1) / [`.sh`](../../scripts/build-backend-railway.sh) | Build / chạy / smoke test 2 image Railway ở local |
| [`dockerfiles/Dockerfile`](../../dockerfiles/Dockerfile) | Image cho docker compose ở local (có cache mount của uv) |
| [`backend/src/config.py`](../../backend/src/config.py) | Đọc cấu hình: **biến môi trường > file `.env` > giá trị mặc định** |
| [`backend/src/infrastructure/firebase/oauth/setup.py`](../../backend/src/infrastructure/firebase/oauth/setup.py) | Firebase Admin: đọc file JSON, không có file thì đọc `FIREBASE_CREDENTIAL_JSON` |
| [`infrastructure/backend/railway/.railway.example.env`](../../infrastructure/backend/railway/.railway.example.env) | Mẫu biến môi trường cho Railway (commit) |
| `infrastructure/backend/railway/.railway.env` | Biến môi trường thật cho Railway — **chứa secret, đã git ignore, KHÔNG commit** |

> **Không bao giờ commit** `.env`, `.railway.env` và file `backend/src/assets/secrets/*.json` (Firebase service account). Tất cả đã nằm trong `.gitignore`.

---

## Bước 1 — Chạy test ở local

CI chạy đúng các lệnh này, local không xanh thì CI cũng không xanh:

```bash
pip install -r backend/requirements.txt
ruff check backend/src backend/tests
APP_ENV=test OPENAI_API_KEY=test-key pytest backend/tests -v
```

PowerShell:

```powershell
$env:APP_ENV = "test"; $env:OPENAI_API_KEY = "test-key"
pytest backend/tests -v
```

---

## Bước 2 — Tạo Project và Environment trên Railway

1. Vào [railway.com](https://railway.com) → **New Project** → **Empty Project**.
2. Góc trên màn hình project, mở menu environment (mặc định `production`) → **New Environment** → đặt tên **`staging`**.
3. Từ đây trở đi **mọi thao tác đều làm khi đang chọn environment `staging`**.

---

## Bước 3 — Tạo Redis

1. **+ Create** → **Database** → **Add Redis**.
2. **Giữ nguyên tên service là `Redis`** — các biến `${{Redis.REDISHOST}}`... tham chiếu theo đúng tên này. Đổi tên thì phải sửa lại các biến ở Bước 6.

---

## Bước 4 — Tạo service `backend`

1. **+ Create** → **Empty Service** → đổi tên thành `backend`.
   Không nối GitHub repo — code được đẩy lên qua `railway up` trong CI.
2. Tab **Settings**:
   - **Networking** → **Generate Domain**, Target Port = `8000`. Ghi lại URL (vd `https://backend-staging-xxx.up.railway.app`).
   - **Deploy** → **Healthcheck Path** = `/health`.
   - **Deploy** → **Restart Policy** = `On Failure`.

---

## Bước 5 — Tạo service `worker`

1. **+ Create** → **Empty Service** → đổi tên thành `worker`.
2. **Settings** → **Deploy** → **Custom Start Command**:

   ```
   celery -A src.celery_tasks worker -B -l info
   ```

   - `-B` chạy luôn Celery beat trong worker để các job định kỳ (OEM sync, reminder, purge onboarding...) hoạt động.
   - **Chỉ để 1 replica** — nhiều replica cùng `-B` sẽ chạy trùng job định kỳ.
3. Không Generate Domain, không đặt Healthcheck (worker không phục vụ HTTP).

---

## Bước 5b — Tạo service `mock-ev-system` (mock OEM)

Mock giả lập hệ thống hãng xe (OEM). `backend` và `worker` gọi nó qua private network, mock gửi webhook ngược về domain public của `backend`.

1. Tạo service kèm biến (chạy ở thư mục gốc repo, đã `railway link` vào `staging`). Dùng **nháy đơn** để shell không xử lý `${{...}}`:

   ```bash
   railway add --service mock-ev-system \
     --variables 'RAILWAY_DOCKERFILE_PATH=mock-ev-system/Dockerfile.railway' \
     --variables 'PORT=8100' \
     --variables 'MOCK_WEBHOOK_SECRET=${{shared.OEM_WEBHOOK_SECRET}}' \
     --variables 'MOCK_WEBHOOK_URL=https://${{backend.RAILWAY_PUBLIC_DOMAIN}}/api/v1/integrations/oem/webhooks' \
     --variables 'MOCK_WEBHOOK_USAGE_MIN_INTERVAL_SECONDS=300'
   ```

   - `RAILWAY_DOCKERFILE_PATH` tính từ `backend/` (không phải gốc repo), vì mock được upload với `backend/` làm gốc (xem bước 3).
   - `MOCK_WEBHOOK_SECRET` phải bằng `OEM_WEBHOOK_SECRET` của backend, nên tham chiếu thẳng shared variable (Bước 6.4).
   - Các biến tuỳ chọn `MOCK_SC0x_MANAGER_EMAIL`, `MOCK_OWN001_EMAIL`, `MOCK_DEV_OWNER_EMAILS`... (xem `.railway.example.env`) đặt trên service này nếu cần.
2. **Settings** → **Deploy** → **Healthcheck Path** = `/health`. Không cần Generate Domain (chỉ bật khi muốn gọi mock từ ngoài để debug, Target Port = `8100`).
3. Deploy lần đầu — upload thư mục `backend/` làm gốc:

   ```bash
   railway up ./backend --path-as-root --service mock-ev-system
   ```

   Private domain `mock-ev-system.railway.internal` chỉ được cấp sau lần deploy đầu; trước đó biến tham chiếu tới nó resolve thành rỗng (`http://:8100`).
4. Trỏ `backend` và `worker` vào mock (biến **mức service**, xem 6.4):

   ```bash
   railway variables --service backend --set 'OEM_API_BASE_URL=http://${{mock-ev-system.RAILWAY_PRIVATE_DOMAIN}}:8100'
   railway variables --service worker  --set 'OEM_API_BASE_URL=http://${{mock-ev-system.RAILWAY_PRIVATE_DOMAIN}}:8100'
   ```

   Mock nghe trên `::` (IPv4 + IPv6) nên gọi được qua private network.

> Log mock có `Webhook ... not delivered: HTTP 404` khi `backend` chưa có deploy nào — bình thường, hết khi backend chạy.

---

## Bước 6 — Biến môi trường trên Railway

### 6.1. Chuẩn bị file `.railway.env`

File `infrastructure/backend/railway/.railway.env` = toàn bộ biến **backend** trong `.env` gốc + nội dung Firebase service account JSON (1 dòng, biến `FIREBASE_CREDENTIAL_JSON`). Các biến `VITE_*` (frontend) đã bỏ.

Thành viên mới: copy từ mẫu rồi điền giá trị:

```bash
cp infrastructure/backend/railway/.railway.example.env infrastructure/backend/railway/.railway.env
```

Trước khi dán lên Railway, **rà lại các giá trị**:

| Biến | Giá trị trên staging |
|---|---|
| `APP_ENV` | `production` — config chỉ nhận `development` / `production` / `test`. Đặt `staging` app sẽ lỗi validate; giá trị khác `production` còn bật bypass header `X-User-Id` của dev |
| `CORS_ORIGINS`, `FRONTEND_URL` | Domain frontend staging thật |
| `OEM_API_BASE_URL` | **Xoá khỏi `.railway.env`** — đặt ở mức service `backend`/`worker` trỏ vào mock (Bước 5b) |
| `DATABASE_*`, `SUPABASE_*` | Supabase của staging |
| `FIREBASE_CREDENTIAL_JSON` | Nội dung file service account JSON, 1 dòng, bọc trong `'...'` |
| Mọi giá trị `localhost` | Đổi sang địa chỉ thật |

### 6.2. Firebase credential

- **Local:** đặt file JSON trong `backend/src/assets/secrets/` và `FIREBASE_CREDENTIAL=<tên file>` trong `.env` như cũ.
- **Railway:** không có file (`railway up` bỏ qua file trong `.gitignore`) → `setup.py` đọc `FIREBASE_CREDENTIAL_JSON`.
- Thiếu cả hai → app báo lỗi `Firebase credential not found ...`.

### 6.3. Redis / Celery

Theo [`config.py`](../../backend/src/config.py), `REDIS_URL` **chỉ dùng cho cache/lock/pub-sub**, Celery đọc `REDIS_BROKER_URL` / `REDIS_BACKEND_URL`. Cách đơn giản và an toàn nhất là **dùng biến lẻ**, để code tự ghép URL và tách DB (cache = 2, broker = 0, result backend = 1):

```env
REDIS_URL=
REDIS_HOST=${{Redis.REDISHOST}}
REDIS_PORT=${{Redis.REDISPORT}}
REDIS_PASSWORD=${{Redis.REDISPASSWORD}}
REDIS_DB=2
REDIS_KEY_PREFIX=p146
REDIS_DEFAULT_CACHE_TTL=300
CELERY_BROKER_DB=0
CELERY_BACKEND_DB=1
# KHÔNG đặt REDIS_BROKER_URL / REDIS_BACKEND_URL
```

> ⚠️ Đừng chỉ đặt `REDIS_URL=${{Redis.REDIS_URL}}` mà bỏ trống biến lẻ: cache chạy được nhưng Celery vẫn nối `localhost` → lỗi.

### 6.4. Dán biến lên Railway

1. **Khối Redis (6.3)** → dán vào **Variables → Raw Editor của TỪNG service** `backend` **và** `worker` (biến tham chiếu `${{Redis...}}` đặt ở mức service). Cả 2 service đều cần Redis: backend đẩy task, worker nhận task.
2. **Phần còn lại của `.railway.env`** → **Project Settings → Shared Variables → `staging` → Raw Editor** → dán → **Update Variables**. Sau đó vào từng service → **Variables** → **Shared Variable** → gắn tất cả.
3. Thêm riêng cho **cả 2 service**:

   | Biến | Giá trị | Service |
   |---|---|---|
   | `RAILWAY_DOCKERFILE_PATH` | `dockerfiles/Dockerfile.railway` | backend, worker |
   | `PORT` | `8000` | backend |

   Hoặc đặt bằng CLI (sau khi `railway link`):

   ```powershell
   railway variables --service backend --environment staging --set "RAILWAY_DOCKERFILE_PATH=dockerfiles/Dockerfile.railway" --set "PORT=8000"
   railway variables --service worker  --environment staging --set "RAILWAY_DOCKERFILE_PATH=dockerfiles/Dockerfile.railway"
   ```

   > ⚠️ 2 biến này **không có** trong `.railway.env`, dán file đó lên là chưa đủ. Thiếu `RAILWAY_DOCKERFILE_PATH` thì Railway không thấy Dockerfile ở thư mục gốc, chuyển sang Railpack và build lỗi `Railpack could not determine how to build the app`.

---

## Bước 7 — Lấy Railway token

Có 2 loại token. Workflow hiện tại dùng **Account Token**.

| | Account Token (đang dùng) | Project Token (khuyến nghị lâu dài) |
|---|---|---|
| Lấy ở đâu | Avatar → **Account Settings** → **Tokens** | Project → **Settings** → **Tokens** (chọn environment `staging`) |
| Biến CLI đọc | `RAILWAY_API_TOKEN` | `RAILWAY_TOKEN` |
| Quyền | **Toàn quyền mọi project** trong tài khoản | Chỉ 1 environment của 1 project |
| Cần `railway link` | Có (cần `RAILWAY_PROJECT_ID`) | Không |

### Lấy Account Token

1. Avatar (góc trên phải) → **Account Settings** → **Tokens**.
2. Đặt tên rõ ràng, vd `github-ci` → **Create** → **copy ngay** (chỉ hiện 1 lần).

### Lấy Project ID

- Từ URL: `https://railway.com/project/`**`<PROJECT_ID>`**`/...`
- Hoặc: Project → **Settings** → **General** → **Project ID**.

### Kiểm tra token ở local (PowerShell)

```powershell
npm i -g @railway/cli
$env:RAILWAY_API_TOKEN = "<account-token>"
railway whoami                                            # in ra email tài khoản
railway link --project <PROJECT_ID> --environment staging
railway status                                            # đúng project + staging
```

> Muốn chuyển sang **Project Token**: đổi secret thành `RAILWAY_TOKEN`, đổi `RAILWAY_API_TOKEN` → `RAILWAY_TOKEN` trong workflow và xoá bước `railway link`. Không để cả `RAILWAY_TOKEN` lẫn `RAILWAY_API_TOKEN` cùng tồn tại.

---

## Bước 8 — Cấu hình GitHub Environment `staging`

GitHub repo → **Settings** → **Environments** → **New environment** → `staging`:

| Loại | Tên | Giá trị |
|---|---|---|
| Secret | `RAILWAY_API_TOKEN` | Account Token (Bước 7) |
| Variable | `RAILWAY_PROJECT_ID` | Project ID (Bước 7) |
| Variable | `RAILWAY_BACKEND_SERVICE` | `backend` |
| Variable | `RAILWAY_WORKER_SERVICE` | `worker` |
| Variable | `RAILWAY_MOCK_SERVICE` | `mock-ev-system` |
| Variable | `BACKEND_STAGING_URL` | Domain ở Bước 4, vd `https://backend-staging-xxx.up.railway.app` (**không** có `/` cuối) |

Tên service phải khớp chính xác (phân biệt hoa thường) với tên trên Railway.

---

## Bước 9 — Deploy thử từ local

Deploy tay 1 lần để chắc Railway build được trước khi giao cho CI. Chạy ở **thư mục gốc repo**:

```bash
railway login
railway link                       # chọn project → environment staging
railway variables --service backend | grep RAILWAY_DOCKERFILE_PATH   # phải có (Bước 6.4)
railway variables --service worker  | grep RAILWAY_DOCKERFILE_PATH
railway up --service backend
railway up --service worker
railway up ./backend --path-as-root --service mock-ev-system   # chỉ khi mock-ev-system có thay đổi
curl https://<domain-backend>/health
```

Kiểm tra:

- `/health` trả `200`.
- `GET /api/v1/health/dependencies` → Redis `up`.
- Log `worker` có dòng `Connected to redis://default:**@redis.railway.internal:6379/0`.
- Log build chạy các bước của Dockerfile. Nếu thấy `railpack prepare` / `Railpack could not determine how to build the app` → service thiếu `RAILWAY_DOCKERFILE_PATH`, đặt lại theo Bước 6.4 rồi chạy lại `railway up`.

---

## Bước 10 — Push workflow và chạy CI/CD

```bash
git checkout staging
git add .github/ .gitignore backend/src/infrastructure/firebase/oauth/setup.py \
        infrastructure/backend/railway/.railway.example.env docs/deployments/
git status                          # đảm bảo KHÔNG có .env / .railway.env / *.json secret
git commit -m "ci: deploy backend to Railway staging via GitHub Actions"
git push origin staging
```

Theo dõi ở tab **Actions**: `backend-test` → `deploy-backend` → `smoke-test` đều xanh là xong.

Từ đây quy trình hằng ngày:

```
feature branch ──PR──► develop (test) ──PR──► staging (test) ──merge──► deploy staging
```

---

## Bước 11 — Branch protection

GitHub → **Settings** → **Branches** → **Add branch ruleset** cho `develop` và `staging`:

1. ✅ **Require a pull request before merging** — không push thẳng.
2. ✅ **Require status checks to pass** → chọn **`backend-test`**.
   (Check chỉ xuất hiện sau khi workflow đã chạy ít nhất 1 lần.)
3. ✅ **Block force pushes**.

> ⚠️ Vì workflow có `paths:`, PR chỉ sửa frontend sẽ **không** chạy `backend-test`. Nếu đặt `backend-test` là required, PR đó sẽ treo không merge được. Cách xử lý: bỏ `paths:` ở trigger `pull_request`, hoặc không đặt check bắt buộc.

---

## Bước 12 — Khoá environment `staging` theo branch

Mục tiêu: **chỉ code trên nhánh `staging` mới được deploy** lên Railway staging, kể cả khi ai đó bấm *Run workflow* từ nhánh khác hoặc sửa điều kiện `if:` trong workflow.

GitHub → **Settings** → **Environments** → **`staging`**:

1. **Deployment branches and tags** → chọn **Selected branches and tags** → **Add deployment branch or tag rule** → nhập `staging`.
   Job có `environment: staging` chạy từ nhánh khác sẽ bị GitHub chặn, và **không đọc được** secret `RAILWAY_API_TOKEN`.
2. (Tuỳ chọn) **Required reviewers** → thêm người duyệt. Job `deploy-backend` sẽ dừng ở trạng thái *Waiting* cho tới khi được Approve — dùng khi muốn có bước duyệt tay trước khi deploy.
3. (Tuỳ chọn) **Wait timer** → số phút chờ trước khi deploy.

> Lớp bảo vệ này độc lập với `if:` trong workflow: `if:` quyết định job có chạy không, còn Environment rule quyết định job có **được phép dùng secret và deploy** không.

---

## Bước 13 — Self-hosted runner (tuỳ chọn, hiện không dùng)

> **Dự án hiện CHỈ dùng GitHub-hosted runner (`ubuntu-latest`) — bỏ qua bước này.**
> Mục này giữ lại để tham khảo khi sau này cần chạy trên máy riêng (VPS, máy lab, cần truy cập mạng nội bộ, hoặc hết phút miễn phí). Với GitHub-hosted, việc "gắn branch" được thay bằng `if:` trong workflow + Environment rule ([Bước 12](#bước-12--khoá-environment-staging-theo-branch)) + branch protection ([Bước 11](#bước-11--branch-protection)).

Khi cần, job của từng nhánh có thể chạy trên **máy riêng của nhóm**, ví dụ:

| Nhánh | Runner | Label |
|---|---|---|
| `develop` (push + PR vào develop) | Runner dev/test | `p146-develop` |
| `staging` (PR vào staging + merge vào staging + deploy) | Runner staging | `p146-staging` |

GitHub không có chỗ "gán branch cho runner" trong Settings — việc gắn được làm bằng **label của runner** + **`runs-on` trong workflow** chọn label theo tên nhánh.

### 13.1. Đăng ký runner (làm trên mỗi máy, Linux x64)

1. GitHub repo → **Settings** → **Actions** → **Runners** → **New self-hosted runner** → chọn **Linux** / **x64**.
2. Chạy các lệnh *Download* GitHub hiển thị (tạo thư mục `actions-runner`, tải và giải nén).
3. Chạy *Configure*, **thêm label** tương ứng với nhánh:

   ```bash
   # Máy runner cho develop
   ./config.sh --url https://github.com/<owner>/<repo> --token <TOKEN> \
     --name p146-develop-01 --labels p146-develop --unattended

   # Máy runner cho staging
   ./config.sh --url https://github.com/<owner>/<repo> --token <TOKEN> \
     --name p146-staging-01 --labels p146-staging --unattended
   ```

   `<TOKEN>` là token đăng ký hiện trên trang *New self-hosted runner* (hết hạn sau 1 giờ).
4. Cài làm service để tự chạy lại khi máy khởi động:

   ```bash
   sudo ./svc.sh install
   sudo ./svc.sh start
   ```

5. Cài công cụ mà workflow cần trên máy runner:

   ```bash
   sudo apt update && sudo apt install -y git curl
   # Node.js (cho Railway CLI) — chỉ cần trên runner staging
   curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs
   ```

   Python 3.11 do `actions/setup-python` tự tải, không cần cài tay.
6. Kiểm tra: **Settings → Actions → Runners** → runner hiện **Idle** với label `self-hosted`, `Linux`, `X64`, `p146-develop` / `p146-staging`.

Thêm/sửa label sau khi đã đăng ký: bấm vào runner → **Labels** → thêm label.

### 13.2. Chọn runner theo branch trong workflow

```yaml
runs-on: ${{ (github.base_ref || github.ref_name) == 'staging'
             && fromJSON('["self-hosted", "linux", "p146-staging"]')
             || fromJSON('["self-hosted", "linux", "p146-develop"]') }}
```

- `github.base_ref`: nhánh **đích** của PR (chỉ có khi event là `pull_request`).
- `github.ref_name`: nhánh được **push** (khi event là `push` / `workflow_dispatch`).
- → PR vào `staging` và merge vào `staging` chạy trên runner `p146-staging`; còn lại chạy trên `p146-develop`.

Job deploy luôn chỉ chạy trên nhánh `staging`, nên gắn thẳng label:

```yaml
runs-on: [self-hosted, linux, p146-staging]
```

> Chỉ có 1 máy runner? Đăng ký 1 runner với **cả 2 label**: `--labels p146-develop,p146-staging`.
> Quay về runner của GitHub: thay `runs-on` về `ubuntu-latest` (cấu hình hiện tại).

### 13.3. Bảo mật khi dùng self-hosted runner

- **Repo public + self-hosted runner là rủi ro**: PR từ fork có thể chạy code bất kỳ trên máy runner. Nên để repo **private**, hoặc vào **Settings → Actions → General → Fork pull request workflows** → bật **Require approval for all external contributors**.
- Không lưu secret trên máy runner; secret chỉ đi qua GitHub Secrets.
- Runner group (giới hạn runner cho repo/workflow cụ thể) chỉ có ở **Organization**; repo cá nhân thì dùng label như trên.

---

## Bước 14 — Luồng test → check → deploy theo branch

### 14.1. Quy trình nhánh

```
(mọi job đều chạy trên GitHub-hosted ubuntu-latest)

feature/*  ──push──► (không chạy)
    │
    └──PR──► develop      : lint + test
               │
            merge/push    : lint + test
               │
               └──PR──► staging   : lint + test + build-check
                          │
                       merge/push : lint + test + build-check
                                     └─► deploy-backend ─► smoke-test
```

- Bất kỳ nhánh nào (`develop`, `hotfix/*`, ...) merge vào `staging` đều đi qua cùng luồng: PR → test/check → merge → test/check lại trên code đã merge → deploy.
- Test chạy **2 lần** với staging (lúc PR và sau merge) là cố ý: lần sau merge kiểm tra đúng code thực sự sẽ được deploy.

| Bước | Làm gì | Fail thì |
|---|---|---|
| `lint` | `ruff check` + `ruff format --check` | Dừng, không deploy |
| `backend-test` | `pytest` | Dừng, không deploy |
| `build-check` | Build 2 image `dockerfiles/Dockerfile.railway` + `backend/mock-ev-system/Dockerfile.railway` (chỉ khi đích là `staging`) | Dừng, không deploy |
| `deploy-backend` | `railway up` mock-ev-system → backend → worker | Không smoke test |
| `smoke-test` | `GET /health` | Workflow đỏ → kiểm tra log Railway |

### 14.2. Workflow mẫu đầy đủ

Đây đúng là nội dung [`.github/workflows/ci-cd.yml`](../../.github/workflows/ci-cd.yml) hiện tại — mọi job chạy trên `ubuntu-latest`.

```yaml
name: Backend CI/CD

on:
  # Push lên develop -> test/check; push (merge) vào staging -> test/check + deploy
  push:
    branches: [develop, staging]
    paths:
      - 'backend/**'
      - 'dockerfiles/**'
      - '.github/workflows/ci-cd.yml'
  # PR vào develop/staging (từ bất kỳ nhánh nào) -> test/check, chặn merge nếu fail
  pull_request:
    branches: [develop, staging]
    paths:
      - 'backend/**'
      - 'dockerfiles/**'
      - '.github/workflows/ci-cd.yml'
  workflow_dispatch:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/staging' }}

jobs:
  # Tất cả job chạy trên GitHub-hosted runner (ubuntu-latest)
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: backend/requirements.txt
      - run: pip install -r ./backend/requirements.txt
      - run: ruff check ./backend/src/ ./backend/tests/
      - run: ruff format --check ./backend/src/ ./backend/tests/

  backend-test:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: backend/requirements.txt
      - run: pip install -r ./backend/requirements.txt
      # ev-contracts là package nội bộ (uv workspace), không có trong requirements.txt
      - run: pip install ./backend/shared/ev-contracts
      - run: pytest ./backend/tests/ -v --tb=short
        env:
          APP_ENV: test
          OPENAI_API_KEY: test-key

  # Chỉ khi đích là staging: đảm bảo image build được trước khi deploy
  build-check:
    needs: backend-test
    if: (github.base_ref || github.ref_name) == 'staging'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -f dockerfiles/Dockerfile.railway -t p146-backend:ci .
      # mock-ev-system: build context là backend/ (uv workspace root)
      - run: docker build -f backend/mock-ev-system/Dockerfile.railway -t p146-mock-ev-system:ci backend

  deploy-backend:
    needs: build-check
    if: github.ref == 'refs/heads/staging' && github.event_name != 'pull_request'
    runs-on: ubuntu-latest
    environment: staging
    env:
      RAILWAY_API_TOKEN: ${{ secrets.RAILWAY_API_TOKEN }}
    steps:
      - uses: actions/checkout@v4
      - run: npm install -g @railway/cli
      - run: railway link --project "${{ vars.RAILWAY_PROJECT_ID }}" --environment staging
      # Mock OEM deploy trước: backend/worker gọi nó qua mock-ev-system.railway.internal
      - run: railway up ./backend --path-as-root --ci --service "${{ vars.RAILWAY_MOCK_SERVICE }}" --environment staging
      - run: railway up --ci --service "${{ vars.RAILWAY_BACKEND_SERVICE }}" --environment staging
      - run: railway up --ci --service "${{ vars.RAILWAY_WORKER_SERVICE }}" --environment staging

  smoke-test:
    needs: deploy-backend
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - run: curl --fail --retry 10 --retry-delay 10 --retry-all-errors "${{ vars.BACKEND_STAGING_URL }}/health"
```

Lưu ý:

- `ubuntu-latest` có sẵn **Docker**, **Node.js/npm**, `curl`, `git` — không cần cài gì thêm. Python 3.11 do `actions/setup-python` cài.
- `ruff format --check` sẽ fail nếu code chưa format. Chạy `ruff format backend/src backend/tests` ở local trước khi bật, hoặc bỏ dòng này.
- Railway CLI được cài lại mỗi lần chạy (`npm install -g @railway/cli`, khoảng 10–20 giây) vì máy ảo GitHub là máy mới cho từng job.

### 14.3. Bắt buộc check trước khi merge

Cập nhật ruleset ở [Bước 11](#bước-11--branch-protection):

| Nhánh | Required status checks |
|---|---|
| `develop` | `lint`, `backend-test` |
| `staging` | `lint`, `backend-test`, `build-check` |

Kết hợp với Bước 12 (environment chỉ cho nhánh `staging`), luồng cuối cùng là: **không merge được nếu check fail → không deploy được nếu không phải nhánh `staging` → chỉ deploy khi mọi check trên code đã merge đều xanh**.

---

## Lưu ý khi dùng GitHub-hosted runner

### Chạy thử

- **Nút *Run workflow* chỉ hiện khi file workflow đã có trên nhánh mặc định (`main`).** Nếu `ci-cd.yml` mới chỉ nằm trên `staging`/`develop`, hãy chạy thử bằng cách push một commit (có sửa `backend/**`, `dockerfiles/**` hoặc chính `ci-cd.yml`) lên `develop`.
- *Run workflow* trên `develop` → chỉ `lint` + `backend-test`. Trên `staging` → **chạy cả deploy thật** lên Railway staging. Muốn thử an toàn thì chạy trên `develop` trước.
- Commit chỉ sửa frontend/docs sẽ **không** kích hoạt workflow (do `paths:`).

### Máy ảo mới cho từng job

- Mỗi job chạy trên **một máy ảo sạch**, xong là bị xoá: không có file/package nào được giữ lại giữa các job hay giữa các lần chạy. Vì vậy mỗi job tự `checkout` và cài lại dependency (đã có trong workflow); pip được cache qua `actions/setup-python` (`cache: pip`).
- Không lưu gì lên máy runner để dùng lại — dữ liệu cần chia sẻ giữa job phải dùng `actions/upload-artifact` / `actions/download-artifact`.

### Phút miễn phí và chi phí

| Loại repo | Hạn mức (gói Free) |
|---|---|
| Public | Không giới hạn phút cho runner chuẩn |
| Private | 2.000 phút/tháng; hết thì job không chạy (hoặc bị tính phí nếu bật) |

- Ước tính mỗi lần merge vào `staging` mất khoảng 10–15 phút (lint + test + build-check + chờ Railway build). Push lên `develop` chỉ vài phút.
- Theo dõi tại **Settings (tài khoản/tổ chức) → Billing and plans → Usage**.
- `build-check` build Docker image trên GitHub, sau đó Railway **build lại lần nữa** khi deploy. Nếu cần tiết kiệm phút có thể bỏ `build-check` (Railway build lỗi thì deploy cũng fail, chỉ là phát hiện muộn hơn).
- `concurrency`: push liên tiếp vào `develop` sẽ huỷ lần chạy cũ; trên `staging` thì **không huỷ** mà xếp hàng, để không cắt ngang một lần deploy đang chạy.

### Mạng và bảo mật

- Runner của GitHub nằm trên Internet, **IP thay đổi mỗi lần chạy**: không truy cập được `localhost`/mạng nội bộ của nhóm, và không dùng được firewall allowlist theo IP. Hiện không ảnh hưởng: unit test không cần DB thật, deploy đi qua API của Railway.
- PR từ **fork** không đọc được secret (`RAILWAY_API_TOKEN`) và không deploy được — đúng thiết kế, vì job PR chỉ test.
- Không gắn được branch với một runner cụ thể (mọi máy `ubuntu-latest` như nhau). Việc "chỉ `staging` được deploy" được bảo đảm bởi 3 lớp: `if:` trong workflow, Deployment branches của Environment `staging` ([Bước 12](#bước-12--khoá-environment-staging-theo-branch)) và branch protection ([Bước 11](#bước-11--branch-protection)).

### Trước khi chạy lần đầu

- **Lint đang fail trên code hiện tại**: `ruff check` báo **154 lỗi** và `ruff format --check` báo **161 file chưa format** (ruff 0.16.x). Pipeline sẽ dừng ở `lint` cho tới khi sửa xong (`ruff check --fix`, `ruff format`, rồi xử lý/tắt các rule còn lại trong `backend/ruff.toml`), hoặc tạm bỏ dòng `ruff format --check`.
- `requirements.txt` ghi `ruff>=0.8.0` → mỗi khi ruff ra bản mới, CI có thể báo thêm lỗi dù code không đổi. Nên **ghim phiên bản** (vd `ruff==0.16.10`) cho ổn định.
- Hoàn tất cấu hình Railway (Bước 2–6) và GitHub Environment `staging` (Bước 8, 12) trước khi merge vào `staging`, nếu không `deploy-backend` sẽ fail.

---

## Xử lý sự cố

| Hiện tượng | Nguyên nhân / Cách sửa |
|---|---|
| Workflow không chạy, GitHub báo lỗi YAML | Kiểm tra cú pháp `ci-cd.yml` (vd dòng thừa cuối file) |
| `Unauthorized` / `Invalid token` | Đặt nhầm loại token vào nhầm biến — Account Token phải là `RAILWAY_API_TOKEN`, Project Token phải là `RAILWAY_TOKEN` |
| `Project not found` / `Environment not found` | Sai `RAILWAY_PROJECT_ID`, hoặc chưa tạo environment `staging` |
| `Service not found` | `RAILWAY_BACKEND_SERVICE` / `RAILWAY_WORKER_SERVICE` / `RAILWAY_MOCK_SERVICE` không khớp tên trên Railway |
| Backend gọi OEM lỗi `http://:8100` / không kết nối được mock | `mock-ev-system` chưa deploy lần nào (chưa có private domain), hoặc `OEM_API_BASE_URL` trong shared variable đè/xung đột — chỉ đặt ở mức service (Bước 5b) |
| Mock build lỗi không tìm thấy `pyproject.toml` / Dockerfile | Thiếu `--path-as-root ./backend` khi `railway up`, hoặc `RAILWAY_DOCKERFILE_PATH` của mock không phải `mock-ev-system/Dockerfile.railway` |
| Backend nhận webhook `401 WEBHOOK_SIGNATURE_INVALID` | `MOCK_WEBHOOK_SECRET` của mock khác `OEM_WEBHOOK_SECRET` của backend |
| Build báo không tìm thấy Dockerfile, hoặc `Railpack could not determine how to build the app` | Service thiếu `RAILWAY_DOCKERFILE_PATH=dockerfiles/Dockerfile.railway` (Dockerfile không nằm ở gốc repo nên Railway chuyển sang Railpack). Đặt biến cho **cả** `backend` và `worker` (Bước 6.4) |
| Build lỗi kiểu *cache mount ID* | Service đang trỏ vào `dockerfiles/Dockerfile` (có `--mount=type=cache`, Railway không nhận). Đổi `RAILWAY_DOCKERFILE_PATH` về `dockerfiles/Dockerfile.railway` |
| App crash `PermissionError: [Errno 13] Permission denied: 'logs'`, healthcheck fail | Container chạy bằng user `app`, `/app` thuộc root nên không tạo được `LOG_DIR`. `Dockerfile.railway` đã tạo sẵn `/app/logs`; nếu đổi `LOG_DIR` thì trỏ vào thư mục ghi được (vd `/app/data/logs`), hoặc đặt `LOG_FILE_FORMATS=` (rỗng) để chỉ log ra stdout. Không cần volume |
| Deploy xong nhưng domain trả 502 | Thiếu `PORT=8000` hoặc Target Port ≠ 8000 |
| App crash: `app_env` validation error | `APP_ENV` phải là `production` (không phải `staging`) |
| `Firebase credential not found` | Thiếu `FIREBASE_CREDENTIAL_JSON`, hoặc JSON bị cắt khi dán |
| `Error -2 connecting to redis.railway.internal` | Redis không cùng project/environment, hoặc biến Redis đặt sai service |
| Celery nối `localhost:6379` | Chỉ đặt `REDIS_URL` mà không đặt `REDIS_HOST/PORT/PASSWORD` (xem 6.3) |
| Worker chạy nhưng task không được xử lý | `backend` và `worker` có bộ biến `REDIS_*` / `CELERY_*` khác nhau |
| Job treo ở *Queued* / *Waiting for a runner* | `runs-on` đang trỏ tới self-hosted label (`p146-*`) — đổi về `ubuntu-latest`; hoặc repo private đã hết phút miễn phí (xem Billing) |
| Không thấy nút *Run workflow* | File `ci-cd.yml` chưa có trên nhánh mặc định `main` — chạy thử bằng cách push lên `develop` |
| `Branch "xxx" is not allowed to deploy to staging` | Đúng thiết kế (Bước 12) — chỉ nhánh `staging` được deploy |
| Job deploy dừng ở *Waiting* | Environment `staging` bật **Required reviewers** — cần người duyệt bấm Approve |
| `smoke-test` fail | Sai `BACKEND_STAGING_URL` (thừa `/` cuối, sai domain) hoặc app khởi động lỗi — xem log service `backend` |

---

## Việc còn tồn đọng

- **Migration database:** image chỉ copy `backend/src`, không có `alembic/` → container không chạy được `alembic upgrade`. Hiện phải chạy từ local, trỏ vào DB staging:

  ```bash
  cd backend && alembic upgrade head
  ```

  Hướng cải tiến: copy `backend/alembic` + `alembic.ini` vào image và đặt Railway **Pre-deploy Command** = `alembic upgrade head`.
- **Token:** chuyển từ Account Token sang Project Token để giới hạn quyền.
- **Bảo mật:** nếu `.env` hoặc file Firebase JSON từng bị chia sẻ/commit, rotate lại key (Firebase service account, Supabase service role, Gemini/OpenAI, ...).
