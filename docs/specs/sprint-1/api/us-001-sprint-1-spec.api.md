# API Technical Specification — Đăng ký & Onboarding người dùng mới qua Google OAuth

> Đặc tả API backend cho Feature `FEAT-AUTH-001` (US-001 → US-004).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-001-sprint-1-spec.ff.md) · **Entity:** [Entity Spec](../entity/us-001-sprint-1-spec.entity.md)
>
> API Spec **tuân theo** Functional Spec, không định nghĩa lại nghiệp vụ. Điểm nào là quyết định kỹ thuật chưa được Product chốt được đánh dấu `[Đề xuất]` / `[Cần xác nhận]` và gom ở mục cuối.

---

# 0. Document Information

| Field | Value |
| --- | --- |
| Document ID | `API-SPEC-AUTH-001` |
| Feature | `FEAT-AUTH-001` |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Author | `[Cần điền]` |
| Base URL | `/api/v1` |
| Created Date | `2026-09-27` |
| Updated Date | `2026-09-27` |

## 0.1 API Catalog

| API ID | Method | Endpoint | Mục đích | FF | Màn hình |
| --- | --- | --- | --- | --- | --- |
| `API-001` | `POST` | `/api/v1/oauth/sign-in` | Đồng bộ tài khoản sau khi đăng nhập Google; tạo mới nếu chưa có; trả bước onboarding tiếp theo | US-001, `AC-001`, `AC-005`, `AF-001`, `AF-002`, `BR-001` | SCR-001 |
| `API-002` | `GET` | `/api/v1/onboarding` | Lấy trạng thái + dữ liệu onboarding đã lưu (resume, polling khi chờ hãng) | `AF-002`, `EDGE-001`, `EDGE-003` | SCR-002 → SCR-006 |
| `API-003` | `PUT` | `/api/v1/onboarding/profile` | Lưu thông tin cá nhân + địa điểm gần đó + consent xử lý dữ liệu | US-002, US-003, `BR-005` | SCR-002 |
| `API-004` | `GET` | `/api/v1/onboarding/vehicle-models` | Danh sách mẫu xe (từ hãng) cho dropdown | US-002 | SCR-003 |
| `API-005` | `POST` | `/api/v1/onboarding/vehicle-verification` | Gửi thông tin xe sang hãng xác thực; thành công → `ACTIVE` | US-002, US-004, `AC-002`→`AC-004`, `BR-002`, `BR-004`, `BR-006`, `EF-002`→`EF-004` | SCR-003 → SCR-006 |

**Endpoint có sẵn:** `GET /api/v1/oauth/profile` (trả `uid`, `email` từ token, không đọc DB). `[Đề xuất]` giữ lại cho mục đích debug trong sprint này, đánh dấu **deprecated**; FE dùng API-001 / API-002.

## 0.2 End-to-end Sequence

```mermaid
sequenceDiagram
    autonumber
    actor U as User (App)
    participant FB as Firebase Auth (Google)
    participant API as EV Care Backend
    participant DB as Supabase Postgres
    participant R as Redis
    participant OEM as Hệ thống hãng xe

    U->>FB: signInWithPopup/Redirect(GoogleAuthProvider)
    FB-->>U: Firebase ID token
    U->>API: POST /oauth/sign-in (Bearer ID token)
    API->>FB: verify_id_token (Admin SDK)
    API->>DB: find/create vehicle_user
    API-->>U: onboarding.status + nextStep

    alt nextStep = PROFILE
        U->>API: PUT /onboarding/profile
        API->>DB: update profile, upsert location, insert consent
        API-->>U: nextStep = VEHICLE
    end

    U->>API: GET /onboarding/vehicle-models
    API->>R: cache hit?
    API->>OEM: GET /models (cache miss)
    API-->>U: models[]

    U->>API: POST /onboarding/vehicle-verification (Idempotency-Key)
    API->>DB: status → PENDING_VEHICLE_VERIFICATION
    API->>OEM: lookup VIN → vehicle detail → warranties
    alt Xác thực thành công
        API->>DB: save vehicle + warranty, status → ACTIVE
        API-->>U: 200 VERIFIED, nextStep = HOME
    else Hãng từ chối
        API->>DB: status → VERIFICATION_FAILED
        API-->>U: 200 FAILED + failureReason, nextStep = VEHICLE
    else Timeout hãng
        API->>R: enqueue retry (Celery)
        API-->>U: 202 PENDING, nextStep = VERIFYING
        loop Polling
            U->>API: GET /onboarding
        end
    end
```

---

# C. Common Specification (áp dụng cho mọi API trong tài liệu)

## C.1 Authentication

Mọi API trong tài liệu yêu cầu **Firebase ID token** (không phải Google access token):

```http
Authorization: Bearer <firebase_id_token>
```

- Backend verify bằng Firebase Admin SDK (`auth.verify_id_token`) — đã có ở `backend/src/modules/oauth/dependency.py::verify_firebase_token`.
- API-001 verify với `check_revoked=True` (gọi thêm Firebase để phát hiện token bị thu hồi). Các API khác chỉ verify chữ ký + hạn để giảm độ trễ.
- Token hết hạn sau 1 giờ; FE tự refresh bằng Firebase SDK (`getIdToken()`), backend **không** cấp session/JWT riêng ở sprint này.
- Claim được dùng: `uid`, `email`, `email_verified`, `name`, `picture`, `firebase.sign_in_provider`.

## C.2 Roles & Onboarding Guard

| Role | Access API-001 → API-005 |
| --- | --- |
| `USER` (`vehicle_user`) | ✅ — chỉ dữ liệu của chính mình |
| `CUSTOMER_SUPPORT` | ❌ (dùng API quản trị riêng — ngoài scope) |
| `ADMIN` | ❌ (dùng API quản trị riêng — ngoài scope) |
| `ANONYMOUS` | ❌ `401` |

Hai dependency FastAPI `[Đề xuất]`:

| Dependency | Dùng cho | Kiểm tra | Lỗi |
| --- | --- | --- | --- |
| `get_current_user` | API-002 → API-005 | Token hợp lệ; `vehicle_user` tồn tại theo `firebase_uid`; `status = active` | `401`, `404 USER_NOT_REGISTERED`, `403 ACCOUNT_SUSPENDED/ACCOUNT_INACTIVE` |
| `require_active_user` | **Mọi API tính năng chính khác** (nhắc bảo dưỡng, đặt lịch...) | Như trên + `onboarding_status = active` | `403 ONBOARDING_REQUIRED` — **`BR-003`** |

Không nhận `userId` từ path/body cho các API "của tôi"; user luôn được xác định từ token.

## C.3 Response Envelope

Thành công:

```json
{ "data": { } }
```

Lỗi (theo template dự án):

```json
{
  "error": {
    "code": "PHONE_ALREADY_IN_USE",
    "message": "Số điện thoại đã được sử dụng bởi tài khoản khác.",
    "details": { "field": "phoneNumber" },
    "traceId": "req-8f2a1c"
  }
}
```

- `traceId` lấy từ header `X-Request-ID` nếu client gửi, nếu không backend tự sinh; luôn trả lại trong header `X-Request-ID`.
- `message` bằng tiếng Việt, hiển thị được cho người dùng; FE nên map theo `code` để tuỳ biến.
- **Cần làm:** global exception handler (`common/exception_handlers.py`) chuyển domain exception → envelope trên; override `RequestValidationError` của FastAPI (mặc định `422` với format khác) → `400 INVALID_REQUEST` / `INVALID_FIELD_FORMAT`; `verify_firebase_token` hiện đang raise `HTTPException(detail=...)` cần đổi sang envelope.

## C.4 Naming & Enum Conventions

- JSON field: `camelCase`. Enum ở API: `UPPER_SNAKE_CASE` (DB lưu lowercase — xem Entity Spec mục 3).
- Thời gian: ISO-8601 UTC (`2026-09-27T02:12:31Z`). Ngày: `YYYY-MM-DD`.

**Enum dùng chung**

| Enum | Values |
| --- | --- |
| `OnboardingStatus` | `ONBOARDING_IN_PROGRESS`, `PENDING_VEHICLE_VERIFICATION`, `VERIFICATION_FAILED`, `ACTIVE` |
| `NextStep` | `PROFILE`, `VEHICLE`, `VERIFYING`, `HOME` |
| `AccountStatus` | `ACTIVE`, `INACTIVE`, `SUSPENDED` |
| `VehicleVerificationStatus` | `PENDING`, `VERIFIED`, `FAILED` |
| `VerificationFailureReason` | `VIN_NOT_FOUND`, `PLATE_MISMATCH`, `OWNER_MISMATCH`, `ALREADY_LINKED`, `OEM_UNAVAILABLE` |
| `LocationSource` | `MANUAL`, `MAP_PICK`, `GPS` |
| `WarrantyComponent` | `BATTERY`, `MOTOR`, `CHASSIS`, `ELECTRONICS` |

**Quy tắc `nextStep`** (tính ở backend, FE chỉ điều hướng theo giá trị này):

| Điều kiện | `nextStep` | Màn hình |
| --- | --- | --- |
| `onboardingStatus = ACTIVE` | `HOME` | Home |
| `onboardingStatus = PENDING_VEHICLE_VERIFICATION` | `VERIFYING` | SCR-004 |
| Chưa hoàn tất hồ sơ (`profileCompleted = false`) | `PROFILE` | SCR-002 |
| Còn lại (`ONBOARDING_IN_PROGRESS`, `VERIFICATION_FAILED`) | `VEHICLE` | SCR-003 / SCR-006 |

## C.5 Shared Object: `OnboardingState`

Được trả bởi API-001, API-002, API-003, API-005.

```json
{
  "status": "ONBOARDING_IN_PROGRESS",
  "nextStep": "PROFILE",
  "profileCompleted": false,
  "profileCompletedAt": null,
  "completedAt": null
}
```

| Field | Type | Nullable | Description |
| --- | --- | ---: | --- |
| `status` | `OnboardingStatus` | No | Trạng thái onboarding của tài khoản |
| `nextStep` | `NextStep` | No | Bước FE cần điều hướng tới |
| `profileCompleted` | `boolean` | No | Đã hoàn tất SCR-002 |
| `profileCompletedAt` | `datetime` | Yes | |
| `completedAt` | `datetime` | Yes | Thời điểm chuyển `ACTIVE` |

## C.6 Error Code Catalog

| Error Code | HTTP | API | Description | FF |
| --- | ---: | --- | --- | --- |
| `INVALID_REQUEST` | `400` | All | Thiếu field / sai kiểu / JSON lỗi | |
| `INVALID_FIELD_FORMAT` | `400` | 003, 005 | Sai định dạng (VIN, biển số, SĐT, ngày...) | `EDGE-005` |
| `CONSENT_REQUIRED` | `400` | 003, 005 | Chưa đồng ý điều khoản bắt buộc | Mục 21 |
| `UNAUTHORIZED` | `401` | All | Thiếu header `Authorization` | `EF-001` |
| `INVALID_TOKEN` | `401` | All | Token sai chữ ký / hết hạn / sai project | `EF-001` |
| `TOKEN_REVOKED` | `401` | 001 | Token đã bị thu hồi | `EF-001` |
| `UNSUPPORTED_SIGN_IN_PROVIDER` | `403` | 001 | Provider ≠ `google.com` | Mục 3.2 |
| `EMAIL_NOT_VERIFIED` | `403` | 001 | Email Google chưa xác minh | |
| `ACCOUNT_SUSPENDED` | `403` | All | Tài khoản bị khoá | `EDGE-004` |
| `ACCOUNT_INACTIVE` | `403` | All | Tài khoản ngừng hoạt động | `EDGE-004` |
| `ONBOARDING_REQUIRED` | `403` | API khác | Chưa `ACTIVE` mà gọi tính năng chính | `BR-003` |
| `USER_NOT_REGISTERED` | `404` | 002–005 | Chưa gọi API-001 | |
| `EMAIL_ALREADY_LINKED` | `409` | 001 | Email thuộc tài khoản có Firebase UID khác | `BR-001` |
| `PHONE_ALREADY_IN_USE` | `409` | 003 | SĐT đã dùng bởi tài khoản khác | |
| `ONBOARDING_ALREADY_COMPLETED` | `409` | 003, 005 | Tài khoản đã `ACTIVE` | `AF-001` |
| `PROFILE_INCOMPLETE` | `409` | 005 | Chưa hoàn tất bước hồ sơ | |
| `VERIFICATION_IN_PROGRESS` | `409` | 003, 005 | Đang chờ hãng xác thực | `EDGE-003` |
| `VEHICLE_ALREADY_LINKED` | `409` | 005 | VIN đã gắn tài khoản Active khác | `BR-002`, `EF-004` |
| `IDEMPOTENCY_KEY_REUSED` | `422` | 005 | Cùng `Idempotency-Key` nhưng body khác | |
| `VERIFICATION_ATTEMPTS_EXCEEDED` | `429` | 005 | Vượt số lần xác thực thất bại | `BR-006` |
| `OEM_UNAVAILABLE` | `503` | 004 | Hãng không phản hồi và không có cache | `EF-002` |
| `DATABASE_ERROR` | `500` | All | Lỗi DB | |
| `INTERNAL_SERVER_ERROR` | `500` | All | Lỗi hệ thống | |

> **Lưu ý:** kết quả xác thực **thất bại do hãng từ chối** (`VIN_NOT_FOUND`, `PLATE_MISMATCH`, `OWNER_MISMATCH`) **không** phải lỗi HTTP — API-005 trả `200` với `verification.status = FAILED` vì request đã được xử lý đúng và trạng thái đã được lưu (xem API-005 §7).

## C.7 External Dependency — Hệ thống hãng xe (OEM)

Backend gọi qua HTTP, cấu hình bằng env `[Đề xuất]`:

```text
OEM_API_BASE_URL=http://localhost:8100      # mock-ev-system ở môi trường dev
OEM_API_KEY=<secret>                        # mock chưa yêu cầu; hãng thật sẽ cần
OEM_API_TIMEOUT_SECONDS=8
```

Endpoint của hãng được dùng (theo `backend/mock-ev-system`):

| # | OEM Endpoint | Dùng ở | Mục đích |
| --- | --- | --- | --- |
| O1 | `GET /models` | API-004 | Danh sách mẫu xe |
| O2 | `GET /vehicles/lookup/by-vin?vin=` | API-005 | VIN có tồn tại không → `vehicle_id`, `license_plate` |
| O3 | `GET /vehicles/{vehicle_id}` | API-005 | Model, thông số, chủ xe (`owner.email`, `owner.phone`) |
| O4 | `GET /vehicles/{vehicle_id}/warranties` | API-005 | Hợp đồng bảo hành theo component |
| O5 | `GET /warranty-policies/{model_id}` | API-005 | Điều khoản, thời hạn, component của policy |

> Mock chưa có endpoint "xác thực quyền sở hữu" riêng — backend tự đối chiếu (API-005 §7). Toàn bộ lời gọi hãng đặt sau một port `OemVehicleGateway` (`ports.py`) để thay bằng API thật của hãng mà không đổi service.

## C.8 Observability (chung)

- Log: `traceId`, `firebaseUid`, `userId`, endpoint, method, status, latency, `attemptId` (API-005), latency từng lời gọi OEM.
- **Không log:** ID token, email/SĐT đầy đủ (mask), VIN đầy đủ (mask `RLLVF6*******0123`), thông tin chủ xe hãng trả về.
- Metrics: `signin_total{result, isNewUser}`, `onboarding_step_total{step}`, `vehicle_verification_total{status, failureReason}`, `oem_request_duration_seconds{endpoint}`, `oem_request_errors_total{endpoint, kind}`, số tài khoản `PENDING_VEHICLE_VERIFICATION` quá 15 phút.

---

# API-001 — Sign-in / Đồng bộ tài khoản

## 1. Overview

### 1.1 API Name

`Sign-in with Firebase (Google)`

### 1.2 Purpose

Được gọi **ngay sau khi** FE đăng nhập Google thành công qua Firebase. Backend xác minh ID token, tìm tài khoản theo `firebase_uid`, tạo mới nếu chưa có (`ONBOARDING_IN_PROGRESS`), và trả về trạng thái onboarding + bước tiếp theo để FE điều hướng.

### 1.3 Endpoint

```http
POST /api/v1/oauth/sign-in
```

### 1.4 HTTP Method

| Property | Value |
| --- | --- |
| Method | `POST` |
| Endpoint | `/api/v1/oauth/sign-in` |
| Authentication | Required (Firebase ID token) |
| Authorization | Không yêu cầu role (user có thể chưa tồn tại) |

### 1.5 Scope

**In Scope**

* Verify token, chặn provider khác Google, chặn email chưa xác minh.
* Tạo `vehicle_user` + gán role `vehicle_user` cho user mới.
* Cập nhật `last_login_at`, `display_name`, `avatar_url`, `email_verified` cho user cũ.
* Chặn tài khoản bị khoá (`EDGE-004`).

**Out of Scope**

* Popup/redirect Google — do Firebase SDK phía FE xử lý.
* Đăng xuất (FE gọi `signOut()` của Firebase; backend không giữ session).

## 2. Authentication & Authorization

### 2.1 Authentication

`Authorization: Bearer <firebase_id_token>`, verify với `check_revoked=True`.

### 2.2 Allowed Roles

| Role | Access |
| --- | --- |
| Bất kỳ người có Firebase ID token hợp lệ (provider Google) | ✅ |
| `ANONYMOUS` | ❌ |

### 2.3 Authorization Rules

* `firebase.sign_in_provider` phải là `google.com`.
* `email_verified` phải là `true`.
* Nếu tài khoản tồn tại: `status` phải là `active`.

## 3. Request

### Request Headers

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `Authorization` | `string` | Yes | `Bearer <firebase_id_token>` |
| `X-Request-ID` | `string` | No | Trace id do client sinh |

### Request Body

Không có body.

## 4. Request Validation

| Validation | Rule | Error |
| --- | --- | --- |
| Header | Có `Authorization: Bearer ...` | `401 UNAUTHORIZED` |
| Token | Verify chữ ký, hạn, audience = Firebase project | `401 INVALID_TOKEN` |
| Revocation | Token chưa bị thu hồi | `401 TOKEN_REVOKED` |
| Provider | `firebase.sign_in_provider == "google.com"` | `403 UNSUPPORTED_SIGN_IN_PROVIDER` |
| Email | `email` có giá trị và `email_verified == true` | `403 EMAIL_NOT_VERIFIED` |

## 5. Internal Processing

### 5.1 Processing Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as OAuth Route
    participant FB as Firebase Admin SDK
    participant Svc as SignInService
    participant DB

    Client->>API: POST /oauth/sign-in
    API->>FB: verify_id_token(token, check_revoked=True)
    FB-->>API: claims
    API->>Svc: sign_in(claims)
    Svc->>DB: SELECT vehicle_user WHERE firebase_uid
    alt Chưa có
        Svc->>DB: SELECT vehicle_user WHERE email
        alt Email thuộc UID khác
            Svc-->>API: EmailAlreadyLinked
            API-->>Client: 409
        else
            Svc->>DB: INSERT vehicle_user + user_role (1 transaction)
            Svc-->>API: user, isNewUser = true
            API-->>Client: 201 Created
        end
    else Đã có
        alt status != active
            API-->>Client: 403 ACCOUNT_SUSPENDED / INACTIVE
        else
            Svc->>DB: UPDATE last_login_at, profile từ Google
            API-->>Client: 200 OK
        end
    end
```

### 5.2 Processing Steps

**Step 1 — Authenticate** — Verify token như §4, lấy `uid`, `email` (lowercase), `email_verified`, `name`, `picture`, `sign_in_provider`.

**Step 2 — Load user** — `SELECT ... FROM vehicle_user WHERE firebase_uid = :uid`.

**Step 3a — User chưa tồn tại**

1. Kiểm tra `SELECT user_id FROM vehicle_user WHERE email = :email` → có ⇒ `409 EMAIL_ALREADY_LINKED` (BR-ENT-002).
2. Transaction: `INSERT vehicle_user (firebase_uid, email, email_verified, auth_provider, display_name, avatar_url, status='active', onboarding_status='onboarding_in_progress', last_login_at=now())` → `INSERT user_role (user_id, role_id của 'vehicle_user')`.
3. `isNewUser = true`, HTTP `201`.

**Step 3b — User đã tồn tại**

1. `status ∈ {suspended, inactive}` ⇒ `403`.
2. `UPDATE vehicle_user SET last_login_at = now(), display_name = :name, avatar_url = :picture, email_verified = :ev, updated_at = now()`.
3. `isNewUser = false`, HTTP `200`.

**Step 4 — Build response** — Tính `nextStep` theo C.4.

## 6. Database / Entity Interaction

### 6.1 Entities Used

| Entity / Table | Operation | Purpose |
| --- | --- | --- |
| `vehicle_user` | Read / Insert / Update | Tìm, tạo, cập nhật đăng nhập |
| `roles` | Read | Lấy `id` của role `vehicle_user` (cache in-process) |
| `user_role` | Insert | Gán role mặc định |

### 6.2 Read Data

```sql
SELECT user_id, firebase_uid, email, display_name, avatar_url, full_name,
       status, onboarding_status, profile_completed_at, onboarding_completed_at
FROM vehicle_user
WHERE firebase_uid = :uid;
```

### 6.3 Write Data

```sql
INSERT INTO vehicle_user (firebase_uid, email, email_verified, auth_provider,
                          display_name, avatar_url, status, onboarding_status, last_login_at)
VALUES (:uid, :email, :email_verified, :provider, :name, :picture,
        'active', 'onboarding_in_progress', now())
ON CONFLICT (firebase_uid) DO NOTHING
RETURNING user_id;

INSERT INTO user_role (user_id, role_id, assigned_at) VALUES (:user_id, :role_id, now());
```

### 6.4 Database Transaction

```text
BEGIN
  1. INSERT vehicle_user ... ON CONFLICT (firebase_uid) DO NOTHING
  2. Nếu không insert được (request song song đã tạo) → SELECT lại, coi như user đã tồn tại
  3. INSERT user_role
COMMIT
```

## 7. Business Logic

**Rule 1 — Một Firebase UID ↔ một tài khoản (`BR-001`)** — `firebase_uid` unique; đăng nhập lại luôn trả tài khoản cũ.

**Rule 2 — Email không được gắn 2 UID** — `409 EMAIL_ALREADY_LINKED`.

**Rule 3 — Tài khoản bị khoá (`EDGE-004`)** — `status != active` ⇒ `403`.

**Rule 4 — Điều hướng (`AC-001`, `AC-005`, `AF-002`)** — theo bảng `nextStep` (C.4). User `ACTIVE` ⇒ `HOME`; onboarding dở ⇒ đúng bước còn thiếu.

## 8. Error Handling

| Case | Error Code | HTTP Status |
| --- | --- | ---: |
| Thiếu header | `UNAUTHORIZED` | `401` |
| Token không hợp lệ / hết hạn | `INVALID_TOKEN` | `401` |
| Token bị thu hồi | `TOKEN_REVOKED` | `401` |
| Provider không phải Google | `UNSUPPORTED_SIGN_IN_PROVIDER` | `403` |
| Email chưa xác minh | `EMAIL_NOT_VERIFIED` | `403` |
| Tài khoản bị khoá / ngừng | `ACCOUNT_SUSPENDED` / `ACCOUNT_INACTIVE` | `403` |
| Email thuộc tài khoản khác | `EMAIL_ALREADY_LINKED` | `409` |
| Lỗi DB | `DATABASE_ERROR` | `500` |
| Firebase Admin không phản hồi | `INTERNAL_SERVER_ERROR` | `500` |

## 9. HTTP Status Codes

| HTTP Status | When |
| ---: | --- |
| `201 Created` | Tạo tài khoản mới |
| `200 OK` | Tài khoản đã tồn tại |
| `401` / `403` / `409` / `500` | Theo §8 |

## 10. Response

### 10.1 Success Response

```http
201 Created
```

```json
{
  "data": {
    "isNewUser": true,
    "user": {
      "userId": 42,
      "email": "nguyen.vana@gmail.com",
      "displayName": "Nguyen Van A",
      "avatarUrl": "https://lh3.googleusercontent.com/a/...",
      "fullName": null,
      "accountStatus": "ACTIVE",
      "roles": ["VEHICLE_USER"]
    },
    "onboarding": {
      "status": "ONBOARDING_IN_PROGRESS",
      "nextStep": "PROFILE",
      "profileCompleted": false,
      "profileCompletedAt": null,
      "completedAt": null
    }
  }
}
```

## 11. Response Fields

| Field | Type | Nullable | Description |
| --- | --- | ---: | --- |
| `isNewUser` | `boolean` | No | `true` nếu tài khoản vừa được tạo |
| `user.userId` | `integer` | No | ID nội bộ |
| `user.email` | `string` | No | Email Google |
| `user.displayName` | `string` | Yes | Tên hiển thị từ Google |
| `user.avatarUrl` | `string` | Yes | Ảnh đại diện |
| `user.fullName` | `string` | Yes | Họ tên đã khai báo (null nếu chưa qua SCR-002) |
| `user.accountStatus` | `AccountStatus` | No | Luôn `ACTIVE` khi trả `2xx` |
| `user.roles` | `string[]` | No | Mã role, UPPER_SNAKE_CASE |
| `onboarding` | `OnboardingState` | No | Xem C.5 |

## 12. Error Response Examples

```http
403 Forbidden
```

```json
{
  "error": {
    "code": "ACCOUNT_SUSPENDED",
    "message": "Tài khoản của bạn đang bị khoá. Vui lòng liên hệ bộ phận hỗ trợ.",
    "details": null,
    "traceId": "req-1a2b3c"
  }
}
```

```http
409 Conflict
```

```json
{
  "error": {
    "code": "EMAIL_ALREADY_LINKED",
    "message": "Email này đã được liên kết với một tài khoản khác. Vui lòng liên hệ bộ phận hỗ trợ.",
    "details": null,
    "traceId": "req-1a2b3d"
  }
}
```

## 13. Idempotency

```text
Required: No (idempotent tự nhiên)
```

Gọi lại nhiều lần với cùng token chỉ cập nhật `last_login_at`. Lần gọi đầu trả `201`, các lần sau `200`.

## 14. Concurrency / Race Condition

FE có thể gọi sign-in 2 lần gần như đồng thời (double tap, `onAuthStateChanged` bắn 2 lần). Unique index `firebase_uid` + `INSERT ... ON CONFLICT DO NOTHING` đảm bảo chỉ tạo 1 bản ghi; request thua đọc lại và trả `200`.

## 15. External Dependencies

| Service | Purpose | Required |
| --- | --- | ---: |
| Firebase Admin SDK | Verify token, kiểm tra revoke | Yes |
| Supabase Postgres | Lưu tài khoản | Yes |

## 16. Observability

Theo C.8. Thêm log `isNewUser`, `signInProvider`.

## 17. Performance Requirements

| Metric | Target |
| --- | --- |
| P95 latency | `< 800 ms` (gồm 1 lời gọi revoke check tới Firebase) |
| P99 latency | `< 1500 ms` |

## 18. Retry & Timeout

Firebase revoke check timeout `5s`, không retry trong request; lỗi → `500`, FE cho người dùng thử lại (`EF-001`).

## 19. Versioning

`/api/v1/oauth/sign-in`

## 20. Example Request

```http
POST /api/v1/oauth/sign-in
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6Ij...
X-Request-ID: req-1a2b3c
```

## 21. Example Success Response (user cũ, đang onboarding dở)

```http
HTTP/1.1 200 OK
```

```json
{
  "data": {
    "isNewUser": false,
    "user": {
      "userId": 42,
      "email": "nguyen.vana@gmail.com",
      "displayName": "Nguyen Van A",
      "avatarUrl": null,
      "fullName": "Nguyễn Văn A",
      "accountStatus": "ACTIVE",
      "roles": ["VEHICLE_USER"]
    },
    "onboarding": {
      "status": "VERIFICATION_FAILED",
      "nextStep": "VEHICLE",
      "profileCompleted": true,
      "profileCompletedAt": "2026-09-27T02:10:00Z",
      "completedAt": null
    }
  }
}
```

## 22. Example Error Response

Xem §12.

---

# API-002 — Lấy trạng thái Onboarding

## 1. Overview

### 1.2 Purpose

Trả trạng thái onboarding và toàn bộ dữ liệu đã lưu để FE **khôi phục đúng bước** khi người dùng quay lại (`AF-002`, `EDGE-001`), và để **polling** khi đang chờ hãng xác thực (`EDGE-003`).

### 1.3 Endpoint

```http
GET /api/v1/onboarding
```

### 1.4 HTTP Method

| Property | Value |
| --- | --- |
| Method | `GET` |
| Authentication | Required |
| Authorization | `get_current_user` (C.2) |

### 1.5 Scope

**In Scope** — hồ sơ, địa điểm chính, xe (draft hoặc đã xác thực), bảo hành (nếu `ACTIVE`), lượt xác thực gần nhất, consent hiện hành, số lượt thử còn lại.

**Out of Scope** — lịch sử đầy đủ các lượt xác thực (dành cho Support).

## 2. Authentication & Authorization

User chỉ đọc dữ liệu của chính mình (xác định bằng `firebase_uid` trong token). Hoạt động ở **mọi** `onboardingStatus`, kể cả `ACTIVE`.

## 3. Request

Headers: `Authorization` (required). Không có query/body.

## 4. Request Validation

| Validation | Rule | Error |
| --- | --- | --- |
| Token | Hợp lệ | `401` |
| User | Đã sign-in (tồn tại `vehicle_user`) | `404 USER_NOT_REGISTERED` |
| Account | `status = active` | `403` |

## 5. Internal Processing

### 5.1 Processing Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant DB
    Client->>API: GET /onboarding
    API->>DB: vehicle_user by firebase_uid
    API->>DB: user_location (primary), user_vehicle (active), latest attempt, latest consents
    opt onboardingStatus = ACTIVE
        API->>DB: vehicle_warranty by user_vehicle_id
    end
    API-->>Client: 200 OK
```

### 5.2 Processing Steps

1. Authenticate + load user (C.2).
2. Đọc song song (hoặc 1 query join) các entity ở §6.
3. `remainingAttempts = MAX_FAILED - count(failed trong 24h, trừ OEM_UNAVAILABLE)`.
4. Build response; tính `nextStep`.

## 6. Database / Entity Interaction

| Entity / Table | Operation | Purpose |
| --- | --- | --- |
| `vehicle_user` | Read | Hồ sơ + trạng thái |
| `user_location` | Read | Địa điểm chính |
| `user_vehicle` | Read | Xe `link_status = active` |
| `vehicle_warranty` | Read | Chỉ khi `verified` |
| `vehicle_verification_attempt` | Read | Lượt gần nhất + đếm lượt failed 24h |
| `user_consent` | Read | Consent hiện hành mỗi loại |

```sql
SELECT * FROM vehicle_verification_attempt
WHERE user_id = :userId
ORDER BY requested_at DESC
LIMIT 1;

SELECT count(*) FROM vehicle_verification_attempt
WHERE user_id = :userId AND status = 'failed'
  AND failure_reason <> 'oem_unavailable'
  AND requested_at > now() - interval '24 hours';
```

## 7. Business Logic

Chỉ đọc. Không đổi trạng thái.

## 8. Error Handling

`401`, `403 ACCOUNT_SUSPENDED/INACTIVE`, `404 USER_NOT_REGISTERED`, `500`.

## 9. HTTP Status Codes

`200 OK` — thành công.

## 10. Response

```http
200 OK
```

```json
{
  "data": {
    "onboarding": {
      "status": "VERIFICATION_FAILED",
      "nextStep": "VEHICLE",
      "profileCompleted": true,
      "profileCompletedAt": "2026-09-27T02:10:00Z",
      "completedAt": null
    },
    "profile": {
      "email": "nguyen.vana@gmail.com",
      "displayName": "Nguyen Van A",
      "fullName": "Nguyễn Văn A",
      "phoneNumber": "+84901000001",
      "dateOfBirth": "1990-05-12"
    },
    "location": {
      "addressLine": "Số 1 Đại Cồ Việt, Hai Bà Trưng, Hà Nội",
      "ward": "Bách Khoa",
      "district": "Hai Bà Trưng",
      "province": "Hà Nội",
      "latitude": 21.007,
      "longitude": 105.843,
      "source": "MAP_PICK"
    },
    "vehicle": {
      "vehicleId": "9f0c7a3e-1d2b-4c5a-8e6f-7a8b9c0d1e2f",
      "vin": "RLLVF6AB1PH000123",
      "licensePlate": "30A12346",
      "declaredModelId": "MDL-03",
      "declaredManufactureYear": 2024,
      "verificationStatus": "FAILED",
      "verificationFailureReason": "PLATE_MISMATCH",
      "verifiedAt": null,
      "spec": null
    },
    "warranties": [],
    "latestVerification": {
      "attemptId": "c3d4e5f6-a7b8-4c9d-8e0f-1a2b3c4d5e6f",
      "status": "FAILED",
      "failureReason": "PLATE_MISMATCH",
      "requestedAt": "2026-09-27T02:11:02Z",
      "respondedAt": "2026-09-27T02:11:03Z"
    },
    "remainingAttempts": 4,
    "consents": {
      "personalDataProcessing": { "granted": true, "policyVersion": "2026-09" },
      "oemDataSharing": { "granted": true, "policyVersion": "2026-09" }
    }
  }
}
```

## 11. Response Fields

| Field | Type | Nullable | Description |
| --- | --- | ---: | --- |
| `onboarding` | `OnboardingState` | No | C.5 |
| `profile` | `object` | No | Các field có thể null nếu chưa nhập |
| `profile.phoneNumber` | `string` | Yes | E.164 |
| `location` | `object` | Yes | `null` nếu chưa nhập |
| `vehicle` | `object` | Yes | `null` nếu chưa từng gửi xác thực |
| `vehicle.vehicleId` | `uuid` | No | ID `user_vehicle` (nội bộ, **không** phải ID của hãng) |
| `vehicle.verificationStatus` | `VehicleVerificationStatus` | No | |
| `vehicle.verificationFailureReason` | `VerificationFailureReason` | Yes | |
| `vehicle.spec` | `VehicleSpec` | Yes | Có khi `VERIFIED` — xem API-005 §11 |
| `warranties` | `Warranty[]` | No | Rỗng nếu chưa `VERIFIED` — xem API-005 §11 |
| `latestVerification` | `object` | Yes | Lượt gần nhất |
| `remainingAttempts` | `integer` | No | Số lượt thất bại còn được phép trong 24h |
| `consents.*` | `object` | Yes | Consent hiện hành, `null` nếu chưa có |

## 12. Error Response Examples

```http
404 Not Found
```

```json
{
  "error": {
    "code": "USER_NOT_REGISTERED",
    "message": "Tài khoản chưa được khởi tạo. Vui lòng đăng nhập lại.",
    "details": null,
    "traceId": "req-2b3c4d"
  }
}
```

## 13. Idempotency

`GET` — idempotent.

## 14. Concurrency / Race Condition

Không ghi dữ liệu. Có thể đọc thấy `PENDING` ngay trước khi job nền cập nhật kết quả — FE tiếp tục polling.

## 15. External Dependencies

Chỉ Supabase Postgres. **Không** gọi hãng.

## 16. Observability

Theo C.8. Polling nên log ở level `DEBUG` để tránh nhiễu.

## 17. Performance Requirements

| Metric | Target |
| --- | --- |
| P95 latency | `< 300 ms` |

**Polling (SCR-004):** `[Đề xuất]` FE gọi mỗi `3s`, tối đa `2 phút`; sau đó hiển thị "Hệ thống đang xử lý lâu hơn dự kiến" (`EF-002`) và dừng polling, cho phép thoát.

## 18. Retry & Timeout

API timeout `5s`. FE có thể retry khi lỗi mạng.

## 19. Versioning

`/api/v1/onboarding`

## 20–22. Examples

Xem §10, §12.

---

# API-003 — Lưu thông tin cá nhân & Địa điểm

## 1. Overview

### 1.2 Purpose

Lưu dữ liệu màn SCR-002: họ tên, SĐT, ngày sinh, địa điểm gần đó và consent xử lý dữ liệu cá nhân. Thành công ⇒ đánh dấu hoàn tất bước hồ sơ, `nextStep = VEHICLE`.

### 1.3 Endpoint

```http
PUT /api/v1/onboarding/profile
```

### 1.4 HTTP Method

| Property | Value |
| --- | --- |
| Method | `PUT` (ghi đè toàn bộ dữ liệu bước hồ sơ) |
| Authentication | Required |
| Authorization | `get_current_user` (C.2) |

### 1.5 Scope

**In Scope** — cập nhật hồ sơ trong lúc onboarding (`ONBOARDING_IN_PROGRESS`, `VERIFICATION_FAILED`).

**Out of Scope** — sửa hồ sơ sau khi `ACTIVE` (feature "Cập nhật hồ sơ" riêng — `TERM-001`), geocoding địa chỉ.

## 2. Authentication & Authorization

| Onboarding status | Cho phép | Lỗi |
| --- | --- | --- |
| `ONBOARDING_IN_PROGRESS` | ✅ | |
| `VERIFICATION_FAILED` | ✅ (sửa hồ sơ trước khi gửi lại) | |
| `PENDING_VEHICLE_VERIFICATION` | ❌ | `409 VERIFICATION_IN_PROGRESS` |
| `ACTIVE` | ❌ | `409 ONBOARDING_ALREADY_COMPLETED` |

## 3. Request

### Request Headers

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `Authorization` | `string` | Yes | Bearer token |
| `Content-Type` | `string` | Yes | `application/json` |

### Request Body

```json
{
  "fullName": "Nguyễn Văn A",
  "phoneNumber": "0901000001",
  "dateOfBirth": "1990-05-12",
  "location": {
    "addressLine": "Số 1 Đại Cồ Việt, Hai Bà Trưng, Hà Nội",
    "ward": "Bách Khoa",
    "district": "Hai Bà Trưng",
    "province": "Hà Nội",
    "latitude": 21.007,
    "longitude": 105.843,
    "source": "MAP_PICK",
    "placeId": null
  },
  "personalDataConsent": {
    "granted": true,
    "policyVersion": "2026-09"
  }
}
```

## 3.2 Request Fields

| Field | Type | Required | Nullable | Description | Constraints |
| --- | --- | ---: | ---: | --- | --- |
| `fullName` | `string` | Yes | No | Họ tên đầy đủ | 2–150 ký tự sau trim |
| `phoneNumber` | `string` | Yes | No | SĐT liên hệ | SĐT di động VN |
| `dateOfBirth` | `date` | No | Yes | Ngày sinh | Quá khứ, `>= 1900-01-01` |
| `location` | `object` | Yes `[Cần xác nhận BR-005]` | No | Địa điểm gần đó | |
| `location.addressLine` | `string` | Yes | No | Địa chỉ hiển thị | 5–500 ký tự |
| `location.ward` | `string` | No | Yes | Phường/xã | ≤ 100 |
| `location.district` | `string` | No | Yes | Quận/huyện | ≤ 100 |
| `location.province` | `string` | Yes | No | Tỉnh/thành phố | ≤ 100 |
| `location.latitude` | `number` | Cond. | Yes | Vĩ độ | `-90..90`; bắt buộc nếu `source ∈ {MAP_PICK, GPS}` |
| `location.longitude` | `number` | Cond. | Yes | Kinh độ | `-180..180`; đi cùng `latitude` |
| `location.source` | `LocationSource` | Yes | No | Cách nhập | `MANUAL`, `MAP_PICK`, `GPS` |
| `location.placeId` | `string` | No | Yes | ID địa điểm của map provider | ≤ 255 |
| `personalDataConsent.granted` | `boolean` | Yes | No | Đồng ý xử lý dữ liệu cá nhân | Phải `true` |
| `personalDataConsent.policyVersion` | `string` | Yes | No | Phiên bản điều khoản | Thuộc danh sách phiên bản hiện hành |

## 3.3 Field Technical Specification

### `phoneNumber`

| Property | Value |
| --- | --- |
| Type | `string` |
| Accepted input | `0xxxxxxxxx` hoặc `+84xxxxxxxxx` (cho phép khoảng trắng, `.`, `-`) |
| Regex (sau khi bỏ ký tự phân cách) | `^(0\|\+84)(3\|5\|7\|8\|9)[0-9]{8}$` |
| Stored | E.164 `+84xxxxxxxxx` |

**Constraints** — Không được trùng SĐT của tài khoản khác (`409 PHONE_ALREADY_IN_USE`, `[Cần xác nhận Q-E03]`).

### `fullName`

Trim, gộp khoảng trắng liên tiếp; chỉ chữ cái Unicode (có dấu tiếng Việt), khoảng trắng, `'`, `-`, `.`.

### `dateOfBirth`

`[Cần xác nhận Q-005]` có yêu cầu tuổi tối thiểu (ví dụ 18) hay không. MVP chỉ kiểm tra là ngày trong quá khứ.

## 4. Request Validation

| Validation | Rule | Error |
| --- | --- | --- |
| Required field | `fullName`, `phoneNumber`, `location`, `personalDataConsent` | `400 INVALID_REQUEST` |
| Format | SĐT, ngày, toạ độ, độ dài | `400 INVALID_FIELD_FORMAT` (kèm `details.field`) |
| Toạ độ | `latitude`/`longitude` cùng có hoặc cùng null; bắt buộc khi `MAP_PICK`/`GPS` | `400 INVALID_FIELD_FORMAT` |
| Consent | `granted = true`, `policyVersion` hợp lệ | `400 CONSENT_REQUIRED` |
| Onboarding state | Theo §2 | `409` |
| Phone unique | Không trùng user khác | `409 PHONE_ALREADY_IN_USE` |

## 5. Internal Processing

### 5.1 Processing Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Svc as OnboardingService
    participant DB
    Client->>API: PUT /onboarding/profile
    API->>Svc: update_profile(user, body)
    Svc->>Svc: validate + normalize (phone E.164)
    Svc->>DB: BEGIN
    Svc->>DB: SELECT vehicle_user FOR UPDATE
    Svc->>DB: UPDATE vehicle_user (full_name, phone, dob, profile_completed_at)
    Svc->>DB: UPSERT user_location (primary)
    Svc->>DB: INSERT user_consent (nếu khác hiện hành)
    Svc->>DB: COMMIT
    API-->>Client: 200 OK (nextStep = VEHICLE)
```

### 5.2 Processing Steps

1. Authenticate + load user (C.2).
2. Validate + chuẩn hoá (§3.3).
3. `BEGIN`; `SELECT ... FROM vehicle_user WHERE user_id = :id FOR UPDATE`; kiểm tra lại `onboarding_status` (§2) sau khi lock.
4. `UPDATE vehicle_user SET full_name, phone, date_of_birth, profile_completed_at = COALESCE(profile_completed_at, now())`.
   Nếu vi phạm unique `phone` ⇒ rollback, `409 PHONE_ALREADY_IN_USE`.
5. Upsert `user_location` với `is_primary = true`.
6. Insert `user_consent (personal_data_processing)` nếu khác consent hiện hành (BR-ENT-051).
7. `COMMIT`; trả `OnboardingState` (`nextStep = VEHICLE`).

## 6. Database / Entity Interaction

### 6.1 Entities Used

| Entity / Table | Operation | Purpose |
| --- | --- | --- |
| `vehicle_user` | Read (lock) / Update | Hồ sơ, `profile_completed_at` |
| `user_location` | Upsert | Địa điểm chính |
| `user_consent` | Read / Insert | Consent xử lý dữ liệu |

### 6.3 Write Data

```sql
INSERT INTO user_location (id, user_id, location_type, address_line, ward, district, province,
                           latitude, longitude, source, place_id, is_primary)
VALUES (:id, :userId, 'home', :addressLine, :ward, :district, :province,
        :lat, :lng, :source, :placeId, true)
ON CONFLICT (user_id) WHERE is_primary
DO UPDATE SET address_line = EXCLUDED.address_line, ward = EXCLUDED.ward,
              district = EXCLUDED.district, province = EXCLUDED.province,
              latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude,
              source = EXCLUDED.source, place_id = EXCLUDED.place_id, updated_at = now();
```

### 6.4 Database Transaction

Toàn bộ bước 3–7 trong một transaction; lỗi bất kỳ ⇒ `ROLLBACK`, không lưu dở.

## 7. Business Logic

* **Rule 1** — Chỉ sửa khi chưa `ACTIVE` và không đang chờ hãng (§2).
* **Rule 2** — `BR-005`: `[Đề xuất]` địa điểm bắt buộc để hoàn tất bước; nếu Product chốt "tuỳ chọn" thì `location` thành optional và không ảnh hưởng `profileCompleted`.
* **Rule 3** — Bước hồ sơ **không** đổi `onboardingStatus` (Entity Spec ENT-001 §8.3).

## 8. Error Handling

| Case | Error Code | HTTP |
| --- | --- | ---: |
| Thiếu field | `INVALID_REQUEST` | `400` |
| Sai định dạng | `INVALID_FIELD_FORMAT` | `400` |
| Chưa đồng ý điều khoản | `CONSENT_REQUIRED` | `400` |
| Token | `UNAUTHORIZED` / `INVALID_TOKEN` | `401` |
| Tài khoản bị khoá | `ACCOUNT_SUSPENDED` / `ACCOUNT_INACTIVE` | `403` |
| Chưa sign-in | `USER_NOT_REGISTERED` | `404` |
| Đang chờ hãng | `VERIFICATION_IN_PROGRESS` | `409` |
| Đã hoàn tất | `ONBOARDING_ALREADY_COMPLETED` | `409` |
| SĐT trùng | `PHONE_ALREADY_IN_USE` | `409` |
| Lỗi DB | `DATABASE_ERROR` | `500` |

## 9. HTTP Status Codes

`200 OK` — lưu thành công (kể cả lần sửa lại).

## 10. Response

```http
200 OK
```

```json
{
  "data": {
    "onboarding": {
      "status": "ONBOARDING_IN_PROGRESS",
      "nextStep": "VEHICLE",
      "profileCompleted": true,
      "profileCompletedAt": "2026-09-27T02:10:00Z",
      "completedAt": null
    },
    "profile": {
      "fullName": "Nguyễn Văn A",
      "phoneNumber": "+84901000001",
      "dateOfBirth": "1990-05-12"
    },
    "location": {
      "addressLine": "Số 1 Đại Cồ Việt, Hai Bà Trưng, Hà Nội",
      "ward": "Bách Khoa",
      "district": "Hai Bà Trưng",
      "province": "Hà Nội",
      "latitude": 21.007,
      "longitude": 105.843,
      "source": "MAP_PICK"
    }
  }
}
```

## 11. Response Fields

| Field | Type | Nullable | Description |
| --- | --- | ---: | --- |
| `onboarding` | `OnboardingState` | No | C.5 |
| `profile.phoneNumber` | `string` | No | Đã chuẩn hoá E.164 |
| `location` | `object` | No | Địa điểm đã lưu |

## 12. Error Response Examples

```http
400 Bad Request
```

```json
{
  "error": {
    "code": "INVALID_FIELD_FORMAT",
    "message": "Số điện thoại không hợp lệ.",
    "details": { "field": "phoneNumber" },
    "traceId": "req-3c4d5e"
  }
}
```

```http
409 Conflict
```

```json
{
  "error": {
    "code": "PHONE_ALREADY_IN_USE",
    "message": "Số điện thoại đã được sử dụng bởi tài khoản khác.",
    "details": { "field": "phoneNumber" },
    "traceId": "req-3c4d5f"
  }
}
```

## 13. Idempotency

```text
Required: No — PUT idempotent: gửi lại cùng body cho cùng kết quả.
```

`profile_completed_at` chỉ set lần đầu (`COALESCE`); consent chỉ ghi khi thay đổi.

## 14. Concurrency / Race Condition

* Lock `vehicle_user FOR UPDATE` để không ghi đè lên request API-005 đang chuyển trạng thái sang `PENDING`.
* Hai user cùng đăng ký một SĐT: unique index `phone` chặn, request thua nhận `409`.

## 15. External Dependencies

Supabase Postgres. `[Tuỳ chọn]` map provider ở FE (không gọi từ backend).

## 16. Observability

Theo C.8; không log `fullName`, `phoneNumber`, địa chỉ, toạ độ.

## 17. Performance Requirements

| Metric | Target |
| --- | --- |
| P95 latency | `< 300 ms` |

## 18. Retry & Timeout

API timeout `5s`; DB retry không áp dụng (FE thử lại, request idempotent).

## 19. Versioning

`/api/v1/onboarding/profile`

## 20–22. Examples

Xem §3, §10, §12.

---

# API-004 — Danh sách mẫu xe

## 1. Overview

### 1.2 Purpose

Cung cấp danh sách mẫu xe của hãng cho dropdown "Model" ở SCR-003, để user chọn đúng mã model thay vì gõ tự do.

### 1.3 Endpoint

```http
GET /api/v1/onboarding/vehicle-models
```

### 1.4 HTTP Method

| Property | Value |
| --- | --- |
| Method | `GET` |
| Authentication | Required |
| Authorization | `get_current_user` (C.2), mọi `onboardingStatus` |

### 1.5 Scope

In: proxy + cache `GET /models` của hãng. Out: thông số chi tiết từng model.

## 2. Authentication & Authorization

Xem C.2.

## 3. Request

Headers: `Authorization`. Không có query/body.

## 4. Request Validation

Token + user như C.2.

## 5. Internal Processing

1. Đọc Redis key `oem:vehicle-models:v1`.
2. Cache miss ⇒ gọi OEM `O1 GET /models` (timeout `5s`), map sang response, ghi cache TTL `24h`.
3. OEM lỗi và **có** bản cache cũ (stale, giữ thêm key `oem:vehicle-models:v1:stale` TTL `7 ngày`) ⇒ trả bản cũ, header `X-Data-Stale: true`.
4. OEM lỗi và không có cache ⇒ `503 OEM_UNAVAILABLE`.

## 6. Database / Entity Interaction

Không truy cập Postgres. Redis: `oem:vehicle-models:v1` (TTL 24h), `oem:vehicle-models:v1:stale` (TTL 7d).

## 7. Business Logic

Danh sách sắp xếp theo `modelName`, `trim`.

## 8. Error Handling

| Case | Error Code | HTTP |
| --- | --- | ---: |
| Token | `UNAUTHORIZED` / `INVALID_TOKEN` | `401` |
| Hãng không phản hồi, không có cache | `OEM_UNAVAILABLE` | `503` |

## 9. HTTP Status Codes

`200 OK`, `401`, `403`, `404`, `503`.

## 10. Response

```http
200 OK
```

```json
{
  "data": {
    "items": [
      { "modelId": "MDL-02",  "modelName": "VF6", "trim": "Eco",  "productionYear": 2024 },
      { "modelId": "MDL-03", "modelName": "VF6", "trim": "Plus", "productionYear": 2024 },
      { "modelId": "MDL-06", "modelName": "VF8", "trim": "Plus", "productionYear": 2023 }
    ]
  }
}
```

## 11. Response Fields

| Field | Type | Nullable | Description |
| --- | --- | ---: | --- |
| `items[].modelId` | `string` | No | Mã model của hãng — gửi lại ở API-005 `modelId` |
| `items[].modelName` | `string` | No | Tên dòng xe |
| `items[].trim` | `string` | No | Phiên bản |
| `items[].productionYear` | `integer` | No | Năm sản xuất của model |

## 12. Error Response Examples

```json
{
  "error": {
    "code": "OEM_UNAVAILABLE",
    "message": "Không tải được danh sách mẫu xe. Vui lòng thử lại sau.",
    "details": null,
    "traceId": "req-4d5e6f"
  }
}
```

## 13. Idempotency

`GET` — idempotent.

## 14. Concurrency / Race Condition

Cache stampede khi key hết hạn: dùng Redis lock ngắn (`lock:oem:vehicle-models`, 10s) để chỉ một request gọi hãng; request khác trả bản stale.

## 15. External Dependencies

| Service | Purpose | Required |
| --- | --- | ---: |
| OEM `GET /models` | Nguồn dữ liệu | Yes (trừ khi có cache) |
| Redis | Cache | No (fail-open: gọi thẳng hãng) |

## 16–17. Observability / Performance

| Metric | Target |
| --- | --- |
| P95 (cache hit) | `< 100 ms` |
| Cache hit ratio | `> 95%` |

## 18. Retry & Timeout

OEM timeout `5s`, 1 retry cho lỗi kết nối (không retry `4xx`).

## 19. Versioning

`/api/v1/onboarding/vehicle-models`

---

# API-005 — Gửi xác thực xe với hãng

## 1. Overview

### 1.1 API Name

`Submit Vehicle Verification`

### 1.2 Purpose

Nhận thông tin xe từ SCR-003, lưu lại, gửi sang hệ thống hãng để xác thực quyền sở hữu. Thành công ⇒ lưu thông tin kỹ thuật + bảo hành, chuyển tài khoản sang `ACTIVE`. Thất bại ⇒ `VERIFICATION_FAILED` kèm lý do để user sửa. Hãng timeout ⇒ giữ `PENDING_VEHICLE_VERIFICATION`, retry nền.

### 1.3 Endpoint

```http
POST /api/v1/onboarding/vehicle-verification
```

### 1.4 HTTP Method

| Property | Value |
| --- | --- |
| Method | `POST` |
| Authentication | Required |
| Authorization | `get_current_user` (C.2) + điều kiện trạng thái (§2.3) |

### 1.5 Scope

**In Scope**

* Validate format VIN/biển số trước khi gọi hãng (`EDGE-005`).
* Kiểm tra VIN đã liên kết tài khoản Active khác (`BR-002`, `EF-004`).
* Gọi hãng, đối chiếu, đồng bộ thông tin kỹ thuật + bảo hành (`BR-004`, `AC-003`).
* Giới hạn số lần thất bại (`BR-006`).
* Timeout → xử lý nền (`EF-002`).

**Out of Scope**

* Nhiều xe / chuyển nhượng xe.
* Đồng bộ lại dữ liệu xe định kỳ sau onboarding.

## 2. Authentication & Authorization

### 2.1 Authentication

Bearer Firebase ID token.

### 2.2 Allowed Roles

`USER` — chỉ cho tài khoản của chính mình.

### 2.3 Authorization Rules

| Điều kiện | Lỗi nếu vi phạm |
| --- | --- |
| `profileCompleted = true` | `409 PROFILE_INCOMPLETE` |
| `onboardingStatus ∈ {ONBOARDING_IN_PROGRESS, VERIFICATION_FAILED}` | `PENDING…` ⇒ `409 VERIFICATION_IN_PROGRESS`; `ACTIVE` ⇒ `409 ONBOARDING_ALREADY_COMPLETED` |
| Số lượt `failed` trong 24h (trừ `OEM_UNAVAILABLE`) `< VEHICLE_VERIFY_MAX_FAILED_ATTEMPTS` (mặc định `5`, `[Cần xác nhận Q-002]`) | `429 VERIFICATION_ATTEMPTS_EXCEEDED` |

## 3. Request

### Request Headers

| Field | Type | Required | Description |
| --- | --- | ---: | --- |
| `Authorization` | `string` | Yes | Bearer token |
| `Content-Type` | `string` | Yes | `application/json` |
| `Idempotency-Key` | `string` | Yes | UUID v4 do FE sinh cho mỗi lần nhấn "Xác nhận & Xác thực" |

### Request Body

```json
{
  "vin": "RLLVF6AB1PH000123",
  "licensePlate": "30A-123.45",
  "modelId": "MDL-03",
  "manufactureYear": 2024,
  "oemDataSharingConsent": {
    "granted": true,
    "policyVersion": "2026-09"
  }
}
```

## 3.2 Request Fields

| Field | Type | Required | Nullable | Description | Constraints |
| --- | --- | ---: | ---: | --- | --- |
| `vin` | `string` | Yes | No | Số VIN / số khung | 17 ký tự `[A-HJ-NPR-Z0-9]` sau khi uppercase |
| `licensePlate` | `string` | Yes | No | Biển số | Regex sau chuẩn hoá (§3.3) |
| `modelId` | `string` | Yes | No | Mã model từ API-004 | ≤ 64 ký tự |
| `manufactureYear` | `integer` | No | Yes | Năm sản xuất user khai | `2015..(năm hiện tại + 1)` |
| `oemDataSharingConsent.granted` | `boolean` | Yes | No | Đồng ý chia sẻ dữ liệu xe cho hãng | Phải `true` (mục 21 FF) |
| `oemDataSharingConsent.policyVersion` | `string` | Yes | No | Phiên bản điều khoản | Hợp lệ |

## 3.3 Field Technical Specification

### `vin`

| Property | Value |
| --- | --- |
| Type | `string` |
| Normalize | `trim()`, `upper()` |
| Format | `^[A-HJ-NPR-Z0-9]{17}$` (không có `I`, `O`, `Q`) |

**Constraints** — Không kiểm tra check digit ở MVP (xem Entity Spec ENT-003 §6).

### `licensePlate`

| Property | Value |
| --- | --- |
| Normalize | `upper()`, bỏ khoảng trắng, `.`, `-` — `30A-123.45` → `30A12345` |
| Format (sau normalize) | `^[0-9]{2}[A-Z]{1,2}[0-9]?[0-9]{4,5}$` `[Cần xác nhận với FE Spec]` |

**Meaning** — So khớp với `license_plate` của hãng sau khi chuẩn hoá **cả hai phía**.

### `Idempotency-Key`

UUID v4. FE sinh mới mỗi khi user chủ động nhấn nút gửi; **giữ nguyên** key khi tự retry do lỗi mạng.

## 4. Request Validation

| Validation | Rule | Error |
| --- | --- | --- |
| Required | `vin`, `licensePlate`, `modelId`, `oemDataSharingConsent`, header `Idempotency-Key` | `400 INVALID_REQUEST` |
| Format | VIN, biển số, năm, UUID key | `400 INVALID_FIELD_FORMAT` |
| Consent | `granted = true`, version hợp lệ | `400 CONSENT_REQUIRED` |
| Trạng thái | §2.3 | `409` |
| Retry limit | §2.3 | `429` |
| Idempotency | Key đã dùng với body khác | `422 IDEMPOTENCY_KEY_REUSED` |
| VIN đã liên kết | VIN `verified` + `active` ở user khác | `409 VEHICLE_ALREADY_LINKED` |

> `modelId` không bắt buộc khớp danh sách API-004 tại thời điểm gửi (danh sách có thể stale) — dữ liệu của hãng sau xác thực là nguồn đúng (ENT-003 BR-ENT-022).

## 5. Internal Processing

### 5.1 Processing Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Svc as VehicleVerificationService
    participant R as Redis
    participant DB
    participant OEM as OemVehicleGateway
    participant Q as Celery

    Client->>API: POST /onboarding/vehicle-verification
    API->>Svc: submit(user, body, idemKey)
    Svc->>DB: find attempt by (user_id, idemKey)
    alt Key đã tồn tại
        Svc-->>API: kết quả đã lưu (hoặc 422 nếu body khác)
    end
    Svc->>R: acquire lock onboarding:verify:{userId} (TTL 30s)
    Svc->>DB: check state, retry limit, VIN linked by other user
    Svc->>DB: TX1 upsert user_vehicle(pending), insert attempt(pending),<br/>insert consent, user.onboarding_status = pending
    Svc->>OEM: O2 lookup by VIN
    Svc->>OEM: O3 vehicle detail
    Svc->>Svc: so khớp biển số + chủ xe
    alt Khớp
        Svc->>OEM: O4 warranties + O5 policies
        Svc->>DB: TX2 vehicle verified + snapshot, replace warranties,<br/>attempt success, user ACTIVE
        API-->>Client: 200 VERIFIED
    else Không khớp / VIN không tồn tại
        Svc->>DB: TX2 vehicle failed, attempt failed, user VERIFICATION_FAILED
        API-->>Client: 200 FAILED
    else Timeout / 5xx
        Svc->>Q: enqueue retry_vehicle_verification(attemptId)
        API-->>Client: 202 PENDING
    end
    Svc->>R: release lock
```

### 5.2 Processing Steps

**Step 1 — Authenticate** — `get_current_user` (C.2).

**Step 2 — Validate & normalize** — §3.3, §4. Tính `request_hash = sha256(canonical_json(normalized body))`.

**Step 3 — Idempotency** — `SELECT * FROM vehicle_verification_attempt WHERE user_id = :uid AND idempotency_key = :key`.
* Có và `request_hash` khớp ⇒ trả lại kết quả theo trạng thái hiện tại của attempt (không gọi hãng lại).
* Có và hash khác ⇒ `422 IDEMPOTENCY_KEY_REUSED`.

**Step 4 — Lock** — Redis lock `lock:onboarding:verify:{userId}` TTL `30s` (dùng `backend/src/infrastructure/redis/lock`). Không lấy được ⇒ `409 VERIFICATION_IN_PROGRESS`.

**Step 5 — Pre-checks** (đọc DB)
1. Trạng thái & `profileCompleted` (§2.3).
2. Retry limit (§2.3).
3. VIN đã liên kết:
   ```sql
   SELECT 1 FROM user_vehicle
   WHERE vin = :vin AND verification_status = 'verified'
     AND link_status = 'active' AND user_id <> :userId;
   ```
   Có ⇒ ghi attempt `failed / already_linked`, user → `verification_failed`, trả `409 VEHICLE_ALREADY_LINKED` (không gọi hãng).

**Step 6 — TX1: ghi nhận yêu cầu** — xem §6.4. Commit trước khi gọi hãng để trạng thái `PENDING` bền vững nếu process chết giữa chừng.

**Step 7 — Gọi hãng & đối chiếu** — xem §7 Rule 2. Tổng thời gian chờ hãng trong request tối đa `OEM_API_TIMEOUT_SECONDS` (mặc định `8s`) cho chuỗi O2 → O3; O4/O5 chỉ gọi khi đã khớp.

**Step 8 — TX2: ghi kết quả**
* **VERIFIED** — update `user_vehicle` (`verification_status='verified'`, `external_vehicle_id`, `external_model_id`, `model_name`, `trim`, `color`, `manufacture_date`, `production_year`, `battery_capacity_kwh`, `motor_power_kw`, `verified_at`, `oem_synced_at`); `DELETE` + `INSERT vehicle_warranty`; attempt `success`; `vehicle_user.onboarding_status='active'`, `onboarding_completed_at=now()`, `external_owner_id`.
  Nếu commit vi phạm `ux_user_vehicle_vin_active` (race với user khác) ⇒ rollback, chạy nhánh FAILED với reason `already_linked`, trả `409 VEHICLE_ALREADY_LINKED`.
* **FAILED** — `user_vehicle.verification_status='failed'`, `verification_failure_reason`; attempt `failed`; user `verification_failed`.
* **TIMEOUT / OEM 5xx / lỗi mạng** — attempt giữ `pending`, `retry_count` không đổi; enqueue Celery `retry_vehicle_verification(attempt_id)`; trả `202`.

**Step 9 — Release lock, build response.**

### 5.3 Background Job — `retry_vehicle_verification` `[Đề xuất — cần xác nhận Q-004]`

| Property | Value |
| --- | --- |
| Runner | Celery (`backend/src/celery_tasks.py`) |
| Input | `attempt_id` |
| Retry schedule | `30s`, `2m`, `10m` (3 lần, exponential) |
| Mỗi lần chạy | Nếu attempt không còn `pending` ⇒ bỏ qua. Ngược lại chạy lại Step 7–8. `retry_count += 1` |
| Hết retry | attempt `failed / oem_unavailable`; `user_vehicle` `failed`; user `verification_failed`. **Không** tính vào retry limit của user |
| Reconciler | Job định kỳ 5 phút: attempt `pending` quá 15 phút mà không có task đang chạy ⇒ enqueue lại |
| Thông báo | Khi có kết quả, FE nhận được qua polling API-002. `[Tuỳ chọn]` push notification — ngoài scope |

## 6. Database / Entity Interaction

### 6.1 Entities Used

| Entity / Table | Operation | Purpose |
| --- | --- | --- |
| `vehicle_user` | Read (lock) / Update | Trạng thái onboarding, `external_owner_id` |
| `user_vehicle` | Read / Insert / Update | Xe, kết quả xác thực, snapshot |
| `vehicle_warranty` | Delete / Insert | Bảo hành từ hãng |
| `vehicle_verification_attempt` | Read / Insert / Update | Idempotency, retry limit, log |
| `user_consent` | Read / Insert | Consent chia sẻ dữ liệu cho hãng |

### 6.2 Read Data

```sql
SELECT id, verification_status FROM user_vehicle
WHERE user_id = :userId AND link_status = 'active';
```

### 6.3 Write Data

```sql
-- Upsert xe draft của user (MVP 1 xe active / user)
INSERT INTO user_vehicle (id, user_id, vin, license_plate, declared_model_id,
                          declared_manufacture_year, verification_status, link_status)
VALUES (:id, :userId, :vin, :plate, :modelId, :year, 'pending', 'active')
ON CONFLICT (user_id) WHERE link_status = 'active'
DO UPDATE SET vin = EXCLUDED.vin, license_plate = EXCLUDED.license_plate,
              declared_model_id = EXCLUDED.declared_model_id,
              declared_manufacture_year = EXCLUDED.declared_manufacture_year,
              verification_status = 'pending', verification_failure_reason = NULL,
              updated_at = now()
RETURNING id;

INSERT INTO vehicle_verification_attempt (id, user_id, user_vehicle_id, vin, license_plate,
                                          status, idempotency_key, request_hash, trace_id, requested_at)
VALUES (:attemptId, :userId, :vehicleId, :vin, :plate, 'pending', :key, :hash, :traceId, now());
```

### 6.4 Database Transaction

```text
TX1 (trước khi gọi hãng)
BEGIN
  1. SELECT vehicle_user ... FOR UPDATE, kiểm tra lại trạng thái
  2. UPSERT user_vehicle → pending
  3. INSERT vehicle_verification_attempt → pending
  4. INSERT user_consent (oem_data_sharing) nếu khác hiện hành
  5. UPDATE vehicle_user SET onboarding_status = 'pending_vehicle_verification'
COMMIT

(gọi hãng — ngoài transaction, không giữ connection/lock DB khi chờ HTTP)

TX2 (ghi kết quả)
BEGIN
  1. SELECT vehicle_verification_attempt ... FOR UPDATE; nếu không còn pending → dừng (job nền đã xử lý)
  2. UPDATE user_vehicle / DELETE+INSERT vehicle_warranty (nếu verified)
  3. UPDATE attempt → success | failed
  4. UPDATE vehicle_user → active | verification_failed
COMMIT
```

## 7. Business Logic

### Rule 1 — Xe chỉ hợp lệ khi hãng xác thực (`BR-004`)

`ACTIVE` chỉ được set trong TX2 nhánh VERIFIED.

### Rule 2 — Đối chiếu với hãng `[Đề xuất — cần xác nhận Q-E01]`

| # | Kiểm tra | Nguồn | Không đạt ⇒ `failureReason` |
| --- | --- | --- | --- |
| 1 | VIN tồn tại | O2 `GET /vehicles/lookup/by-vin` trả `200` (`404` ⇒ không tồn tại) | `VIN_NOT_FOUND` |
| 2 | Biển số khớp | `normalize(oem.license_plate) == normalize(request.licensePlate)` | `PLATE_MISMATCH` |
| 3 | Chủ xe khớp | O3 `owner.email` (lowercase) `== user.email` **hoặc** `normalize_phone(owner.phone) == user.phone` | `OWNER_MISMATCH` |

Thứ tự kiểm tra như bảng; dừng ở điều kiện đầu tiên không đạt. Model khai báo khác model của hãng **không** làm fail (ENT-003 BR-ENT-022).

> Khi tích hợp hãng thật có API xác thực ownership, Rule 2 được thay bằng kết quả của hãng bên trong `OemVehicleGateway`, contract API này không đổi.

### Rule 3 — Một VIN một tài khoản Active (`BR-002`)

Pre-check (Step 5.3) + partial unique index (bảo vệ khi race). Kết quả: `409 VEHICLE_ALREADY_LINKED`; FE hiển thị "Xe đã được đăng ký bởi tài khoản khác" + nút liên hệ hỗ trợ (`EF-004`).

### Rule 4 — Giới hạn số lần thất bại (`BR-006`)

Đếm attempt `failed` trong 24h, **không** tính `OEM_UNAVAILABLE`. Vượt ⇒ `429`, header `Retry-After` = số giây tới khi lượt failed cũ nhất trong cửa sổ hết hạn.

### Rule 5 — Thất bại nghiệp vụ trả `200`

Hãng từ chối (`VIN_NOT_FOUND`, `PLATE_MISMATCH`, `OWNER_MISMATCH`) là **kết quả hợp lệ** của request, đã được lưu và đổi trạng thái ⇒ trả `200` với `verification.status = FAILED`. FE chuyển SCR-006 theo `failureReason` (`AC-004`, US-004). Chỉ `ALREADY_LINKED` trả `409` vì FE cần xử lý khác (không cho sửa lại cùng VIN mà hướng tới hỗ trợ).

### Rule 6 — Bảo hành rỗng

Hãng trả danh sách bảo hành rỗng ⇒ vẫn `VERIFIED`, `warranties = []` (ENT-004 BR-ENT-031).

## 8. Error Handling

### 8.1 Error Response Standard

Xem C.3.

### 8.2 Error Cases

| Case | Error Code | HTTP Status |
| --- | --- | ---: |
| Thiếu field / header | `INVALID_REQUEST` | `400` |
| Sai định dạng VIN / biển số / năm | `INVALID_FIELD_FORMAT` | `400` |
| Chưa đồng ý chia sẻ dữ liệu | `CONSENT_REQUIRED` | `400` |
| Token | `UNAUTHORIZED` / `INVALID_TOKEN` | `401` |
| Tài khoản bị khoá | `ACCOUNT_SUSPENDED` / `ACCOUNT_INACTIVE` | `403` |
| Chưa sign-in | `USER_NOT_REGISTERED` | `404` |
| Chưa xong bước hồ sơ | `PROFILE_INCOMPLETE` | `409` |
| Đang chờ hãng / request song song | `VERIFICATION_IN_PROGRESS` | `409` |
| Đã hoàn tất onboarding | `ONBOARDING_ALREADY_COMPLETED` | `409` |
| VIN đã gắn tài khoản khác | `VEHICLE_ALREADY_LINKED` | `409` |
| Dùng lại Idempotency-Key với body khác | `IDEMPOTENCY_KEY_REUSED` | `422` |
| Vượt số lần thất bại | `VERIFICATION_ATTEMPTS_EXCEEDED` | `429` |
| Lỗi DB | `DATABASE_ERROR` | `500` |
| Lỗi không dự kiến | `INTERNAL_SERVER_ERROR` | `500` |

## 9. HTTP Status Codes

| HTTP Status | When |
| ---: | --- |
| `200 OK` | Có kết quả xác thực: `VERIFIED` hoặc `FAILED` |
| `202 Accepted` | Hãng timeout/lỗi — đang xử lý nền, FE polling API-002 |
| `400` / `401` / `403` / `404` / `409` / `422` / `429` / `500` | Theo §8.2 |

## 10. Response

### 10.1 Success — VERIFIED

```http
200 OK
```

```json
{
  "data": {
    "onboarding": {
      "status": "ACTIVE",
      "nextStep": "HOME",
      "profileCompleted": true,
      "profileCompletedAt": "2026-09-27T02:10:00Z",
      "completedAt": "2026-09-27T02:12:31Z"
    },
    "verification": {
      "attemptId": "d4e5f6a7-b8c9-4d0e-9f1a-2b3c4d5e6f70",
      "status": "VERIFIED",
      "failureReason": null,
      "message": "Xác thực xe thành công.",
      "remainingAttempts": 5
    },
    "vehicle": {
      "vehicleId": "9f0c7a3e-1d2b-4c5a-8e6f-7a8b9c0d1e2f",
      "vin": "RLLVF6AB1PH000123",
      "licensePlate": "30A12345",
      "verificationStatus": "VERIFIED",
      "verifiedAt": "2026-09-27T02:12:31Z",
      "spec": {
        "modelId": "MDL-03",
        "modelName": "VF6",
        "trim": "Plus",
        "color": "Xanh",
        "manufactureDate": "2024-03-15",
        "productionYear": 2024,
        "batteryCapacityKwh": 59.6,
        "motorPowerKw": 150.0
      }
    },
    "warranties": [
      {
        "component": "BATTERY",
        "startDate": "2024-03-15",
        "endDate": "2032-03-15",
        "kmLimit": 160000,
        "durationMonths": 96,
        "status": "ACTIVE",
        "termsDescription": "Bảo hành pin 8 năm hoặc 160.000 km, tuỳ điều kiện nào đến trước"
      },
      {
        "component": "MOTOR",
        "startDate": "2024-03-15",
        "endDate": "2029-03-15",
        "kmLimit": 100000,
        "durationMonths": 60,
        "status": "ACTIVE",
        "termsDescription": "Bảo hành động cơ điện 5 năm"
      }
    ]
  }
}
```

### 10.2 Success — FAILED (hãng từ chối)

```http
200 OK
```

```json
{
  "data": {
    "onboarding": {
      "status": "VERIFICATION_FAILED",
      "nextStep": "VEHICLE",
      "profileCompleted": true,
      "profileCompletedAt": "2026-09-27T02:10:00Z",
      "completedAt": null
    },
    "verification": {
      "attemptId": "c3d4e5f6-a7b8-4c9d-8e0f-1a2b3c4d5e6f",
      "status": "FAILED",
      "failureReason": "PLATE_MISMATCH",
      "message": "Biển số không khớp với số VIN trên hệ thống hãng. Vui lòng kiểm tra lại.",
      "remainingAttempts": 4
    },
    "vehicle": {
      "vehicleId": "9f0c7a3e-1d2b-4c5a-8e6f-7a8b9c0d1e2f",
      "vin": "RLLVF6AB1PH000123",
      "licensePlate": "30A12346",
      "verificationStatus": "FAILED",
      "verifiedAt": null,
      "spec": null
    },
    "warranties": []
  }
}
```

### 10.3 Accepted — PENDING (hãng timeout)

```http
202 Accepted
```

```json
{
  "data": {
    "onboarding": {
      "status": "PENDING_VEHICLE_VERIFICATION",
      "nextStep": "VERIFYING",
      "profileCompleted": true,
      "profileCompletedAt": "2026-09-27T02:10:00Z",
      "completedAt": null
    },
    "verification": {
      "attemptId": "e5f6a7b8-c9d0-4e1f-8a2b-3c4d5e6f7a81",
      "status": "PENDING",
      "failureReason": null,
      "message": "Hệ thống hãng đang xử lý lâu hơn dự kiến. Chúng tôi sẽ cập nhật kết quả sớm.",
      "remainingAttempts": 5
    },
    "vehicle": {
      "vehicleId": "9f0c7a3e-1d2b-4c5a-8e6f-7a8b9c0d1e2f",
      "vin": "RLLVF6AB1PH000123",
      "licensePlate": "30A12345",
      "verificationStatus": "PENDING",
      "verifiedAt": null,
      "spec": null
    },
    "warranties": []
  }
}
```

## 11. Response Fields

| Field | Type | Nullable | Description |
| --- | --- | ---: | --- |
| `onboarding` | `OnboardingState` | No | C.5 |
| `verification.attemptId` | `uuid` | No | ID lượt xác thực |
| `verification.status` | `string` | No | `VERIFIED`, `FAILED`, `PENDING` |
| `verification.failureReason` | `VerificationFailureReason` | Yes | Có khi `FAILED` |
| `verification.message` | `string` | No | Thông điệp hiển thị cho user |
| `verification.remainingAttempts` | `integer` | No | Lượt thất bại còn được phép trong 24h |
| `vehicle.vehicleId` | `uuid` | No | ID `user_vehicle` nội bộ |
| `vehicle.vin` | `string` | No | VIN đã chuẩn hoá |
| `vehicle.licensePlate` | `string` | No | Biển số đã chuẩn hoá |
| `vehicle.verificationStatus` | `VehicleVerificationStatus` | No | |
| `vehicle.verifiedAt` | `datetime` | Yes | |
| `vehicle.spec` | `VehicleSpec` | Yes | Chỉ có khi `VERIFIED` |
| `warranties[]` | `Warranty[]` | No | Rỗng nếu chưa `VERIFIED` |

### 11.1 Response Field Details

#### `VehicleSpec`

| Field | Type | Nullable | Source (OEM) |
| --- | --- | ---: | --- |
| `modelId` | `string` | No | `model.model_id` |
| `modelName` | `string` | No | `model.model_name` |
| `trim` | `string` | Yes | `model.trim` |
| `color` | `string` | Yes | `color` |
| `manufactureDate` | `date` | Yes | `manufacture_date` |
| `productionYear` | `integer` | Yes | `model.production_year` |
| `batteryCapacityKwh` | `number` | Yes | `model.battery_capacity_kwh` |
| `motorPowerKw` | `number` | Yes | `model.motor_power_kw` |

#### `Warranty`

| Field | Type | Nullable | Description |
| --- | --- | ---: | --- |
| `component` | `WarrantyComponent` | No | Hạng mục |
| `startDate` / `endDate` | `date` | No | Hiệu lực |
| `kmLimit` | `integer` | Yes | Giới hạn km |
| `durationMonths` | `integer` | Yes | Thời hạn (từ policy) |
| `status` | `string` | No | `ACTIVE` / `EXPIRED` — **tính lại** theo `endDate` so với ngày hiện tại |
| `termsDescription` | `string` | Yes | Điều khoản (từ policy) |

#### `verification.message` theo `failureReason`

| `failureReason` | Message gợi ý | Hành động FE (SCR-006) |
| --- | --- | --- |
| `VIN_NOT_FOUND` | "Không tìm thấy số VIN trên hệ thống hãng. Vui lòng kiểm tra lại số VIN." | Sửa thông tin xe |
| `PLATE_MISMATCH` | "Biển số không khớp với số VIN trên hệ thống hãng. Vui lòng kiểm tra lại." | Sửa thông tin xe |
| `OWNER_MISMATCH` | "Thông tin chủ xe trên hệ thống hãng không khớp với tài khoản của bạn." | Liên hệ hỗ trợ / sửa |
| `OEM_UNAVAILABLE` | "Hệ thống hãng tạm thời không phản hồi. Vui lòng thử lại sau." | Gửi lại |

## 12. Error Response Examples

### 12.1 Invalid VIN

```http
400 Bad Request
```

```json
{
  "error": {
    "code": "INVALID_FIELD_FORMAT",
    "message": "Số VIN phải gồm 17 ký tự chữ và số, không chứa I, O, Q.",
    "details": { "field": "vin" },
    "traceId": "req-5e6f7a"
  }
}
```

### 12.2 Vehicle Already Linked

```http
409 Conflict
```

```json
{
  "error": {
    "code": "VEHICLE_ALREADY_LINKED",
    "message": "Xe đã được đăng ký bởi tài khoản khác. Vui lòng liên hệ bộ phận hỗ trợ.",
    "details": { "attemptId": "f6a7b8c9-d0e1-4f2a-8b3c-4d5e6f7a8b92" },
    "traceId": "req-5e6f7b"
  }
}
```

### 12.3 Attempts Exceeded

```http
429 Too Many Requests
Retry-After: 43200
```

```json
{
  "error": {
    "code": "VERIFICATION_ATTEMPTS_EXCEEDED",
    "message": "Bạn đã xác thực thất bại quá nhiều lần. Vui lòng thử lại sau hoặc liên hệ hỗ trợ.",
    "details": { "retryAfterSeconds": 43200 },
    "traceId": "req-5e6f7c"
  }
}
```

## 13. Idempotency

```text
Required: Yes
Idempotency-Key: <uuid-v4>
```

* **Client** — sinh key mới mỗi lần user nhấn gửi; giữ nguyên key khi tự retry do mất mạng/timeout phía client.
* **Backend lưu** — cột `vehicle_verification_attempt.idempotency_key` + `request_hash`, unique `(user_id, idempotency_key)`.
* **Hiệu lực** — theo vòng đời bản ghi attempt (không hết hạn trong scope này).
* **Gửi lại cùng key + cùng body** — trả kết quả hiện tại của attempt: `200` (VERIFIED/FAILED), `202` (còn PENDING). Không gọi hãng lần nữa.
* **Cùng key + body khác** — `422 IDEMPOTENCY_KEY_REUSED`.

## 14. Concurrency / Race Condition

| Tình huống | Giải pháp |
| --- | --- |
| User double-tap, 2 request khác key | Redis lock theo user + partial unique `ux_attempt_user_pending` ⇒ request thứ hai `409 VERIFICATION_IN_PROGRESS` |
| 2 user cùng xác thực một VIN | Pre-check + partial unique `ux_user_vehicle_vin_active` khi commit TX2 ⇒ người sau `409 VEHICLE_ALREADY_LINKED` |
| Request đồng bộ và job nền cùng ghi kết quả | TX2 `SELECT attempt FOR UPDATE` và chỉ ghi khi còn `pending` |
| API-003 sửa hồ sơ trong lúc API-005 chạy | Cả hai lock `vehicle_user FOR UPDATE`; API-003 thấy `PENDING` ⇒ `409` |
| Redis không khả dụng | Fail-open: bỏ lock, dựa vào partial unique index ở DB |

## 15. External Dependencies

| Service | Purpose | Required |
| --- | --- | ---: |
| Firebase Admin SDK | Verify token | Yes |
| Supabase Postgres | Lưu dữ liệu | Yes |
| Hệ thống hãng xe (O2–O5) | Xác thực + dữ liệu kỹ thuật/bảo hành | Yes |
| Redis | Lock | No (fail-open) |
| Celery (broker Redis) | Retry nền khi hãng timeout | Yes cho `EF-002` |

## 16. Observability

Theo C.8, thêm:

* Log mỗi lời gọi OEM: endpoint, status, latency, `attemptId` — **không** log body response (chứa thông tin chủ xe).
* Alert: tỉ lệ `OEM_UNAVAILABLE` > 10% trong 15 phút; có attempt `pending` > 15 phút.

## 17. Performance Requirements

| Metric | Target |
| --- | --- |
| P95 (không tính thời gian hãng) | `< 500 ms` |
| P95 end-to-end (hãng phản hồi bình thường) | `< 3 s` |
| Thời gian tối đa trước khi trả `202` | `OEM_API_TIMEOUT_SECONDS` (`8 s`) + overhead |

`[Cần xác nhận]` SLA của hãng (FF mục 18).

## 18. Retry & Timeout

### Timeout

```text
API timeout (request đồng bộ): 12 seconds
OEM timeout mỗi lời gọi: connect 2s, read 5s; tổng chuỗi O2→O3 tối đa 8s
Database statement timeout: 5 seconds
```

### Retry

| Dependency | Retry | Max Attempts | Backoff |
| --- | ---: | ---: | --- |
| OEM trong request đồng bộ | Yes (chỉ lỗi kết nối, không retry timeout) | 1 | Không |
| OEM qua Celery (timeout/5xx) | Yes | 3 | `30s`, `2m`, `10m` |
| OEM `4xx` (trừ `404` ở O2 = VIN không tồn tại) | No | — | Ghi `failed / oem_unavailable`, log error |
| Database | No | — | Trả `500` |

## 19. Versioning

`/api/v1/onboarding/vehicle-verification`

## 20. Example Request

```http
POST /api/v1/onboarding/vehicle-verification
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: 6f1c1c56-2d7c-4d3e-b7e9-1a0e0c9b5a11
```

```json
{
  "vin": "rllvf6ab1ph000123",
  "licensePlate": "30A-123.45",
  "modelId": "MDL-03",
  "manufactureYear": 2024,
  "oemDataSharingConsent": { "granted": true, "policyVersion": "2026-09" }
}
```

## 21. Example Success Response

Xem §10.1.

## 22. Example Error Response

Xem §12.

---

# 23. Change Log

| Version | Date | Author | Changes |
| --- | --- | --- | --- |
| `v1.0` | `2026-09-27` | `[Cần điền]` | Bản nháp đầu tiên: 5 API cho đăng ký & onboarding |

---

# 24. Open Questions

* [ ] **Q-A01 (FF Q-004)** — Hãng timeout: giữ `PENDING` + retry nền 3 lần rồi chuyển `VERIFICATION_FAILED / OEM_UNAVAILABLE` (đề xuất hiện tại), hay cho vào Home tạm với trạng thái "Chờ xác thực"?
* [ ] **Q-A02 (FF Q-002)** — Giới hạn `5` lượt thất bại / 24h có phù hợp không?
* [ ] **Q-A03 (Entity Q-E01)** — Rule xác thực quyền sở hữu: so khớp email hoặc SĐT với chủ xe bên hãng; hãng thật có API xác thực ownership riêng không?
* [ ] **Q-A04 (FF Q-001, BR-005)** — Địa điểm bắt buộc hay tuỳ chọn; nhập địa chỉ hay chọn trên bản đồ?
* [ ] **Q-A05** — Hãng thật dùng cơ chế đồng bộ hay webhook/callback? Nếu webhook, cần thêm endpoint `POST /api/v1/integrations/oem/vehicle-verification-callback` và bỏ Celery retry.
* [ ] **Q-A06** — Nội dung và phiên bản điều khoản consent (`policyVersion`) do ai quản lý (Legal)? Có cần API trả nội dung điều khoản không?
* [ ] **Q-A07** — Endpoint cũ `GET /api/v1/oauth/profile`: xoá hay giữ?
* [ ] **Q-A08** — Có cần push notification khi kết quả xác thực nền có (thay cho polling)?

---

# 25. References

* Functional Spec: [us-001-sprint-1-spec.ff.md](../feature-functional/us-001-sprint-1-spec.ff.md)
* Entity Spec: [us-001-sprint-1-spec.entity.md](../entity/us-001-sprint-1-spec.entity.md)
* ERD hệ thống hãng (mock): [proposed_erd.md](../../entity/proposed_erd.md)
* Mock OEM API: `backend/mock-ev-system/src/mock_ev_system/routers/`
* Hướng dẫn cấu trúc backend: `backend/guide/api.md`
* Code hiện có: `backend/src/modules/oauth/`, `backend/src/common/core/identity/vehicle_user.py`
