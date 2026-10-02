# Hướng dẫn viết & chạy Unit Test (backend)

Test dùng **pytest** + **pytest-asyncio**. Dự án hỗ trợ 2 cách chạy: **uv**
(workspace) và **python/pip thông thường**. Phần dưới có cả hai.

---

## 0. Cấu hình test có sẵn

File `pytest.ini` ở **gốc repo** (không phải trong `backend/`):

```ini
[pytest]
testpaths = backend/tests
pythonpath = backend        # để `import src...` và `from tests... ` chạy được
asyncio_mode = strict       # test async PHẢI có @pytest.mark.asyncio
```

Vì cấu hình nằm ở gốc repo, `rootdir` của pytest luôn là gốc repo — chạy từ
gốc repo hay từ `backend/` đều được (pytest tự tìm ngược lên).

Cấu trúc test (`backend/tests/`):

```text
tests/
  conftest.py                # fixture chung: client (AsyncClient), mock_llm
  _auth.py, _onboarding.py   # helper dùng chung (SQLite in-memory, stub gateway)
  test_api/                  # test tầng HTTP qua ASGI (không mở cổng thật)
  test_modules/              # test service/business logic
  test_infrastructure/       # test redis (fakeredis), llm provider, oem…
    test_redis/conftest.py   # fixture redis riêng (FakeAsyncRedis)
```

---

## 1. Cài môi trường

### Cách A — uv (khuyến nghị)

`uv` tự dựng venv và cài cả workspace member (`mock-ev-system`, `shared/ev-contracts`)
lẫn nhóm `dev` (pytest, pytest-asyncio, fakeredis, httpx).

```bash
cd backend
uv sync --all-packages          # cài toàn bộ workspace + dev deps
```

### Cách B — python/pip thông thường

```bash
cd backend
python -m venv .venv

# Kích hoạt venv:
#   Windows PowerShell:  .venv\Scripts\Activate.ps1
#   Git Bash / Linux/mac: source .venv/bin/activate

pip install -r requirements.local.txt

# ⚠️ 2 gói cần cài thêm — KHÔNG có sẵn trong requirements.local.txt:
pip install "fakeredis[lua]"     # cần cho tests/test_infrastructure/test_redis
pip install ./shared/ev-contracts # package local, cần cho tests onboarding/oem
```

> Nếu thiếu `fakeredis` → lỗi import ở test redis. Thiếu `ev-contracts` →
> lỗi `ModuleNotFoundError: ev_contracts` ở test onboarding/oem.

---

## 2. Chạy test

Chạy từ **gốc repo** (khuyến nghị, khớp `pytest.ini`) hoặc từ `backend/`.

| Việc | uv | python/pip |
|------|-----|-----------|
| Chạy toàn bộ | `uv run pytest -v` | `pytest -v` |
| Một thư mục | `uv run pytest backend/tests/test_api -v` | `pytest backend/tests/test_api -v` |
| Một file | `uv run pytest backend/tests/test_api/test_vehicles_api.py -v` | `pytest backend/tests/test_api/test_vehicles_api.py -v` |
| Một test | `uv run pytest backend/tests/test_api/test_vehicles_api.py::test_create_vehicle_returns_201` | `pytest .../test_vehicles_api.py::test_create_vehicle_returns_201` |
| Theo từ khóa | `uv run pytest -k "vehicle and not invalid"` | `pytest -k "vehicle and not invalid"` |
| Dừng ở lỗi đầu | `uv run pytest -x` | `pytest -x` |
| Xem print/log | `uv run pytest -s` | `pytest -s` |

### Lối tắt qua Makefile (chạy trong `backend/`)

```bash
make test        # pytest tests/ -v          (dùng python trong PATH/venv)
make uv-test     # uv run pytest tests/ -v   (dùng uv)
make check       # lint + format + test
```

### Đo coverage (tùy chọn)

```bash
pip install pytest-cov          # hoặc: uv add --dev pytest-cov
uv run pytest --cov=backend/src --cov-report=term-missing
```

---

## 3. Viết test mới

### 3.1 Test API (tầng HTTP) — dùng fixture `client`

`conftest.py` cung cấp `client` (httpx `AsyncClient` gắn thẳng vào ASGI app,
không mở cổng). Vì `asyncio_mode = strict`, test async phải đánh dấu
`@pytest.mark.asyncio`.

```python
# backend/tests/test_api/test_vehicles_api.py
import pytest


@pytest.mark.asyncio
async def test_create_vehicle_returns_201(client):
    response = await client.post(
        "/api/v1/vehicles/",
        json={"license_plate": "59a-12345", "brand": "Toyota", "model": "Camry", "year": 2024},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["license_plate"] == "59A-12345"  # chuẩn hóa hoa
```

### 3.2 Test service / business logic — cô lập, không I/O thật

Import service và dựng dependency giả (in-memory SQLite + stub gateway).
Xem helper có sẵn `tests/_onboarding.py`:

```python
from src.modules.vehicle_owner_onboarding.service import OnboardingService
from tests._onboarding import StubOemGateway, make_session


def _service(gateway, *, max_failed=5):
    session = next(make_session())  # SQLite in-memory, tự tạo bảng
    return OnboardingService(
        session,
        gateway,
        retention_days=15,
        max_failed_attempts=max_failed,
        policy_version="2026-09",
    )


def test_verify_success():
    svc = _service(StubOemGateway())
    ...
```

### 3.3 Test Redis — dùng fixture `toolkit` (fakeredis)

`tests/test_infrastructure/test_redis/conftest.py` cung cấp `redis` và `toolkit`
chạy trên `FakeAsyncRedis` (không cần Redis thật):

```python
import pytest


@pytest.mark.asyncio
async def test_cache_set_get(toolkit):
    await toolkit.cache.set("k", {"v": 1})
    assert await toolkit.cache.get("k") == {"v": 1}
```

### 3.4 Mock LLM — dùng fixture `mock_llm`

Tránh gọi OpenAI thật trong test:

```python
@pytest.mark.asyncio
async def test_agent(mock_llm):
    mock_llm.ainvoke.return_value.content == "Mocked LLM response"
    ...
```

---

## 4. Quy ước & mẹo

- **Đặt tên**: file `test_*.py`, hàm `test_*`, class `Test*`.
- **Async**: luôn thêm `@pytest.mark.asyncio` (strict mode sẽ báo lỗi nếu quên).
- **Không I/O thật**: DB → SQLite in-memory; Redis → fakeredis; OEM → stub;
  LLM → `mock_llm`. Test phải chạy được offline và lặp lại được.
- **Fixture dùng lại nhiều nơi** đặt ở `conftest.py`; helper phức tạp đặt ở
  module `_ten.py` rồi import (`from tests._onboarding import ...`).
- **Chạy nhanh khi dev**: `pytest -x -q -k "tên_test"`.
- **Trước khi push**: `make check` (lint + format + test) hoặc
  `uv run ruff check src/ tests/ && uv run pytest -v`.
