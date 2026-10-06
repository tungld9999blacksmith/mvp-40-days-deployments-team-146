# Frontend Technical Specification — Nhắc mốc bảo dưỡng & cấu hình thông báo

> **Cập nhật phạm vi (02/10/2026):** các phần dưới đây trong tài liệu này không còn áp dụng.
>
> - Kết nối Discord (`user_discord_link`, ENT-417): **đã bỏ**. Nhắc bảo dưỡng, nhắc lịch hẹn và hỏi thăm hiện trong mục **Thông báo** của app; danh sách kênh ngoài (Zalo / Telegram / SMS / Email) vẫn có nhưng đều "Sắp có", bật nhắc không bắt buộc chọn kênh.

> Đặc tả frontend cho Feature `FEAT-NOTI-001` (PRD F7 phần nhắc mốc + NOTI-01, US-021 → US-024).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-021-sprint-2-spec.ff.md) · **API:** [API Spec](../api/us-021-sprint-2-spec.api.md) · **Entity:** [Entity Spec](../entity/us-021-sprint-2-spec.entity.md)
>
> **Phạm vi FE:** chỉ màn **Cài đặt thông báo** (SCR-501) và **banner mời kết nối Discord** trên Home. Việc tạo và gửi nhắc (JOB-NOTI-001, `NotificationService`, adapter) chạy hoàn toàn ở backend, không có UI. Danh sách thông báo trong app (`/notifications`) **không** thuộc feature này — chưa có API.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-NOTI-001` — Nhắc mốc bảo dưỡng & cấu hình thông báo |
| Screen | `SCR-501` Cài đặt thông báo · Banner kết nối Discord trên `SCR-301` Home |
| Route | `/notifications/settings` · `/dashboard` (banner) |
| Version | `v1.0` |
| Author | Mai Văn Trung |
| FE Owner | Mai Văn Trung |
| Status | `Draft` |
| Related PRD | [PRD_EV_Care_MVP.md §F7](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-021-sprint-2-spec.ff.md#7-user-flow) |
| Related API | [API-NOTI-001, API-NOTI-002](../api/us-021-sprint-2-spec.api.md) |
| Last Updated | `2026-09-29` |

---

# 2. Screen Overview

## 2.1 Purpose

Chủ xe tự quyết định:

- Có nhận nhắc mốc bảo dưỡng hay không (bật/tắt).
- Nhắc trước hạn bao nhiêu ngày (0–30, mặc định 2).
- Nhận qua kênh nào (MVP: chỉ **Discord** chọn được; Zalo / Telegram / SMS / Email hiển thị "Sắp có").

Và được nhắc kết nối Discord khi kênh đã bật nhưng chưa có nơi nhận (BR-507).

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Trang `/notifications` | Nhấn nút `Cài đặt` (icon bánh răng) ở header | `/notifications/settings` |
| Banner Discord trên Home | Nhấn `Kết nối Discord` / `Cài đặt thông báo` | `/notifications/settings` |
| Menu tài khoản (topbar) `[Đề xuất]` | Nhấn `Cài đặt thông báo` | `/notifications/settings` |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| Nhấn Back | Màn trước đó |
| Lưu thành công | Ở lại màn, toast `Đã lưu cài đặt thông báo.` |
| Rời màn khi còn thay đổi chưa lưu | Hộp thoại xác nhận (mục 13.2) |
| `401` | Login |
| `403 ONBOARDING_REQUIRED` | Onboarding |

## 2.4 Preconditions

- Chủ xe `ACTIVE`.
- Chưa từng lưu cấu hình vẫn xem được: API trả giá trị mặc định (AC-509).

---

# 3. UI Structure

## 3.1 Layout

```text
SCR-501 Cài đặt thông báo (/notifications/settings)
├── Header: "Cài đặt thông báo" + mô tả ngắn
├── Card "Nhắc bảo dưỡng"
│   ├── Switch "Bật nhắc bảo dưỡng"
│   │     └── Mô tả: "Nhận thông báo khi xe sắp đến mốc bảo dưỡng hoặc đã quá hạn."
│   └── Field "Nhắc trước hạn"  [ - ] [ 2 ] [ + ]  ngày
│         ├── Helper: "0 = nhắc đúng ngày đến hạn. Mặc định: {defaultReminderLeadDays} ngày."
│         └── Helper: "Bạn cũng được nhắc khi xe còn dưới 500 km tới mốc." (ngưỡng km — BR-501)
├── Card "Kênh nhận thông báo"
│   ├── Row Discord    [Checkbox] · Badge "Đã kết nối" / "Chưa kết nối" · [Kết nối Discord]
│   ├── Row Zalo       [Checkbox disabled] · Badge "Sắp có"
│   ├── Row Telegram   [Checkbox disabled] · Badge "Sắp có"
│   ├── Row SMS        [Checkbox disabled] · Badge "Sắp có"
│   ├── Row Email      [Checkbox disabled] · Badge "Sắp có"
│   └── Inline error (NO_CHANNEL_ENABLED)
├── Info note: "Thay đổi áp dụng từ lần kiểm tra kế tiếp (08:00 hằng ngày)."
└── Footer: [Huỷ thay đổi] [Lưu]  (sticky)

Home (/dashboard) — bổ sung
└── DiscordConnectBanner (trên cùng nội dung)
    ├── Icon Bell + "Bạn chưa kết nối Discord nên sẽ không nhận được nhắc bảo dưỡng."
    ├── Button "Kết nối Discord"
    └── Button đóng (x)
```

## 3.2 Screen Layout Notes

- Premium Dark theo [design-guidelines.md](../../../design/design-guidelines.md). Switch/checkbox bật dùng màu emerald.
- Khi tắt "Bật nhắc bảo dưỡng": card "Nhắc trước hạn" và card kênh vẫn hiển thị nhưng **mờ** (`opacity-50`) và disabled — giữ nguyên giá trị để bật lại không mất cấu hình.
- Footer `Lưu` chỉ enable khi form có thay đổi (`isDirty`) và hợp lệ.

---

# 4. Component Specification

## 4.1 Reminders Switch

| Property | Value |
|---|---|
| Component | `Switch` |
| Label | `Bật nhắc bảo dưỡng` |
| Field | `remindersEnabled` |
| Default | Từ `API-NOTI-001` (mặc định hệ thống `true`) |

### Behavior

- Đổi giá trị → cập nhật `form.remindersEnabled`, `isDirty = true`.
- Bật lại khi không có kênh nào bật → hiện lỗi `NO_CHANNEL_ENABLED` phía client (mục 8).

---

## 4.2 Lead Days Input

| Property | Value |
|---|---|
| Component | `NumberStepper` (nút `−` / ô số / nút `+`) |
| Label | `Nhắc trước hạn` · đơn vị `ngày` |
| Field | `reminderLeadDays` |
| Required | Yes (khi `remindersEnabled = true`) |
| Min / Max | `0` / `30` |
| Step | `1` |
| Default | Từ API (`reminderLeadDays`), hiển thị thêm `Mặc định: {defaultReminderLeadDays} ngày` |
| Disabled When | `remindersEnabled = false` hoặc đang lưu |

### Behavior

- Chỉ cho nhập số nguyên; nút `−` disabled ở `0`, `+` disabled ở `30`.
- Link nhỏ `Đặt về mặc định` khi giá trị khác `defaultReminderLeadDays`.

---

## 4.3 Channel List

| Property | Value |
|---|---|
| Component | `NotificationChannelList` |
| Data Source | `API-NOTI-001.channels[]` |
| Field | `channels[].enabled` |

### Hiển thị từng kênh

| `channel` | Nhãn | Icon |
|---|---|---|
| `DISCORD` | `Discord` | Discord / `MessageSquare` |
| `ZALO` | `Zalo` | `MessageCircle` |
| `TELEGRAM` | `Telegram` | `Send` |
| `SMS` | `Tin nhắn SMS` | `Smartphone` |
| `EMAIL` | `Email` | `Mail` |
| Kênh lạ (enum mới) | Tên `channel` | `Bell` — xử lý như `COMING_SOON` (API §19) |

### Trạng thái theo `status`

| `status` | Badge | Checkbox | Hành động phụ |
|---|---|---|---|
| `CONNECTED` | `Đã kết nối` (emerald) | Enabled | — |
| `NOT_CONNECTED` | `Chưa kết nối` (warning) | Enabled | Nút `Kết nối Discord` |
| `COMING_SOON` / `available = false` | `Sắp có` (muted) | **Disabled**, không chọn được (BR-506) | — |

- Discord `enabled = true` + `NOT_CONNECTED` → hiển thị cảnh báo dưới dòng: `Bạn sẽ không nhận được nhắc qua Discord cho tới khi kết nối.` (EF-501).

### Nút "Kết nối Discord"

- Luồng kết nối Discord (OAuth2, bot tạo kênh riêng — ENT-417) **chưa có API** (FF §3.2, API §24).
- `[Đề xuất]` Giai đoạn này nút hiển thị nhưng mở dialog: `Tính năng kết nối Discord sẽ sớm có. Vui lòng quay lại sau.` Khi có API, nút chuyển sang mở URL OAuth2 của Discord và quay về `/notifications/settings?discord=connected`.

---

## 4.4 Save Bar

| Property | Value |
|---|---|
| Component | `SettingsSaveBar` |
| Buttons | `Huỷ thay đổi` (secondary) · `Lưu` (primary) |
| Enabled When | `isDirty && isValid && !isSaving` |
| Loading State | `Lưu` disabled + spinner |

### Behavior

1. `Lưu` → validate (mục 8) → gọi `API-NOTI-002` với **chỉ các trường đã đổi** (mục 7.2).
2. `200` → cập nhật `saved` = response, reset `isDirty`, toast `Đã lưu cài đặt thông báo. Thay đổi áp dụng từ lần kiểm tra kế tiếp.`
3. Lỗi → giữ nguyên dữ liệu người dùng đã chỉnh, hiển thị lỗi (mục 11).
4. `Huỷ thay đổi` → khôi phục `form` = `saved`.

---

## 4.5 Discord Connect Banner (Home)

| Property | Value |
|---|---|
| Component | `DiscordConnectBanner` |
| Data Source | `API-NOTI-001` (gọi khi mở Home) |
| Visibility | `remindersEnabled = true` **và** kênh `DISCORD` có `enabled = true` **và** `status = NOT_CONNECTED` |

### Behavior

- `Kết nối Discord` → `/notifications/settings` (focus vào dòng Discord).
- Nút `x` → ẩn banner trong phiên hiện tại (`sessionStorage`), hiện lại ở phiên sau nếu vẫn chưa kết nối.
- `API-NOTI-001` lỗi → không hiển thị banner (không làm Home lỗi).

> FF SCR-301 mô tả banner hiện khi "lần nhắc gần nhất ở trạng thái chưa có nơi nhận". API hiện **không** trả trạng thái delivery, nên FE dùng điều kiện tương đương gần nhất ở trên. Xem Q-FE-NOTI-01.

---

# 5. User Interaction

## 5.1 Interaction Flow

```text
Mở /notifications/settings
   ↓
GET /notification-settings  →  form = saved = data
   ↓
Người dùng chỉnh switch / số ngày / kênh   (isDirty = true)
   ↓
Nhấn "Lưu"
   ↓
Validate client ──(lỗi)──► hiện lỗi inline, không gọi API
   ↓ OK
PUT /notification-settings (chỉ trường đã đổi)
   ├── 200 → saved = data, toast thành công
   └── 4xx/5xx → giữ form, hiện lỗi
```

## 5.2 Interaction Table

| User Action | Frontend Behavior | Result |
|---|---|---|
| Mở màn | `API-NOTI-001` | Form có giá trị hiện tại (AC-509) |
| Tắt switch | Làm mờ các card bên dưới | `remindersEnabled = false` (AC-506 sau khi lưu) |
| Đổi số ngày 2 → 5 | Cập nhật form | Sau lưu: nhắc khi còn 5 ngày (AC-502) |
| Bỏ tick Discord khi đang bật nhắc | Lỗi inline `Chọn ít nhất một kênh` | Không cho lưu (BR-505) |
| Nhấn checkbox kênh `Sắp có` | Không có tác dụng (disabled), tooltip `Kênh này sắp được hỗ trợ.` | (AC-510) |
| Nhấn `Lưu` | `API-NOTI-002` | Toast thành công |
| Rời màn khi chưa lưu | Hộp thoại xác nhận | Ở lại / bỏ thay đổi |

---

# 6. State Management

## 6.1 State Model

```text
NotificationSettingsState
├── saved          NotificationSettings | null     (bản đã lưu — từ API)
├── form           { remindersEnabled, reminderLeadDays, channels: Record<Channel, boolean> }
├── isDirty        boolean                         (form khác saved)
├── fieldErrors    { reminderLeadDays?, channels? }
├── request        { isLoading, isSaving, error }
```

## 6.2 State Fields

| State | Type | Default | Description |
|---|---|---|---|
| `saved` | `NotificationSettings \| null` | `null` | Response gần nhất của `API-NOTI-001/002` |
| `form.remindersEnabled` | `boolean` | `saved.remindersEnabled` | |
| `form.reminderLeadDays` | `number` | `saved.reminderLeadDays` | |
| `form.channels` | `Record<NotificationChannel, boolean>` | từ `saved.channels[].enabled` | |
| `isDirty` | `boolean` | `false` | So sánh sâu `form` với `saved` |
| `fieldErrors` | object | `{}` | Lỗi client hoặc map từ mã lỗi server |
| `request.isLoading` | `boolean` | `true` | Đang gọi `API-NOTI-001` |
| `request.isSaving` | `boolean` | `false` | Đang gọi `API-NOTI-002` |

Banner Home dùng một lần gọi `API-NOTI-001` riêng (không chia sẻ form state).

---

# 7. API Integration

> Hợp đồng chi tiết: [API Spec](../api/us-021-sprint-2-spec.api.md). Quy ước chung theo [US-001 FE §7.0](../../sprint-1/frontend/us-001-sprint-1-spec.fe.md#70-quy-ước-chung).

## 7.1 Xem cấu hình — `API-NOTI-001`

```http
GET /api/v1/notification-settings
```

### Trigger

- Mở `/notifications/settings`.
- Mở Home (cho banner).
- Quay lại từ luồng kết nối Discord (khi có).

### Mapping

| Frontend State | API Response |
|---|---|
| `saved`, `form.remindersEnabled` | `data.remindersEnabled` |
| `form.reminderLeadDays` | `data.reminderLeadDays` |
| Helper "Mặc định" | `data.defaultReminderLeadDays` |
| `form.channels[c]` | `data.channels[].enabled` |
| Badge / disabled | `data.channels[].status`, `.available` |

Thứ tự hiển thị kênh: theo thứ tự mảng API trả về.

---

## 7.2 Lưu cấu hình — `API-NOTI-002`

```http
PUT /api/v1/notification-settings
```

### Trigger

Nhấn `Lưu`.

### Request Mapping

Chỉ gửi trường đã đổi so với `saved` (API cho phép partial; kênh không gửi giữ nguyên):

```json
{
  "remindersEnabled": "{form.remindersEnabled — nếu đổi}",
  "reminderLeadDays": "{form.reminderLeadDays — nếu đổi}",
  "channels": [
    { "channel": "DISCORD", "enabled": "{form.channels.DISCORD}" }
  ]
}
```

- `channels` chỉ chứa kênh có `enabled` thay đổi, và **không bao giờ** chứa kênh `available = false` với `enabled = true`.
- Nếu không có gì thay đổi, không gọi API (nút `Lưu` đã disabled).

### Success

`200` → `saved = form = data`, `isDirty = false`, toast.

### Failure

Mục 11.2.

---

# 8. Client-side Validation

## 8.1 Validation Rules

| Field | Rule | Error Message |
|---|---|---|
| Nhắc trước hạn | Số nguyên | `Vui lòng nhập số ngày hợp lệ.` |
| Nhắc trước hạn | `0 ≤ x ≤ 30` (BR-504) | `Số ngày nhắc trước phải từ 0 đến 30.` |
| Kênh | Khi `remindersEnabled = true`: ít nhất 1 kênh `enabled` (BR-505) | `Chọn ít nhất một kênh nhận thông báo, hoặc tắt nhắc bảo dưỡng.` |
| Kênh | Không bật kênh `available = false` (BR-506) | (không xảy ra — checkbox disabled) |

## 8.2 Validation Timing

- Validate ngay khi giá trị thay đổi (form nhỏ, phản hồi tức thì).
- Validate toàn form trước khi gọi `API-NOTI-002`; không gọi API khi có lỗi.

---

# 9. Loading States

## 9.1 Tải cấu hình

- **Condition:** `API-NOTI-001` đang chạy.
- **UI:** Skeleton cho 2 card; footer ẩn.

## 9.2 Lưu

- **Condition:** `isSaving = true`.
- **UI:** Nút `Lưu` spinner + disabled; mọi input disabled; chặn gửi trùng.

---

# 10. Empty States

Không có empty state: API luôn trả cấu hình (mặc định nếu chủ xe chưa từng lưu — AC-509) và luôn trả đủ danh sách kênh của hệ thống.

---

# 11. Error States

## 11.1 General Error

Khi `API-NOTI-001` lỗi (thay nội dung màn):

```text
Không tải được cài đặt thông báo.
Vui lòng thử lại.

[Thử lại]
```

## 11.2 Error Mapping

| HTTP Status / Error Code | API | Frontend Behavior |
|---|---|---|
| `400 INVALID_REQUEST` | 002 | Toast `Không lưu được cài đặt. Vui lòng thử lại.` (lỗi lập trình — log) |
| `401 UNAUTHORIZED` / `INVALID_TOKEN` | 001, 002 | Interceptor → Login ([US-005 FE](../../sprint-1/frontend/us-005-sprint-1-spec.fe.md)) |
| `403 ONBOARDING_REQUIRED` | 001, 002 | Điều hướng onboarding |
| `403 FORBIDDEN` | 001, 002 | Chủ xưởng: về `/technician` |
| `422 INVALID_LEAD_DAYS` | 002 | Lỗi inline dưới ô số ngày: `error.message` |
| `422 CHANNEL_NOT_AVAILABLE` | 002 | Toast `Kênh này chưa được hỗ trợ.`, gọi lại `API-NOTI-001` để làm mới danh sách kênh (AC-510) |
| `422 NO_CHANNEL_ENABLED` | 002 | Lỗi inline ở card kênh |
| `500` | 001, 002 | 001: General Error; 002: toast lỗi + giữ form để lưu lại |
| Lỗi mạng | 001, 002 | `Không có kết nối mạng.` + `Thử lại` |

---

# 12. Error Handling

## 12.1 Field-level Error

- Số ngày: dưới ô `NumberStepper`.
- Kênh: dưới danh sách kênh.

## 12.2 Screen-level Error

Chỉ khi `API-NOTI-001` lỗi lúc mở màn.

## 12.3 Retry Behavior

- `Thử lại` gọi lại `API-NOTI-001`.
- Lưu lỗi: người dùng nhấn `Lưu` lần nữa; form giữ nguyên thay đổi.

---

# 13. Navigation

## 13.1 Routes

| Route | Purpose |
|---|---|
| `/notifications/settings` | SCR-501 Cài đặt thông báo (mới) |
| `/notifications` | Danh sách thông báo (hiện có, dùng mock — ngoài phạm vi) — thêm nút `Cài đặt` |
| `/dashboard` | Home — banner Discord |

## 13.2 Navigation Rules

- Rời màn khi `isDirty = true` (Back, đổi menu) → dialog: `Bạn có thay đổi chưa lưu. Rời trang?` · `Ở lại` / `Rời trang` (dùng `useBlocker` của React Router).
- Sau khi lưu thành công: ở lại màn.

---

# 14. Permission / Visibility

| UI Element | Condition |
|---|---|
| SCR-501 | Chủ xe `ACTIVE` |
| Checkbox kênh | Enabled khi `available = true` và `remindersEnabled = true` |
| Nút `Kết nối Discord` | `DISCORD.status = NOT_CONNECTED` |
| Banner Home | Mục 4.5 |

## 14.1 Role-based Behavior

| Role | Access |
|---|---|
| Chủ xe | Xem / sửa cấu hình của mình |
| Chủ xưởng | Không có màn này (`403 FORBIDDEN` — FF §3.2) |

---

# 15. Responsive / Device Behavior

## Mobile

- Card xếp dọc, full-width; save bar dính đáy màn hình, 2 nút chia đôi.
- Mỗi dòng kênh: tên + badge dòng trên, nút `Kết nối Discord` dòng dưới.

## Tablet / Desktop

- Nội dung rộng tối đa `max-w-2xl`; save bar dính đáy khung nội dung.

---

# 16. Accessibility

- Switch: `role="switch"`, `aria-checked`, `aria-describedby` trỏ tới mô tả.
- `NumberStepper`: `<input type="number" min=0 max=30>` có label; nút `−`/`+` có `aria-label` "Giảm một ngày" / "Tăng một ngày".
- Checkbox kênh disabled có `aria-disabled="true"` và mô tả "Sắp có".
- Lỗi inline gắn `aria-describedby`; toast dùng `role="status"`.

---

# 17. Analytics / Tracking

| Event | Trigger | Properties |
|---|---|---|
| `notification_settings_viewed` | Mở SCR-501 | `remindersEnabled`, `reminderLeadDays` |
| `notification_settings_saved` | `API-NOTI-002` 200 | `remindersEnabled`, `reminderLeadDays`, `enabledChannels` |
| `notification_settings_save_failed` | `API-NOTI-002` lỗi | `errorCode` |
| `discord_connect_clicked` | Nhấn `Kết nối Discord` | `source` (`settings` / `home_banner`) |
| `discord_banner_dismissed` | Đóng banner | — |

---

# 18. Acceptance Criteria

## AC-FE-501 — Cấu hình mặc định (FF AC-509)

**Given** chủ xe chưa từng lưu cấu hình
**When** mở `/notifications/settings`
**Then** switch bật, số ngày `2`, Discord được tick; Zalo/Telegram/SMS/Email hiển thị `Sắp có` và không tick được.

## AC-FE-502 — Đổi số ngày (FF AC-502)

**Given** chủ xe đổi số ngày thành `5` và nhấn `Lưu`
**Then** FE gửi `PUT /notification-settings` với `{"reminderLeadDays": 5}`
**And** hiển thị toast thành công, `Lưu` trở lại disabled.

## AC-FE-503 — Số ngày ngoài khoảng (FF BR-504)

**Given** chủ xe nhập `31`
**Then** FE hiện lỗi `Số ngày nhắc trước phải từ 0 đến 30.` và không gọi API.

## AC-FE-504 — Tắt nhắc (FF AC-506)

**Given** chủ xe tắt switch và lưu
**Then** FE gửi `{"remindersEnabled": false}`; các card bên dưới mờ đi nhưng giữ giá trị.

## AC-FE-505 — Không kênh nào bật (FF BR-505, EDGE-509)

**Given** nhắc đang bật và chủ xe bỏ tick Discord
**Then** FE hiện lỗi `Chọn ít nhất một kênh…` và không cho lưu.

## AC-FE-506 — Kênh chưa hỗ trợ (FF AC-510)

**Given** kênh SMS có `available = false`
**Then** checkbox SMS disabled, FE không bao giờ gửi `{"channel":"SMS","enabled":true}`
**And** nếu server vẫn trả `422 CHANNEL_NOT_AVAILABLE` (danh sách kênh vừa đổi), FE báo lỗi và tải lại cấu hình.

## AC-FE-507 — Chưa kết nối Discord (FF AC-507)

**Given** nhắc bật, Discord `enabled = true`, `status = NOT_CONNECTED`
**Then** SCR-501 hiện badge `Chưa kết nối` + cảnh báo không nhận được nhắc
**And** Home hiển thị banner mời kết nối Discord.

## AC-FE-508 — Rời màn khi chưa lưu

**Given** `isDirty = true`
**When** chủ xe chuyển trang
**Then** FE hỏi xác nhận trước khi bỏ thay đổi.

---

# 19. Technical Notes

## Frontend Stack

```text
Framework: React 19 + Vite
Language: TypeScript
State Management: useReducer cục bộ trong trang
Networking: fetch qua shared/api/client.ts
Navigation: React Router 7 (useBlocker cho cảnh báo rời trang)
UI Library: Tailwind CSS 4 + lucide-react
```

## Component Structure

```text
frontend/src/features/notifications/
├── api.ts                                  # getNotificationSettings(), updateNotificationSettings()
├── types.ts                                # NotificationSettings, NotificationChannel, ChannelStatus
├── pages/Notifications.tsx                 # hiện có — thêm nút "Cài đặt"
├── pages/NotificationSettings.tsx          # SCR-501
└── components/
    ├── NotificationChannelList.tsx
    ├── NumberStepper.tsx                   # có thể đưa vào shared/ui
    ├── SettingsSaveBar.tsx
    └── DiscordConnectBanner.tsx            # dùng trên Dashboard
```

## Implementation Notes

- Backend đã có `GET` / `PUT /api/v1/notification-settings` ([backend/src/modules/notification/route.py](../../../../backend/src/modules/notification/route.py)); kênh Discord hiện là adapter ghi log (chưa gửi thật).
- Trang [Notifications.tsx](../../../../frontend/src/features/notifications/pages/Notifications.tsx) đang dùng `mocks/notifications.ts`; việc nối danh sách thông báo thật cần API mới (ngoài spec này).
- `isDirty` so sánh `form` với `saved` theo giá trị, không theo tham chiếu.
- Diff request: dựng body từ các trường khác `saved` để tránh ghi đè kênh ngoài ý muốn.

---

# 20. Open Questions

- [ ] **Q-FE-NOTI-01** — Banner Home theo FF cần biết "lần nhắc gần nhất `no_recipient`", nhưng API không trả trạng thái delivery. Có bổ sung field (vd `lastReminderDeliveryStatus`) vào `API-NOTI-001` không, hay chấp nhận điều kiện `Discord bật + NOT_CONNECTED`?
- [ ] **Q-FE-NOTI-02** — Luồng "Kết nối Discord" (OAuth2 + bot) khi nào có API? Trước đó nút hiển thị dialog "sắp có".
- [ ] **Q-FE-NOTI-03** — Helper "nhắc khi còn dưới 500 km" cần số `DUE_SOON_KM` thật; có thêm vào response `API-NOTI-001` không (hiện chỉ có ở `API-VEH-003.thresholds`)?
- [ ] **Q-FE-NOTI-04** — Danh sách thông báo trong app (`/notifications`) có nằm trong MVP không? Nếu có cần API liệt kê `reminder` / `reminder_delivery`.
- [ ] Nghiệp vụ còn mở: [FF §24](../feature-functional/us-021-sprint-2-spec.ff.md#24-open-questions) (Q-501 → Q-506).

---

# 21. Related Documents

- PRD: [PRD_EV_Care_MVP.md §F7](../../../product/PRD_EV_Care_MVP.md)
- Functional Spec: [us-021-sprint-2-spec.ff.md](../feature-functional/us-021-sprint-2-spec.ff.md)
- API Specification: [us-021-sprint-2-spec.api.md](../api/us-021-sprint-2-spec.api.md)
- Entity Spec: [us-021-sprint-2-spec.entity.md](../entity/us-021-sprint-2-spec.entity.md)
- FE liên quan: [US-017 Hồ sơ xe & trạng thái đến hạn](./us-017-sprint-2-spec.fe.md)

---

# 22. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Mai Văn Trung | Bản nháp đầu tiên, dựng từ FF v1.0 và API Spec v1.0 |
