# API Technical Specification — Đăng nhập & Đăng xuất (Chủ xưởng) kèm ghi log

> Đặc tả API cho Feature `FEAT-AUTH-004` (US-013 → US-016).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-013-sprint-1-spec.ff.md) · **Entity:** [Entity Spec](../entity/us-013-sprint-1-spec.entity.md)
>
> **Quan hệ:** Đăng nhập **tái sử dụng** `POST /api/v1/workshop-owner/oauth/sign-in` (API-201, [us-009 API](./us-009-sprint-1-spec.api.md)) và **bổ sung ghi log**. Tài liệu này đặc tả mới **API-301 Logout** và **API-302 Session check**. Envelope, mã lỗi chung theo [us-009 API C.3/C.6](./us-009-sprint-1-spec.api.md).

---

# 0. Document Information

| Field | Value |
| --- | --- |
| Document ID | `API-SPEC-AUTH-004` |
| Feature | `FEAT-AUTH-004` |
| Version | `v1.0` |
| Status | `Review` |
| Sprint | `Sprint 1` |
| Base URL | `/api/v1` |
| Created Date | `2026-09-27` |

## 0.1 API Catalog

| API ID | Method | Endpoint | Mục đích | FF | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| `API-201` | `POST` | `/api/v1/workshop-owner/oauth/sign-in` | Đăng nhập / đồng bộ tài khoản; **ghi log** `login` / `login_denied` | US-013, AC-301→AC-303 | **Tái sử dụng + bổ sung log** |
| `API-301` | `POST` | `/api/v1/workshop-owner/oauth/logout` | Đăng xuất: ghi `last_logout_at` + log, xếp hàng thu hồi | US-014, AC-304, AC-305 | **Mới** |
| `API-302` | `GET` | `/api/v1/workshop-owner/oauth/session` | Kiểm tra phiên (có kiểm tra revoke) + trạng thái tài khoản | US-015, AC-306 | **Mới** |

## 0.2 Sequence

```mermaid
sequenceDiagram
    autonumber
    actor O as Chủ xưởng (Portal)
    participant FB as Firebase
    participant API as Backend
    participant DB
    participant Q as Worker

    O->>API: GET /workshop-owner/oauth/session (mở lại portal)
    API->>FB: verify_id_token(check_revoked=True)
    API-->>O: 200 session / 401 TOKEN_REVOKED
    O->>API: POST /workshop-owner/oauth/sign-in
    API->>DB: last_login_at + log login (hoặc log login_denied)
    API-->>O: 200 nextStep
    O->>API: POST /workshop-owner/oauth/logout
    API->>DB: last_logout_at + log logout
    API->>Q: enqueue workshop_auth.revoke_session(uid, ownerId)
    API-->>O: 204
    Q->>FB: revoke_refresh_tokens(uid)
    Q->>DB: log session_revoked | session_revoke_failed
```

## 0.3 Error Codes (bổ sung)

| Error Code | HTTP | API | Description | FF |
| --- | ---: | --- | --- | --- |
| `UNAUTHORIZED` / `INVALID_TOKEN` | `401` | All | Thiếu / sai / hết hạn token | EF-304 |
| `TOKEN_REVOKED` | `401` | 302 | Refresh token đã bị thu hồi | AC-306 |
| `ACCOUNT_SUSPENDED` / `ACCOUNT_INACTIVE` | `403` | 201, 302 | Tài khoản bị khoá | EF-302 |
| `WORKSHOP_OWNER_NOT_REGISTERED` | `404` | 302 | Chưa có tài khoản chủ xưởng | AF-303 |
| `AUTH_PROVIDER_UNAVAILABLE` | `503` | 301, 302 | Không xác minh được token / không xếp hàng được thu hồi | EF-303 |

---

# LOGIN — API-201 (bổ sung ghi log)

Request/response/validation giữ nguyên [us-009 API-201](./us-009-sprint-1-spec.api.md). Bổ sung:

| Tình huống | Kết quả API-201 | Log (ENT-301) |
| --- | --- | --- |
| Tạo tài khoản mới | `201` | `login / success` |
| Tài khoản đã có, không khoá | `200`, cập nhật `last_login_at` | `login / success` |
| Tài khoản bị khoá | `403 ACCOUNT_SUSPENDED / ACCOUNT_INACTIVE` | `login_denied / denied`, `reason = account_suspended / account_inactive` |
| Provider sai / email chưa xác minh / email đã liên kết UID khác | `403` / `409` | Không ghi (chưa có tài khoản) |

- Log ghi **cùng transaction** với cập nhật `last_login_at` (BR-ENT-303); với tài khoản bị khoá, log được commit trước khi trả `403`.
- Thông tin ghi: `ip_address` (IP client), `user_agent` (header `User-Agent`), `trace_id` (`X-Request-ID`), `auth_provider`.
- **Auto-login (US-015):** portal gọi API-302 trước; hợp lệ thì gọi API-201 để lấy `nextStep` (ghi thêm một log `login`).

---

# API-301 — Logout

## 1. Overview

### 1.1 API Name

`Workshop Owner Logout`

### 1.2 Purpose

Ghi `last_logout_at`, ghi log `logout`, xếp hàng tác vụ thu hồi refresh token của UID. Trả `204` khi yêu cầu đã được nhận; worker thu hồi và ghi log kết quả. Portal tự xoá token cục bộ (`signOut()`).

### 1.3 Endpoint

```http
POST /api/v1/workshop-owner/oauth/logout
```

### 1.4 HTTP Method

| Property | Value |
| --- | --- |
| Method | `POST` |
| Authentication | Required (Firebase ID token, chỉ chữ ký + hạn) |
| Authorization | Chỉ đăng xuất phiên của chính UID trong token |

### 1.5 Scope

**In:** `last_logout_at`, log `logout`, enqueue `workshop_auth.revoke_session`. **Out:** xoá phiên client; quản lý thiết bị.

## 2. Authentication & Authorization

- Không dùng `check_revoked` (token đầu vào thuộc phiên đang cần kết thúc).
- **Không** kiểm tra `status`: tài khoản bị khoá vẫn đăng xuất được (BR-304).
- Không nhận `ownerId` / `uid` từ body.

## 3. Request

| Header | Required | Description |
| --- | ---: | --- |
| `Authorization` | Yes | `Bearer <firebase_id_token>` |
| `X-Request-ID` | No | Trace id |
| `User-Agent` | No | Ghi vào log |

Không có body.

## 4. Request Validation

| Validation | Error |
| --- | --- |
| Thiếu header | `401 UNAUTHORIZED` |
| Token sai / hết hạn | `401 INVALID_TOKEN` |

## 5. Internal Processing

```mermaid
sequenceDiagram
    participant Client
    participant API as WorkshopAuth Route
    participant Svc as WorkshopAuthService
    participant DB
    participant Q as Celery

    Client->>API: POST /workshop-owner/oauth/logout
    API->>Svc: logout(claims, ip, ua, trace)
    Svc->>DB: SELECT workshop_owner WHERE firebase_uid
    opt Có tài khoản
        Svc->>DB: last_logout_at = now(), INSERT log(logout, success)
    end
    Svc->>Q: enqueue workshop_auth.revoke_session(uid, ownerId, trace)
    alt Enqueue OK
        Svc->>DB: COMMIT
        API-->>Client: 204
    else Broker lỗi
        Svc->>DB: ROLLBACK
        API-->>Client: 503 AUTH_PROVIDER_UNAVAILABLE
    end
```

1. Verify token, lấy `uid`.
2. Tìm `workshop_owner` theo `firebase_uid`. Có ⇒ cập nhật `last_logout_at`, thêm log `logout / success`. Không có ⇒ bỏ qua ghi DB (EDGE-304).
3. Enqueue `workshop_auth.revoke_session(uid, owner_id | null, trace_id)`.
4. Enqueue OK ⇒ `COMMIT`, trả `204`. Lỗi ⇒ `ROLLBACK`, `503`.

### 5.1 Background — `workshop_auth.revoke_session`

| Property | Value |
| --- | --- |
| Runner | Celery (`src/infrastructure/celery/tasks/workshop_auth_tasks.py`) |
| Gọi | `firebase_admin.auth.revoke_refresh_tokens(uid)` |
| Thành công | Log `session_revoked / success` (nếu có `owner_id`) |
| Lỗi | Log `session_revoke_failed / failed` (`reason` = tên exception), retry tối đa 5 lần, cách 10s |
| Phạm vi | Toàn bộ refresh token của UID — kể cả phiên app chủ xe nếu cùng Gmail (BR-306) |

## 6. Database / Entity Interaction

| Entity / Table | Operation | Purpose |
| --- | --- | --- |
| `workshop_owner` | Read / Update | `last_logout_at` |
| `workshop_owner_auth_event` | Insert | Log `logout` (API), kết quả thu hồi (worker) |

```sql
UPDATE workshop_owner SET last_logout_at = now(), updated_at = now() WHERE firebase_uid = :uid;
INSERT INTO workshop_owner_auth_event (id, owner_id, event_type, result, auth_provider,
                                       ip_address, user_agent, trace_id)
VALUES (:id, :ownerId, 'logout', 'success', 'google.com', :ip, :ua, :traceId);
```

## 7. Business Logic

| Rule | Nội dung |
| --- | --- |
| BR-304 | `204` chỉ xác nhận yêu cầu đã được nhận, không phải Firebase đã thu hồi xong |
| BR-305 | Log `logout` ghi cùng transaction với `last_logout_at`, commit sau khi enqueue |
| BR-306 | Thu hồi theo UID ảnh hưởng mọi app dùng cùng Gmail |
| ID token còn hạn | Token đã cấp vẫn hợp lệ tới `exp` với các endpoint không kiểm tra revoke; API-302 phát hiện ngay |

## 8. Error Handling

| Case | Error Code | HTTP |
| --- | --- | ---: |
| Thiếu / sai token | `UNAUTHORIZED` / `INVALID_TOKEN` | `401` |
| Không ghi nhận / xếp hàng được | `AUTH_PROVIDER_UNAVAILABLE` | `503` |

## 9. HTTP Status Codes

`204 No Content` · `401` · `503`.

## 10–11. Response

```http
204 No Content
```

Không có body.

## 12. Error Response Examples

```json
{
  "error": {
    "code": "AUTH_PROVIDER_UNAVAILABLE",
    "message": "Không thể thu hồi phiên lúc này. Vui lòng thử lại; phiên trên thiết bị đã được đăng xuất.",
    "details": null,
    "traceId": "req-w301b"
  }
}
```

## 13–19

Idempotent tự nhiên (mỗi lần gọi ghi thêm một log `logout`; revoke Firebase idempotent) · đồng thời: `last_logout_at` ghi đè mốc mới nhất · Firebase Admin, Postgres, Celery · P95 `< 300 ms` (không chờ Firebase) · không retry trong request · `/api/v1/workshop-owner/oauth/logout`.

## 20. Example Request

```http
POST /api/v1/workshop-owner/oauth/logout
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6Ij...
X-Request-ID: req-w301a
```

---

# API-302 — Session check

## 1. Overview

### 1.2 Purpose

Portal gọi khi mở lại / định kỳ để biết phiên còn hợp lệ không (kể cả đã bị thu hồi) và trạng thái tài khoản chủ xưởng. Endpoint **duy nhất** của portal dùng `check_revoked=True` (BR-307). Không ghi log.

### 1.3 Endpoint

```http
GET /api/v1/workshop-owner/oauth/session
```

| Property | Value |
| --- | --- |
| Method | `GET` |
| Authentication | Required — verify với `check_revoked=True` |
| Authorization | Chủ xưởng đã có tài khoản, không bị khoá |

## 4. Request Validation

| Validation | Error |
| --- | --- |
| Thiếu header | `401 UNAUTHORIZED` |
| Token sai / hết hạn | `401 INVALID_TOKEN` |
| Token đã bị thu hồi | `401 TOKEN_REVOKED` |
| Firebase không kiểm tra được revoke | `503 AUTH_PROVIDER_UNAVAILABLE` |
| Chưa có tài khoản chủ xưởng | `404 WORKSHOP_OWNER_NOT_REGISTERED` |
| Tài khoản bị khoá | `403 ACCOUNT_SUSPENDED / ACCOUNT_INACTIVE` |

## 5. Internal Processing

1. `auth.verify_id_token(token, check_revoked=True)`.
2. Tìm `workshop_owner` theo `uid`; kiểm tra `status`.
3. Trả trạng thái tài khoản + `WorkshopOnboardingState` (us-009 C.5). Không cập nhật DB, không ghi log.

## 6. Database / Entity Interaction

`workshop_owner` — Read.

## 10. Response

```http
200 OK
```

```json
{
  "data": {
    "ownerId": "3a7e9c10-2b4d-4f61-9a0e-5c8d7b6a1f20",
    "email": "ha.tran.sc01@gmail.com",
    "accountStatus": "ACTIVE",
    "onboarding": {
      "status": "ACTIVE",
      "nextStep": "DASHBOARD",
      "profileCompleted": true,
      "profileCompletedAt": "2026-09-27T03:02:00Z",
      "completedAt": "2026-09-27T03:06:12Z",
      "expiresAt": null
    },
    "lastLoginAt": "2026-09-27T08:00:00Z",
    "lastLogoutAt": "2026-09-26T17:40:00Z"
  }
}
```

## 11. Response Fields

| Field | Type | Nullable | Description |
| --- | --- | ---: | --- |
| `ownerId` | `uuid` | No | |
| `email` | `string` | No | |
| `accountStatus` | `AccountStatus` | No | Luôn `ACTIVE` khi `200` |
| `onboarding` | `WorkshopOnboardingState` | No | Điều hướng |
| `lastLoginAt`, `lastLogoutAt` | `datetime` | Yes | Mốc gần nhất |

## 12. Error Response Examples

```json
{
  "error": {
    "code": "TOKEN_REVOKED",
    "message": "Phiên đăng nhập đã bị thu hồi. Vui lòng đăng nhập lại.",
    "details": null,
    "traceId": "req-w302a"
  }
}
```

## 13–19

`GET` idempotent · Firebase Admin (revoke check), Postgres · P95 `< 800 ms` (gồm 1 lời gọi Firebase) · `/api/v1/workshop-owner/oauth/session`.

---

# 20. Background Jobs

| Task | Lịch | Việc |
| --- | --- | --- |
| `workshop_auth.revoke_session` | Theo yêu cầu (API-301) | Thu hồi refresh token, ghi log kết quả |
| `workshop_auth.purge_events` | Hằng ngày 02:30 | Xoá log > 60 ngày (`WORKSHOP_AUTH_EVENT_RETENTION_DAYS`) |

---

# 21. Change Log

| Version | Date | Author | Changes |
| --- | --- | --- | --- |
| `v1.0` | `2026-09-27` | `[Cần điền]` | Bổ sung log cho API-201; thêm API-301 logout, API-302 session check |

---

# 22. References

* Functional Spec: [us-013-sprint-1-spec.ff.md](../feature-functional/us-013-sprint-1-spec.ff.md)
* Entity Spec: [us-013-sprint-1-spec.entity.md](../entity/us-013-sprint-1-spec.entity.md)
* Onboarding chủ xưởng: [us-009-sprint-1-spec.api.md](./us-009-sprint-1-spec.api.md)
* Tương đương chủ xe: [us-005-sprint-1-spec.api.md](./us-005-sprint-1-spec.api.md)
