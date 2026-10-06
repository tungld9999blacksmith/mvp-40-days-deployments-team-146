# Quy ước khởi động dự án

Khi người dùng nói "chạy dự án", "chạy project" hoặc yêu cầu tương đương mà
không chỉ định thành phần khác, khởi động cả backend thật và frontend thật của
EV Care.

- Backend: entry point `src.main:app`, chạy từ thư mục `backend`, cổng `8000`.
- Dùng cấu hình hiện có trong `.env` ở gốc repository.
- Ưu tiên Python trong `backend/.venv`; lệnh tương đương:
  `uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000`.
- Frontend: chạy từ gốc repository bằng
  `npm --prefix frontend run dev -- --host 127.0.0.1`, cổng `5173`.
- Frontend gọi backend thật: đặt `VITE_BACKEND_URL=http://127.0.0.1:8000`,
  `VITE_CHAT_TRANSPORT=http` và `VITE_API_MOCKS=off` trong môi trường tiến trình
  frontend khi khởi động; không sửa `.env` để áp dụng các giá trị này.
- Nếu BE/FE thật đã chạy đúng cổng và cấu hình, kiểm tra rồi dùng tiến trình đó;
  chỉ khởi động thành phần còn thiếu.
- Không dùng `src.demo.main:app` hoặc tự chuyển sang chế độ demo.
- Không tự khởi động Firebase Emulator, Docker stack hoặc Celery
  trong yêu cầu khởi động mặc định này. Chỉ chạy thêm thành phần khi người dùng
  yêu cầu; có thể dùng các dịch vụ phụ trợ đang chạy sẵn.
- Kiểm tra `http://localhost:8000/health` và `http://localhost:5173`; báo địa chỉ
  frontend `http://localhost:5173` và API docs `http://localhost:8000/docs`.
  Nếu dịch vụ phụ trợ không kết nối được, báo
  đúng lỗi thay vì thay cấu hình sang dữ liệu giả.

Quy ước này áp dụng cho các yêu cầu khởi động về sau; không tự dừng các dịch vụ
đang chạy khi người dùng chỉ yêu cầu lưu quy ước.

## Tổng hợp lệnh chạy BE, FE và demo

Các lệnh dưới đây dùng PowerShell trên Windows. Mỗi terminal bắt đầu tại gốc
repository `H:\AI2026\P-146`, trừ khi ghi rõ thư mục khác. BE và FE chạy ở các
terminal riêng. Chỉ chạy thành phần được yêu cầu; bảng lệnh này không thay đổi
quy ước khởi động mặc định ở trên.

### 1. Chuẩn bị môi trường

Dùng `.env` hiện có ở gốc repository; không ghi đè khi đã có cấu hình.
Backend và Vite cùng đọc cấu hình ở gốc; giữ key LLM ở backend, không đưa vào
biến `VITE_*`.

```powershell
# Từ gốc repo, chỉ tạo .env khi chưa có rồi điền cấu hình cần thiết.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

# Cài dependency backend, mock hãng xe và shared contracts.
cd backend
uv sync --all-packages
cd ..

# Cài dependency frontend.
npm --prefix frontend ci

# Chỉ cần cho Firebase Auth Emulator và công cụ demo.
npm --prefix tools/demo ci
```

Trước lần chạy backend thật đầu tiên hoặc khi có migration mới, chạy từ
`backend/`:

```powershell
uv run alembic upgrade head
```

### 2. Backend thật — FastAPI, cổng 8000

Từ gốc repo:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Lệnh tương đương bằng uv, chạy từ `backend/`:

```powershell
uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Nếu cần truy cập qua mạng LAN, dùng `--host 0.0.0.0` và cấu hình CORS phù hợp.
Nếu có GNU Make, từ `backend/` có thể dùng `make uv-run` hoặc `make run`
(hai target này bind `0.0.0.0`; `make run` cần uvicorn trong PATH).

- Health: `http://localhost:8000/health`.
- Swagger: `http://localhost:8000/docs`.
- Dùng database, Redis, Firebase và LLM theo `.env`; lỗi kết nối phải được báo
  đúng, không tự chuyển sang backend demo.

### 3. Frontend thật — React/Vite, cổng 5173

Từ gốc repo, terminal riêng:

```powershell
npm --prefix frontend run dev -- --host 127.0.0.1
```

Hoặc chạy trong `frontend/`:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

Frontend ở `http://localhost:5173`; Vite proxy `/api` và `/health` đến backend.
Khi cần chỉ định đích proxy, đặt biến trong terminal FE trước khi chạy Vite:

```powershell
$env:VITE_BACKEND_URL = 'http://127.0.0.1:8000'
$env:VITE_CHAT_TRANSPORT = 'http'
$env:VITE_API_MOCKS = 'off'
npm --prefix frontend run dev -- --host 127.0.0.1
```

### 4. Demo end-to-end — Firebase Emulator + BE demo + FE

Chỉ chạy khi người dùng yêu cầu demo. Demo dùng LLM thật và dữ liệu nghiệp vụ
mock trong backend; không cần SQL, Redis hoặc mock hãng xe riêng.
Backend demo cũng dùng cổng 8000: không chạy đồng thời với backend thật trên
cổng này, không tự dừng tiến trình hiện có khi chỉ cập nhật tài liệu.

**Terminal 1 — Firebase Auth Emulator, từ gốc repo:**

```powershell
npm --prefix tools/demo run auth
```

Auth Emulator chạy ở `127.0.0.1:9099`, project `demo-ev-care`; giao diện quản lý
emulator được tắt trong `tools/demo/firebase.json`.

**Terminal 2 — backend demo, từ gốc repo:**

```powershell
cd backend
$env:FIREBASE_AUTH_EMULATOR_HOST = '127.0.0.1:9099'
$env:VITE_FIREBASE_PROJECT_ID = 'demo-ev-care'
.\.venv\Scripts\python.exe -m uvicorn src.demo.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Lệnh tương đương bằng uv, sau khi đặt các biến trên, từ `backend/`:

```powershell
uv run uvicorn src.demo.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Giữ một worker và không dùng `--reload` trong buổi demo vì booking/chat ở RAM.
Hồ sơ đăng ký được lưu ở `data/demo/registration.json` tại gốc repo.
Health demo trả `mode: demo`; Swagger ở `http://localhost:8000/docs`.
API demo yêu cầu Bearer Firebase token, không hỗ trợ bypass bằng `X-User-Id`.

Tùy chọn đặt provider/model hoặc đồng hồ demo trong terminal BE **trước** lệnh
uvicorn; provider demo hỗ trợ `gemini` và `openai`, cần key tương ứng trong `.env`:

```powershell
$env:DEMO_LLM_PROVIDER = 'gemini' # Hoặc 'openai'.
# $env:DEMO_LLM_MODEL = '<model tương ứng với provider>'

# Đặt mốc 09:00 hôm nay theo UTC+7 để trình diễn đặt lịch/check-in trong ngày.
$demoDate = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(7)).ToString('yyyy-MM-dd')
$env:DEMO_NOW = $demoDate + 'T09:00:00+07:00'
```

Đồng hồ demo tiếp tục chạy từ mốc này; bỏ `DEMO_NOW` để dùng giờ thật.
Thiếu cấu hình LLM thì chat báo lỗi.

**Terminal 3 — frontend demo, từ gốc repo:**

```powershell
$env:VITE_FIREBASE_API_KEY = 'demo-api-key'
$env:VITE_FIREBASE_AUTH_DOMAIN = 'demo-ev-care.firebaseapp.com'
$env:VITE_FIREBASE_PROJECT_ID = 'demo-ev-care'
$env:VITE_FIREBASE_APP_ID = 'demo-app'
$env:VITE_FIREBASE_AUTH_EMULATOR_URL = 'http://127.0.0.1:9099'
$env:VITE_BACKEND_URL = 'http://127.0.0.1:8000'
$env:VITE_CHAT_TRANSPORT = 'http'
$env:VITE_API_MOCKS = 'off'
npm --prefix frontend run dev:demo -- --host 127.0.0.1
```

Cũng có thể dùng `npm --prefix frontend run dev -- --host 127.0.0.1` với cùng
các biến trên. `dev:demo` chỉ chọn Vite mode `demo`; không bỏ Firebase và không
tự bật mock API/chat trong trình duyệt.

- Chủ xe: `http://127.0.0.1:5173`.
- Chủ xưởng: `http://127.0.0.1:5173/workshop/login`.
- Dùng hai profile trình duyệt hoặc cửa sổ thường/ẩn danh cho hai vai trò.

Biến `$env:*` áp dụng cho terminal hiện tại và ghi đè giá trị trong `.env`.
Khi quay lại BE/FE thật, dùng terminal mới để tránh giữ cấu hình emulator/demo.

### 5. Frontend với mock API/chat trong trình duyệt

Chỉ bật khi người dùng yêu cầu giả lập frontend; đây là cấu hình riêng với
demo end-to-end ở mục 4. Từ gốc repo:

```powershell
$env:VITE_CHAT_TRANSPORT = 'mock'
$env:VITE_API_MOCKS = 'all' # Hoặc 'estimate,bookings,board,crm' / một số nhóm.
npm --prefix frontend run dev:demo -- --host 127.0.0.1
```

Mock chỉ bao phủ các nhóm API được hỗ trợ và chat. Đăng nhập/onboarding cùng
các API chưa có mock vẫn cần Firebase và backend; không coi đây là chế độ
chạy toàn bộ ứng dụng offline.

### 6. Build và xem trước frontend

Từ gốc repo, chọn **một** lệnh build:

```powershell
npm --prefix frontend run build      # Build thường vào frontend/dist/.
npm --prefix frontend run build:demo # Build Vite mode demo vào cùng thư mục.
```

Sau đó xem trước bản vừa build:

```powershell
npm --prefix frontend run preview -- --host 127.0.0.1 --port 5173 --strictPort
```

Các biến `VITE_*` cần đặt trước lúc build. Preview dùng cổng 5173 nên phải
chạy riêng với dev server. Bản build cần host/proxy chuyển `/api` và `/health`
đến backend và hỗ trợ SPA fallback; cấu hình proxy `server` của Vite chỉ áp dụng
cho dev server.

### 7. Dịch vụ phụ trợ và Docker (chạy khi được yêu cầu)

**Chỉ hạ tầng Redis + mock hãng xe, BE vẫn chạy bằng terminal — từ gốc repo:**

```powershell
.\scripts\infra-stack.ps1 up
# Tương đương:
docker compose -f docker-compose.infra.yaml up -d --build
```

**Toàn bộ stack BE thật + Redis + mock hãng xe trong Docker — từ gốc repo:**

```powershell
.\scripts\dev-stack.ps1 up
# Tương đương:
docker compose -f docker-compose.dev.yaml up -d --build
```

Hai stack này dùng chung tên container/cổng Redis và mock; chọn một stack.
Stack Docker BE dùng cổng 8000, không chạy cùng BE terminal trên cổng đó.
FE vẫn chạy riêng bằng lệnh ở mục 3.

Các lựa chọn Compose khác có sẵn, chạy từ gốc repo khi được yêu cầu cụ thể:

```powershell
docker compose -f docker-compose.yml up -d --build       # Chỉ container BE.
docker compose -f docker-compose.local.yaml up -d --build # BE + Postgres/pgAdmin + Redis/RedisInsight.
```

Compose local cần cấu hình `.env` phù hợp với database/Redis trong container;
không tự đổi cấu hình đang có. Trên macOS/Linux/Git Bash, lệnh tương ứng là
`bash scripts/infra-stack.sh up` hoặc `bash scripts/dev-stack.sh up`.

**Mock hãng xe chạy trực tiếp bằng Python — terminal riêng, từ gốc repo:**

```powershell
cd backend
uv run --package mock-ev-system uvicorn mock_ev_system.main:app --reload --host 127.0.0.1 --port 8100
```

Mock OEM ở `http://localhost:8100/health` và `http://localhost:8100/docs`;
đây là dịch vụ phụ trợ cho BE thật, khác `src.demo.main:app`.
Có GNU Make thì dùng `make mock-run` từ `backend/` (bind `0.0.0.0`).

**Celery worker + lịch tác vụ — terminal riêng, từ gốc repo:**

```powershell
cd backend
uv run celery -A src.celery_tasks worker -B --loglevel=info --pool=solo
```

Dùng cho đồng bộ ODO/nhắc bảo dưỡng, cần Redis theo `.env`;
`--pool=solo` phù hợp Windows. Không cần Celery cho BE demo.

**Giao diện Streamlit kiểm thử agent — tùy chọn, từ gốc repo:**

```powershell
cd backend
uv run --with streamlit streamlit run ./tools/test_ui/streamlit_app.py
```

### 8. Kiểm tra và dừng dịch vụ

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-WebRequest http://localhost:8000/docs -UseBasicParsing
# Chỉ kiểm tra nếu mock OEM được chạy:
Invoke-RestMethod http://localhost:8100/health
```

Health 200 xác nhận API có phản hồi; cần kiểm tra lỗi từng nghiệp vụ để kết luận
database, Redis, Firebase hoặc LLM kết nối được.

Dừng BE/FE/Emulator/Celery/Streamlit bằng `Ctrl+C` tại terminal của dịch vụ.
Với Docker, chạy từ gốc repo và chọn stack đang dùng:

```powershell
.\scripts\infra-stack.ps1 ps   # Hoặc logs / down.
.\scripts\dev-stack.ps1 ps     # Hoặc logs / down / restart.
```

`down` giữ volume; `clean` hoặc `docker compose ... down -v` xóa volume dữ liệu,
chỉ dùng khi người dùng yêu cầu xóa dữ liệu. Không tự dừng dịch vụ khi chỉ yêu
cầu tổng hợp lệnh.

Nguồn đối chiếu: [README.md](README.md), [frontend/package.json](frontend/package.json),
[backend/Makefile](backend/Makefile), [hướng dẫn demo](docs/plans/AGENT_BACKEND_DEMO_PLAN.md),
[hướng dẫn backend local](docs/RUN_LOCAL_BACKEND.md).
