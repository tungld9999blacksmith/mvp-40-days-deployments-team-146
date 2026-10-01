# Frontend Technical Specification — Đăng nhập & Đăng xuất (Chủ xe)

> Đặc tả frontend cho Feature `FEAT-AUTH-002` (US-005 → US-008).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-005-sprint-1-spec.ff.md) · **API:** [API Spec](../api/us-005-sprint-1-spec.api.md) · **Entity:** [Entity Spec](../entity/us-005-sprint-1-spec.entity.md)
>
> **Quan hệ với US-001 FE:** Nút đăng nhập Google, lời gọi `POST /oauth/sign-in` và hàm điều hướng `resolveOnboardingRoute()` đã đặc tả ở [US-001 FE](./us-001-sprint-1-spec.fe.md). Tài liệu này tập trung vào **vòng đời phiên**: khôi phục phiên khi mở app, xử lý token hết hạn / bị thu hồi, tài khoản bị khoá và **đăng xuất**.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-AUTH-002` — Đăng nhập & Đăng xuất (Chủ xe) |
| Screen | `SCR-101` Login · `SCR-102` Splash / Đang đăng nhập · `SCR-103` Lỗi đăng nhập / Tài khoản bị khoá · `SCR-104` Xác nhận đăng xuất (modal) |
| Route | `/` (Login, Splash, lỗi) · modal trong `AppLayout` |
| Version | `v1.0` |
| Author | Mai Văn Trung |
| FE Owner | Lê Đức Tùng |
| Status | `Draft` |
| Related PRD | [PRD_EV_Care_MVP.md](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-005-sprint-1-spec.ff.md#7-user-flow) |
| Related API | [API-001 sign-in](../api/us-001-sprint-1-spec.api.md) · [API-101 logout, API-102 profile](../api/us-005-sprint-1-spec.api.md) |
| Last Updated | `2026-09-29` |

---

# 2. Screen Overview

## 2.1 Purpose

- Chủ xe đã có tài khoản đăng nhập lại bằng Google và vào thẳng Home nếu tài khoản `ACTIVE`.
- Mở lại app khi phiên Firebase còn hiệu lực → tự vào lại, không phải bấm đăng nhập (auto-login).
- Token hết hạn không làm mới được, hoặc bị thu hồi → báo rõ và đưa về Login.
- Đăng xuất: hỏi xác nhận, báo backend ghi audit + thu hồi nền, **luôn** xoá phiên trên thiết bị.

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Mở app | Firebase còn phiên | `SCR-102` Splash → `API-001` → điều hướng theo `nextStep` |
| Mở app | Không có phiên | `SCR-101` Login |
| Sau đăng xuất | — | `SCR-101` Login |
| Bất kỳ API nào trả `401` | Token hết hạn/thu hồi, không làm mới được | `SCR-101` Login + thông báo phiên hết hạn |
| Nhấn `Đăng xuất` ở sidebar | Đang đăng nhập | Mở `SCR-104` |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| `API-001` → `nextStep = HOME` | `/dashboard` |
| `API-001` → `nextStep ∈ {PROFILE, VEHICLE, VERIFYING}` | Bước onboarding tương ứng (US-001 FE §13) |
| `API-001` → `403 ACCOUNT_SUSPENDED / ACCOUNT_INACTIVE` | `SCR-103` (trên `/`) |
| Xác nhận đăng xuất | `/` |
| Huỷ đăng xuất | Ở lại màn hiện tại |
| Nhấn "Liên hệ hỗ trợ" ở `SCR-103` | Kênh hỗ trợ `[Cần xác nhận]` |

## 2.4 Preconditions

- Firebase Web SDK đã cấu hình Google Provider, persistence `browserLocalPersistence` (giữ phiên giữa các lần mở trình duyệt — US-007).
- Có kết nối mạng cho đăng nhập, khôi phục phiên và tính năng được bảo vệ (FF Q-105: không hỗ trợ offline).

---

# 3. UI Structure

## 3.1 Layout

```text
SCR-101 Login (/)                    — dùng lại component của US-001 FE §3.1
├── Left Panel (brand)
└── Right Panel
    ├── Session Notice (nếu vừa bị đẩy ra do hết phiên / vừa đăng xuất)
    ├── GoogleSignInButton
    └── Inline Error

SCR-102 Splash (/ khi authStatus = 'initializing')
├── Logo EV Care
├── Spinner
└── Text "Đang đăng nhập..."

SCR-103 Login Error / Account Locked (/)
├── Icon cảnh báo
├── Title
├── Message (từ error.message)
├── Button "Liên hệ hỗ trợ"
└── Button "Đăng nhập bằng tài khoản khác"

SCR-104 Logout Confirm (Modal trong AppLayout)
├── Title "Đăng xuất khỏi EV Care?"
├── Description
├── Button "Huỷ"
└── Button "Đăng xuất" (danger)

Offline Banner (toàn app, trong AppLayout)
└── "Mất kết nối mạng. Một số tính năng tạm thời không dùng được."
```

## 3.2 Screen Layout Notes

- `SCR-102` thay thế toàn bộ màn hình (không render sidebar) để tránh nháy giữa Login và Home khi khôi phục phiên.
- `SCR-103` hiển thị trong panel phải của Login, thay cho nút Google.
- `SCR-104` là modal căn giữa, overlay tối, đóng được bằng `Esc` / click ra ngoài (tương đương "Huỷ").
- Nút `Đăng xuất` dùng style danger: `text-error border border-error/20 hover:bg-error/10` ([design-guidelines.md](../../../design/design-guidelines.md)).

---

# 4. Component Specification

## 4.1 Session Bootstrap

| Property | Value |
|---|---|
| Component | `AuthProvider` (trong `AuthContext.tsx`) |
| Type | Provider (không có UI riêng, hiển thị `SCR-102` khi đang khởi tạo) |
| Data Source | Firebase `onAuthStateChanged`, `API-001` |
| Visibility | Bọc toàn app |

### Behavior

1. Khi app khởi động: `authStatus = 'initializing'`, render `SCR-102`.
2. Đăng ký `onAuthStateChanged`:
   - `user = null` → `authStatus = 'signed-out'`, render Login.
   - `user != null` → gọi `API-001` (token lấy từ `user.getIdToken()`, SDK tự làm mới nếu hết hạn).
3. `API-001` thành công → lưu `user`, `onboarding`; `authStatus = 'signed-in'`; điều hướng theo `resolveOnboardingRoute()` **chỉ khi** đang ở `/` (nếu người dùng mở thẳng một route hợp lệ như `/vehicle` thì giữ nguyên route đó).
4. `API-001` lỗi → xử lý theo mục 11.2 (thường là `signOut()` + về Login).
5. Chống gọi trùng: `onAuthStateChanged` có thể bắn 2 lần → chỉ gọi `API-001` một lần cho mỗi `uid` (giữ promise đang chạy).

---

## 4.2 Token Refresh & 401 Interceptor

| Property | Value |
|---|---|
| Component | `requestJson` trong `shared/api/client.ts` |
| Type | Networking layer |

### Behavior

- Trước mỗi request: `await auth.currentUser?.getIdToken()` — Firebase trả token còn hạn hoặc tự làm mới (EDGE-103).
- Nếu `getIdToken()` ném lỗi (refresh token đã bị thu hồi, `auth/user-token-expired`, `auth/user-disabled`) → coi như phiên kết thúc: `handleSessionExpired()`.
- Nếu response `401` (`UNAUTHORIZED`, `INVALID_TOKEN`, `TOKEN_REVOKED`):
  1. Thử **một lần** `getIdToken(true)` (ép làm mới) rồi gửi lại request.
  2. Lần thứ hai vẫn `401` → `handleSessionExpired()`.
- `handleSessionExpired()`:
  1. `signOut()` Firebase, xoá state `AuthContext`.
  2. Lưu cờ `sessionNotice = 'expired'` (in-memory) để Login hiển thị thông báo.
  3. Điều hướng `/` (replace).
- Chỉ **một** lần `handleSessionExpired()` được chạy dù nhiều request cùng trả `401` (dùng cờ `isHandlingExpiry`).

---

## 4.3 Session Check (API-102)

| Property | Value |
|---|---|
| Component | `useSessionCheck` (hook trong `AuthProvider`) |
| Data Source | `GET /api/v1/oauth/profile` |

### Behavior

- `/profile` là endpoint duy nhất kiểm tra token bị thu hồi tức thời (API Spec C.1). Các API khác chấp nhận ID token còn hạn tới `exp` kể cả khi đã bị revoke.
- `[Đề xuất]` FE gọi `API-102` khi tab được focus lại (`visibilitychange` → `visible`) và đã quá **15 phút** kể từ lần kiểm tra trước. Điều này giúp thiết bị khác phát hiện sớm khi người dùng đã đăng xuất ở thiết bị này (Firebase revoke theo UID).
- `200` → cập nhật `lastSessionCheckAt`.
- `401` → `handleSessionExpired()`.
- Lỗi mạng / `5xx` → bỏ qua, không đăng xuất người dùng.

---

## 4.4 Login Screen (SCR-101)

Dùng lại `Login.tsx` và `GoogleSignInButton` của [US-001 FE §4.1](./us-001-sprint-1-spec.fe.md#41-google-sign-in-button). Bổ sung:

### Session Notice

| `sessionNotice` | Hiển thị (banner trên nút Google) |
|---|---|
| `expired` | `Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.` (màu warning) |
| `logged-out` | `Bạn đã đăng xuất.` (màu muted) |
| `logged-out-offline` | `Bạn đã đăng xuất trên thiết bị này. Hệ thống chưa xác nhận thu hồi phiên do mất kết nối — hãy đăng nhập và đăng xuất lại khi có mạng nếu bạn dùng thiết bị chung.` (màu warning) |
| `null` | Không hiển thị |

Banner tự ẩn khi người dùng nhấn đăng nhập.

---

## 4.5 Splash (SCR-102)

| Property | Value |
|---|---|
| Component | `SplashScreen` |
| Visibility | `authStatus = 'initializing'` hoặc đang chờ `API-001` |

### Behavior

- Hiển thị tối thiểu cho tới khi có kết quả; không có nút thao tác.
- Nếu quá **10 giây** chưa có kết quả → hiển thị thêm `Kết nối chậm hơn bình thường...` + nút `Thử lại` (gọi lại `API-001`).
- Mất mạng (`navigator.onLine = false`) → hiển thị `Không có kết nối mạng. Vui lòng kết nối để tiếp tục.` + `Thử lại` (EDGE-102). Không cho vào Home với dữ liệu cũ.

---

## 4.6 Login Error / Account Locked (SCR-103)

| Property | Value |
|---|---|
| Component | `LoginErrorPanel` |
| Visibility | `API-001` trả `403 ACCOUNT_SUSPENDED`, `403 ACCOUNT_INACTIVE`, `409 EMAIL_ALREADY_LINKED`, `403 EMAIL_NOT_VERIFIED`, `403 UNSUPPORTED_SIGN_IN_PROVIDER` |

### Nội dung

| Error Code | Title | Message |
|---|---|---|
| `ACCOUNT_SUSPENDED` | `Tài khoản đang bị khoá` | `error.message` (vd: "Tài khoản của bạn đang bị khoá. Vui lòng liên hệ bộ phận hỗ trợ.") |
| `ACCOUNT_INACTIVE` | `Tài khoản ngừng hoạt động` | `error.message` |
| `EMAIL_ALREADY_LINKED` | `Không thể đăng nhập` | `error.message` |
| `EMAIL_NOT_VERIFIED` | `Email chưa xác minh` | `Email Google của bạn chưa được xác minh.` |
| `UNSUPPORTED_SIGN_IN_PROVIDER` | `Không thể đăng nhập` | `Vui lòng đăng nhập bằng tài khoản Google.` |

### Behavior

- Trước khi hiển thị: gọi Firebase `signOut()` (không để phiên Firebase "treo" khi backend từ chối — BR-103).
- `Liên hệ hỗ trợ` → kênh hỗ trợ.
- `Đăng nhập bằng tài khoản khác` → ẩn panel, hiện lại nút Google (Google popup dùng `prompt: 'select_account'`).

---

## 4.7 Logout Confirm Modal (SCR-104)

| Property | Value |
|---|---|
| Component | `LogoutConfirmDialog` |
| Type | Modal dialog |
| Trigger | Nút `Đăng xuất` ở sidebar `AppLayout` |
| Title | `Đăng xuất khỏi EV Care?` |
| Description | `Bạn sẽ cần đăng nhập lại bằng Google để tiếp tục. Các thiết bị khác đang đăng nhập cùng tài khoản cũng sẽ phải đăng nhập lại.` |
| Primary (danger) | `Đăng xuất` |
| Secondary | `Huỷ` |
| Loading State | Nút `Đăng xuất` disabled + spinner, nút `Huỷ` disabled |

> Câu "các thiết bị khác cũng phải đăng nhập lại" phản ánh việc Firebase revoke theo UID (API-101 Rule 2).

### Behavior

1. Nhấn `Đăng xuất` → `isLoggingOut = true`.
2. Gọi `API-101 POST /oauth/logout` với timeout client **5 giây**.
3. **Bất kể kết quả** (`204`, `401`, `503`, `500`, timeout, offline):
   - Firebase `signOut()`.
   - Xoá toàn bộ state người dùng (AuthContext, cache dữ liệu xe, hội thoại...).
   - Điều hướng `/` (replace).
4. Đặt `sessionNotice`:
   - `204` hoặc `401` → `logged-out`.
   - `503` / `500` / timeout / offline → `logged-out-offline` (EF-104, EDGE-105).

> Thứ tự bắt buộc: gọi `API-101` **trước**, `signOut()` **sau** — vì `API-101` cần ID token còn hợp lệ.

---

# 5. User Interaction

## 5.1 Interaction Flow

```text
Mở app
  │
  ▼
SCR-102 Splash ──(không có phiên Firebase)──► SCR-101 Login
  │ có phiên                                     │ Google OK
  ▼                                              ▼
POST /oauth/sign-in ◄────────────────────────────┘
  │
  ├─ 200/201 ─► resolveOnboardingRoute() ─► /dashboard hoặc onboarding
  ├─ 403 khoá ─► signOut() ─► SCR-103
  └─ 401 ─────► signOut() ─► SCR-101 (notice: expired)

Đang dùng app
  │
  ├─ API trả 401 ─► getIdToken(true) + retry 1 lần ─► vẫn 401 ─► signOut() ─► SCR-101 (expired)
  │
  └─ Nhấn "Đăng xuất" ─► SCR-104 ─► Xác nhận
                                    │
                                    ▼
                          POST /oauth/logout (timeout 5s)
                                    │ (mọi kết quả)
                                    ▼
                          signOut() ─► clear state ─► SCR-101 (logged-out / logged-out-offline)
```

## 5.2 Interaction Table

| User Action | Frontend Behavior | Result |
|---|---|---|
| Mở app, có phiên | Splash → `API-001` | Vào Home / onboarding (AC-102) |
| Mở app, không phiên | Hiện Login | SCR-101 |
| Nhấn "Tiếp tục với Google" | Theo US-001 FE §4.1 | Vào Home nếu `ACTIVE` (AC-101) |
| Huỷ popup Google | Reset nút, không báo lỗi | Ở lại Login (EDGE-101) |
| Quay lại tab sau > 15 phút | Gọi `API-102` | Hết phiên → Login |
| Token hết hạn giữa chừng | Tự làm mới; không được → Login | AC-105 |
| Nhấn `Đăng xuất` | Mở modal | SCR-104 |
| Nhấn `Huỷ` / `Esc` | Đóng modal | Ở lại màn hiện tại |
| Xác nhận đăng xuất | `API-101` → `signOut()` | Login (AC-104) |

---

# 6. State Management

## 6.1 State Model

```text
AuthContext
├── authStatus          'initializing' | 'signed-out' | 'signed-in'
├── firebaseUser        Firebase User | null
├── user                SignInUser | null        (API-001)
├── onboarding          OnboardingState | null   (API-001)
├── sessionNotice       'expired' | 'logged-out' | 'logged-out-offline' | null
├── loginError          ApiError | null          (SCR-103)
├── isLoggingOut        boolean
├── lastSessionCheckAt  number | null
└── isOnline            boolean
```

## 6.2 State Fields

| State | Type | Default | Description |
|---|---|---|---|
| `authStatus` | `'initializing' \| 'signed-out' \| 'signed-in'` | `'initializing'` | Map với FF §13: `AUTHENTICATING` ≈ `initializing`, `AUTHENTICATED` ≈ `signed-in`, `UNAUTHENTICATED/REVOKED` ≈ `signed-out` |
| `firebaseUser` | `User \| null` | `null` | Từ `onAuthStateChanged` |
| `user` | `SignInUser \| null` | `null` | `userId`, `email`, `displayName`, `avatarUrl`, `fullName`, `roles` |
| `onboarding` | `OnboardingState \| null` | `null` | Để guard `RequireActiveUser` |
| `sessionNotice` | enum `\| null` | `null` | Thông báo ở Login |
| `loginError` | `ApiError \| null` | `null` | Lỗi hiển thị ở SCR-103 |
| `isLoggingOut` | `boolean` | `false` | Đang gọi `API-101` |
| `lastSessionCheckAt` | `number \| null` | `null` | Epoch ms của lần gọi `API-102` gần nhất |
| `isOnline` | `boolean` | `navigator.onLine` | Theo sự kiện `online` / `offline` |

> **Không** lưu ID token vào `localStorage`/state tự quản. Firebase SDK tự giữ token; FE luôn lấy qua `getIdToken()` (FF §18 Security).

Topbar và sidebar dùng `user.fullName ?? user.displayName` và `user.avatarUrl` thay cho `userName` giả lập hiện có.

---

# 7. API Integration

> Hợp đồng chi tiết: [API-001](../api/us-001-sprint-1-spec.api.md#api-001--sign-in--đồng-bộ-tài-khoản), [API-101 / API-102](../api/us-005-sprint-1-spec.api.md). Quy ước chung (token, `X-Request-ID`, envelope) theo [US-001 FE §7.0](./us-001-sprint-1-spec.fe.md#70-quy-ước-chung).

## 7.1 Sign-in — `API-001`

```http
POST /api/v1/oauth/sign-in
```

### Trigger

- Sau khi đăng nhập Google.
- Khi app khởi động và Firebase còn phiên (auto-login — US-007).

### Mapping

| Frontend State | API Response |
|---|---|
| `user` | `data.user` |
| `onboarding` | `data.onboarding` |

### Success

`200` / `201` → `authStatus = 'signed-in'` → điều hướng (mục 4.1).

### Failure

Mục 11.2.

---

## 7.2 Logout — `API-101`

```http
POST /api/v1/oauth/logout
```

### Trigger

Xác nhận ở `SCR-104`.

### Request

Không body. Header `Authorization` + `X-Request-ID`.

### Success

`204 No Content` → **không** parse JSON (cần sửa `requestJson` để trả `undefined` khi `status = 204`).

### Failure

Mọi lỗi đều không chặn đăng xuất cục bộ (BR-107). Chỉ ảnh hưởng `sessionNotice` (mục 4.7).

---

## 7.3 Session Check — `API-102`

```http
GET /api/v1/oauth/profile
```

### Trigger

Tab focus lại sau ≥ 15 phút (mục 4.3).

### Success

`200` (`uid`, `email`) → chỉ cập nhật `lastSessionCheckAt`, không dùng dữ liệu trả về.

### Failure

`401` → `handleSessionExpired()`. Lỗi khác → bỏ qua.

---

# 8. Client-side Validation

Feature không có form nhập liệu. Kiểm tra phía client duy nhất:

| Check | Rule | Behavior |
|---|---|---|
| Kết nối mạng trước khi đăng nhập | `navigator.onLine = true` | Nếu offline: disable nút Google, hiện `Không có kết nối mạng.` |
| Chống bấm lặp | Không có request đăng nhập/đăng xuất đang chạy | Disable nút khi đang chạy |

---

# 9. Loading States

## 9.1 Khôi phục phiên

- **Condition:** `authStatus = 'initializing'`.
- **UI:** `SCR-102` toàn màn; sau 10s hiện thêm thông báo chậm + `Thử lại`.

## 9.2 Đăng nhập

- **Condition:** Firebase popup / `API-001` đang chạy.
- **UI:** Nút Google disabled + spinner.

## 9.3 Đăng xuất

- **Condition:** `isLoggingOut = true`.
- **UI:** Trong modal: nút `Đăng xuất` spinner, cả hai nút disabled, không đóng modal bằng `Esc`. Tối đa 5 giây rồi vẫn tiếp tục đăng xuất cục bộ.

---

# 10. Empty States

Không áp dụng — feature không hiển thị danh sách dữ liệu.

---

# 11. Error States

## 11.1 General Error

Ở Login:

```text
Đăng nhập không thành công.
Vui lòng thử lại.

[Thử lại]
Mã lỗi: {traceId}
```

## 11.2 Error Mapping

| HTTP Status / Error Code | API | Frontend Behavior |
|---|---|---|
| Firebase `auth/popup-closed-by-user`, `auth/cancelled-popup-request` | — | Không báo lỗi, reset nút (EDGE-101) |
| Firebase `auth/network-request-failed` | — | `Không có kết nối mạng. Vui lòng thử lại.` |
| Firebase lỗi khác | — | General Error |
| `401 UNAUTHORIZED` / `INVALID_TOKEN` / `TOKEN_REVOKED` | 001, 102, API khác | Retry 1 lần với `getIdToken(true)`; vẫn lỗi → `handleSessionExpired()` (AC-105) |
| `403 ACCOUNT_SUSPENDED` / `ACCOUNT_INACTIVE` | 001, 102, API khác | `signOut()` → `SCR-103` (AC-103, EDGE-104) |
| `403 EMAIL_NOT_VERIFIED` / `UNSUPPORTED_SIGN_IN_PROVIDER` | 001 | `signOut()` → `SCR-103` |
| `409 EMAIL_ALREADY_LINKED` | 001 | `signOut()` → `SCR-103` |
| `403 ONBOARDING_REQUIRED` | API tính năng chính | Điều hướng onboarding (US-001 FE) (AC-106) |
| `503 AUTH_PROVIDER_UNAVAILABLE` | 101 | Vẫn đăng xuất cục bộ, `sessionNotice = 'logged-out-offline'` |
| `500 INTERNAL_SERVER_ERROR` | 001 | General Error + `Thử lại`, `signOut()` |
| `500` | 101 | Như `503` |
| Timeout / offline | 001 | Splash / Login: `Không có kết nối mạng...` + `Thử lại` |
| Timeout / offline | 101 | Như `503` |

---

# 12. Error Handling

## 12.1 Field-level Error

Không áp dụng.

## 12.2 Screen-level Error

- Lỗi đăng nhập: hiển thị trong panel phải của Login (General Error hoặc `SCR-103`).
- Mất mạng khi đang dùng app: `Offline Banner` cố định dưới topbar; các nút gọi API hiển thị lỗi mạng theo từng màn. Không tự đăng xuất người dùng chỉ vì offline.

## 12.3 Retry Behavior

- `Thử lại` ở Splash/Login chỉ gọi lại `API-001` (không mở lại popup Google nếu Firebase vẫn còn phiên).
- Đăng xuất không có nút retry: người dùng đã được đăng xuất cục bộ; nếu cần thu hồi phía máy chủ, đăng nhập lại và đăng xuất khi có mạng (EF-104).

---

# 13. Navigation

## 13.1 Routes

| Route | Purpose |
|---|---|
| `/` | Login / Splash / SCR-103 |
| `/dashboard` | Home chủ xe |
| `/onboarding/*` | Onboarding (US-001 FE) |

## 13.2 Navigation Rules

### Sau đăng nhập / auto-login

```text
API-001 OK
   ↓
đang ở "/" ? → resolveOnboardingRoute(onboarding)
đang ở route khác ? → giữ route nếu onboarding.status = ACTIVE, ngược lại resolveOnboardingRoute()
```

### Phiên hết hạn

```text
401 (sau 1 lần làm mới)
   ↓
signOut() + clear state
   ↓
navigate("/", { replace: true })  +  sessionNotice = 'expired'
```

`[Đề xuất]` Lưu `returnTo` (pathname hiện tại) trong memory; sau khi đăng nhập lại và `nextStep = HOME` thì quay về `returnTo` thay vì `/dashboard`. Dữ liệu form chưa lưu **không** được giữ (FF EF-102 `[Cần xác nhận]`).

### Đăng xuất

```text
SCR-104 xác nhận → API-101 → signOut() → navigate("/", { replace: true })
```

Sau khi đăng xuất, nút Back của trình duyệt **không** được đưa người dùng vào lại trang được bảo vệ (guard `RequireActiveUser` đẩy về `/`).

---

# 14. Permission / Visibility

| UI Element | Condition |
|---|---|
| Sidebar, topbar, trang tính năng | `authStatus = 'signed-in'` và `onboarding.status = ACTIVE` (BR-104) |
| Nút `Đăng xuất` (sidebar) | `authStatus = 'signed-in'` |
| Nút `Đăng xuất` (header onboarding) | Đang trong luồng onboarding (US-001 FE) |
| `SCR-103` | Backend từ chối tài khoản |

## 14.1 Role-based Behavior

| Role | Access |
|---|---|
| `VEHICLE_USER` | Đăng nhập / đăng xuất phiên của chính mình |
| Chủ xưởng | Dùng luồng riêng: [US-013 FE](./us-013-sprint-1-spec.fe.md) |

> Kiểm tra ở FE chỉ phục vụ UX. Backend là nơi quyết định.

---

# 15. Responsive / Device Behavior

## Mobile

- Modal `SCR-104` hiển thị dạng bottom sheet, nút xếp dọc (`Đăng xuất` trên, `Huỷ` dưới), full-width.
- Sidebar thu thành menu (ngoài scope feature — nút `Đăng xuất` vẫn phải truy cập được trong menu).

## Tablet / Desktop

- Modal căn giữa, rộng `max-w-sm`.

---

# 16. Accessibility

- Modal `SCR-104`: `role="alertdialog"`, `aria-modal="true"`, `aria-labelledby` (title), `aria-describedby` (description); focus mặc định vào `Huỷ` (tránh đăng xuất nhầm); trap focus trong modal; `Esc` đóng.
- Splash: `role="status"`, `aria-live="polite"`.
- Session notice ở Login: `role="alert"`.
- Offline banner: `role="status"`.

---

# 17. Analytics / Tracking

| Event | Trigger | Properties |
|---|---|---|
| `session_restored` | Auto-login thành công | `nextStep` |
| `login_succeeded` | Đăng nhập thủ công thành công | `isNewUser`, `nextStep` |
| `login_blocked` | `SCR-103` hiển thị | `errorCode` |
| `session_expired` | `handleSessionExpired()` | `source` (`api-401` / `refresh-failed` / `session-check`) |
| `logout_confirmed` | Xác nhận `SCR-104` | — |
| `logout_completed` | Sau `signOut()` | `serverAck` (`true` nếu `204`) |

> Không gửi token, email, uid vào analytics.

---

# 18. Acceptance Criteria

## AC-FE-101 — Đăng nhập tài khoản ACTIVE (FF AC-101)

**Given** người dùng có tài khoản `ACTIVE`
**When** đăng nhập Google thành công
**Then** FE gọi `POST /oauth/sign-in`, nhận `nextStep = HOME` và điều hướng tới `/dashboard`.

## AC-FE-102 — Auto-login (FF AC-102)

**Given** Firebase còn phiên trên trình duyệt
**When** người dùng mở lại app
**Then** FE hiển thị Splash, gọi `POST /oauth/sign-in` và vào `/dashboard` mà không hiển thị màn Login.

## AC-FE-103 — Tài khoản bị khoá (FF AC-103)

**Given** `POST /oauth/sign-in` trả `403 ACCOUNT_SUSPENDED`
**Then** FE gọi Firebase `signOut()`
**And** hiển thị `SCR-103` với thông điệp từ `error.message` và nút `Liên hệ hỗ trợ`.

## AC-FE-104 — Đăng xuất (FF AC-104)

**Given** người dùng đang đăng nhập
**When** nhấn `Đăng xuất` và xác nhận
**Then** FE gọi `POST /oauth/logout` rồi gọi Firebase `signOut()`
**And** điều hướng về `/` với thông báo `Bạn đã đăng xuất.`
**And** mở lại app sẽ hiển thị Login (không auto-login).

## AC-FE-105 — Đăng xuất khi mất mạng (FF EF-104, EDGE-105)

**Given** thiết bị offline hoặc `POST /oauth/logout` trả `503`
**When** người dùng xác nhận đăng xuất
**Then** FE vẫn gọi `signOut()` và về Login
**And** hiển thị thông báo chưa xác nhận thu hồi phiên phía máy chủ.

## AC-FE-106 — Phiên hết hạn (FF AC-105)

**Given** refresh token đã bị thu hồi
**When** người dùng thao tác một chức năng gọi API
**Then** FE thử làm mới token một lần, thất bại thì đăng xuất cục bộ
**And** đưa về Login với thông báo `Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.`

## AC-FE-107 — Onboarding chưa xong (FF AC-106)

**Given** `POST /oauth/sign-in` trả `nextStep = VEHICLE`
**Then** FE điều hướng vào bước onboarding tương ứng, không hiển thị sidebar tính năng chính.

---

# 19. Technical Notes

## Frontend Stack

```text
Framework: React 19 + Vite
Language: TypeScript
State Management: React Context (AuthContext)
Networking: fetch qua shared/api/client.ts
Navigation: React Router 7
UI Library: Tailwind CSS 4 + lucide-react
Auth: Firebase Web SDK (firebase/auth), persistence browserLocalPersistence
Testing: [Cần xác nhận — Vitest + Testing Library đề xuất]
```

## Component Structure

```text
frontend/src/
├── features/auth/
│   ├── context/AuthContext.tsx        # bootstrap, sessionNotice, logout()
│   ├── hooks/useSessionCheck.ts       # API-102 khi tab focus lại
│   ├── components/SplashScreen.tsx    # SCR-102
│   ├── components/LoginErrorPanel.tsx # SCR-103
│   ├── components/LogoutConfirmDialog.tsx  # SCR-104
│   ├── guards/RequireActiveUser.tsx
│   └── api.ts                         # signIn(), logout(), getProfile()
├── layouts/AppLayout.tsx              # nút Đăng xuất mở dialog, hiển thị user thật
└── shared/api/client.ts               # gắn token, retry 401, xử lý 204
```

## Implementation Notes

- **Hiện trạng:** nút `Đăng xuất` trong [AppLayout.tsx](../../../../frontend/src/layouts/AppLayout.tsx) chỉ `navigate('/')`, không xoá phiên; tên người dùng lấy từ mock trong `AuthContext`. Cần thay theo spec này.
- `requestJson` cần: (1) tự gắn `Authorization`; (2) trả `undefined` khi `204`; (3) retry một lần với token làm mới khi `401`; (4) gọi `handleSessionExpired()` (được inject từ `AuthProvider` để tránh phụ thuộc vòng).
- Khi đăng xuất phải xoá mọi cache theo người dùng (dữ liệu xe, hội thoại AI, thông báo) để người dùng kế tiếp trên cùng thiết bị không thấy dữ liệu cũ.

---

# 20. Open Questions

- [ ] **Q-FE-101** (FF EF-102) — Khi phiên hết hạn giữa lúc đang nhập form, có cần giữ dữ liệu chưa lưu không? Spec hiện: không giữ, chỉ nhớ `returnTo`.
- [ ] **Q-FE-102** — Chu kỳ gọi session check `API-102` (15 phút khi tab focus lại) có phù hợp không?
- [ ] **Q-FE-103** — Kênh "Liên hệ hỗ trợ" ở `SCR-103`.
- [ ] **Q-FE-104** — Có cần hiển thị lần đăng nhập gần nhất (`last_login_at`) cho người dùng không? API-001 hiện chưa trả field này.

---

# 21. Related Documents

- Functional Spec: [us-005-sprint-1-spec.ff.md](../feature-functional/us-005-sprint-1-spec.ff.md)
- API Specification: [us-005-sprint-1-spec.api.md](../api/us-005-sprint-1-spec.api.md) · [us-001 API-001](../api/us-001-sprint-1-spec.api.md)
- Entity Spec: [us-005-sprint-1-spec.entity.md](../entity/us-005-sprint-1-spec.entity.md)
- FE liên quan: [US-001 Onboarding chủ xe](./us-001-sprint-1-spec.fe.md) · [US-013 Đăng nhập/Đăng xuất chủ xưởng](./us-013-sprint-1-spec.fe.md)
- Design: [design-guidelines.md](../../../design/design-guidelines.md)

---

# 22. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Mai Văn Trung | Bản nháp đầu tiên, dựng từ FF v1.0 và API Spec v1.0 |
