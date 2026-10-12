# API Technical Specification — Sức chứa theo thời lượng và hạn phản hồi

> Backend cho Feature `FEAT-P2-WS02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ws-02-phase2-spec.ff.md). **Entity:** [Entity Spec](ws-02-phase2-spec.entity.md).
>
> **Rủi ro cao:** đổi lõi sức chứa của `BookingService`. AC-F6-01 (20 yêu cầu cùng chỗ cuối ⇒ 1 thành công) phải nằm trong bộ hồi quy cho **cả hai** mô hình. Xưởng chưa bật `duration_model_enabled` phải cho kết quả giống hệt MVP (AC-WS02-04).
>
> **Tái dùng:** `BookingService._capacity` / `open_slots` / `_create_booking_locked` (thay phần đếm), `available_from` (công thức BR-005), `cancel_unconfirmed` (job hạn duyệt), `SchedulerService.run` (BK-01), `workshop_board` route + dependency chủ xưởng, `booking_reminder`.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-WS02` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/booking/capacity.py` (mới, `CapacityService`), `backend/src/modules/workshop_board/` (route bổ sung) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `SVC-WS02-01` | Internal | `CapacityService.fits(...)` / `occupancy(...)` | Kiểm tra sức chứa theo khoảng; nơi duy nhất | UC-WS02-02, BR-WS02-01..03, 07, 08 |
| `API-WS02-01` | `GET` | `/workshop-owner/service-durations` | Bảng thời lượng: mặc định, của xưởng, trung vị thực tế, đề xuất | UC-WS02-01, SCR-WS02-01 |
| `API-WS02-02` | `PUT` | `/workshop-owner/service-durations/{itemCode}` | Chỉnh thời lượng của xưởng | UC-WS02-01 |
| `API-WS02-03` | `POST` | `/workshop-owner/service-durations/{itemCode}/apply-suggestion` | "Dùng số thực tế" | UC-WS02-05 |
| `API-WS02-04` | `GET` | `/workshop-owner/capacity` (sửa) | Sức chứa theo đơn vị `SLOT_UNIT_MIN` + khoảng lịch | SCR-WS02-02 |
| `API-WS02-05` | `PUT` | `/workshop-owner/slot-blocks` (sửa) | Khoá chỗ theo khoảng (`endTime`) | BR-WS02-07 |
| `API-WS02-06` | `GET` / `PUT` | `/workshop-owner/booking-settings` (sửa) | Bật mô hình thời lượng; chỗ dự phòng + đề xuất | BR-WS02-08, SCR-WS02-03 |
| `API-WS02-07` | `GET` | `/workshops/{workshopId}/availability` (sửa) | Thêm `itemCodes` / `durationMin` để chủ xe thấy đúng khung | UC-WS02-02 |
| `JOB-WS02-01` | Celery | `capacity.ws_confirm_deadline` (thay `cancel_unconfirmed`) | Nhắc ở `WS_CONFIRM_REMIND_PCT`; hết hạn ⇒ giữ phương án rồi huỷ | UC-WS02-03, UC-WS02-04 |
| `JOB-WS02-02` | Celery | `capacity.duration_suggestions` (tuần) | Đề xuất chỉnh thời lượng | UC-WS02-05, BR-WS02-06 |
| `HOOK-WS02-01` | Internal | Tiến độ `ready_for_pickup` ⇒ ghi `booking_duration_sample` | | BR-WS02-06 |

---

# 2. Authorization & Guards

1. `API-WS02-01..06`: chủ xưởng đăng nhập (dependency `workshop_board`), chỉ xưởng của mình. KTV (WS-03) không chỉnh được thời lượng hay dự phòng (`403 FORBIDDEN`).
2. `API-WS02-07`: như endpoint us-029 hiện có (chủ xe).
3. `itemCode` không có trong danh mục (`service_item_duration` mặc định hoặc `maintenance_rule.item_code`) ⇒ `404 ITEM_NOT_FOUND`.

---

# 3. SVC-WS02-01 — `CapacityService`

```python
class CapacityService:
    def duration_for(self, workshop: Workshop, item_codes: Sequence[str] | None) -> Duration: ...
    def fits(self, workshop: Workshop, d: date, start: time, duration_min: int,
             *, exclude_booking_id: UUID | None = None) -> FitResult: ...
    def occupancy(self, workshop: Workshop, start: date, end: date) -> dict[date, list[UnitOut]]: ...
```

## 3.1 `duration_for`

- `workshop.duration_model_enabled = false` ⇒ `Duration(min = slot_minutes, source = MVP_SLOT)`.
- Không có `item_codes` ⇒ `LEGACY_BOOKING_MIN`, `source = LEGACY` (BR-WS02-03).
- Có ⇒ Σ thời lượng (xưởng → mặc định → `LEGACY_BOOKING_MIN` + log `capacity.duration_missing`), làm tròn lên `SLOT_UNIT_MIN` (BR-WS02-01), `source = ITEMS`.

Nguồn `item_codes` khi giữ chỗ: hạng mục của mốc (`maintenance_rule` theo `odo_milestone`) cộng gói đã chọn (`maintenance_package_code`, `selected_item_codes` có sẵn trong `create_for_slot`).

## 3.2 `fits` (BR-ENT-WS02-02)

1. Xưởng chưa bật ⇒ gọi đúng `_capacity` MVP (đếm `time_slot`), trả kết quả không đổi (AC-WS02-04).
2. Đã bật:
   - `start` phải là bội của `SLOT_UNIT_MIN` tính từ giờ mở cửa; `start + duration ≤ close_time` ⇒ không thì `FitResult(ok = False, reason = OUT_OF_HOURS)` (AF-WS02-02).
   - Một truy vấn: lịch chiếm chỗ chồng lên `[starts_at, ends_at)` (index `ix_booking_workshop_interval`), trừ `exclude_booking_id`; một truy vấn khoá chỗ (`time_slot`, `end_time`) chồng khoảng.
   - Quét các đơn vị trong khoảng bằng mảng đếm (sweep line), `available(u)` theo `available_from(total_technicians, emergency_slots_reserved, blocked(u), occupied(u))`.
   - `ok = min(available(u)) ≥ 1`; trả `remaining = min(available(u))`, `bottleneckAt`.
3. Mục tiêu ≤ 100 ms p90 (FF §18): 2 truy vấn, không phụ thuộc số đơn vị.

## 3.3 Nguyên tử (NFR-01, AC-WS02-02)

- Xưởng chưa bật: giữ khoá MVP (`booking:vehicle:{id}` + `booking:slot:{workshop}:{date}:{time}`).
- Đã bật: thay khoá khung bằng **khoá ngày của xưởng** `booking:capacity:{workshopId}:{date}` (cùng `ttl` / `wait_timeout` như hiện tại). Mọi thao tác giữ / đổi / gộp việc của xưởng đó trong ngày đó tuần tự hoá; `fits` được gọi lại **bên trong khoá** ngay trước khi chèn. Không lấy nhiều khoá đơn vị (tránh deadlock).
- `_create_booking_locked`, `_reschedule_locked` (us-053) và `replace_booking` (BK-01) gọi `CapacityService.fits` thay `_capacity`, và ghi `duration_min`, `duration_source`, `starts_at`, `ends_at`.
- `open_slots` (quét theo lô cho BK-01 / us-061) nhận thêm `duration_min` và dùng cùng sweep line trên dữ liệu đã tải cho cả cửa sổ (vẫn 3 truy vấn mỗi xưởng).

---

# 4. API-WS02-01..03 — Thời lượng hạng mục

## 4.1 `GET /workshop-owner/service-durations`

```json
{
  "data": {
    "slotUnitMin": 30,
    "durationModelEnabled": true,
    "items": [
      { "itemCode": "BRAKE_FLUID_REPLACE", "itemName": "Thay dầu phanh", "defaultMin": 45, "workshopMin": 60,
        "effectiveMin": 60, "actualMedianMin": 40, "sampleCount": 14,
        "suggestion": { "id": "s1…", "suggestedMin": 40 } }
    ]
  }
}
```

`actualMedianMin` = trung vị 30 ngày của mẫu không `excluded` (entity §6); `null` khi < 10 mẫu.

## 4.2 `PUT …/service-durations/{itemCode}`

`{ "durationMin": 50 }` — `5..600`, bội của 5 ⇒ không thì `400 INVALID_REQUEST`. `{ "durationMin": null }` ⇒ xoá dòng của xưởng (quay về mặc định). Không ảnh hưởng lịch đã giữ. Đề xuất `open` cùng hạng mục ⇒ `superseded`.

## 4.3 `POST …/{itemCode}/apply-suggestion`

Đề xuất `open` ⇒ upsert dòng xưởng `duration_min = median_min`, `source = ACTUAL_MEDIAN`; đề xuất `applied`. Không có ⇒ `404 SUGGESTION_NOT_FOUND`.

---

# 5. API-WS02-04 — `GET /workshop-owner/capacity` (sửa)

Giữ shape MVP khi xưởng chưa bật. Khi bật, mỗi ngày trả theo đơn vị:

```json
{ "date": "2026-10-10", "unitMin": 30,
  "units": [ { "start": "08:00", "total": 4, "reserved": 1, "blocked": 0, "occupied": 2, "remaining": 1 } ],
  "bookings": [ { "bookingId": "…", "bookingCode": "EVC-…", "start": "08:00", "end": "10:30", "durationMin": 150, "status": "CONFIRMED", "proactive": false } ] }
```

`bookings` cho phép frontend vẽ lịch dài trải nhiều ô (SCR-WS02-02).

---

# 6. API-WS02-05 — `PUT /workshop-owner/slot-blocks` (sửa)

Thêm `endTime` (tuỳ chọn) vào mỗi khoá. `endTime` phải > `timeSlot`, ≤ giờ đóng cửa. Xưởng chưa bật mà gửi `endTime` ⇒ tách thành nhiều khoá một khung (giữ hành vi MVP).

**EF-WS02-03:** khoá chỗ hoặc giảm `total_technicians` làm `available(u) < 0` ở đơn vị đã có lịch ⇒ **vẫn lưu**, trả `200` với `warnings: [{ "code": "OVERBOOKED_UNITS", "units": [...], "bookingIds": [...] }]`; không huỷ tự động. Frontend gợi ý dùng "Không phục vụ được" (BK-01 `API-BK01-09`) cho lịch bị ảnh hưởng.

---

# 7. API-WS02-06 — `booking-settings` (sửa)

## 7.1 `GET`

```json
{ "data": { "confirmationMode": "MANUAL", "durationModelEnabled": true, "emergencySlotsReserved": 1,
            "reserveSuggestion": { "suggested": 1, "walkInRatePct": 18.5, "basisDays": 30, "sampleUnits": 412 } } }
```

`reserveSuggestion` (BR-WS02-05): tỉ lệ vãng lai = khoá chỗ `reason = walk_in` / tổng đơn vị có xe trong 30 ngày; `suggested = round(total_technicians × walkInRate)`, kẹp `[0, total_technicians − 1]`. < 100 đơn vị dữ liệu ⇒ `reserveSuggestion = null`.

## 7.2 `PUT`

Thêm `durationModelEnabled`, `emergencySlotsReserved` (`0 ≤ x < total_technicians`). Bật / tắt theo BR-ENT-WS02-04. Ghi log `capacity.model_toggled`.

---

# 8. API-WS02-07 — `GET /workshops/{workshopId}/availability` (sửa)

Thêm query `itemCodes` (lặp) **hoặc** `userVehicleId` + `odoMilestone` để backend tự lấy hạng mục. Response thêm `durationMin`, và mỗi khung `available` theo `fits(duration)` (khung không đủ chỗ cho cả khoảng ⇒ `available = false`, `reason = "INSUFFICIENT_DURATION"`). Không truyền ⇒ dùng `LEGACY_BOOKING_MIN` cho xưởng đã bật.

---

# 9. JOB-WS02-01 — `capacity.ws_confirm_deadline`

Thay `BookingService.cancel_unconfirmed` (job hiện có, cùng lịch chạy).

| Bước | Điều kiện | Việc |
|---|---|---|
| Bỏ qua | `proactive = true` (BK-01 HOOK-BK01-01) | — |
| Mốc | `base = coalesce(proactive_confirmed_at, created_at)`; `deadline = min(base + BOOKING_WS_CONFIRM_DEADLINE_HOURS, starts_at)` | |
| Nhắc | `now ≥ base + WS_CONFIRM_REMIND_PCT × (deadline − base)` và chưa có `booking_reminder` loại `WS_CONFIRM_REMIND` | Thông báo chủ xưởng (Workshop Portal + kênh đã cấu hình): "Lịch {mã} còn {phút} phút để duyệt" |
| Hết hạn | `now ≥ deadline` | (1) `SchedulerService.run(trigger = WS_CONFIRM_TIMEOUT, user = chủ xe, excludeSlots = [lịch này], applyAutomation = true, force_hold = true)` — luôn giữ phương án đầu, kể cả chủ xe ở mức `SUGGEST`, vì chủ xe sắp mất lịch. (2) Một transaction: lịch cũ `cancelled`, `reason_code = WS_CONFIRM_TIMEOUT`, `actor = system`; lịch mới `replaced_booking_id = old.id`, `proactive = true`. (3) Thông báo chủ xe SCR-WS02-04 |
| Không có phương án | EF-WS02-01 | Huỷ lịch cũ; thông báo kèm lý do + `relaxationOffers` (link mở BK-01 SCR-BK01-03) |
| Lỗi bộ lập lịch | | Vẫn huỷ theo MVP (không giữ lịch quá hạn chót); thông báo "Xưởng chưa kịp xác nhận" + nút "Tìm lịch khác"; log `capacity.timeout_without_replacement` |

Thứ tự "giữ mới rồi mới huỷ cũ" (BR-WS02-04): phương án mới không được trùng khung lịch cũ, nên giữ trước rồi huỷ trong cùng transaction là an toàn với BR-013 nhờ `replace_booking` (BK-01 §5.2 bước 3). BK-02 không tính điểm chủ xe; tính vào chỉ số tin cậy của xưởng.

---

# 10. JOB-WS02-02 — `capacity.duration_suggestions`

Thứ Hai 02:00. Với mỗi xưởng đã bật, mỗi `item_code` có ≥ 10 mẫu 30 ngày: tính trung vị (phân bổ theo entity §6), `|median − effective| / effective > 20 %` ⇒ tạo / thay đề xuất `open`. Thông báo chủ xưởng một lần mỗi tuần nếu có đề xuất mới.

## HOOK-WS02-01

`ServiceProgressService` khi ghi `ready_for_pickup`: tính `actual_min` (entity §6), upsert `booking_duration_sample`. Lỗi không chặn ghi tiến độ (log `capacity.sample_failed`).

---

# 11. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | Thời lượng sai bội, `endTime ≤ timeSlot`, `emergencySlotsReserved ≥ total_technicians` | WS02-02, 05, 06 |
| 403 | `FORBIDDEN` | KTV / chủ xe gọi API của chủ xưởng | WS02-01..06 |
| 404 | `ITEM_NOT_FOUND` / `SUGGESTION_NOT_FOUND` | | WS02-02, 03 |
| 409 | `SLOT_FULL` | Giữ chỗ: không đủ thợ trong toàn khoảng (mã có sẵn của booking) | luồng giữ chỗ |
| 422 | `SLOT_OUT_OF_HOURS` | Lịch kết thúc sau giờ đóng cửa (mã có sẵn) | luồng giữ chỗ |

---

# 12. Observability

- Log `capacity.fits` mức DEBUG (`workshop_id`, `duration_min`, `remaining`, `ms`); `capacity.duration_missing` (`item_code`); `capacity.ws_confirm_reminded`; `capacity.ws_confirm_timeout` (`booking_id`, `replacement_held`).
- Metric: `capacity_fits_duration_seconds` (p90 ≤ 100 ms), `ws_confirm_timeout_total{replacement}` (AC-WS02-03), `booking_overbooked_units` (gauge, phải = 0 ngoài EF-WS02-03).

---

# 13. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `duration_for`: tổng + làm tròn 30; thiếu hạng mục ⇒ 60; xưởng chưa bật ⇒ `slot_minutes` | +4 |
| Unit | Sweep line: ví dụ Main Flow (4 thợ, A 150', B 30') ⇒ 08:00 còn 2, 08:30 còn 3 | +1 |
| Unit | Nửa mở: kết thúc 10:30 / bắt đầu 10:30 không chồng | +1 |
| Unit | Vượt giờ đóng cửa ⇒ `OUT_OF_HOURS` | +1 |
| Property | Sinh ngẫu nhiên lịch + khoá: không đơn vị nào `occupied > total − reserved − blocked` (AC-WS02-01) | +1 |
| Concurrency | 20 yêu cầu song song vào khoảng còn 1 thợ ⇒ đúng 1 thành công, cả hai mô hình (AC-WS02-02, EDGE-WS02-01) | +2 |
| Regression | Xưởng chưa bật: toàn bộ test sức chứa us-029 / us-037 / us-061 không đổi (AC-WS02-04) | bộ có sẵn |
| Service | Đổi lịch cùng khung không tự tính chính nó (EDGE-WS02-03) | +1 |
| Job | Nhắc ở 50 % hạn; hết hạn ⇒ phương án giữ trước, lịch cũ huỷ sau, cùng transaction (AC-WS02-03) | +3 |
| Job | Hết hạn không có phương án ⇒ huỷ + lý do | +1 |
| Job | Đề xuất chỉ khi ≥ 10 mẫu và lệch > 20 % | +2 |
| API | `PUT slot-blocks` gây quá tải ⇒ `200` + `OVERBOOKED_UNITS`, không huỷ lịch | +1 |

---

# 14. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
