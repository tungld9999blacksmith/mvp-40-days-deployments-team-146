# Entity Specification — Bản đồ xưởng (Google Maps)

> Entity cho Feature `FEAT-P2-BK05`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-05-phase2-spec.ff.md). **API:** [API Spec](bk-05-phase2-spec.api.md).
>
> **Nguyên tắc:** BK-05 hầu như chỉ đọc dữ liệu có sẵn (`workshop` có toạ độ, giờ mở cửa, sức chứa). Thời gian di chuyển là dữ liệu tạm, đệm Redis ≤ 30 phút, không lưu DB. Bảng mới duy nhất là bộ đếm sử dụng API bản đồ để kiểm soát ngân sách (AC-BK05-02, NFR-07); bảng này dùng chung cho mọi tính năng gọi Google Maps Platform.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-BK05` — BK-05 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [bk-05-phase2-spec.ff.md](bk-05-phase2-spec.ff.md) |
| Related API | [bk-05-phase2-spec.api.md](bk-05-phase2-spec.api.md) |
| Related FE | [bk-05-phase2-spec.fe.md](bk-05-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table / Store | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-BK05-01` | `ExternalApiUsageDaily` | `external_api_usage_daily` | **Mới** | Đếm lượt gọi + chi phí ước tính theo ngày, theo SKU |
| `ENT-BK05-02` | Travel-time cache | Redis `travel:{cell}:{workshopId}:{bucket}` | **Mới (Redis)** | TTL 30 phút |
| `ENT-008` | `Workshop` | `workshop` | Có sẵn — không đổi cột | Đọc `latitude`, `longitude`, `address`, `status`, `region` |
| — | `WorkshopOperatingHour` | `workshop_operating_hour` | Có sẵn — không đổi | Giờ mở cửa hôm nay, lọc "đang mở cửa" |

---

# 2. `external_api_usage_daily` (ENT-BK05-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `usage_date` | `date` | No | — | PK (1/3), theo Asia/Ho_Chi_Minh |
| `provider` | `varchar(16)` | No | — | PK (2/3): `GOOGLE_MAPS` (mở rộng sau: `GOOGLE_CALENDAR`) |
| `sku` | `varchar(32)` | No | — | PK (3/3): `MAPS_JS_LOAD`, `ROUTES_COMPUTE`, `PLACES_AUTOCOMPLETE`, `GEOCODING` |
| `call_count` | `integer` | No | `0` | |
| `estimated_cost_usd` | `numeric(10,4)` | No | `0` | `call_count × MAPS_SKU_PRICE_USD[sku]` (config, cập nhật theo bảng giá Google) |
| `updated_at` | `timestamptz` | No | `now()` | |

Ghi bằng job gộp mỗi 5 phút từ bộ đếm Redis `usage:{provider}:{sku}:{yyyymmdd}` (INCR khi gọi); không ghi DB trên đường nóng.

## 2.1 Giới hạn theo người dùng (NFR-07)

Redis `usage:user:{userId}:{sku}:{yyyymmdd}` TTL 2 ngày. Không lưu DB.

| SKU | Giới hạn mỗi chủ xe / ngày | Config |
|---|---|---|
| `ROUTES_COMPUTE` (gọi thật, không tính lượt trúng đệm) | 60 | `MAPS_ROUTES_PER_USER_DAY` |
| `MAPS_JS_LOAD` | 30 | `MAPS_LOADS_PER_USER_DAY` |

---

# 3. Travel-time cache (ENT-BK05-02)

| Thành phần khoá | Giá trị |
|---|---|
| `cell` | Ô lưới ~500 m: `round(lat / 0.0045)`, `round(lng / 0.0045)` (BR-BK05-07: toạ độ chính xác không vào khoá, không gửi Google) |
| `workshopId` | Xưởng đích |
| `bucket` | Khung 15 phút của thời điểm khởi hành (theo giờ Asia/Ho_Chi_Minh) |

Giá trị: `{ "durationSec": 720, "distanceM": 3400, "fetchedAt": "…" }`, TTL 1.800 s (BR-BK05-03).

Điểm gốc gửi Google Routes là **tâm ô lưới**, không phải toạ độ thiết bị.

---

# 4. Business Rules (bổ sung)

## BR-ENT-BK05-01 — Không lưu vị trí chủ xe

API bản đồ nhận toạ độ trong request và chỉ dùng trong request đó (tính khoảng cách, ô lưới). Không ghi `user_location` từ BK-05; lưu vị trí chỉ qua hồ sơ BK-01 khi chủ xe chủ động lưu và có `CONSENT_LOCATION` (FF §16).

## BR-ENT-BK05-02 — Xưởng thiếu toạ độ

`workshop.latitude IS NULL` ⇒ không ghim, vẫn có trong danh sách với `distanceKm = null` (EF-BK05-03).

---

# 5. Migration

Một revision: bảng `external_api_usage_daily`. Không đổi bảng khác.

---

# 6. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
