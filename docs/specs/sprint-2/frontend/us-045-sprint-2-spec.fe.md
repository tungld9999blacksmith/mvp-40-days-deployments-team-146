# Frontend Technical Specification — Dự toán chi phí bảo dưỡng

> Đặc tả frontend cho Feature `FEAT-COST-001` (PRD F5, US-045 → US-048).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-045-sprint-2-spec.ff.md) · **API:** [API Spec](../api/us-045-sprint-2-spec.api.md)
>
> **Phạm vi FE:** App chủ xe (mobile-first) — màn Dự toán (SCR-1001) thay dữ liệu mock của trang `/estimate` hiện có (`features/quotes/pages/MaintenanceEstimate.tsx`), bộ chọn mốc/xưởng, so sánh xưởng, và thẻ dự toán trong chat (`CARD-EST`).

---

## 1. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-COST-001` — Dự toán chi phí |
| Screen | `SCR-1001` Dự toán · `SCR-1002` Chọn mốc · `SCR-1003` Chọn xưởng · `SCR-1004` So sánh xưởng · `CARD-EST` |
| Route | `/estimate` (query `odoMilestone`, `workshopId` tuỳ chọn) · `/estimate/compare` · thẻ trong `/ai/:conversationId` |
| Version | `v1.0` |
| Author | Team 4 Người |
| Status | `Draft` |
| Related PRD | [PRD §F5](../../../product/PRD_EV_Care_MVP.md) |
| Related User Flow | [FF §7, §8](../feature-functional/us-045-sprint-2-spec.ff.md#7-user-flow) |
| Related API | [API-EST-01 → 03](../api/us-045-sprint-2-spec.api.md), [us-029 API-BK-01](../../sprint-3/api/us-029-sprint-3-spec.api.md) |
| Last Updated | `2026-09-30` |

---

# 2. Screen Overview

## 2.1 Purpose

Cho chủ xe xem hạng mục + chi phí ước tính của một mốc tại một xưởng, tách rõ miễn phí/tính phí, và đi tiếp sang báo giá (F5b) hoặc đặt lịch (F6).

## 2.2 Entry Points

| Entry Point | Condition | Action |
|---|---|---|
| Home — thẻ trạng thái đến hạn (F3) | Nút "Xem chi phí dự kiến" | `/estimate` (mốc tiếp theo, xưởng mặc định) |
| Chat — `CARD-EST` | Nút "Xem chi tiết" | `/estimate?odoMilestone=…&workshopId=…` |
| Sidebar/menu "Chi phí bảo dưỡng" | | `/estimate` |

## 2.3 Exit Points

| Condition / Action | Destination |
|---|---|
| "Gửi xưởng báo giá" | Luồng F5b — `/quotes/new?odoMilestone=…&workshopId=…` ([us-049 FE](../../sprint-3/frontend/us-049-sprint-3-spec.fe.md)) |
| "Đặt lịch" | `/booking?workshopId=…&odoMilestone=…` ([us-029 FE](../../sprint-3/frontend/us-029-sprint-3-spec.fe.md)) |
| `401 UNAUTHORIZED` | `/` (Login) |

## 2.4 Preconditions

- Chủ xe đăng nhập, onboarding xong, có xe `active` (lấy từ `API-VEH-001`).

---

# 3. UI Structure

## 3.1 Layout (mobile)

```text
┌──────────────────────────────────────┐
│ ← Chi phí bảo dưỡng                  │
│ [Mốc 12.000 km / 12 tháng ▾] (Tiếp theo) │
│ [VinFast Smart City ▾]  ★ ưa thích   │
│  (ghi chú khi selectedBy = NEAREST)  │
├──────────────────────────────────────┤
│ Trong bảo hành (miễn phí)            │
│  • Kiểm tra pin cao áp      Miễn phí │
│ Tính phí                             │
│  • Kiểm tra hệ thống phanh   300.000 │
│  • Thay dầu phanh *          350.000 │
├──────────────────────────────────────┤
│ Tổng chi phí ước tính     1.300.000 ₫│
│ [Chi phí ước tính] Chi phí thực tế…  │
│ * Giá tham khảo của hãng             │
├──────────────────────────────────────┤
│ [Gửi xưởng báo giá]   [Đặt lịch]     │
│ So sánh với xưởng khác →             │
└──────────────────────────────────────┘
```

## 3.2 Screen Layout Notes

- Desktop: cột phải "Thông tin xe" (model, biển số che, ODO + thời điểm hãng cập nhật) như mock hiện có.
- Bỏ stepper "AI Recommendation → Technician Review → Confirmed Quote" của mock: dự toán **không** phải báo giá (FF TERM-1001); stepper chuyển sang màn báo giá F5b.
- Bỏ chế độ "sửa/xoá dịch vụ" (`editing`, `included` trong `features/quotes/types.ts`) khỏi màn dự toán — chủ xe không sửa số (FF BR-1006).

---

# 4. Component Specification

## 4.1 MilestoneSelector (SCR-1002)

| Item | Spec |
|---|---|
| Data | `API-EST-01` `milestones[]` |
| Label | `Mốc {odoMilestone} km / {monthMilestone} tháng`; badge "Tiếp theo" khi `isNext` |
| Default | `query.odoMilestone` → `nextOdoMilestone` → không chọn (hiện hướng dẫn chọn) |
| Empty | `milestones = []` ⇒ không render selector, hiện trạng thái `NO_RULE` (§10.1) |

## 4.2 WorkshopSelector (SCR-1003)

| Item | Spec |
|---|---|
| Data | `API-BK-01` (`/workshops/nearby`, không truyền `date`) |
| Hiển thị | Tên, địa chỉ, `distanceKm` (nếu có), nhãn ★ "Ưa thích" |
| Ghi chú | Khi `estimate.workshop.selectedBy = NEAREST`: "Đang tính theo xưởng gần bạn nhất" (FF AF-1002) |

## 4.3 EstimateItemList

- Hai nhóm theo `items[].covered`. Nhóm "Trong bảo hành" ẩn khi `coveredCount = 0` hoặc `warrantyStatus = EXPIRED`.
- `priceSource = REFERENCE_PRICE` ⇒ thêm `*` sau tên.
- Định dạng tiền: `Intl.NumberFormat('vi-VN')` + " ₫"; **không** tự cộng — tổng lấy `chargeableTotal`.

## 4.4 EstimateTotal & Disclaimer

- `chargeableTotal`; nếu `= 0` ⇒ "Mốc này không phát sinh chi phí theo định mức" (FF EDGE-1004).
- Badge cố định `estimateLabel` ("Chi phí ước tính") + câu lưu ý chi phí thực tế (FF BR-1005).
- `hasReferencePrice` ⇒ chú thích `*`.
- `warrantyStatus = EXPIRED` ⇒ ghi "Xe đã hết thời hạn bảo hành"; `UNKNOWN` ⇒ "Chưa có dữ liệu bảo hành từ hãng".

## 4.5 NextActions

- "Gửi xưởng báo giá" và "Đặt lịch" mang theo `odoMilestone` + `workshopId` hiện tại. Ghi chú nhỏ: "Đặt lịch không bắt buộc có báo giá".
- Ẩn cả hai khi `status = NO_RULE`; thay bằng "Liên hệ xưởng" (mở thông tin xưởng).

## 4.6 CompareView (SCR-1004) `[Đề xuất — Q-1003]`

- Chọn 2–3 xưởng từ WorkshopSelector (multi-select, tối đa 3).
- Bảng: xưởng | tổng ước tính | số mục giá tham khảo; thứ tự theo response (backend đã sắp).
- Dòng lỗi riêng lẻ hiển thị "Không tính được cho xưởng này".

## 4.7 CARD-EST (trong chat)

- Render từ `chat_message.meta.estimate` (cùng schema `data` của `API-EST-02`).
- Gọn: mốc, xưởng, tối đa 3 dòng tính phí + "và N mục khác", tổng, badge "Chi phí ước tính", nút "Xem chi tiết".

---

# 5. User Interaction

| # | User Action | FE Behavior | API |
|---|---|---|---|
| 1 | Mở `/estimate` | Gọi song song `API-EST-01` và `API-EST-02` (không truyền tham số nếu query trống) | EST-01, EST-02 |
| 2 | Đổi mốc | Cập nhật query `odoMilestone`, gọi lại `API-EST-02` | EST-02 |
| 3 | Đổi xưởng | Mở SCR-1003; chọn ⇒ cập nhật query `workshopId`, gọi lại | BK-01, EST-02 |
| 4 | "So sánh với xưởng khác" | `/estimate/compare?odoMilestone=…` | EST-03 |
| 5 | "Gửi xưởng báo giá" / "Đặt lịch" | Điều hướng kèm tham số | — |
| 6 | Thử lại khi lỗi | Gọi lại request vừa lỗi | — |

---

# 6. State Management

## 6.1 State Model

```ts
type EstimateViewState =
  | { kind: 'LOADING' }
  | { kind: 'READY'; estimate: CostEstimate }
  | { kind: 'NO_RULE' }
  | { kind: 'NEED_MILESTONE'; validMilestones: number[] }   // 422 MILESTONE_REQUIRED
  | { kind: 'NEED_WORKSHOP' }                               // 422 WORKSHOP_REQUIRED
  | { kind: 'ERROR'; code: string };
```

## 6.2 Notes

- Nguồn sự thật cho mốc/xưởng là **query string** (chia sẻ link, back/forward giữ nguyên).
- Cache `API-EST-01` theo `userVehicleId` trong phiên; `API-EST-02` không cache quá 60 s (giá có thể đổi).
- Huỷ request cũ khi đổi mốc/xưởng liên tiếp (AbortController) để tránh hiển thị dự toán cũ.

---

# 7. API Integration

## 7.1 `API-EST-01`

```http
GET /api/v1/user-vehicles/{userVehicleId}/maintenance-milestones
```

## 7.2 `API-EST-02`

```http
GET /api/v1/user-vehicles/{userVehicleId}/cost-estimate?odoMilestone={k}&workshopId={w}
```

| Response | FE |
|---|---|
| `200 status=READY` | Render §4 |
| `200 status=NO_RULE` | §10.1 |
| `422 MILESTONE_REQUIRED` / `MILESTONE_NOT_FOUND` | Mở MilestoneSelector với `details.validMilestones` |
| `422 WORKSHOP_REQUIRED` | Mở WorkshopSelector |
| `404 WORKSHOP_NOT_FOUND` | Toast "Xưởng hiện không nhận khách", mở WorkshopSelector |
| `404 VEHICLE_NOT_FOUND` | Về `/dashboard` |
| `503` / `500` | §11 |

## 7.3 `API-EST-03`

```http
GET /api/v1/user-vehicles/{id}/cost-estimate/compare?odoMilestone={k}&workshopIds={a}&workshopIds={b}
```

---

# 8. Client-side Validation

| Rule | Behavior |
|---|---|
| So sánh: 2–3 xưởng | Nút "So sánh" disabled khi < 2; không cho chọn thứ 4 |
| `odoMilestone` từ query không nằm trong `API-EST-01` | Bỏ tham số, dùng mốc tiếp theo |

---

# 9. Loading States

- Skeleton cho danh sách hạng mục và tổng; selector hiển thị giá trị cũ kèm spinner nhỏ khi tính lại.

# 10. Empty States

## 10.1 `NO_RULE`

> "EV Care chưa có định mức bảo dưỡng cho mẫu xe/mốc này nên chưa thể dự toán. Bạn có thể liên hệ xưởng để được báo giá." — **không** hiển thị bất kỳ con số nào (FF BR-1009).

## 10.2 Không có xưởng

> "Chưa xác định được xưởng. Bạn chọn một xưởng để xem chi phí." + nút mở WorkshopSelector.

# 11. Error States

| Code | Message |
|---|---|
| `SERVICE_UNAVAILABLE` / `INTERNAL_SERVER_ERROR` | "Tạm thời chưa tính được chi phí, bạn thử lại sau ít phút." + nút Thử lại (FF EF-1001) |
| Mất mạng | "Không có kết nối mạng." + Thử lại |

---

# 12. Navigation

| Route | Screen | Guard |
|---|---|---|
| `/estimate` | SCR-1001 | Chủ xe active |
| `/estimate/compare` | SCR-1004 | Chủ xe active |

---

# 13. Permission / Visibility

- Chỉ vai trò chủ xe; route không xuất hiện trong Workshop Portal.

# 14. Responsive / Accessibility

- Mobile-first; nút hành động chính cố định cuối màn trên mobile.
- Số tiền có `aria-label` đầy đủ ("một triệu ba trăm nghìn đồng" không bắt buộc — tối thiểu đọc được số và đơn vị).
- Dấu `*` có chú thích văn bản, không chỉ dựa vào màu.

# 15. Analytics

| Event | Properties |
|---|---|
| `estimate_viewed` | `odoMilestone`, `workshopSelectedBy`, `status`, `hasReferencePrice` |
| `estimate_next_action` | `action = QUOTE / BOOKING / COMPARE` |

---

# 16. Acceptance Criteria (FE)

## AC-FE-1001 — Tổng hiển thị đúng `chargeableTotal`

**Given** response có `chargeableTotal = 1300000` **When** render **Then** tổng hiển thị "1.300.000 ₫", FE không tự cộng.

## AC-FE-1002 — `NO_RULE` không có số

**Given** `status = NO_RULE` **When** render **Then** không có con số tiền nào trên màn; nút Gửi báo giá/Đặt lịch bị ẩn.

## AC-FE-1003 — Nhãn ước tính luôn hiện

**Given** `status = READY` **Then** badge "Chi phí ước tính" và câu lưu ý luôn hiển thị.

## AC-FE-1004 — Thẻ chat khớp màn chi tiết

**Given** `CARD-EST` trong chat **When** bấm "Xem chi tiết" **Then** SCR-1001 hiển thị cùng mốc, xưởng và cùng tổng (tại cùng thời điểm giá).

---

# 17. Technical Notes

- Vite + React 19 + React Router 7 + Tailwind 4 (theo `frontend/package.json`).
- Tái dùng layout/khối "Thông tin xe" của `MaintenanceEstimate.tsx`; tách `features/estimate/` (api, hooks, components) khỏi `features/quotes/`.
- Kiểu `CostEstimate` sinh từ schema API; không dùng lại `ServiceItem` mock.

# 18. Open Questions

| ID | Question |
|---|---|
| `Q-1003` | Có làm SCR-1004 trong MVP? |
| `Q-FE-1001` | Có cần nút chia sẻ dự toán (ảnh/link) không? `[Đề xuất]` không trong MVP |

# 19. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu |
