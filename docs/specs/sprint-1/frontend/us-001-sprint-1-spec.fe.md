# Frontend Technical Specification — Đăng ký & Onboarding chủ xe qua Google OAuth

> Đặc tả frontend cho Feature `FEAT-AUTH-001` (US-001 → US-004).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-001-sprint-1-spec.ff.md) · **API:** [API Spec](../api/us-001-sprint-1-spec.api.md) · **Entity:** [Entity Spec](../entity/us-001-sprint-1-spec.entity.md)
>
> Frontend Spec **tuân theo** Functional Spec và API Spec, không định nghĩa lại nghiệp vụ. Điểm FE tự đề xuất được đánh dấu `[Đề xuất]`, điểm còn chờ Product được đánh dấu `[Cần xác nhận]` và gom ở mục 20.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-AUTH-001` — Đăng ký & Onboarding chủ xe qua Google OAuth |
| Screen | `SCR-001` Login · `SCR-002` Thông tin cá nhân & Địa điểm · `SCR-003` Thông tin xe · `SCR-004` Đang xác thực · `SCR-005` Thành công · `SCR-006` Xác thực thất bại |
| Route | `/` · `/onboarding/profile` · `/onboarding/vehicle` · `/onboarding/verifying` · `/onboarding/success` · `/onboarding/failed` |
| Version | `v1.0` |
| Author | Mai Văn Trung |
| FE Owner | Lê Đức Tùng |
| Status | `Draft` |
| Related PRD | [PRD_EV_Care_MVP.md](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-001-sprint-1-spec.ff.md#7-user-flow) |
| Related API | [API-001 → API-005](../api/us-001-sprint-1-spec.api.md) |
| Last Updated | `2026-09-29` |

---

# 2. Screen Overview

## 2.1 Purpose

Cho phép chủ xe chưa có tài khoản đăng nhập bằng Google (Firebase Authentication), sau đó đi qua luồng onboarding 3 bước: khai báo thông tin cá nhân + địa điểm gần đó → khai báo thông tin xe → chờ hãng xác thực quyền sở hữu. Khi hãng xác thực thành công, tài khoản chuyển `ACTIVE` và người dùng vào Home (`/dashboard`).

Frontend **không tự quyết định** bước tiếp theo: mọi điều hướng trong luồng dựa trên `onboarding.nextStep` do backend trả về (API Spec C.4).

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Mở ứng dụng (chưa có phiên Firebase) | — | Hiển thị `SCR-001` Login |
| Mở ứng dụng (đã có phiên Firebase) | Firebase `onAuthStateChanged` trả user | Gọi `API-001`, điều hướng theo `nextStep` |
| Truy cập route tính năng chính khi chưa `ACTIVE` | Guard phát hiện `onboarding.status != ACTIVE`, hoặc API trả `403 ONBOARDING_REQUIRED` | Điều hướng tới bước onboarding theo `nextStep` (`BR-003`) |
| Truy cập trực tiếp `/onboarding/*` | Đã đăng nhập | Gọi `API-002`, điều hướng về đúng bước nếu route không khớp `nextStep` |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| `nextStep = HOME` (tài khoản `ACTIVE`) | `/dashboard` |
| `nextStep = PROFILE` | `/onboarding/profile` |
| `nextStep = VEHICLE` và `onboarding.status = ONBOARDING_IN_PROGRESS` | `/onboarding/vehicle` |
| `nextStep = VEHICLE` và `onboarding.status = VERIFICATION_FAILED` | `/onboarding/failed` |
| `nextStep = VERIFYING` | `/onboarding/verifying` |
| Người dùng huỷ đăng nhập Google / lỗi Firebase | Ở lại `/` |
| `401` từ bất kỳ API nào | Firebase `signOut()` → `/` |
| Nhấn "Liên hệ hỗ trợ" | Kênh hỗ trợ `[Cần xác nhận — link/hotline]` |

## 2.4 Preconditions

- Frontend đã cấu hình Firebase Web SDK với Google Provider (biến môi trường `VITE_FIREBASE_*`).
- Người dùng có tài khoản Google hợp lệ, email đã xác minh.
- Người dùng có kết nối mạng.
- Với bước SCR-003: `profileCompleted = true` (nếu không, backend trả `409 PROFILE_INCOMPLETE`).

---

# 3. UI Structure

## 3.1 Layout

Các màn onboarding dùng **layout riêng** (không có sidebar/topbar của `AppLayout`), vì người dùng chưa được phép dùng tính năng chính.

```text
SCR-001 Login (/)
├── Left Panel (brand, headline, feature chips)      — giữ như hiện tại
└── Right Panel
    ├── Title "Đăng nhập"
    ├── Subtitle
    ├── Google Sign-in Button "Tiếp tục với Google"
    ├── Inline Error (khi đăng nhập thất bại)
    └── Footer (điều khoản / chính sách)

OnboardingLayout (/onboarding/*)
├── Header (logo EV Care, email Google, nút "Đăng xuất")
├── Stepper: 1. Thông tin cá nhân → 2. Thông tin xe → 3. Xác thực
└── Content
    ├── SCR-002 Profile Form
    │   ├── Họ tên
    │   ├── Số điện thoại
    │   ├── Ngày sinh (tuỳ chọn)
    │   ├── Địa điểm gần đó (địa chỉ + tỉnh/thành, quận/huyện, phường/xã)
    │   ├── Checkbox đồng ý xử lý dữ liệu cá nhân (+ link điều khoản)
    │   └── Button "Tiếp tục"
    ├── SCR-003 Vehicle Form
    │   ├── Số VIN
    │   ├── Biển số
    │   ├── Model (dropdown)
    │   ├── Năm sản xuất (tuỳ chọn)
    │   ├── Checkbox đồng ý chia sẻ dữ liệu xe cho hãng
    │   ├── Nút "Quay lại" (về SCR-002)
    │   └── Button "Xác nhận & Xác thực"
    ├── SCR-004 Verifying
    │   ├── Spinner + "Đang xác thực thông tin xe của bạn..."
    │   └── (sau 2 phút) Thông báo chờ lâu + nút "Kiểm tra lại" / "Để sau"
    ├── SCR-005 Success
    │   ├── Icon check
    │   ├── Tóm tắt xe (model, biển số, VIN) + bảo hành
    │   └── Button "Vào trang chủ"
    └── SCR-006 Verification Failed
        ├── Icon cảnh báo + thông điệp theo failureReason
        ├── Số lượt còn lại
        ├── Button "Sửa lại thông tin xe"
        └── Button "Liên hệ hỗ trợ"
```

## 3.2 Screen Layout Notes

- Theo [design-guidelines.md](../../../design/design-guidelines.md): nền `bg-background`, card `bg-card rounded-2xl border border-border`, CTA chính `bg-emerald text-background`.
- Form onboarding: một cột, rộng tối đa `max-w-xl`, căn giữa.
- VIN, biển số hiển thị bằng font mono (JetBrains Mono).
- Stepper luôn hiển thị bước hiện tại; bước đã xong có dấu check, không cho nhảy tới bước chưa tới.
- Login bỏ form email/mật khẩu và nút chọn vai trò hiện có (đăng ký bằng email/password nằm ngoài scope — FF §3.2). Vai trò được xác định theo cổng đăng nhập: chủ xe dùng `/`, chủ xưởng dùng cổng riêng (xem [US-009 FE](./us-009-sprint-1-spec.fe.md)).

---

# 4. Component Specification

## 4.1 Google Sign-in Button

| Property | Value |
|---|---|
| Component | `GoogleSignInButton` |
| Type | Button |
| Label | `Tiếp tục với Google` |
| Enabled When | Không có request đăng nhập đang chạy |
| Loading State | Disabled + spinner, label `Đang đăng nhập...` |
| Visibility | Always (SCR-001) |

### Behavior

1. Gọi Firebase `signInWithPopup(auth, new GoogleAuthProvider())`. Trên thiết bị chặn popup, fallback `signInWithRedirect`.
2. Lấy ID token bằng `user.getIdToken()`.
3. Gọi `API-001 POST /oauth/sign-in`.
4. Lưu `user` + `onboarding` vào `AuthContext`.
5. Điều hướng theo `onboarding.nextStep` (mục 13).

### UI Error

| Trường hợp | Thông điệp |
|---|---|
| Người dùng đóng popup (`auth/popup-closed-by-user`, `auth/cancelled-popup-request`) | Không hiện lỗi, chỉ reset trạng thái nút |
| Lỗi Firebase khác | `Đăng nhập Google không thành công. Vui lòng thử lại.` |
| Lỗi từ API-001 | Theo bảng mục 11.2 |

---

## 4.2 Profile Form (SCR-002)

| Property | Value |
|---|---|
| Component | `OnboardingProfileForm` |
| Type | Form |
| Data Source | Prefill từ `API-002` (`profile`, `location`, `consents`) |
| Submit | `API-003 PUT /onboarding/profile` |

### Fields

| Field | Component | Required | Default | Constraints | Ghi chú |
|---|---|---|---|---|---|
| `fullName` | `TextInput` | Yes | `profile.fullName` → nếu null lấy `displayName` từ Google | 2–150 ký tự sau trim | Chỉ chữ cái (có dấu), khoảng trắng, `'`, `-`, `.` |
| `phoneNumber` | `TextInput` (`type=tel`) | Yes | `profile.phoneNumber` | SĐT di động VN | Chấp nhận `0xxxxxxxxx`, `+84xxxxxxxxx`, có khoảng trắng / `.` / `-` |
| `dateOfBirth` | `DatePicker` | No | `profile.dateOfBirth` | Ngày trong quá khứ, `>= 1900-01-01` | Format hiển thị `DD/MM/YYYY`, gửi `YYYY-MM-DD` |
| `location.addressLine` | `TextInput` | Yes `[Cần xác nhận BR-005]` | `location.addressLine` | 5–500 ký tự | |
| `location.province` | `Select` | Yes | `location.province` | ≤ 100 | Danh sách tỉnh/thành tĩnh phía FE |
| `location.district` | `TextInput` / `Select` | No | `location.district` | ≤ 100 | |
| `location.ward` | `TextInput` | No | `location.ward` | ≤ 100 | |
| `location.source` | (ẩn) | Yes | `MANUAL` | `MANUAL` / `MAP_PICK` / `GPS` | MVP chỉ nhập tay → luôn `MANUAL` `[Đề xuất]` |
| `personalDataConsent.granted` | `Checkbox` | Yes | `consents.personalDataProcessing.granted` hoặc `false` | Phải `true` | Label có link mở điều khoản |

`personalDataConsent.policyVersion` lấy từ hằng số cấu hình FE `CONSENT_POLICY_VERSION` (mặc định `2026-09`) `[Cần xác nhận Q-A06]`.

### Behavior

- Khi mở màn: nếu `AuthContext` chưa có dữ liệu onboarding đầy đủ, gọi `API-002` để prefill (`AF-002`, `EDGE-001`).
- Nhấn "Tiếp tục" → validate toàn form (mục 8) → gọi `API-003` → thành công thì cập nhật `onboarding` và điều hướng theo `nextStep` (thường là `VEHICLE`).
- Không có nút "Quay lại" ở SCR-002 (đây là bước đầu).

---

## 4.3 Vehicle Form (SCR-003)

| Property | Value |
|---|---|
| Component | `OnboardingVehicleForm` |
| Type | Form |
| Data Source | Prefill từ `API-002.vehicle` (khi đã từng gửi); danh sách model từ `API-004` |
| Submit | `API-005 POST /onboarding/vehicle-verification` |

### Fields

| Field | Component | Required | Constraints | Ghi chú |
|---|---|---|---|---|
| `vin` | `TextInput` (font mono, tự uppercase) | Yes | Sau trim + uppercase: `^[A-HJ-NPR-Z0-9]{17}$` | Hiển thị bộ đếm `n/17`; helper: "17 ký tự, không có I, O, Q" |
| `licensePlate` | `TextInput` (font mono, tự uppercase) | Yes | Sau khi bỏ khoảng trắng/`.`/`-`: `^[0-9]{2}[A-Z]{1,2}[0-9]?[0-9]{4,5}$` | Placeholder `30A-123.45`; gửi nguyên chuỗi người dùng nhập, backend tự chuẩn hoá |
| `modelId` | `Select` | Yes | Một `modelId` trong danh sách API-004 | Hiển thị `"{modelName} {trim} ({productionYear})"` |
| `manufactureYear` | `NumberInput` / `Select` | No | `2015 .. (năm hiện tại + 1)` | |
| `oemDataSharingConsent.granted` | `Checkbox` | Yes | Phải `true` | Label: "Tôi đồng ý chia sẻ thông tin xe (VIN, biển số) cho hãng xe để xác thực quyền sở hữu." (FF §21) |

### Model Dropdown

| State | UI |
|---|---|
| Loading | Select disabled, placeholder `Đang tải mẫu xe...` |
| Loaded | Danh sách sắp theo `modelName`, `trim` (backend đã sắp) |
| Response có header `X-Data-Stale: true` | Vẫn cho chọn; không cần báo người dùng |
| `503 OEM_UNAVAILABLE` | Select disabled + lỗi inline `Không tải được danh sách mẫu xe.` + link `Thử lại` |

### Behavior

- Nhấn "Xác nhận & Xác thực":
  1. Validate toàn form (mục 8). Lỗi → không gọi API (`EDGE-005`).
  2. Sinh `Idempotency-Key` mới (UUID v4 — `crypto.randomUUID()`).
  3. Chuyển sang trạng thái submitting (nút disabled + spinner). Có thể hiển thị luôn SCR-004 trong khi chờ response đồng bộ (tối đa ~12s).
  4. Gọi `API-005` và xử lý kết quả theo mục 7.5.
- Nếu request lỗi mạng / timeout phía client: **tự retry 1 lần với cùng `Idempotency-Key`** (API Spec §13). Chỉ sinh key mới khi người dùng chủ động nhấn nút lần nữa.
- Nhấn "Quay lại" → `/onboarding/profile` (giữ dữ liệu form xe trong state).

---

## 4.4 Verifying Screen (SCR-004)

| Property | Value |
|---|---|
| Component | `VerifyingScreen` |
| Type | Status screen |
| Data Source | Polling `API-002` |
| Visibility | `nextStep = VERIFYING` hoặc đang chờ response `API-005` |

### Behavior

- Khi vào màn do `API-005` trả `202` hoặc do `nextStep = VERIFYING`: bắt đầu polling `API-002` mỗi **3 giây**, tối đa **2 phút** (API Spec API-002 §17).
- Mỗi lần poll: nếu `nextStep != VERIFYING` → dừng polling, điều hướng theo mục 13.
- Hết 2 phút mà vẫn `VERIFYING` → dừng polling, hiển thị trạng thái "chờ lâu" (`EF-002`):
  - Thông điệp: `Hệ thống hãng đang xử lý lâu hơn dự kiến. Chúng tôi sẽ cập nhật kết quả sớm.`
  - Nút `Kiểm tra lại` → gọi `API-002` một lần, nếu vẫn `VERIFYING` thì chạy lại chu kỳ polling.
  - Nút `Để sau` → Firebase `signOut()` và về `/`. Lần đăng nhập sau sẽ quay lại đúng màn này (`AF-002`) `[Cần xác nhận Q-A01]`.
- Dừng polling khi rời màn (unmount) hoặc tab bị ẩn (`document.visibilityState = hidden`), tiếp tục khi tab hiện lại.

---

## 4.5 Success Screen (SCR-005)

| Property | Value |
|---|---|
| Component | `OnboardingSuccess` |
| Data Source | Response `API-005` (VERIFIED) hoặc `API-002` (`vehicle`, `warranties`) |

### Behavior

- Hiển thị: model + phiên bản (`spec.modelName spec.trim`), biển số, VIN, danh sách bảo hành (`component`, `endDate`, `kmLimit`, `status`).
- `warranties = []` → hiển thị `Chưa có thông tin bảo hành từ hãng.` (API Rule 6) — không coi là lỗi.
- Nút `Vào trang chủ` → `/dashboard` (replace history, không cho Back về onboarding).
- Nhãn component bảo hành: `BATTERY` → Pin, `MOTOR` → Động cơ, `CHASSIS` → Khung gầm, `ELECTRONICS` → Điện tử.

---

## 4.6 Verification Failed Screen (SCR-006)

| Property | Value |
|---|---|
| Component | `VerificationFailed` |
| Data Source | `verification` từ `API-005` hoặc `latestVerification` + `remainingAttempts` từ `API-002` |

### Nội dung theo `failureReason`

| `failureReason` | Tiêu đề / Thông điệp | Hành động chính | Hành động phụ |
|---|---|---|---|
| `VIN_NOT_FOUND` | `Không tìm thấy số VIN trên hệ thống hãng. Vui lòng kiểm tra lại số VIN.` | `Sửa lại thông tin xe` | `Liên hệ hỗ trợ` |
| `PLATE_MISMATCH` | `Biển số không khớp với số VIN trên hệ thống hãng. Vui lòng kiểm tra lại.` | `Sửa lại thông tin xe` | `Liên hệ hỗ trợ` |
| `OWNER_MISMATCH` | `Thông tin chủ xe trên hệ thống hãng không khớp với tài khoản của bạn.` | `Liên hệ hỗ trợ` | `Sửa lại thông tin xe` |
| `OEM_UNAVAILABLE` | `Hệ thống hãng tạm thời không phản hồi. Vui lòng thử lại sau.` | `Gửi lại` (về SCR-003 với dữ liệu cũ) | `Liên hệ hỗ trợ` |
| `ALREADY_LINKED` | `Xe đã được đăng ký bởi tài khoản khác. Vui lòng liên hệ bộ phận hỗ trợ.` | `Liên hệ hỗ trợ` | `Nhập xe khác` |

- Ưu tiên hiển thị `verification.message` từ backend; bảng trên là fallback khi message rỗng.
- Hiển thị `Bạn còn {remainingAttempts} lần thử trong 24 giờ.` khi `remainingAttempts <= 2`.
- `remainingAttempts = 0` → ẩn nút sửa/gửi lại, chỉ còn `Liên hệ hỗ trợ` + thông điệp giới hạn (mục 11.2 — `429`).
- `Sửa lại thông tin xe` → `/onboarding/vehicle`, prefill VIN/biển số/model đã gửi; highlight trường liên quan (`vin` cho `VIN_NOT_FOUND`, `licensePlate` cho `PLATE_MISMATCH`).

---

## 4.7 Onboarding Guard

| Property | Value |
|---|---|
| Component | `RequireActiveUser` (route wrapper) |
| Áp dụng | Mọi route bên trong `AppLayout` của chủ xe |

### Behavior

- Chưa có phiên Firebase → `/`.
- Có phiên nhưng `onboarding.status != ACTIVE` → điều hướng theo `nextStep` (`BR-003`).
- Trong lúc đang khôi phục phiên (chờ `onAuthStateChanged` + `API-001`) → hiển thị splash/spinner toàn màn, không render trang đích.

---

# 5. User Interaction

## 5.1 Interaction Flow

```text
Mở /  ──►  Nhấn "Tiếp tục với Google"
             │
             ▼
        Firebase popup ──(huỷ/lỗi)──► ở lại Login
             │ OK
             ▼
        POST /oauth/sign-in
             │
             ├── nextStep = HOME ─────────────► /dashboard
             ├── nextStep = VERIFYING ────────► /onboarding/verifying
             ├── nextStep = VEHICLE ──────────► /onboarding/vehicle hoặc /onboarding/failed
             └── nextStep = PROFILE ──────────► /onboarding/profile
                                                   │ PUT /onboarding/profile
                                                   ▼
                                             /onboarding/vehicle
                                                   │ GET /onboarding/vehicle-models
                                                   │ POST /onboarding/vehicle-verification
                                                   ▼
                        ┌──────────── 200 VERIFIED ─► /onboarding/success ─► /dashboard
                        ├──────────── 200 FAILED ───► /onboarding/failed ─► (sửa) /onboarding/vehicle
                        ├──────────── 202 PENDING ──► /onboarding/verifying (polling GET /onboarding)
                        └──────────── 409 VEHICLE_ALREADY_LINKED ─► /onboarding/failed (ALREADY_LINKED)
```

## 5.2 Interaction Table

| User Action | Frontend Behavior | Result |
|---|---|---|
| Nhấn "Tiếp tục với Google" | Firebase sign-in → `API-001` | Điều hướng theo `nextStep` |
| Đóng popup Google | Reset nút, không hiện lỗi | Ở lại Login |
| Nhập SĐT rồi rời ô | Validate format | Lỗi inline nếu sai |
| Nhấn "Tiếp tục" (SCR-002) | Validate → `API-003` | `/onboarding/vehicle` |
| Mở SCR-003 | Gọi `API-004` | Dropdown model có dữ liệu |
| Gõ VIN | Tự uppercase, đếm ký tự | Lỗi inline khi rời ô nếu sai |
| Nhấn "Xác nhận & Xác thực" | Validate → sinh key → `API-005` | SCR-004 / 005 / 006 |
| Ở SCR-004 | Polling `API-002` 3s, tối đa 2 phút | Tự chuyển màn khi có kết quả |
| Nhấn "Sửa lại thông tin xe" | Điều hướng + prefill | SCR-003 |
| Nhấn "Đăng xuất" ở header onboarding | Firebase `signOut()`, xoá state | `/` |

---

# 6. State Management

## 6.1 State Model

```text
AuthContext (toàn app)
├── firebaseUser            (Firebase User | null)
├── authStatus              ('initializing' | 'signed-out' | 'signed-in')
├── user                    (API-001 user)
└── onboarding              (OnboardingState)

OnboardingState (store theo luồng — React context trong OnboardingLayout)
├── snapshot                (response API-002)
├── profileForm             { fullName, phoneNumber, dateOfBirth, location, consentGranted }
├── vehicleForm             { vin, licensePlate, modelId, manufactureYear, consentGranted }
├── vehicleModels           ({ items, isLoading, error })
├── verification            (API-005 verification | null)
├── idempotencyKey          (string | null)
├── polling                 { isPolling, startedAt, timedOut }
└── request                 { isLoading, isSubmitting, error, fieldErrors }
```

## 6.2 State Fields

| State | Type | Default | Description |
|---|---|---|---|
| `authStatus` | `'initializing' \| 'signed-out' \| 'signed-in'` | `'initializing'` | Trạng thái khôi phục phiên Firebase |
| `user` | `SignInUser \| null` | `null` | Thông tin tài khoản từ `API-001` |
| `onboarding` | `OnboardingState \| null` | `null` | `status`, `nextStep`, `profileCompleted`, … |
| `profileForm` | `ProfileForm` | prefill từ `API-002` | Dữ liệu SCR-002 |
| `vehicleForm` | `VehicleForm` | prefill từ `API-002.vehicle` | Dữ liệu SCR-003 |
| `vehicleModels.items` | `VehicleModel[]` | `[]` | Từ `API-004` |
| `verification` | `Verification \| null` | `null` | Kết quả `API-005` |
| `remainingAttempts` | `number \| null` | `null` | Từ `API-002` / `API-005` |
| `idempotencyKey` | `string \| null` | `null` | Key của lần nhấn gửi hiện tại |
| `polling.isPolling` | `boolean` | `false` | Đang polling ở SCR-004 |
| `polling.timedOut` | `boolean` | `false` | Đã quá 2 phút |
| `isSubmitting` | `boolean` | `false` | Đang gọi `API-003` / `API-005` |
| `fieldErrors` | `Record<string, string>` | `{}` | Lỗi theo field (client hoặc `details.field` từ server) |
| `error` | `AppError \| null` | `null` | Lỗi cấp màn hình |

> Dữ liệu cá nhân (SĐT, địa chỉ, VIN) **không** lưu vào `localStorage`. Khôi phục khi quay lại luôn dựa vào `API-002`.

---

# 7. API Integration

> Hợp đồng chi tiết nằm ở [API Spec](../api/us-001-sprint-1-spec.api.md). Mục này chỉ mô tả cách FE dùng API.

## 7.0 Quy ước chung

- Mọi request gắn `Authorization: Bearer <firebase_id_token>` lấy từ `auth.currentUser.getIdToken()` (Firebase tự refresh khi token sắp hết hạn).
- Gắn `X-Request-ID` (UUID) cho mỗi request để đối chiếu log; khi hiện lỗi `500` hiển thị kèm mã `traceId`.
- Response thành công: `{ "data": ... }` → FE đọc `data`.
- Response lỗi: `{ "error": { code, message, details, traceId } }` → FE map theo `error.code` (mục 11.2); nếu không có mapping thì hiển thị `error.message`.
- Cần mở rộng `requestJson` trong [client.ts](../../../../frontend/src/shared/api/client.ts): tự gắn token, trả về `data`, và ném `ApiError` có `code`, `message`, `details`, `traceId`, `status`, header `Retry-After`.

## 7.1 Sign-in — `API-001`

```http
POST /api/v1/oauth/sign-in
```

### Trigger

- Sau khi Firebase sign-in thành công (nút Google).
- Khi app khởi động và `onAuthStateChanged` trả user (khôi phục phiên).

### Mapping

| Frontend State | API Response |
|---|---|
| `user` | `data.user` |
| `onboarding` | `data.onboarding` |

### Success

`201` hoặc `200` → lưu state → điều hướng theo `data.onboarding.nextStep`.

### Failure

Theo mục 11.2. Với mọi lỗi `401`/`403`/`409` của API này: gọi Firebase `signOut()` để không giữ phiên Firebase "treo".

---

## 7.2 Get Onboarding — `API-002`

```http
GET /api/v1/onboarding
```

### Trigger

- Mở trực tiếp một route `/onboarding/*` (reload trang, deep link).
- Polling ở SCR-004 (3s / tối đa 2 phút).
- Mở SCR-006 khi chưa có `verification` trong state.

### Mapping

| Frontend State | API Response |
|---|---|
| `onboarding` | `data.onboarding` |
| `profileForm.fullName` / `phoneNumber` / `dateOfBirth` | `data.profile.*` |
| `profileForm.location` | `data.location` |
| `profileForm.consentGranted` | `data.consents.personalDataProcessing.granted` |
| `vehicleForm.vin` / `licensePlate` / `modelId` / `manufactureYear` | `data.vehicle.vin` / `licensePlate` / `declaredModelId` / `declaredManufactureYear` |
| `vehicleForm.consentGranted` | `data.consents.oemDataSharing.granted` |
| `verification` | `data.latestVerification` |
| `remainingAttempts` | `data.remainingAttempts` |

### Failure

- `404 USER_NOT_REGISTERED` → gọi lại `API-001` một lần rồi điều hướng theo kết quả.
- Lỗi mạng khi polling → bỏ qua lượt đó, tiếp tục lượt sau; 3 lượt lỗi liên tiếp → dừng polling, hiện lỗi có nút `Thử lại`.

---

## 7.3 Save Profile — `API-003`

```http
PUT /api/v1/onboarding/profile
```

### Trigger

Nhấn `Tiếp tục` ở SCR-002 sau khi validate thành công.

### Request Mapping

```json
{
  "fullName": "{profileForm.fullName (trim)}",
  "phoneNumber": "{profileForm.phoneNumber}",
  "dateOfBirth": "{profileForm.dateOfBirth | null}",
  "location": {
    "addressLine": "{profileForm.location.addressLine}",
    "ward": "{profileForm.location.ward | null}",
    "district": "{profileForm.location.district | null}",
    "province": "{profileForm.location.province}",
    "latitude": null,
    "longitude": null,
    "source": "MANUAL",
    "placeId": null
  },
  "personalDataConsent": {
    "granted": true,
    "policyVersion": "{CONSENT_POLICY_VERSION}"
  }
}
```

### Success

`200` → cập nhật `onboarding` = `data.onboarding` → điều hướng theo `nextStep`.

### Failure

`400 INVALID_FIELD_FORMAT` → gán `error.message` vào `fieldErrors[details.field]`. Còn lại theo mục 11.2.

---

## 7.4 Load Vehicle Models — `API-004`

```http
GET /api/v1/onboarding/vehicle-models
```

### Trigger

Mở SCR-003 (gọi một lần mỗi phiên; cache trong state cho tới khi rời luồng onboarding).

### Mapping

| Frontend State | API Response |
|---|---|
| `vehicleModels.items` | `data.items` |

### Failure

`503 OEM_UNAVAILABLE` → lỗi inline ở dropdown + `Thử lại` (mục 4.3). Các field khác vẫn nhập được nhưng nút gửi disabled cho tới khi chọn được model.

---

## 7.5 Submit Vehicle Verification — `API-005`

```http
POST /api/v1/onboarding/vehicle-verification
Idempotency-Key: <uuid-v4>
```

### Trigger

Nhấn `Xác nhận & Xác thực` ở SCR-003.

### Request Mapping

```json
{
  "vin": "{vehicleForm.vin (trim + uppercase)}",
  "licensePlate": "{vehicleForm.licensePlate}",
  "modelId": "{vehicleForm.modelId}",
  "manufactureYear": "{vehicleForm.manufactureYear | null}",
  "oemDataSharingConsent": {
    "granted": true,
    "policyVersion": "{CONSENT_POLICY_VERSION}"
  }
}
```

### Kết quả

| HTTP | `verification.status` | Frontend |
|---|---|---|
| `200` | `VERIFIED` | Lưu `vehicle`, `warranties`, `onboarding` → `/onboarding/success` |
| `200` | `FAILED` | Lưu `verification`, `remainingAttempts` → `/onboarding/failed` |
| `202` | `PENDING` | → `/onboarding/verifying`, bắt đầu polling `API-002` |
| `409` | `VEHICLE_ALREADY_LINKED` | → `/onboarding/failed` với `failureReason = ALREADY_LINKED` |
| `409` | `VERIFICATION_IN_PROGRESS` | → `/onboarding/verifying`, polling |
| `409` | `PROFILE_INCOMPLETE` | → `/onboarding/profile` |
| `409` | `ONBOARDING_ALREADY_COMPLETED` | → `/dashboard` |
| `429` | `VERIFICATION_ATTEMPTS_EXCEEDED` | → `/onboarding/failed`, trạng thái hết lượt (dùng `details.retryAfterSeconds`) |

> Thất bại do hãng từ chối là **HTTP 200**, không phải lỗi (API Spec C.6). FE không được hiển thị toast lỗi chung cho trường hợp này.

---

# 8. Client-side Validation

## 8.1 Validation Rules

| Field | Rule | Error Message |
|---|---|---|
| Họ tên | Bắt buộc | `Vui lòng nhập họ tên.` |
| Họ tên | 2–150 ký tự sau trim; chỉ chữ cái, khoảng trắng, `'`, `-`, `.` | `Họ tên không hợp lệ.` |
| Số điện thoại | Bắt buộc | `Vui lòng nhập số điện thoại.` |
| Số điện thoại | Sau khi bỏ khoảng trắng/`.`/`-`: `^(0\|\+84)(3\|5\|7\|8\|9)[0-9]{8}$` | `Số điện thoại không hợp lệ.` |
| Ngày sinh | Nếu nhập: trước hôm nay và `>= 01/01/1900` | `Ngày sinh không hợp lệ.` |
| Địa chỉ | Bắt buộc, 5–500 ký tự | `Vui lòng nhập địa chỉ (tối thiểu 5 ký tự).` |
| Tỉnh/thành | Bắt buộc | `Vui lòng chọn tỉnh/thành phố.` |
| Đồng ý xử lý dữ liệu | Phải tick | `Bạn cần đồng ý với điều khoản xử lý dữ liệu cá nhân để tiếp tục.` |
| VIN | Bắt buộc | `Vui lòng nhập số VIN.` |
| VIN | `^[A-HJ-NPR-Z0-9]{17}$` sau uppercase | `Số VIN phải gồm 17 ký tự chữ và số, không chứa I, O, Q.` |
| Biển số | Bắt buộc | `Vui lòng nhập biển số xe.` |
| Biển số | `^[0-9]{2}[A-Z]{1,2}[0-9]?[0-9]{4,5}$` sau chuẩn hoá | `Biển số xe không hợp lệ.` |
| Model | Bắt buộc | `Vui lòng chọn mẫu xe.` |
| Năm sản xuất | Nếu nhập: `2015 .. năm hiện tại + 1` | `Năm sản xuất không hợp lệ.` |
| Đồng ý chia sẻ dữ liệu cho hãng | Phải tick | `Bạn cần đồng ý chia sẻ thông tin xe cho hãng để xác thực.` |

## 8.2 Validation Timing

- Validate từng field khi blur.
- Validate toàn form khi nhấn nút submit; focus vào field lỗi đầu tiên.
- Không gọi API khi validate phía client thất bại.
- Lỗi từ server có `details.field` → hiển thị inline dưới field đó (field name khớp camelCase của request).

---

# 9. Loading States

## 9.1 Khôi phục phiên (App start)

- **Condition:** `authStatus = 'initializing'` (chờ Firebase + `API-001`).
- **UI:** Splash toàn màn (logo + spinner). Không render Login hay trang đích để tránh nháy màn.

## 9.2 Đăng nhập

- **Condition:** Đang chạy Firebase popup hoặc `API-001`.
- **UI:** Nút Google disabled + spinner. Chặn double-click.

## 9.3 Prefill onboarding

- **Condition:** Đang gọi `API-002` khi mở `/onboarding/*`.
- **UI:** Skeleton cho form; stepper vẫn hiển thị.

## 9.4 Tải danh sách model

- **Condition:** Đang gọi `API-004`.
- **UI:** Dropdown model disabled với placeholder `Đang tải mẫu xe...`.

## 9.5 Submit

- **Condition:** Đang gọi `API-003` / `API-005`.
- **UI:** Nút submit disabled + spinner; toàn bộ input read-only; chặn gửi trùng.

## 9.6 Chờ hãng xác thực

- **Condition:** SCR-004.
- **UI:** Spinner lớn + `Đang xác thực thông tin xe của bạn...`; sau 2 phút đổi sang trạng thái "chờ lâu" (mục 4.4).

---

# 10. Empty States

## 10.1 Không có mẫu xe

- **Condition:** `API-004` trả `items = []`.
- **UI:** Dropdown disabled, thông điệp `Chưa có danh sách mẫu xe từ hãng.` + `Thử lại`.

## 10.2 Không có bảo hành

- **Condition:** `warranties = []` khi `VERIFIED`.
- **UI:** Ở SCR-005: `Chưa có thông tin bảo hành từ hãng.` Vẫn cho `Vào trang chủ`.

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
| `400 INVALID_REQUEST` | 003, 005 | Toast `Dữ liệu gửi lên không hợp lệ. Vui lòng kiểm tra lại.` |
| `400 INVALID_FIELD_FORMAT` | 003, 005 | Lỗi inline theo `details.field`, nội dung `error.message` |
| `400 CONSENT_REQUIRED` | 003, 005 | Lỗi inline dưới checkbox đồng ý |
| `401 UNAUTHORIZED` / `INVALID_TOKEN` / `TOKEN_REVOKED` | All | Firebase `signOut()` → `/`, toast `Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.` |
| `403 UNSUPPORTED_SIGN_IN_PROVIDER` | 001 | Ở lại Login: `Vui lòng đăng nhập bằng tài khoản Google.` |
| `403 EMAIL_NOT_VERIFIED` | 001 | Ở lại Login: `Email Google của bạn chưa được xác minh.` |
| `403 ACCOUNT_SUSPENDED` / `ACCOUNT_INACTIVE` | All | `signOut()` → Login, hiển thị `error.message` + link hỗ trợ (`EDGE-004`) |
| `403 ONBOARDING_REQUIRED` | API tính năng chính | Gọi `API-002`, điều hướng theo `nextStep` (`BR-003`) |
| `404 USER_NOT_REGISTERED` | 002–005 | Gọi lại `API-001`, điều hướng theo kết quả |
| `409 EMAIL_ALREADY_LINKED` | 001 | `signOut()`, ở lại Login: `error.message` + link hỗ trợ |
| `409 PHONE_ALREADY_IN_USE` | 003 | Lỗi inline ở ô SĐT |
| `409 ONBOARDING_ALREADY_COMPLETED` | 003, 005 | → `/dashboard` |
| `409 PROFILE_INCOMPLETE` | 005 | → `/onboarding/profile` |
| `409 VERIFICATION_IN_PROGRESS` | 003, 005 | → `/onboarding/verifying` |
| `409 VEHICLE_ALREADY_LINKED` | 005 | → SCR-006 dạng `ALREADY_LINKED` (`EF-004`) |
| `422 IDEMPOTENCY_KEY_REUSED` | 005 | Sinh key mới, không tự gửi lại; toast `Vui lòng nhấn gửi lại.` (lỗi lập trình — log) |
| `429 VERIFICATION_ATTEMPTS_EXCEEDED` | 005 | SCR-006 hết lượt: `error.message` + `Bạn có thể thử lại sau {hh giờ mm phút}.` (từ `details.retryAfterSeconds` / `Retry-After`) + `Liên hệ hỗ trợ` |
| `503 OEM_UNAVAILABLE` | 004 | Lỗi inline ở dropdown model + `Thử lại` |
| `500 DATABASE_ERROR` / `INTERNAL_SERVER_ERROR` | All | General Error (11.1) + `Thử lại` |
| Lỗi mạng / timeout client | All | `Không có kết nối mạng. Vui lòng kiểm tra và thử lại.` + `Thử lại` |

---

# 12. Error Handling

## 12.1 Field-level Error

Hiển thị ngay dưới field, màu `text-error`, kèm icon; field có viền `border-error`. Ví dụ:

```text
Số VIN
[RLLVF6AB1PH00012       ] 16/17
Số VIN phải gồm 17 ký tự chữ và số, không chứa I, O, Q.
```

## 12.2 Screen-level Error

Dùng khi `API-002` không tải được lúc mở `/onboarding/*`, hoặc lỗi `500` khi submit. Hiển thị card lỗi thay cho nội dung form, giữ stepper và header.

## 12.3 Retry Behavior

1. Chỉ gọi lại request bị lỗi.
2. Giữ nguyên dữ liệu người dùng đã nhập.
3. Với `API-005`: retry tự động do lỗi mạng dùng **cùng** `Idempotency-Key`; người dùng nhấn gửi lại thì dùng key **mới**.

---

# 13. Navigation

## 13.1 Routes

| Route | Screen | Layout | Guard |
|---|---|---|---|
| `/` | SCR-001 Login | Không layout | Nếu đã đăng nhập → điều hướng theo `nextStep` |
| `/onboarding/profile` | SCR-002 | `OnboardingLayout` | Đã đăng nhập, chưa `ACTIVE` |
| `/onboarding/vehicle` | SCR-003 | `OnboardingLayout` | Đã đăng nhập, `profileCompleted = true` |
| `/onboarding/verifying` | SCR-004 | `OnboardingLayout` | Đã đăng nhập |
| `/onboarding/success` | SCR-005 | `OnboardingLayout` | `status = ACTIVE` |
| `/onboarding/failed` | SCR-006 | `OnboardingLayout` | Đã đăng nhập |
| `/dashboard` | Home | `AppLayout` | `RequireActiveUser` |

## 13.2 Navigation Rules

### Điều hướng theo `nextStep`

```text
resolveOnboardingRoute(onboarding):
  HOME       → /dashboard
  VERIFYING  → /onboarding/verifying
  PROFILE    → /onboarding/profile
  VEHICLE    → status == VERIFICATION_FAILED ? /onboarding/failed : /onboarding/vehicle
```

Hàm này là **điểm duy nhất** quyết định route của luồng onboarding; mọi màn gọi chung.

### Authentication Required

```text
401
 ↓
Firebase signOut()
 ↓
Login (/)
 ↓
Đăng nhập lại → điều hướng theo nextStep
```

### Back Action

- Từ SCR-003 Back → SCR-002 (giữ dữ liệu form xe).
- Từ SCR-004/005 không cho Back về form (dùng `navigate(..., { replace: true })`).
- Back không gọi API ghi dữ liệu.

---

# 14. Permission / Visibility

| UI Element | Condition |
|---|---|
| Luồng onboarding | Có phiên Firebase, `onboarding.status != ACTIVE` |
| Sidebar / tính năng chính | `onboarding.status = ACTIVE` (`BR-003`) |
| Nút `Sửa lại thông tin xe` | `remainingAttempts > 0` và `failureReason != ALREADY_LINKED` |
| Nút `Gửi lại` | `failureReason = OEM_UNAVAILABLE` |

## 14.1 Role-based Behavior

| Role | Access |
|---|---|
| `VEHICLE_USER` | Toàn bộ màn trong spec này, chỉ dữ liệu của chính mình |
| Chủ xưởng | Không dùng luồng này (xem [US-009 FE](./us-009-sprint-1-spec.fe.md)) |

> Kiểm tra quyền ở FE chỉ phục vụ UX. Backend là nơi quyết định (`get_current_user`, `require_active_user`).

---

# 15. Responsive / Device Behavior

## Mobile (< 768px)

- Login: ẩn panel trái, chỉ còn form (như hiện tại).
- Form một cột, input full-width, nút submit full-width ở cuối form.
- Stepper rút gọn: `Bước 1/3 · Thông tin cá nhân`.
- Firebase: ưu tiên `signInWithRedirect` nếu popup bị chặn.

## Tablet

- Form căn giữa, rộng tối đa `max-w-xl`.

## Desktop

- Login 2 cột (55% / 45%) như hiện tại.
- Onboarding: form căn giữa; SCR-005 có thể chia 2 cột (thông tin xe | bảo hành).

---

# 16. Accessibility

- Mọi input có `<label>` gắn `htmlFor`; lỗi gắn `aria-describedby` và `aria-invalid="true"`.
- Nút Google có `aria-label="Đăng nhập bằng Google"`.
- SCR-004 dùng `role="status"` + `aria-live="polite"` để trình đọc màn hình đọc thay đổi trạng thái.
- Không chỉ dùng màu để báo lỗi (có icon + chữ).
- Khi submit lỗi, focus vào field lỗi đầu tiên.
- Stepper có `aria-current="step"` cho bước hiện tại.

---

# 17. Analytics / Tracking

| Event | Trigger | Properties |
|---|---|---|
| `login_google_clicked` | Nhấn nút Google | — |
| `login_succeeded` | `API-001` 2xx | `isNewUser`, `nextStep` |
| `login_failed` | Firebase lỗi hoặc `API-001` lỗi | `errorCode` |
| `onboarding_profile_submitted` | `API-003` 200 | — |
| `onboarding_vehicle_submitted` | Nhấn "Xác nhận & Xác thực" | `modelId` |
| `vehicle_verification_result` | Có kết quả `API-005` / polling | `status`, `failureReason`, `remainingAttempts` |
| `onboarding_completed` | Vào SCR-005 | — |

> Không gửi SĐT, email, địa chỉ, VIN, biển số vào analytics (FF §21, API C.8).

---

# 18. Acceptance Criteria

## AC-FE-001 — Người dùng mới được đưa vào onboarding (FF AC-001)

**Given** người dùng chưa có tài khoản
**When** họ đăng nhập Google thành công
**Then** FE gọi `POST /oauth/sign-in`, nhận `nextStep = PROFILE`
**And** FE điều hướng tới `/onboarding/profile`.

## AC-FE-002 — Không gọi API khi dữ liệu sai định dạng (FF EDGE-005)

**Given** người dùng nhập VIN 16 ký tự hoặc có chữ `O`
**When** nhấn `Xác nhận & Xác thực`
**Then** FE hiển thị lỗi inline dưới ô VIN
**And** FE không gọi `API-005`.

## AC-FE-003 — Gửi xác thực xe (FF AC-002)

**Given** người dùng đã hoàn tất SCR-002 và nhập hợp lệ SCR-003
**When** nhấn `Xác nhận & Xác thực`
**Then** FE gửi `POST /onboarding/vehicle-verification` kèm `Idempotency-Key` mới
**And** nút chuyển sang trạng thái loading, không gửi trùng.

## AC-FE-004 — Xác thực thành công (FF AC-003)

**Given** `API-005` trả `200` với `verification.status = VERIFIED`
**Then** FE hiển thị SCR-005 với thông tin xe và bảo hành
**And** nhấn `Vào trang chủ` đưa tới `/dashboard`, Back không quay lại onboarding.

## AC-FE-005 — Xác thực thất bại (FF AC-004)

**Given** `API-005` trả `200` với `verification.status = FAILED`, `failureReason = PLATE_MISMATCH`
**Then** FE hiển thị SCR-006 với thông điệp tương ứng
**And** nhấn `Sửa lại thông tin xe` mở SCR-003 đã điền sẵn dữ liệu cũ, ô biển số được highlight.

## AC-FE-006 — Hãng phản hồi chậm (FF EF-002)

**Given** `API-005` trả `202 PENDING`
**Then** FE hiển thị SCR-004 và polling `GET /onboarding` mỗi 3 giây
**And** khi `nextStep` đổi, FE tự chuyển sang SCR-005 hoặc SCR-006
**And** sau 2 phút chưa có kết quả, FE dừng polling và hiển thị thông báo chờ lâu kèm `Kiểm tra lại` / `Để sau`.

## AC-FE-007 — Tài khoản đã Active (FF AC-005)

**Given** người dùng đã `ACTIVE`
**When** đăng nhập lại bằng Google
**Then** FE điều hướng thẳng tới `/dashboard`, không hiển thị màn onboarding nào.

## AC-FE-008 — Tiếp tục onboarding dang dở (FF AF-002, EDGE-001)

**Given** người dùng đã lưu SCR-002 rồi thoát app
**When** đăng nhập lại
**Then** FE điều hướng tới `/onboarding/vehicle` và không bắt nhập lại SCR-002.

## AC-FE-009 — Xe đã liên kết tài khoản khác (FF EF-004)

**Given** `API-005` trả `409 VEHICLE_ALREADY_LINKED`
**Then** FE hiển thị SCR-006 với thông điệp "Xe đã được đăng ký bởi tài khoản khác" và nút `Liên hệ hỗ trợ` là hành động chính.

---

# 19. Technical Notes

## Frontend Stack

```text
Framework: React 19 + Vite
Language: TypeScript
State Management: React Context (AuthContext, OnboardingContext) + useState/useReducer
Networking: fetch qua shared/api/client.ts (requestJson)
Navigation: React Router 7
UI Library: Tailwind CSS 4 + lucide-react
Auth: Firebase Web SDK (firebase/auth) — cần thêm dependency `firebase`
Testing: [Cần xác nhận — Vitest + Testing Library đề xuất]
```

## Component Structure

```text
frontend/src/
└── features/
    └── auth/
        ├── context/AuthContext.tsx          # thay mock role bằng Firebase + API-001
        ├── firebase.ts                      # khởi tạo Firebase app/auth
        ├── pages/Login.tsx                  # SCR-001
        ├── guards/RequireActiveUser.tsx
        └── onboarding/
            ├── OnboardingLayout.tsx
            ├── OnboardingContext.tsx
            ├── pages/ProfileStep.tsx        # SCR-002
            ├── pages/VehicleStep.tsx        # SCR-003
            ├── pages/Verifying.tsx          # SCR-004
            ├── pages/Success.tsx            # SCR-005
            ├── pages/VerificationFailed.tsx # SCR-006
            ├── api.ts                       # API-001 → API-005
            ├── validation.ts                # regex VIN, biển số, SĐT
            ├── navigation.ts                # resolveOnboardingRoute()
            └── types.ts
```

## Implementation Notes

- **Hiện trạng:** `AuthContext` đang giả lập vai trò, `Login.tsx` là form email/mật khẩu mock, chưa có Firebase. Spec này thay thế hoàn toàn luồng giả lập cho chủ xe.
- `requestJson` hiện ném `ApiError(status, detail)` với `detail` là toàn bộ body; cần chuẩn hoá thành `error.code` / `error.message` / `error.details` / `traceId` theo envelope C.3.
- `fetch` coi `202` là `ok` → `requestJson` phải trả kèm `status` để phân biệt `200` và `202` ở `API-005`.
- Regex VIN / biển số / SĐT đặt ở `validation.ts`, dùng chung với US-009 (CCCD, SĐT).
- Không đặt logic "bước tiếp theo" trong component; chỉ dùng `resolveOnboardingRoute()`.

---

# 20. Open Questions

- [ ] **Q-FE-001** (FF Q-001, API Q-A04) — Địa điểm nhập tay hay chọn trên bản đồ? Spec đang dùng nhập tay (`source = MANUAL`), bắt buộc.
- [ ] **Q-FE-002** (FF Q-004, API Q-A01) — Khi hãng chậm quá 2 phút, "Để sau" có cho vào Home tạm với trạng thái "Chờ xác thực" không? Spec hiện: đăng xuất, lần sau quay lại SCR-004.
- [ ] **Q-FE-003** (API Q-A06) — Nội dung điều khoản consent hiển thị ở đâu (trang tĩnh FE hay API trả)? `policyVersion` do ai cấp?
- [ ] **Q-FE-004** — Kênh "Liên hệ hỗ trợ" là gì (hotline, email, Discord, form)?
- [ ] **Q-FE-005** (API §3.3) — Regex biển số `^[0-9]{2}[A-Z]{1,2}[0-9]?[0-9]{4,5}$` đã đủ cho các loại biển VN chưa? Cần backend + FE thống nhất.
- [ ] **Q-FE-006** — Danh sách tỉnh/thành: dùng danh sách tĩnh ở FE hay có API?

---

# 21. Related Documents

- PRD: [PRD_EV_Care_MVP.md](../../../product/PRD_EV_Care_MVP.md)
- Functional Spec: [us-001-sprint-1-spec.ff.md](../feature-functional/us-001-sprint-1-spec.ff.md)
- API Specification: [us-001-sprint-1-spec.api.md](../api/us-001-sprint-1-spec.api.md)
- Entity Spec: [us-001-sprint-1-spec.entity.md](../entity/us-001-sprint-1-spec.entity.md)
- Design: [design-guidelines.md](../../../design/design-guidelines.md) · [wireframe.md](../../../design/wireframe.md)
- FE liên quan: [US-005 Đăng nhập/Đăng xuất chủ xe](./us-005-sprint-1-spec.fe.md)

---

# 22. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Mai Văn Trung | Bản nháp đầu tiên, dựng từ FF v1.0 và API Spec v1.0 |
