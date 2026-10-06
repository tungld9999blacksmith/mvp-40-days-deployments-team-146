# Source code backend của dự án

Vector store mặc định là **Qdrant** (Cloud hoặc local), dùng chung cho RAG và tìm kiếm ngữ nghĩa trong chat.
Xem [cấu hình Qdrant](guide/qdrant.md). PostgreSQL/Supabase vẫn lưu dữ liệu nghiệp vụ.

## Đặt lịch và hội thoại

- Trước khi chạy phiên bản mới, chạy `uv run alembic upgrade head` từ `backend/`.
  Migration `c9e4a2f6b8d1` thêm bảng `booking_request`, lưu kết quả đặt lịch cùng
  transaction với lịch hẹn để phục hồi khi mất phản hồi HTTP.
- `POST /api/v1/bookings` nhận `Idempotency-Key` (1–128 ký tự). Khi thử lại, gửi
  cùng khóa và payload; server trả lại cùng lịch hẹn. Dùng cùng khóa cho payload
  khác trả `409 IDEMPOTENCY_CONFLICT`. Nếu không gửi khóa, token xác nhận được
  dùng để nhận diện lần thử lại. Token chỉ bị xóa sau khi DB ghi thành công.
- WebSocket `/api/v1/conversations/{id}/stream` yêu cầu frame đầu tiên
  `{"type":"auth","token":"<Firebase ID token>"}`. Danh tính được lấy từ token;
  frame chỉ có `userId` không còn được chấp nhận.
- API trích đoạn hội thoại yêu cầu token chủ xưởng và kiểm tra xưởng thuộc tài
  khoản đó; header `X-Workshop-Id` không quyết định quyền truy cập.
- Lượt AI dùng `CHAT_RUN_TIMEOUT_SECONDS` (mặc định 30 giây). Sau khi chấp nhận
  tin nhắn, lỗi trả bằng SSE `error` kèm `traceId`; quá thời gian có mã
  `CHAT_TIMEOUT`. Khi hủy một lượt có thao tác ghi DB đang chạy, khóa đặt lịch
  được giữ đến khi thao tác đó kết thúc để bảo vệ transaction.

## Giới thiệu về các cấu trúc thư mục 

- `./backend/src/*`: thư mục này chứa toàn bộ src code backend, sử dụng fast-api để giao tiếp với frontend

- `./backend/tools/test_ui/`: Đây là thư  mục chứa source code chứa code streamlit code, để anh em backend kiểm thử luồng agent mình chạy như thế nào
  - **Lưu ý**: Vì source code của agent nằm ở thư mục `./backend/src/agents/.` anh em phải khi chạy strealit bằng terminal thì thư mục hiện tại mà terminal đứng là `./backend/.` thì streamlit app mới thấy source code. Và câu lệnh khi chạy thí dụ là, giả sử .venv nằm tại thư mục ./backend/.:
    ```bash
    py -m streamlit run ./tools/test_ui/streamlit_app.py
    ```

## Lưu ý khi muốn kiểm thử agent với streamlit 

- src code ui sử dụng streamlit nên lưu tại thư mục `./backend/tools/test_ui/.`
- Nếu bạn muốn chạy streamlit app mà terminal đang đứng tại thư mục `./backend/tools/test_ui/.` thì bạn nên cân nhắc việc load src code từ thư mục `.\backend\tools\test_ui\.` như sau:
  - Tại file bạn muốn import src code của agent từ folder `./backend/src/agents/.` bạn hãy viết như sau để môi trường ảo nhận thức được source code của agent:

    ```python
    import sys
    from pathlib import Path
    

    root_dir = Path(__file__).resolve().parent.parent.parent # point to ./backend

    if str(root_dir) not in sys.path:
        sys.path.apppend(str(root_dir))
    # Lúc này bạn import bình thường 

    from src.agent.my_agent import MyAgent
    ```

## Deprecation

- Các source code không sử dụng nữa mà không xóa sẽ cho vô thư mục `./backend/deprecated/`

- Move `./backend/src/services/` => `./backend/deprecated/services/`
- Move `./backend/src/services/` => `./backend/deprecated/models`

## Quản lý package bằng uv (monorepo / workspace)

`backend/` là một uv workspace. Cách cũ (`pip install -r requirements.txt`) vẫn dùng được: Dockerfile và CI hiện vẫn cài bằng `requirements.txt`.

```text
backend/
├── pyproject.toml          # workspace root + app EV Care (code ở ./src, package = false)
├── uv.lock                 # lockfile chung cho cả workspace — commit file này
├── src/                    # app EV Care (không đổi)
├── mock-ev-system/         # member: FastAPI giả lập hệ thống công ty xe điện
│   └── src/mock_ev_system/
└── shared/
    └── ev-contracts/       # member: thư viện dùng chung (contract/schema API xe điện)
        └── src/ev_contracts/
```

- App EV Care **không import** code của `mock-ev-system`. Hai bên chỉ chia sẻ qua `shared/`.
- Trong giai đoạn chuyển đổi, khi thêm dependency cho app EV Care, hãy cập nhật cả `pyproject.toml` lẫn `requirements.txt`.

### Các lệnh uv hữu ích (đứng tại `./backend/`)

#### Cài đặt / đồng bộ môi trường

```bash
uv sync --all-packages          # cài toàn bộ workspace (app + mock + shared) vào ./backend/.venv
uv sync --all-packages --locked # cài đúng theo uv.lock, báo lỗi nếu lock lệch với pyproject (dùng cho CI)
uv sync --package mock-ev-system # chỉ cài những gì mock cần
uv lock                          # cập nhật uv.lock sau khi sửa pyproject.toml bằng tay
uv lock --upgrade-package fastapi # nâng version một package trong lock
```

#### Chạy

```bash
uv run uvicorn src.main:app --reload --port 8000                                  # app EV Care
uv run --package mock-ev-system uvicorn mock_ev_system.main:app --reload --port 8100 # mock
uv run pytest tests/ -v                                                           # test app EV Care
uv run ruff check src/ tests/
uv run alembic upgrade head
uv run --with streamlit streamlit run ./tools/test_ui/streamlit_app.py            # test UI
```

Có thể dùng Makefile thay cho các lệnh trên: `make uv-sync`, `make uv-run`, `make uv-test`, `make mock-run`.

#### Thêm / bớt dependency

```bash
uv add <pkg>                             # thêm cho app EV Care
uv add --package mock-ev-system <pkg>    # thêm cho mock
uv add --package ev-contracts <pkg>      # thêm cho thư viện dùng chung
uv add --dev <pkg>                       # thêm dev dependency (pytest, ruff, ...)
uv remove <pkg>                          # bỏ dependency
```

#### Thêm thư viện dùng chung mới

```bash
uv init --lib shared/<ten-lib>                 # tự được nhận vào workspace (members = shared/*)
uv add <ten-lib>                               # app EV Care dùng lib này
uv add --package mock-ev-system <ten-lib>      # mock dùng lib này
```

`uv add` tự ghi `<ten-lib> = { workspace = true }` vào `[tool.uv.sources]`.

#### Xem / xuất

```bash
uv tree                     # cây dependency của workspace
uv tree --package mock-ev-system
uv export --no-dev --no-hashes -o requirements.uv.txt # xuất requirements từ uv.lock (cho Docker/pip)
uv python pin 3.11          # ghim version Python cho workspace (.python-version)
```
