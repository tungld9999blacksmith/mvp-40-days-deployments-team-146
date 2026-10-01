# EV Care — AI Agent chăm sóc xe điện

Ứng dụng hỗ trợ chủ xe theo dõi bảo dưỡng, hỏi trợ lý AI, xem dự toán và đặt lịch; kỹ thuật viên xem và duyệt báo giá.

Repository được tổ chức thành frontend React và backend FastAPI, chia theo nghiệp vụ. Dự án phát triển từ AI20K Agent Template; giao diện gốc từ [trungmv2004/EV-Care](https://github.com/trungmv2004/EV-Care).

## Trạng thái hiện tại

- Frontend: 12 màn hình React + TypeScript + Vite + Tailwind, dùng mock.
- Backend: `GET /health`, `GET /api/v1/status`, `POST /api/v1/chat`.
- Chat backend chạy graph LangGraph với các node mẫu; chưa gọi LLM hoặc RAG trong luồng này.
- Các module nghiệp vụ ngoài assistant, database và migrations mới là khung tổ chức.
- HTTP client và adapter chat đã có trong frontend; các trang demo chưa chuyển sang gọi backend.

## Cấu trúc

```text
frontend/
  src/
    app/                 Router và providers
    features/            auth, dashboard, vehicles, maintenance,
                         quotes, bookings, assistant, notifications
    layouts/             Sidebar và topbar
    shared/              UI, HTTP client, tiện ích dùng chung
    mocks/               Các bộ dữ liệu giả của giao diện
    styles/              Theme và CSS
  package.json
  package-lock.json
backend/
  app/
    main.py              FastAPI entry point
    core/                Settings và thành phần nền tảng
    modules/             auth, vehicles, maintenance, quotes,
                         bookings, assistant, notifications
    ai/                  graph, state, nodes, tools, prompts, retrieval, llm
    db/                  Vị trí dành cho kết nối database
  tests/                 unit và integration
  migrations/            Vị trí dành cho migrations
  requirements.txt
  Dockerfile
knowledge/sources/       Danh mục nguồn kiến thức
data/                   Dữ liệu cục bộ, không commit
eval/                   datasets và results
tests/e2e/              Vị trí dành cho kiểm thử xuyên hệ thống
docs/                   architecture, product, design, guide
scripts/                Setup và hook ghi log AI
presentation/           Tài liệu Demo Day
```

## Chạy trên máy

Yêu cầu: Python 3.11, Node.js 24 và npm. Chạy các lệnh dưới đây từ thư mục gốc repository.

```bash
python -m venv .venv
```

Kích hoạt môi trường:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS
source .venv/bin/activate
```

Cài dependencies:

```bash
python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
```

Sao chép `.env.example` thành `.env` nếu chưa có; giữ nguyên `.env` đã cấu hình. Điền các API key khi sử dụng tính năng tương ứng. Không commit key thật.

Chạy backend trong terminal thứ nhất:

```bash
python -m uvicorn src.main:app --app-dir backend --reload --port 8000
```

Chạy frontend trong terminal thứ hai:

```bash
npm --prefix frontend run dev
```

Frontend: <http://localhost:5173>. API docs: <http://localhost:8000/docs>.
Vite dev server proxy `/api` và `/health` đến backend; biến môi trường `VITE_BACKEND_URL` đổi địa chỉ đích. Khi deploy frontend, cấu hình host để phục vụ SPA và proxy API; Vite dev proxy không áp dụng cho bản build production.

## Kiểm tra

```bash
python -m ruff check backend tests
python -m pytest backend/tests -v
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Hoặc dùng `make check` khi đã cài Make. `make run`, `make fe-dev`, `make test`, `make lint` và `make format` dùng các đường dẫn mới.

## Docker

```bash
docker compose up --build
```

Compose hiện chạy backend. Dockerfile ở `backend/Dockerfile`, build context là thư mục gốc; dependencies nằm trong `/opt/venv` để user không phải root vẫn chạy được ứng dụng. `data/` được mount để lưu dữ liệu cục bộ khi triển khai persistence.

## Tài liệu

- [Kiến trúc và quy tắc tổ chức mã](docs/architecture/README.md)
- [Luồng nghiệp vụ](docs/product/README.md)
- [Wireframe](docs/design/wireframe.md) và [design guidelines](docs/design/design-guidelines.md)
- [Frontend](frontend/README.md) và [backend](backend/README.md)
- [Technical Guidebook](docs/guide/chapter-01.md): tài liệu khóa học; các ví dụ dùng cấu trúc template cũ, đối chiếu đường dẫn trong tài liệu kiến trúc.
- [Evaluation](eval/results/report.md), [journal](JOURNAL.md), [worklog](WORKLOG.md) và [presentation](presentation/README.md)

## AI usage logging

Giữ nguyên cấu hình hook và scripts của template. Cài hook một lần sau khi clone:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_hooks.ps1
```

```bash
bash scripts/setup_hooks.sh
```

Mỗi thành viên tự cấu hình `AI_LOG_API_KEY` từ dashboard Phoenix. Hook ghi log cục bộ và gửi log ở bước pre-push. Với công cụ web, dùng `scripts/log_manual.py` theo hướng dẫn của khóa học.

## Đóng góp và license

Xem [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) và [MIT license](LICENSE).
