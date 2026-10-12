# API Technical Specification — Gộp việc vào một lần đến xưởng

> Backend cho Feature `FEAT-P2-HS02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](hs-02-phase2-spec.ff.md). **Entity:** [Entity Spec](hs-02-phase2-spec.entity.md).
>
> **Tái dùng:** `get_maintenance_status` + lịch mốc (F3), khuyến nghị chưa làm (HS-01: dòng `EXTRA` `DECLINED`), `CostEstimationService` / `repair_price` (giá ước tính), `CapacityService.duration_for` / `fits` (WS-02), `SchedulerService.run` (BK-01) khi khung không đủ dài, `booking_proposal` + `API-QB-02` (us-061), luồng `POST /bookings` (wizard), `service_price` cho kiểm tra xưởng có làm hạng mục không.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-HS02` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/booking/merge.py` (mới), `modules/oem_integration` (đồng bộ chiến dịch) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `SVC-HS02-01` | Internal | `MergeAdvisor.suggest(vehicle, workshop, slot)` | Tìm việc có thể gộp | UC-HS02-01 |
| `API-HS02-01` | `GET` | `/user-vehicles/{userVehicleId}/merge-suggestions?workshopId&date&timeSlot` | Gợi ý cho wizard (màn xác nhận) | UC-HS02-01 |
| `API-HS02-02` | `POST` | `/conversations/{conversationId}/booking-proposals/{proposalId}/merge` | Chọn gộp trên thẻ đề xuất (chat) | UC-HS02-02 |
| `API-HS02-03` | `POST` | `/bookings` (sửa) | Nhận `mergedItems` khi đặt từ wizard | UC-HS02-02 |
| `HOOK-HS02-01` | Internal | `CardFactory` (CH-02) gắn khối gợi ý vào `BOOKING_PROPOSAL` | | SCR-HS02-01 |
| `JOB-HS02-01` | Celery | `oem.sync_recalls` (hằng ngày) | Đồng bộ chiến dịch theo VIN | P2Q-06 |

---

# 2. Authorization & Guards

Chủ xe; xe / đề xuất / hội thoại của mình (guards us-061 cho `API-HS02-02`, khoá `booking-proposal:{id}`).

---

# 3. SVC-HS02-01 — `MergeAdvisor.suggest`

Đầu vào: xe, xưởng, khung dự kiến, hạng mục chính của lịch. Mục tiêu ≤ 300 ms (FF §18): 4 truy vấn có index, đệm theo (xe, ngày) 10 phút.

| Nguồn | Điều kiện | Mặc định chọn |
|---|---|---|
| `RECALL` | `vehicle_recall.status = OPEN`; chiến dịch còn hiệu lực trong `MERGE_WINDOW_DAYS` quanh ngày hẹn (BR-HS02-01); không có `merge_dismissal` còn hạn | **Chọn sẵn** khi `free_of_charge` (BR-HS02-05) |
| `DUE_SOON` | Hạng mục của mốc kế tiếp (sau mốc đang đặt) có ngày đến hạn ≤ ngày hẹn + `MERGE_WINDOW_DAYS` (F3); không trùng hạng mục chính | Không chọn |
| `DEFERRED` | Dòng `EXTRA` `DECLINED` của xe trong 365 ngày, chưa được làm sau đó (HS-01 `deferred`) | Không chọn |

- Bỏ mục xưởng không làm được (EF-HS02-02): không có `service_price` / `repair_price` cho `item_code` và không phải triệu hồi (triệu hồi: xưởng uỷ quyền hãng mặc định làm được).
- Mỗi mục: `estimate` (giá ước tính; triệu hồi = 0), `durationMin` (WS-02), `reason` ("Chiến dịch {tên} của hãng", "Đến hạn {dd/MM}", "Xưởng đề xuất lần {dd/MM}").

---

# 4. Chọn gộp — kiểm tra lại chỗ (UC-HS02-02)

## 4.1 API-HS02-02 (chat)

`{ "selected": [ { "source": "RECALL", "refKey": "…" }, { "source": "DUE_SOON", "refKey": "BATTERY_CHECK" } ], "deselectedDefaults": [ … ] }`

1. Đề xuất `proposed`, chưa hết hạn (us-061).
2. Tính lại các mục từ `MergeAdvisor` (không tin dữ liệu client ngoài khoá); mục không còn hợp lệ ⇒ bỏ, trả `warnings`.
3. `deselectedDefaults` ⇒ ghi `merge_dismissal` 30 ngày (EDGE-HS02-02).
4. Thời lượng mới = `duration_for(hạng mục chính + mục chọn)` (AC-HS02-02); `fits(workshop, date, time, duration)`:
   - Đủ ⇒ cập nhật `booking_proposal.merged_items` **trong cùng đề xuất** (ngoại lệ có kiểm soát của BR-ENT-1503 us-061: chỉ cột `merged_items` được đổi, `options` giữ nguyên); tin trợ lý cập nhật thẻ (`patch`).
   - Không đủ (AF-HS02-01) ⇒ không đổi đề xuất; `SchedulerService.run(overrides.workshopId, itemCodes = tất cả)` tìm khung đủ dài ⇒ trả `409 MERGE_SLOT_TOO_SHORT` với `details = { "run": RunDto, "keepWithoutMerge": true }` để chủ xe chọn "Giữ khung cũ, không gộp" hoặc một phương án mới.
5. Khi `API-QB-02` xác nhận: tạo booking với `duration_min` mới và các dòng gộp (entity §4).

## 4.2 Wizard

`API-HS02-01` trả cùng cấu trúc; `POST /bookings` thêm `mergedItems: [{ source, refKey }]` — kiểm như §4.1 bước 2, 4 trong khoá giữ chỗ; không đủ ⇒ `409 MERGE_SLOT_TOO_SHORT`.

---

# 5. Thẻ `BOOKING_PROPOSAL` — khối gộp (HOOK-HS02-01)

`data.mergeSuggestions = [{ source, refKey, name, reason, estimate, durationMin, freeOfCharge, preselected }]`, `data.mergedItems = [...]`, `data.totalDurationMin`. Làm giàu (CH-02) tính lại khi mở lại để bỏ mục đã hết hiệu lực.

---

# 6. JOB-HS02-01 — `oem.sync_recalls`

Hãng (mock) `GET /vehicles/{vin}/campaigns` ⇒ upsert `recall_campaign`, `vehicle_recall`; `COMPLETED` từ hãng ⇒ không gợi ý (EDGE-HS02-01). Lỗi ⇒ giữ dữ liệu cũ.

---

# 7. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 404 | `PROPOSAL_NOT_FOUND` | |
| 409 | `PROPOSAL_INACTIVE` / `PROPOSAL_EXPIRED` | (us-061) |
| 409 | `MERGE_SLOT_TOO_SHORT` | Khung không đủ thời lượng sau gộp (`details.run`) |
| 422 | `MERGE_ITEM_INVALID` | Mục không thuộc gợi ý hợp lệ |

---

# 8. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Chọn sẵn chỉ triệu hồi miễn phí; tính phí không bao giờ chọn sẵn (BR-HS02-05) | +2 |
| Unit | Cửa sổ `MERGE_WINDOW_DAYS`; xưởng không làm được ⇒ bỏ | +2 |
| Service | Không dòng tính phí nào khi chủ xe chưa chọn (AC-HS02-01) | +1 |
| Service | Thời lượng sau gộp = Σ chuẩn (AC-HS02-02); không đủ ⇒ `409` + phương án | +2 |
| Service | Bỏ chọn triệu hồi ⇒ không gợi ý 30 ngày (EDGE-HS02-02) | +1 |
| Service | Hãng báo triệu hồi đã làm ⇒ không gợi ý | +1 |
| Perf | `suggest` ≤ 300 ms | +1 |

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
