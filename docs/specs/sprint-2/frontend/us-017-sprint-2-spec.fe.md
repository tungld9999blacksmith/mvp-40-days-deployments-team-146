# Frontend Technical Specification — Hồ sơ xe & Trạng thái đến hạn bảo dưỡng

> Đặc tả frontend cho Feature `FEAT-VEH-001` (PRD F3, US-017 → US-018).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-017-sprint-2-spec.ff.md) · **API:** [API Spec](../api/us-017-sprint-2-spec.api.md) · **Entity:** [Entity Spec](../entity/us-017-sprint-2-spec.entity.md)
>
> **Nguyên tắc cốt lõi:** FE **chỉ hiển thị** kết quả backend trả về (BR-008). FE không tự tính trạng thái, mốc tiếp theo hay số km/ngày còn lại, và **không có** chức năng nhập/sửa số km (BR-003, AC-005). US-019 (đồng bộ từ hãng) và US-020 (tool AI) không có UI.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-VEH-001` — Hồ sơ xe & Trạng thái đến hạn bảo dưỡng |
| Screen | `SCR-301` Home — thẻ xe & trạng thái đến hạn · `SCR-302` Hồ sơ xe |
| Route | `/dashboard` · `/vehicle` |
| Version | `v1.0` |
| Author | Mai Văn Trung |
| FE Owner | Mai Văn Trung |
| Status | `Draft` |
| Related PRD | [PRD_EV_Care_MVP.md §F3](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-017-sprint-2-spec.ff.md#7-user-flow) |
| Related API | [API-VEH-001 → 003](../api/us-017-sprint-2-spec.api.md) |
| Last Updated | `2026-09-29` |

---

# 2. Screen Overview

## 2.1 Purpose

- **SCR-301 Home:** mở app là thấy ngay xe đang **Bình thường / Sắp đến hạn / Quá hạn**, mốc tiếp theo, còn bao nhiêu km / ngày, số km hiện tại và thời điểm hãng cập nhật.
- **SCR-302 Hồ sơ xe:** xem thông tin xe do hãng xác thực: định danh, thông số, bảo hành theo hạng mục, ODO, lần bảo dưỡng gần nhất, cùng trạng thái bảo dưỡng.

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Đăng nhập thành công, tài khoản `ACTIVE` | — | `/dashboard` |
| Sidebar "Tổng quan" | — | `/dashboard` |
| Sidebar "Xe của tôi" / nút "Xem chi tiết" trên thẻ xe | — | `/vehicle` |
| Thông báo nhắc mốc (F7) | Chủ xe nhấn thông báo | `/vehicle` hoặc `/dashboard` ([US-021 FE](./us-021-sprint-2-spec.fe.md)) |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| Nhấn "Xem chi tiết" trên thẻ xe | `/vehicle` |
| Nhấn "Hỏi AI" | `/ai` ([US-025 FE](./us-025-sprint-2-spec.fe.md)) |
| Nhấn "Đặt lịch bảo dưỡng" (khi `DUE_SOON` / `OVERDUE`) | `/booking` (F6 — ngoài phạm vi) |
| `409 VEHICLE_NOT_ACTIVE` | Luồng onboarding xe ([US-001 FE](../../sprint-1/frontend/us-001-sprint-1-spec.fe.md)) |
| `403 ONBOARDING_REQUIRED` | Luồng onboarding |
| `401` | Login |

## 2.4 Preconditions

- Tài khoản `ACTIVE`; xe `verified` + `link_status = active` (BR-010).
- MVP: mỗi tài khoản đúng **một** xe đang liên kết.

---

# 3. UI Structure

## 3.1 Layout

```text
SCR-301 Home (/dashboard)
├── Greeting "Xin chào, {fullName} 👋"
├── Vehicle Card
│   ├── Model + phiên bản ("VinFast VF6 Plus"), biển số
│   ├── Ảnh xe (placeholder)
│   └── Link "Xem chi tiết" → /vehicle
├── Maintenance Status Card                       ← trọng tâm F3
│   ├── DueStatusBadge (Bình thường / Sắp đến hạn / Quá hạn / Chưa xác định)
│   ├── Mốc tiếp theo: "Mốc 12.000 km / 12 tháng"
│   ├── Khoảng cách: "Còn 400 km · 17 ngày" | "Quá 300 km" | "Quá 10 ngày"
│   ├── Progress bar km (ẩn khi TIME_ONLY)
│   ├── Dòng ODO: "ODO 11.600 km · Hãng cập nhật lúc 09:00 28/09"
│   ├── DataNotice (khi cần): TIME_ONLY / dữ liệu cũ / đang lấy dữ liệu / chưa có định mức
│   ├── Danh sách hạng mục (tối đa 3 + "và N hạng mục khác")
│   └── CTA theo trạng thái
├── Quick Actions: Hỏi AI · Đặt lịch · Lịch sử dịch vụ
└── (các khối khác của Home — ngoài phạm vi F3)

SCR-302 Hồ sơ xe (/vehicle)
├── Page title "Xe của tôi" + dòng "Dữ liệu do hãng cung cấp"
├── Vehicle Identity Card
│   ├── Model, phiên bản, màu, năm sản xuất
│   ├── VIN (đã che) · Biển số
│   └── Thông số: pin (kWh), động cơ (kW)
├── Odometer Card
│   ├── "11.600 km"
│   └── "Hãng cập nhật lúc 09:00 28/09" (+ cảnh báo dữ liệu cũ)
├── Maintenance Status Card (cùng component với Home, bản đầy đủ)
│   └── Toàn bộ hạng mục của mốc, đánh dấu "Trong bảo hành"
├── Last Service Card
│   └── Ngày · km · nơi làm | "Chưa có lịch sử — tính từ ngày mua"
└── Warranty Card
    └── Bảng: Hạng mục · Hết hạn · Giới hạn km · Trạng thái
```

## 3.2 Screen Layout Notes

- Theo [design-guidelines.md](../../../design/design-guidelines.md) và [wireframe.md §4, §6](../../../design/wireframe.md): card `bg-card rounded-2xl border border-border`; số km, biển số, VIN, ngày giờ dùng font mono.
- Không có ô nhập, nút "Cập nhật số km" hay "Đồng bộ ngay" ở bất kỳ đâu (FF §3.2, AC-005).
- Thứ tự ưu tiên thị giác trên Home: trạng thái → khoảng cách còn lại → mốc → ODO + thời điểm cập nhật (wireframe §18).

---

# 4. Component Specification

## 4.1 DueStatusBadge

| Property | Value |
|---|---|
| Component | `DueStatusBadge` (thay `shared/ui/StatusBadge` cho F3) |
| Type | Badge |
| Data Source | `MaintenanceStatus.dueStatus` |

| `dueStatus` | Nhãn | Style (design-guidelines) | Icon |
|---|---|---|---|
| `NORMAL` | `Bình thường` | `text-emerald bg-emerald/10` | `CheckCircle` |
| `DUE_SOON` | `Sắp đến hạn` | `text-warning bg-warning/10` | `AlertTriangle` |
| `OVERDUE` | `Quá hạn` | `text-error bg-error/10` | `AlertOctagon` |
| `UNKNOWN` | `Chưa xác định` | `text-muted bg-card` | `HelpCircle` |
| Giá trị lạ (enum mới) | `Chưa xác định` | như `UNKNOWN` | — (API Spec §19) |

> Dùng "Quá hạn", **không** dùng "Hết hạn" (FF §22 Terminology).

---

## 4.2 Maintenance Status Card

| Property | Value |
|---|---|
| Component | `MaintenanceStatusCard` |
| Props | `status: MaintenanceStatus`, `variant: 'compact' \| 'full'` |
| Data Source | `API-VEH-003` |
| Visibility | Home (`compact`), Hồ sơ xe (`full`) |

### Mốc tiếp theo

- Hiển thị tiếng Việt từ số: `Mốc {odoMilestoneKm formatted} km / {monthMilestone} tháng` → `Mốc 12.000 km / 12 tháng`.
- **Không** dùng `nextMilestone.label` (chuỗi tiếng Anh cho code/AI — API Spec C.6).
- `isRecurring = true` → thêm chú thích nhỏ `(mốc định kỳ)`.
- Ngày đến hạn: `Đến hạn {dueDate DD/MM/YYYY}`.

### Khoảng cách còn lại

| Điều kiện | Hiển thị |
|---|---|
| `remainingKm >= 0` và `remainingDays >= 0` | `Còn {remainingKm} km · {remainingDays} ngày` |
| `remainingKm = null` (TIME_ONLY) | `Còn {remainingDays} ngày` |
| `remainingKm < 0` | `Quá {abs(remainingKm)} km` |
| `remainingDays < 0` | `Quá {abs(remainingDays)} ngày` |
| Cả hai âm | `Quá {abs(km)} km · {abs(days)} ngày` |
| `remainingKm = 0` / `remainingDays = 0` | `Đúng mốc hôm nay` / `Đến mốc km` |

Phần gây ra trạng thái (theo `dueReason`: `KM`, `TIME`, `BOTH`) được tô màu theo trạng thái; phần còn lại màu `text-muted`. Ví dụ AC-004: `OVERDUE`, `dueReason = TIME` → "Quá 10 ngày" màu đỏ, km còn lại màu muted.

Dòng lý do (chỉ khi `DUE_SOON` / `OVERDUE`):

| `dueReason` | Text |
|---|---|
| `KM` | `Theo số km` |
| `TIME` | `Theo thời gian` |
| `BOTH` | `Theo số km và thời gian` |

### Progress bar km

- Hiển thị khi `odometer != null` và `nextMilestone != null`.
- Giá trị: `(odometer.odoKm − baseKm) / (nextMilestone.odoMilestoneKm − baseKm)`, với `baseKm = lastService.odoKm ?? 0`. Kẹp trong `[0, 1]`.
- Đây chỉ là **hình minh hoạ** dựa trên các số backend trả về, không dùng để quyết định trạng thái. Màu theo `dueStatus`.
- Nhãn hai đầu: `{odoKm} km` · `{odoMilestoneKm} km`.

### Dòng ODO

`ODO {odometer.odoKm} km · Hãng cập nhật lúc {recordedAt HH:mm DD/MM}` (giờ Asia/Ho_Chi_Minh). `recordedAt` là thời điểm **hãng đo**, không phải `oemSyncedAt`.

### DataNotice

| Điều kiện | Nội dung | Kiểu |
|---|---|---|
| `calculationBasis = TIME_ONLY` | `Hãng chưa có dữ liệu số km — trạng thái tính theo thời gian.` (AF-001, AC-002) | info |
| `odometer.isStale = true` | `Số km được hãng cập nhật lần cuối ngày {recordedAt DD/MM/YYYY}, có thể chưa phản ánh hiện tại.` (BR-009) | warning |
| `UNKNOWN` + `OEM_DATA_NOT_SYNCED` | `Đang lấy dữ liệu từ hãng...` (AF-005, AC-011) | loading |
| `UNKNOWN` + `NO_MAINTENANCE_RULE` | `Chưa có lịch bảo dưỡng cho mẫu xe này — vui lòng liên hệ xưởng.` (EF-003) | info |

### Hạng mục của mốc

- `compact`: tối đa 3 hạng mục, sau đó `và {n} hạng mục khác`.
- `full`: toàn bộ `nextMilestone.items`.
- Mỗi hạng mục: `itemName`; nếu `isCoveredByWarranty` thì thêm tag `Trong bảo hành` (`text-emerald`).
- **Không** hiển thị giá (F3 không trả giá — FF §3.2).

### CTA theo trạng thái

| `dueStatus` | CTA chính | CTA phụ |
|---|---|---|
| `DUE_SOON`, `OVERDUE` | `Đặt lịch bảo dưỡng` → `/booking` | `Hỏi AI về mốc này` → `/ai` |
| `NORMAL` | — | `Xem chi tiết` → `/vehicle` (chỉ ở Home) |
| `UNKNOWN` | — | — |

---

## 4.3 Vehicle Card (Home)

| Property | Value |
|---|---|
| Component | `VehicleSummaryCard` |
| Data Source | `API-VEH-001` (phần tử đầu tiên) |

- Tên: `VinFast {modelName} {trim}` (bỏ phần null).
- Biển số: format hiển thị từ chuỗi đã chuẩn hoá `30A12345` → `30A-123.45` `[Đề xuất]` (hàm `formatLicensePlate`, chỉ hiển thị).
- Link `Xem chi tiết` → `/vehicle`.

---

## 4.4 Vehicle Identity Card (Hồ sơ xe)

| Field | Nguồn | Hiển thị khi null |
|---|---|---|
| Model / phiên bản | `modelName`, `trim` | `—` |
| Màu | `color` | `—` |
| Năm sản xuất | `productionYear` | `—` |
| VIN | `vinMasked` | (luôn có) — hiển thị nguyên chuỗi đã che, **không** có nút "hiện VIN" |
| Biển số | `licensePlate` | — |
| Dung lượng pin | `batteryCapacityKwh` → `59,6 kWh` | `—` |
| Công suất động cơ | `motorPowerKw` → `150 kW` | `—` |

Cuối card: `Dữ liệu do hãng cung cấp. Nếu thông tin chưa đúng, vui lòng liên hệ hãng hoặc xưởng dịch vụ.` (FF SCR-302, AC-005).

---

## 4.5 Odometer Card (Hồ sơ xe)

| Trạng thái | Hiển thị |
|---|---|
| `odometer != null` | Số lớn `11.600 km`; dưới: `Hãng cập nhật lúc {recordedAt}`; nếu `isStale` → cảnh báo BR-009 |
| `odometer = null` | `Hãng chưa có dữ liệu số km.` |

Không có nút sửa (AC-005).

---

## 4.6 Last Service Card (Hồ sơ xe)

| Trạng thái | Hiển thị |
|---|---|
| `lastService != null` (API-VEH-002) | `{serviceDate DD/MM/YYYY} · {odoKm} km · {centerName ?? 'Xưởng dịch vụ chính hãng'}`; tag nguồn: `source = OEM` → `Hãng ghi nhận`, `EV_CARE` → `Qua EV Care` |
| `lastService = null` | `Chưa có lịch sử bảo dưỡng — mốc được tính từ ngày mua.` |

---

## 4.7 Warranty Card (Hồ sơ xe)

| Cột | Nguồn | Format |
|---|---|---|
| Hạng mục | `component` | `BATTERY` → Pin cao áp · `MOTOR` → Động cơ điện · `CHASSIS` → Khung gầm · `ELECTRONICS` → Điện tử |
| Hết hạn | `endDate` | `DD/MM/YYYY` |
| Giới hạn km | `kmLimit` | `200.000 km`; null → `Không giới hạn` |
| Trạng thái | `isActive` | `Còn hiệu lực` (emerald) / `Hết hiệu lực` (muted) |

`warranties = []` → `Chưa có thông tin bảo hành từ hãng.`

> "Hết hiệu lực" dùng cho **bảo hành**; "Quá hạn" chỉ dùng cho **bảo dưỡng** (FF §22).

---

# 5. User Interaction

## 5.1 Interaction Flow

```text
Mở /dashboard
   ↓
GET /user-vehicles ──(rỗng)──► Empty state "Chưa có xe"
   ↓ userVehicleId
GET /user-vehicles/{id}/maintenance-status
   ↓
UNKNOWN + OEM_DATA_NOT_SYNCED ──► "Đang lấy dữ liệu từ hãng..." ─► tự tải lại (5s, tối đa 6 lần)
   ↓
Hiển thị trạng thái + CTA
   ↓
"Xem chi tiết" ─► /vehicle
                    ↓
     GET /user-vehicles/{id}  +  GET /user-vehicles/{id}/maintenance-status (song song)
```

## 5.2 Interaction Table

| User Action | Frontend Behavior | Result |
|---|---|---|
| Mở Home | `API-VEH-001` → `API-VEH-003` | Thẻ trạng thái (AC-001) |
| Mở Hồ sơ xe | `API-VEH-002` + `API-VEH-003` song song | Đủ thông tin xe |
| Nhấn `Thử lại` khi lỗi | Gọi lại request lỗi | — |
| Quay lại tab sau ≥ 5 phút | Tải lại `API-VEH-003` ngầm (giữ dữ liệu cũ khi đang tải) | Dữ liệu mới nếu hãng vừa cập nhật (AC-003) |
| Nhấn `Đặt lịch bảo dưỡng` | Điều hướng | `/booking` |
| Nhấn `Hỏi AI về mốc này` | Điều hướng | `/ai` |

> Không có "kéo để tải lại" trên web desktop; "tải lại" = reload trang hoặc focus lại tab.

---

# 6. State Management

## 6.1 State Model

```text
VehicleQueryState (dùng chung Home + Hồ sơ xe, cache theo userVehicleId)
├── vehicles          { data: VehicleSummary[], status, error }
├── profile           { data: VehicleProfile | null, status, error }
├── maintenance       { data: MaintenanceStatus | null, status, error, fetchedAt }
└── pendingSync       { attempts: number }         (khi OEM_DATA_NOT_SYNCED)
```

`status ∈ 'idle' | 'loading' | 'success' | 'error'`.

## 6.2 State Fields

| State | Type | Default | Description |
|---|---|---|---|
| `vehicles.data` | `VehicleSummary[]` | `[]` | `API-VEH-001` |
| `selectedVehicleId` | `string \| null` | `vehicles.data[0].userVehicleId` | MVP 1 xe |
| `profile.data` | `VehicleProfile \| null` | `null` | `API-VEH-002` |
| `maintenance.data` | `MaintenanceStatus \| null` | `null` | `API-VEH-003` |
| `maintenance.fetchedAt` | `number \| null` | `null` | Dùng cho refetch khi focus lại tab (≥ 5 phút) |
| `pendingSync.attempts` | `number` | `0` | Số lần tự tải lại khi `OEM_DATA_NOT_SYNCED` |

- Cache dữ liệu trong bộ nhớ khi chuyển giữa Home và Hồ sơ xe; hiển thị cache ngay, tải lại ngầm nếu `fetchedAt` cũ hơn 5 phút.
- Xoá toàn bộ cache khi đăng xuất ([US-005 FE](../../sprint-1/frontend/us-005-sprint-1-spec.fe.md)).
- Không lưu vào `localStorage`.

---

# 7. API Integration

> Hợp đồng chi tiết: [API Spec](../api/us-017-sprint-2-spec.api.md). Quy ước chung (token, envelope, lỗi) theo [US-001 FE §7.0](../../sprint-1/frontend/us-001-sprint-1-spec.fe.md#70-quy-ước-chung).

## 7.1 Danh sách xe — `API-VEH-001`

```http
GET /api/v1/user-vehicles
```

### Trigger

Mở Home hoặc Hồ sơ xe khi chưa có `selectedVehicleId` trong cache.

### Mapping

| Frontend State | API Response |
|---|---|
| `vehicles.data` | `data` (mảng) |
| `selectedVehicleId` | `data[0].userVehicleId` |

### Success

Mảng rỗng → Empty State 10.1. Có phần tử → gọi tiếp `API-VEH-003` (Home) hoặc `API-VEH-002` + `API-VEH-003` (Hồ sơ xe).

---

## 7.2 Hồ sơ xe — `API-VEH-002`

```http
GET /api/v1/user-vehicles/{userVehicleId}
```

### Trigger

Mở `/vehicle`.

### Mapping

| UI | API Response |
|---|---|
| Identity Card | `modelName`, `trim`, `color`, `productionYear`, `vinMasked`, `licensePlate`, `batteryCapacityKwh`, `motorPowerKw` |
| Odometer Card | `odometer` |
| Last Service Card | `lastService` |
| Warranty Card | `warranties[]` |

---

## 7.3 Trạng thái đến hạn — `API-VEH-003`

```http
GET /api/v1/user-vehicles/{userVehicleId}/maintenance-status
```

### Trigger

- Mở Home / Hồ sơ xe.
- Tự tải lại khi `UNKNOWN + OEM_DATA_NOT_SYNCED` (mục 9.3).
- Tab focus lại và `fetchedAt` ≥ 5 phút.

### Mapping

| UI | API Response |
|---|---|
| `DueStatusBadge` | `dueStatus` |
| Lý do | `dueReason` |
| Mốc | `nextMilestone.odoMilestoneKm`, `monthMilestone`, `dueDate`, `isRecurring` |
| Khoảng cách | `remainingKm`, `remainingDays` |
| Progress | `odometer.odoKm`, `lastService.odoKm`, `nextMilestone.odoMilestoneKm` |
| Dòng ODO | `odometer.odoKm`, `odometer.recordedAt` |
| DataNotice | `calculationBasis`, `odometer.isStale`, `unknownReason` |
| Hạng mục | `nextMilestone.items[]` |

### Failure

API này **không** lỗi khi hãng lỗi (chỉ đọc DB). Lỗi chỉ đến từ auth/guard/hệ thống (mục 11.2).

---

# 8. Client-side Validation

Không có form nhập liệu. Kiểm tra phía client duy nhất: `userVehicleId` có trong cache/`API-VEH-001` trước khi gọi `API-VEH-002/003`.

---

# 9. Loading States

## 9.1 Tải lần đầu

- **Condition:** `vehicles` hoặc `maintenance` đang `loading` và chưa có cache.
- **UI:** Skeleton cho Vehicle Card và Maintenance Status Card (giữ đúng kích thước để không nhảy layout). Hồ sơ xe: skeleton cho từng card.

## 9.2 Tải lại ngầm

- **Condition:** Đã có dữ liệu, đang refetch.
- **UI:** Giữ dữ liệu cũ, không hiện skeleton; spinner nhỏ cạnh dòng ODO.

## 9.3 Đang lấy dữ liệu từ hãng (AF-005, AC-011)

- **Condition:** `dueStatus = UNKNOWN` và `unknownReason = OEM_DATA_NOT_SYNCED`.
- **UI:** Badge `Chưa xác định` + DataNotice `Đang lấy dữ liệu từ hãng...` có spinner. **Không** hiển thị mốc, khoảng cách, progress.
- **Behavior:** Tự gọi lại `API-VEH-003` mỗi **5 giây**, tối đa **6 lần** (30 giây). Sau đó dừng, đổi thông điệp thành `Hãng chưa gửi dữ liệu. Vui lòng quay lại sau ít phút.` + nút `Tải lại`.

---

# 10. Empty States

## 10.1 Chưa có xe

- **Condition:** `API-VEH-001` trả `[]`.
- **UI:** Title `Bạn chưa có xe nào được liên kết.` · Description `Hoàn tất xác thực xe để theo dõi lịch bảo dưỡng.` · CTA `Xác thực xe` → luồng onboarding xe.

## 10.2 Chưa có lịch sử bảo dưỡng

- **Condition:** `lastService = null` (API-VEH-002).
- **UI:** `Chưa có lịch sử bảo dưỡng — mốc được tính từ ngày mua.` Không phải lỗi.

## 10.3 Chưa có bảo hành

- **Condition:** `warranties = []`.
- **UI:** `Chưa có thông tin bảo hành từ hãng.`

## 10.4 Model chưa có định mức

- **Condition:** `UNKNOWN` + `NO_MAINTENANCE_RULE`.
- **UI:** DataNotice mục 4.2; hồ sơ xe vẫn hiển thị đầy đủ (EF-003).

---

# 11. Error States

## 11.1 General Error

Hiển thị **trong card** bị lỗi (không thay cả trang), để các card khác vẫn dùng được:

```text
Không tải được trạng thái bảo dưỡng.
[Thử lại]
```

## 11.2 Error Mapping

| HTTP Status / Error Code | Frontend Behavior |
|---|---|
| `401 UNAUTHORIZED` / `INVALID_TOKEN` | Interceptor làm mới token → vẫn lỗi thì về Login ([US-005 FE §4.2](../../sprint-1/frontend/us-005-sprint-1-spec.fe.md#42-token-refresh--401-interceptor)) |
| `403 ONBOARDING_REQUIRED` | Điều hướng onboarding (`resolveOnboardingRoute()`) |
| `403 FORBIDDEN` | Token chủ xưởng: điều hướng `/technician` |
| `404 VEHICLE_NOT_FOUND` | Xoá cache xe, gọi lại `API-VEH-001`; nếu vẫn không có xe → Empty 10.1 (AC-008: không tiết lộ xe người khác) |
| `409 VEHICLE_NOT_ACTIVE` | Thông báo `Xe chưa được xác thực hoặc đã gỡ liên kết.` + CTA `Xác thực xe` (EF-004) |
| `400 INVALID_REQUEST` | General Error (lỗi lập trình — log) |
| `500` | General Error trong card + `Thử lại` |
| Lỗi mạng | `Không có kết nối mạng.` + `Thử lại` trong card |

---

# 12. Error Handling

## 12.1 Field-level Error

Không áp dụng.

## 12.2 Screen-level Error

- Chỉ dùng khi `API-VEH-001` lỗi (không biết xe nào để hiển thị): card lỗi thay nội dung Home phần xe.
- Lỗi `API-VEH-002` hoặc `API-VEH-003` → lỗi trong card tương ứng; card kia vẫn hiển thị.

## 12.3 Retry Behavior

`Thử lại` chỉ gọi lại request lỗi; giữ dữ liệu các card khác.

---

# 13. Navigation

## 13.1 Routes

| Route | Purpose |
|---|---|
| `/dashboard` | Home — SCR-301 |
| `/vehicle` | Hồ sơ xe — SCR-302 |
| `/booking` | Đặt lịch (F6) |
| `/ai` | AI Trợ lý (F4) |

> `[Đề xuất]` Giữ `/vehicle` (không có id) vì MVP chỉ một xe. Khi hỗ trợ nhiều xe, đổi thành `/vehicles/:userVehicleId`.

## 13.2 Navigation Rules

- Back từ `/vehicle` → màn trước đó.
- Không có thao tác ghi dữ liệu nên không cần xác nhận khi rời màn.

---

# 14. Permission / Visibility

| UI Element | Condition |
|---|---|
| Home, Hồ sơ xe | Chủ xe `ACTIVE` (BR-010) |
| CTA `Đặt lịch bảo dưỡng` | `dueStatus ∈ {DUE_SOON, OVERDUE}` |
| Progress bar | `odometer != null` và `nextMilestone != null` |
| Nút sửa ODO / lịch sử bảo dưỡng | **Không tồn tại** (BR-003, AC-005) |
| VIN đầy đủ | **Không hiển thị** — chỉ `vinMasked` |

## 14.1 Role-based Behavior

| Role | Access |
|---|---|
| Chủ xe | Xem xe của mình, chỉ đọc |
| Chủ xưởng | Không truy cập (`403 FORBIDDEN`) |

---

# 15. Responsive / Device Behavior

## Mobile

- Home: Vehicle Card và Maintenance Status Card xếp dọc, full-width; Quick Actions 3 cột nhỏ hoặc cuộn ngang.
- Hồ sơ xe: các card xếp dọc; bảng bảo hành chuyển sang danh sách thẻ.

## Tablet

- Home: 2 cột (Vehicle | Maintenance).

## Desktop

- Home: lưới 3 cột như hiện tại (Vehicle | Maintenance | AI panel).
- Hồ sơ xe: 2 cột — trái (Identity, Warranty), phải (Odometer, Maintenance, Last Service).

---

# 16. Accessibility

- Badge trạng thái có chữ + icon, không chỉ dùng màu.
- Progress bar: `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, `aria-label="Tiến độ tới mốc {odoMilestoneKm} km"`.
- DataNotice "Đang lấy dữ liệu" dùng `aria-live="polite"`.
- Số và ngày có định dạng đọc được (`11.600 km`, `28/09/2026`).

---

# 17. Analytics / Tracking

| Event | Trigger | Properties |
|---|---|---|
| `maintenance_status_viewed` | Có kết quả `API-VEH-003` | `dueStatus`, `dueReason`, `calculationBasis`, `screen` (`home` / `vehicle`) |
| `vehicle_profile_viewed` | Mở `/vehicle` thành công | — |
| `maintenance_cta_clicked` | Nhấn CTA | `cta` (`booking` / `ai`), `dueStatus` |
| `oem_data_pending_shown` | Hiển thị `OEM_DATA_NOT_SYNCED` | `attempts` |

> Không gửi VIN, biển số, số km cụ thể.

---

# 18. Acceptance Criteria

## AC-FE-001 — `DUE_SOON` theo km (FF AC-001)

**Given** `API-VEH-003` trả `DUE_SOON`, `dueReason = KM`, `remainingKm = 400`, `remainingDays = 17`, mốc `12000 / 12`
**When** chủ xe mở `/dashboard`
**Then** thẻ hiển thị `Sắp đến hạn`, `Mốc 12.000 km / 12 tháng`, `Còn 400 km · 17 ngày`, lý do `Theo số km`, và dòng `Hãng cập nhật lúc …`.

## AC-FE-002 — Hãng chưa có ODO (FF AC-002)

**Given** `calculationBasis = TIME_ONLY`, `remainingKm = null`, `odometer = null`
**Then** thẻ chỉ hiển thị số ngày còn lại, ẩn progress bar, và hiển thị `Hãng chưa có dữ liệu số km — trạng thái tính theo thời gian.`

## AC-FE-003 — `OVERDUE` theo thời gian (FF AC-004)

**Given** `OVERDUE`, `dueReason = TIME`, `remainingDays = -10`
**Then** thẻ hiển thị `Quá hạn`, `Quá 10 ngày` (màu đỏ), lý do `Theo thời gian`, và CTA `Đặt lịch bảo dưỡng`.

## AC-FE-004 — Không có chức năng nhập ODO (FF AC-005)

**Given** chủ xe ở `/dashboard` hoặc `/vehicle`
**Then** không có ô nhập, nút "Cập nhật số km" hay quick action "Cập nhật km"
**And** Hồ sơ xe có dòng `Dữ liệu do hãng cung cấp`.

## AC-FE-005 — Đang lấy dữ liệu từ hãng (FF AC-011)

**Given** `UNKNOWN` + `OEM_DATA_NOT_SYNCED`
**Then** FE hiển thị `Đang lấy dữ liệu từ hãng...`, không hiển thị mốc/khoảng cách
**And** tự gọi lại mỗi 5s, tối đa 6 lần; có kết quả thì hiển thị trạng thái.

## AC-FE-006 — Dữ liệu cũ (FF BR-009)

**Given** `odometer.isStale = true`
**Then** hiển thị cảnh báo số km có thể chưa phản ánh hiện tại, trạng thái vẫn hiển thị bình thường.

## AC-FE-007 — Xe người khác (FF AC-008)

**Given** `API-VEH-002/003` trả `404 VEHICLE_NOT_FOUND`
**Then** FE không hiển thị thông tin xe nào, tải lại danh sách xe của chính người dùng.

## AC-FE-008 — FE không tự tính (FF BR-008)

**Given** bất kỳ response nào của `API-VEH-003`
**Then** trạng thái, số km/ngày còn lại hiển thị đúng giá trị backend; FE không suy ra trạng thái từ ODO hay ngày.

## AC-FE-009 — Hồ sơ xe (US-018)

**Given** `API-VEH-002` trả đủ dữ liệu
**When** mở `/vehicle`
**Then** hiển thị model, phiên bản, màu, năm, VIN đã che, biển số, pin (kWh), động cơ (kW), ODO + thời điểm cập nhật, lần bảo dưỡng gần nhất, bảo hành theo hạng mục với trạng thái còn/hết hiệu lực.

---

# 19. Technical Notes

## Frontend Stack

```text
Framework: React 19 + Vite
Language: TypeScript
State Management: hook useVehicleQueries (useState/useEffect + cache module-level) [Đề xuất]
Networking: fetch qua shared/api/client.ts
Navigation: React Router 7
UI Library: Tailwind CSS 4 + lucide-react
Date/number format: Intl.NumberFormat('vi-VN'), Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })
```

## Component Structure

```text
frontend/src/features/vehicles/
├── api.ts                              # listVehicles(), getVehicleProfile(), getMaintenanceStatus()
├── types.ts                            # VehicleSummary, VehicleProfile, MaintenanceStatus, Odometer...
├── hooks/useVehicleQueries.ts          # cache + refetch + pendingSync
├── components/
│   ├── DueStatusBadge.tsx
│   ├── MaintenanceStatusCard.tsx       # compact | full
│   ├── VehicleSummaryCard.tsx
│   ├── VehicleIdentityCard.tsx
│   ├── OdometerCard.tsx
│   ├── LastServiceCard.tsx
│   └── WarrantyCard.tsx
├── utils/format.ts                     # formatKm, formatRemaining, formatLicensePlate, componentLabel
└── pages/VehicleDetail.tsx             # SCR-302
frontend/src/features/dashboard/pages/Dashboard.tsx   # SCR-301 dùng VehicleSummaryCard + MaintenanceStatusCard
```

## Implementation Notes — thay đổi so với code hiện tại

| File | Hiện trạng | Việc cần làm |
|---|---|---|
| [VehicleDetail.tsx](../../../../frontend/src/features/vehicles/pages/VehicleDetail.tsx) | Có nút **"Cập nhật số km"** + ô nhập km | **Xoá** (vi phạm BR-003, AC-005) |
| [VehicleDetail.tsx](../../../../frontend/src/features/vehicles/pages/VehicleDetail.tsx) | Khối "Trạng thái pin / SoH 98,2%" | **Xoá** — SOH pin ngoài phạm vi F3 (FF §3.2) |
| [Dashboard.tsx](../../../../frontend/src/features/dashboard/pages/Dashboard.tsx) | Quick action **"Cập nhật km"** | Thay bằng `Lịch sử dịch vụ` → `/history` |
| `Dashboard.tsx`, `VehicleDetail.tsx` | Dùng `mocks/vehicle.ts` (`CURRENT_KM`, `NEXT_KM`) | Thay bằng `API-VEH-001/002/003` |
| [StatusBadge.tsx](../../../../frontend/src/shared/ui/StatusBadge.tsx) | Nhãn tiếng Anh `DUE SOON`, `OVERDUE` | Dùng `DueStatusBadge` tiếng Việt cho F3 |

- Kiểu TypeScript khớp `schemas.py` của backend (`backend/src/modules/user_vehicle/schemas.py`); JSON đã là camelCase.
- `remainingKm`, `remainingDays` có thể âm — không dùng `Math.max(0, …)` khi hiển thị.
- Enum lạ → xử lý như `UNKNOWN` (API Spec §19).

---

# 20. Open Questions

- [ ] **Q-FE-VEH-01** — Format biển số hiển thị (`30A-123.45`) có cần thống nhất với backend (trả sẵn chuỗi hiển thị) không?
- [ ] **Q-FE-VEH-02** — Home có cần hiển thị `thresholds` (vd "Nhắc khi còn 500 km / 14 ngày") không?
- [ ] **Q-FE-VEH-03** — Có hiển thị `oemSyncedAt` ("Đồng bộ lúc …") bên cạnh `recordedAt` không? Spec hiện chỉ hiện thời điểm hãng đo để tránh gây nhầm.
- [ ] Nghiệp vụ còn mở: [FF §24](../feature-functional/us-017-sprint-2-spec.ff.md#24-open-questions), [pending-questions.md](../pending-questions.md) (Q-301, Q-302).

---

# 21. Related Documents

- PRD: [PRD_EV_Care_MVP.md §F3](../../../product/PRD_EV_Care_MVP.md)
- Functional Spec: [us-017-sprint-2-spec.ff.md](../feature-functional/us-017-sprint-2-spec.ff.md)
- API Specification: [us-017-sprint-2-spec.api.md](../api/us-017-sprint-2-spec.api.md)
- Entity Spec: [us-017-sprint-2-spec.entity.md](../entity/us-017-sprint-2-spec.entity.md)
- Design: [design-guidelines.md](../../../design/design-guidelines.md) · [wireframe.md](../../../design/wireframe.md)
- FE liên quan: [US-021 Nhắc mốc bảo dưỡng](./us-021-sprint-2-spec.fe.md) · [US-025 Chat RAG](./us-025-sprint-2-spec.fe.md)

---

# 22. Change Log

| Version | Date | Author | Changes |
|---|---|---|---|
| `v1.0` | `2026-09-29` | Mai Văn Trung | Bản nháp đầu tiên, dựng từ FF v1.2 và API Spec v1.3 |
