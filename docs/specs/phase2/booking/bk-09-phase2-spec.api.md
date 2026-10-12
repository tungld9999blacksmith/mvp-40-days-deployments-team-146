# API Technical Specification — Chọn xưởng theo phụ tùng sẵn có

> Backend cho Feature `FEAT-P2-BK09`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-09-phase2-spec.ff.md). **Entity:** [Entity Spec](bk-09-phase2-spec.entity.md).
>
> **Tái dùng:** `SchedulerService.run` (BK-01: yếu tố mềm + lọc cứng), `BookingStateMachine` (giữ phụ tùng cùng transaction khi xưởng nhận lịch), `API-BK01-09` (hết phụ tùng sau khi nhận), BK-05 thẻ bản đồ, AD-02 tư vấn sửa chữa, WS-01 luật `R-PARTS`, nhập CSV cùng kiểu bảng giá sửa chữa (AD-02).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-BK09` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/parts/` (mới: `availability.py` — `PartsAvailabilityService`, `stock.py`, `route.py`) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `SVC-BK09-01` | Internal | `PartsAvailabilityService.status(workshop_ids, vehicle, item_codes)` | Trạng thái theo xưởng | UC-BK09-02, BR-BK09-01, 02 |
| `API-BK09-01` | `GET` | `/workshop-owner/part-stock?q` | Tồn kho (SCR-BK09-01) | UC-BK09-01 |
| `API-BK09-02` | `PUT` | `/workshop-owner/part-stock/{partNumber}` | Sửa một dòng | UC-BK09-01 |
| `API-BK09-03` | `POST` | `/workshop-owner/part-stock/import` | Tải CSV (chạy thử / áp dụng) | Q-BK09-01 |
| `API-BK09-04` | `GET` | `/parts?q&modelId` | Tìm danh mục phụ tùng | — |
| `API-BK09-05` | `POST` | `/scheduling/runs` (sửa BK-01) | `requirePartsInStock`, `preorderParts` | BR-BK09-03, 04 |
| `HOOK-BK09-01` | Internal | Chuyển trạng thái booking ⇒ giữ / dùng / trả phụ tùng | | UC-BK09-04, BR-BK09-05, 06 |
| `API-BK09-06` | `POST` | `/workshop-owner/bookings/{bookingId}/parts-unavailable` | Hết phụ tùng sau khi nhận ⇒ BK-01 AF-08 | EF-BK09-02 |

---

# 2. Authorization & Guards

Chủ xưởng sửa tồn kho xưởng mình (KTV không). Chủ xe chỉ nhận trạng thái, không số lượng (FF §16). Khoá DB: giữ phụ tùng dùng `SELECT … FOR UPDATE` trên các dòng `workshop_part_stock` liên quan.

---

# 3. SVC-BK09-01 — trạng thái

`status(workshop_ids, vehicle, item_codes) → { workshopId: { status, arrivalDate?, updatedAt, parts: [{ partNumber, name, status }] } }` theo entity §3.1. Một truy vấn tồn + một truy vấn giữ cho tất cả xưởng. `item_codes` = hạng mục mốc (F3) + hạng mục sửa chữa (AD-02 `reported_symptom_items` / `itemCodes`). Không xác định được hạng mục ⇒ `NOT_REQUIRED` + `note: "Xưởng sẽ kiểm tra"` (EF-BK09-03).

---

# 4. Tích hợp BK-01 (API-BK09-05)

Request `POST /scheduling/runs` thêm:

| Field | Ý nghĩa |
|---|---|
| `requirePartsInStock` | `true` ⇒ lọc cứng chỉ xưởng `IN_STOCK` (AC-BK09-03); `rejected_by.PARTS` đếm loại |
| `preorderParts` | `true` ⇒ chấp nhận xưởng `ARRIVING`, cửa sổ tìm khung bắt đầu từ **ngày sau** `arrivalDate` của xưởng đó (BR-BK09-04) |

Mặc định (mềm, BR-BK09-03): yếu tố `PARTS` thêm vào chấm điểm: `IN_STOCK = 1`, `ARRIVING` trước ngày hẹn = 0,5, `UNKNOWN = 0,3`, `NOT_REQUIRED` không tính; trọng số `SCHEDULER_WEIGHTS.PARTS = 15`; lý do `PARTS_IN_STOCK` "Có sẵn phụ tùng". Phương án mang `parts: { status, arrivalDate }`.

**AF-BK09-01:** `requirePartsInStock = true` mà không có phương án ⇒ `NO_OPTION` với `relaxationOffers` thêm `PREORDER_PARTS` ("Đặt trước phụ tùng ở {xưởng}, sớm nhất {ngày}") và `ALLOW_NOT_IN_STOCK`.

Booking tạo từ phương án ghi `require_parts_in_stock`, `parts_preordered`.

---

# 5. HOOK-BK09-01 — giữ / dùng / trả

| Chuyển trạng thái | Việc (cùng transaction, FF §18) |
|---|---|
| ⇒ `confirmed` (xưởng nhận: tự nhận WS-01 hoặc duyệt tay) | Với mỗi phụ tùng cần: khoá dòng tồn, khả dụng ≥ cần ⇒ chèn `part_reservation (reserved)`; thiếu ⇒ không giữ dòng đó, `booking.parts_shortage = true`, thông báo xưởng (EDGE-BK09-01: lịch nhận trước được giữ; lịch sau thiếu) |
| ⇒ `cancelled` / đổi sang xưởng khác (BK-01 `replace_booking`) | `reserved ⇒ released` ngay (BR-BK09-06, AC-BK09-02) |
| ⇒ `completed` | `reserved ⇒ consumed`, trừ `quantity_on_hand` |
| Đổi giờ cùng xưởng | Giữ nguyên |

Giữ phụ tùng không bao giờ làm thất bại việc xác nhận lịch (thiếu ⇒ cờ + thông báo).

---

# 6. Tồn kho — API-BK09-01..03

- `GET` ⇒ `[{ partNumber, name, quantityOnHand, reserved, available, expectedArrivalDate, expectedQuantity, updatedAt, stale }]`.
- `PUT { quantityOnHand, expectedArrivalDate?, expectedQuantity? }` ⇒ cập nhật `updated_at` (kể cả giá trị không đổi — xác nhận "vẫn đúng" để tránh `stale`; khác bảng giá). Giảm dưới số đang giữ ⇒ `200` + `warnings: ["BELOW_RESERVED"]` + danh sách lịch bị ảnh hưởng.
- `POST import` CSV `part_number,quantity_on_hand,expected_arrival_date,expected_quantity` ≤ 1 MB, `dryRun` như AD-02; mã không có trong danh mục ⇒ lỗi dòng.

---

# 7. API-BK09-06 — hết phụ tùng sau khi nhận

`{ "partNumbers": ["…"], "note": "…" }` ⇒ gọi `API-BK01-09` với `reason = PARTS` (EF-BK09-02); giữ phụ tùng của lịch ⇒ `released`.

---

# 8. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 400 | `INVALID_REQUEST` | Số âm, ngày về trong quá khứ |
| 404 | `PART_NOT_FOUND` | Mã không có trong danh mục |
| 413 | `FILE_TOO_LARGE` | |

---

# 9. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Trạng thái: đủ / thiếu có ngày về / quá hạn ⇒ `UNKNOWN` (AC-BK09-01) / mã tương đương | +5 |
| Service | "Chỉ xưởng có sẵn" ⇒ không phương án nào ở xưởng khác (AC-BK09-03) | +1 |
| Service | Đặt trước ⇒ khung sau ngày hàng về | +1 |
| Concurrency | Hai lịch giữ phụ tùng cuối ⇒ lịch nhận trước được giữ, lịch sau `parts_shortage` (EDGE-BK09-01) | +1 |
| Service | Huỷ ⇒ trả ngay (AC-BK09-02); hoàn tất ⇒ trừ tồn | +2 |
| API | Chủ xe không nhận số lượng | +1 |

---

# 10. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
