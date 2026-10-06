# Sử dụng Alembic để quản lý migration CSDL

Alembic quản lý schema của EV Care. Mọi lệnh chạy từ thư mục `backend/` (nơi có `alembic.ini`), qua `uv run`:

```bash
cd backend
uv run alembic <lệnh>
```

## Cấu trúc

| Đường dẫn | Vai trò |
|---|---|
| `backend/alembic.ini` | Cấu hình Alembic (`script_location = alembic`). **Không** chứa URL DB |
| `backend/alembic/env.py` | Nạp model, lấy URL DB từ `get_settings().sqlalchemy_database_url` |
| `backend/alembic/versions/` | Các file migration (chuỗi tuyến tính, 1 `head`) |

## Cấu hình kết nối DB

`env.py` lấy URL từ `src/config.py` (đọc từ `.env` gốc), theo thứ tự ưu tiên:

1. `DATABASE_URL` nếu có.
2. Nếu không có `DATABASE_PASSWORD` → SQLite `sqlite:///./data/app.db` (chỉ để chạy nhanh local).
3. Ngược lại ghép từ `DATABASE_USER / PASSWORD / HOST / PORT / NAME / SSLMODE` thành URL PostgreSQL (`postgresql+psycopg2`).

Lưu ý: các migration dùng tính năng PostgreSQL (extension `vector`/pgvector, `unaccent`, ...), nên môi trường thật cần **PostgreSQL**, không dùng SQLite. User DB cần quyền `CREATE EXTENSION` (hoặc extension đã được bật sẵn).

## Quy trình tạo migration

1. Sửa/thêm model (SQLModel).
2. **Đảm bảo model được import trong `alembic/env.py`.** Autogenerate chỉ thấy bảng đã đăng ký vào `SQLModel.metadata`. Hiện `env.py` import sẵn `src.common.core` (đăng ký toàn bộ bảng core), `src.infrastructure.vectorstore.models` và domain của các module `auth`, `authorization`, `vehicle_owner_onboarding`, `workshop_owner_auth`, `workshop_owner_onboarding`. Module mới có bảng riêng ngoài các chỗ trên → thêm dòng import vào `env.py`, nếu không autogenerate sẽ không sinh gì (hoặc sinh lệnh `drop_table`).
3. Sinh migration:

   ```bash
   uv run alembic revision --autogenerate -m "add items table"
   ```

4. **Đọc lại file sinh ra trong `alembic/versions/`** trước khi áp dụng. Autogenerate không phát hiện được hết (đổi tên cột/bảng thành drop + add, enum, extension, data migration). Cần sửa tay nếu cần, và bảo đảm `downgrade()` đúng.
5. Áp dụng:

   ```bash
   uv run alembic upgrade head
   ```

`env.py` bật `compare_type=True`, nên thay đổi kiểu cột cũng được phát hiện.

## Quy ước

- Tên file: `<revision>_<mô_tả_snake_case>.py` (ví dụ `c8f2d4a6e1b9_add_service_record_is_periodic.py`).
- Mỗi migration một thay đổi logic; viết đủ `upgrade()` và `downgrade()`.
- Không sửa migration đã merge vào `develop`/`main` — tạo migration mới để sửa.
- Tên bảng/cột, comment, message trong migration viết bằng tiếng Anh.
- Khi 2 nhánh cùng tạo migration từ một `down_revision`, Alembic sẽ có nhiều head (xem phần xử lý lỗi).

## Các lệnh thường dùng

```bash
uv run alembic current                 # revision hiện tại của DB
uv run alembic heads                   # revision đầu mới nhất trong code (phải chỉ có 1)
uv run alembic history --verbose       # lịch sử migration
uv run alembic upgrade head            # nâng lên bản mới nhất
uv run alembic upgrade +1              # nâng 1 bước
uv run alembic downgrade -1            # rollback 1 bước
uv run alembic downgrade <revision>    # rollback về revision chỉ định
uv run alembic upgrade head --sql      # in SQL ra stdout (offline), không chạy vào DB
uv run alembic stamp head              # đánh dấu DB đã ở head mà không chạy migration
uv run alembic check                   # báo lỗi nếu model lệch với DB (còn migration chưa sinh)
```

## Chuỗi migration hiện tại

Thứ tự từ cũ đến mới (`head` là cuối cùng):

| # | Revision | Nội dung |
|---|---|---|
| 1 | `272915ecc478` | create authorization tables |
| 2 | `a1f4c2d3e5b6` | add onboarding tables |
| 3 | `b2e5d7f1a9c4` | add auth_event + last_logout |
| 4 | `c3f8a1d2e4b7` | add workshop owner onboarding |
| 5 | `d4a9b2c5e6f1` | add workshop owner auth_event |
| 6 | `e5b1c7d9f2a3` | add core domain tables |
| 7 | `f6c3a8d1b2e4` | reminder channel: Discord |
| 8 | `a7d2e9c4f1b3` | add vehicle OEM sync tables |
| 9 | `b7e1c2f34d58` | add conversation + vector store (pgvector, `unaccent`) |
| 10 | `c8f2d4a6e1b9` | add `service_record.is_periodic` |
| 11 | `d9a3e5b7f2c1` | add maintenance reminder tables |
| 12 | `e2b6a4c8d1f7` | add booking capacity |
| 13 | `f1d3b5a7c9e2` | add booking lifecycle, quote, CRM (**head**) |

Danh sách này chỉ là ảnh chụp; nguồn sự thật là `uv run alembic history` / `heads`.

## Xử lý sự cố

- **`Multiple head revisions are present`** — hai migration cùng `down_revision`. Merge:

  ```bash
  uv run alembic merge heads -m "merge heads"
  uv run alembic upgrade head
  ```

- **`Target database is not up to date`** khi chạy `revision --autogenerate` — DB chưa ở `head`; chạy `uv run alembic upgrade head` trước.
- **`Can't locate revision identified by ...`** — DB đang trỏ tới revision không có trong code (thường do đổi nhánh). Checkout đúng nhánh, hoặc với DB dev dùng `alembic stamp <revision>` / dựng lại DB.
- **Autogenerate sinh `drop_table` ngoài ý muốn** — model chưa được import trong `env.py` (xem bước 2). Xóa các lệnh drop đó và thêm import.
- **Lỗi `permission denied to create extension`** — cấp quyền hoặc bật `vector`, `unaccent` bằng user có quyền superuser trước khi chạy migration.
- **Dev local muốn làm lại từ đầu** — xóa/tạo lại database rồi `uv run alembic upgrade head`. Tuyệt đối không làm trên môi trường dùng chung/production.
