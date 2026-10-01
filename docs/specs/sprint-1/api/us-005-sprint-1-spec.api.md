# API Technical Specification — Đăng nhập & Đăng xuất (Chủ xe)

> Đặc tả API backend cho Feature `FEAT-AUTH-002` (US-005 → US-008).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-005-sprint-1-spec.ff.md) · **Entity:** [Entity Spec](../entity/us-005-sprint-1-spec.entity.md)
>
> **Quan hệ với FEAT-AUTH-001:** Hành động **đăng nhập** tái sử dụng endpoint `POST /api/v1/oauth/sign-in` (API-001) đã đặc tả ở [us-001 API Spec](./us-001-sprint-1-spec.api.md); tài liệu này **tham chiếu** API-001 (mục Login) và đặc tả đầy đủ endpoint **đăng xuất** mới (API-101).
>
> **Quyết định đã chốt:** mọi endpoint được bảo vệ yêu cầu Firebase ID token; chỉ `/profile` kiểm tra revoke tức thời. Logout ghi audit và xếp hàng tác vụ revoke nền.

---

# 0. Document Information

| Field | Value |
| --- | --- |
| Document ID | `API-SPEC-AUTH-002` |
| Feature | `FEAT-AUTH-002` |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Backend Team |
| Author | `[Cần điền]` |
| Base URL | `/api/v1` |
| Created Date | `2026-09-27` |
| Updated Date | `2026-09-27` |

## 0.1 API Catalog

| API ID | Method | Endpoint | Mục đích | FF | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| `API-001` | `POST` | `/api/v1/oauth/sign-in` | Đăng nhập / đồng bộ tài khoản, trả bước điều hướng | US-005, US-007, AC-101, AC-102, AC-106 | **Tái sử dụng** (đặc tả tại [us-001 API](./us-001-sprint-1-spec.api.md)) |
| `API-101` | `POST` | `/api/v1/oauth/logout` | Đăng xuất: thu hồi phiên phía máy chủ + ghi mốc/audit | US-006, AC-104, BR-105 | **Mới** |
| `API-102` | `GET` | `/api/v1/oauth/profile` | Kiểm tra phiên/định danh hiện tại (session check nhẹ) | US-007, US-008 | **Có sẵn** (endpoint hiện tại) |

> Backend **stateless theo token**: không có server session. "Đăng nhập" = client lấy Firebase ID token rồi gọi API-001; "đăng xuất" = client xoá token cục bộ **và** gọi API-101 để thu hồi refresh token phía Firebase.

## 0.2 Sequence (Login → dùng dịch vụ → Logout)

```mermaid
sequenceDiagram
    autonumber
    actor U as User (App)
    participant FB as Firebase Auth (Google)
    participant API as EV Care Backend
    participant DB as Supabase Postgres

    U->>FB: signInWithGoogle()
    FB-->>U: ID token (+ refresh token giữ trong SDK)
    U->>API: POST /oauth/sign-in (Bearer ID token)
    API->>FB: verify_id_token
    API->>DB: find vehicle_user, update last_login_at
    API-->>U: onboarding.nextStep (HOME nếu ACTIVE)

    Note over U,API: ... dùng dịch vụ với Bearer ID token ...

    U->>API: POST /oauth/logout (Bearer ID token)
    API->>FB: revoke_refresh_tokens(uid)
    API->>DB: set last_logout_at, insert AuthEvent(logout)
    API-->>U: 204 No Content
    U->>FB: signOut() (xoá token cục bộ)
```

---

# C. Common Specification

## C.1 Authentication

Mọi API yêu cầu **Firebase ID token**:

```http
Authorization: Bearer <firebase_id_token>
```

Verify bằng Firebase Admin SDK (`auth.verify_id_token`), tái dùng dependency `verify_firebase_token` hiện có (`backend/src/modules/oauth/dependency.py`).

- ID token sống ~1 giờ; client tự làm mới bằng Firebase SDK (`getIdToken()`) — backend **không** cấp token/session riêng.
- **`check_revoked`:** mọi endpoint được bảo vệ đều xác minh chữ ký và hạn token. Riêng `/api/v1/oauth/profile` dùng `check_revoked=True` để phát hiện token đã revoke tức thời; các endpoint khác không gọi kiểm tra revoke với Firebase trên từng request.

## C.2 Roles

| Role | Access |
| --- | --- |
| Chủ xe (`vehicle_user`) có token hợp lệ | ✅ (chỉ phiên/tài khoản của chính mình) |
| `ANONYMOUS` | ❌ `401` |

## C.3 Error Envelope

Nhất quán với FEAT-AUTH-001 (C.3):

```json
{
  "error": { "code": "INVALID_TOKEN", "message": "…", "details": null, "traceId": "req-…" }
}
```

## C.4 Error Code Catalog (feature này)

| Error Code | HTTP | API | Description | FF |
| --- | ---: | --- | --- | --- |
| `UNAUTHORIZED` | `401` | All | Thiếu header `Authorization` | EF-101 |
| `INVALID_TOKEN` | `401` | All | Token sai chữ ký / hết hạn / sai project | EF-102 |
| `TOKEN_REVOKED` | `401` | API-102 (khi verify `check_revoked`) | Token đã bị thu hồi | BR-106 |
| `ACCOUNT_SUSPENDED` | `403` | API-001/102 | Tài khoản bị khoá | EF-103 |
| `ACCOUNT_INACTIVE` | `403` | API-001/102 | Tài khoản ngừng hoạt động | EF-103 |
| `AUTH_PROVIDER_UNAVAILABLE` | `503` | API-101 | Không thể xác minh token hoặc ghi nhận/xếp hàng yêu cầu logout | EF-104 |
| `INTERNAL_SERVER_ERROR` | `500` | All | Lỗi hệ thống | |

> Các mã của **đăng nhập** (`UNSUPPORTED_SIGN_IN_PROVIDER`, `EMAIL_NOT_VERIFIED`, `EMAIL_ALREADY_LINKED`, `USER_NOT_REGISTERED`...) được định nghĩa ở API Spec của FEAT-AUTH-001; không lặp lại ở đây.

---

# LOGIN — tham chiếu API-001

Đăng nhập của feature này **không tạo endpoint mới**; client gọi `POST /api/v1/oauth/sign-in` (API-001) sau khi lấy được Firebase ID token.

**Hành vi liên quan feature (chủ xe đã có tài khoản):**

| Tình huống | Kết quả API-001 | Điều hướng (FF) |
| --- | --- | --- |
| Tài khoản `ACTIVE` | `200 OK`, `onboarding.nextStep = HOME`, cập nhật `last_login_at` | Vào Home (AC-101) |
| Onboarding chưa xong | `200 OK`, `nextStep ∈ {PROFILE, VEHICLE, VERIFYING}` | Tiếp tục onboarding (AC-106) |
| Tài khoản bị khoá | `403 ACCOUNT_SUSPENDED / ACCOUNT_INACTIVE` | Màn thông báo khoá (AC-103) |
| Định danh Firebase chưa từng tồn tại | `201 Created` (tạo mới, `ONBOARDING_IN_PROGRESS`) | Vào onboarding (EDGE-106) |

**Auto-login (US-007):** khi mở lại app, client dùng token còn hiệu lực (tự làm mới nếu cần) và gọi API-001 để lấy `nextStep`. Không có API riêng cho auto-login.

**Token refresh (US-008):** khi ID token hết hạn, client làm mới qua Firebase SDK. Nếu refresh token đã bị thu hồi (đã đăng xuất) → không làm mới được → client đưa người dùng về màn Login (BR-106).

Chi tiết request/response/validation của đăng nhập: xem [us-001 API Spec — API-001](./us-001-sprint-1-spec.api.md).

---

# API-101 — Logout

## 1. Overview

### 1.1 API Name

`Logout (revoke session)`

### 1.2 Purpose

Ghi nhận `last_logout_at`, audit `AuthEvent` và xếp hàng tác vụ thu hồi refresh token qua Firebase. API trả `204` sau khi yêu cầu được nhận; worker hoàn tất revoke bất đồng bộ. Client vẫn phải tự xoá token cục bộ (Firebase `signOut()`).

### 1.3 Endpoint

```http
POST /api/v1/oauth/logout
```

### 1.4 HTTP Method

| Property | Value |
| --- | --- |
| Method | `POST` |
| Endpoint | `/api/v1/oauth/logout` |
| Authentication | Required (Firebase ID token) |
| Authorization | Người dùng chỉ đăng xuất phiên của chính mình |

### 1.5 Scope

**In Scope**

- Ghi `last_logout_at` và `AuthEvent(logout)` khi nhận yêu cầu.
- Xếp hàng worker thu hồi refresh token của `uid` hiện tại (`auth.revoke_refresh_tokens`) và ghi kết quả `session_revoked` hoặc `session_revoke_failed`.

**Out of Scope**

- Xoá token/phiên phía client (do app + Firebase SDK làm).
- Giao diện/API quản lý danh sách thiết bị hoặc thu hồi từng thiết bị. Firebase revoke theo UID vốn áp dụng cho refresh token trên mọi thiết bị của UID.

## 2. Authentication & Authorization

### 2.1 Authentication

`Authorization: Bearer <firebase_id_token>`. Verify chữ ký + hạn. Logout không yêu cầu `check_revoked` vì token đầu vào có thể thuộc phiên đang cần kết thúc.

### 2.2 Allowed Roles

| Role | Access |
| --- | --- |
| Chủ xe có token hợp lệ | ✅ |
| `ANONYMOUS` | ❌ |

### 2.3 Authorization Rules

- `uid` được lấy từ token; endpoint chỉ thu hồi phiên của chính `uid` đó.
- Không nhận `user_id`/`uid` từ body.

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
| Token | Verify chữ ký + hạn hợp lệ | `401 INVALID_TOKEN` |

> Không kiểm tra trạng thái tài khoản khi đăng xuất: tài khoản bị khoá vẫn được phép đăng xuất phiên hiện tại.

## 5. Internal Processing

### 5.1 Processing Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as Logout Route
    participant FB as Firebase Admin SDK
    participant DB
    participant Q as Background Worker

    Client->>API: POST /oauth/logout (Bearer token)
    API->>FB: verify_id_token(token)
    FB-->>API: claims (uid)
    API->>DB: update last_logout_at + insert AuthEvent(logout)
    API->>Q: enqueue durable revoke task(uid, trace_id)
    Q-->>API: accepted
    API-->>Client: 204 No Content
    Q->>FB: revoke_refresh_tokens(uid)
    alt Revoke OK
      Q->>DB: insert AuthEvent(session_revoked, success)
    else Firebase lỗi
      Q->>DB: insert AuthEvent(session_revoke_failed, failed)
      Q->>Q: retry theo chính sách tác vụ nền
    end
```

### 5.2 Processing Steps

**Step 1 — Authenticate** — verify token, lấy `uid`.

**Step 2 — Record and enqueue** — cập nhật `last_logout_at`, ghi `AuthEvent(logout, success)` và enqueue tác vụ revoke bền vững với `uid`/`trace_id`. Nếu không thể ghi nhận hoặc enqueue, trả lỗi; client vẫn xóa phiên cục bộ theo EF-104.

**Step 3 — Background revoke** — worker gọi `auth.revoke_refresh_tokens(uid)`, retry lỗi tạm thời và ghi `AuthEvent(session_revoked, success)` hoặc `AuthEvent(session_revoke_failed, failed)`. Nếu không tìm thấy `vehicle_user`, vẫn cho phép xếp hàng revoke theo UID đã xác minh; bỏ qua cập nhật hồ sơ nhưng vẫn ghi audit phù hợp.

**Step 4 — Response** — trả `204 No Content` sau khi API đã ghi nhận audit và tác vụ revoke được nhận bền vững. Đây không phải xác nhận Firebase đã hoàn tất revoke.

## 6. Database / Entity Interaction

### 6.1 Entities Used

| Entity / Table | Operation | Purpose |
| --- | --- | --- |
| `vehicle_user` | Read / Update | Tìm theo `firebase_uid`, cập nhật `last_logout_at` |
| `auth_event` | Insert | Ghi yêu cầu logout và kết quả worker revoke |

### 6.2 Write Data

```sql
UPDATE vehicle_user SET last_logout_at = now(), updated_at = now()
WHERE firebase_uid = :uid;

INSERT INTO auth_event (id, user_id, event_type, result, auth_provider, trace_id, created_at)
VALUES (:id, :user_id, 'logout', 'success', 'google.com', :trace_id, now());
```

### 6.3 Database Transaction

Cập nhật `last_logout_at`, insert `AuthEvent(logout)` và ghi tác vụ vào hàng đợi bền vững theo một transaction/outbox tương đương. Trả `204` chỉ sau khi tác vụ đã được nhận bền vững. Worker revoke Firebase ngoài transaction và ghi kết quả audit; nếu Firebase lỗi, retry theo chính sách tác vụ nền.

## 7. Business Logic

### Rule 1 — Đăng xuất thu hồi nền (BR-105)

Sau khi worker hoàn tất `revoke_refresh_tokens`, refresh token hiện có không thể dùng để lấy ID token mới → lần sau buộc đăng nhập lại. `204` chỉ xác nhận tác vụ đã được nhận.

### Rule 2 — Phạm vi thu hồi

`revoke_refresh_tokens(uid)` của Firebase thu hồi **toàn bộ** refresh token của UID (mọi thiết bị). MVP không cung cấp giao diện/quản lý thiết bị riêng; một lần logout có thể làm các thiết bị khác phải đăng nhập lại. Thu hồi từng thiết bị cần quản lý session riêng và nằm ngoài scope.

### Rule 3 — ID token còn hạn sau khi revoke

ID token đã cấp có thể còn hợp lệ tới `exp` (thường khoảng 1 giờ). `/profile` xác minh `check_revoked=True`; các endpoint được bảo vệ khác chỉ xác minh chữ ký/hạn và có thể chấp nhận token đó đến khi hết hạn. Client xóa token cục bộ ngay khi logout.

## 8. Error Handling

## 8.1 Error Response Standard

Xem C.3.

## 8.2 Error Cases

| Case | Error Code | HTTP Status |
| --- | --- | ---: |
| Thiếu header Authorization | `UNAUTHORIZED` | `401` |
| Token không hợp lệ / hết hạn | `INVALID_TOKEN` | `401` |
| Không thể xác minh token hoặc xếp hàng yêu cầu logout | `AUTH_PROVIDER_UNAVAILABLE` | `503` |
| Lỗi hệ thống | `INTERNAL_SERVER_ERROR` | `500` |

## 9. HTTP Status Codes

| HTTP Status | When |
| ---: | --- |
| `204 No Content` | Yêu cầu logout đã được ghi audit và xếp hàng revoke bền vững; Firebase revoke chạy nền |
| `401` | Chưa xác thực / token không hợp lệ |
| `503` | Không thể xác minh token hoặc ghi nhận/xếp hàng tác vụ logout (client vẫn xoá phiên cục bộ) |
| `500` | Lỗi hệ thống |

## 10. Response

### 10.1 Success Response

```http
204 No Content
```

Không có response body.

## 11. Response Fields

Không có (204). Kết quả thể hiện qua HTTP status.

## 12. Error Response Examples

```http
401 Unauthorized
```

```json
{
  "error": {
    "code": "INVALID_TOKEN",
    "message": "Token không hợp lệ hoặc đã hết hạn.",
    "details": null,
    "traceId": "req-7a8b9c"
  }
}
```

```http
503 Service Unavailable
```

```json
{
  "error": {
    "code": "AUTH_PROVIDER_UNAVAILABLE",
    "message": "Không thể thu hồi phiên lúc này. Vui lòng thử lại; phiên trên thiết bị đã được đăng xuất.",
    "details": null,
    "traceId": "req-7a8b9d"
  }
}
```

## 13. Idempotency

```text
Required: No (idempotent tự nhiên)
```

Gọi logout nhiều lần với cùng uid đều có thể enqueue revoke; revoke phía Firebase idempotent. Mỗi request hợp lệ trả `204` sau khi tác vụ tương ứng được nhận. Nếu token đã hết hạn/không hợp lệ ở lần gọi sau → `401`, client vẫn xóa phiên cục bộ.

## 14. Concurrency / Race Condition

Nhiều request logout đồng thời cho cùng uid: `revoke_refresh_tokens` idempotent; cập nhật `last_logout_at` là ghi đè mốc mới nhất — không xung đột.

## 15. External Dependencies

| Service | Purpose | Required |
| --- | --- | ---: |
| Firebase Admin SDK | Verify token; worker thu hồi refresh token | Yes |
| Supabase Postgres | Ghi `last_logout_at` + `AuthEvent` | Yes |
| Durable background queue | Tiếp nhận và retry tác vụ revoke | Yes |

## 16. Observability

- Log: `traceId`, `firebaseUid`, `userId`, kết quả revoke, latency. **Không** log token.
- Metric: `logout_total{result}`, `logout_revoke_errors_total`.

## 17. Performance Requirements

| Metric | Target |
| --- | --- |
| P95 latency | `< 800 ms` (gồm 1 lời gọi Firebase revoke) |

## 18. Retry & Timeout

Firebase revoke timeout `5s`. Client có thể retry khi `503`. Không retry trong request.

## 19. Versioning

`/api/v1/oauth/logout`

## 20. Example Request

```http
POST /api/v1/oauth/logout
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6Ij...
X-Request-ID: req-7a8b9c
```

## 21. Example Success Response

```http
HTTP/1.1 204 No Content
```

## 22. Example Error Response

Xem §12.

---

# API-102 — Profile / Session check (tham chiếu)

`GET /api/v1/oauth/profile` (endpoint hiện có) trả `uid`, `email` từ token đã verify bằng `check_revoked=True`. Dùng như **session check**: nếu trả `200` thì token chưa bị revoke; nếu `401` (kể cả `TOKEN_REVOKED`) thì client điều hướng về Login (BR-106, US-008).

Đây là endpoint duy nhất dùng `check_revoked=True`. Mọi endpoint được bảo vệ khác vẫn bắt buộc xác thực ID token nhưng không kiểm tra revoke tức thời.

---

# 23. Change Log

| Version | Date | Author | Changes |
| --- | --- | --- | --- |
| `v1.0` | `2026-09-27` | `[Cần điền]` | Bản nháp: đặc tả logout (API-101), tham chiếu login (API-001) & session check (API-102) |

---

# 24. Decisions

| ID | Decision | Resolution |
|---|---|---|
| `Q-101` | Có ghi audit logout không? | Có; ghi `last_logout_at` và `AuthEvent`. |
| `Q-102` | Endpoint nào kiểm tra revoke tức thời? | Chỉ `/profile`; mọi endpoint được bảo vệ vẫn xác thực token. |
| `Q-103` | Logout chờ Firebase revoke hay chạy nền? | Chạy nền; trả `204` sau khi yêu cầu được ghi nhận và enqueue bền vững. |
| `Q-104` | Có quản lý phiên/thiết bị riêng không? | Không; Firebase revoke theo UID vốn áp dụng mọi thiết bị. |

---

# 25. References

* Functional Spec: [us-005-sprint-1-spec.ff.md](../feature-functional/us-005-sprint-1-spec.ff.md)
* Entity Spec: [us-005-sprint-1-spec.entity.md](../entity/us-005-sprint-1-spec.entity.md)
* Login endpoint (API-001): [us-001-sprint-1-spec.api.md](./us-001-sprint-1-spec.api.md)
* Code hiện có: `backend/src/modules/oauth/` (`verify_firebase_token`, `GET /oauth/profile`)
