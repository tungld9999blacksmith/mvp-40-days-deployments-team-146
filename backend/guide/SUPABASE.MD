# Supabase — Hướng dẫn kết nối & thiết lập

## 1. Thông tin kết nối

| Thông số | Giá trị |
|---|---|
| **Direct Host** | `db.<project-ref>.supabase.co` (IPv6 only) |
| **Pooler Host** | `aws-0-ap-southeast-1.pooler.supabase.com` (IPv4) |
| **Pooler Port** | `6543` (transaction mode) / `5432` (session mode) |
| **User (pooler)** | `postgres.<project-ref>` |
| **Database** | `postgres` |
| **SSL** | `require` |

> **Lưu ý**: Direct host (`db.xxx.supabase.co`) chỉ trả về IPv6.
> Nếu mạng không hỗ trợ IPv6, dùng **Connection Pooler** với hostname `aws-0-<region>.pooler.supabase.com`.

## 2. Biến môi trường (.env)

```env
DATABASE_HOST=aws-0-ap-southeast-1.pooler.supabase.com
DATABASE_PORT=6543
DATABASE_NAME=postgres
DATABASE_USER=postgres.<project-ref>
DATABASE_PASSWORD=<your-password>
DATABASE_SSLMODE=require

SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<supabase-anon-or-service-key>

FILE_STORAGE=supabase
SUPABASE_STORAGE_BUCKET=documents
STORAGE_SIGNED_URL_TTL_SECONDS=3600
```

## 3. Kiểm tra kết nối bằng CLI

### 3.1. Python — SQLAlchemy

```bash
cd backend
python -c "
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
load_dotenv('../.env')

host = os.getenv('DATABASE_HOST')
port = os.getenv('DATABASE_PORT')
db   = os.getenv('DATABASE_NAME')
user = os.getenv('DATABASE_USER')
pw   = os.getenv('DATABASE_PASSWORD')
ssl  = os.getenv('DATABASE_SSLMODE', 'require')

url = f'postgresql+psycopg2://{quote_plus(user)}:{quote_plus(pw)}@{host}:{port}/{db}?sslmode={ssl}'
engine = create_engine(url, connect_args={'connect_timeout': 10})
with engine.connect() as conn:
    print(conn.execute(text('SELECT version()')).fetchone()[0])
    print('Connection OK')
"
```

### 3.2. psql (nếu đã cài PostgreSQL client)

```bash
psql "postgresql://postgres.<project-ref>:<password>@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require"
```

### 3.3. DNS debug — kiểm tra resolve hostname

```bash
# Kiểm tra direct host (IPv6 only)
nslookup db.<project-ref>.supabase.co

# Kiểm tra pooler host (IPv4)
nslookup aws-0-ap-southeast-1.pooler.supabase.com
```

### 3.4. Supabase REST API

```bash
curl -s https://<project-ref>.supabase.co/rest/v1/ \
  -H "apikey: <service-role-key>" \
  -H "Authorization: Bearer <service-role-key>"
```

## 4. Alembic migration

```bash
cd backend

# Tạo migration mới (autogenerate từ SQLModel)
alembic revision --autogenerate -m "describe your change"

# Chạy migration
alembic upgrade head

# Xem trạng thái migration hiện tại
alembic current

# Rollback 1 bước
alembic downgrade -1
```

## 5. Seed data

```bash
cd backend

# Chạy seed SQL trực tiếp qua psql
psql "<connection-string>" -f seed.sql

# Hoặc qua Python
python -c "
from sqlalchemy import create_engine, text
# ... (build URL như mục 3.1)
with open('seed.sql') as f:
    sql = f.read()
with engine.connect() as conn:
    conn.execute(text(sql))
    conn.commit()
    print('Seed data inserted')
"
```

## 6. Xử lý sự cố

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `could not translate host name` | Mạng không hỗ trợ IPv6 | Dùng pooler host thay direct host |
| `password authentication failed` | Sai password hoặc ký tự đặc biệt chưa encode | URL-encode password bằng `quote_plus()` |
| `ModuleNotFoundError: psycopg` | Dùng driver `psycopg` (v3) nhưng chưa cài | Cài `psycopg2-binary` và dùng `postgresql+psycopg2://` |
| `SSL connection required` | Thiếu `sslmode=require` | Thêm `?sslmode=require` vào connection string |

## 7. File Storage (bucket)

- Code: `src/infrastructure/storage/` — interface `FileStorage` (`base.py`), implementation
  `SupabaseFileStorage` (`supabase_store.py`), `create_file_storage` / `get_file_storage` (factory + DI).
- The bucket (default `documents`) must already exist and stay **private**; read files through
  `signed_url(...)`. `SUPABASE_KEY` must be the server-side secret key (bypasses Storage RLS).
- Object keys must be ASCII: use `safe_key(...)` for Vietnamese file names.

```python
from src.infrastructure.storage import get_file_storage

storage = get_file_storage()
storage.upload_file("data/knowledge/raw/manual.pdf", "manuals/vf8/manual.pdf")
pdf = storage.download("manuals/vf8/manual.pdf")
url = storage.signed_url("manuals/vf8/manual.pdf", expires_in=600)
```

### CLI (`scripts/storage_cli.py`, run from `backend/`)

```bash
python scripts/storage_cli.py upload data/knowledge/raw -r --prefix manuals --include "*.pdf" --dry-run
python scripts/storage_cli.py upload data/knowledge/raw -r --prefix manuals --include "*.pdf" --skip-existing
python scripts/storage_cli.py ls manuals -r
python scripts/storage_cli.py info manuals/manual.pdf
python scripts/storage_cli.py url manuals/manual.pdf --expires 600
python scripts/storage_cli.py download manuals/manual.pdf -o ./tmp
python scripts/storage_cli.py delete manuals/old --prefix
```
