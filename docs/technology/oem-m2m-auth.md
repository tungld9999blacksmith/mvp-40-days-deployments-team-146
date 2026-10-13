# Xác thực M2M backend ↔ OEM

> Cập nhật: 2026-10-12. Đặc tả đầy đủ: [specs/mock-system/m2m_authentication_spec.md](../specs/mock-system/m2m_authentication_spec.md) (`SPEC-SEC-OEM-M2M-001` v2.0). Trang này là bản **hướng dẫn dùng và vận hành** cho dev.

## 1. Vấn đề và quyết định

| v1.0 (đã bỏ) | v2.0 (hiện tại) |
| --- | --- |
| Backend tự ký một JWT cho **mỗi** request gửi OEM; OEM chỉ kiểm chữ ký | Backend đổi *client assertion* lấy **access token do OEM cấp**, cache và dùng lại |
| JWT webhook không gắn với body → token bị bắt có thể gửi lại với body tùy ý | JWT webhook mang claim `body_sha256`, bên nhận so với hash của body thô |
| `jti` có trong token nhưng không ai kiểm | OEM chặn `jti` của assertion dùng lại |

Nguyên tắc: **không chia sẻ secret**. Mỗi bên giữ private key của mình, chỉ trao đổi public key.

## 2. Khóa và biến môi trường

| Biến | Bên giữ | Dùng để |
| --- | --- | --- |
| `EVCARE_PRIVATE_KEY` | backend + worker | Ký client assertion gửi OEM |
| `OEM_PUBLIC_KEY` | backend + worker | Verify access token do OEM cấp và JWT webhook (là public key của `MOCK_PRIVATE_KEY`) |
| `MOCK_PRIVATE_KEY` | mock-ev-system (OEM) | Ký access token và JWT webhook |
| `EVCARE_PUBLIC_KEY` | mock-ev-system (OEM) | Verify client assertion của EV Care |
| `OEM_AUTH_MODE` | backend | Cách nhận webhook: `hmac` / `jwt` / `both` (mặc định) |
| `OEM_ACCESS_TOKEN_REFRESH_MARGIN_SECONDS` | backend | Làm mới token sớm hơn hạn (mặc định 60) |
| `MOCK_AUTH_REQUIRED` | mock | Bắt buộc access token kể cả khi chưa có `EVCARE_PUBLIC_KEY` |
| `MOCK_ACCESS_TOKEN_TTL_SECONDS` | mock | Hạn access token (spec: 900 giây) |

- Thuật toán lấy từ **kiểu khóa sau khi load** (Ed25519 mặc định, RS256 cho RSA 2048/4096), PEM PKCS#8 / SubjectPublicKeyInfo.
- Khóa staging khác khóa local; không dùng chung giữa các môi trường. File `.railway.env` không commit.
- Chưa cấu hình khóa → hai bên chạy như trước (không xác thực) để dev/test không vướng.

## 3. Luồng

**Backend → OEM** (`infrastructure/oem/auth.py`, `gateway.py`):

1. `OemAccessTokenProvider.get_token()` đọc `{prefix}:oem:m2m:access_token` trong Redis (dùng chung API và Celery worker).
2. Miss → lấy lock `...:lock` (TTL 10 giây). Ai giành được lock thì ký assertion (`typ=JWT`, `iss=sub=ev-care-backend`, `aud=mock-ev-system`, `exp=+60s`, `jti`) và gọi `POST /oauth/token` (`grant_type=client_credentials`, `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer`). Người còn lại chờ cache.
3. Verify access token bằng `OEM_PUBLIC_KEY`, cache `expires_in − refresh margin`, nhả lock (chỉ khi còn là lock của mình).
4. Gateway gọi API nghiệp vụ với `Authorization: Bearer <access token>`. Gặp **401** thì xoá đúng token đó khỏi cache (compare-and-delete), xin token mới và gọi lại **một lần**; vẫn 401 thì `OemAuthError`.
5. Redis lỗi → cache bỏ qua, mỗi lời gọi tự xin token. Token không bao giờ được ghi log. Mỗi lời gọi mở client Redis riêng vì Celery chạy mỗi job trong event loop mới.

**OEM → backend (webhook)** (`modules/oem_integration/service.py::_verify_auth`):

- JWT ký bằng `MOCK_PRIVATE_KEY`, `typ=JWT`, `aud=ev-care-backend`, claim `body_sha256`. Backend verify chữ ký, `iss`, `aud`, rồi so `body_sha256` với hash của body thô bằng `hmac.compare_digest`.
- `jwt`: chỉ nhận JWT. `both`: JWT hợp lệ thì qua, ngược lại lùi về HMAC (`X-OEM-Signature` + `X-OEM-Timestamp` trong 300 giây). `hmac`: không nhận JWT.

Loại token tách bằng `typ`/`aud`: token endpoint và webhook receiver chỉ nhận `typ=JWT`, nên gửi access token vào đó bị từ chối. Mọi bên dùng leeway **60 giây** cho `exp`/`iat`.

## 4. Mã lỗi

Mock trả `{"detail": {"code": "M2M_..."}}` (ví dụ token hết hạn, sai `typ`, assertion bị dùng lại). Backend ghi log `M2M JWT verification failed (<code>)` và trả `WebhookSignatureInvalid` cho webhook. Không áp dụng cho `/health`, `/oauth/token`, `/admin/**` (dùng `X-Admin-Token`), `/webhooks/**`.

## 5. Mã nguồn

| Việc | File |
| --- | --- |
| Ký/verify token, hằng số, `body_sha256`, lỗi `M2MAuthError` | `backend/shared/ev-contracts/src/ev_contracts/auth.py` |
| Provider access token, cache, lock | `backend/src/infrastructure/oem/auth.py` |
| Gateway gọi OEM, retry 401 | `backend/src/infrastructure/oem/gateway.py` |
| Xác thực webhook | `backend/src/modules/oem_integration/service.py` |
| `/oauth/token`, chống replay `jti`, middleware bắt buộc token | `backend/mock-ev-system/src/mock_ev_system/auth.py`, `routers/oauth.py` |
| Test | `backend/tests/test_infrastructure/test_m2m_auth.py` |

## 6. Triển khai và sự cố

- **Deploy đồng thời backend, worker và mock-ev-system.** Mock đã có `EVCARE_PUBLIC_KEY` sẽ bắt buộc access token; nếu chỉ một bên nhận khoá mới, mọi lệnh gọi OEM trả 401.
- Đổi khóa: sinh cặp mới, cập nhật cả hai phía, xoá key token cache trong Redis (hoặc chờ hết hạn).
- OEM thật chưa dùng JWT gắn body thì giữ `OEM_AUTH_MODE=both`; chuyển `jwt` khi đã sẵn sàng.
