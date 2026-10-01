# Frontend Technical Specification — Đăng ký & Onboarding Chủ xưởng dịch vụ qua Google OAuth

> Đặc tả frontend (Workshop Portal) cho Feature `FEAT-AUTH-003` (US-009 → US-012).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-009-sprint-1-spec.ff.md) · **API:** [API Spec](../api/us-009-sprint-1-spec.api.md) · **Entity:** [Entity Spec](../entity/us-009-sprint-1-spec.entity.md)
>
> Luồng này dựng **song song** với [US-001 FE](./us-001-sprint-1-spec.fe.md) (onboarding chủ xe): cùng cơ chế Firebase, cùng quy ước gọi API, cùng mẫu "điều hướng theo `nextStep`". Chỗ giống được tham chiếu, chỗ khác được nêu rõ. Điểm FE tự đề xuất đánh dấu `[Đề xuất]`.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-AUTH-003` — Đăng ký & Onboarding Chủ xưởng dịch vụ |
| Screen | `SCR-201` Login Workshop Portal · `SCR-202` Thông tin chủ xưởng · `SCR-203` Thông tin vận hành xưởng · `SCR-204` Đang xác thực · `SCR-205` Thành công · `SCR-206` Xác thực thất bại |
| Route | `/workshop/login` · `/workshop/onboarding/profile` · `/workshop/onboarding/operations` · `/workshop/onboarding/verifying` · `/workshop/onboarding/success` · `/workshop/onboarding/failed` |
| Version | `v1.0` |
| Author | Mai Văn Trung |
| FE Owner | Lê Đức Tùng |
| Status | `Draft` |
| Related PRD | [PRD_EV_Care_MVP.md](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-009-sprint-1-spec.ff.md#7-user-flow) |
| Related API | [API-201 → API-204](../api/us-009-sprint-1-spec.api.md) |
| Last Updated | `2026-09-29` |

---

# 2. Screen Overview

## 2.1 Purpose

Chủ xưởng dịch vụ đăng nhập Workshop Portal bằng Google, khai báo thông tin cá nhân (họ tên, SĐT, **CCCD**) và thông tin vận hành xưởng (địa chỉ, hotline, số kỹ thuật viên, slot dự phòng, giờ hoạt động 7 ngày). Hệ thống gửi **Gmail + CCCD** sang hãng; hãng trả về đúng **một** xưởng. Chủ xưởng **không chọn xưởng**. Thành công ⇒ tài khoản `ACTIVE`, vào Dashboard xưởng.

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Mở `/workshop/login` | Chưa có phiên | Hiển thị `SCR-201` |
| Mở Workshop Portal khi Firebase còn phiên | — | Gọi `API-201`, điều hướng theo `nextStep` |
| Truy cập trang quản lý xưởng khi chưa `ACTIVE` | Guard, hoặc API trả `403 ONBOARDING_REQUIRED` | Điều hướng theo `nextStep` (`BR-203`) |
| Truy cập trực tiếp `/workshop/onboarding/*` | Đã đăng nhập | Gọi `API-202`, điều hướng về đúng bước |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| `nextStep = DASHBOARD` | `/technician` (Dashboard xưởng hiện có) |
| `nextStep = PROFILE` | `/workshop/onboarding/profile` |
| `nextStep = WORKSHOP` và `status = ONBOARDING_IN_PROGRESS` | `/workshop/onboarding/operations` |
| `nextStep = WORKSHOP` và `status = VERIFICATION_FAILED` | `/workshop/onboarding/failed` |
| `nextStep = VERIFYING` | `/workshop/onboarding/verifying` |
| `401` | `signOut()` → `/workshop/login` |
| "Liên hệ hãng" | Kênh liên hệ hãng `[Cần xác nhận]` |

## 2.4 Preconditions

- Firebase Web SDK dùng **chung project** với app chủ xe; tách tài khoản do endpoint `/workshop-owner/...` quyết định (`BR-209`).
- Gmail đăng nhập đã được hãng ghi nhận là người quản lý một xưởng (nếu không, kết quả sẽ là `MANAGER_NOT_FOUND`).
- Với SCR-203: `profileCompleted = true`.

---

# 3. UI Structure

## 3.1 Layout

```text
SCR-201 Login — Workshop Portal (/workshop/login)
├── Left Panel: "EV Care · Workshop Portal", headline cho xưởng dịch vụ
└── Right Panel
    ├── Title "Đăng nhập cổng xưởng dịch vụ"
    ├── Note "Dùng đúng Gmail đã đăng ký với hãng làm người quản lý xưởng"
    ├── GoogleSignInButton
    ├── Inline Error
    └── Link "Bạn là chủ xe? Đăng nhập tại đây" → /

WorkshopOnboardingLayout (/workshop/onboarding/*)
├── Header (logo, "Workshop Portal", email Google, nút "Đăng xuất")
├── Stepper: 1. Thông tin chủ xưởng → 2. Vận hành xưởng → 3. Xác thực
├── Expiry Notice: "Hoàn tất trước {expiresAt} để giữ dữ liệu đã nhập."
└── Content
    ├── SCR-202 Owner Profile Form
    │   ├── Email Google (read-only) + ghi chú
    │   ├── Họ tên
    │   ├── Số điện thoại
    │   ├── Số CCCD
    │   ├── Checkbox đồng ý xử lý dữ liệu cá nhân
    │   └── Button "Tiếp tục"
    ├── SCR-203 Operations Form
    │   ├── Section "Vị trí & liên hệ": Địa chỉ, Toạ độ (tuỳ chọn), Hotline
    │   ├── Section "Công suất": Số KTV mỗi ca, Slot dự phòng khẩn cấp
    │   ├── Section "Giờ hoạt động": 7 dòng (Thứ 2 → Chủ nhật)
    │   │     └── mỗi dòng: Toggle "Mở cửa" · Giờ mở · Giờ đóng
    │   ├── Button "Áp dụng giờ Thứ 2 cho các ngày khác" [Đề xuất]
    │   ├── Checkbox đồng ý chia sẻ Gmail + CCCD cho hãng
    │   ├── Button "Quay lại"
    │   └── Button "Gửi xác thực"
    ├── SCR-204 Verifying
    ├── SCR-205 Success (thông tin xưởng hãng trả về + tóm tắt vận hành)
    └── SCR-206 Verification Failed
```

## 3.2 Screen Layout Notes

- Cùng phong cách Premium Dark ([design-guidelines.md](../../../design/design-guidelines.md)).
- SCR-203 dài: chia 3 card theo section; nút `Gửi xác thực` cố định (sticky) cuối màn trên desktop.
- Bảng giờ hoạt động: 1 hàng/ngày; khi tắt "Mở cửa" thì ẩn/disable 2 ô giờ và hiển thị nhãn `Đóng cửa`.
- CCCD, hotline, giờ hiển thị bằng font mono.
- SCR-205 **không** có ô nhập tên xưởng / khu vực / loại xưởng — các giá trị này đến từ hãng (`BR-205`).

---

# 4. Component Specification

## 4.1 Google Sign-in (SCR-201)

Giống [US-001 FE §4.1](./us-001-sprint-1-spec.fe.md#41-google-sign-in-button), khác ở:

| Property | Value |
|---|---|
| API gọi sau Firebase | `API-201 POST /workshop-owner/oauth/sign-in` |
| State lưu | `WorkshopAuthContext.owner`, `.onboarding`, `.workshop` |
| Điều hướng | `resolveWorkshopRoute(onboarding)` (mục 13.2) |

---

## 4.2 Owner Profile Form (SCR-202)

| Property | Value |
|---|---|
| Component | `WorkshopOwnerProfileForm` |
| Data Source | Prefill từ `API-202.profile`, `.consents` |
| Submit | `API-203 PUT /workshop-owner/onboarding/profile` |

### Fields

| Field | Component | Required | Default | Constraints | Ghi chú |
|---|---|---|---|---|---|
| Email Google | Text (read-only) | — | `owner.email` | — | Helper: `Dùng đúng Gmail đã đăng ký với hãng làm người quản lý xưởng.` |
| `fullName` | `TextInput` | Yes | `profile.fullName` → fallback `displayName` | 2–150 ký tự; chữ cái, khoảng trắng, `'`, `-`, `.` | |
| `phoneNumber` | `TextInput` (`tel`) | Yes | `profile.phoneNumber` | `^(0\|\+84)(3\|5\|7\|8\|9)[0-9]{8}$` sau bỏ phân cách | |
| `nationalId` | `TextInput` (`inputmode=numeric`, font mono) | Yes | **Rỗng** | `^[0-9]{12}$` sau bỏ khoảng trắng | Xem "CCCD khi quay lại" bên dưới |
| `personalDataConsent.granted` | `Checkbox` | Yes | `consents.personalDataProcessing.granted` | Phải `true` | Link mở điều khoản |

`policyVersion` lấy từ cấu hình FE `WORKSHOP_CONSENT_POLICY_VERSION` (mặc định `WS-2026-09`).

### CCCD khi quay lại

`API-202` chỉ trả `nationalIdMasked` (vd `001******101`), **không** trả CCCD đầy đủ. Vì `API-203` là `PUT` ghi đè toàn bộ và `nationalId` bắt buộc:

- Hiển thị `nationalIdMasked` làm placeholder: `CCCD đã lưu: 001******101`.
- Người dùng phải nhập lại CCCD đầy đủ mỗi khi gửi lại SCR-202 (vd khi sửa sau `NATIONAL_ID_MISMATCH`).
- Nếu chỉ muốn đi tiếp mà không sửa hồ sơ (đã `profileCompleted`), stepper cho phép bấm sang bước 2 mà không gửi lại SCR-202.

### Behavior

- `Tiếp tục` → validate → `API-203` → cập nhật `onboarding` → điều hướng theo `nextStep` (thường `WORKSHOP`).
- **Không** lưu CCCD vào `localStorage` hay log/analytics.

---

## 4.3 Operations Form (SCR-203)

| Property | Value |
|---|---|
| Component | `WorkshopOperationsForm` |
| Data Source | Prefill từ `API-202.registration` (nếu đã gửi trước đó) |
| Submit | `API-204 POST /workshop-owner/onboarding/workshop-verification` |

### Fields — Vị trí & liên hệ

| Field | Component | Required | Constraints |
|---|---|---|---|
| `address` | `TextArea` (2 dòng) | Yes | 5–500 ký tự |
| `latitude`, `longitude` | 2 `NumberInput` (hoặc map picker khi có) | No | `-90..90` / `-180..180`; nhập cả hai hoặc bỏ trống cả hai |
| `hotline` | `TextInput` (`tel`) | Yes | Sau bỏ khoảng trắng/`.`/`-`: `^((\+84\|0)[0-9]{9,10}\|(1900\|1800)[0-9]{4,6})$` |

### Fields — Công suất

| Field | Component | Required | Default | Constraints |
|---|---|---|---|---|
| `totalTechnicians` | `NumberInput` (stepper) | Yes | — | Số nguyên `1..200` |
| `emergencySlotsReserved` | `NumberInput` (stepper) | No | `0` | Số nguyên `0..totalTechnicians` (`EDGE-206`) |

Helper dưới `emergencySlotsReserved`: `Số slot giữ lại cho trường hợp khẩn cấp, không vượt quá số kỹ thuật viên.`

### Fields — Giờ hoạt động (`OperatingHoursEditor`)

| Field (mỗi ngày) | Component | Default | Constraints |
|---|---|---|---|
| `dayOfWeek` | Nhãn cố định | 1 = Thứ 2 … 7 = Chủ nhật | Đủ 7 ngày, không trùng |
| `isClosed` | `Toggle` "Mở cửa" (bật = `isClosed=false`) | T2–T7 mở, CN đóng `[Đề xuất]` | Ít nhất 1 ngày mở |
| `openTime` | `TimeInput` `HH:mm` (bước 15 phút) | `08:00` | Bắt buộc khi mở |
| `closeTime` | `TimeInput` `HH:mm` | `17:30` | Bắt buộc khi mở, `> openTime` |

Khi ngày đóng cửa: gửi `openTime = null`, `closeTime = null`.

### Consent

| Field | Label | Required |
|---|---|---|
| `oemDataSharingConsent.granted` | `Tôi đồng ý chia sẻ Gmail và số CCCD cho hãng để xác thực người quản lý xưởng.` | Phải `true` (`BR-210`) |

### Behavior

1. `Gửi xác thực` → validate toàn form (mục 8). Lỗi → không gọi API.
2. Sinh `Idempotency-Key` (UUID v4) mới.
3. Gọi `API-204` và xử lý theo mục 7.4.
4. Lỗi mạng: tự retry 1 lần với **cùng** key.
5. `Quay lại` → SCR-202, giữ dữ liệu SCR-203 trong state.

---

## 4.4 Verifying (SCR-204)

| Property | Value |
|---|---|
| Component | `WorkshopVerifying` |
| Data Source | Polling `API-202` |

### Behavior

- Polling `API-202`: mỗi **3 giây** trong 60 giây đầu, sau đó mỗi **30 giây** (API-202 §13–19).
- Mỗi lần poll: `nextStep != VERIFYING` → dừng, điều hướng theo mục 13.
- Thông điệp:
  - 0–60s: `Đang xác thực thông tin của bạn với hãng...`
  - Sau 60s: `Hệ thống hãng phản hồi chậm, chúng tôi sẽ tiếp tục xác thực trong khoảng 30 phút. Bạn có thể quay lại sau.` + nút `Đăng xuất và quay lại sau`.
- Tổng thời gian polling tối đa **35 phút** (retry nền của backend ~30 phút). Sau đó dừng và hiện nút `Kiểm tra lại`.
- Dừng polling khi tab ẩn; khi tab hiện lại gọi `API-202` ngay một lần rồi tiếp tục.
- Không có nút gửi lại ở màn này (backend đã chặn gửi trùng — `AF-203`).

---

## 4.5 Success (SCR-205)

| Property | Value |
|---|---|
| Component | `WorkshopOnboardingSuccess` |
| Data Source | `API-204.workshop` (VERIFIED) hoặc `API-202.workshop` |

### Nội dung

| Nhóm | Field | Hiển thị |
|---|---|---|
| Từ hãng | `name`, `centerId`, `region`, `type` | Card nổi bật; `type`: `DEALER` → `Đại lý 3S`, `SERVICE_ONLY` → `Xưởng dịch vụ` |
| Vận hành | `address`, `hotline`, `totalTechnicians`, `emergencySlotsReserved` | Danh sách |
| Giờ hoạt động | `operatingHours` | Bảng 7 ngày, ngày đóng hiển thị `Đóng cửa` |
| Trạng thái | `status` | Badge `ACTIVE` |

- Nút `Vào Dashboard` → `/technician` (replace history).

---

## 4.6 Verification Failed (SCR-206)

| Property | Value |
|---|---|
| Component | `WorkshopVerificationFailed` |
| Data Source | `verification` từ `API-204` hoặc `latestAttempt` + `registration.failureReason` từ `API-202` |

### Nội dung theo `failureReason`

| `failureReason` | Thông điệp | Hành động chính | Hành động phụ |
|---|---|---|---|
| `MANAGER_NOT_FOUND` | `Gmail {email} chưa được hãng ghi nhận là người quản lý xưởng nào. Hãy đăng nhập bằng đúng Gmail đã đăng ký với hãng, hoặc liên hệ hãng để cập nhật.` | `Đăng nhập bằng Gmail khác` (signOut → `/workshop/login`) | `Liên hệ hãng` |
| `NATIONAL_ID_MISMATCH` | `Số CCCD không khớp với người quản lý xưởng trên hệ thống hãng. Vui lòng kiểm tra lại.` | `Sửa CCCD` (→ SCR-202, focus ô CCCD) | `Liên hệ hãng` |
| `ALREADY_CLAIMED` | `Xưởng này đang được quản lý bởi một tài khoản khác. Vui lòng liên hệ hãng.` | `Liên hệ hãng` | — |
| `OEM_UNAVAILABLE` | `Hệ thống hãng không phản hồi. Vui lòng gửi lại sau.` | `Gửi lại` (→ SCR-203, dữ liệu giữ nguyên) | `Liên hệ hãng` |

- Hiển thị `Đã thất bại {failedAttemptsLast24h}/{maxFailedAttempts} lần trong 24 giờ.` khi `failedAttemptsLast24h >= 3`.
- `failedAttemptsLast24h >= maxFailedAttempts` → ẩn nút sửa/gửi lại; hiển thị thời điểm có thể thử lại (mục 11.2 — `429`).
- Luôn có link phụ `Sửa thông tin vận hành` (→ SCR-203) trừ khi `ALREADY_CLAIMED`.

---

## 4.7 Workshop Onboarding Guard

| Property | Value |
|---|---|
| Component | `RequireActiveWorkshopOwner` |
| Áp dụng | Mọi route `/technician/*`, `/customers` khi đăng nhập bằng cổng xưởng |

- Chưa đăng nhập → `/workshop/login`.
- `onboarding.status != ACTIVE` → `resolveWorkshopRoute()`.

---

# 5. User Interaction

## 5.1 Interaction Flow

```text
/workshop/login ─► Google ─► POST /workshop-owner/oauth/sign-in
                                 │
     ┌───────────────────────────┼──────────────────────────────┐
     ▼                           ▼                              ▼
 DASHBOARD → /technician   PROFILE → SCR-202            VERIFYING → SCR-204
                                 │ PUT /workshop-owner/onboarding/profile
                                 ▼
                             SCR-203
                                 │ POST /workshop-owner/onboarding/workshop-verification
        ┌────────────────┬───────┴────────┬────────────────────────┐
        ▼                ▼                ▼                        ▼
   200 VERIFIED     200 FAILED      202 PENDING         409 WORKSHOP_ALREADY_CLAIMED
   SCR-205          SCR-206         SCR-204 (polling)   SCR-206 (ALREADY_CLAIMED)
        │                │
   /technician      Sửa CCCD → SCR-202 / Gửi lại → SCR-203
```

## 5.2 Interaction Table

| User Action | Frontend Behavior | Result |
|---|---|---|
| Nhấn Google ở `/workshop/login` | Firebase → `API-201` | Điều hướng theo `nextStep` |
| Nhập CCCD có khoảng trắng | Tự bỏ khoảng trắng khi validate/gửi | — |
| Nhấn `Tiếp tục` (SCR-202) | Validate → `API-203` | SCR-203 |
| Tắt toggle "Mở cửa" một ngày | Disable 2 ô giờ, xoá lỗi của hàng đó | Ngày đó `Đóng cửa` |
| Nhấn `Áp dụng giờ Thứ 2 cho các ngày khác` | Copy `isClosed/openTime/closeTime` của T2 sang T3–T7 | CN giữ nguyên |
| Đổi `totalTechnicians` nhỏ hơn slot dự phòng | Hiện lỗi ở slot dự phòng | Chặn gửi |
| Nhấn `Gửi xác thực` | Validate → key → `API-204` | SCR-204/205/206 |
| Ở SCR-204 | Polling 3s → 30s | Tự chuyển màn |

---

# 6. State Management

## 6.1 State Model

```text
WorkshopAuthContext
├── authStatus          'initializing' | 'signed-out' | 'signed-in'
├── owner               (API-201 owner)
├── onboarding          (WorkshopOnboardingState)
└── workshop            (WorkshopSummary | null)

WorkshopOnboardingContext
├── snapshot            (API-202 data)
├── profileForm         { fullName, phoneNumber, nationalId, consentGranted }
├── operationsForm      { address, latitude, longitude, hotline, totalTechnicians,
│                         emergencySlotsReserved, operatingHours[7], consentGranted }
├── verification        (API-204 verification | null)
├── idempotencyKey
├── polling             { isPolling, startedAt, intervalMs, stopped }
└── request             { isLoading, isSubmitting, error, fieldErrors }
```

## 6.2 State Fields

| State | Type | Default | Description |
|---|---|---|---|
| `owner` | `WorkshopOwner \| null` | `null` | `ownerId`, `email`, `displayName`, `fullName`, `roles` |
| `onboarding` | `WorkshopOnboardingState \| null` | `null` | Có thêm `expiresAt` so với chủ xe |
| `workshop` | `WorkshopSummary \| null` | `null` | Chỉ khi `ACTIVE` |
| `profileForm.nationalId` | `string` | `""` | Không prefill (API chỉ trả mask) |
| `profileForm.nationalIdMasked` | `string \| null` | từ `API-202` | Chỉ để hiển thị |
| `operationsForm.operatingHours` | `OperatingHour[7]` | T2–T7 `08:00–17:30`, CN đóng | |
| `operationsForm.emergencySlotsReserved` | `number` | `0` | |
| `verification` | `object \| null` | `null` | `status`, `failureReason`, `failedAttemptsLast24h`, `maxFailedAttempts` |
| `polling.intervalMs` | `number` | `3000` | Đổi thành `30000` sau 60s |
| `fieldErrors` | `Record<string,string>` | `{}` | Key dạng `operatingHours[5].closeTime` khớp `details.field` của API |

> Phiên chủ xưởng và phiên chủ xe dùng chung Firebase user nhưng **state tách riêng** (`WorkshopAuthContext` ≠ `AuthContext`). Một trình duyệt chỉ hoạt động ở một vai trò tại một thời điểm (xác định bằng cổng đăng nhập đã dùng — lưu `portal = 'workshop' | 'owner'` trong `sessionStorage`).

---

# 7. API Integration

> Hợp đồng chi tiết: [API Spec](../api/us-009-sprint-1-spec.api.md). Quy ước chung theo [US-001 FE §7.0](./us-001-sprint-1-spec.fe.md#70-quy-ước-chung).

## 7.1 Sign-in — `API-201`

```http
POST /api/v1/workshop-owner/oauth/sign-in
```

| Trigger | Mapping |
|---|---|
| Sau Firebase sign-in ở `/workshop/login`; khi mở portal còn phiên | `owner ← data.owner`, `onboarding ← data.onboarding`, `workshop ← data.workshop` |

`201` / `200` → điều hướng `resolveWorkshopRoute()`. Lỗi → mục 11.2.

---

## 7.2 Get Onboarding — `API-202`

```http
GET /api/v1/workshop-owner/onboarding
```

### Trigger

Mở trực tiếp `/workshop/onboarding/*`; polling SCR-204; mở SCR-206 khi chưa có `verification`.

### Mapping

| Frontend State | API Response |
|---|---|
| `onboarding` | `data.onboarding` |
| `profileForm.fullName`, `phoneNumber` | `data.profile.fullName`, `phoneNumber` |
| `profileForm.nationalIdMasked` | `data.profile.nationalIdMasked` |
| `profileForm.consentGranted` | `data.consents.personalDataProcessing.granted` |
| `operationsForm.*` | `data.registration.*` (khi khác `null`) |
| `operationsForm.consentGranted` | `data.consents.oemDataSharing.granted` |
| `verification` | `data.latestAttempt` (+ `registration.failureReason`) |
| `workshop` | `data.workshop` |

### Failure

`404 WORKSHOP_OWNER_NOT_REGISTERED` → gọi lại `API-201`. Lỗi mạng khi polling: bỏ qua lượt; 3 lượt lỗi liên tiếp → dừng, hiện `Thử lại`.

---

## 7.3 Save Profile — `API-203`

```http
PUT /api/v1/workshop-owner/onboarding/profile
```

### Request Mapping

```json
{
  "fullName": "{profileForm.fullName (trim)}",
  "phoneNumber": "{profileForm.phoneNumber}",
  "nationalId": "{profileForm.nationalId (bỏ khoảng trắng)}",
  "personalDataConsent": { "granted": true, "policyVersion": "{WORKSHOP_CONSENT_POLICY_VERSION}" }
}
```

### Success

`200` → `onboarding ← data.onboarding`; xoá `profileForm.nationalId` khỏi state, cập nhật `nationalIdMasked ← data.profile.nationalIdMasked` → điều hướng theo `nextStep`.

---

## 7.4 Submit Workshop Verification — `API-204`

```http
POST /api/v1/workshop-owner/onboarding/workshop-verification
Idempotency-Key: <uuid-v4>
```

### Request Mapping

```json
{
  "address": "{operationsForm.address (trim)}",
  "latitude": "{operationsForm.latitude | null}",
  "longitude": "{operationsForm.longitude | null}",
  "hotline": "{operationsForm.hotline}",
  "totalTechnicians": "{operationsForm.totalTechnicians}",
  "emergencySlotsReserved": "{operationsForm.emergencySlotsReserved}",
  "operatingHours": [
    { "dayOfWeek": 1, "isClosed": false, "openTime": "08:00", "closeTime": "17:30" },
    "... đủ 7 phần tử, dayOfWeek 1..7 ..."
  ],
  "oemDataSharingConsent": { "granted": true, "policyVersion": "{WORKSHOP_CONSENT_POLICY_VERSION}" }
}
```

> Body **không** có CCCD hay `centerId` — CCCD lấy từ hồ sơ, Gmail từ token (API §3.2).

### Kết quả

| HTTP | Trường hợp | Frontend |
|---|---|---|
| `200` | `verification.status = VERIFIED` | Lưu `workshop`, `onboarding` → `/workshop/onboarding/success` |
| `200` | `verification.status = FAILED` | Lưu `verification` → `/workshop/onboarding/failed` |
| `202` | `PENDING` | → `/workshop/onboarding/verifying`, polling |
| `409` | `WORKSHOP_ALREADY_CLAIMED` | → SCR-206 với `failureReason = ALREADY_CLAIMED` |
| `409` | `VERIFICATION_IN_PROGRESS` | → SCR-204 |
| `409` | `PROFILE_INCOMPLETE` | → SCR-202 |
| `409` | `ONBOARDING_ALREADY_COMPLETED` | → `/technician` |
| `429` | `VERIFICATION_ATTEMPTS_EXCEEDED` | → SCR-206 trạng thái hết lượt |

---

# 8. Client-side Validation

## 8.1 Validation Rules

| Field | Rule | Error Message |
|---|---|---|
| Họ tên | Bắt buộc; 2–150 ký tự hợp lệ | `Vui lòng nhập họ tên hợp lệ.` |
| Số điện thoại | Bắt buộc; SĐT di động VN | `Số điện thoại không hợp lệ.` |
| CCCD | Bắt buộc | `Vui lòng nhập số CCCD.` |
| CCCD | `^[0-9]{12}$` sau bỏ khoảng trắng (`EDGE-204`) | `Số CCCD phải gồm đúng 12 chữ số.` |
| Đồng ý xử lý dữ liệu | Phải tick | `Bạn cần đồng ý với điều khoản xử lý dữ liệu cá nhân để tiếp tục.` |
| Địa chỉ xưởng | Bắt buộc, 5–500 ký tự | `Vui lòng nhập địa chỉ xưởng (tối thiểu 5 ký tự).` |
| Toạ độ | Cùng có hoặc cùng trống; trong khoảng hợp lệ | `Vui lòng nhập đủ vĩ độ và kinh độ hợp lệ, hoặc để trống cả hai.` |
| Hotline | Bắt buộc; regex hotline | `Số hotline không hợp lệ.` |
| Số KTV mỗi ca | Bắt buộc; số nguyên `1..200` | `Số kỹ thuật viên phải từ 1 đến 200.` |
| Slot dự phòng | Số nguyên `>= 0` | `Số slot dự phòng không hợp lệ.` |
| Slot dự phòng | `<= totalTechnicians` (`EDGE-206`) | `Số slot dự phòng không được vượt quá số kỹ thuật viên.` |
| Giờ mở/đóng | Bắt buộc khi ngày mở cửa | `Vui lòng nhập giờ mở và giờ đóng.` |
| Giờ đóng | `closeTime > openTime` (`EDGE-205`) | `Giờ đóng cửa phải sau giờ mở cửa.` |
| Giờ hoạt động | Ít nhất 1 ngày mở cửa (`BR-206`) | `Xưởng phải mở cửa ít nhất 1 ngày trong tuần.` |
| Đồng ý chia sẻ cho hãng | Phải tick | `Bạn cần đồng ý chia sẻ Gmail và CCCD cho hãng để xác thực.` |

## 8.2 Validation Timing

- Blur từng field; toàn form khi submit, focus field lỗi đầu tiên (với giờ hoạt động: focus ô giờ của ngày lỗi đầu tiên).
- Validate chéo `emergencySlotsReserved` ↔ `totalTechnicians` mỗi khi một trong hai thay đổi.
- Không gọi API khi validate thất bại.
- `details.field` của server (vd `operatingHours[5].closeTime`) → gắn lỗi vào đúng ô.

---

# 9. Loading States

| Tình huống | UI |
|---|---|
| Khôi phục phiên (`API-201`) | Splash toàn màn |
| Đăng nhập | Nút Google disabled + spinner |
| Prefill (`API-202`) | Skeleton form, stepper vẫn hiển thị |
| Submit `API-203` / `API-204` | Nút submit disabled + spinner, form read-only, chặn gửi trùng |
| Chờ hãng (SCR-204) | Spinner + thông điệp theo mốc thời gian (mục 4.4) |

---

# 10. Empty States

## 10.1 Chưa có bản nháp vận hành

- **Condition:** `API-202.registration = null`.
- **UI:** SCR-203 hiển thị form với giá trị mặc định (giờ T2–T7 `08:00–17:30`, CN đóng; slot dự phòng `0`). Không phải lỗi.

## 10.2 Không có toạ độ

- **Condition:** `latitude/longitude = null`.
- **UI:** SCR-205 hiển thị `Chưa có vị trí trên bản đồ.`

---

# 11. Error States

## 11.1 General Error

```text
Không thể tải dữ liệu.
Vui lòng thử lại.

[Thử lại]
Mã lỗi: {traceId}
```

## 11.2 Error Mapping

| HTTP Status / Error Code | API | Frontend Behavior |
|---|---|---|
| `400 INVALID_REQUEST` | 203, 204 | Toast `Dữ liệu gửi lên không hợp lệ.` |
| `400 INVALID_FIELD_FORMAT` | 203, 204 | Lỗi inline theo `details.field` |
| `400 CONSENT_REQUIRED` | 203, 204 | Lỗi inline dưới checkbox tương ứng |
| `401 *` | All | `signOut()` → `/workshop/login` + `Phiên đăng nhập đã hết hạn.` |
| `403 UNSUPPORTED_SIGN_IN_PROVIDER` / `EMAIL_NOT_VERIFIED` | 201 | Ở lại login, thông điệp tương ứng |
| `403 ACCOUNT_SUSPENDED` / `ACCOUNT_INACTIVE` | All | `signOut()`, panel lỗi (như [US-005 FE SCR-103](./us-005-sprint-1-spec.fe.md#46-login-error--account-locked-scr-103)) (`EF-205`) |
| `403 ONBOARDING_REQUIRED` | API quản lý xưởng | Gọi `API-202` → `resolveWorkshopRoute()` |
| `404 WORKSHOP_OWNER_NOT_REGISTERED` | 202–204 | Gọi lại `API-201` |
| `409 EMAIL_ALREADY_LINKED` | 201 | `signOut()`, `error.message` + `Liên hệ hỗ trợ` |
| `409 PHONE_ALREADY_IN_USE` | 203 | Lỗi inline ô SĐT |
| `409 NATIONAL_ID_ALREADY_IN_USE` | 203 | Lỗi inline ô CCCD: `error.message` + link `Liên hệ hãng` (`EDGE-208`) |
| `409 ONBOARDING_ALREADY_COMPLETED` | 203, 204 | → `/technician` |
| `409 PROFILE_INCOMPLETE` | 204 | → SCR-202 |
| `409 VERIFICATION_IN_PROGRESS` | 203, 204 | → SCR-204 |
| `409 WORKSHOP_ALREADY_CLAIMED` | 204 | → SCR-206 `ALREADY_CLAIMED` (`EF-204`, AC-206) |
| `422 IDEMPOTENCY_KEY_REUSED` | 204 | Sinh key mới, yêu cầu người dùng nhấn gửi lại |
| `429 VERIFICATION_ATTEMPTS_EXCEEDED` | 204 | SCR-206 hết lượt: `error.message` + `Có thể thử lại sau {hh giờ mm phút}.` (AC-208) |
| `500` | All | General Error + `Thử lại` |
| Lỗi mạng | All | `Không có kết nối mạng. Vui lòng thử lại.` |

---

# 12. Error Handling

## 12.1 Field-level Error

Inline dưới field. Với giờ hoạt động, lỗi hiển thị ngay dưới hàng của ngày đó:

```text
Thứ 7   [●] Mở cửa   [12:00] – [08:00]
        Giờ đóng cửa phải sau giờ mở cửa.
```

## 12.2 Screen-level Error

`API-202` lỗi khi mở `/workshop/onboarding/*` → card lỗi thay nội dung, giữ header + stepper.

## 12.3 Retry Behavior

1. Chỉ gọi lại request lỗi, giữ dữ liệu đã nhập.
2. `API-204`: retry tự động do mạng dùng cùng key; người dùng nhấn gửi lại dùng key mới.
3. Sau khi `API-203` thành công, xoá CCCD khỏi state (không giữ dữ liệu nhạy cảm lâu hơn cần thiết).

---

# 13. Navigation

## 13.1 Routes

| Route | Screen | Guard |
|---|---|---|
| `/workshop/login` | SCR-201 | Đã đăng nhập cổng xưởng → `resolveWorkshopRoute()` |
| `/workshop/onboarding/profile` | SCR-202 | Đăng nhập, chưa `ACTIVE` |
| `/workshop/onboarding/operations` | SCR-203 | `profileCompleted = true` |
| `/workshop/onboarding/verifying` | SCR-204 | Đăng nhập |
| `/workshop/onboarding/success` | SCR-205 | `ACTIVE` |
| `/workshop/onboarding/failed` | SCR-206 | Đăng nhập |
| `/technician` | Dashboard xưởng (hiện có) | `RequireActiveWorkshopOwner` |

> `[Đề xuất]` FF giả định Workshop Portal là web app riêng. Codebase hiện tại là **một** app React có vai trò `technician`; spec đặt portal dưới tiền tố `/workshop/*` trong cùng app. Nếu tách app, chỉ đổi base path.

## 13.2 Navigation Rules

```text
resolveWorkshopRoute(onboarding):
  DASHBOARD  → /technician
  VERIFYING  → /workshop/onboarding/verifying
  PROFILE    → /workshop/onboarding/profile
  WORKSHOP   → status == VERIFICATION_FAILED ? /workshop/onboarding/failed
                                              : /workshop/onboarding/operations
```

- Từ SCR-203 Back → SCR-202. Từ SCR-204/205 không Back về form (`replace`).
- `401` → `/workshop/login` (không phải `/` của chủ xe).
- Đăng xuất từ header onboarding: theo [US-013 FE](./us-013-sprint-1-spec.fe.md).

---

# 14. Permission / Visibility

| UI Element | Condition |
|---|---|
| Luồng onboarding xưởng | Có phiên, đăng nhập qua cổng xưởng, chưa `ACTIVE` |
| Sidebar kỹ thuật viên (`/technician`, `/technician/quotes`, `/customers`) | `onboarding.status = ACTIVE` (`BR-203`) |
| Nút `Sửa CCCD` | `failureReason = NATIONAL_ID_MISMATCH` và còn lượt |
| Nút `Gửi lại` | `failureReason = OEM_UNAVAILABLE` và còn lượt |
| Hiển thị CCCD | Chỉ dạng mask từ API |

## 14.1 Role-based Behavior

| Role | Access |
|---|---|
| `WORKSHOP_OWNER` | Toàn bộ màn trong spec, chỉ dữ liệu của chính mình |
| `VEHICLE_USER` | Không truy cập `/workshop/*`; cùng Gmail vẫn có thể đăng ký tài khoản chủ xưởng riêng (`BR-209`) |

> Kiểm tra ở FE chỉ phục vụ UX. Backend quyết định (`get_current_workshop_owner`, `require_active_workshop_owner`).

---

# 15. Responsive / Device Behavior

## Mobile

- Form một cột; `OperatingHoursEditor` mỗi ngày là một card nhỏ (tên ngày + toggle trên, 2 ô giờ dưới).
- Nút submit full-width cuối form.

## Tablet / Desktop

- Workshop Portal ưu tiên desktop (chủ xưởng làm việc trên máy tính).
- SCR-203: 3 card xếp dọc, rộng tối đa `max-w-3xl`; bảng giờ hoạt động dạng lưới 4 cột (Ngày · Mở cửa · Giờ mở · Giờ đóng).
- SCR-205: 2 cột (thông tin hãng | vận hành + giờ hoạt động).

---

# 16. Accessibility

- Mỗi hàng giờ hoạt động có `aria-label` theo ngày (vd `Giờ mở cửa Thứ 2`).
- Toggle dùng `role="switch"` + `aria-checked`.
- Ô CCCD `autocomplete="off"`; không để trình duyệt lưu gợi ý.
- SCR-204 `role="status"`, `aria-live="polite"`.
- Lỗi inline gắn `aria-describedby`; focus field lỗi đầu tiên khi submit.

---

# 17. Analytics / Tracking

| Event | Trigger | Properties |
|---|---|---|
| `workshop_login_succeeded` | `API-201` 2xx | `isNewOwner`, `nextStep` |
| `workshop_onboarding_profile_submitted` | `API-203` 200 | — |
| `workshop_verification_submitted` | Nhấn `Gửi xác thực` | `totalTechnicians`, `openDays` |
| `workshop_verification_result` | Có kết quả | `status`, `failureReason` |
| `workshop_onboarding_completed` | Vào SCR-205 | `centerId` |

> Không gửi CCCD, SĐT, email, họ tên, địa chỉ.

---

# 18. Acceptance Criteria

## AC-FE-201 — Chủ xưởng mới (FF AC-201)

**Given** Gmail chưa có tài khoản chủ xưởng
**When** đăng nhập Google ở `/workshop/login`
**Then** FE gọi `POST /workshop-owner/oauth/sign-in`, nhận `nextStep = PROFILE` và mở SCR-202.

## AC-FE-202 — Lưu hồ sơ (FF AC-202)

**Given** SCR-202 nhập đủ họ tên, SĐT, CCCD 12 số và tick đồng ý
**When** nhấn `Tiếp tục`
**Then** FE gọi `PUT /workshop-owner/onboarding/profile` và mở SCR-203.

## AC-FE-203 — Chặn dữ liệu vận hành sai (FF EDGE-204 → EDGE-206)

**Given** slot dự phòng lớn hơn số KTV, hoặc một ngày có giờ đóng ≤ giờ mở, hoặc cả tuần đóng cửa
**When** nhấn `Gửi xác thực`
**Then** FE hiển thị lỗi inline tương ứng và không gọi API.

## AC-FE-204 — Gửi xác thực (FF AC-203)

**Given** SCR-203 hợp lệ
**When** nhấn `Gửi xác thực`
**Then** FE gửi `POST /workshop-owner/onboarding/workshop-verification` với `Idempotency-Key` mới, đủ 7 phần tử `operatingHours`.

## AC-FE-205 — Thành công (FF AC-204)

**Given** `API-204` trả `200 VERIFIED`
**Then** SCR-205 hiển thị tên xưởng, khu vực, loại xưởng do hãng trả về
**And** `Vào Dashboard` mở `/technician`.

## AC-FE-206 — Thất bại (FF AC-205)

**Given** `API-204` trả `200 FAILED` với `NATIONAL_ID_MISMATCH`
**Then** SCR-206 hiển thị thông điệp CCCD không khớp và nút `Sửa CCCD` mở SCR-202 với ô CCCD trống, được focus.

## AC-FE-207 — Xưởng đã có chủ (FF AC-206)

**Given** `API-204` trả `409 WORKSHOP_ALREADY_CLAIMED`
**Then** SCR-206 chỉ có hành động `Liên hệ hãng`, không có nút sửa/gửi lại.

## AC-FE-208 — Hết lượt (FF AC-208)

**Given** `API-204` trả `429` với `retryAfterSeconds = 5400`
**Then** FE hiển thị `Có thể thử lại sau 1 giờ 30 phút.` và ẩn nút gửi lại.

## AC-FE-209 — Hãng chậm (FF AC-209, EF-202)

**Given** `API-204` trả `202`
**Then** SCR-204 polling `GET /workshop-owner/onboarding` mỗi 3s trong 60s đầu, sau đó 30s
**And** sau 60s hiển thị thông điệp phản hồi chậm ~30 phút
**And** khi kết quả chuyển `VERIFICATION_FAILED / OEM_UNAVAILABLE`, FE mở SCR-206 với nút `Gửi lại`.

## AC-FE-210 — Đã Active (FF AC-207)

**Given** chủ xưởng `ACTIVE`
**When** đăng nhập lại
**Then** FE vào thẳng `/technician`.

---

# 19. Technical Notes

## Frontend Stack

```text
Framework: React 19 + Vite
Language: TypeScript
State Management: React Context (WorkshopAuthContext, WorkshopOnboardingContext)
Networking: fetch qua shared/api/client.ts
Navigation: React Router 7
UI Library: Tailwind CSS 4 + lucide-react
Auth: Firebase Web SDK (chung project với app chủ xe)
Testing: [Cần xác nhận — Vitest + Testing Library đề xuất]
```

## Component Structure

```text
frontend/src/features/workshop-auth/
├── context/WorkshopAuthContext.tsx
├── pages/WorkshopLogin.tsx               # SCR-201
├── guards/RequireActiveWorkshopOwner.tsx
└── onboarding/
    ├── WorkshopOnboardingLayout.tsx
    ├── WorkshopOnboardingContext.tsx
    ├── pages/OwnerProfileStep.tsx        # SCR-202
    ├── pages/OperationsStep.tsx          # SCR-203
    ├── components/OperatingHoursEditor.tsx
    ├── pages/Verifying.tsx               # SCR-204
    ├── pages/Success.tsx                 # SCR-205
    ├── pages/VerificationFailed.tsx      # SCR-206
    ├── api.ts                            # API-201 → API-204
    ├── validation.ts                     # CCCD, hotline, giờ hoạt động
    ├── navigation.ts                     # resolveWorkshopRoute()
    └── types.ts
```

## Implementation Notes

- **Hiện trạng:** `Login.tsx` có nút chọn vai trò "Kỹ thuật viên" giả lập. Spec này thay bằng cổng đăng nhập riêng `/workshop/login`; nút chọn vai trò bị bỏ.
- Dùng lại `GoogleSignInButton`, regex SĐT và `requestJson` của US-001.
- Giờ hoạt động luôn gửi đủ 7 phần tử theo thứ tự `dayOfWeek` 1..7, kể cả ngày đóng cửa.
- Giờ là giờ địa phương `Asia/Ho_Chi_Minh`, dạng chuỗi `HH:mm` — **không** chuyển sang UTC.

---

# 20. Open Questions

- [ ] **Q-FE-201** — Workshop Portal là app riêng (domain riêng) hay nằm dưới `/workshop/*` của app hiện tại?
- [ ] **Q-FE-202** — Có dùng bản đồ để chọn toạ độ xưởng không, nhà cung cấp nào? Spec hiện: 2 ô nhập tay, tuỳ chọn.
- [ ] **Q-FE-203** — Kênh "Liên hệ hãng" (hotline/email/form) là gì?
- [ ] **Q-FE-204** — Giá trị mặc định giờ hoạt động (T2–T7 08:00–17:30, CN đóng) có phù hợp không?
- [ ] **Q-FE-205** — Khi một trình duyệt đã đăng nhập vai trò chủ xe, mở `/workshop/login` thì xử lý thế nào (tự đăng xuất vai trò kia hay cho song song)?

---

# 21. Related Documents

- Functional Spec: [us-009-sprint-1-spec.ff.md](../feature-functional/us-009-sprint-1-spec.ff.md)
- API Specification: [us-009-sprint-1-spec.api.md](../api/us-009-sprint-1-spec.api.md)
- Entity Spec: [us-009-sprint-1-spec.entity.md](../entity/us-009-sprint-1-spec.entity.md)
- Core Entity: [core.entity.md](../../entity/core.entity.md)
- FE liên quan: [US-001 Onboarding chủ xe](./us-001-sprint-1-spec.fe.md) · [US-013 Đăng nhập/Đăng xuất chủ xưởng](./us-013-sprint-1-spec.fe.md)
- Design: [design-guidelines.md](../../../design/design-guidelines.md)

---

# 22. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Mai Văn Trung | Bản nháp đầu tiên, dựng từ FF v1.1 và API Spec v1.1 |
