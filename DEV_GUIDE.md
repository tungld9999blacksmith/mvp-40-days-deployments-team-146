# DEV GUIDE — EV Care

Điểm bắt đầu cho dev: mục lục mọi hướng dẫn trong repo và các hướng dẫn dùng hằng ngày với mock hãng xe và tool `api_sync`.

## Mục lục

1. [Mục lục hướng dẫn dev](#1-mục-lục-hướng-dẫn-dev)
2. [Mock hãng xe: tạo dữ liệu cho Gmail của bạn](#2-mock-hãng-xe-tạo-dữ-liệu-cho-gmail-của-bạn)
3. [Tra cứu dữ liệu mock theo định danh (`find`)](#3-tra-cứu-dữ-liệu-mock-theo-định-danh-find)
4. [Quy trình test onboarding chủ xe bằng Gmail thật](#4-quy-trình-test-onboarding-chủ-xe-bằng-gmail-thật)
5. [Đồng bộ schema API sang TypeScript & sinh dữ liệu mẫu (`api_sync`)](#5-đồng-bộ-schema-api-sang-typescript--sinh-dữ-liệu-mẫu-api_sync)

---

## 1. Mục lục hướng dẫn dev

### Bắt đầu & chạy local

| Tài liệu | Nội dung |
|---|---|
| [README.md](README.md) | Giới thiệu dự án |
| [docs/guide/setup/quick-start.md](docs/guide/setup/quick-start.md) | Quick start |
| [docs/RUN_LOCAL_BACKEND.md](docs/RUN_LOCAL_BACKEND.md) | Chạy backend local bằng Docker, debug bằng terminal |
| [docs/RUN_LOCAL_BACKEND_RAILWAY.md](docs/RUN_LOCAL_BACKEND_RAILWAY.md) | Debug backend local với hạ tầng trên Railway |
| [docs/guide/troubleshooting.md](docs/guide/troubleshooting.md) | Sửa lỗi thường gặp |
| [docs/guide/free-accounts.md](docs/guide/free-accounts.md) | Đăng ký tài khoản miễn phí (LLM, vector DB...) |
| [docs/guide/cost-management.md](docs/guide/cost-management.md) | Quản lý chi phí API |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Quy trình đóng góp |

### Kiến trúc & nghiệp vụ

| Tài liệu | Nội dung |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Kiến trúc tổng quan |
| [docs/architecture.md](docs/architecture.md) · [docs/architecture/README.md](docs/architecture/README.md) · [docs/architecture_diagram.md](docs/architecture_diagram.md) | Kiến trúc hệ thống, sơ đồ |
| [docs/product/README.md](docs/product/README.md) · [docs/product/PRD_EV_Care_MVP.md](docs/product/PRD_EV_Care_MVP.md) | Nghiệp vụ, PRD MVP |
| [docs/specs/INSTRUCTION.MD](docs/specs/INSTRUCTION.MD) | Cách viết / đọc tài liệu đặc tả (FF, API, FE, Entity) |
| [docs/specs/](docs/specs/) | Đặc tả theo sprint (`sprint-1` … `sprint-4`), entity, AI agent, mock system |
| [docs/design/design-guidelines.md](docs/design/design-guidelines.md) · [docs/design/wireframe.md](docs/design/wireframe.md) | Design guidelines, wireframe |

### Backend

| Tài liệu | Nội dung |
|---|---|
| [backend/guide/api.md](backend/guide/api.md) | Cấu trúc backend & thiết kế API |
| [backend/guide/alembic.md](backend/guide/alembic.md) | Migration CSDL với Alembic |
| [backend/guide/redis.md](backend/guide/redis.md) | Redis toolkit |
| [backend/guide/qdrant.md](backend/guide/qdrant.md) | Qdrant vector store |
| [backend/guide/agent.md](backend/guide/agent.md) | AI agent |
| [backend/src/agents/tools/RAG/README.md](backend/src/agents/tools/RAG/README.md) | RAG engine |
| [backend/guide/swagger.md](backend/guide/swagger.md) | Dùng Swagger UI |
| [backend/guide/testing-swagger-onboarding.md](backend/guide/testing-swagger-onboarding.md) | Test module qua Swagger + mock hãng (Firebase Auth Emulator) |
| [backend/guide/testing.md](backend/guide/testing.md) | Viết & chạy unit test backend |
| [backend/guide/reference.md](backend/guide/reference.md) | Tài liệu tham khảo |
| [docs/guide/code-style/python.md](docs/guide/code-style/python.md) | Python style guide |

### Mock hãng xe (OEM) & dữ liệu

| Tài liệu | Nội dung |
|---|---|
| [backend/mock-ev-system/README.md](backend/mock-ev-system/README.md) | mock-ev-system: API, cấu hình |
| [backend/mock-ev-system/seed-data/SAMPLES.md](backend/mock-ev-system/seed-data/SAMPLES.md) | Dữ liệu mẫu của dump dùng chung |
| [backend/shared/ev-contracts/README.md](backend/shared/ev-contracts/README.md) | Contract dùng chung backend ↔ mock |
| [tools/ev_mock_data/README.md](tools/ev_mock_data/README.md) | Sinh / import / query / dump dữ liệu mock |
| [§2 bên dưới](#2-mock-hãng-xe-tạo-dữ-liệu-cho-gmail-của-bạn) | Tạo chủ xe + xe cho Gmail của bạn |
| [§3 bên dưới](#3-tra-cứu-dữ-liệu-mock-theo-định-danh-find) | Tra cứu theo email / VIN / biển số / CCCD |

### Frontend, test, DevOps

| Tài liệu | Nội dung |
|---|---|
| [tools/api_sync/README.md](tools/api_sync/README.md) | Đồng bộ schema API sang TypeScript, sinh mock JSON |
| [§5 bên dưới](#5-đồng-bộ-schema-api-sang-typescript--sinh-dữ-liệu-mẫu-api_sync) | Tóm tắt lệnh & quy trình `api_sync` |
| [frontend/src/shared/utils/README.md](frontend/src/shared/utils/README.md) | Tiện ích dùng chung frontend |
| [tests/e2e/README.md](tests/e2e/README.md) | Kiểm thử xuyên hệ thống |
| [docs/guide/testing/writing-tests.md](docs/guide/testing/writing-tests.md) | Cấu trúc test |
| [docs/guide/devops/docker-cicd.md](docs/guide/devops/docker-cicd.md) | Docker & CI/CD |
| [tools/repo_sync/README.md](tools/repo_sync/README.md) | Đồng bộ code nhánh `develop` sang repo deploy riêng |

> Thêm hướng dẫn dev mới? Thêm một dòng vào bảng phù hợp ở trên.

---

## 2. Mock hãng xe: tạo dữ liệu cho Gmail của bạn

Onboarding chủ xe chỉ thành công khi **Gmail đăng nhập** và **CCCD** trùng với một chủ xe trên hệ thống hãng.
Dữ liệu mẫu chỉ có email `@example.com`, nên để test bằng Gmail thật, khai báo Gmail trong `.env`
và mock sẽ tự tạo dữ liệu khi khởi động.

### 2.1 Cấu hình (`.env` ở gốc repo)

```dotenv
# Nhiều email cách nhau dấu phẩy; CCCD cố định (12 số) thêm sau dấu ":" nếu muốn
MOCK_DEV_OWNER_EMAILS=you@gmail.com,teammate@gmail.com:079200009999
# Số xe tạo cho mỗi email (mặc định 2)
MOCK_DEV_OWNER_VEHICLES=2
# Ngày tham chiếu cố định để tính ODO / ngày SX / trạng thái bảo hành (trống = 2026-09-01)
MOCK_DEV_REFERENCE_DATE=
```

Với mỗi email **chưa có** trên mock, khi khởi động mock tạo:

| Bảng | Dữ liệu |
|---|---|
| `owner` | 1 chủ xe: `full_name = "Dev <phần trước @>"`, SĐT, CCCD (sinh tự động hoặc lấy sau dấu `:`) |
| `vehicle` | `MOCK_DEV_OWNER_VEHICLES` xe, VIN dạng `DEV<model><trim>…` (17 ký tự), biển `30X-xxxxx` |
| `vehicle_usage` | ODO, % pin theo tuổi xe |
| `warranty` | Một bảo hành cho mỗi policy của model (pin, động cơ, khung gầm, điện tử) |
| `service_history` | Các mốc bảo dưỡng đã qua theo lịch chuẩn của model |

- Dữ liệu **đơn định theo email**: cùng một email luôn ra cùng ID, VIN, biển số, CCCD, SĐT, ODO, bảo hành và lịch sử bảo dưỡng, bất kể ngày chạy, thứ tự email hay các dòng khác đang có trong DB.
  - ID sinh từ hash email: `OWN-DEV-<key>`, `VEH-DEV-<key>-<n>`, `WRT-DEV-<key>-<n>-<policy>`, `SH-DEV-<key>-<n>-<mốc km>`.
  - Mỗi trường có RNG riêng (seed `email | trường | số thứ tự`), nên thêm xe hay đặt CCCD cố định không làm đổi các giá trị khác.
  - Ngày tháng tính theo `MOCK_DEV_REFERENCE_DATE` (mặc định `2026-09-01`), không theo ngày hôm nay.
  - Kết quả chỉ đổi khi dữ liệu nền đổi (model xe, chính sách bảo hành, lịch bảo dưỡng), hoặc khi VIN/biển số/CCCD trùng với dòng có sẵn (khi đó rút lại, vẫn đơn định).
- Email đã có trên mock thì **bỏ qua**. Chạy lại khi restart hay `ev_mock_data reset` đều an toàn.
- Chạy được với cả dump dùng chung (`MOCK_SEED_DUMP`) lẫn seed có sẵn.
- Code: [dev_accounts.py](backend/mock-ev-system/src/mock_ev_system/dev_accounts.py).

### 2.2 Áp dụng

```bash
# Hạ tầng local (mock + redis), backend chạy bằng terminal
docker compose -f docker-compose.infra.yaml up -d --build mock-ev-system

# Hoặc full stack
docker compose -f docker-compose.dev.yaml up -d --build mock-ev-system
```

Mock in ra dữ liệu đã tạo (VIN, biển số, CCCD) trong log:

```bash
docker logs p146_mock_ev 2>&1 | grep MOCK_DEV_OWNER_EMAILS
# MOCK_DEV_OWNER_EMAILS: created owner OWN-DEV-D88CAF58 (you@gmail.com, CCCD=0792...) with vehicles: VEH-DEV-D88CAF58-1 VIN=DEVVF9PLUS0601817 plate=30G-97834 model=MDL-07; ...
```

Chạy mock không qua Docker:

```bash
cd backend
MOCK_DEV_OWNER_EMAILS=you@gmail.com uv run --package mock-ev-system uvicorn mock_ev_system.main:app --reload --port 8100
```

> Chạy không qua Docker (không đặt `MOCK_DB_PATH`) thì mock lưu in-memory: thay đổi bằng tay (import, create) mất khi restart, còn dữ liệu của `MOCK_DEV_OWNER_EMAILS` được tạo lại y hệt mỗi lần khởi động. Qua `docker-compose.infra.yaml` thì DB nằm trên volume `mock_ev_data` và được giữ lại (xem [docs/RUN_LOCAL_BACKEND.md](docs/RUN_LOCAL_BACKEND.md)). Dữ liệu sinh theo kiểu cũ (`OWN-016`, …) còn trong volume cho tới khi `POST /admin/reset`.

---

## 3. Tra cứu dữ liệu mock theo định danh (`find`)

Lệnh `find` của [ev_mock_data](tools/ev_mock_data/README.md) tìm chủ xe / xe theo **một định danh**
rồi lấy mọi dữ liệu liên quan. Cần mock có API `/admin` (build lại container nếu báo
`endpoint not found`).

```bash
alias evm="python tools/ev_mock_data/ev_mock_data.py"   # Windows: gõ đầy đủ lệnh python ...
```

### 3.1 Định danh (chọn đúng một)

| Cờ | Ví dụ | Ghi chú |
|---|---|---|
| `--email` | `--email you@gmail.com` | Không phân biệt hoa thường |
| `--vin` | `--vin DEVVF9PLUS9016207` | |
| `--plate` | `--plate "30A-766.78"` | Bỏ qua khoảng trắng, `-`, `.` |
| `--national-id` / `--cccd` | `--cccd 079202771941` | |
| `--phone` | `--phone +84966826205` | `0xxx` và `+84xxx` đều khớp |
| `--owner-id` | `--owner-id OWN-016` | |
| `--vehicle-id` | `--vehicle-id VEH-029` | |

Tìm theo chủ xe (email, CCCD, SĐT, owner id) → lấy **mọi xe** của chủ đó.
Tìm theo xe (VIN, biển số, vehicle id) → lấy **xe đó** và chủ của nó.

### 3.2 Chọn bảng / cột

| Cờ | Ý nghĩa |
|---|---|
| _(không cờ)_ | `owners` + `vehicles`, đủ cột |
| `-s TABLE` | Cả bảng, đủ cột. Vd `-s warranties` |
| `-s TABLE.COLUMN,...` | Chỉ các cột này. Vd `-s owners.full_name,owners.national_id` |
| `-s` lặp lại | Gộp nhiều bảng: `-s vehicles.vin -s warranties.status` |
| `--all` | Mọi bảng liên quan, đủ cột |
| `--json` | In JSON `{bảng: [dòng]}` (dùng cho script) |
| `--max-width N` | Cắt bớt ô dài khi in bảng (mặc định 40) |

Bảng liên quan: `owners`, `vehicles`, `vehicle_usage`, `warranties`, `warranty_claims`, `service_history`,
`vehicle_models`, `warranty_policies`, `maintenance_schedules`, `maintenance_items`, `service_centers`.
Chấp nhận tên ngắn: `owner`, `vehicle`, `usage`, `warranty`, `claims`, `history`, `model(s)`, `policies`, `schedules`, `items`, `centers`.
Gõ sai bảng / cột, tool in ra danh sách hợp lệ.

### 3.3 Ví dụ

```bash
# Chủ xe + các xe của một Gmail
evm find --email you@gmail.com

# Dữ liệu cần nhập khi onboarding (CCCD, VIN, biển số, model)
evm find --email you@gmail.com -s owners.national_id -s vehicles.vin,vehicles.license_plate,vehicles.model_id

# Bảo hành của một xe theo biển số
evm find --plate 30A-76678 -s vehicles.vin -s warranties.policy_id,warranties.end_date,warranties.status

# Toàn bộ dữ liệu liên quan tới một CCCD, xuất JSON
evm find --cccd 079202771941 --all --json > my-owner.json
```

Thoát với mã `1` khi không tìm thấy chủ xe / xe nào.

---

## 4. Quy trình test onboarding chủ xe bằng Gmail thật

1. Đặt `MOCK_DEV_OWNER_EMAILS=<gmail của bạn>` trong `.env`, rồi build lại mock (§2.2).
2. Lấy dữ liệu để nhập:
   `evm find --email <gmail> -s owners.national_id -s vehicles.vin,vehicles.license_plate,vehicles.model_id`
3. Đăng nhập app chủ xe bằng Gmail đó → nhập hồ sơ với **CCCD** ở bước 2 → nhập **VIN, biển số, model** của một xe.
4. Kết quả mong đợi: xác thực `VERIFIED`, tài khoản chuyển `ACTIVE`.
5. Muốn thử các lỗi: sai biển số → `PLATE_MISMATCH`, sai model → `MODEL_MISMATCH`, sai CCCD → `NATIONAL_ID_MISMATCH`,
   VIN của chủ xe khác → `OWNER_EMAIL_MISMATCH`.

Kiểm tra nhanh phía hãng mà không cần app:

```bash
evm post vehicles/verify-ownership --body '{"vin":"<VIN>","license_plate":"<biển số>","model_id":"<MDL-xx>","email":"<gmail>","national_id":"<CCCD>"}'
```

Test API backend qua Swagger: xem [backend/guide/testing-swagger-onboarding.md](backend/guide/testing-swagger-onboarding.md).

---

## 5. Đồng bộ schema API sang TypeScript & sinh dữ liệu mẫu (`api_sync`)

[tools/api_sync](tools/api_sync/README.md) đọc OpenAPI của backend FastAPI rồi sinh **TypeScript** cho
model request/response, **phát hiện thay đổi** input/output giữa các lần sync, và **sinh dữ liệu mẫu JSON**
(văn bản dài có thể cho LLM viết). Chỉ dùng thư viện chuẩn của Python 3.11+.

### 5.1 Chuẩn bị

1. Copy cấu hình: `cp tools/api_sync/.env.example tools/api_sync/.env` (không commit `.env`; API key LLM chỉ cần cho `--llm`).
2. **Bật backend trước** (tool đọc `http://localhost:8000/openapi.json`):
   `cd backend && uv run uvicorn src.main:app --reload --port 8000`.
   Không muốn bật server: thêm `--source app` hoặc `--source <file openapi.json>`.
3. Kiểm tra: `python tools/api_sync/api_sync.py config` → phải thấy `Backend: UP`.

### 5.2 Các lệnh

| Lệnh | Dùng để | Chi tiết |
|---|---|---|
| `config` | Xem cấu hình, kiểm tra backend chạy chưa | [README §2](tools/api_sync/README.md#2-bắt-đầu-nhanh) |
| `list` | Liệt kê model / endpoint / trường (`--kind`, `--tag`, `--endpoints`, `--fields`) | [README §3.1](tools/api_sync/README.md#31-list--liệt-kê-model-endpoint-trường) |
| `sync` | Sinh TypeScript vào `frontend/src/shared/api/generated`, lưu version | [README §3.2](tools/api_sync/README.md#32-sync--sinh-typescript-và-lưu-version) |
| `check` | Model / endpoint nào đổi input hay output so với lần sync trước (exit `1` nếu có đổi) | [README §3.3](tools/api_sync/README.md#33-check--xem-schema-nào-thay-đổi) |
| `history` | Lịch sử các lần sync | [README §3.4](tools/api_sync/README.md#34-history--lịch-sử-sync) |
| `mock` | Sinh dữ liệu mẫu JSON vào `frontend/src/mocks/generated` (`-n`, `--seed`, `--set`, `--llm`) | [README §3.5](tools/api_sync/README.md#35-mock--sinh-dữ-liệu-mẫu-json) |
| `hints` | Sinh `api_hints.json` mô tả trường văn bản dài cho LLM | [README §3.6](tools/api_sync/README.md#36-hints--sinh-file-api_hintsjson) |

### 5.3 Quy trình thường dùng

```bash
# Sau khi backend đổi schema
python tools/api_sync/api_sync.py check     # xem input/output nào đổi
python tools/api_sync/api_sync.py sync      # sinh lại TypeScript, lưu version mới

# Cần dữ liệu mẫu cho màn hình
python tools/api_sync/api_sync.py list --endpoints --tag onboarding
python tools/api_sync/api_sync.py mock ProfileUpdateRequest -n 20 --seed 42
```

- Commit cả `<out>/.api-sync/` (manifest, lịch sử, snapshot) để team dùng chung mốc so sánh — [README §4](tools/api_sync/README.md#4-version-lịch-sử-snapshot).
- CI: `python tools/api_sync/api_sync.py check --source app` báo lỗi khi TypeScript chưa sync theo backend.
- Dữ liệu `mock` chỉ theo schema, **không** khớp dữ liệu mock hãng; để test xác thực với hãng dùng [§2](#2-mock-hãng-xe-tạo-dữ-liệu-cho-gmail-của-bạn) + [§3](#3-tra-cứu-dữ-liệu-mock-theo-định-danh-find). Giới hạn khác: [README §6](tools/api_sync/README.md#6-giới-hạn).
