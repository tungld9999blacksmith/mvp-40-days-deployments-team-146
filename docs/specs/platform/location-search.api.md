# API Technical Specification — Nền tảng Tìm vị trí (Location Search)

> Đặc tả API backend cho **tìm vị trí theo từ khoá** (gợi ý khi gõ), **lấy chi tiết một địa điểm** và **đổi toạ độ thành địa chỉ**. Đây là nền tảng **dùng chung**, không gắn với một use case. Các màn dùng: đăng ký chủ xe (địa chỉ nhà), đăng ký chủ xưởng (địa chỉ xưởng), đặt lịch (điểm gốc tìm xưởng gần), và các màn sau này.
>
> **Nhà cung cấp:** Amazon Location Service — Places API v2, dữ liệu **GrabMaps**. Backend làm **proxy**: frontend không bao giờ gọi thẳng Places API.
>
> **Hiển thị bản đồ** (tile) đi thẳng từ trình duyệt tới Amazon Location Maps, không qua backend. Xem §8.
>
> Điểm chưa chốt đánh dấu `[Đề xuất]`. Câu hỏi mở ở §13.

---

# 0. Document Information

| Field | Value |
| --- | --- |
| Document ID | `API-SPEC-PLATFORM-LOC-001` |
| Version | `v1.1` |
| Status | `Implemented (backend)` — frontend chưa làm |
| Owner | Backend Team |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/location/` (route, service, schemas, errors, dependency, ports, domain) · `backend/src/infrastructure/location/` (`aws_places.py`, `fake.py`) · `backend/src/common/geo/provinces.py` (chuẩn hoá 34 tỉnh) |
| Created Date | `2026-10-10` |

## 0.1 API Catalog

| ID | Method | Endpoint | Caller | Mục đích | AWS operation |
| --- | --- | --- | --- | --- | --- |
| `API-LOC-001` | `GET` | `/api/v1/locations/suggest` | App chủ xe, Workshop Portal | Gợi ý địa điểm khi người dùng gõ | `Suggest` |
| `API-LOC-002` | `GET` | `/api/v1/locations/places/{placeId}` | App chủ xe, Workshop Portal | Chi tiết địa điểm đã chọn: địa chỉ chuẩn hoá + toạ độ | `GetPlace` |
| `API-LOC-003` | `GET` | `/api/v1/locations/reverse` | App chủ xe, Workshop Portal | Toạ độ (GPS, ghim trên bản đồ) → địa chỉ | `ReverseGeocode` |

## 0.2 Màn hình dùng nền tảng

| Màn | Trường đang có | Dùng API | Ghi gì vào đâu |
| --- | --- | --- | --- |
| Đăng ký chủ xe — hồ sơ (us-001, API-003) | `location: LocationIn` | `001` → `002`; nút "Vị trí hiện tại" → `003` | `user_location` (`address_line`, `ward`, `district`, `province`, `latitude`, `longitude`, `place_id`, `source`) |
| Đăng ký chủ xưởng (us-009) | `address`, `latitude`, `longitude` | `001` → `002`, `003` | `workshop_registration` → `workshop` |
| Đặt lịch — chọn điểm gốc (us-029, `LocationAnchorPicker`) | `query` / `lat`,`lng` | `001` → `002` | Không lưu. Gửi `lat`/`lng` vào `GET /workshops/nearby` → xếp theo khoảng cách thật |
| Báo giá — chọn xưởng (`WorkshopPickerDrawer`) | như trên | như trên | Không lưu |

Không cần đổi schema của API-003 hay API onboarding chủ xưởng: `LocationIn` đã có `latitude`, `longitude`, `placeId`, `source` (`MANUAL | MAP_PICK | GPS`).

## 0.3 Kiến trúc

```
Trình duyệt (Vite + React)
  ├── ô tìm vị trí ──▶ backend /api/v1/locations/* ──▶ PlaceSearchProvider (port)
  │                     (Firebase auth, rate limit,       └── AwsGrabPlacesProvider (adapter)
  │                      chuẩn hoá tỉnh, envelope lỗi)          └── places.geo.ap-southeast-1.amazonaws.com/v2/*
  └── bản đồ (MapLibre) ──────────────────────────────────▶ maps.geo.ap-southeast-1.amazonaws.com/v2/* (key riêng, chỉ Maps)
```

- **Port** `PlaceSearchProvider` có ba hàm `suggest`, `get_place`, `reverse`, trả về DTO trung lập, không phải JSON của AWS. Đổi nhà cung cấp (Goong, VietMap…) chỉ cần viết adapter mới.
- **Adapter giả** `FakePlacesProvider` trả dữ liệu cố định, dùng cho test, dev không có key và chế độ demo.

## 0.4 Region và GrabMaps — bắt buộc đọc

| Điểm | Nội dung |
| --- | --- |
| Region gọi Places/Maps | **`ap-southeast-1` (Singapore)**. Dự phòng: `ap-southeast-5` (Malaysia) |
| Vì sao | AWS chỉ dùng dữ liệu GrabMaps (có phủ Việt Nam) ở hai region trên. Region khác, kể cả `ap-southeast-2` (Sydney) đang dùng, trả dữ liệu của nhà cung cấp khác và **không phải GrabMaps** |
| Hạ tầng khác của dự án | Giữ nguyên region hiện tại. Chỉ API key Amazon Location tạo ở `ap-southeast-1`, vì API key gắn với region |
| Không có ở GrabMaps | `Autocomplete`, `Geocode`. Trong `Suggest` không có `MaxQueryRefinements`, `PoliticalView`. Trong `SearchText` không có `QueryId`. `GetPlace` không trả `Contacts`, `OpeningHours`, `AccessPoints` và **không nhận `IntendedUse`**. `ReverseGeocode` có `QueryRadius` tối đa 100 000 m |
| Ngôn ngữ | `vi` (GrabMaps hỗ trợ `en, id, km, lo, ms, my, pt, th, tl, vi, zh`) |

---

# 1. Quy ước chung

## 1.1 Authentication & Authorization

```http
Authorization: Bearer <Firebase ID token>
```

| Endpoint | Dependency `[Đề xuất]` | Ai được gọi |
| --- | --- | --- |
| `API-LOC-001` → `003` | `require_location_caller` + rate limit `suggest_caller` / `detail_caller` (`modules/location/dependency.py`) | Token Firebase hợp lệ **và** `uid` là một `vehicle_user` hoặc `workshop_owner` đã có (mọi trạng thái onboarding), không bị khoá |

- Không dùng `require_active_vehicle_owner`, vì người dùng **đang onboarding** cũng phải tìm được vị trí.
- Chỉ cần token mà không kiểm tra tài khoản thì bất kỳ tài khoản Google nào cũng gọi được, tiêu tiền API. Vì vậy phải kiểm tra `uid` đã đăng ký.
- Token thiếu/sai → `401 UNAUTHORIZED`. `uid` chưa đăng ký → `403 FORBIDDEN`. Tài khoản bị khoá → `403 ACCOUNT_LOCKED`, theo mã sẵn có của module onboarding.

## 1.2 Định dạng chung

- Tên trường JSON: `camelCase`. Toạ độ: số thập phân WGS 84, **luôn là object `{ "lat": …, "lng": … }`**. AWS dùng mảng `[lng, lat]`; adapter phải đổi, frontend không bao giờ thấy mảng này.
- Thành công: `{ "data": ... }`.
- Lỗi: envelope chung theo [error-handling.md](error-handling.md) §1.

```json
{
  "error": {
    "code": "LOCATION_PROVIDER_UNAVAILABLE",
    "message": "Location service is temporarily unavailable.",
    "details": null,
    "traceId": "tr-20261010-0915-abc123"
  }
}
```

## 1.3 Đối tượng dùng chung

### `LatLngDto`

| Field | Type | Nullable | Mô tả |
| --- | --- | --- | --- |
| `lat` | `number` | No | Vĩ độ, `-90..90` |
| `lng` | `number` | No | Kinh độ, `-180..180` |

### `LocationSuggestionDto`

| Field | Type | Nullable | Mô tả |
| --- | --- | --- | --- |
| `placeId` | `string` | No | ID của nhà cung cấp, dùng cho `API-LOC-002`. Coi là chuỗi mờ, không phân tích |
| `title` | `string` | No | Tên hiển thị dòng 1, ví dụ "VinFast Thăng Long", "Phố Trần Duy Hưng" |
| `address` | `string` | Yes | Địa chỉ đầy đủ hiển thị dòng 2 (`Address.Label`) |
| `placeType` | `string` | No | `POI | STREET | ADDRESS | AREA` (gộp từ `PlaceType` của AWS, xem §5.3) |
| `position` | `LatLngDto` | Yes | Có thể thiếu. Toạ độ dùng để lưu **phải** lấy từ `API-LOC-002` |
| `distanceMeters` | `integer` | Yes | Khoảng cách tới `lat`/`lng` của request, nếu có |
| `highlights` | `[{ "start": int, "end": int }]` | No | Đoạn trong `title` khớp từ khoá (để in đậm). Rỗng nếu không có |

### `PlaceDetailDto`

Map 1-1 vào `LocationIn` của API-003 và địa chỉ xưởng của us-009.

| Field | Type | Nullable | Mô tả | → `LocationIn` |
| --- | --- | --- | --- | --- |
| `placeId` | `string` | No | ID của nhà cung cấp | `placeId` |
| `title` | `string` | No | Tên địa điểm | — |
| `placeType` | `string` | No | Như trên | — |
| `addressLine` | `string` | No | Địa chỉ đầy đủ. Nếu nhà cung cấp không có `Label` thì ghép từ các thành phần | `addressLine` |
| `street` | `string` | Yes | Số nhà + đường | — |
| `ward` | `string` | Yes | Phường/xã | `ward` |
| `district` | `string` | Yes | Quận/huyện. **Cấp cũ**: từ 01/07/2025 Việt Nam bỏ cấp huyện; giữ để hiển thị/tương thích | `district` |
| `province` | `string` | Yes | **Một trong 34 tỉnh/thành hiện hành**, đã chuẩn hoá (§5.4). `null` nếu không xác định được | `province` |
| `provinceRaw` | `string` | Yes | Tên tỉnh đúng như nhà cung cấp trả, để đối soát | — |
| `countryCode` | `string` | No | ISO alpha-2, luôn `VN` (kết quả ngoài VN bị loại) | — |
| `position` | `LatLngDto` | No | Toạ độ | `latitude`, `longitude` |
| `provider` | `string` | No | `aws-grabmaps` (hoặc `fake`) | — |

Frontend gửi `source = "MAP_PICK"` khi lấy từ `API-LOC-002`, `source = "GPS"` khi lấy từ `API-LOC-003` với toạ độ GPS.

---

# API-LOC-001 — Gợi ý địa điểm theo từ khoá

```http
GET /api/v1/locations/suggest?q=cau%20giay&lat=21.0285&lng=105.8542&limit=8
```

## 1. Request

| Query | Type | Required | Mặc định | Ràng buộc | Mô tả |
| --- | --- | --- | --- | --- | --- |
| `q` | `string` | Yes | — | Sau khi trim: `2..200` ký tự | Từ khoá người dùng gõ |
| `lat` | `number` | No | — | `-90..90`, đi cùng `lng` | Vị trí ưu tiên (GPS hoặc toạ độ trong hồ sơ). Kết quả gần hơn xếp trên |
| `lng` | `number` | No | — | `-180..180`, đi cùng `lat` | |
| `limit` | `integer` | No | `8` | `1..10` | Số gợi ý tối đa |

Chỉ gửi một trong `lat`/`lng` → `422 INVALID_REQUEST`.

## 2. Processing

1. Xác thực (§1.1). Rate limit theo `uid` (§9).
2. Chuẩn hoá `q`: trim, gộp khoảng trắng.
3. Gọi `Suggest`:

```json
POST https://places.geo.ap-southeast-1.amazonaws.com/v2/suggest?key=<server key>
{
  "QueryText": "cau giay",
  "MaxResults": 8,
  "Language": "vi",
  "BiasPosition": [105.8542, 21.0285],
  "Filter": { "IncludeCountries": ["VNM"] },
  "AdditionalFeatures": ["Core"]
}
```

- Có `lat`/`lng` → `BiasPosition = [lng, lat]`. Không có → `Filter.BoundingBox` = khung Việt Nam `[102.14, 8.18, 109.47, 23.39]`. AWS không cho dùng `BiasPosition` cùng `BoundingBox`/`Circle`.
- `IntendedUse` bỏ trống (mặc định `SingleUse`). **Suggest không cho lưu kết quả.**

4. Chỉ lấy item có `SuggestResultItemType = "Place"`. Bỏ item `Query` (GrabMaps không hỗ trợ query refinement).
2. Loại item có `Address.Country.Code2 ≠ "VN"`. Map sang `LocationSuggestionDto` (§5.3).
3. **Không cache** kết quả, kể cả trong Redis: theo điều khoản AWS, cache là "lưu trữ".

## 3. Response — `200 OK`

```json
{
  "data": {
    "query": "cau giay",
    "items": [
      {
        "placeId": "AQAAAD…",
        "title": "Cầu Giấy",
        "address": "Cầu Giấy, Hà Nội, Việt Nam",
        "placeType": "AREA",
        "position": { "lat": 21.0362, "lng": 105.7906 },
        "distanceMeters": 6750,
        "highlights": [{ "start": 0, "end": 8 }]
      },
      {
        "placeId": "AQAAAE…",
        "title": "Công viên Cầu Giấy",
        "address": "Đường Cầu Giấy, Phường Cầu Giấy, Hà Nội, Việt Nam",
        "placeType": "POI",
        "position": { "lat": 21.0301, "lng": 105.7939 },
        "distanceMeters": 6420,
        "highlights": [{ "start": 11, "end": 19 }]
      }
    ]
  }
}
```

Không có kết quả → `200` với `items: []`. Không trả `404`.

## 4. Errors

| Case | Code | HTTP |
| --- | --- | --- |
| `q` thiếu, ngắn hơn 2 / dài hơn 200 ký tự; chỉ có `lat` hoặc `lng`; `limit` ngoài `1..10` | `INVALID_REQUEST` | 422 |
| Token thiếu/sai | `UNAUTHORIZED` | 401 |
| `uid` chưa đăng ký | `FORBIDDEN` | 403 |
| Vượt rate limit backend | `RATE_LIMIT_EXCEEDED` (+`Retry-After`) | 429 |
| AWS `ThrottlingException`, `5xx`, timeout | `LOCATION_PROVIDER_UNAVAILABLE` | 503 |
| AWS `403 AccessDeniedException` (key sai, hết hạn, thiếu quyền) | `LOCATION_PROVIDER_UNAVAILABLE` + log `ERROR` "misconfigured" | 503 |

---

# API-LOC-002 — Chi tiết địa điểm

```http
GET /api/v1/locations/places/{placeId}
```

## 1. Request

| Param | Vị trí | Type | Required | Ràng buộc |
| --- | --- | --- | --- | --- |
| `placeId` | path | `string` | Yes | `1..500` ký tự (giới hạn của AWS). Client phải URL-encode |

## 2. Processing

1. Xác thực, rate limit (§9).
2. Gọi `GetPlace`:

```http
GET https://places.geo.ap-southeast-1.amazonaws.com/v2/place/{placeId}?language=vi&key=<server key>
```

- **Không gửi `intended-use`**: GrabMaps ở `ap-southeast-1` không hỗ trợ tham số này. Điều khoản lưu trữ: xem §7 và câu hỏi mở Q-01.

3. Nếu `Address.Country.Code2 ≠ "VN"` → `422 LOCATION_OUT_OF_COVERAGE`.
2. Map sang `PlaceDetailDto` (§5.3). Chuẩn hoá `province` (§5.4).

## 3. Response — `200 OK`

```json
{
  "data": {
    "placeId": "AQAAAE…",
    "title": "Công viên Cầu Giấy",
    "placeType": "POI",
    "addressLine": "Đường Cầu Giấy, Phường Cầu Giấy, Hà Nội, Việt Nam",
    "street": "Đường Cầu Giấy",
    "ward": "Phường Cầu Giấy",
    "district": null,
    "province": "Hà Nội",
    "provinceRaw": "Hà Nội",
    "countryCode": "VN",
    "position": { "lat": 21.0301, "lng": 105.7939 },
    "provider": "aws-grabmaps"
  }
}
```

## 4. Errors

| Case | Code | HTTP |
| --- | --- | --- |
| `placeId` rỗng / dài hơn 500 ký tự | `INVALID_REQUEST` | 422 |
| AWS `ValidationException` hoặc `404` (ID không tồn tại, hết hiệu lực) | `LOCATION_NOT_FOUND` | 404 |
| Địa điểm ngoài Việt Nam | `LOCATION_OUT_OF_COVERAGE` | 422 |
| Như `API-LOC-001` | `UNAUTHORIZED` 401 · `FORBIDDEN` 403 · `RATE_LIMIT_EXCEEDED` 429 · `LOCATION_PROVIDER_UNAVAILABLE` 503 | |

---

# API-LOC-003 — Toạ độ → địa chỉ

```http
GET /api/v1/locations/reverse?lat=21.0301&lng=105.7939
```

Dùng cho nút "Dùng vị trí hiện tại" (GPS trình duyệt) và khi người dùng kéo ghim trên bản đồ.

## 1. Request

| Query | Type | Required | Ràng buộc |
| --- | --- | --- | --- |
| `lat` | `number` | Yes | `-90..90` |
| `lng` | `number` | Yes | `-180..180` |

## 2. Processing

1. Xác thực, rate limit (§9).
2. Toạ độ ngoài khung Việt Nam `[102.14, 8.18, 109.47, 23.39]` → `422 LOCATION_OUT_OF_COVERAGE`, không gọi AWS.
3. Gọi `ReverseGeocode`:

```json
POST https://places.geo.ap-southeast-1.amazonaws.com/v2/reverse-geocode?key=<server key>
{
  "QueryPosition": [105.7939, 21.0301],
  "QueryRadius": 500,
  "MaxResults": 1,
  "Language": "vi",
  "IntendedUse": "Storage"
}
```

- `IntendedUse = "Storage"`, vì kết quả thường được ghi vào `user_location` / `workshop`. Giá cao hơn `SingleUse`, xem §7.
- `QueryRadius` `[Đề xuất]` 500 m. GrabMaps cho tối đa 100 000 m.

4. Không có kết quả trong bán kính → `404 LOCATION_NOT_FOUND`. Frontend vẫn giữ toạ độ và cho người dùng tự nhập địa chỉ.
2. Map sang `PlaceDetailDto`. `position` là **toạ độ của request** (vị trí người dùng thật), không phải toạ độ của địa chỉ gần nhất.

## 3. Response — `200 OK`

Cùng dạng `PlaceDetailDto` như `API-LOC-002`.

## 4. Errors

| Case | Code | HTTP |
| --- | --- | --- |
| Thiếu / sai `lat`, `lng` | `INVALID_REQUEST` | 422 |
| Toạ độ ngoài Việt Nam | `LOCATION_OUT_OF_COVERAGE` | 422 |
| Không có địa chỉ nào trong bán kính | `LOCATION_NOT_FOUND` | 404 |
| Như `API-LOC-001` | `UNAUTHORIZED` 401 · `FORBIDDEN` 403 · `RATE_LIMIT_EXCEEDED` 429 · `LOCATION_PROVIDER_UNAVAILABLE` 503 | |

---

# 5. Xử lý nội bộ

## 5.1 Port

```python
class PlaceSearchProvider(Protocol):
    async def suggest(self, query: str, *, near: LatLng | None, limit: int) -> list[LocationSuggestion]: ...
    async def get_place(self, place_id: str) -> PlaceDetail: ...           # raises PlaceNotFound
    async def reverse(self, position: LatLng) -> PlaceDetail: ...          # raises PlaceNotFound
```

- Lỗi hạ tầng của adapter → `ProviderUnavailable`. Service đổi thành mã lỗi miền (§6).
- Chọn adapter theo `LOCATION_PROVIDER` (`aws` | `fake`) trong `get_place_search_provider()`, giống DI seam `get_location_finder()` của booking.

## 5.2 Gọi AWS

| Mục | Giá trị |
| --- | --- |
| HTTP client | `httpx.AsyncClient` dùng chung (keep-alive). Không gọi blocking trong event loop |
| Xác thực tới AWS | API key ở query `?key=` (**server key**, chỉ backend giữ). Phương án thay thế: IAM SigV4 qua `boto3` client `geo-places`, nếu backend chạy trên AWS và có role |
| Timeout | `LOCATION_TIMEOUT_SECONDS` (mặc định 3 s) |
| Retry | 1 lần, backoff 200 ms, chỉ khi `ThrottlingException` / `5xx` / timeout. Không retry `4xx` |
| Không log | API key, URL đầy đủ có `?key=` |

## 5.3 Map từ AWS sang DTO

| DTO | Nguồn AWS |
| --- | --- |
| `title` | `Title` |
| `address` / `addressLine` | `Address.Label` (nếu thiếu thì ghép `Street`, `SubDistrict`, `District`, `Locality`, `Region.Name`) |
| `street` | `AddressNumber` + `Street` |
| `ward` | `Address.SubDistrict`, nếu không có thì `Address.District` `[Đề xuất — xác nhận bằng mẫu thật, Q-03]` |
| `district` | `Address.Locality` hoặc `Address.SubRegion.Name` `[Đề xuất — Q-03]` |
| `provinceRaw` | `Address.Region.Name` |
| `province` | chuẩn hoá `provinceRaw` (§5.4) |
| `position` | `Position` `[lng, lat]` → `{ lat, lng }` |
| `distanceMeters` | `Place.Distance` |
| `highlights` | `Highlights.Title[] → { start: StartIndex, end: EndIndex }` |
| `placeType` | `PointOfInterest` → `POI` · `Street`, `Intersection` → `STREET` · `PointAddress`, `InterpolatedAddress`, `SecondaryAddress` → `ADDRESS` · còn lại (`Region`, `SubRegion`, `Locality`, `District`, `SubDistrict`, `PostalCode`, `Block`…) → `AREA` |

## 5.4 Chuẩn hoá tỉnh/thành

- Dùng chung logic với [tools/workshop_crawl/provinces.py](../../../tools/workshop_crawl/provinces.py), chuyển vào `backend/src/common/geo/provinces.py`: 34 tỉnh/thành hiện hành, bảng tên cũ (63 tỉnh) → mới, bỏ dấu, bỏ tiền tố "Tỉnh"/"Thành phố".
- Thứ tự: `Address.Region.Name` → tìm tên tỉnh trong `Address.Label` (khớp cuối cùng) → `null`.
- Ví dụ: "Bình Dương" → "TP. Hồ Chí Minh"; "Quảng Nam" → "Đà Nẵng"; "Thành phố Hồ Chí Minh" → "TP. Hồ Chí Minh".
- `province` có giá trị khớp với `workshop.region`, nên tìm xưởng theo tỉnh (`RankedBy.REGION`) hoạt động đúng.

---

# 6. Mã lỗi của module `location`

| Code | HTTP | Khi nào | Frontend hiển thị |
| --- | --- | --- | --- |
| `INVALID_REQUEST` | 422 | Tham số sai | Không hiện: frontend chỉ gọi khi `q` đủ 2 ký tự |
| `LOCATION_NOT_FOUND` | 404 | `placeId` hết hiệu lực; reverse không có địa chỉ | "Không tìm thấy địa điểm. Bạn thử tìm lại hoặc nhập địa chỉ." |
| `LOCATION_OUT_OF_COVERAGE` | 422 | Ngoài Việt Nam | "Hiện chỉ hỗ trợ địa điểm tại Việt Nam." |
| `RATE_LIMIT_EXCEEDED` | 429 | Vượt giới hạn (§9) | Im lặng, thử lại sau `Retry-After` |
| `LOCATION_PROVIDER_UNAVAILABLE` | 503 | AWS lỗi / quá tải / key sai | "Chưa tải được gợi ý. Bạn có thể nhập địa chỉ thủ công." + **luôn cho nhập tay** |

Thêm một dòng `location` vào bảng §2.2 của [error-handling.md](error-handling.md). Hàm `locationErrorMessage()` đặt ở `frontend/src/features/location/utils.ts` `[Đề xuất]`.

**Nguyên tắc:** tìm vị trí là **hỗ trợ**, không phải điều kiện bắt buộc. Mọi màn phải cho nhập địa chỉ thủ công khi API lỗi. API-003 vẫn nhận `source = "MANUAL"` không có toạ độ.

---

# 7. Chi phí và điều khoản lưu dữ liệu

| Thao tác | `IntendedUse` | Được lưu? | Mức giá (tham khảo, xem bảng giá hiện hành) |
| --- | --- | --- | --- |
| `Suggest` | `SingleUse` (duy nhất) | **Không**, kể cả cache | Label/Core |
| `GetPlace` (GrabMaps) | không hỗ trợ tham số | **Chưa rõ, Q-01** | Core |
| `ReverseGeocode` | `Storage` | Có | Stored (cao hơn) |

- Free tier Places chỉ có trong **3 tháng đầu** (10 000 Suggest + 20 000 GetPlace/Reverse… mỗi tháng). Sau đó trả theo từng request.
- Tiết kiệm chi phí: frontend debounce 300 ms và chỉ gọi khi `q` có ≥ 2 ký tự; bỏ qua request cũ khi người dùng gõ tiếp (AbortController); backend rate limit.
- `place_id` được lưu vào `user_location.place_id` để đối soát và để lấy lại chi tiết khi cần.

---

# 8. Hiển thị bản đồ (frontend, không qua backend)

Frontend hiện là **Vite + React 19** (không phải Next.js).

| Package | Vai trò |
| --- | --- |
| `maplibre-gl` | Vẽ bản đồ, mã nguồn mở. AWS hướng dẫn dùng thư viện này |
| `react-map-gl` (import từ `react-map-gl/maplibre`) | Component React `<Map>`, `<Marker>` |
| `@aws/amazon-location-utilities-auth-helper` | Chỉ cần nếu sau này gọi SDK Amazon Location từ client. Với tile thì chỉ cần URL style có `?key=` |

```tsx
// Style URL — key chỉ có quyền Maps (GetStyleDescriptor, GetTile), giới hạn referer
const styleUrl =
  `https://maps.geo.${import.meta.env.VITE_AWS_LOCATION_REGION}.amazonaws.com/v2/styles/Standard/descriptor` +
  `?key=${import.meta.env.VITE_AWS_LOCATION_MAP_API_KEY}&color-scheme=Light`

<Map mapStyle={styleUrl} initialViewState={{ latitude: 21.0285, longitude: 105.8542, zoom: 13 }} />
```

- **Hai API key riêng**, đều tạo ở `ap-southeast-1`:

| Key | Giữ ở | Quyền (actions) | Giới hạn |
| --- | --- | --- | --- |
| Server key | Backend `.env` | `geo-places:Suggest`, `geo-places:GetPlace`, `geo-places:ReverseGeocode` | Không giới hạn referer (server gọi). Không bao giờ đưa ra frontend |
| Map key | Frontend `VITE_*` (công khai) | Chỉ `geo-maps:GetTile`, `geo-maps:GetStyleDescriptor` | `AllowReferers`: domain Vercel + `http://localhost:5173/*` |

- Nếu sau này chuyển sang Next.js: MapLibre cần `window`, nên phải đặt trong client component (`"use client"`) và tải bằng `next/dynamic(..., { ssr: false })`.

---

# 9. Rate limit

Dùng `toolkit.rate_limiter` + `rate_limit(...)` có sẵn (`infrastructure/redis/ratelimit`), khoá theo `uid` của Firebase.

| Endpoint | Thuật toán | Giới hạn `[Đề xuất]` | Cấu hình |
| --- | --- | --- | --- |
| `API-LOC-001` | Token bucket | 30 request / phút, burst 10 | `LOCATION_SUGGEST_RATE_PER_MINUTE` |
| `API-LOC-002`, `003` | Token bucket | 20 request / phút | `LOCATION_DETAIL_RATE_PER_MINUTE` |

Redis lỗi → **không chặn** request (fail-open), log `WARNING`. Tìm vị trí không phải thao tác nhạy cảm.

---

# 10. Observability

- Log mỗi request: `traceId`, `uid` (không log email), endpoint, độ dài `q` (**không log nguyên văn `q`**, vì địa chỉ nhà là dữ liệu cá nhân), số kết quả, `provider`, `latencyMs`, mã AWS khi lỗi, header `x-amz-geo-pricing-bucket`.
- Log audit HTTP (`AuditLogMiddleware`) che giá trị các tham số `q`, `lat`, `lng` thành `***` trong trường `query`, cho mọi endpoint.
- Logger `httpx` in URL request ở mức INFO; adapter AWS gắn filter che `key=` thành `key=***`.
- Metric: số request theo endpoint, tỉ lệ lỗi theo mã, latency gọi AWS (p50/p95), số lần `429` của backend.
- Toạ độ trong log làm tròn tới 3 chữ số thập phân (~100 m).

---

# 11. Cấu hình (`backend/src/config.py` / `.env`)

| Biến | Mặc định | Mô tả |
| --- | --- | --- |
| `LOCATION_PROVIDER` | `fake` (test, dev) / `aws` (staging, prod) | Chọn adapter |
| `AWS_LOCATION_REGION` | `ap-southeast-1` | **Phải** là `ap-southeast-1` hoặc `ap-southeast-5` để có GrabMaps |
| `AWS_LOCATION_PLACES_API_KEY` | — | Server key (§8). Bắt buộc khi `LOCATION_PROVIDER=aws` |
| `LOCATION_TIMEOUT_SECONDS` | `3` | Timeout gọi AWS |
| `LOCATION_SUGGEST_RATE_PER_MINUTE` | `30` | §9 |
| `LOCATION_DETAIL_RATE_PER_MINUTE` | `20` | §9 |
| `LOCATION_REVERSE_RADIUS_METERS` | `500` | `QueryRadius` của reverse, tối đa 100 000 |

Frontend (`frontend/.env`): `VITE_AWS_LOCATION_REGION=ap-southeast-1`, `VITE_AWS_LOCATION_MAP_API_KEY=<map key>`.

`backend/.env.example` và `frontend/.env.example` phải liệt kê các biến trên, để trống giá trị key.

---

# 12. Test tối thiểu

| Lớp | Kiểm tra |
| --- | --- |
| Adapter AWS (mock `httpx`) | Body gửi đúng: `[lng, lat]`, `BiasPosition` loại trừ `BoundingBox`, `Language=vi`, không có `IntendedUse` ở Suggest/GetPlace, `Storage` ở reverse; bỏ item `Query`; loại kết quả ngoài VN; map `PlaceType` → `placeType`; `ThrottlingException`/timeout → `ProviderUnavailable`; `404`/`ValidationException` của GetPlace → `PlaceNotFound` |
| Chuẩn hoá tỉnh | Tên cũ → 34 tỉnh, có/không dấu, có tiền tố, tìm trong `Label` |
| Service + route (`FakePlacesProvider`) | Envelope `{data}`, `422` khi `q` < 2 ký tự hoặc chỉ có `lat`, `403` khi `uid` chưa đăng ký, người dùng đang onboarding vẫn gọi được, `429` khi vượt rate limit, `503` khi provider lỗi |
| Frontend (vitest) | Debounce 300 ms, huỷ request cũ, chọn gợi ý → gọi `API-LOC-002` → điền đúng các trường của `LocationIn` với `source=MAP_PICK`; lỗi `503` vẫn cho nhập tay |
| Kiểm thử thủ công với key thật | 20–30 địa chỉ thật: tên phường mới sau sáp nhập, địa chỉ có hẻm/ngõ, POI (đại lý VinFast), địa chỉ ở tỉnh miền núi |

---

# 13. Open Questions

| ID | Câu hỏi | Ảnh hưởng | Đề xuất tạm |
| --- | --- | --- | --- |
| Q-01 | GrabMaps (`ap-southeast-1`) không nhận `IntendedUse` ở `GetPlace`. Có được **lưu** toạ độ/địa chỉ từ `GetPlace` vào DB không, và tính giá nào? | Pháp lý / chi phí của `API-LOC-002` | Hỏi AWS Support trước khi lên production. MVP/demo: lưu `place_id` + toạ độ. Nếu không được lưu: sau khi chọn, gọi `ReverseGeocode(Storage)` tại toạ độ đó và lưu kết quả reverse |
| Q-02 | Server key (API key) hay IAM SigV4 cho backend? | Bảo mật, vận hành | API key (backend chạy ngoài AWS, ví dụ Railway). Chuyển sang IAM role nếu backend lên AWS |
| Q-03 | GrabMaps điền `SubDistrict` / `District` / `Locality` / `SubRegion` thế nào cho địa chỉ Việt Nam sau sáp nhập (bỏ cấp huyện)? | Map `ward`, `district` (§5.3) | Chạy 30 mẫu thật bằng `tools/workshop_crawl` (đã có client AWS), chốt bảng map |
| Q-04 | Có cần `SearchText` (danh sách đầy đủ khi bấm Enter) ngoài `Suggest` không? | Thêm `API-LOC-004` | Chưa cần cho MVP |
| Q-05 | Người dùng khách (chưa đăng nhập, kế hoạch chat cho khách sau MVP) có được tìm vị trí không? | Auth §1.1 | Chưa. Khi cần: rate limit theo IP + captcha |

---

# 14. Change Log

| Version | Date | Author | Changes |
| --- | --- | --- | --- |
| `v1.0` | `2026-10-10` | Backend Team | Bản đầu: 3 endpoint proxy Amazon Location (GrabMaps), port/adapter, chuẩn hoá 34 tỉnh, rate limit, chi phí và điều khoản lưu, hiển thị bản đồ bằng MapLibre |
| `v1.1` | `2026-10-10` | Backend Team | Đã code backend. Lỗi validation của `/api/v1/locations/*` trả envelope `422 INVALID_REQUEST` kèm `details.field`. Rate limit tự kiểm tra trong dependency (token bucket, burst = 1/3 giới hạn phút), trả `429` + `Retry-After`. Che `q`/`lat`/`lng` trong log audit và `key=` trong log httpx. `FakePlacesProvider` có 7 địa điểm mẫu (Hà Nội, TP.HCM, Đà Nẵng) |

---

# 15. References

- AWS: [GrabMaps for Southeast Asia](https://docs.aws.amazon.com/location/latest/developerguide/GrabMaps.html) · [Suggest](https://docs.aws.amazon.com/location/latest/APIReference/API_geoplaces_Suggest.html) · [GetPlace](https://docs.aws.amazon.com/location/latest/APIReference/API_geoplaces_GetPlace.html) · [ReverseGeocode](https://docs.aws.amazon.com/location/latest/APIReference/API_geoplaces_ReverseGeocode.html) · [Places intended use](https://docs.aws.amazon.com/location/latest/developerguide/places-intended-use.html) · [Pricing](https://aws.amazon.com/location/pricing) · [First app (MapLibre)](https://docs.aws.amazon.com/location/latest/developerguide/first-app.md)
- Repo: [error-handling.md](error-handling.md) · [user_location (ENT-002)](../../../backend/src/modules/vehicle_owner_onboarding/domain.py) · [booking/location.py](../../../backend/src/modules/booking/location.py) · [LocationAnchorPicker.tsx](../../../frontend/src/features/bookings/components/LocationAnchorPicker.tsx) · [tools/workshop_crawl](../../../tools/workshop_crawl/README.md)
