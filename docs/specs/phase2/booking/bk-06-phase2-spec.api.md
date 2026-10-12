# API Technical Specification — Lịch bảo dưỡng định kỳ tại xưởng quen

> Backend cho Feature `FEAT-P2-BK06`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-06-phase2-spec.ff.md). **Entity:** [Entity Spec](bk-06-phase2-spec.entity.md).
>
> **Tái dùng:** `SchedulerService.run(trigger = SERIES)` + giữ chủ động + `API-BK01-07/08` (xác nhận / bỏ qua lịch giữ sẵn), `get_maintenance_status` (F3), đổi lịch us-053, BK-02 phân loại huỷ, WS-01 khi chủ xe xác nhận, đồng bộ hãng (`oem_integration`) để phát hiện làm ở nơi khác / đổi chủ.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-BK06` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/scheduler/series.py` (mới), route trong `scheduler/route.py`, job trong `scheduler/jobs.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-BK06-01` | `POST` | `/booking-series` | Tạo chuỗi | UC-BK06-01 |
| `API-BK06-02` | `GET` | `/booking-series?userVehicleId` | Xem chuỗi (SCR-BK06-01) | — |
| `API-BK06-03` | `PATCH` | `/booking-series/{seriesId}` | Đổi xưởng / ràng buộc (áp từ lần sau) | AF-BK06-05 |
| `API-BK06-04` | `POST` | `/booking-series/{seriesId}/pause` · `/resume` | Tạm dừng / tiếp tục | UC-BK06-05 |
| `API-BK06-05` | `POST` | `/booking-series/{seriesId}/cancel` | Huỷ chuỗi (tuỳ chọn huỷ lịch đang mở) | UC-BK06-04 |
| `API-BK06-06` | `POST` | `/booking-series/{seriesId}/occurrences/{occurrenceId}/skip` | Bỏ qua lần này | UC-BK06-03 |
| `API-BK06-07` | `GET` | `/booking-series/invitation?bookingId` | Có nên mời tạo chuỗi sau lịch vừa xong không (SCR-BK06-02) | UC-BK06-01 |
| `API-BK06-08` | `POST` | `/booking-series/invitation/dismiss` | Chủ xe từ chối lời mời (ẩn 180 ngày) | UC-BK06-01 |
| `JOB-BK06-01` | Celery | `series.daily` | Tính lại ngày kích hoạt; tạo lần kế tiếp | UC-BK06-02, BR-BK06-02, 07 |
| `HOOK-BK06-01` | Internal | Đồng bộ hãng: lịch sử mới / đổi chủ; xưởng `inactive` | | EF-BK06-01..03 |

---

# 2. Authorization & Guards

Chủ xe, xe của mình (`VERIFIED` + `ACTIVE`). Chủ xưởng không đọc cấu hình chuỗi; chỉ thấy `seriesId != null` trên lịch (nhãn "Khách định kỳ").

---

# 3. API-BK06-01 — tạo chuỗi

```json
{ "userVehicleId": "…", "workshopId": "…", "useProfileConstraints": true, "constraintsOverride": null, "fromBookingId": "…" }
```

1. BR-BK06-08: hồ sơ BK-01 `automation_level ∈ {HOLD, AUTO_BOOK}` ⇒ không thì `422 SERIES_REQUIRES_HOLD_LEVEL` (`details.currentLevel`; frontend đề nghị bật "Giữ chỗ sẵn"). Mức `AUTO_BOOK` cần `CONSENT_AUTO_BOOKING` như BK-01.
2. Xưởng `ACTIVE` ⇒ không thì `422 WORKSHOP_INACTIVE`. Xe đã có chuỗi `active` / `paused` ⇒ `409 SERIES_EXISTS` (`details.seriesId`).
3. Mốc `UNKNOWN` ⇒ vẫn tạo (`next_* = NULL`), trả `warnings: ["DUE_UNKNOWN"]` (EF-BK06-04).
4. Chèn chuỗi, tính `next_*` (§6.1). `next_trigger_date ≤ today` (EDGE-BK06-01) ⇒ chạy tạo lần kế tiếp ngay (§6.2) sau commit.

Response `201 SeriesDto`:

```json
{ "seriesId": "…", "status": "ACTIVE", "workshop": { "workshopId": "…", "name": "VinFast Cầu Giấy", "active": true },
  "constraints": { "source": "PROFILE", "availability": [ { "weekday": 6, "startTime": "08:00", "endTime": "12:00" } ] },
  "next": { "milestoneKm": 24000, "dueDate": "2026-10-26", "triggerDate": "2026-10-12", "occurrence": { "occurrenceId": "…", "status": "HELD", "bookingId": "…", "holdExpiresAt": "…" } },
  "history": [ { "milestoneKm": 12000, "status": "CONFIRMED", "bookingId": "…" } ] }
```

---

# 4. Quản lý chuỗi

- `PATCH`: `workshopId`, `constraintsOverride` / `useProfileConstraints`. Áp từ lần **sau**; lịch đang giữ / đã xác nhận không đổi (AF-BK06-05). Xưởng mới phải `ACTIVE`.
- `pause` (`OWNER`) / `resume`: `resume` khi `pause_reason = WORKSHOP_INACTIVE` và xưởng vẫn `inactive` ⇒ `409 WORKSHOP_INACTIVE` (đổi xưởng trước).
- `cancel` `{ "cancelOpenBooking": false }`: chuỗi `cancelled (OWNER)`. Lịch đang mở của chuỗi: `cancelOpenBooking = false` ⇒ giữ nguyên (vẫn giữ `series_id` để lịch sử đúng); `true` ⇒ huỷ qua luồng huỷ MVP (BK-02 phân loại bình thường; lịch giữ chủ động chưa xác nhận ⇒ `PROACTIVE_HOLD_DISMISSED`, không tính) (AC-BK06-03).
- `skip`: occurrence `held` / `alternatives_offered` ⇒ `skipped`; lịch giữ chủ động chưa xác nhận ⇒ `API-BK01-08` (`PROACTIVE_HOLD_DISMISSED`, không tính điểm, BR-BK06-05). Đã xác nhận ⇒ huỷ theo BK-02 (có thể bị tính huỷ muộn — trả `cancelPreview` của BK-02 trước khi xác nhận, frontend hiện).

---

# 5. API-BK06-07 — lời mời tạo chuỗi

Sau lịch `completed` (hiển thị ở hỏi thăm sau dịch vụ F9 và vé): trả `{ "invite": true, "workshop": {…} }` khi: xe không có chuỗi `active` / `paused`, lịch là `MAINTENANCE` (BK-03), chủ xe chưa từ chối lời mời trong 180 ngày (`Redis series:invite_dismissed:{vehicleId}`). Frontend gọi `POST /booking-series/invitation/dismiss` khi chủ xe bấm "Không".

---

# 6. JOB-BK06-01 — `series.daily` (06:00)

## 6.1 Tính lại (BR-BK06-07, EDGE-BK06-02)

Mỗi chuỗi `active`: `get_maintenance_status` ⇒ `next_milestone_km`, `next_due_date` (từ F3, đã gồm dự báo km), `next_trigger_date`. `UNKNOWN` ⇒ để `NULL`, thông báo chủ xe một lần mỗi 30 ngày (EF-BK06-04).

## 6.2 Tạo lần kế tiếp

Điều kiện: `next_trigger_date ≤ today` **và** chưa có occurrence cho (`series_id`, `next_milestone_km`) **và** xe không có lịch mở (BR-BK06-04). Khoá Redis `series:{seriesId}` + unique occurrence ⇒ chạy lại cùng ngày không tạo trùng (FF §18, AC-BK06-01).

1. `SchedulerService.run(trigger = SERIES, overrides = { workshopId: series.workshop_id, availability: constraints }, applyAutomation = true)`; cửa sổ = `today … next_due_date` (hạn chót mốc, BR-BK01-12).
2. Có phương án ở xưởng chuỗi ⇒ BK-01 giữ chủ động (mức `HOLD`) hoặc tự đặt (mức `AUTO_BOOK`, Q-BK06-02) ⇒ occurrence `held`; booking `series_id`. Thông báo "Lịch định kỳ: {xưởng} {giờ}" + nút Xác nhận / Bỏ qua lần này / Xem phương án khác (SCR-BK06-03).
3. Không có ở xưởng chuỗi ⇒ chạy lại **không** ràng buộc xưởng, `applyAutomation = false` ⇒ occurrence `alternatives_offered` với `scheduling_run_id`; thông báo "Xưởng {tên} kín, có phương án khác **cho lần này**" (AF-BK06-01). Chuỗi giữ xưởng gốc.
4. Không có gì ⇒ `no_option` + thông báo kèm gợi ý nới (BK-01).
5. Lịch giữ hết hạn ⇒ BK-01 JOB-BK01-02 huỷ (không tính); hook cập nhật occurrence `expired`; chuỗi vẫn `active`; nhắc mốc F7 tiếp tục (EF-BK06-05).
6. Lịch được xác nhận ⇒ occurrence `confirmed` (hook từ `API-BK01-07`).

---

# 7. HOOK-BK06-01 — sự kiện ngoài

| Sự kiện | Xử lý |
|---|---|
| Xưởng chuỗi chuyển `inactive` | Chuỗi `paused (WORKSHOP_INACTIVE)`; thông báo mời chọn xưởng mới (EF-BK06-01) |
| Hãng đồng bộ lịch sử bảo dưỡng định kỳ mới (làm ở nơi khác) cho mốc đang có occurrence `held` / `alternatives_offered` | Huỷ lịch giữ (`PROACTIVE_HOLD_DISMISSED`, không tính) / đóng phương án; occurrence `superseded`; tính lại mốc; báo chủ xe; không gửi nhắc thừa (EF-BK06-02, AC-BK06-04) |
| Hãng báo đổi chủ | Chuỗi `cancelled (OWNERSHIP_CHANGED)`, xoá `constraints_override` (EF-BK06-03) |

---

# 8. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 404 | `SERIES_NOT_FOUND` / `OCCURRENCE_NOT_FOUND` | |
| 409 | `SERIES_EXISTS` | Xe đã có chuỗi |
| 409 | `SERIES_INVALID_STATE` | Thao tác sai trạng thái |
| 409 | `WORKSHOP_INACTIVE` | Tiếp tục khi xưởng vẫn ngừng |
| 422 | `SERIES_REQUIRES_HOLD_LEVEL` | Mức tự động hoá < Giữ chỗ sẵn |

---

# 9. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `next_trigger_date` theo mốc; ODO tăng nhanh kéo sớm | +2 |
| Job | Chạy hai lần cùng ngày ⇒ một lịch (AC-BK06-01); xe có lịch mở ⇒ không tạo | +2 |
| Job | Xưởng chuỗi kín ⇒ phương án khác, chuỗi giữ xưởng | +1 |
| Service | Bỏ qua lần này ⇒ mốc sau vẫn được tạo (AC-BK06-02) | +1 |
| Service | Huỷ chuỗi không huỷ lịch đã xác nhận khi không chọn (AC-BK06-03) | +2 |
| Hook | Làm ở nơi khác ⇒ huỷ giữ, không nhắc thừa (AC-BK06-04); đổi chủ ⇒ huỷ chuỗi | +2 |
| API | Mức `SUGGEST` ⇒ `422` | +1 |

---

# 10. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
