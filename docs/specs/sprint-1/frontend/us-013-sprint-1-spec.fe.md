# Frontend Technical Specification — Đăng nhập & Đăng xuất (Chủ xưởng) kèm ghi log

> Đặc tả frontend (Workshop Portal) cho Feature `FEAT-AUTH-004` (US-013 → US-016).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-013-sprint-1-spec.ff.md) · **API:** [API Spec](../api/us-013-sprint-1-spec.api.md) · **Entity:** [Entity Spec](../entity/us-013-sprint-1-spec.entity.md)
>
> Spec này dựng **song song** với [US-005 FE](./us-005-sprint-1-spec.fe.md) (phiên chủ xe) và dùng lại màn đăng nhập của [US-009 FE](./us-009-sprint-1-spec.fe.md). Chỗ giống được tham chiếu; mục này chỉ nêu phần **khác**: endpoint riêng của chủ xưởng, **session check trước khi sign-in** khi mở lại portal, và lưu ý thu hồi phiên ảnh hưởng app chủ xe.
>
> Ghi log audit hoàn toàn do backend làm (API-201, API-301, worker). FE **không** gọi API ghi log nào, chỉ cần gửi `X-Request-ID` để log có `trace_id`.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-AUTH-004` — Đăng nhập & Đăng xuất (Chủ xưởng) kèm ghi log |
| Screen | `SCR-301` Login (= `SCR-201`) · `SCR-302` Splash · `SCR-303` Lỗi / Bị khoá · `SCR-304` Xác nhận đăng xuất |
| Route | `/workshop/login` · modal trong layout kỹ thuật viên (`/technician/*`) |
| Version | `v1.0` |
| Author | Mai Văn Trung |
| FE Owner | Lê Đức Tùng |
| Status | `Draft` |
| Related PRD | [PRD_EV_Care_MVP.md](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-013-sprint-1-spec.ff.md#7-user-flow) |
| Related API | [API-201](../api/us-009-sprint-1-spec.api.md) · [API-301 logout, API-302 session](../api/us-013-sprint-1-spec.api.md) |
| Last Updated | `2026-09-29` |

---

# 2. Screen Overview

## 2.1 Purpose

- Chủ xưởng đã có tài khoản đăng nhập lại Workshop Portal bằng Google → vào Dashboard xưởng (`/technician`).
- Mở lại portal khi phiên còn hiệu lực → kiểm tra phiên (có phát hiện bị thu hồi) rồi tự vào lại.
- Phiên hết hạn / bị thu hồi / tài khoản bị khoá → thông báo rõ và về Login.
- Đăng xuất an toàn trên máy dùng chung tại quầy xưởng.

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Mở Workshop Portal | Firebase còn phiên | `SCR-302` → `API-302` → `API-201` → điều hướng |
| Mở Workshop Portal | Không có phiên | `SCR-301` |
| `401` từ API bất kỳ | Không làm mới được | `SCR-301` + thông báo hết phiên |
| Nhấn `Đăng xuất` ở sidebar kỹ thuật viên | Đang đăng nhập | `SCR-304` |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| `nextStep = DASHBOARD` | `/technician` |
| `nextStep ∈ {PROFILE, WORKSHOP, VERIFYING}` | Bước onboarding ([US-009 FE §13](./us-009-sprint-1-spec.fe.md#13-navigation)) |
| `403 ACCOUNT_SUSPENDED / ACCOUNT_INACTIVE` | `SCR-303` |
| `404 WORKSHOP_OWNER_NOT_REGISTERED` (session check) | Gọi `API-201` → luồng đăng ký US-009 (AF-303) |
| Đăng xuất | `/workshop/login` |

## 2.4 Preconditions

- Firebase dùng chung project với app chủ xe; persistence `browserLocalPersistence`.
- Có mạng.

---

# 3. UI Structure

## 3.1 Layout

```text
SCR-301 Login (/workshop/login)       — component của US-009 FE §4.1
├── Session Notice (hết phiên / đã đăng xuất / đăng xuất chưa xác nhận)
└── GoogleSignInButton

SCR-302 Splash                        — dùng lại SplashScreen của US-005 FE
└── Logo "EV Care · Workshop Portal" + spinner + "Đang kiểm tra phiên đăng nhập..."

SCR-303 Login Error / Locked          — dùng lại LoginErrorPanel của US-005 FE
├── Title + message
├── Button "Liên hệ hãng"
└── Button "Đăng nhập bằng tài khoản khác"

SCR-304 Logout Confirm (Modal)
├── Title "Đăng xuất khỏi Workshop Portal?"
├── Description
├── Note (muted): lưu ý app chủ xe cùng Gmail
├── Button "Huỷ"
└── Button "Đăng xuất" (danger)
```

## 3.2 Screen Layout Notes

- Giống US-005 FE §3.2. Branding "Workshop Portal" trên Splash và Login để người dùng phân biệt với app chủ xe.
- Nút `Đăng xuất` hiện có trong sidebar `AppLayout` (nhánh `technicianNav`) phải mở `SCR-304` thay vì `navigate('/')`.

---

# 4. Component Specification

## 4.1 Portal Session Bootstrap

| Property | Value |
|---|---|
| Component | `WorkshopAuthProvider` |
| Data Source | Firebase `onAuthStateChanged`, `API-302`, `API-201` |

### Behavior (khác US-005: gọi session check trước)

1. `authStatus = 'initializing'` → hiển thị `SCR-302`.
2. `onAuthStateChanged`:
   - `user = null` → `signed-out`, render `SCR-301`.
   - `user != null` → gọi **`API-302 GET /workshop-owner/oauth/session`** (phát hiện token đã bị thu hồi — AF-301, BR-307).
3. Kết quả `API-302`:
   - `200` → gọi `API-201` để lấy `nextStep` + `workshop` → `signed-in` → điều hướng (chỉ khi đang ở `/workshop/login`; nếu đang mở một route hợp lệ thì giữ nguyên).
   - `401 TOKEN_REVOKED` / `INVALID_TOKEN` → `signOut()`, `sessionNotice = 'expired'`, `SCR-301` (AC-306).
   - `404 WORKSHOP_OWNER_NOT_REGISTERED` → gọi `API-201` (tạo tài khoản — AF-303) → điều hướng onboarding.
   - `403 ACCOUNT_SUSPENDED / INACTIVE` → `signOut()` → `SCR-303`.
   - `503 AUTH_PROVIDER_UNAVAILABLE` → hiện `Không kiểm tra được phiên đăng nhập. Vui lòng thử lại.` + `Thử lại` trên Splash.
4. Đăng nhập thủ công từ `SCR-301` (vừa lấy token mới) **bỏ qua** `API-302`, gọi thẳng `API-201`.

> Mỗi lần gọi `API-201` backend ghi một log `login`. Vì vậy FE chỉ gọi `API-201` **một lần** cho mỗi lần mở portal / đăng nhập — không gọi lại khi đổi route hay khi tab focus lại.

---

## 4.2 Periodic Session Check

| Property | Value |
|---|---|
| Component | `useWorkshopSessionCheck` |
| Data Source | `API-302` |

- `[Đề xuất]` Gọi `API-302` khi tab focus lại sau ≥ **15 phút** và định kỳ mỗi **15 phút** khi tab đang mở (máy dùng chung tại quầy thường để portal mở cả ngày).
- `200` → cập nhật `onboarding` (nếu `status` đổi, điều hướng lại); không gọi `API-201`.
- `401` → `handleSessionExpired()` (như US-005 FE §4.2).
- `403` khoá → `signOut()` → `SCR-303` (tài khoản bị khoá khi đang dùng).
- Lỗi mạng / `503` → bỏ qua, thử lại ở chu kỳ sau.

---

## 4.3 Token Refresh & 401 Interceptor

Giống [US-005 FE §4.2](./us-005-sprint-1-spec.fe.md#42-token-refresh--401-interceptor), khác ở đích điều hướng: `/workshop/login`.

---

## 4.4 Login Error / Locked (SCR-303)

Giống [US-005 FE §4.6](./us-005-sprint-1-spec.fe.md#46-login-error--account-locked-scr-303). Khác:

| Error Code | Title | Hành động chính |
|---|---|---|
| `ACCOUNT_SUSPENDED` | `Tài khoản chủ xưởng đang bị khoá` | `Liên hệ hãng` |
| `ACCOUNT_INACTIVE` | `Tài khoản chủ xưởng ngừng hoạt động` | `Liên hệ hãng` |
| `EMAIL_ALREADY_LINKED` | `Không thể đăng nhập` | `Liên hệ hãng` |

---

## 4.5 Logout Confirm Modal (SCR-304)

| Property | Value |
|---|---|
| Component | `WorkshopLogoutConfirmDialog` |
| Title | `Đăng xuất khỏi Workshop Portal?` |
| Description | `Bạn sẽ cần đăng nhập lại bằng Google để tiếp tục quản lý xưởng.` |
| Note | `Nếu Gmail này cũng dùng ứng dụng EV Care dành cho chủ xe, bạn có thể phải đăng nhập lại ứng dụng đó.` (BR-306) |
| Primary (danger) | `Đăng xuất` |
| Secondary | `Huỷ` |

> FE không biết Gmail có tài khoản chủ xe hay không, nên `[Đề xuất]` luôn hiển thị lưu ý ở dạng chữ phụ (muted).

### Behavior

Giống [US-005 FE §4.7](./us-005-sprint-1-spec.fe.md#47-logout-confirm-modal-scr-104):

1. Gọi `API-301 POST /workshop-owner/oauth/logout` (timeout client 5s).
2. **Mọi kết quả** → `signOut()` → xoá state (`WorkshopAuthContext`, dữ liệu lịch hẹn, khách hàng) → `/workshop/login` (replace).
3. `sessionNotice`: `204` / `401` → `logged-out`; `503` / `500` / timeout / offline → `logged-out-offline` (EF-303, EDGE-302).

Tài khoản đang bị khoá vẫn gọi `API-301` bình thường (BR-304, EDGE-303).

---

# 5. User Interaction

## 5.1 Interaction Flow

```text
Mở portal
  │
  ▼
SCR-302 ──(không phiên)──► SCR-301 ──Google──► POST /workshop-owner/oauth/sign-in
  │ có phiên                                              │
  ▼                                                       │
GET /workshop-owner/oauth/session                         │
  ├─ 200 ───────────► POST /workshop-owner/oauth/sign-in ─┤
  ├─ 404 ───────────► POST /workshop-owner/oauth/sign-in ─┤ (tạo tài khoản — US-009)
  ├─ 401 ───────────► signOut() ─► SCR-301 (expired)      │
  └─ 403 khoá ──────► signOut() ─► SCR-303                ▼
                                          resolveWorkshopRoute()
                                          ├─ /technician
                                          └─ /workshop/onboarding/*

Đang dùng portal ─► "Đăng xuất" ─► SCR-304 ─► POST /workshop-owner/oauth/logout
                                                   │ (mọi kết quả)
                                                   ▼
                                     signOut() ─► /workshop/login
```

## 5.2 Interaction Table

| User Action | Frontend Behavior | Result |
|---|---|---|
| Mở portal, còn phiên | `API-302` → `API-201` | Vào `/technician` (AC-301) |
| Mở portal, phiên đã bị thu hồi | `API-302` trả `401 TOKEN_REVOKED` | Login + thông báo (AC-306) |
| Đăng nhập Google | `API-201` | Điều hướng theo `nextStep` |
| Tài khoản bị khoá | `API-201`/`API-302` trả `403` | `SCR-303` (AC-302) |
| Để portal mở > 15 phút | `API-302` định kỳ | Phát hiện thu hồi/khoá |
| Nhấn `Đăng xuất` → xác nhận | `API-301` → `signOut()` | Login (AC-304) |

---

# 6. State Management

## 6.1 State Model

```text
WorkshopAuthContext
├── authStatus          'initializing' | 'signed-out' | 'signed-in'
├── owner               (API-201 owner)
├── onboarding          (WorkshopOnboardingState)
├── workshop            (WorkshopSummary | null)
├── lastLoginAt         (API-302)
├── lastLogoutAt        (API-302)
├── sessionNotice       'expired' | 'logged-out' | 'logged-out-offline' | null
├── loginError          ApiError | null
├── isLoggingOut        boolean
└── lastSessionCheckAt  number | null
```

## 6.2 State Fields

| State | Type | Default | Description |
|---|---|---|---|
| `authStatus` | enum | `'initializing'` | Như US-005 |
| `owner` | `WorkshopOwner \| null` | `null` | `ownerId`, `email`, `fullName`, `displayName`, `avatarUrl` |
| `onboarding` | `WorkshopOnboardingState \| null` | `null` | Từ `API-201` hoặc `API-302` |
| `workshop` | `WorkshopSummary \| null` | `null` | Tên xưởng hiển thị ở topbar |
| `lastLoginAt` / `lastLogoutAt` | `string \| null` | `null` | Từ `API-302`, dùng cho mục 17 (tuỳ chọn hiển thị) |
| `sessionNotice` | enum `\| null` | `null` | Banner ở Login |
| `isLoggingOut` | `boolean` | `false` | |
| `lastSessionCheckAt` | `number \| null` | `null` | Chu kỳ `API-302` |

Topbar kỹ thuật viên hiển thị `owner.fullName ?? owner.displayName` và nhãn vai trò `Chủ xưởng · {workshop.name}` thay cho tên giả lập `Trần Minh Kỹ`.

---

# 7. API Integration

> Hợp đồng chi tiết: [us-013 API](../api/us-013-sprint-1-spec.api.md), [us-009 API-201](../api/us-009-sprint-1-spec.api.md). Quy ước chung theo [US-001 FE §7.0](./us-001-sprint-1-spec.fe.md#70-quy-ước-chung). **Luôn gửi `X-Request-ID`** để log audit có `trace_id`.

## 7.1 Session Check — `API-302`

```http
GET /api/v1/workshop-owner/oauth/session
```

### Trigger

Mở portal khi Firebase còn phiên; định kỳ 15 phút; tab focus lại sau ≥ 15 phút.

### Mapping

| Frontend State | API Response |
|---|---|
| `owner.ownerId`, `owner.email` | `data.ownerId`, `data.email` |
| `onboarding` | `data.onboarding` |
| `lastLoginAt`, `lastLogoutAt` | `data.lastLoginAt`, `data.lastLogoutAt` |

### Failure

Mục 11.2.

---

## 7.2 Sign-in — `API-201`

Theo [US-009 FE §7.1](./us-009-sprint-1-spec.fe.md#71-sign-in--api-201). Gọi **tối đa một lần** mỗi lần mở portal / đăng nhập.

---

## 7.3 Logout — `API-301`

```http
POST /api/v1/workshop-owner/oauth/logout
```

### Trigger

Xác nhận `SCR-304`.

### Success

`204` (không có body).

### Failure

Không chặn đăng xuất cục bộ (BR-308). Chỉ đổi `sessionNotice`.

---

# 8. Client-side Validation

Không có form. Chỉ:

| Check | Behavior |
|---|---|
| Offline khi nhấn Google | Disable nút, `Không có kết nối mạng.` |
| Chống bấm lặp | Disable nút khi request đang chạy |

---

# 9. Loading States

| Tình huống | UI |
|---|---|
| Khôi phục phiên (`API-302` + `API-201`) | `SCR-302` toàn màn; > 10s hiện `Kết nối chậm...` + `Thử lại` |
| Đăng nhập | Nút Google disabled + spinner |
| Đăng xuất | Modal: nút `Đăng xuất` spinner, cả hai nút disabled; tối đa 5s |
| Session check định kỳ | Chạy nền, không hiển thị loading |

---

# 10. Empty States

Không áp dụng.

---

# 11. Error States

## 11.1 General Error

Như [US-005 FE §11.1](./us-005-sprint-1-spec.fe.md#111-general-error).

## 11.2 Error Mapping

| HTTP Status / Error Code | API | Frontend Behavior |
|---|---|---|
| `401 UNAUTHORIZED` / `INVALID_TOKEN` | 201, 302, API khác | Làm mới token 1 lần, vẫn lỗi → `handleSessionExpired()` |
| `401 TOKEN_REVOKED` | 302 | `signOut()` → `/workshop/login`, `Phiên đăng nhập đã bị thu hồi. Vui lòng đăng nhập lại.` (AC-306) |
| `403 ACCOUNT_SUSPENDED` / `ACCOUNT_INACTIVE` | 201, 302 | `signOut()` → `SCR-303` (AC-302) |
| `404 WORKSHOP_OWNER_NOT_REGISTERED` | 302 | Gọi `API-201` → onboarding (AF-303) |
| `409 EMAIL_ALREADY_LINKED` | 201 | `signOut()` → `SCR-303` |
| `503 AUTH_PROVIDER_UNAVAILABLE` | 302 (lúc mở portal) | Splash: `Không kiểm tra được phiên đăng nhập.` + `Thử lại` |
| `503 AUTH_PROVIDER_UNAVAILABLE` | 302 (định kỳ) | Bỏ qua |
| `503 AUTH_PROVIDER_UNAVAILABLE` | 301 | Vẫn đăng xuất cục bộ, `sessionNotice = 'logged-out-offline'` |
| `500` | 201, 302 | General Error + `Thử lại` |
| Timeout / offline | 301 | Như `503` |

---

# 12. Error Handling

## 12.1 Field-level Error

Không áp dụng.

## 12.2 Screen-level Error

Lỗi khôi phục phiên hiển thị trên Splash; lỗi đăng nhập hiển thị trong panel Login. Không tự đăng xuất chỉ vì offline.

## 12.3 Retry Behavior

`Thử lại` trên Splash chạy lại chuỗi `API-302` → `API-201`. Đăng xuất không có retry (đã đăng xuất cục bộ); nếu cần thu hồi phía máy chủ: đăng nhập lại và đăng xuất khi có mạng (EF-303).

---

# 13. Navigation

## 13.1 Routes

| Route | Purpose |
|---|---|
| `/workshop/login` | SCR-301 / SCR-302 / SCR-303 |
| `/technician` | Dashboard xưởng |
| `/workshop/onboarding/*` | Onboarding (US-009 FE) |

## 13.2 Navigation Rules

- Sau đăng nhập / khôi phục phiên: `resolveWorkshopRoute(onboarding)` ([US-009 FE §13.2](./us-009-sprint-1-spec.fe.md#132-navigation-rules)).
- Phiên hết hạn / bị thu hồi / đăng xuất → `/workshop/login` (replace). **Không** đưa về `/` (Login của chủ xe).
- Sau đăng xuất, Back của trình duyệt không vào lại `/technician/*` (guard `RequireActiveWorkshopOwner`).

---

# 14. Permission / Visibility

| UI Element | Condition |
|---|---|
| Sidebar kỹ thuật viên | `signed-in` và `onboarding.status = ACTIVE` |
| Nút `Đăng xuất` | `signed-in` (kể cả khi đang onboarding) |
| Lưu ý BR-306 trong `SCR-304` | Luôn hiển thị (muted) |
| Lịch sử đăng nhập | Không có màn hình (FF §3.2, Q-302) |

## 14.1 Role-based Behavior

| Role | Access |
|---|---|
| `WORKSHOP_OWNER` | Đăng nhập / đăng xuất phiên của chính mình |
| `VEHICLE_USER` | Dùng luồng [US-005 FE](./us-005-sprint-1-spec.fe.md) |

---

# 15. Responsive / Device Behavior

Workshop Portal ưu tiên desktop. Modal `SCR-304` căn giữa `max-w-sm`; trên mobile hiển thị bottom sheet như US-005.

---

# 16. Accessibility

Như [US-005 FE §16](./us-005-sprint-1-spec.fe.md#16-accessibility): modal `role="alertdialog"`, focus mặc định `Huỷ`, trap focus, `Esc` đóng; Splash `role="status"`; banner `role="alert"`.

---

# 17. Analytics / Tracking

| Event | Trigger | Properties |
|---|---|---|
| `workshop_session_restored` | Khôi phục phiên thành công | `nextStep` |
| `workshop_session_revoked_detected` | `API-302` trả `401 TOKEN_REVOKED` | `source` (`startup` / `periodic`) |
| `workshop_login_blocked` | `SCR-303` hiển thị | `errorCode` |
| `workshop_logout_completed` | Sau `signOut()` | `serverAck` |

> Log audit nghiệp vụ (IP, user agent) do backend ghi — FE không gửi thêm dữ liệu đó vào analytics.

---

# 18. Acceptance Criteria

## AC-FE-301 — Đăng nhập (FF AC-301)

**Given** chủ xưởng `ACTIVE`
**When** đăng nhập Google ở `/workshop/login`
**Then** FE gọi `POST /workshop-owner/oauth/sign-in` **một lần** kèm `X-Request-ID` và mở `/technician`.

## AC-FE-302 — Tài khoản bị khoá (FF AC-302)

**Given** `API-201` trả `403 ACCOUNT_SUSPENDED`
**Then** FE gọi `signOut()` và hiển thị `SCR-303` với nút `Liên hệ hãng`.

## AC-FE-303 — Onboarding chưa xong (FF AC-303)

**Given** `API-201` trả `nextStep = WORKSHOP`
**Then** FE mở bước onboarding tương ứng của US-009.

## AC-FE-304 — Đăng xuất (FF AC-304)

**Given** đang đăng nhập
**When** nhấn `Đăng xuất` và xác nhận
**Then** FE gọi `POST /workshop-owner/oauth/logout`, sau đó `signOut()` và mở `/workshop/login` với thông báo `Bạn đã đăng xuất.`

## AC-FE-305 — Đăng xuất khi backend lỗi (FF EF-303)

**Given** `API-301` trả `503` hoặc mất mạng
**Then** FE vẫn `signOut()`, về Login, hiển thị thông báo chưa xác nhận thu hồi phiên.

## AC-FE-306 — Phát hiện phiên bị thu hồi (FF AC-306)

**Given** refresh token đã bị thu hồi (vd đã đăng xuất ở máy khác)
**When** mở lại portal, hoặc đến chu kỳ session check
**Then** FE gọi `GET /workshop-owner/oauth/session`, nhận `401 TOKEN_REVOKED`, `signOut()` và về Login với thông báo phiên bị thu hồi.

## AC-FE-307 — Không gọi sign-in lặp

**Given** portal đang mở
**When** người dùng chuyển giữa các trang hoặc tab focus lại
**Then** FE không gọi lại `POST /workshop-owner/oauth/sign-in` (tránh ghi log `login` thừa).

---

# 19. Technical Notes

## Frontend Stack

Như [US-005 FE §19](./us-005-sprint-1-spec.fe.md#19-technical-notes).

## Component Structure

```text
frontend/src/features/workshop-auth/
├── context/WorkshopAuthContext.tsx          # bootstrap: session → sign-in
├── hooks/useWorkshopSessionCheck.ts         # API-302 định kỳ
├── components/WorkshopLogoutConfirmDialog.tsx
└── api.ts                                   # signIn(), getSession(), logout()
```

Dùng lại từ `features/auth`: `SplashScreen`, `LoginErrorPanel`, logic interceptor trong `shared/api/client.ts`.

## Implementation Notes

- `requestJson` phải gửi `X-Request-ID` (UUID) cho mọi request của portal.
- Không thêm header `User-Agent` thủ công (trình duyệt tự gửi; backend đọc để ghi log).
- `AuthContext` (chủ xe) và `WorkshopAuthContext` không được cùng tự khôi phục phiên từ một Firebase user — cổng nào đang mở (`sessionStorage.portal`) mới chạy bootstrap của cổng đó.

---

# 20. Open Questions

- [ ] **Q-FE-301** (FF Q-301) — Có giữ việc thu hồi refresh token theo UID khi Gmail cũng dùng app chủ xe không? Spec giả định **có** và luôn hiển thị lưu ý.
- [ ] **Q-FE-302** — Chu kỳ session check 15 phút có phù hợp với máy quầy dùng chung không, hay cần tự đăng xuất khi không thao tác (idle timeout)?
- [ ] **Q-FE-303** (FF Q-302) — Có hiển thị "Lần đăng nhập trước: …" (từ `lastLoginAt`) cho chủ xưởng không?

---

# 21. Related Documents

- Functional Spec: [us-013-sprint-1-spec.ff.md](../feature-functional/us-013-sprint-1-spec.ff.md)
- API Specification: [us-013-sprint-1-spec.api.md](../api/us-013-sprint-1-spec.api.md) · [us-009 API-201](../api/us-009-sprint-1-spec.api.md)
- Entity Spec: [us-013-sprint-1-spec.entity.md](../entity/us-013-sprint-1-spec.entity.md)
- FE liên quan: [US-009 Onboarding chủ xưởng](./us-009-sprint-1-spec.fe.md) · [US-005 Phiên chủ xe](./us-005-sprint-1-spec.fe.md)

---

# 22. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Mai Văn Trung | Bản nháp đầu tiên, dựng từ FF v1.0 và API Spec v1.0 |
