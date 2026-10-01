# mock-ev-system

Service FastAPI giả lập hệ thống của công ty xe điện, chạy như một hệ thống **bên ngoài**. EV Care backend chỉ được gọi nó qua HTTP, không import code từ đây. Phần dùng chung giữa hai bên đặt ở `shared/ev-contracts`.

## Chạy

```bash
# Từ thư mục backend/
uv run --package mock-ev-system uvicorn mock_ev_system.main:app --reload --port 8100
```

Swagger UI: http://localhost:8100/docs

## API Endpoints

### 🚗 Vehicles & Owners

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/vehicles` | Danh sách tất cả xe |
| GET | `/vehicles/{vehicle_id}` | Chi tiết xe (kèm model & chủ xe) |
| GET | `/vehicles/lookup/by-vin?vin=...` | Tra cứu xe theo VIN |
| GET | `/vehicles/lookup/by-plate?plate=...` | Tra cứu xe theo biển số |
| GET | `/owners` | Danh sách chủ xe |
| GET | `/owners/{owner_id}` | Chi tiết chủ xe (kèm danh sách xe) |

### 🛡️ Warranty

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/warranty-policies/{model_id}` | Chính sách bảo hành theo model |
| GET | `/vehicles/{vehicle_id}/warranties` | Hợp đồng bảo hành của xe |
| GET | `/vehicles/{vehicle_id}/warranty-claims` | Lịch sử yêu cầu bảo hành |
| GET | `/warranty-claims/{claim_id}` | Chi tiết claim (kèm lý do từ chối) |

### 🔧 Maintenance

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/vehicles/{vehicle_id}/maintenance-schedule` | Lịch bảo dưỡng chuẩn theo model |
| GET | `/vehicles/{vehicle_id}/service-history` | Lịch sử bảo dưỡng thực tế |
| GET | `/vehicles/{vehicle_id}/next-maintenance` | Mốc tiếp theo (computed) — cho AI nhắc lịch |
| POST | `/vehicles/{vehicle_id}/service-history` | Ghi một lần bảo dưỡng (demo) → gửi webhook `vehicle.service_history.updated` |

### 📊 Vehicle Usage (Realtime)

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/vehicles/{vehicle_id}/usage` | Snapshot hiện tại (km, battery SOH) |
| GET | `/vehicles/{vehicle_id}/usage/stream` | **SSE stream** — odometer realtime |

### 🔔 Webhooks (gửi sang EV Care)

Mock ký và gửi webhook theo hợp đồng API-VEH-004 (`docs/specs/sprint-2/api/us-017-sprint-2-spec.api.md`). Header, tên sự kiện và hàm ký nằm trong `ev_contracts`.

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/webhooks/config` | Cấu hình hiện tại (ẩn secret) |
| POST | `/webhooks/test-events` | Gửi ngay một sự kiện đã ký, trả kết quả giao |

Sự kiện tự động:

- `vehicle.usage.updated` — sau mỗi tick của simulator ODO, tối đa 1 lần / xe / `MOCK_WEBHOOK_USAGE_MIN_INTERVAL_SECONDS`.
- `vehicle.service_history.updated` — sau `POST /vehicles/{vehicle_id}/service-history`.

Biến môi trường:

| Biến | Mặc định | Ý nghĩa |
|------|----------|---------|
| `MOCK_WEBHOOK_URL` | (trống = tắt) | URL nhận của EV Care, vd. `http://localhost:8000/api/v1/integrations/oem/webhooks` |
| `MOCK_WEBHOOK_SECRET` | (trống) | Secret HMAC, phải bằng `OEM_WEBHOOK_SECRET` của backend |
| `MOCK_WEBHOOK_USAGE_MIN_INTERVAL_SECONDS` | `300` | Khoảng cách tối thiểu giữa 2 sự kiện usage của một xe |
| `MOCK_WEBHOOK_TIMEOUT_SECONDS` | `5` | Timeout mỗi lần gửi |

Retry 3 lần (1 s, 4 s) khi lỗi mạng / 5xx; không retry 4xx.

### 📋 Lookup (Master Data)

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/models` | Danh sách mẫu xe |
| GET | `/models/{model_id}` | Chi tiết mẫu xe |
| GET | `/service-centers` | Danh sách đại lý / xưởng dịch vụ |
| GET | `/service-centers/{center_id}` | Chi tiết xưởng |
| GET | `/health` | Health check |

### ✅ Verification

| Method | Path | Mô tả |
|--------|------|--------|
| POST | `/vehicles/verify-ownership` | Xác thực chủ xe (VIN + biển số + model + email + CCCD) |
| POST | `/service-centers/verify-manager` | Xác thực người quản lý xưởng (email + CCCD) → trả về xưởng tương ứng |

### 🗄️ Admin (data import / query / dump)

Dùng bởi CLI [`tools/ev_mock_data`](../../tools/ev_mock_data/README.md). Nếu đặt `MOCK_ADMIN_TOKEN`, mọi request phải gửi header `X-Admin-Token`.

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/admin/entities` | Bảng, khoá chính, cột, số dòng |
| GET | `/admin/data/{entity}` | Truy vấn (query param = lọc bằng, `limit`, `offset`) |
| POST | `/admin/data/{entity}` | Tạo bản ghi một bảng (`?upsert=true` để ghi đè) |
| POST | `/admin/import` | Import nhiều bảng trong một transaction (kiểm tra FK) |
| DELETE | `/admin/data/{entity}/{key}` | Xoá một bản ghi |
| GET | `/admin/dump?format=sql\|json` | Dump toàn bộ DB |
| POST | `/admin/reset` | Nạp lại dữ liệu khởi động |

**Dữ liệu khởi động:** nếu có `MOCK_SEED_DUMP=<file .sql>`, mock nạp dump đó thay cho seed gốc. Docker image đã có sẵn dump dùng chung [`seed-data/ev-mock-dump.sql`](seed-data/ev-mock-dump.sql) (15 chủ xe, 28 xe). Chạy với `-e MOCK_SEED_DUMP=` để dùng seed gốc bên dưới.

**Gmail dev:** `MOCK_DEV_OWNER_EMAILS=you@gmail.com[:CCCD],...` (và `MOCK_DEV_OWNER_VEHICLES`, mặc định 2) — sau khi nạp dump/seed, mock tự tạo chủ xe + xe + ODO + bảo hành + lịch sử bảo dưỡng cho từng email chưa có. Xem [DEV_GUIDE.md §2](../../DEV_GUIDE.md#2-mock-hãng-xe-tạo-dữ-liệu-cho-gmail-của-bạn).

## SSE Stream (Realtime Odometer)

Kết nối SSE để nhận update km mỗi 5 giây:

```bash
curl -N http://localhost:8100/vehicles/VEH-001/usage/stream
```

Output:
```
data: {"vehicle_id": "VEH-001", "current_km": 42502, "battery_soh": 96.2, "last_updated_at": "2026-09-26T10:00:05"}

data: {"vehicle_id": "VEH-001", "current_km": 42504, "battery_soh": 96.2, "last_updated_at": "2026-09-26T10:00:10"}
```

## Dữ liệu Mock

- **7 xe** (VF5, VF6×2, VF7, VF8×2, VF9) — **5 chủ xe** (1-2 xe/chủ)
- **28 hợp đồng bảo hành** (4 component × 7 xe)
- **4 warranty claims** (1 rejected/pin, 1 approved/khung gầm, 1 rejected/hết hạn, 1 pending)
- **5 mốc bảo dưỡng** × 7 model + items chi tiết cho model VF5
- **19 lượt bảo dưỡng thực tế** (mỗi xe 2-3 lượt)
- **3 xưởng dịch vụ** (Hà Nội, HCM, Đà Nẵng), mỗi xưởng có 1 người quản lý (email + CCCD):
  `SC-01` ha.tran.sc01@example.com / 001190000101 · `SC-02` khoa.nguyen.sc02@example.com / 079190000202 · `SC-03` lan.vo.sc03@example.com / 048190000303.
  Đổi email bằng env `MOCK_SC01_MANAGER_EMAIL` (… `SC02`, `SC03`) để đăng nhập Google thật trên Workshop Portal.

Dữ liệu deterministic — restart là fresh, lặp lại được.

## Kiến trúc

```
mock_ev_system/
├── main.py          # FastAPI app + lifespan
├── db.py            # SQLite in-memory + StaticPool
├── models.py        # 11 SQLModel table models (theo proposed_erd.md)
├── seed.py          # Seed data deterministic
├── service.py       # Business logic / data access
├── simulator.py     # Background odometer simulator + SSE pub/sub
└── routers/
    ├── vehicles.py  # Vehicle & Owner endpoints
    ├── warranty.py  # Warranty endpoints
    ├── maintenance.py # Maintenance endpoints
    ├── usage.py     # Usage snapshot + SSE stream
    └── lookup.py    # Models & Service Centers
```
