# Hướng dẫn test module qua Swagger + mock EV system

Tài liệu này hướng dẫn **test thủ công** các module qua Swagger UI: cách lấy
token đăng nhập (Firebase Auth Emulator), cách chuẩn bị / lấy dữ liệu từ
`mock-ev-system`, và luồng test **onboarding** đầu-cuối. Các route khác
(user-vehicles, webhook OEM, vehicles, oauth) được mô tả tương tự ở cuối.

> Bổ trợ cho:
> - [swagger.md](swagger.md) — tổng quan Swagger UI, tags, error envelope.
> - [testing.md](testing.md) — viết & chạy **unit test** (pytest). Khác với tài
>   liệu này (test **thủ công** qua HTTP thật).
> - [../../docs/RUN_LOCAL_BACKEND.md](../../docs/RUN_LOCAL_BACKEND.md) — dựng stack bằng Docker.

---

## 0. Bức tranh tổng thể — ai giữ dữ liệu gì

Hiểu điểm này trước thì mọi bước sau sẽ rõ:

| Thành phần | Cổng | Giữ dữ liệu gì | Test qua |
|-----------|------|----------------|----------|
| **backend** (EV Care) | 8000 | Tài khoản người dùng, hồ sơ, trạng thái onboarding, xe đã liên kết | http://localhost:8000/docs |
| **mock-ev-system** | 8100 | "Sự thật" phía hãng: VIN, biển số, chủ xe, bảo hành, ODO, lịch sử BD | http://localhost:8100/docs |
| **Firebase Auth Emulator** | 9099 | Cấp Firebase ID token giả để đăng nhập | REST / script (mục 2) |
| Redis | 6379 | Cache/lock/queue (bắt buộc sống khi backend start) | — |

**Hai quy tắc cốt lõi của onboarding:**

1. **Hãng là nguồn sự thật.** Backend không tự nghĩ ra thông tin xe — nó gọi
   `POST /vehicles/verify-ownership` của mock để xác minh. Muốn verify **thành
   công**, dữ liệu bạn gửi phải khớp seed của mock (mục 3).
2. **Xác minh khớp 5 trường:** `VIN` + `biển số` + `modelId` + **email tài
   khoản đăng nhập** + **CCCD trong hồ sơ**. Email lấy từ token Firebase, CCCD
   lấy từ bước cập nhật hồ sơ. Sai bất kỳ trường nào → verify fail với lý do
   tương ứng (mục 5.6).

---

## 1. Khởi động môi trường

Cần **3 tiến trình**: mock-ev-system, Redis, backend. (Emulator ở mục 2.)

```bash
# 1) Redis (nếu chưa có)
docker run -d -p 6379:6379 redis:7-alpine

# 2) mock-ev-system (từ backend/)
cd backend
uv run --package mock-ev-system uvicorn mock_ev_system.main:app --reload --port 8100

# 3) backend (terminal khác, từ backend/)
cd backend
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Kiểm tra nhanh: http://localhost:8000/health và http://localhost:8100/health đều trả `{"status":"ok"}`.

> Backend đọc `OEM_API_BASE_URL` (mặc định `http://localhost:8100`) để gọi mock —
> không import trực tiếp. Nếu chạy bằng Docker stack thì đổi thành tên DNS nội bộ.

---

## 2. Lấy token đăng nhập bằng Firebase Auth Emulator

Mọi route onboarding/user-vehicles đều yêu cầu **Firebase ID token thật** (backend
gọi `firebase_admin.auth.verify_id_token`). Không có chế độ bỏ qua auth. Ở local
ta dùng **Firebase Auth Emulator** để cấp token giả mà backend vẫn chấp nhận.

### 2.1. Yêu cầu

- **Java 11+** (emulator cần JVM) và **Node.js** để cài Firebase CLI:
  ```bash
  npm install -g firebase-tools
  ```
- File service-account JSON hiện có (biến `FIREBASE_CREDENTIAL` trong
  `.env` gốc) **vẫn phải tồn tại** — `src/infrastructure/firebase/oauth/setup.py`
  đọc nó lúc import. Khi bật emulator, chữ ký/khoá riêng **không** được dùng; chỉ
  trường `project_id` trong JSON được đọc để so `aud` của token.

### 2.2. Bật emulator

Dùng đúng **project id** bằng với `project_id` trong file service-account JSON
(mở JSON ra xem, ví dụ `p146-ev-care`):

```bash
firebase emulators:start --only auth --project <project_id-trong-json>
```

Emulator lắng nghe ở `127.0.0.1:9099` (UI ở http://127.0.0.1:4000).

### 2.3. Trỏ backend vào emulator

Thêm dòng sau vào `.env` ở gốc repo rồi **khởi động lại backend**:

```
FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099
```

Từ giờ `verify_id_token` sẽ xác thực token do emulator phát mà không kiểm chữ ký.

### 2.4. Mint một ID token (provider `google.com`)

`sign_in` chỉ chấp nhận provider `google.com` và email đã verify. Emulator cho
phép "đăng nhập Google giả" qua REST `accounts:signInWithIdp` với một `id_token`
IdP dạng JSON mà **ta tự điền email**. Đặt `email` = email một owner trong seed
(mục 3) để sau này verify xe thành công — ví dụ `an.nguyen@example.com`.

**Bash / Git Bash:**

```bash
# key có thể là chuỗi bất kỳ khi chạy emulator
curl -s -X POST \
  "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=fake-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "postBody": "id_token={\"sub\":\"test-uid-own001\",\"email\":\"an.nguyen@example.com\",\"email_verified\":true,\"name\":\"Nguyen Van An\"}&providerId=google.com",
    "requestUri": "http://localhost",
    "returnIdpCredential": true,
    "returnSecureToken": true
  }' | python -c "import sys,json;print(json.load(sys.stdin)['idToken'])"
```

**PowerShell:**

```powershell
$body = @{
  postBody = 'id_token={"sub":"test-uid-own001","email":"an.nguyen@example.com","email_verified":true,"name":"Nguyen Van An"}&providerId=google.com'
  requestUri = 'http://localhost'
  returnIdpCredential = $true
  returnSecureToken = $true
} | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -ContentType 'application/json' `
  -Uri 'http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=fake-api-key' `
  -Body $body
$r.idToken
```

Chuỗi in ra chính là **ID token**. Token của emulator sống ~1 giờ; hết hạn thì
mint lại (giữ nguyên `sub` để vẫn là cùng một user).

> Muốn đóng vai user khác: đổi `email` + `sub`. Mỗi `sub` là một `firebase_uid`
> khác → backend tạo tài khoản mới.

### 2.5. Authorize trong Swagger

1. Mở http://localhost:8000/docs → bấm **Authorize** (ổ khoá góc phải).
2. Dán token vào (chỉ dán chuỗi token, Swagger tự thêm `Bearer`).
3. Mọi request "Try it out" từ giờ tự đính header `Authorization: Bearer <token>`.

---

## 3. Dữ liệu mock — chuẩn bị & tra cứu

`mock-ev-system` seed **cố định, lặp lại được** (restart là fresh). Dùng đúng các
giá trị này khi test happy-path.

### 3.1. Bảng owner + xe (khớp `mock-ev-system/src/mock_ev_system/seed.py`)

| Owner | Email | CCCD | Xe (VIN / biển số / modelId) |
|-------|-------|------|------------------------------|
| OWN-001 | an.nguyen@example.com | 079200001001 | `VF5PLUS2024000001` / `30A-12345` / **MDL-01** (VF5 Plus)<br>`VF8ECO20230000001` / `30A-67890` / **MDL-05** (VF8 Eco) |
| OWN-002 | binh.tran@example.com | 079200001002 | `VF6ECO20240000001` / `51A-11111` / **MDL-02** |
| OWN-003 | cuong.le@example.com | 079200001003 | `VF7ECO20230000001` / `43A-22222` / MDL-04<br>`VF9PLUS2023000001` / `43A-33333` / MDL-07 |
| OWN-004 | dung.pham@example.com | 079200001004 | `VF6PLUS2024000001` / `29A-44444` / MDL-03 |
| OWN-005 | em.hoang@example.com | 079200001005 | `VF8PLUS2023000001` / `51A-55555` / MDL-06 |

### 3.2. Lấy dữ liệu mock qua Swagger của mock (không cần token)

Mở http://localhost:8100/docs và dùng:

| Việc | Endpoint |
|------|----------|
| Danh sách model (để lấy `modelId` hợp lệ) | `GET /models` |
| Tra xe theo VIN | `GET /vehicles/lookup/by-vin?vin=VF5PLUS2024000001` |
| Tra xe theo biển số | `GET /vehicles/lookup/by-plate?plate=30A-12345` |
| Chi tiết chủ xe (email/CCCD/danh sách xe) | `GET /owners/OWN-001` |
| Bảo hành của xe | `GET /vehicles/VEH-001/warranties` |
| Snapshot ODO / SOH | `GET /vehicles/VEH-001/usage` |
| Lịch sử bảo dưỡng | `GET /vehicles/VEH-001/service-history` |

Hoặc thử trực tiếp endpoint xác minh mà backend sẽ gọi:

```bash
curl -s -X POST http://localhost:8100/vehicles/verify-ownership \
  -H "Content-Type: application/json" \
  -d '{"vin":"VF5PLUS2024000001","license_plate":"30A-12345","model_id":"MDL-01","email":"an.nguyen@example.com","national_id":"079200001001"}'
# → {"verified": true, "vehicle": {...}, "warranties": [...]}
```

### 3.3. Hai cách để happy-path verify thành công

Backend so khớp **email của token** với email owner trong mock.

- **Cách A (khuyên dùng — không sửa code):** ở mục 2.4 đặt `email` của token = một
  email owner có sẵn (vd `an.nguyen@example.com`). Xong, dùng đúng VIN/biển
  số/model/CCCD của owner đó.
- **Cách B (dùng Gmail thật của bạn):** sửa seed để owner mang email của bạn, rồi
  **restart mock**. Trong `mock-ev-system/src/mock_ev_system/seed.py`, hàm
  `_seed_owners`, đổi email của `OWN-001`:

  ```python
  Owner(
      owner_id="OWN-001", full_name="Nguyễn Văn An",
      phone="0901000001", email="ban@gmail.com",   # ← email test của bạn
      national_id="079200001001",
  ),
  ```

  (CCCD giữ nguyên `079200001001` để nhập ở bước hồ sơ.) Token ở mục 2.4 khi đó
  đặt `email` = `ban@gmail.com`.

---

## 4. (Tùy chọn) Trường hợp không có emulator — chỉ test các case fail

Nếu chưa cài được emulator, bạn vẫn test được **phần mock** và **các nhánh lỗi
định dạng/validation** không cần đăng nhập:

- Toàn bộ `mock-ev-system` (mục 3.2) — không cần token.
- Endpoint `vehicles` (module examples) ở backend — không cần token (mục 6.3).

Còn các route onboarding/user-vehicles bắt buộc token → cần emulator (mục 2) hoặc
một Firebase ID token Google thật dán vào **Authorize**.

---

## 5. Test onboarding đầu-cuối (5 bước)

Đảm bảo đã **Authorize** bằng token có email khớp owner (mục 2–3). Các endpoint
nằm dưới tag **onboarding**. Response bọc trong `{"data": ...}`; lỗi domain bọc
trong `{"error": {...}}` (xem [swagger.md](swagger.md) mục 6).

### 5.1. `POST /api/v1/oauth/sign-in` — đăng nhập & tạo tài khoản

Không có body (thông tin lấy từ token). Bấm **Execute**.

- Lần đầu với `sub`/email mới → **201**, `data.isNewUser = true`,
  `data.onboarding.status = "ONBOARDING_IN_PROGRESS"`, `nextStep = "PROFILE"`.
- Gọi lại → **200**, `isNewUser = false`.

### 5.2. `GET /api/v1/onboarding` — xem trạng thái hiện tại

Trả trạng thái + dữ liệu đã lưu. Lúc này `profile` gần như rỗng,
`remainingAttempts = 5`, `vehicle = null`.

### 5.3. `PUT /api/v1/onboarding/profile` — lưu hồ sơ + vị trí + consent

Trong "Try it out", chọn ví dụ **"Valid: manual address (seed owner OWN-001)"**
(dropdown Examples), hoặc gửi:

```json
{
  "fullName": "Nguyen Van An",
  "phoneNumber": "0901000001",
  "nationalId": "079200001001",
  "dateOfBirth": "1990-05-20",
  "location": {
    "addressLine": "12 Ly Thai To",
    "ward": "Hang Trong",
    "district": "Hoan Kiem",
    "province": "Ha Noi",
    "source": "MANUAL"
  },
  "personalDataConsent": { "granted": true, "policyVersion": "2026-09" }
}
```

- **200**, `nextStep` chuyển sang bước xác minh xe, `profile.nationalIdMasked` bị che.
- **Bắt buộc**: `nationalId` khớp CCCD owner (`079200001001`), consent `granted=true`,
  `policyVersion="2026-09"` (khớp `CONSENT_POLICY_VERSION`).
- Ví dụ lỗi có sẵn: `invalid_phone` (400 `INVALID_REQUEST`), `consent_declined`
  (409/400 `CONSENT_REQUIRED`).

### 5.4. `GET /api/v1/onboarding/vehicle-models` — danh sách model

Backend proxy `GET /models` của mock. Trả danh sách để lấy `modelId` đúng
(vd `MDL-01`). Nếu mock chết → **503 `OEM_UNAVAILABLE`**.

### 5.5. `POST /api/v1/onboarding/vehicle-verification` — xác minh sở hữu xe

Endpoint này cần **header `Idempotency-Key`** (ô riêng trong "Try it out"). Chọn
ví dụ **"Valid: VF5 Plus of OWN-001 (VEH-001)"** hoặc gửi:

```json
{
  "vin": "VF5PLUS2024000001",
  "licensePlate": "30A-12345",
  "modelId": "MDL-01",
  "manufactureYear": 2024,
  "oemDataSharingConsent": { "granted": true, "policyVersion": "2026-09" }
}
```

Header: `Idempotency-Key: 3f0c9a52-6d1e-4b8a-9c7f-2e5b1d0a4c11` (đổi giá trị cho mỗi
lần gửi **mới**).

- **200** + `verification.status = "SUCCESS"`, `vehicle.verificationStatus = "VERIFIED"`,
  kèm `spec` (pin, motor…) và danh sách `warranties`. `onboarding.status = "ACTIVE"`
  → onboarding hoàn tất.
- **Idempotency**: gửi lại **cùng key + cùng body** → phát lại kết quả cũ (không tạo
  lần thử mới). Cùng key nhưng **body khác** → **409 `IDEMPOTENCY_KEY_REUSE`**.
- Nếu mock timeout/5xx → **202**, giữ `PENDING` (worker nền sẽ thử lại).

### 5.6. Các nhánh fail (dùng ví dụ có sẵn trong dropdown)

| Ví dụ | Kết quả | `failureReason` |
|-------|---------|-----------------|
| `vin_not_found` (VIN lạ) | 200, status FAILED | `VIN_NOT_FOUND` |
| `plate_mismatch` (sai biển số) | 200, FAILED | `PLATE_MISMATCH` |
| `model_mismatch` (sai model) | 200, FAILED | `MODEL_MISMATCH` |
| Email token ≠ email owner | 200, FAILED | `OWNER_EMAIL_MISMATCH` |
| CCCD hồ sơ ≠ CCCD owner | 200, FAILED | `NATIONAL_ID_MISMATCH` |
| `invalid_vin_format` (VIN không đủ 17 ký tự) | 400 `INVALID_REQUEST` | — (chặn ở tầng định dạng) |

- Mỗi lần FAIL trừ 1 lượt; quá `VEHICLE_VERIFY_MAX_FAILED_ATTEMPTS` (5) trong 24h →
  **429 `VERIFICATION_ATTEMPTS_EXCEEDED`** kèm header `Retry-After`.
- `OEM_UNAVAILABLE` **không** bị tính vào giới hạn lượt.

---

## 6. Các route khác — test tương tự

### 6.1. `user-vehicles` (tag `user-vehicles`) — cần onboarding ACTIVE

Chỉ dùng được **sau khi verify xe thành công** (mục 5.5). Cùng token đó:

| Endpoint | Ý nghĩa |
|----------|---------|
| `GET /api/v1/user-vehicles` | Danh sách xe đã verify của user |
| `GET /api/v1/user-vehicles/{userVehicleId}` | Hồ sơ xe: spec, bảo hành, ODO, lần BD gần nhất |
| `GET /api/v1/user-vehicles/{userVehicleId}/maintenance-status` | Trạng thái đến hạn bảo dưỡng + mốc kế tiếp |

- Lấy `userVehicleId` (UUID) từ `data.vehicle.vehicleId` ở response bước 5.5 hoặc từ
  `GET /api/v1/user-vehicles`.
- Chưa onboarding xong → **`ONBOARDING_REQUIRED`**; xe không thuộc user → lỗi
  forbidden/not-found.
- **ODO/lịch sử BD là read-only, đến từ đồng bộ OEM** (không nhập tay). Ngay sau
  verify, backend xếp một job "initial sync". Muốn ODO có số liệu thật, phải chạy
  **Celery worker** (xem [../../docs/RUN_LOCAL_BACKEND.md](../../docs/RUN_LOCAL_BACKEND.md) mục 5):
  ```bash
  cd backend
  uv run celery -A src.celery_tasks worker -B --loglevel=info --pool=solo
  ```
  Không có worker thì job nằm chờ trong Redis, `odometer` sẽ trống.

### 6.2. Webhook OEM (tag `oem-integration`) — ký HMAC, không dùng token

`POST /api/v1/integrations/oem/webhooks` do **hãng gọi**, xác thực bằng chữ ký HMAC
(header event-id/timestamp/signature), **không** phải Firebase. Đừng bấm "Try it
out" tay (thiếu chữ ký hợp lệ). Thay vào đó, cho mock tự bắn sự kiện đã ký:

```bash
# từ Swagger của mock (8100) hoặc curl:
curl -s -X POST http://localhost:8100/webhooks/test-events
```

- Điều kiện: mock đặt `MOCK_WEBHOOK_URL` trỏ về backend
  (`http://localhost:8000/api/v1/integrations/oem/webhooks`) và
  `MOCK_WEBHOOK_SECRET` = `OEM_WEBHOOK_SECRET` của backend.
- Secret hai bên lệch → backend trả **401 `WEBHOOK_SIGNATURE_INVALID`**.
- Bắn `POST /vehicles/{vehicle_id}/service-history` trên mock cũng phát webhook
  `vehicle.service_history.updated`.

### 6.3. `vehicles` (module examples, tag `vehicles`) — không cần token

CRUD xe mẫu, dùng để làm quen Swagger. Xem ví dụ trong [swagger.md](swagger.md) mục 4:
`POST /api/v1/vehicles/` với `{"license_plate":"59a-12345","brand":"Toyota","model":"Camry","year":2024}` → **201**, biển số được chuẩn hoá hoa.

### 6.4. `oauth` / `auth`

- `GET /api/v1/oauth/profile` — kiểm tra token nhanh: trả `uid` + `email` giải mã từ
  token. Tiện để xác nhận Authorize đúng.
- Logout/thu hồi token thuộc tag `auth` (module `auth`).

---

## 7. Reset & lặp lại test

- **mock-ev-system**: dữ liệu in-memory, **restart process là về seed gốc**. Sửa
  seed (cách B mục 3.3) cũng cần restart mới có hiệu lực.
- **backend**: dữ liệu người dùng được lưu bền (Postgres/Supabase, hoặc SQLite
  `backend/data/app.db` nếu không cấu hình DB). Để test lại onboarding từ đầu, chọn 1:
  - Mint token với **`sub` + email mới** (mục 2.4) → tài khoản mới, onboarding mới.
  - Hoặc xoá bản ghi `vehicle_user` tương ứng trong DB.
- Onboarding chưa hoàn tất sẽ tự hết hạn sau `ONBOARDING_RETENTION_DAYS` (15 ngày);
  lần `sign-in` sau đó sẽ dọn và cho làm lại từ đầu.

---

## 8. Xử lý sự cố nhanh

| Triệu chứng | Nguyên nhân thường gặp |
|-------------|------------------------|
| `401 Invalid or expired Firebase token` | Chưa set `FIREBASE_AUTH_EMULATOR_HOST` / chưa restart backend / token hết hạn / dán nhầm (dán cả chữ "Bearer") |
| `sign-in` báo `UNSUPPORTED_SIGN_IN_PROVIDER` | Token không phải provider `google.com` — dùng đúng `signInWithIdp` với `providerId=google.com` (mục 2.4), không dùng `signInWithPassword` |
| `sign-in` báo `EMAIL_NOT_VERIFIED` | Thiếu `email` hoặc `email_verified:true` trong `id_token` giả |
| Verify luôn `OWNER_EMAIL_MISMATCH` | Email token ≠ email owner trong mock (mục 3.3) |
| Verify luôn `NATIONAL_ID_MISMATCH` | `nationalId` ở bước hồ sơ ≠ CCCD owner |
| `vehicle-models` trả `503 OEM_UNAVAILABLE` | mock-ev-system chưa chạy / sai `OEM_API_BASE_URL` |
| `user-vehicles` trả `ONBOARDING_REQUIRED` | Chưa verify xe thành công (chưa `ACTIVE`) |
| Webhook trả `401 WEBHOOK_SIGNATURE_INVALID` | `MOCK_WEBHOOK_SECRET` ≠ `OEM_WEBHOOK_SECRET` |
| ODO xe trống sau verify | Chưa chạy Celery worker (mục 6.1) |
| Backend không start | Redis chưa sống (lifespan gọi `redis_toolkit.start()`) |
