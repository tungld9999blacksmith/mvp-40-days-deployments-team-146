# Hướng dẫn sử dụng Swagger UI

FastAPI tự sinh tài liệu OpenAPI cho backend EV Care. Không cần cài thêm gì —
chỉ cần chạy app là có ngay giao diện thử API.

## 1. Khởi động backend

Chọn **một** trong hai cách (xem chi tiết trong [testing.md](testing.md) phần cài môi trường):

```bash
# Cách A — uv (workspace)
cd backend
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Cách B — python/venv thông thường (đã activate venv)
cd backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

> Backend cần Redis sống khi khởi động (lifespan gọi `redis_toolkit.start()`).
> Chạy nhanh Redis bằng Docker: `docker run -d -p 6379:6379 redis:7-alpine`,
> hoặc dùng nguyên stack trong [../../docs/RUN_LOCAL_BACKEND.md](../../docs/RUN_LOCAL_BACKEND.md).

## 2. Các URL tài liệu

| Giao diện | URL | Dùng khi |
|-----------|-----|----------|
| **Swagger UI** | http://localhost:8000/docs | Thử API trực tiếp trên trình duyệt |
| **ReDoc** | http://localhost:8000/redoc | Đọc tài liệu dạng tĩnh, dễ in/chia sẻ |
| **OpenAPI JSON** | http://localhost:8000/openapi.json | Import vào Postman / sinh client SDK |
| **Health check** | http://localhost:8000/health | Kiểm tra app sống |

## 3. Bố cục Swagger UI

API được nhóm theo **tags**, tương ứng các module trong `src/modules/`:

| Tag | Prefix | Chức năng |
|-----|--------|-----------|
| `vehicles` | `/api/v1/vehicles` | CRUD xe (module `examples`) |
| `onboarding` | `/api/v1/onboarding`, `/api/v1/oauth/sign-in` | Đăng ký, xác minh sở hữu xe, profile |
| `auth` | `/api/v1/oauth` | Đăng xuất / thu hồi token |
| `oauth` | `/api/v1/oauth/profile` | Thông tin profile qua OAuth |
| _(mặc định)_ | `/health` | Health check |

Mỗi endpoint có sẵn: mô tả, schema request/response, mã lỗi, và ví dụ.

## 4. Thử một request (workflow điển hình)

1. Mở http://localhost:8000/docs.
2. Bấm vào endpoint muốn thử, ví dụ **POST `/api/v1/vehicles/`**.
3. Bấm **Try it out** → sửa JSON trong ô **Request body**, ví dụ:
   ```json
   {
     "license_plate": "59a-12345",
     "brand": "Toyota",
     "model": "Camry",
     "year": 2024
   }
   ```
4. Bấm **Execute**.
5. Xem **Response body**, **Response code** và **Response headers** ở ngay bên dưới.
   Swagger cũng in sẵn lệnh **curl** tương đương để bạn copy chạy ở terminal.

## 5. Endpoint có bảo vệ (Authorize)

Các route onboarding/auth yêu cầu token (Firebase / OAuth). Trên Swagger:

1. Bấm nút **Authorize** (ổ khóa, góc phải trên).
2. Dán token vào (thường theo dạng `Bearer <token>`).
3. Từ đó mọi request "Try it out" sẽ tự đính kèm header `Authorization`.

Endpoint đăng nhập để lấy token: **POST `/api/v1/oauth/sign-in`** (tag `onboarding`).

## 6. Định dạng lỗi (error envelope)

Các lỗi domain của onboarding/auth trả về theo bao chuẩn (xem `src/main.py`):

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "…",
    "details": { "field": "license_plate" },
    "traceId": "…"
  }
}
```

- Route onboarding/auth: lỗi validate trả **400** kèm envelope trên.
- Các route khác: giữ mặc định FastAPI **422** với `{"detail": [...]}`.
- Gửi header `X-Request-ID` để nhận lại `traceId` tương ứng khi debug.

## 7. Mock EV system (dịch vụ ngoài)

`mock-ev-system` là một FastAPI riêng, giả lập hệ thống hãng xe. Swagger của nó:
http://localhost:8100/docs (chạy `make mock-run` trong `backend/`). Backend gọi
service này qua `OEM_API_BASE_URL`, không import trực tiếp.
