# Frontend Technical Specification — Chỉ số đo hiệu quả

> Frontend cho Feature `FEAT-P2-PL03` (SCR-PL03-01) và việc gửi sự kiện phía client.
>
> **Nguồn nghiệp vụ:** [Functional Spec](pl-03-phase2-spec.ff.md). **API:** [API Spec](pl-03-phase2-spec.api.md) (`API-PL03-01..04`).
>
> **Nguyên tắc:** frontend chỉ gửi sự kiện mà backend không tự biết (một thẻ thực sự hiển thị trên màn hình). Không gửi định danh, văn bản tự do hay toạ độ. Các sự kiện `analytics` liệt kê ở mục 8 của từng FE spec khác là **sự kiện analytics UI** (đi qua hàm `track` hiện có ở `shared/utils/track.ts`); chỉ các sự kiện có trong danh mục PL-03 mới vào `product_event`.

---

## 1. Document Information

| Field | Value |
|---|---|
| Document ID | `FE-SPEC-P2-PL03` |
| Version | `v0.1` |
| Status | `Draft` |
| Screens | SCR-PL03-01 Bảng chỉ số nội bộ; `/technician/metrics` (chỉ số xưởng) |
| Routes | `/internal/metrics` (mới, chỉ claim `ops`), `/technician/metrics` (mới) |
| Feature folder | `frontend/src/features/metrics/` (mới), `frontend/src/shared/analytics/productEvents.ts` (mới) |
| Created Date | `2026-10-12` |

---

# 2. Components

## 2.1 `productEvents.ts` — gửi sự kiện client

```ts
export function emitProductEvent(name: ClientEventName, props: Record<string, string | number | boolean>): void
```

- `ClientEventName` là union cố định (hiện có: `option_shown`); TypeScript chặn tên lạ.
- Gom hàng đợi trong bộ nhớ, gửi `POST /metrics/client-events` mỗi 5 s hoặc khi đủ 20 sự kiện, và khi `visibilitychange = hidden` (`navigator.sendBeacon` nếu có, kèm token qua header không được với beacon ⇒ dùng `fetch(..., { keepalive: true })`).
- `idempotencyKey` = `crypto.randomUUID()`.
- Lỗi mạng ⇒ giữ tối đa 100 sự kiện, bỏ phần cũ; **không** bao giờ hiện lỗi cho người dùng hay chặn UI (BR-PL03-04).
- Bộ lọc client trước khi gửi: loại khoá cấm (`phone`, `email`, `vin`, `licensePlate`, `lat`, `lng`, `name`, `content`) — lớp phòng thủ thứ hai.

`option_shown`: `ScheduleOptionsList` (BK-01) gọi khi thẻ phương án vào viewport ≥ 50 % lần đầu (`IntersectionObserver`), props `{ runId, rank, tier }`.

## 2.2 `MetricsDashboardPage` (SCR-PL03-01, `/internal/metrics`)

| Vùng | Nội dung |
|---|---|
| Bộ lọc | Khoảng tuần (mặc định 8 tuần gần nhất), xưởng (tất cả / một xưởng) |
| Lưới chỉ số | 12 thẻ M-01…M-12: tên, giá trị tuần gần nhất (`font-mono`), mục tiêu, mũi tên xu hướng so với tuần trước (kèm chữ "tăng / giảm", không chỉ màu), `sampleSize`; `value = null` ⇒ "Chưa đủ dữ liệu" |
| Xu hướng | Bấm thẻ mở biểu đồ đường theo tuần (SVG thuần, không thêm thư viện), trục dùng token màu; hover hiện giá trị + cỡ mẫu |
| Định nghĩa | Liên kết "Định nghĩa v{n}" mở drawer `API-PL03-03` (công thức, ghi chú thay đổi) |

Truy cập: route bọc `RequireOpsClaim` (đọc custom claim `ops` từ Firebase ID token); không có ⇒ 404 nội bộ. Không có link từ app chủ xe / xưởng.

## 2.3 `WorkshopMetricsPage` (`/technician/metrics`)

Chỉ số có chiều xưởng (M-05, M-06, M-07, M-09, M-10, M-11) từ `API-PL03-04`; cùng thẻ chỉ số của §2.2 ở chế độ gọn. Link từ `TechnicianDashboard` ("Hiệu quả xưởng"). WS-01 (tỉ lệ duyệt tay) và BK-10 (báo cáo A/B) dùng lại thẻ này.

---

# 3. API Integration & Errors

`features/metrics/api.ts`: `getInternalMetrics`, `getMetricDefinitions`, `getWorkshopMetrics`.

| API | Lỗi | Xử lý |
|---|---|---|
| PL03-01 | Bất kỳ | Bỏ qua im lặng |
| PL03-02/04 | `403` | Trang 404 nội bộ / "Bạn không có quyền xem" |
| PL03-02/04 | 5xx | Lỗi khối + "Thử lại" |

---

# 4. Acceptance Criteria (FE)

1. `emitProductEvent` không bao giờ throw và không gửi khoá cấm (test).
2. `option_shown` chỉ gửi một lần cho mỗi (`runId`, `rank`).
3. Trang nội bộ chỉ mở được với claim `ops`.
4. Không thêm thư viện biểu đồ; hai theme; `npm test`, `npx tsc --noEmit -p .` qua.

---

# 5. Tests (Vitest)

| File | What | Count |
|---|---|---|
| `shared/analytics/productEvents.test.ts` | Gom lô 20 / 5 s (đồng hồ giả); lọc khoá cấm; lỗi fetch không throw; giới hạn 100 | +5 |
| `metrics/metricCard.test.ts` | `metricCardView(row)` → giá trị, xu hướng có chữ, "Chưa đủ dữ liệu" | +3 |
| `metrics/lineChart.test.ts` | `buildPath(series, w, h)` tạo path SVG đúng điểm | +2 |

---

# 6. Truy vết FF → FE

| FF | FE |
|---|---|
| UC-PL03-01, BR-PL03-02, 04 | §2.1 |
| SCR-PL03-01, BR-PL03-06 | §2.2 |
| FF §16 (chủ xưởng) | §2.3 |

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
