# Đặc tả kỹ thuật: Xác thực M2M (Machine-to-Machine) giữa EV Care Backend và Hệ thống Hãng xe (mock-ev-system)

> **Mã tài liệu:** `SPEC-SEC-OEM-M2M-001`  
> **Phiên bản:** `v2.0`  
> **Trạng thái:** `Approved`  
> **Ngày phê duyệt:** `2026-10-12`  
> **Áp dụng cho:** `EV Care Backend` (`src/`) · `mock-ev-system` (`backend/mock-ev-system/`) · `Shared Contracts` (`backend/shared/ev-contracts/`)

## Lịch sử thay đổi

| Phiên bản | Ngày | Thay đổi |
|---|---|---|
| v1.0 | 2026-10-12 | Backend tự ký JWT cho **mỗi** request gửi sang OEM; OEM tự ký JWT cho mỗi webhook. |
| v2.0 | 2026-10-12 | Chiều Backend → OEM chuyển sang **OAuth2 client_credentials + `private_key_jwt`** (RFC 7523 §2.2): Backend đổi *client assertion* lấy *access token phiên* do OEM ký, cache trên Redis và dùng lại. Thêm phân loại token qua `typ`, chống replay assertion bằng `jti`, ràng buộc body vào JWT webhook (`body_sha256`), chuẩn hóa leeway 60s và mã lỗi. |

---

## 1. Bối cảnh & Mục tiêu

### 1.1. Hiện trạng (v1.0)
- **Backend → OEM:** Backend tự ký một JWT ngắn hạn cho từng request. OEM chỉ kiểm tra chữ ký, không phát hành token và không kiểm soát được thời gian phiên.
- **OEM → Backend (Webhook):** OEM tự ký JWT cho từng webhook, nhưng JWT không gắn với body nên token bị lộ có thể dùng lại với body tùy ý.
- `jti` có trong token nhưng không bên nào kiểm tra.

### 1.2. Mục tiêu v2.0
1. **Zero Shared Secret:** Mỗi bên giữ Private Key của mình, chỉ trao đổi Public Key.
2. **Phiên do OEM cấp:** Backend chứng minh danh tính một lần ở token endpoint, OEM ký và trả về **access token phiên**. Backend cũng kiểm tra chữ ký của OEM trên token đó → hai bên đều chứng minh danh tính trong lúc thiết lập phiên.
3. **Dùng lại token:** Access token được cache trên Redis, dùng chung giữa API và Celery worker, tự làm mới trước khi hết hạn.
4. **Không nhầm lẫn token:** Mỗi loại token có `typ`/`aud` riêng, bên nhận từ chối loại không đúng.
5. **Chống replay & tampering:** Assertion dùng một lần (`jti`), webhook JWT gắn với hash của body.
6. **Tương thích dev/test:** Khi chưa cấu hình key, cả hai bên chạy được như trước (không xác thực).

---

## 2. Mô hình Khóa & Thuật toán

### 2.1. Cặp khóa của 2 hệ thống

```
+------------------------------------------------------------------+
|                        EV Care Backend                           |
|  EVCARE_PRIVATE_KEY  ký client assertion gửi sang OEM            |
|  OEM_PUBLIC_KEY      verify access token do OEM cấp + webhook JWT|
+------------------------------------------------------------------+
                         ↕ (HTTP / M2M)
+------------------------------------------------------------------+
|                    Hệ thống hãng (mock-ev-system)                |
|  MOCK_PRIVATE_KEY    ký access token phiên + webhook JWT         |
|                      (public key suy ra từ private key này để    |
|                       tự verify access token của chính mình)     |
|  EVCARE_PUBLIC_KEY   verify client assertion của EV Care         |
+------------------------------------------------------------------+
```

`OEM_PUBLIC_KEY` (phía backend) là public key tương ứng với `MOCK_PRIVATE_KEY` (phía mock).

### 2.2. Thuật toán
- **Ed25519 (EdDSA)** — mặc định khuyến nghị. Khóa PEM PKCS#8 (`BEGIN PRIVATE KEY`) / SubjectPublicKeyInfo (`BEGIN PUBLIC KEY`).
- **RS256** — hỗ trợ RSA 2048/4096-bit.
- Thuật toán được xác định từ **kiểu khóa sau khi load**, không dò chuỗi trong PEM.
- Sinh khóa: `ev_contracts.generate_key_pair("Ed25519")`.

---

## 3. Các loại token

Mọi token là JWT ký bất đối xứng, gửi trong `Authorization: Bearer <token>` (riêng assertion gửi trong form body).

| Loại | Người ký | `typ` (header) | `iss` | `sub` | `aud` | TTL | Dùng ở |
|---|---|---|---|---|---|---|---|
| **Client assertion** | EV Care (`EVCARE_PRIVATE_KEY`) | `JWT` | `ev-care-backend` | `ev-care-backend` | `mock-ev-system` | 60s | `POST /oauth/token` |
| **Access token (phiên)** | OEM (`MOCK_PRIVATE_KEY`) | `at+jwt` (RFC 9068) | `mock-ev-system` | `ev-care-backend` | `mock-ev-system` | 900s (cấu hình) | Mọi API nghiệp vụ của OEM |
| **Webhook token** | OEM (`MOCK_PRIVATE_KEY`) | `JWT` | `mock-ev-system` | — | `ev-care-backend` | 180s | `POST /api/v1/integrations/oem/webhooks` |

Claim bắt buộc chung: `iss`, `aud`, `iat`, `exp`, `jti` (UUIDv4).  
Claim riêng: assertion có `sub`; access token có `sub` và `client_id`; webhook token có `body_sha256` (hex SHA-256 của raw body).

**Quy tắc phân loại (bắt buộc):**
- API nghiệp vụ của OEM chỉ nhận `typ=at+jwt`. Gửi assertion hay webhook token vào đây → `401 M2M_TOKEN_TYPE_INVALID`.
- Token endpoint và webhook receiver chỉ nhận `typ=JWT`. Gửi access token vào đây → bị từ chối.
- Access token và webhook token cùng do `MOCK_PRIVATE_KEY` ký nhưng khác `aud` và `typ`, nên không thể dùng thay cho nhau.

**Clock skew:** mọi bên kiểm tra `exp`/`iat` với leeway **60 giây**.

---

## 4. Luồng xử lý

### 4.1. Chiều 1: EV Care Backend gọi API OEM

Áp dụng cho mọi route nghiệp vụ của mock: `/vehicles/**`, `/owners/**`, `/service-centers/**`, `/models/**`, `/warranty*`, `/maintenance*`, usage. Không áp dụng cho `/health`, `/oauth/token`, `/admin/**` (dùng `X-Admin-Token`), `/webhooks/**` (công cụ test của mock).

#### Pha A — Lấy access token phiên

```mermaid
sequenceDiagram
    autonumber
    participant GW as EV Care Gateway
    participant R as Redis
    participant OEM as mock-ev-system

    GW->>R: GET {prefix}:oem:m2m:access_token
    alt Có trong cache
        R-->>GW: access_token
    else Không có (miss)
        GW->>R: SET {prefix}:oem:m2m:access_token:lock <rand> NX EX 10
        alt Giành được lock
            GW->>R: GET lại (double-check)
            GW->>GW: Ký client assertion bằng EVCARE_PRIVATE_KEY<br/>(typ=JWT, iss=sub=ev-care-backend, aud=mock-ev-system, exp=+60s, jti)
            GW->>OEM: POST /oauth/token (form-urlencoded)<br/>grant_type=client_credentials<br/>client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer<br/>client_assertion=<assertion>
            OEM->>OEM: Verify assertion bằng EVCARE_PUBLIC_KEY<br/>(chữ ký, typ, iss, sub, aud, exp, jti chưa dùng)
            OEM->>OEM: Ghi nhận jti đến khi assertion hết hạn
            OEM->>OEM: Ký access token bằng MOCK_PRIVATE_KEY<br/>(typ=at+jwt, iss=mock-ev-system, sub=ev-care-backend, aud=mock-ev-system, exp=+900s)
            OEM-->>GW: 200 {access_token, token_type: "Bearer", expires_in: 900}
            GW->>GW: Verify access token bằng OEM_PUBLIC_KEY<br/>(chữ ký, typ, iss, sub, aud, exp)
            GW->>R: SET access_token EX (expires_in − 60)
            GW->>R: Xóa lock (chỉ khi còn là lock của mình)
        else Không giành được lock
            GW->>R: Chờ và đọc lại cache (tối đa ~timeout + 2s)
            Note over GW: Hết thời gian chờ → tự lấy token (không lock)
        end
    end
```

#### Pha B — Gọi API nghiệp vụ

```mermaid
sequenceDiagram
    autonumber
    participant GW as EV Care Gateway
    participant R as Redis
    participant OEM as mock-ev-system

    GW->>OEM: GET /vehicles/{id}/usage<br/>Authorization: Bearer <access_token>
    OEM->>OEM: Verify bằng public key của chính mình (từ MOCK_PRIVATE_KEY)<br/>typ=at+jwt, iss, aud, sub, exp (leeway 60s)
    alt Hợp lệ
        OEM-->>GW: 200 dữ liệu
    else Không hợp lệ / hết hạn
        OEM-->>GW: 401 {"detail": {"code": "M2M_TOKEN_EXPIRED", ...}}
        GW->>R: Xóa cache (chỉ khi giá trị đang là token vừa bị từ chối)
        GW->>GW: Lấy token mới (Pha A)
        GW->>OEM: Retry đúng 1 lần
    end
```

**Ghi chú thiết kế:**
- Access token là **Bearer**: OEM chỉ chứng minh được token do chính mình cấp và còn hạn, không chứng minh ai đang cầm. Danh tính EV Care được chứng minh ở Pha A. Bảo vệ token dựa vào TTL ngắn và HTTPS cho `OEM_API_BASE_URL` khi deploy. Không dùng DPoP (RFC 9449) ở phiên bản này.
- OEM **không lưu phiên**: verify access token là stateless.
- **TTL cache = `expires_in` − 60s** (biên an toàn), lấy `expires_in` từ response, giới hạn thêm bởi `exp − iat` của token. TTL cache luôn **nhỏ hơn** thời hạn token để cache không bao giờ trả token đã hết hạn. Nếu kết quả ≤ 0 thì không cache.
- Redis dùng chung giữa API và Celery worker nên cả hệ thống chỉ xin token khi cache hết hạn; lock tránh việc nhiều worker cùng xin token một lúc (ví dụ khi `oem.sync_all_vehicles` sinh hàng loạt task).
- Token là credential: **không ghi token vào log/trace**.

### 4.2. Chiều 2: OEM gửi Webhook sang EV Care Backend

Áp dụng cho endpoint: `POST /api/v1/integrations/oem/webhooks`. Chiều này giữ mô hình token tự ký cho từng request (không có token endpoint phía backend).

```mermaid
sequenceDiagram
    autonumber
    participant OEM as mock-ev-system (Webhooks)
    participant App as EV Care Backend (OemWebhookService)

    OEM->>OEM: Tạo body, tính body_sha256
    OEM->>OEM: Ký webhook token bằng MOCK_PRIVATE_KEY<br/>(typ=JWT, iss=mock-ev-system, aud=ev-care-backend, exp=+180s, body_sha256)
    OEM->>App: POST /api/v1/integrations/oem/webhooks<br/>Authorization: Bearer webhook_token<br/>X-OEM-Event-Id, X-OEM-Timestamp<br/>X-OEM-Signature: sha256=hmac_hex (khi có MOCK_WEBHOOK_SECRET)
    App->>App: Verify bằng OEM_PUBLIC_KEY (chữ ký, typ, iss, aud, exp, leeway 60s)
    App->>App: So body_sha256 với SHA-256 của raw body
    alt Hợp lệ
        App->>App: Dedupe event-id, debounce Redis, enqueue Celery sync
        App-->>OEM: 202 Accepted
    else Không hợp lệ
        App-->>OEM: 401 WEBHOOK_SIGNATURE_INVALID
    end
```

Chế độ `OEM_AUTH_MODE` của backend:
- `jwt`: chỉ nhận webhook token hợp lệ (kể cả `body_sha256`).
- `hmac`: chỉ nhận HMAC cũ.
- `both` (mặc định): JWT hợp lệ thì nhận; nếu không thì thử HMAC.

---

## 5. Token endpoint của OEM

`POST /oauth/token` — `Content-Type: application/x-www-form-urlencoded`

| Tham số | Bắt buộc | Giá trị |
|---|:---:|---|
| `grant_type` | Có | `client_credentials` |
| `client_assertion_type` | Có | `urn:ietf:params:oauth:client-assertion-type:jwt-bearer` |
| `client_assertion` | Có | Client assertion đã ký |
| `client_id` | Không | Nếu có phải bằng `iss` của assertion |

**200 OK** (header `Cache-Control: no-store`):
```json
{ "access_token": "<jwt>", "token_type": "Bearer", "expires_in": 900 }
```

**Lỗi** (định dạng RFC 6749 §5.2):
| HTTP | `error` | Khi nào |
|---|---|---|
| 400 | `unsupported_grant_type` | `grant_type` khác `client_credentials` |
| 400 | `invalid_request` | Thiếu tham số / sai `client_assertion_type` |
| 401 | `invalid_client` | Assertion sai chữ ký, hết hạn, sai `typ`/`iss`/`sub`/`aud`, `jti` đã dùng, `client_id` không khớp |
| 503 | `server_error` | Mock chưa cấu hình `EVCARE_PUBLIC_KEY` hoặc `MOCK_PRIVATE_KEY` |

---

## 6. Mã lỗi xác thực API (401)

API nghiệp vụ của OEM trả `401` với header `WWW-Authenticate: Bearer` và body:
```json
{ "detail": { "code": "M2M_TOKEN_EXPIRED", "message": "..." } }
```

| `code` | Nguyên nhân | Xử lý phía gọi |
|---|---|---|
| `M2M_TOKEN_MISSING` | Thiếu `Authorization: Bearer`. | Gắn access token. |
| `M2M_TOKEN_EXPIRED` | `exp` đã qua (quá leeway 60s). | Xóa cache, lấy token mới, retry 1 lần. |
| `M2M_SIGNATURE_INVALID` | Chữ ký sai / token hỏng. | Kiểm tra cặp key; lấy token mới. |
| `M2M_TOKEN_TYPE_INVALID` | `typ` không phải `at+jwt`. | Không dùng assertion/webhook token làm access token. |
| `M2M_AUDIENCE_MISMATCH` | `aud` sai. | — |
| `M2M_ISSUER_MISMATCH` | `iss` sai. | — |
| `M2M_SUBJECT_MISMATCH` | `sub` không phải client được phép. | — |
| `M2M_CONFIG_ERROR` | Mock bật xác thực nhưng thiếu `MOCK_PRIVATE_KEY`. | Cấu hình mock. |

Phía backend: nếu sau khi làm mới token vẫn bị 401, hoặc không lấy được token, gateway ghi log mức `ERROR` (phân biệt với lỗi mạng) rồi báo lỗi như OEM không khả dụng để luồng nghiệp vụ xử lý theo cơ chế pending/retry sẵn có.

---

## 7. Cấu hình môi trường

### 7.1. EV Care Backend (`.env`)
```ini
# Private key của EV Care: ký client assertion. Để trống = không xác thực (dev/test).
EVCARE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
# Public key của OEM (cặp với MOCK_PRIVATE_KEY): verify access token + webhook JWT.
# Bắt buộc khi đã đặt EVCARE_PRIVATE_KEY.
OEM_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
# Chế độ xác thực webhook: both | jwt | hmac
OEM_AUTH_MODE=both
# Làm mới access token trước khi hết hạn bao nhiêu giây (TTL cache = expires_in - giá trị này)
OEM_ACCESS_TOKEN_REFRESH_MARGIN_SECONDS=60
```

### 7.2. mock-ev-system
```ini
# Private key của OEM: ký access token + webhook JWT.
MOCK_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
# Public key của EV Care (cặp với EVCARE_PRIVATE_KEY): verify client assertion.
EVCARE_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
# Thời hạn access token (giây)
MOCK_ACCESS_TOKEN_TTL_SECONDS=900
# true: luôn bắt buộc xác thực. false/unset: bắt buộc khi đã có EVCARE_PUBLIC_KEY, bypass khi chưa có.
MOCK_AUTH_REQUIRED=false
```

---

## 8. Triển khai

1. **`ev_contracts.auth`** (thư viện dùng chung):
   - `generate_key_pair`, `public_key_from_private`, `clean_pem`, `detect_algorithm`
   - `create_m2m_token` / `verify_m2m_token` — token tự ký `typ=JWT` (webhook), hỗ trợ `extra_claims` và kiểm tra `typ`
   - `create_client_assertion` / `verify_client_assertion`
   - `create_access_token` / `verify_access_token` (`typ=at+jwt`)
   - Hằng số: `EVCARE_CLIENT_ID`, `OEM_ISSUER`, `OAUTH_TOKEN_PATH`, `CLIENT_ASSERTION_TYPE`, `ACCESS_TOKEN_TYPE`, `M2M_CLOCK_SKEW_SECONDS`
   - Mỗi lỗi `M2MAuthError` có thuộc tính `code` theo bảng §6.
2. **mock-ev-system:**
   - `routers/oauth.py`: `POST /oauth/token`; lưu `jti` assertion trong bộ nhớ đến khi hết hạn (mock chạy 1 tiến trình; nhiều instance thì cần store dùng chung).
   - `auth.py`: dependency `require_access_token` bảo vệ các router nghiệp vụ.
   - `webhooks.py`: thêm `body_sha256` vào webhook token.
3. **EV Care Backend:**
   - `src/infrastructure/oem/auth.py`: `OemAccessTokenProvider` (Redis cache + lock + verify access token + invalidate).
   - `src/infrastructure/oem/gateway.py`: `OemHttpClient` gắn token, retry 1 lần khi 401; các gateway dựng bằng `from_settings(settings)`.
   - `OemWebhookService`: kiểm tra `body_sha256`, leeway 60s.
   - Script `seed_multi_vehicle_owner.py`, `smoke_live_integration.py` gọi OEM qua `OemHttpClient`.

### Tương thích ngược
- Backend không có `EVCARE_PRIVATE_KEY` → không gửi `Authorization`.
- Mock không có `EVCARE_PUBLIC_KEY` và `MOCK_AUTH_REQUIRED` ≠ true → không kiểm tra token trên API nghiệp vụ.
- Token tự ký kiểu v1.0 gửi thẳng vào API nghiệp vụ bị từ chối (`M2M_TOKEN_TYPE_INVALID`) → backend và mock phải nâng cấp cùng lúc.
