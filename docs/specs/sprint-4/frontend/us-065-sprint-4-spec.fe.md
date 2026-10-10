# Frontend Technical Specification — Lịch sử dịch vụ của xe

> Đặc tả frontend cho Feature `FEAT-VEH-002` (mở rộng PRD F3, US-065 → US-068).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-065-sprint-4-spec.ff.md) · **API:** [API Spec](../api/us-065-sprint-4-spec.api.md)
>
> **Bối cảnh:** màn đã chạy với API thật (`frontend/src/features/maintenance/pages/ServiceHistory.tsx`, `features/dashboard/components/RecentServiceHistory.tsx`). Tài liệu ghi lại hành vi hiện tại để làm chuẩn kiểm thử và chỉnh sửa sau này.

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-VEH-002` |
| Screen | `SCR-1601` Lịch sử dịch vụ · `SCR-1602` khối lịch sử trên Home |
| Route | `/history` · `/dashboard` |
| Version | `v1.0` |
| Status | `Draft` |
| Owner | Mai Văn Trung |
| Last Updated | `2026-10-07` |

---

# 2. Screen Overview

| | SCR-1601 `/history` | SCR-1602 Home |
|---|---|---|
| Mục đích | Toàn bộ lịch sử, lọc, tìm, phân trang | 3 lần gần nhất |
| Entry | Menu chủ xe "Lịch sử dịch vụ" (`OwnerLayout`); "Xem tất cả →" từ Home | `/dashboard` |
| Exit | "Lịch hẹn" ⇒ `/bookings/:bookingId` (us-053) | "Xem tất cả →" ⇒ `/history` |
| Precondition | Đăng nhập chủ xe (`RequireActiveUser`), có xe đang hoạt động | Như bên trái |

---

# 3. UI Structure

## 3.1 SCR-1601

```text
┌──────────────────────────────────────────────────────────────┐
│ Lịch sử dịch vụ                                              │
│ Các lần bảo dưỡng và sửa chữa của xe, đồng bộ từ hãng và từ  │
│ EV Care                                                      │
├──────────────────────────────────────────────────────────────┤
│ [Tất cả] [Bảo dưỡng định kỳ] [Sửa chữa / kiểm tra]  🔍 Tìm…  │
├──────────────────────────────────────────────────────────────┤
│ Ngày | Số km | Hạng mục | Xưởng dịch vụ | Nguồn | Chi phí | ↗ │
│ …10 dòng / trang…                                            │
├──────────────────────────────────────────────────────────────┤
│ Hiển thị 1–10 trong 23 kết quả              ‹  1 2 3  ›      │
└──────────────────────────────────────────────────────────────┘
```

## 3.2 SCR-1602

Thẻ "Lịch sử dịch vụ" + "Xem tất cả →"; bảng 3 dòng: Số km · Ngày · Hạng mục · Xưởng dịch vụ · Nguồn. Không có cột chi phí và liên kết lịch hẹn.

---

# 4. Component Specification

## 4.1 VehicleGate (dùng chung, us-017 FE)

Lấy xe đầu tiên của `API-VEH-001` (MVP một xe), và tự xử lý: đang tải, lỗi danh sách xe, chưa có xe, xe không còn hoạt động, chuyển hướng khi `ONBOARDING_REQUIRED`. `HistoryTable` chỉ render khi đã có xe (FF EF-1602).

## 4.2 Bộ lọc loại

| Giá trị | Nhãn | Giữ dòng khi | FF |
|---|---|---|---|
| `ALL` | Tất cả | luôn | BR-1610 |
| `PERIODIC` | Bảo dưỡng định kỳ | `isPeriodic = true` | BR-1604 |
| `OTHER` | Sửa chữa / kiểm tra | `isPeriodic = false` | BR-1604 |

Đổi bộ lọc ⇒ `page = 1`.

## 4.3 Ô tìm

- Placeholder "Tìm hạng mục, xưởng, mã lịch hẹn...".
- Khớp một phần, không phân biệt hoa thường, trên `itemsDone`, `workshop.name`, `bookingCode` (`matchesServiceRecord`, `features/maintenance/utils.ts`).
- Lọc tại chỗ, không gọi API; gõ ⇒ `page = 1`.

## 4.4 Bảng

| Cột | Giá trị | Trống | FF |
|---|---|---|---|
| Ngày | `formatDate(serviceDate)` (`dd/mm/yyyy`) | — | BR-1603 |
| Số km | `formatKm(odoKm)` | "—" | EDGE-1602 |
| Hạng mục | `serviceRecordTitle`: `itemsDone`, trống ⇒ "Bảo dưỡng định kỳ" / "Sửa chữa / kiểm tra" | — | BR-1605 |
| Xưởng dịch vụ | `workshop.name` | "—" | BR-1606 |
| Nguồn | `EV_CARE` ⇒ "EV Care", `OEM` ⇒ "Hãng" | — | BR-1602 |
| Chi phí | `formatVnd(actualCost)` (chuỗi số được chuyển sang number) | "—" | BR-1607 |
| (liên kết) | "Lịch hẹn ↗" khi có `bookingId` | ẩn | BR-1609 |

- Thứ tự giữ nguyên thứ tự API trả (FF BR-1603); FE **không** sắp lại.
- Không có nút thêm/sửa/xoá (FF BR-1601).

## 4.5 Phân trang

- 10 dòng/trang, phía client, trên danh sách đã lọc.
- Chân bảng: "Hiển thị {from}–{to} trong {n} kết quả"; nút ‹ › và số trang. ‹ tắt ở trang 1, › tắt ở trang cuối.

---

# 5. User Interaction

| Hành động | Kết quả |
|---|---|
| Chọn bộ lọc | Lọc lại, về trang 1 |
| Gõ từ khoá | Lọc lại, về trang 1 |
| Bấm số trang / ‹ › | Đổi trang |
| Bấm "Lịch hẹn" | Điều hướng `/bookings/:bookingId` |
| SCR-1602 "Xem tất cả →" | Điều hướng `/history` |

---

# 6. State Management

| State | Kiểu | Nguồn |
|---|---|---|
| `records` | `ServiceRecordList` | `useServiceRecords(userVehicleId)` — `useCachedQuery`, khoá `service-records:{userVehicleId}`, dữ liệu coi là mới trong 5 phút |
| `filter` | `'ALL' \| 'PERIODIC' \| 'OTHER'` | state cục bộ, mặc định `ALL` |
| `search` | `string` | state cục bộ |
| `page` | `number` | state cục bộ, mặc định 1 |

Home và `/history` dùng chung khoá cache ⇒ mở `/history` từ Home không gọi lại API nếu dữ liệu còn mới. Lọc/tìm/trang **không** lưu vào URL.

---

# 7. API Integration

| Action | API | Mapping |
|---|---|---|
| Tải xe | `GET /user-vehicles` (`API-VEH-001`) | Qua `VehicleGate` |
| Tải lịch sử | `GET /user-vehicles/{id}/service-records` (`API-VEH-005`) | `listServiceRecords` (`features/vehicles/api.ts`), type `ServiceRecord` (`features/vehicles/types.ts`) |

---

# 8. Loading / Empty / Error States

| State | Điều kiện | SCR-1601 | SCR-1602 |
|---|---|---|---|
| Loading | Chưa có `records.data` | `SkeletonCard` 5 dòng | `SkeletonCard` 3 dòng |
| Empty | `items = []` (FF AF-1601) | `EmptyState` "Chưa có lịch sử dịch vụ" — "Các lần bảo dưỡng từ hãng và lịch hẹn hoàn thành trên EV Care sẽ hiện ở đây." | "Chưa có lịch sử bảo dưỡng — mốc được tính từ ngày mua." |
| Không khớp | Có dữ liệu nhưng lọc/tìm ra 0 (FF AF-1602) | Một dòng "Không tìm thấy kết quả phù hợp" | — |
| Error | Lỗi và chưa có dữ liệu (FF EF-1601) | `ErrorState` "Chưa tải được lịch sử dịch vụ." + "Thử lại" + `traceId` | Ẩn khối (lỗi xe đã hiện ở thẻ xe phía trên) |
| Error khi làm mới | Lỗi nhưng đã có dữ liệu cũ | Giữ bảng cũ | Giữ bảng cũ |

## 8.1 Error Mapping

| API | FE |
|---|---|
| `404 VEHICLE_NOT_FOUND`, `409 VEHICLE_NOT_ACTIVE`, `403 ONBOARDING_REQUIRED` từ `API-VEH-001` | `VehicleGate` (us-017 FE §11.2) |
| Lỗi bất kỳ của `API-VEH-005` | `ErrorState` §8 |

---

# 9. Responsive

| Kích thước | Hành vi |
|---|---|
| < `sm` | SCR-1601 chỉ giữ cột Ngày · Hạng mục · Chi phí; số km xuống dưới ngày; tên xưởng và "Lịch hẹn" xuống dưới hạng mục. SCR-1602 ẩn cột Xưởng, Nguồn; tên xưởng xuống dưới hạng mục |
| ≥ `sm` | Đủ cột |
| Bảng | Cuộn ngang trong khung khi tràn, không cuộn ngang cả trang |

---

# 10. Accessibility

- Nút ‹ › có `aria-label` "Trang trước" / "Trang sau".
- Bộ lọc là `button`; `[Đề xuất]` thêm `aria-pressed` cho nút đang chọn.
- Bảng dùng `<th>` cho tiêu đề cột.

---

# 11. Acceptance Criteria (FE)

- **AC-FE-1601** — Thứ tự dòng trên màn trùng thứ tự API trả.
- **AC-FE-1602** — Dòng `OEM` hiện "Hãng" và chi phí "—"; dòng `EV_CARE` có chi phí thực tế hiện số tiền VNĐ.
- **AC-FE-1603** — Lọc "Sửa chữa / kiểm tra" chỉ còn các dòng `isPeriodic = false`, chân bảng đếm đúng.
- **AC-FE-1604** — Tìm "evc-1a2b" khớp dòng có `bookingCode = "EVC-1A2B…"`.
- **AC-FE-1605** — Đổi bộ lọc khi đang ở trang 3 ⇒ về trang 1.
- **AC-FE-1606** — `items = []` ⇒ trạng thái trống, không hiện bảng.
- **AC-FE-1607** — Home hiện tối đa 3 dòng và liên kết `/history`.

---

# 12. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-1601, AC-1601 | §4.4 (giữ thứ tự API) |
| UC-1602, AC-1607 | §3.2, §8 |
| BR-1601, AC-1603 | §4.4 (không có thao tác ghi) |
| BR-1604, BR-1610, AC-1604 | §4.2, §4.3 |
| BR-1605 | §4.4 cột Hạng mục |
| BR-1606, EDGE-1603 | §4.4 cột Xưởng |
| BR-1607, AC-1602 | §4.4 cột Chi phí |
| BR-1609, AC-1606, EDGE-1604 | §4.4 liên kết |
| EF-1601 | §8 |
| EF-1602, BR-1608, AC-1605 | §4.1 |
| AF-1601, AF-1602 | §8 |
| EDGE-1607 | §6 (cache 5 phút) |

---

# 13. Technical Notes

| Mục | Vị trí |
|---|---|
| Trang | `frontend/src/features/maintenance/pages/ServiceHistory.tsx` |
| Khối Home | `frontend/src/features/dashboard/components/RecentServiceHistory.tsx` |
| Hàm thuần (có test) | `frontend/src/features/maintenance/utils.ts` · `utils.test.ts` |
| Mock demo | `frontend/src/mocks/server/vehicles.ts` (`GET /user-vehicles/:id/service-records`) |

---

# 14. Open Questions

| ID | Question | Status |
|---|---|---|
| `Q-FE-1601` | Lưu bộ lọc / từ khoá / trang vào URL để chia sẻ và quay lại đúng chỗ? | Open — `[Đề xuất]` chưa cần |
| `Q-1603` | Dòng EV Care có tên mốc ở cột Hạng mục (FF Q-1603) | Open — chỉ cần backend; FE không đổi |

---

# 15. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-10-07` | Team 4 Người | Bản đầu, theo màn đã triển khai |
