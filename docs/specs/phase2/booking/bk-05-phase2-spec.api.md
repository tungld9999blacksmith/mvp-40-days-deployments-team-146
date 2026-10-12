# API Technical Specification — Bản đồ xưởng (Google Maps)

> Backend cho Feature `FEAT-P2-BK05`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-05-phase2-spec.ff.md). **Entity:** [Entity Spec](bk-05-phase2-spec.entity.md).
>
> **Tái dùng:** `GET /workshops/nearby` + `WorkshopLocationFinder` / `geo_index.py` (us-029, us-061), `BookingService.open_slots` / `CapacityService.occupancy` (WS-02) cho số chỗ, `workshop_operating_hour`, điểm đánh giá PS-02 (`WorkshopRatingService`), `PartsAvailabilityService` (BK-09), `SchedulerService.run` (BK-01, `trigger = MAP`). Google Routes qua adapter mới `infrastructure/location/google_routes.py`.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-BK05` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/booking/map.py` (mới) + route trong `booking/route.py`; `modules/location` cho cấu hình bản đồ |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-BK05-01` | `GET` | `/workshops/map` | Ghim xưởng + số chỗ ngày đang xem + bộ lọc | UC-BK05-01, 02, BR-BK05-01, 02 |
| `API-BK05-02` | `GET` | `/workshops/travel-times` | Thời gian di chuyển theo giao thông cho tối đa 10 xưởng | BR-BK05-03, BR-BK05-07 |
| `API-BK05-03` | `GET` | `/maps/config` | Khoá API bản đồ (giới hạn domain), tâm mặc định, cờ hạn mức | EF-BK05-01, NFR-07 |
| `API-BK05-04` | `POST` | `/maps/usage` | Frontend báo một lượt tải bản đồ (đếm chi phí) | AC-BK05-02 |
| `JOB-BK05-01` | Celery | `maps.usage_rollup` (5 phút) + `maps.budget_check` (giờ) | Gộp đếm, cảnh báo 80 % ngân sách | AC-BK05-02 |

"Đặt ở đây" dùng `POST /scheduling/runs` của BK-01 với `trigger = MAP`, `overrides.workshopId` (UC-BK05-03) — không có endpoint riêng.

---

# 2. Authorization & Guards

Chủ xe đăng nhập (FF §16). Giới hạn tần suất: `API-BK05-01` 60 lần / phút / chủ xe; `API-BK05-02` theo entity §2.1. Vượt ⇒ `429 RATE_LIMITED` (`details.retryAfter`) cho API-BK05-01; với API-BK05-02 **không** lỗi mà trả `travelTimes` rỗng + `limited: true` (frontend ẩn thời gian di chuyển, giữ khoảng cách chim bay).

---

# 3. API-BK05-01 — `GET /workshops/map`

## 3.1 Query

| Field | Validation / ý nghĩa |
|---|---|
| `date` | `YYYY-MM-DD`, hôm nay … hôm nay + 60; mặc định hôm nay |
| `lat`, `lng` | Tuỳ chọn; cả hai hoặc không. Chỉ dùng khi frontend đã có quyền vị trí (`CONSENT_LOCATION`, PL-01) |
| `anchor` | `DEVICE` / `PROFILE` / `CITY` — frontend báo điểm neo đang dùng (BR-BK05-05) |
| `bbox` | `minLat,minLng,maxLat,maxLng` — vùng đang nhìn; không có ⇒ bán kính 30 km quanh tâm |
| `available` | `bool` — lọc "Còn chỗ" (AF-BK05-01) |
| `openNow` | `bool` — đang mở cửa (giờ máy chủ) |
| `minRating` | `1..5` — chỉ áp khi xưởng đủ `MIN_REVIEWS` (PS-02) |
| `hasParts` | `bool` — chỉ khi BK-09 bật; cần `userVehicleId` để biết hạng mục |
| `userVehicleId` | Tuỳ chọn, cho `hasParts` |

## 3.2 Processing

1. Tâm: `lat/lng` → hồ sơ BK-01 (`anchor_location_id`) → `MAP_DEFAULT_CENTER` của khu vực có nhiều xưởng nhất (BR-BK05-05).
2. Xưởng `ACTIVE` trong `bbox` qua `geo_index`; xưởng thiếu toạ độ ⇒ chỉ trong `list` (EF-BK05-03).
3. Số chỗ của `date` (BR-BK05-01): một lượt `open_slots(workshop, date, date)` mỗi xưởng (đã gộp 3 truy vấn / xưởng); `remainingSlots` = số khung `available` còn ≥ 1 chỗ; `remainingCapacity` = tổng chỗ còn. Xưởng bật WS-02 ⇒ theo `occupancy`, quy về số lịch chuẩn `LEGACY_BOOKING_MIN`. Tối đa 40 xưởng mỗi lần (giới hạn truy vấn); vượt ⇒ `truncated: true`, frontend yêu cầu phóng to.
4. Khoảng cách chim bay (haversine) từ tâm.
5. Áp lọc. Không còn xưởng nào trong vùng ⇒ thêm `nearestOutside`: xưởng `ACTIVE` gần nhất ngoài vùng (EDGE-BK05-02).
6. Không gọi Google.

## 3.3 Response `200`

```json
{
  "data": {
    "date": "2026-10-12",
    "center": { "lat": 21.03, "lng": 105.78, "anchor": "DEVICE" },
    "workshops": [
      { "workshopId": "…", "name": "VinFast Mỹ Đình", "address": "…", "lat": 21.02, "lng": 105.77,
        "distanceKm": 3.4, "openToday": { "open": "08:00", "close": "17:30" }, "openNow": true,
        "rating": { "avg": 4.6, "count": 18 }, "remainingCapacity": 5, "remainingSlots": 4,
        "isPreferred": true, "parts": null }
    ],
    "list": [ { "…": "xưởng thiếu toạ độ, cùng shape, lat/lng = null" } ],
    "nearestOutside": null,
    "truncated": false,
    "capacityAsOf": "2026-10-12T02:15:00Z"
  }
}
```

`rating = null` khi chưa đủ `MIN_REVIEWS` hoặc PS-02 chưa bật. `parts` = `{ "status": "IN_STOCK" | "ARRIVING" | "UNKNOWN" }` khi `hasParts` được yêu cầu (BK-09).

---

# 4. API-BK05-02 — `GET /workshops/travel-times`

Query: `lat`, `lng` (bắt buộc), `workshopIds` (≤ 10), `departAt` (mặc định now).

1. `cell` = ô lưới ~500 m của (`lat`, `lng`) (entity §3). Điểm gốc gửi Google = tâm ô (BR-BK05-07).
2. Mỗi xưởng: đọc Redis `travel:{cell}:{workshopId}:{bucket}`; trúng ⇒ dùng.
3. Trượt: gộp mọi xưởng trượt vào **một** lời gọi Routes `computeRouteMatrix` (`travelMode = DRIVE`, `routingPreference = TRAFFIC_AWARE`, timeout 2 s), ghi đệm TTL 30 phút, INCR bộ đếm `ROUTES_COMPUTE` (số phần tử) + bộ đếm theo chủ xe.
4. Lỗi / hết hạn mức / vượt giới hạn ⇒ trả những xưởng trúng đệm, còn lại `durationMin = null`; `degraded: true` (EF-BK05-02). Không bao giờ `5xx`.

```json
{ "data": { "travelTimes": [ { "workshopId": "…", "durationMin": 12, "distanceKm": 3.6, "cached": true } ], "degraded": false, "limited": false } }
```

---

# 5. API-BK05-03 — `GET /maps/config`

```json
{ "data": { "mapsEnabled": true, "browserKey": "AIza…", "mapId": "evcare-light", "defaultCenter": { "lat": 21.0278, "lng": 105.8342 },
            "dailyLoadsRemaining": 27, "fallbackReason": null } }
```

- `browserKey`: khoá **chỉ dùng phía trình duyệt**, giới hạn HTTP referrer = domain app và chỉ bật Maps JavaScript API (FF §23). Khoá server (Routes) không bao giờ trả ra.
- `mapsEnabled = false` khi: ngân sách tháng ≥ 100 % (`fallbackReason = BUDGET`), chủ xe hết lượt tải ngày (`USER_LIMIT`), hoặc tắt bằng cờ `MAPS_ENABLED` ⇒ frontend dùng danh sách (SCR-BK05-03).

---

# 6. API-BK05-04 — `POST /maps/usage`

Body `{ "sku": "MAPS_JS_LOAD" }`. Frontend gọi một lần mỗi lần khởi tạo bản đồ (không mỗi lần pan/zoom). INCR bộ đếm hệ thống + chủ xe. `204`. Không xác thực nội dung, chỉ đếm (Google Cloud Billing budget alert là lớp kiểm soát thứ hai, đặt cùng ngưỡng).

---

# 7. JOB-BK05-01 — ngân sách

- `maps.usage_rollup` (5 phút): Redis → `external_api_usage_daily`.
- `maps.budget_check` (mỗi giờ): `Σ estimated_cost_usd` tháng hiện tại / `MAPS_MONTHLY_BUDGET_USD` (P2Q-07). ≥ 80 % lần đầu trong tháng ⇒ cảnh báo vận hành (log `maps.budget_80` mức `WARNING` + alert Grafana + email vận hành) (AC-BK05-02); ≥ 100 % ⇒ `mapsEnabled = false` cho tới tháng sau hoặc vận hành nâng ngân sách.

---

# 8. "Đặt ở đây" (UC-BK05-03)

Frontend gọi `POST /scheduling/runs`:

```json
{ "userVehicleId": "…", "trigger": "MAP", "overrides": { "workshopId": "…" }, "applyAutomation": true, "location": { "lat": 21.03, "lng": 105.78 } }
```

BK-01 xử lý `overrides.workshopId`: chỉ xưởng này (AC-BK05-03), giữ các ràng buộc khác (BR-BK05-06). Ngày đang xem kín ⇒ cửa sổ BK-01 bình thường tìm ngày gần nhất tại xưởng đó (AF-BK05-03). Không còn gì ⇒ `NO_OPTION` + nới.

---

# 9. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | `lat/lng` thiếu một nửa, `bbox` sai, `date` ngoài khoảng, `workshopIds` > 10 | BK05-01, 02 |
| 429 | `RATE_LIMITED` | Quá 60 lần / phút | BK05-01 |

---

# 10. Observability

- Log `map.loaded` (`workshops`, `filters`, `ms`), `routes.matrix` (`elements`, `cache_hit_ratio`, `ms`), `maps.budget_80`, `maps.disabled` (`reason`). Không log toạ độ (chỉ `cell`).
- Metric: `map_pins_latency_seconds` (p90 ≤ 2 s trên tải backend; mục tiêu FF tính cả mạng 4G), `routes_cache_hit_ratio`, `maps_cost_usd_month`.

---

# 11. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Ô lưới: hai điểm cách 100 m cùng ô; khoá đệm không chứa toạ độ gốc | +2 |
| Unit | Thứ tự điểm neo thiết bị → hồ sơ → thành phố | +3 |
| Service | Số chỗ trên ghim khớp `open_slots` (AC-BK05-04); xưởng kín ⇒ `remainingCapacity = 0` vẫn trả về | +2 |
| Service | Lọc còn chỗ / đang mở / đánh giá / phụ tùng | +4 |
| Service | Routes lỗi ⇒ `degraded`, không 5xx (EF-BK05-02); trúng đệm không gọi Google | +2 |
| Service | Vượt giới hạn chủ xe ⇒ `limited` | +1 |
| Job | 80 % ngân sách ⇒ một cảnh báo / tháng (AC-BK05-02); 100 % ⇒ `mapsEnabled = false` | +2 |
| Integration | `trigger = MAP` + `workshopId` ⇒ mọi phương án thuộc xưởng đó (AC-BK05-03) | +1 |

---

# 12. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
