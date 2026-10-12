# API Technical Specification — Giá bảo dưỡng theo mốc, tách phần bảo hành

> Backend cho Feature `FEAT-P2-AD01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-01-phase2-spec.ff.md). **Entity:** [Entity Spec](ad-01-phase2-spec.entity.md).
>
> **Tái dùng, không viết lại (F5):** `CostEstimationService.estimate` (tính một xưởng, tách bảo hành, giá tham khảo khi thiếu) và `CostEstimationService.compare` / `GET /user-vehicles/{userVehicleId}/cost-estimate/compare` (us-045). AD-01 thêm: tự chọn xưởng bằng BK-01, ngày cập nhật giá, tổng bảo hành / chủ xe trả, nhãn "Thấp nhất". LLM không tính số (BR-AD01-03).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-AD01` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/cost_estimate/` (mở rộng `service.py`, `schemas.py`) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-AD01-01` | `GET` | `/user-vehicles/{userVehicleId}/cost-estimate/compare` (sửa) | So sánh 1–3 xưởng; `workshopIds` trở thành tuỳ chọn | UC-AD01-01, BR-AD01-01..04 |
| `API-AD01-02` | `GET` | `/user-vehicles/{userVehicleId}/cost-estimate` (sửa) | Một xưởng: thêm `priceUpdatedAt`, `stale`, tổng tách | AF-AD01-01 |
| `TOOL-AD01-01` | Agent tool | `compare_cost_estimates` | Agent gọi so sánh, gắn thẻ `ESTIMATE` (biến thể `COMPARE`) | UC-AD01-01 |

"Đặt ở xưởng này" (UC-AD01-02) = `runScheduler({ trigger: 'OWNER_REQUEST' | 'CHAT', overrides: { workshopId } })` của BK-01.

---

# 2. Authorization & Guards

Như us-045: chủ xe, xe thuộc chủ xe, `VERIFIED` + `ACTIVE`. Giá xưởng là dữ liệu công khai trong mạng lưới (FF §16).

---

# 3. API-AD01-01 — `compare` (sửa)

## 3.1 Query

| Field | Validation / ý nghĩa |
|---|---|
| `odoMilestone` | Như us-045; không có ⇒ mốc kế tiếp (F3) |
| `workshopIds` | **Tuỳ chọn** (trước là bắt buộc), 1–3 id. Không có ⇒ tự chọn §3.2 |
| `lat`, `lng` | Tuỳ chọn, cho tự chọn (chỉ khi `CONSENT_LOCATION`) |

## 3.2 Processing

1. **Chọn xưởng (BR-AD01-01):** `workshopIds` có ⇒ dùng đúng thứ tự gửi. Không có ⇒ `SchedulerService.rank_workshops(user, vehicle, location, limit = 3)` — hàm mới của BK-01 dùng lại bước lọc cứng (bán kính / khu vực / xưởng bị loại) + chấm điểm **không** cần khung giờ (bỏ yếu tố `USUAL_TIME`, không quét `open_slots`). Không ghi `scheduling_run`.
2. Chỉ 1 xưởng thoả ⇒ `mode = SINGLE` (AF-AD01-01); 0 ⇒ `mode = NONE` + gợi ý mở rộng khu vực.
3. `CostEstimationService.estimate(vehicle, milestone, workshop)` cho từng xưởng (song song bằng threadpool, đọc chung `maintenance_rule` một lần). Giữ nguyên toàn bộ quy tắc F5.
4. Bổ sung từng cột:
   - `priceUpdatedAt`, `stale` (entity §2).
   - `warrantyTotal`, `ownerTotal`, `itemsTotal`; mỗi dòng `warrantyStatus` (entity §3). Kiểm bất biến; lệch ⇒ log `estimate.invariant_broken` mức `ERROR` và trả `500` (không trả số sai).
   - `hasReferencePrice` (F5) khi có dòng dùng giá tham khảo (EF-AD01-01).
5. **Thứ tự cột = thứ hạng BK-01** (BR-AD01-04, EDGE-AD01-01), không sắp theo giá. `isLowest = true` cho cột có `ownerTotal` nhỏ nhất **duy nhất** (hoà thì không gắn nhãn).
6. Mục tiêu ≤ 3 s p90 (FF §18): 3 xưởng × (1 truy vấn giá + tính) + 1 truy vấn xếp hạng.

## 3.3 Response `200`

```json
{
  "data": {
    "mode": "COMPARE",
    "milestone": { "odoMilestoneKm": 24000, "label": "24.000 km / 24 tháng" },
    "columns": [
      { "rank": 1, "workshop": { "workshopId": "…", "name": "VinFast Cầu Giấy", "distanceKm": 2.1, "isPreferred": true },
        "itemsTotal": "1650000", "warrantyTotal": "200000", "ownerTotal": "1450000", "currency": "VND",
        "isLowest": false, "hasReferencePrice": false,
        "priceUpdatedAt": "2026-08-01T00:00:00Z", "stale": false, "staleDays": 72,
        "lines": [ { "itemCode": "BATTERY_CHECK", "itemName": "Kiểm tra pin cao áp", "amount": "200000", "warrantyStatus": "COVERED", "priceSource": "WORKSHOP" } ] }
    ],
    "label": "Chi phí ước tính",
    "priceStaleDays": 90
  }
}
```

---

# 4. API-AD01-02 — một xưởng (sửa)

Response us-045 thêm `priceUpdatedAt`, `stale`, `staleDays`, `warrantyTotal`, `ownerTotal`, `itemsTotal`, `lines[].warrantyStatus`. Không bỏ trường cũ.

---

# 5. TOOL-AD01-01 — `compare_cost_estimates`

| | |
|---|---|
| File | `backend/src/agents/tools/cost_tools.py` |
| Args (LLM thấy) | `odo_milestone?`, `workshop_names?` (≤ 3, khớp tên → id bằng tìm kiếm có sẵn) |
| Trả về LLM | `{ mode, columns: [{ rank, workshop_name, owner_total, warranty_total, stale, is_lowest }] }` — chỉ để diễn đạt, chuỗi số đã định dạng |
| Thẻ | `card = { type: "ESTIMATE", version: 2, variant: "COMPARE", data: <response §3.3> }` (CH-02); `actions`: mỗi cột một nút `CHIP` "Đặt ở {xưởng}" (intent `booking.pick_workshop`), thêm `LINK` "Xem chi tiết" → `/estimate/compare?…` |
| Prompt | "Không nêu con số nào ngoài số trong kết quả tool; luôn nói 'ước tính'. Không khuyên chọn xưởng chỉ vì rẻ." |

---

# 6. Error Cases

Giữ mã lỗi us-045. Thêm:

| HTTP | Code | Khi |
|---|---|---|
| 400 | `INVALID_REQUEST` | `workshopIds` > 3 hoặc trùng |
| 500 | `ESTIMATE_INVARIANT_BROKEN` | Bất biến tổng không thoả (không bao giờ trả số sai) |

---

# 7. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `warrantyTotal + ownerTotal = itemsTotal` với dữ liệu ngẫu nhiên (AC-AD01-03) | +1 property |
| Unit | `UNDETERMINED` tính vào chủ xe trả, có nhãn (EF-AD01-02) | +1 |
| Unit | `stale` đúng mốc 90 ngày (AC-AD01-02); không có giá ⇒ `priceUpdatedAt = null` | +2 |
| Unit | `isLowest` chỉ khi duy nhất; thứ tự cột theo thứ hạng, không theo giá | +2 |
| Service | Tổng từng xưởng khớp `estimate` một xưởng (AC-AD01-01, giữ AC-F5-01) | +1 |
| Service | Tự chọn xưởng theo BK-01 `rank_workshops`; 1 xưởng ⇒ `SINGLE` | +2 |
| Regression | Gọi kèm `workshopIds` như us-045 ⇒ kết quả cũ không đổi | bộ có sẵn |
| Service | Lưu bảng giá không đổi giá trị không làm mới `updated_at` | +1 |

---

# 8. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
