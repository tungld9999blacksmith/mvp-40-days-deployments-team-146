# api_sync — Đồng bộ schema API backend sang TypeScript và sinh dữ liệu mẫu

Tool dòng lệnh (Python, chỉ dùng thư viện chuẩn) đọc **schema input/output** của backend
FastAPI rồi:

1. **Sinh TypeScript** (`interface` / `type`) cho các model request/response.
2. **Liệt kê** model, endpoint và các trường của từng model.
3. **Lưu version theo ngày giờ** mỗi lần sync, kèm **lịch sử** và **snapshot** schema.
4. **Kiểm tra thay đổi**: model/endpoint nào đổi input hay output so với lần sync trước, rồi **sync lại**.
5. **Sinh dữ liệu mẫu JSON** với số lượng tuỳ ý; các trường văn bản dài có thể cho **LLM** viết nội dung có nghĩa.

> ⚠️ **Trước khi chạy tool, phải khởi động API backend** (xem [mục 2](#2-bắt-đầu-nhanh)).
> Tool đọc schema từ `http://localhost:8000/openapi.json` của backend đang chạy; backend tắt thì
> mọi lệnh (`list`, `check`, `sync`, `mock`) đều báo lỗi `The backend API is not running`.

```
tools/api_sync/
  .env.example   mẫu cấu hình (copy thành .env)
  .env           cấu hình riêng của tool — KHÔNG commit (đã có trong .gitignore)
  api_hints.json ý nghĩa các trường văn bản dài cho LLM (sinh bằng lệnh `hints`, nên commit)
  api_sync.py    CLI (config, list, check, sync, history, mock, hints)
  settings.py    đọc cấu hình từ tools/api_sync/.env
  openapi.py     đọc OpenAPI, phân loại model input/output, chọn model
  typescript.py  sinh TypeScript
  diff.py        so sánh 2 phiên bản schema
  store.py       version, lịch sử, snapshot
  mockdata.py    sinh dữ liệu mẫu
  hints.py       sinh file hints
  llm.py         gọi LLM (HTTP thuần, không cần SDK)
```

---

## 1. Cách hoạt động

FastAPI tự sinh **OpenAPI** (`/openapi.json`) từ các model Pydantic: kiểu dữ liệu, trường bắt
buộc, enum, `maxLength`, `minimum`, mô tả (`Field(description=...)`)... Tool dùng tài liệu này
làm nguồn duy nhất.

- Model dùng trong **request body** → `input`; dùng trong **response** → `output`
  (có thể là cả hai: `both`). Model con được tính theo (vd. `LocationIn` nằm trong `ProfileUpdateRequest`).
- Response lỗi 422 mặc định của FastAPI (`HTTPValidationError`) không tính là output.

> **Vì sao không dùng parser code Python/TypeScript?** Pydantic → OpenAPI đã là cấu trúc
> chuẩn và đầy đủ, nên không cần phân tích AST Python hay đọc code TS (ts-morph, tree-sitter...).
> Thêm parser chỉ làm tool phức tạp mà không có thêm thông tin. Nếu sau này cần client
> đầy đủ (hàm gọi API), có thể cân nhắc `openapi-typescript` / `orval` bên frontend.

---

## 2. Bắt đầu nhanh

Yêu cầu: Python **3.11+** (đã có sẵn khi dùng `uv` của backend). Không cần cài thêm gì.
Tuỳ chọn: `pip install faker` để tên/địa chỉ tiếng Việt thực tế hơn.

### Bước 1 — Tạo file cấu hình `.env` cho tool

```bash
cp tools/api_sync/.env.example tools/api_sync/.env      # PowerShell: Copy-Item tools/api_sync/.env.example tools/api_sync/.env
```

Mở `tools/api_sync/.env` và điền:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `API_SYNC_SOURCE` | `http://localhost:8000/openapi.json` | Nơi đọc schema (URL backend đang chạy) |
| `API_SYNC_OUT` | `frontend/src/shared/api/generated` | Thư mục xuất **file sync** TypeScript + trạng thái `.api-sync/` |
| `API_SYNC_MOCK_OUT` | `frontend/src/mocks/generated` | Thư mục xuất **dữ liệu mẫu** JSON (lệnh `mock`) |
| `API_SYNC_HINTS_FILE` | `tools/api_sync/api_hints.json` | File hints (lệnh `hints` ghi, `mock` tự đọc) |
| `LLM_PROVIDER` | `openai` | `openai` \| `anthropic` \| `gemini` \| `grok` \| `deepseek` |
| `LLM_API_KEY` | — | API key của provider trên (chỉ cần khi dùng `mock --llm`) |
| `LLM_MODEL` | theo provider | Tên model; để trống sẽ dùng mặc định (xem [mục 3.5](#cấu-hình-llm)) |
| `LLM_BASE_URL` | theo provider | Tuỳ chọn: server tương thích OpenAI (Ollama, LM Studio, proxy nội bộ) |

- Đường dẫn tương đối được tính từ **thư mục gốc repo**, nên chạy tool ở đâu cũng ra cùng kết quả.
  `backend/data/api_samples` và `/backend/data/api_samples` là như nhau. Muốn ra ngoài repo thì
  dùng đường dẫn tuyệt đối đầy đủ (vd. `D:/exports/api`).
- Biến để trống = dùng mặc định.
- **Thứ tự ưu tiên:** tham số dòng lệnh (`--out`, `--mock-out`, `--source`, `--llm-provider`,
  `--llm-model`) > biến môi trường của shell > `tools/api_sync/.env` > mặc định.
- Tool **không đọc** `backend/.env`; API key của tool tách riêng khỏi backend.
- `.env` đã được `.gitignore` bỏ qua — **không commit API key**. Chỉ commit `.env.example`.

### Bước 2 — Khởi động API backend (bắt buộc)

Tool đọc schema input/output từ OpenAPI mà backend FastAPI sinh ra, nên **backend phải đang chạy**
trước khi chạy tool. Mở một terminal riêng:

```bash
cd backend
uv run uvicorn src.main:app --reload --port 8000
```

Chờ đến khi thấy `Application startup complete`, rồi để terminal đó chạy.
Backend chạy ở cổng khác thì sửa `API_SYNC_SOURCE` trong `.env` cho khớp.

### Bước 3 — Kiểm tra cấu hình và kết nối

```bash
python tools/api_sync/api_sync.py config
```

```
Env file:      .../tools/api_sync/.env (found)
Source:        http://localhost:8000/openapi.json
Sync out:      .../frontend/src/shared/api/generated
Mock out:      .../frontend/src/mocks/generated
Hints file:    .../tools/api_sync/api_hints.json (found)
LLM:           openai / gpt-4o-mini @ https://api.openai.com/v1
LLM API key:   sk-p...x9Qa

Backend:       UP - 58 model(s), 20 endpoint(s)
```

API key chỉ hiện 4 ký tự đầu/cuối. Nếu thấy `Backend: DOWN` → quay lại bước 2.
Lệnh trả exit code `1` khi backend không chạy.

### Bước 4 — Chạy các lệnh

Chạy từ thư mục gốc repo:

```bash
python tools/api_sync/api_sync.py <lệnh> [tuỳ chọn]
python tools/api_sync/api_sync.py <lệnh> --help     # xem mọi tuỳ chọn của lệnh
```

**Không muốn bật server?** Dùng `--source`:

| `--source` | Khi nào dùng |
|---|---|
| `http://localhost:8000/openapi.json` (mặc định, lấy từ `.env`) | Backend đang chạy — **cách chuẩn** |
| `app` | Tool import `src.main:app` bằng `uv run` trong `backend/` (cần `uv` và cài đủ dependency backend) |
| đường dẫn file `.json` | Dùng file OpenAPI có sẵn (vd. một snapshot cũ) |

---

## 3. Các lệnh

Mọi lệnh đều nhận `--source` và `--out` (ghi đè giá trị trong `.env` cho lần chạy đó):

| Tuỳ chọn | Mặc định | Ý nghĩa |
|---|---|---|
| `--source` | `API_SYNC_SOURCE` | Nguồn OpenAPI (xem [mục 2](#2-bắt-đầu-nhanh)) |
| `--out` | `API_SYNC_OUT` | Thư mục ghi file TypeScript **và** trạng thái sync |

`config` — in cấu hình đang dùng và kiểm tra backend có chạy không (xem bước 3 ở trên).

### 3.1 `list` — liệt kê model, endpoint, trường

```bash
# Tất cả model: tên TS, loại (input/output/both/unused), số trường, số endpoint, đã sync chưa
python tools/api_sync/api_sync.py list

# Chỉ model input / output
python tools/api_sync/api_sync.py list --kind input
python tools/api_sync/api_sync.py list --kind output

# Chỉ model dùng bởi endpoint có tag
python tools/api_sync/api_sync.py list --tag onboarding workshop-owner-onboarding

# Endpoint kèm model input / output
python tools/api_sync/api_sync.py list --endpoints
python tools/api_sync/api_sync.py list --endpoints --tag onboarding

# Các trường của 1 model (kiểu TS, bắt buộc hay không, mô tả, endpoint dùng nó)
python tools/api_sync/api_sync.py list --fields ProfileUpdateRequest
```

Ví dụ `list --endpoints`:

```
PUT /api/v1/onboarding/profile        in: ProfileUpdateRequest        out: VehicleOwnerOnboardingProfileUpdateEnvelope
POST /api/v1/onboarding/vehicle-verification  in: VehicleVerificationRequest  out: VehicleOwnerOnboardingVerificationEnvelope
```

> **Tên model trùng:** khi 2 module có class trùng tên (vd. `SignInEnvelope`), FastAPI đặt tên
> theo đường dẫn module; tool rút gọn thành `<Module><Class>`, vd.
> `VehicleOwnerOnboardingSignInEnvelope` và `WorkshopOwnerOnboardingSignInEnvelope`.

### 3.2 `sync` — sinh TypeScript và lưu version

```bash
# Lần đầu: tất cả model
python tools/api_sync/api_sync.py sync

# Chọn model cụ thể (tên hoặc glob); model phụ thuộc được thêm tự động để file luôn compile
python tools/api_sync/api_sync.py sync --models ProfileUpdateRequest VehicleVerificationRequest
python tools/api_sync/api_sync.py sync --models "*Request" "*Envelope"

# Theo tag endpoint và/hoặc chỉ input/output
python tools/api_sync/api_sync.py sync --tag workshop-owner-onboarding --kind input

# Dùng `type` thay vì `interface`, đổi tên file
python tools/api_sync/api_sync.py sync --style type --file workshop-types.ts

# Quay lại "tất cả model"
python tools/api_sync/api_sync.py sync --all

# Xem trước, không ghi gì
python tools/api_sync/api_sync.py sync --dry-run          # chỉ in số model
python tools/api_sync/api_sync.py sync --dry-run --print  # in cả nội dung TypeScript
```

| Tuỳ chọn | Ý nghĩa |
|---|---|
| `--models A B` / `--models "A,B"` | Tên model hoặc glob (`*Request`), không phân biệt hoa thường |
| `--tag T1 T2` | Chỉ model dùng bởi endpoint có tag |
| `--kind input\|output\|all` | Chỉ model input hoặc output |
| `--all` | Bỏ lựa chọn đã lưu, sync tất cả |
| `--style interface\|type` | Kiểu khai báo (mặc định `interface`) |
| `--file NAME` | Tên file trong `--out` (mặc định `api-models.ts`) |
| `--force` | Sinh lại dù không có thay đổi |
| `--dry-run`, `--print` | Không ghi file / in nội dung |

**Lựa chọn được nhớ:** các tuỳ chọn trên được lưu lại. Lần sau chỉ cần chạy `sync`, tool dùng
lại đúng lựa chọn cũ. Nếu schema không đổi, tool báo `Up to date` và không tạo version mới.

File sinh ra (rút gọn):

```ts
/* eslint-disable */
// AUTO-GENERATED by tools/api_sync — do not edit by hand; run `api_sync.py sync`.
// Sync version: 2026-09-27_200305
// Synced at:    2026-09-27T20:03:05+07:00
// Source:       http://localhost:8000/openapi.json

/** Used by: POST /api/v1/workshop-owner/onboarding/workshop-verification (input) */
export interface WorkshopVerificationRequest {
  address: string;
  latitude?: number | null;
  hotline: string;
  /** @default 0 */
  emergencySlotsReserved?: number;
  operatingHours: OperatingHourIn[];
  oemDataSharingConsent: WorkshopOwnerOnboardingConsentIn;
}

export type VehicleStatus = "active" | "in_service" | "deactivated";
```

Quy tắc chuyển kiểu:

| OpenAPI / Pydantic | TypeScript |
|---|---|
| `str`, `date`, `datetime`, `UUID` | `string` (JSDoc ghi `@format`) |
| `int`, `float` | `number` |
| `X \| None` | `X \| null` |
| trường không bắt buộc (có default) | `field?:` |
| `Enum`, `Literal[...]` | union chuỗi: `"a" \| "b"` |
| `list[X]` | `X[]` |
| `dict[str, X]` | `Record<string, X>` |
| `description` của Field | JSDoc `/** ... */` |

### 3.3 `check` — xem schema nào thay đổi

So sánh schema hiện tại với lần sync gần nhất (hoặc một version cụ thể). Chỉ tính thay đổi cấu
trúc (kiểu, bắt buộc, enum, thêm/xoá trường, tham số); sửa mô tả không tính.

```bash
python tools/api_sync/api_sync.py check
python tools/api_sync/api_sync.py check --against 2026-09-27_200245
```

Ví dụ kết quả:

```
Models:
  [removed] VehicleModelOut *
  [changed] ProfileUpdateRequest *
      ~ nationalId: optional (was required)
      + nickname?: string
  [changed] WarrantyOut *
      ~ kmLimit: number | null  ->  string
Endpoints:
  [changed] PUT /api/v1/onboarding/profile
      input schema changed via ProfileUpdateRequest
  [changed] GET /api/v1/onboarding
      output schema changed via WarrantyOut
(* = model included in the last synced TypeScript file)
```

- `+` trường mới, `-` trường bị xoá, `~` đổi kiểu hoặc đổi bắt buộc.
- Mỗi endpoint cho biết thay đổi nằm ở **input** hay **output**, và do model nào.
- Exit code: `0` = không đổi, `1` = có thay đổi → dùng được trong CI / pre-commit.

Sau khi xem, chạy `sync` để sinh lại; phần thay đổi được in ra và ghi vào lịch sử.

### 3.4 `history` — lịch sử sync

```bash
python tools/api_sync/api_sync.py history
python tools/api_sync/api_sync.py history --limit 5
```

```
2026-09-27_200248  2026-09-27T20:02:48+07:00   57 models  modelsRemoved=1, modelsChanged=3, endpointsChanged=4
    removed models:  VehicleModelOut
    changed models:  ProfileUpdateRequest, VehicleModelsData, WarrantyOut
    endpoints:       GET /api/v1/onboarding, PUT /api/v1/onboarding/profile, ...
2026-09-27_200245  2026-09-27T20:02:45+07:00   58 models  initial sync
```

### 3.5 `mock` — sinh dữ liệu mẫu JSON

```bash
# 20 bản ghi cho mỗi model -> <API_SYNC_MOCK_OUT>/<Model>.json
python tools/api_sync/api_sync.py mock ProfileUpdateRequest WarrantyOut -n 20

# In ra màn hình, cố định seed để lần nào cũng ra cùng dữ liệu
python tools/api_sync/api_sync.py mock VehicleVerificationRequest -n 3 --seed 42 --stdout

# Trường văn bản dài do LLM viết, tiếng Việt
python tools/api_sync/api_sync.py mock WarrantyOut -n 10 --llm --lang vi --hints tools/api_sync/hints.json
```

| Tuỳ chọn | Ý nghĩa |
|---|---|
| `-n, --count` | Số bản ghi mỗi model (mặc định 5) |
| `--mock-out DIR` | Thư mục ghi (mặc định `API_SYNC_MOCK_OUT` trong `.env`) |
| `--stdout` | In JSON thay vì ghi file |
| `--seed N` | Dữ liệu lặp lại được |
| `--set FIELD=VALUE` | Ép giá trị cho trường (lặp lại được, xem bên dưới) |
| `--locale` | Locale cho Faker nếu đã cài (mặc định `vi_VN`) |
| `--llm` | Dùng LLM viết các trường văn bản dài |
| `--llm-provider`, `--llm-model` | Đổi provider / model cho lần chạy này (mặc định `LLM_PROVIDER` / `LLM_MODEL` trong `.env`) |
| `--llm-fields f1 Model.f2` | Chỉ định thêm trường cần LLM viết |
| `--no-auto-long-text` | Tắt tự nhận diện, chỉ dùng `--llm-fields` |
| `--hints FILE` | File JSON mô tả ý nghĩa model/trường cho LLM (mặc định `API_SYNC_HINTS_FILE` nếu file đã có) |
| `--lang vi\|en\|...` | Ngôn ngữ LLM viết (mặc định `vi`) |

**Cách chọn giá trị cho mỗi trường** (theo thứ tự ưu tiên):

1. `--set` của người dùng.
2. `const`, `enum`, `examples` trong schema; `default` (với chuỗi).
3. `format`: `date`, `date-time`, `email`, `uuid`, `uri`...
4. Theo tên trường: email, số điện thoại VN (`09xxxxxxxx`), CCCD 12 số, VIN 17 ký tự, biển số
   (`51A-12345`), họ tên, địa chỉ, phường/quận/tỉnh, ngày sinh (18–65 tuổi), vĩ độ/kinh độ trong
   Việt Nam, năm, giờ `HH:mm`, mã/ID...
5. Theo kiểu, luôn nằm trong `minLength/maxLength`, `minimum/maximum`, `pattern` số.

**`--set` cho quy tắc mà schema không thể hiện** (validate ở tầng service): giá trị là JSON nếu
parse được (số, `true`, mảng, object), ngược lại là chuỗi. Khoá có thể là `field` hoặc `Model.field`.

```bash
python tools/api_sync/api_sync.py mock WorkshopVerificationRequest -n 10 \
  --set WorkshopOwnerOnboardingConsentIn.policyVersion=WS-2026-09 \
  --set granted=true \
  --set 'operatingHours=[{"dayOfWeek":1,"isClosed":false,"openTime":"08:00","closeTime":"17:30"}, ...]'
```

#### Văn bản dài bằng LLM

Trường được coi là **văn bản dài** khi là chuỗi tự do (không enum/format) và:
- `maxLength >= 200`, **hoặc**
- không có `maxLength` và tên chứa: `description, content, note, comment, message, summary,
  terms, detail, bio, body, instruction, feedback, review, remark`;
- trừ các trường đã có quy tắc riêng (địa chỉ, tên, ID, email...);
- cộng thêm các trường khai báo trong `--llm-fields`.

Để LLM viết **có nghĩa**, mỗi trường được gửi kèm:

| Thông tin | Lấy từ |
|---|---|
| Ý nghĩa trường (`meaning`) | file `--hints` → `description` của Field → tên trường |
| Mục đích model (`about`) | file `--hints` → `description` của model |
| Endpoint dùng model (`usedBy`) | method, path, summary của endpoint |
| Dữ liệu cùng bản ghi (`record`) | các trường khác của cùng object, để nội dung khớp (vd. `component: battery` → điều khoản về pin) |

Gửi theo lô 25 trường / lần gọi. Nếu LLM lỗi, tool **không dừng**: giữ câu placeholder và in cảnh báo.

**File hints**, khoá là `Model`, `Model.field` hoặc `field`. Sinh tự động bằng lệnh
[`hints`](#36-hints--sinh-file-api_hintsjson) rồi sửa lại cho đúng nghiệp vụ:

```json
{
  "WarrantyOut": "Manufacturer warranty contract for one EV component",
  "WarrantyOut.termsDescription": "Plain-language warranty terms: what is covered, exclusions, how to claim",
  "message": "Short message shown to the vehicle owner after verification"
}
```

> Cách tốt nhất về lâu dài là viết `Field(description="...")` ngay trong schema Pydantic của
> backend: mô tả sẽ vào OpenAPI, hiện trong Swagger, JSDoc của TypeScript và prompt của LLM.

#### Cấu hình LLM

Đặt trong `tools/api_sync/.env`: `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`.

| `LLM_PROVIDER` | Model mặc định (khi `LLM_MODEL` trống) | Base URL mặc định |
|---|---|---|
| `openai` (mặc định) | `gpt-4o-mini` | `https://api.openai.com/v1` |
| `anthropic` | `claude-haiku-4-5-20251001` | `https://api.anthropic.com/v1` |
| `gemini` | `gemini-2.5-flash` | `https://generativelanguage.googleapis.com/v1beta/openai` |
| `grok` | `grok-4` | `https://api.x.ai/v1` |
| `deepseek` | `deepseek-chat` | `https://api.deepseek.com` |

- `LLM_API_KEY` phải là key của đúng provider đã chọn.
- `LLM_BASE_URL` cho phép trỏ tới bất kỳ server tương thích OpenAI (Ollama, LM Studio, proxy nội bộ).
- Khi đổi provider bằng `--llm-provider` khác với `.env`, tool bỏ qua `LLM_MODEL`/`LLM_BASE_URL`
  (vốn dành cho provider kia) và dùng mặc định của provider mới; `LLM_API_KEY` vẫn dùng chung.
- Thiếu `LLM_API_KEY` thì `mock --llm` dừng với lỗi `LLM_API_KEY is not set`; `mock` không có
  `--llm` vẫn chạy bình thường.

### 3.6 `hints` — sinh file `api_hints.json`

Tạo sẵn file hints cho `mock --llm`: mỗi model có trường văn bản dài được một khoá `Model`
(mục đích model) và mỗi trường một khoá **`Model.field`** (ý nghĩa trường). Trường `message`
cũng được sinh theo dạng này (vd. `MessageResponse.message`) giống `WarrantyOut.termsDescription`,
nên mỗi model có câu mô tả riêng thay vì dùng chung một khoá `message`.

```bash
# Tất cả model có trường văn bản dài -> API_SYNC_HINTS_FILE
python tools/api_sync/api_sync.py hints

# Chỉ vài model; thêm trường không tự nhận diện
python tools/api_sync/api_sync.py hints WarrantyOut --llm-fields WarrantyOut.component

# Cho LLM viết câu mô tả (dùng cấu hình LLM trong .env), bằng tiếng Việt
python tools/api_sync/api_sync.py hints --llm --lang vi

# Xem trước / viết lại từ đầu
python tools/api_sync/api_sync.py hints --stdout
python tools/api_sync/api_sync.py hints --force
```

Kết quả (rút gọn):

```json
{
  "MessageResponse": "Generic message response for mutation operations.",
  "MessageResponse.message": "Short message shown to the user after 'Delete a vehicle'; one or two sentences explaining the result and the next step",
  "WarrantyOut": "Response data: warranty, used by GET /api/v1/onboarding (...)",
  "WarrantyOut.termsDescription": "Plain-language warranty terms: what is covered, conditions, exclusions and how to claim"
}
```

Giá trị ban đầu lấy theo thứ tự:

1. `description` của Field / model trong schema Pydantic (nếu có).
2. Bản nháp của LLM khi dùng `--llm`.
3. Câu mẫu theo tên trường: `terms`, `message`, `summary`, `description`, `note/comment/remark`,
   `feedback/review`, `instruction`, `detail`, `content/body`, `bio`; kèm tên model và endpoint dùng nó.

- **Không ghi đè phần đã sửa:** chạy lại `hints` chỉ **thêm** khoá mới (vd. sau khi backend có
  model mới); giá trị đã có giữ nguyên. `--force` mới viết lại toàn bộ bản nháp.
- `mock` tự đọc file này khi đã tồn tại, không cần `--hints`.
- Trường được chọn theo **cùng quy tắc** với `mock` (xem "Văn bản dài bằng LLM"), nên
  `--llm-fields` / `--no-auto-long-text` có ý nghĩa như nhau ở hai lệnh.

| Tuỳ chọn | Ý nghĩa |
|---|---|
| `MODEL ...` | Chỉ các model này (mặc định: mọi model có trường văn bản dài) |
| `--hints-file FILE` | File ghi (mặc định `API_SYNC_HINTS_FILE`) |
| `--llm`, `--llm-provider`, `--llm-model` | Cho LLM viết bản nháp |
| `--lang` | Ngôn ngữ của câu hints (mặc định `en`) |
| `--llm-fields`, `--no-auto-long-text` | Như lệnh `mock` |
| `--force` | Thay giá trị cũ bằng bản nháp mới |
| `--stdout` | In ra màn hình, không ghi file |

---

## 4. Version, lịch sử, snapshot

Trạng thái lưu cạnh file TypeScript, trong `<out>/.api-sync/` — **nên commit** để cả team
dùng chung mốc so sánh:

```
<out>/
  api-models.ts
  .api-sync/
    manifest.json               lần sync gần nhất: version, ngày giờ, nguồn, lựa chọn, danh sách model
    history.jsonl               mỗi dòng một lần sync (chỉ ghi thêm)
    snapshots/<version>.json    toàn bộ OpenAPI tại lần sync đó
```

- **Version** = ngày giờ sync, dạng `YYYY-MM-DD_HHMMSS` (vd. `2026-09-27_200305`), cũng ghi ở đầu file TS.
- **Khôi phục phiên bản cũ**: dùng snapshot làm nguồn:
  ```bash
  python tools/api_sync/api_sync.py sync --force \
    --source frontend/src/shared/api/generated/.api-sync/snapshots/2026-09-27_200245.json
  ```

---

## 5. Quy trình gợi ý

```bash
# 0. Terminal riêng: bật backend và để nó chạy
cd backend && uv run uvicorn src.main:app --reload --port 8000

# 1. Kiểm tra cấu hình + backend
python tools/api_sync/api_sync.py config

# Sau khi backend đổi schema (backend --reload tự nạp code mới)
python tools/api_sync/api_sync.py check          # xem input/output nào đổi
python tools/api_sync/api_sync.py sync           # sinh lại TS, lưu version mới
python tools/api_sync/api_sync.py history --limit 3   # (tuỳ chọn) xem lại

# Cần dữ liệu test cho màn hình / API
python tools/api_sync/api_sync.py hints                  # lần đầu hoặc khi có model mới; sửa lại file cho đúng nghiệp vụ
python tools/api_sync/api_sync.py list --endpoints --tag onboarding
python tools/api_sync/api_sync.py mock VehicleOwnerOnboardingOnboardingEnvelope -n 30 --llm
```

CI: `python tools/api_sync/api_sync.py check --source app` trả exit `1` nếu TypeScript chưa sync theo backend.

---

## 6. Giới hạn

- Dữ liệu mẫu chỉ tuân theo những gì **schema mô tả**. Quy tắc ở tầng service (vd. `policyVersion`
  phải đúng giá trị, `operatingHours` đủ 7 ngày, `emergencySlotsReserved <= totalTechnicians`,
  `endDate > startDate`) không có trong OpenAPI → dùng `--set`, hoặc khai báo ràng buộc trong
  Pydantic (vd. `Field(min_length=7, max_length=7)` cho list) để tool tự hiểu.
- Dữ liệu dùng để test/hiển thị, **không** khớp với dữ liệu seed của mock-ev-system; để xác minh
  thành công với mock hãng, dùng các example trong Swagger.
- TypeScript chỉ gồm type/interface, không sinh hàm gọi API.
