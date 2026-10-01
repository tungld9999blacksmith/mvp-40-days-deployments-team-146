# ev_mock_data — Sinh dữ liệu, import và truy vấn dữ liệu trên mock-ev-system

Tool dòng lệnh (Python, chỉ dùng thư viện chuẩn) làm việc với
[mock-ev-system](../../backend/mock-ev-system/README.md) qua HTTP:

1. **Sinh dữ liệu** xe điện nhất quán: chủ xe → xe → ODO/pin → hợp đồng bảo hành → claim → lịch sử bảo dưỡng.
2. **Import** dữ liệu lên mock (cả bộ nhiều bảng trong một transaction, hoặc từng bảng).
3. **Truy vấn** dữ liệu: lọc theo bảng (admin API) hoặc gọi bất kỳ API nghiệp vụ nào của mock.
4. **Export / dump** toàn bộ DB của mock ra file JSON hoặc SQL để chia sẻ cho team.

```
tools/ev_mock_data/
  .env.example     mẫu cấu hình (copy thành .env)
  ev_mock_data.py  CLI (config, entities, generate, import, seed, create, query, find, get, post, export, dump, delete, reset)
  generator.py     sinh dữ liệu (đọc master data trên mock để FK luôn hợp lệ)
  client.py        HTTP client
  data/            file sinh ra (git-ignored)
```

---

## 1. Cách hoạt động

mock-ev-system lưu dữ liệu trong **SQLite in-memory**. Tool không đụng trực tiếp vào DB mà gọi
nhóm API **`/admin/*`** của mock:

| Method | Path | Mô tả |
|---|---|---|
| GET | `/admin/entities` | Danh sách bảng, khoá chính, cột, số dòng |
| GET | `/admin/data/{entity}?field=value&limit=&offset=` | Truy vấn một bảng; query param khác = lọc bằng |
| POST | `/admin/data/{entity}[?upsert=true]` | Tạo bản ghi cho **một bảng** (body: object list) |
| POST | `/admin/import` | Import **nhiều bảng** một lần: `{"mode": "upsert"\|"insert", "data": {entity: [...]}}` |
| DELETE | `/admin/data/{entity}/{key}` | Xoá một bản ghi |
| GET | `/admin/dump?format=sql\|json` | Dump toàn bộ DB (SQL script SQLite hoặc JSON đúng format import) |
| POST | `/admin/reset` | Xoá hết, nạp lại dữ liệu khởi động |

- Import chạy **trong một transaction**: lỗi ở bất kỳ bản ghi nào thì không ghi gì cả, và mock trả về
  `422 {"entity", "index", "message"}` chỉ đúng bản ghi lỗi.
- Mock tự **kiểm tra khoá ngoại** (SQLite mặc định không kiểm), trùng `vin` / `license_plate` cũng bị chặn.
- Các bảng được import theo thứ tự FK, nên một file có thể chứa cả cha lẫn con.
- Khi mock có biến `MOCK_ADMIN_TOKEN`, mọi lệnh admin phải gửi header `X-Admin-Token`
  (tool tự gửi từ `EV_MOCK_ADMIN_TOKEN`). **Nên đặt token cho mock deploy trên Railway.**

Tên entity: `vehicle_models`, `owners`, `service_centers`, `vehicles`, `vehicle_usage`,
`warranty_policies`, `warranties`, `warranty_claims`, `maintenance_schedules`,
`maintenance_items`, `service_history`.

---

## 2. Bắt đầu nhanh

Yêu cầu: Python 3.11+ (có sẵn khi dùng `uv` của backend). Không cần cài thêm gì.

```bash
# 1) Chạy mock-ev-system
cd backend && uv run --package mock-ev-system uvicorn mock_ev_system.main:app --reload --port 8100

# 2) (Tuỳ chọn) cấu hình tool — mặc định đã trỏ tới http://localhost:8100
cp tools/ev_mock_data/.env.example tools/ev_mock_data/.env

# 3) Kiểm tra kết nối + số dòng mỗi bảng
python tools/ev_mock_data/ev_mock_data.py config

# 4) Sinh 10 chủ xe (mỗi người 1-3 xe) và import luôn
python tools/ev_mock_data/ev_mock_data.py seed -n 10 --vehicles 1-3 --seed 2026
```

> Các ví dụ dưới đây viết tắt `python tools/ev_mock_data/ev_mock_data.py` thành `evm`.

### Cấu hình (`tools/ev_mock_data/.env`)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `EV_MOCK_URL` | `http://localhost:8100` | URL của mock (local hoặc Railway) |
| `EV_MOCK_ADMIN_TOKEN` | — | Bằng `MOCK_ADMIN_TOKEN` của mock (để trống nếu mock không đặt) |
| `EV_MOCK_DATA_DIR` | `tools/ev_mock_data/data` | Thư mục file sinh ra (tương đối theo gốc repo) |

Thứ tự ưu tiên: tham số `--url` / `--token` > biến môi trường shell > `.env` > mặc định.

---

## 3. Các lệnh

### 3.1 Sinh dữ liệu — `generate` / `seed`

```bash
evm generate -n 20                       # chỉ ghi file JSON, chưa import
evm seed -n 20 --vehicles 1-3            # sinh + import (file vẫn được lưu lại)
evm seed -n 5 --models MDL-01 MDL-05     # chỉ dùng các mẫu xe này
evm seed -n 5 --seed 42 --today 2026-10-01   # tái lập được y hệt
```

| Tuỳ chọn | Mặc định | Ý nghĩa |
|---|---|---|
| `-n, --owners` | 5 | Số chủ xe |
| `--vehicles` | `1-2` | Số xe mỗi chủ: `N` hoặc `MIN-MAX` |
| `--models` | tất cả | Giới hạn mẫu xe (`model_id`) |
| `--claim-rate` | 0.3 | Xác suất một xe có claim bảo hành |
| `--email-domain` | `example.com` | Domain email chủ xe |
| `--today` | hôm nay | Ngày mốc tính tuổi xe, số km, trạng thái bảo hành |
| `--seed` | ngẫu nhiên | Seed để sinh lại đúng bộ dữ liệu |
| `--out` | `<data dir>/<lệnh>-<thời gian>.json` | File output |
| `--stdout` (generate) / `--no-save` (seed) | | In ra màn hình / không lưu file |

Dữ liệu sinh ra:
- **Chủ xe**: tên tiếng Việt, SĐT, email (không trùng), CCCD 12 số theo mã tỉnh.
- **Xe**: VIN 17 ký tự theo mẫu xe, biển số theo tỉnh (vd. `30A-12345`), không trùng với dữ liệu sẵn có.
- **ODO / pin**: km tương quan tuổi xe (12k–22k km/năm), SOH giảm dần theo tuổi và km.
- **Bảo hành**: mỗi chính sách của mẫu xe sinh một hợp đồng, `active` / `expired` theo `--today`.
- **Claim**: approved / rejected (kèm lý do) / pending.
- **Lịch sử bảo dưỡng**: theo các mốc `maintenance_schedules` mà xe đã vượt qua, ở xưởng cùng khu vực.
- ID nối tiếp ID lớn nhất đang có (`OWN-006`, `VEH-008`...), nên không đè dữ liệu cũ.

### 3.2 Import — `import` / `create`

```bash
evm import tools/ev_mock_data/data/generated-20261001-101500.json          # upsert (mặc định)
evm import my-data.json --mode insert     # báo lỗi nếu id đã tồn tại

# Tạo bản ghi cho một bảng
evm create service_centers --set center_id=SC-04 --set name="EV Care Cần Thơ" \
    --set region="Cần Thơ" --set type=service_only \
    --set manager_email=sc04@example.com --set manager_national_id=092190000404
evm create owners --file owners.json      # file chứa 1 object hoặc 1 list
evm create vehicle_usage --json '{"vehicle_id":"VEH-001","current_km":50000,"battery_soh":95,"last_updated_at":"2026-10-01T08:00:00"}' --upsert
```

File import có dạng `{"data": {"owners": [...], "vehicles": [...]}}` hoặc `{"owners": [...]}`.
Với `--set`, giá trị là số / `true` / `false` / `null` được hiểu là JSON; còn lại là chuỗi
(chuỗi toàn chữ số như CCCD: đặt trong ngoặc kép JSON, vd. `--set national_id='"0792..."'`, hoặc dùng `--json`).

### 3.3 Truy vấn — `query` / `get` / `post`

> Tra cứu mọi dữ liệu liên quan tới **một email / VIN / biển số / CCCD / SĐT** (chọn bảng, cột hoặc `--all`):
> dùng `evm find` — xem [DEV_GUIDE.md §3](../../DEV_GUIDE.md#3-tra-cứu-dữ-liệu-mock-theo-định-danh-find).

```bash
evm entities                                           # bảng + cột
evm query vehicles                                     # bảng dạng table
evm query vehicles -w current_owner_id=OWN-006 --fields vehicle_id,vin,license_plate
evm query warranty_claims -w status=rejected --json
evm query service_history --limit 20 --offset 40

# API nghiệp vụ của mock (viết path KHÔNG có "/" đầu nếu dùng Git Bash)
evm get vehicles --table
evm get vehicles/VEH-008/next-maintenance
evm get vehicles/lookup/by-plate -p plate=30A-12345
evm post vehicles/verify-ownership --body-file verify.json
```

> Git Bash tự đổi `/vehicles` thành `C:/Program Files/Git/vehicles`; tool sẽ báo lỗi nếu gặp trường hợp này.

### 3.4 Export / dump / dọn dữ liệu

```bash
evm export                         # JSON, import lại được bằng `evm import`
evm export --entities owners vehicles
evm dump                           # SQL script SQLite (schema + data)
evm dump --format json
evm samples -n 3                   # Markdown: vài dòng mẫu mỗi bảng -> backend/mock-ev-system/seed-data/SAMPLES.md
evm delete vehicles VEH-010
evm reset -y                       # nạp lại dữ liệu khởi động
```

---

## 4. Bản dump dùng chung cho team

Bản dump được commit tại
[`backend/mock-ev-system/seed-data/ev-mock-dump.sql`](../../backend/mock-ev-system/seed-data/ev-mock-dump.sql)
(và bản JSON `ev-mock-dump.json`). Dump hiện tại gồm seed gốc cộng thêm 10 chủ xe sinh bằng
`seed -n 10 --vehicles 1-3 --seed 2026 --today 2026-10-01`, tổng cộng 15 chủ xe, 28 xe,
112 hợp đồng bảo hành, 10 claim và 68 lượt bảo dưỡng.

**Mock nạp dump lúc khởi động** khi có biến `MOCK_SEED_DUMP`:

- **Docker** (`Dockerfile`, `Dockerfile.railway`, compose): đã copy sẵn dump vào image và đặt
  `MOCK_SEED_DUMP=/app/seed-data/ev-mock-dump.sql`. Muốn dùng seed gốc thì chạy với `-e MOCK_SEED_DUMP=`.
- **Chạy local**:
  ```bash
  cd backend
  MOCK_SEED_DUMP=mock-ev-system/seed-data/ev-mock-dump.sql \
    uv run --package mock-ev-system uvicorn mock_ev_system.main:app --reload --port 8100
  # PowerShell: $env:MOCK_SEED_DUMP="mock-ev-system/seed-data/ev-mock-dump.sql"; uv run ...
  ```
- `POST /admin/reset` (`evm reset`) nạp lại đúng dump này.
- Mở bằng SQLite: `sqlite3 ev_mock.db < backend/mock-ev-system/seed-data/ev-mock-dump.sql`.

**Cập nhật dump** sau khi thêm hoặc sửa dữ liệu:

```bash
evm dump --out backend/mock-ev-system/seed-data/ev-mock-dump.sql
evm dump --format json --out backend/mock-ev-system/seed-data/ev-mock-dump.json
evm samples                        # cập nhật SAMPLES.md (xem nhanh dữ liệu mẫu)
git add backend/mock-ev-system/seed-data && git commit -m "chore(mock): update shared dump"
```

> Lưu ý: dump chụp trạng thái tại thời điểm chạy, gồm cả `current_km` mà simulator đã tăng.
> Khi nạp từ dump, các biến override email (`MOCK_OWN001_EMAIL`, `MOCK_SC01_MANAGER_EMAIL`...)
> **không** có tác dụng; muốn đổi email thì sửa dữ liệu bằng `evm create ... --upsert` rồi dump lại.
> Nếu sửa cấu trúc bảng (`models.py`), phải tạo lại dump, nếu không mock sẽ chạy theo schema cũ trong dump.
