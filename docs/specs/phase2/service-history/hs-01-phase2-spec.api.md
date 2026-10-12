# API Technical Specification — Tra cứu lịch sử bảo dưỡng phía chủ xe

> Backend cho Feature `FEAT-P2-HS01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](hs-01-phase2-spec.ff.md). **Entity:** [Entity Spec](hs-01-phase2-spec.entity.md).
>
> **Tái dùng:** `GET /user-vehicles/{userVehicleId}/service-records` (API-VEH-005, `UserVehicleService.list_service_records`) — mở rộng, không viết endpoint song song; đồng bộ hãng `oem_integration` (pull + webhook, F3); `booking_line` + `booking_line_photo` (báo giá hai tầng); `VehicleOemSync.last_synced_at`. Dữ liệu đọc từ DB của EV Care, không gọi hãng khi xem (FF §18).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-HS01` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/user_vehicle/history.py` (mới: đọc, gộp, che), `modules/user_vehicle/share.py` (link), route trong `user_vehicle/route.py`; route công khai `modules/public_history/route.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-HS01-01` | `GET` | `/user-vehicles/{userVehicleId}/service-records` (sửa) | Dòng thời gian, đã gộp, lọc nhóm / năm, phân trang | UC-HS01-01, BR-HS01-01, 02 |
| `API-HS01-02` | `GET` | `/user-vehicles/{userVehicleId}/service-records/{recordId}` | Chi tiết một lần | UC-HS01-02 |
| `API-HS01-03` | `GET` | `/user-vehicles/{userVehicleId}/history-share-links` | Link đang hoạt động | SCR-HS01-03 |
| `API-HS01-04` | `POST` | `/user-vehicles/{userVehicleId}/history-share-links` | Tạo link | UC-HS01-04 |
| `API-HS01-05` | `POST` | `/user-vehicles/{userVehicleId}/history-share-links/{linkId}/revoke` | Thu hồi | UC-HS01-05 |
| `API-HS01-06` | `GET` | `/public/history/{token}` | Trang công khai chỉ đọc (không đăng nhập) | SCR-HS01-04 |
| `TOOL-HS01-01` | Agent tool | `search_service_history` | Agent tra lịch sử | UC-HS01-03, BR-HS01-04 |

---

# 2. Authorization & Guards

1. `API-HS01-01..05`: chủ xe, xe thuộc chủ xe (`get_owned_active_vehicle`). Xe `INACTIVE` vẫn xem được lịch sử (dependency đọc-only mới `get_owned_vehicle_readonly`), nhưng không tạo link.
2. `API-HS01-06`: không xác thực; token tra theo `token_hash`. Giới hạn 30 lần / phút / IP (Redis). Không có token / sai / hết hạn / thu hồi ⇒ **cùng** `404 SHARE_LINK_INACTIVE` (không phân biệt để không dò token, EF-HS01-02).
3. Chủ xưởng / KTV không gọi được (`403`), dùng TA-01.

---

# 3. API-HS01-01 — danh sách (sửa API-VEH-005)

## 3.1 Query (mới, đều tuỳ chọn)

| Field | Ý nghĩa |
|---|---|
| `category` | Lặp được; mã nhóm entity §4 |
| `year` | `YYYY` |
| `limit` | 1–50, mặc định 50 |
| `cursor` | Phân trang theo (`service_date`, `id`) |

Không truyền gì ⇒ 50 mục gần nhất (tương thích frontend MVP: thêm trường, không bỏ trường).

## 3.2 Processing

1. Lọc `merged_into_id IS NULL` + quy tắc chủ mới (BR-ENT-HS01-01).
2. `category` ⇒ `EXISTS` trong `vehicle_service_record_item` + `service_item_category`.
3. Hai truy vấn phụ theo lô (xưởng, booking) như hiện có; một truy vấn đếm hạng mục / tổng tiền theo `record_id`.
4. Mục tiêu ≤ 500 ms p90 cho 50 mục (AC-HS01-03): dùng index `ix_vsr_vehicle_date`.

## 3.3 Response `200` (thêm trường vào `ServiceRecordOut`)

```json
{
  "data": {
    "items": [
      { "recordId": "…", "source": "OEM", "sources": ["OEM", "EV_CARE"], "serviceDate": "2025-10-15", "odoKm": 18020,
        "isPeriodic": false, "itemsDone": "Thay má phanh trước", "workshop": { "workshopId": "…", "name": "VinFast Cầu Giấy" },
        "bookingId": "…", "bookingCode": "EVC-…", "actualCost": "1480000",
        "categories": ["BRAKE"], "itemSummary": "Thay má phanh trước · Kiểm tra dầu phanh",
        "cost": { "amount": "1480000", "kind": "APPROVED_QUOTE" },
        "hasPhotos": true, "deferredCount": 1 }
    ],
    "nextCursor": null,
    "facets": { "years": [2026, 2025], "categories": [ { "code": "BRAKE", "label": "Phanh", "count": 2 } ] },
    "oemSync": { "lastSyncedAt": "2026-10-11T22:00:00Z", "status": "OK" }
  }
}
```

- `sources`: có hai phần tử khi đã gộp (nhãn "Từ dữ liệu hãng · EV Care").
- `cost.kind`: `ACTUAL` / `APPROVED_QUOTE` / `ESTIMATE` / `null` (thiếu chi phí, AF-HS01-02).
- `oemSync` cho EF-HS01-01. Danh sách rỗng ⇒ `items = []` (EF-HS01-03).

---

# 4. API-HS01-02 — chi tiết

```json
{
  "data": {
    "record": { "…": "như §3.3" },
    "lines": [ { "itemName": "Má phanh trước", "kind": "PART", "partNumber": "VF-BRK-0021", "quantity": 1, "amount": "980000", "amountKind": "APPROVED_QUOTE", "isCoveredByWarranty": false, "category": "BRAKE" } ],
    "photos": [ { "photoId": "…", "url": "https://…signed…", "caption": "Má phanh mòn 2 mm" } ],
    "approvedQuote": { "quoteId": "…", "total": "1480000", "approvedAt": "…" },
    "deferred": [ { "itemName": "Thay dầu phanh", "reason": "DECLINED", "proposedAt": "…", "amount": "450000", "safety": false } ],
    "odoNote": "Số km theo hãng là 18.020; EV Care ghi 18.050.",
    "canBookFollowUp": true
  }
}
```

- `photos`: URL ký có hạn 10 phút (storage có sẵn của `booking_line`); chỉ bản ghi `EV_CARE` của chủ hiện tại.
- `deferred` (khuyến nghị chưa làm): `booking_line` cùng booking có trạng thái bị chủ xe từ chối / hoãn, cộng báo giá phát sinh AD-04 bị từ chối (EDGE-HS01-03). `safety` theo cờ hạng mục an toàn có sẵn.
- `canBookFollowUp`: có `deferred` và xe không có lịch mở ⇒ "Đặt lịch làm tiếp" mở BK-01 với hạng mục = `deferred` (frontend truyền `itemCodes`).
- `odoNote` khi `odo_mismatch_km ≠ 0` (EDGE-HS01-01).

---

# 5. Link chia sẻ

## 5.1 API-HS01-04 — tạo

Body: `{ "days": 7 }` (1–30, mặc định `SHARE_LINK_DAYS`). Đã có 3 link `active` chưa hết hạn ⇒ `409 SHARE_LINK_LIMIT` (BR-HS01-08). Response `201`:

```json
{ "data": { "linkId": "…", "url": "https://app.evcare.vn/h/Xk2…", "expiresAt": "…", "tokenHint": "…a9Qz" } }
```

`url` chỉ trả **một lần**; danh sách sau chỉ có `tokenHint`.

## 5.2 API-HS01-03 / 05

- Danh sách: `[ { linkId, tokenHint, status: ACTIVE|EXPIRED|REVOKED, expiresAt, viewCount, lastViewedAt, createdAt } ]` (30 ngày gần nhất).
- Thu hồi: `status = revoked`, `revoked_at = now`; idempotent. Lần truy cập kế tiếp ⇒ `404` (AC-HS01-04): API-HS01-06 không đệm kết quả.

## 5.3 API-HS01-06 — `GET /public/history/{token}`

1. Tra `token_hash`; `active` và `now < expires_at` ⇒ tiếp, ngược lại `404 SHARE_LINK_INACTIVE`.
2. `view_count + 1`, `last_viewed_at`.
3. Payload **đã che** (BR-HS01-05, AC-HS01-02) — dựng bằng DTO riêng `PublicHistoryOut` (không tái dùng DTO chủ xe để tránh lộ trường mới thêm sau này):

```json
{ "data": { "vehicle": { "modelName": "VF 8", "trim": "Plus", "year": 2024, "licensePlateMasked": "30A-***.45", "vinMasked": "RLL******1234" },
            "records": [ { "serviceDate": "…", "odoKm": 18020, "workshopName": "…", "itemSummary": "…", "categories": ["BRAKE"], "sources": ["OEM"] } ],
            "expiresAt": "…", "generatedAt": "…" } }
```

   Không có: VIN đầy đủ, SĐT, email, tên chủ xe, `userVehicleId`, `bookingId`, mã lịch, ảnh, chi phí, báo giá, ghi chú.
4. Header: `X-Robots-Tag: noindex, nofollow`, `Cache-Control: no-store`, `Referrer-Policy: no-referrer` (BR-HS01-07).

---

# 6. TOOL-HS01-01 — `search_service_history`

| | |
|---|---|
| File | `backend/src/agents/tools/maintenance_tools.py` |
| Args (LLM thấy) | `category?` (enum entity §4), `year?`, `keyword?` (khớp `item_name` không dấu), `limit?` (≤ 5) |
| Danh tính | `user_id`, `user_vehicle_id` từ `RunnableConfig` |
| Xử lý | Gọi cùng hàm đọc §3 (cùng quy tắc chủ mới, gộp), sắp mới nhất trước |
| Trả về LLM | `[{ record_id, service_date, odo_km, workshop_name, item_summary, cost_kind }]` hoặc `{ "found": false }` |
| Gắn thẻ | `card = { type: "SERVICE_HISTORY_ITEM", userVehicleId, recordId }` cho mục đầu (CH-02); thẻ đọc lại API-HS01-02 |
| Prompt | "Chỉ trả lời từ kết quả tool. `found = false` thì nói không có trong lịch sử, không đoán (EF-HS01-04)." |

---

# 7. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | `category` / `year` / `days` sai | HS01-01, 04 |
| 404 | `VEHICLE_NOT_FOUND` / `RECORD_NOT_FOUND` / `SHARE_LINK_NOT_FOUND` | Không thuộc chủ xe | HS01-01..05 |
| 404 | `SHARE_LINK_INACTIVE` | Token sai / hết hạn / thu hồi | HS01-06 |
| 409 | `SHARE_LINK_LIMIT` | Đã có 3 link | HS01-04 |
| 409 | `VEHICLE_NOT_ACTIVE` | Tạo link cho xe không hoạt động | HS01-04 |
| 429 | `RATE_LIMITED` | Trang công khai bị gọi dồn | HS01-06 |

---

# 8. Observability

Log `history.listed` (`count`, `filters`, `ms`), `history.share_created`, `history.share_revoked`, `history.public_viewed` (`link_id`, không IP), `history.merge` (`oem_id`, `ev_care_id`, `odo_mismatch_km`).

---

# 9. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `dedupe_key`; gộp ưu tiên hãng, giữ chi phí EV Care (AC-HS01-01) | +3 |
| Unit | Phân nhóm theo `item_code` và từ khoá; không khớp ⇒ `OTHER` | +3 |
| Service | Lọc nhóm + năm; facets đúng | +2 |
| Service | Chủ mới không thấy ảnh / báo giá / bản `EV_CARE` của chủ cũ (BR-HS01-06) | +2 |
| Service | Lịch huỷ không có trong lịch sử; phát sinh bị từ chối là `deferred` | +2 |
| API | Payload công khai không chứa VIN đầy đủ, SĐT, email (quét chuỗi + so khoá, AC-HS01-02) | +1 |
| API | Thu hồi ⇒ lần sau `404` (AC-HS01-04); hết hạn ⇒ `404`; token sai ⇒ cùng `404` | +3 |
| API | Link thứ 4 ⇒ `409` | +1 |
| Perf | 50 mục ≤ 500 ms (AC-HS01-03) với dữ liệu mẫu 200 bản ghi | +1 |
| Agent | Không có mục ⇒ không đoán; có ⇒ thẻ `SERVICE_HISTORY_ITEM` | +2 |

---

# 10. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
