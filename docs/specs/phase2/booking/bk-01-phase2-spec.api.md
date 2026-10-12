# API Technical Specification — Tự động lập lịch theo ràng buộc của chủ xe

> Backend cho Feature `FEAT-P2-BK01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-01-phase2-spec.ff.md). **Entity:** [Entity Spec](bk-01-phase2-spec.entity.md) — `owner_scheduling_profile`, `owner_scheduling_constraint`, `scheduling_run`, `scheduling_option`, cột mới của `booking`.
>
> **Tái dùng, không viết lại (BR-BK01-07):** `BookingService.open_slots` (quét khung theo lô, us-061), `check_availability`, `create_for_slot` (khoá xe + khoá khung + sức chứa + BR-013), `_reschedule_locked` (us-053), `BookingStateMachine.transition` (ghi `booking_status_event`), `WorkshopLocationFinder` (khoảng cách), `UserVehicleService.get_maintenance_status` (mốc, hạn chót), `ConsentService` (PL-01). Bộ lập lịch **không** tự đếm chỗ.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-BK01` |
| Version | `v0.2` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/scheduler/` (mới): `engine.py` (hàm thuần: lọc, chấm điểm, lý do, nới), `service.py`, `route.py`, `jobs.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-BK01-01` | `GET` | `/scheduling/profile` | Đọc hồ sơ thói quen + ràng buộc (gồm suy ra) | UC-BK01-01 |
| `API-BK01-02` | `PUT` | `/scheduling/profile` | Lưu hồ sơ (thay toàn bộ ràng buộc `USER`) | UC-BK01-01, BR-BK01-10 |
| `API-BK01-03` | `POST` | `/scheduling/profile/constraints/{constraintId}/review` | Xác nhận / xoá ràng buộc suy ra | BR-BK01-10 |
| `API-BK01-04` | `GET` | `/scheduling/config` | Tham số hiển thị (giờ giữ, giờ huỷ miễn phí, buổi) | — |
| `API-BK01-05` | `POST` | `/scheduling/runs` | Chạy bộ lập lịch → phương án / nới / câu hỏi mâu thuẫn | UC-BK01-02, BR-BK01-01..04, 11, 12 |
| `API-BK01-06` | `POST` | `/scheduling/options/{optionId}/select` | Chọn phương án: giữ / chuyển giữ / đổi xưởng | UC-BK01-04, BR-BK01-09, EF-BK01-01 |
| `API-BK01-07` | `POST` | `/bookings/{bookingId}/proactive/confirm` | Xác nhận lịch giữ sẵn (SCR-BK01-04) | UC-BK01-03, BR-BK01-06 |
| `API-BK01-08` | `POST` | `/bookings/{bookingId}/proactive/dismiss` | "Bỏ qua lần này" | SCR-BK01-04 |
| `API-BK01-09` | `POST` | `/workshop-owner/bookings/{bookingId}/unable-to-serve` | Xưởng báo không phục vụ được | UC-BK01-05, AF-BK01-08 |
| `JOB-BK01-01` | Celery | `scheduler.proactive_due_scan` | Lập lịch chủ động khi xe `DUE_SOON` | UC-BK01-03 |
| `JOB-BK01-02` | Celery | `scheduler.expire_proactive_holds` | Hết hạn giữ + nhắc trước 2 giờ | EF-BK01-02, AC-BK01-07 |
| `TOOL-BK01-01` | Agent tool | `find_schedule_options` | Agent gọi bộ lập lịch; không tự chọn | BR-BK01-15 |
| `HOOK-BK01-01` | Internal | `cancel_unconfirmed` bỏ qua `proactive` | Không chạy hạn chót duyệt khi chưa xác nhận | BR-BK01-06 |

Mọi nơi khác cần lập lịch (CH-01 chip, BK-04 widget, BK-05 bản đồ, BK-06 lịch định kỳ, BK-07 danh sách chờ, đổi lịch) gọi `SchedulerService.run(...)` — cùng hàm với `API-BK01-05`, chỉ khác `trigger`.

---

# 2. Authorization & Guards

1. `API-BK01-01..08`: chủ xe đăng nhập (`get_current_user_id`), tài khoản `ACTIVE`. Xe (`userVehicleId`) phải thuộc chủ xe, `VERIFIED` + `ACTIVE` ⇒ không thì `409 VEHICLE_NOT_ACTIVE`.
2. `optionId` phải thuộc `scheduling_run.user_id = user_id` ⇒ không thì `404 OPTION_NOT_FOUND`. `bookingId` phải thuộc chủ xe ⇒ `404 BOOKING_NOT_FOUND`.
3. `API-BK01-09`: chủ xưởng (`/workshop-owner`, dependency có sẵn của `workshop_board`), booking thuộc xưởng của mình ⇒ không thì `404 BOOKING_NOT_FOUND`. Chủ xưởng không đọc được hồ sơ thói quen (FF §16): phản hồi chỉ có trạng thái booking.
4. Khoá Redis:
   - `scheduler-run:{userVehicleId}` (`blocking=False`) cho `API-BK01-05`: đang chạy ⇒ `409 SCHEDULER_BUSY`.
   - `scheduling-option:{optionId}` (`wait_timeout = 2s`) cho `API-BK01-06` (EDGE-BK01-06): không lấy được ⇒ `409 OPTION_IN_PROGRESS`. Khoá xe + khoá khung vẫn do `create_for_slot` lấy bên trong.
   - Redis lỗi ⇒ `503 SERVICE_UNAVAILABLE`.

---

# 3. Hồ sơ thói quen

## 3.1 `ProfileDto`

```json
{
  "automationLevel": "HOLD",
  "anchor": { "type": "HOME", "locationId": "0b6d…", "label": "Nhà", "province": "Hà Nội" },
  "radiusKm": 5,
  "preferredWorkshop": { "workshopId": "c0ca…", "name": "VinFast Cầu Giấy", "source": "USER", "inactive": false },
  "minRating": null,
  "availability": [ { "id": "a1…", "weekday": 6, "startTime": "08:00", "endTime": "12:00", "source": "USER", "status": "ACTIVE" } ],
  "preferredTimes": [ { "id": "p1…", "weekday": null, "startTime": "08:00", "endTime": "09:00", "source": "INFERRED", "status": "PENDING_REVIEW" } ],
  "excludedWorkshops": [ { "id": "e1…", "workshopId": "…", "name": "…", "reason": "LOW_RATING" } ],
  "needsReview": false,
  "autoBookAllowed": false,
  "version": 3
}
```

- `autoBookAllowed` = `ConsentService.is_granted(CONSENT_AUTO_BOOKING)`.
- Ràng buộc `INFERRED` chỉ trả khi `CONSENT_LONG_TERM_MEMORY` hiệu lực (BR-ENT-BK01-03).
- Chưa có hồ sơ ⇒ `200` với mặc định và `version = 0`.

## 3.2 API-BK01-02 — `PUT /scheduling/profile`

Body = `ProfileDto` phần ghi được: `automationLevel`, `anchor { type, locationId?, province? }`, `radiusKm`, `preferredWorkshopId`, `minRating`, `availability[]`, `preferredTimes[]` (chỉ dòng `USER`), `expectedVersion`.

| Rule | Error |
|---|---|
| `automationLevel = AUTO_BOOK` khi chưa có `CONSENT_AUTO_BOOKING` | `422 AUTO_BOOK_CONSENT_REQUIRED` |
| `radiusKm` ngoài `(0, 100]` | `400 INVALID_REQUEST` |
| `availability` > 21 dòng, `startTime ≥ endTime`, chồng lấn trong cùng `weekday` | `400 INVALID_REQUEST` |
| `anchor.type ∈ {HOME, WORK}` mà `locationId` không thuộc chủ xe | `404 LOCATION_NOT_FOUND` |
| `preferredWorkshopId` không `ACTIVE` | `422 WORKSHOP_INACTIVE` |
| `expectedVersion` lệch | `409 PROFILE_VERSION_CONFLICT` |

Xử lý: một transaction; upsert profile (`version + 1`), xoá dòng `USER` của các `kind` `AVAILABILITY` / `PREFERRED_TIME` rồi chèn lại. Không đụng dòng `INFERRED` và `EXCLUDED_WORKSHOP`. `availability = []` hợp lệ (EDGE-BK01-03: coi như rảnh mọi giờ xưởng mở; `API-BK01-05` trả `warnings: ["NO_AVAILABILITY_WINDOW"]`).

## 3.3 API-BK01-03 — review ràng buộc suy ra

`{ "action": "CONFIRM" | "REJECT" }`. `CONFIRM` ⇒ `status = active`, giữ `source = INFERRED` (vẫn hiện nhãn "suy ra"). `REJECT` ⇒ `status = rejected` và gọi PS-01 đánh dấu mục nhớ gốc bị chủ xe bác (không suy ra lại cùng giá trị).

## 3.4 API-BK01-04 — `GET /scheduling/config`

```json
{ "data": { "proactiveHoldHours": 24, "autoBookFreeCancelHours": 2, "maxOptions": 3, "windowDays": 14,
            "defaultRadiusKm": 10, "dayParts": { "MORNING": ["08:00","12:00"], "AFTERNOON": ["12:00","17:00"], "EVENING": ["17:00","20:00"] } } }
```

Không cần đăng nhập phía chủ xe khác; vẫn yêu cầu đăng nhập để thống nhất.

---

# 4. API-BK01-05 — `POST /scheduling/runs`

## 4.1 Request

```json
{
  "userVehicleId": "a751…",
  "trigger": "OWNER_REQUEST",
  "location": { "lat": 21.03, "lng": 105.79 },
  "overrides": { "availability": [ { "date": "2026-10-13", "startTime": "13:00", "endTime": "17:00" } ], "workshopId": null, "radiusKm": null },
  "relaxations": [],
  "conflictPreference": null,
  "saveOverridesAsDefault": false,
  "excludeWorkshopIds": [],
  "applyAutomation": false
}
```

| Field | Validation / ý nghĩa |
|---|---|
| `trigger` | `OWNER_REQUEST`, `CHAT`, `CHIP`, `WIDGET`, `MAP`, `RESCHEDULE` (chủ xe gọi được). `DUE_JOB`, `SERIES`, `WORKSHOP_UNABLE`, `WS_CONFIRM_TIMEOUT`, `WAITLIST` chỉ nội bộ |
| `location` | Chỉ dùng khi `CONSENT_LOCATION` hiệu lực; không thì bỏ qua (BR-PL01-05) |
| `overrides.availability` | Theo ngày cụ thể; thắng hồ sơ cho lần này (BR-BK01-11) |
| `overrides.workshopId` | Chủ xe chọn trên bản đồ (BK-05) / widget: chỉ tìm ở xưởng này |
| `relaxations[]` | Mã nới chủ xe đã chọn từ lần trước: `RADIUS_X1_5`, `ADJACENT_DAY_PART`, `WINDOW_PLUS_7D` |
| `conflictPreference` | `KEEP_WORKSHOP` / `KEEP_TIME` — trả lời câu hỏi mâu thuẫn (EF-BK01-03) |
| `saveOverridesAsDefault` | `true` ⇒ ghi `overrides.availability` (đổi thành `weekday`) vào hồ sơ sau khi chạy |
| `applyAutomation` | `true` ⇒ giữ chỗ phương án đầu nếu mức ≥ `HOLD` (màn Đặt lịch, chip). `false` ⇒ chỉ trả phương án (bản đồ, xem trước) |
| `itemCodes` | Tuỳ chọn: hạng mục cụ thể thay cho hạng mục của mốc (khuyến nghị chưa làm HS-01, gộp việc HS-02, sửa chữa AD-02). Dùng cho thời lượng (WS-02) và lọc phụ tùng (BK-09) |
| `reportedSymptom` | Tuỳ chọn (AD-02): triệu chứng chủ xe kể, ≤ 500 ký tự; đi theo phương án → `booking_proposal` → `booking.reported_symptom` |
| `conversationId` | Tuỳ chọn: khi gọi từ màn ngoài chat nhưng bắt đầu từ chat (bản đồ BK-05 `from=chat`), backend gắn thẻ `SCHEDULE_OPTIONS` vào hội thoại này |

## 4.2 Processing (`SchedulerService.run`)

1. Guards §2, khoá `scheduler-run`. Đo `duration_ms` từ đây; ngân sách `SCHEDULER_TIMEOUT_MS = 1800`.
2. **Nạp ràng buộc hiệu lực:** hồ sơ (§3) + `overrides` (thắng hồ sơ) + đồng ý: `CONSENT_LONG_TERM_MEMORY` ⇒ thêm `INFERRED` `active`; `CONSENT_CALENDAR_SYNC` ⇒ trừ khoảng bận từ `calendar_busy_cache` (BK-04) khỏi khung rảnh. `ConsentService` lỗi ⇒ coi như chưa đồng ý.
3. **Mốc + hạn chót (BR-BK01-12):** `get_maintenance_status`. `DUE_SOON` / `NORMAL` ⇒ `deadline = next_milestone.due_date`; `OVERDUE` ⇒ không hạn chót, sắp khung sớm nhất trước (BK-03); `UNKNOWN` ⇒ `outcome = NO_OPTION` kèm `reason = DUE_UNKNOWN` (EF-BK01-05, frontend mở chọn hạng mục).
4. **Điểm neo:** `location` (nếu được phép) → `anchor` hồ sơ → `anchor_province` → không có ⇒ `outcome = NEED_LOCATION` + `regions[]` (tái dùng us-061 `QUICK_BOOKING_NEED_LOCATION`, EF-BK01-04).
5. **Xe đã có lịch mở (BR-BK01-08):** ghi `openBookingId`; mọi phương án trả về có `mode = RESCHEDULE`, loại trừ đúng khung của lịch đang mở.
6. **Lọc cứng (`engine.filter_hard`, hàm thuần):**
   - Xưởng `ACTIVE`, trong `radius_km` (có toạ độ) hoặc cùng khu vực (không toạ độ); bỏ `EXCLUDED_WORKSHOP` và `excludeWorkshopIds`.
   - Cửa sổ: `today … min(today + SCHEDULER_WINDOW_DAYS, deadline)`; khung bắt đầu ≥ `now + QUICK_BOOKING_MIN_LEAD_MINUTES`.
   - `BookingService.open_slots(workshop, first, last)` cho từng xưởng (3 truy vấn / xưởng); chỉ khung `available = true` và nằm trọn trong khung rảnh. Khi WS-02 bật cho xưởng: khung phải chứa đủ `duration_min` của hạng mục (WS-02 `CapacityService.fits`).
   - **BR-BK01-14:** xưởng có `count(proactive pending) ≥ ceil(PROACTIVE_HOLD_MAX_PCT × capacity_day)` cho ngày đó ⇒ khung của ngày đó vẫn là ứng viên nhưng gắn `holdable = false`.
   - **Bậc `RESTRICTED` (BK-02 BR-BK02-03):** chỉ giữ xưởng `MANUAL` hoặc khung thấp điểm (đơn vị có tỉ lệ lấp đầy 30 ngày < `OFF_PEAK_FILL_PCT`, mặc định 50 %); không còn gì ⇒ `NO_OPTION` với `reason = RELIABILITY_RESTRICTED` (EDGE-BK02-05).
   - Đếm loại theo lý do vào `rejected_by`.
7. **Mâu thuẫn (EF-BK01-03):** xưởng yêu thích có trong bán kính nhưng **không mở cửa** trong bất kỳ khung rảnh nào của cửa sổ, và `conflictPreference = null` ⇒ `outcome = CONFLICT`, `question = { "code": "WORKSHOP_VS_TIME", "options": ["KEEP_WORKSHOP", "KEEP_TIME"] }`; không trả phương án. `KEEP_WORKSHOP` ⇒ bỏ khung rảnh, chỉ xưởng yêu thích; `KEEP_TIME` ⇒ coi xưởng yêu thích như xưởng thường.
8. **Chấm điểm (`engine.score`, BR-BK01-04):** `score = Σ w_i × f_i` với `f ∈ [0,1]`:
   | Yếu tố | `f` | Trọng số mặc định (`SCHEDULER_WEIGHTS`, Q-BK01-01) |
   |---|---|---|
   | `PREFERRED` | 1 nếu là xưởng yêu thích | 40 |
   | `DISTANCE` | `1 − d / radius` (không toạ độ: 0,5) | 25 |
   | `USUAL_TIME` | 1 nếu khung nằm trong `PREFERRED_TIME`, giảm tuyến tính 0 sau 3 giờ | 20 |
   | `RATING` | `(rating − 1) / 4` khi đủ `MIN_REVIEWS` (PS-02) và `CONSENT_PERSONALIZATION_DATA`; không thì 0,5 | 10 |
   | `RELIABILITY` | `1 − workshop_unreliability` (BK-02 BR-BK02-06), mặc định 1 | 5 |
   | `AFFINITY` | 1 khi chủ xe từng chấm xưởng ≥ 4 (PS-02 `owner_workshop_preference_signal`, cần `CONSENT_PERSONALIZATION_DATA`) | 10 |
   | `COHORT` | `share` của xưởng trong nhóm tương đồng (PS-04); chỉ khi có đồng ý | 25 khi chủ xe chưa có lịch sử, 5 khi đã có (≤ yếu tố cá nhân nhỏ nhất) |
   Hoà ⇒ khung sớm hơn, rồi xưởng gần hơn. `search_tier` theo BR-BK01-02: tier 1 (yêu thích, đúng giờ quen) > tier 2 (yêu thích, giờ khác) > tier 3 (xưởng khác); sắp theo `(tier, −score, start, distance)`. Q-BK01-02 chốt "đổi giờ cùng xưởng" trước ⇒ tier 2 trước tier 3.
9. **Lấy tối đa `SCHEDULER_MAX_OPTIONS`**, mỗi xưởng tối đa 2 phương án (đa dạng). Lý do: 1–3 mã có đóng góp lớn nhất, chỉ yếu tố > 0 (`engine.reasons`); câu dẫn (`headline`) khi tier 1 trống: "Xưởng {tên} đã kín {buổi} {ngày}".
10. **Không có phương án (AF-BK01-04):** `engine.relaxations` thử lần lượt `RADIUS_X1_5`, `ADJACENT_DAY_PART`, `WINDOW_PLUS_7D` (mỗi cách một ràng buộc), chạy lại bước 6 (không ghi DB), giữ cách cho ≥ 1 phương án và không vượt `deadline`. Trả tối đa 3 `relaxationOffers` kèm `optionCount`. Mọi xưởng trong vùng đều bị loại (`EXCLUDED_WORKSHOP`) ⇒ `reason = ALL_EXCLUDED` + offer `UNHIDE_WORKSHOPS` (PS-02 EDGE-PS02-01). **Không** giữ chỗ (AC-BK01-04). Kèm `waitlistAvailable` khi BK-07 bật.
11. **Ghi `scheduling_run` + `scheduling_option`** (một transaction), `expires_at = now + SCHEDULER_OPTION_TTL_MIN`.
12. **Mức tự động hoá** (khi `applyAutomation` hoặc trigger nội bộ):
    - `SUGGEST` ⇒ không giữ.
    - `HOLD` và phương án đầu `holdable` ⇒ `hold_option(option, proactive=True)` (§5.3). Thua tranh chấp (EF-BK01-01) ⇒ thử phương án kế tiếp, tối đa hết danh sách; kết quả `heldOptionId`.
    - `AUTO_BOOK` ⇒ như `HOLD` rồi `confirm_proactive(..., by_system=True)` (§6), trừ khi chủ xe ở bậc `RESTRICTED` (điểm ≥ 3, BK-02) ⇒ hạ về `HOLD` cho lần đó, `automationDowngrade = "RELIABILITY_TIER"` (EDGE-BK01-08).
    - Xe có lịch mở ⇒ không tự giữ ở mọi mức.
13. **Quá thời gian (EF-BK01-06):** hết ngân sách giữa bước 6 ⇒ dừng quét xưởng còn lại, chấm điểm các ứng viên đã có, `outcome = TIMEOUT_PARTIAL` nếu ≥ 1 phương án; không có ⇒ `503 SCHEDULER_TIMEOUT` (cho thử lại).
14. `saveOverridesAsDefault` ⇒ ghi hồ sơ sau khi trả kết quả thành công.
15. Sự kiện PL-03: `scheduler_run` (`trigger`, `outcome`, `optionCount`, `candidateCount`, `rejectedBy`, `durationMs`); `booking_intent_started` khi `trigger` do chủ xe khởi tạo.

## 4.3 Response `201`

```json
{
  "data": {
    "runId": "9c1a…",
    "outcome": "OPTIONS",
    "headline": "Xưởng VinFast Cầu Giấy đã kín sáng thứ Bảy 10/10",
    "mode": "NEW",
    "openBookingId": null,
    "options": [
      {
        "optionId": "o1…", "rank": 1, "tier": 3,
        "workshop": { "workshopId": "…", "name": "VinFast Thanh Xuân", "address": "…", "isPreferred": false },
        "date": "2026-10-10", "timeSlot": "08:00", "distanceKm": 3.2, "travelMinutes": 12, "remainingCapacity": 2,
        "score": 71.5,
        "reasons": [ { "code": "NEAREST", "text": "Gần bạn nhất (3,2 km)" }, { "code": "IN_FREE_WINDOW", "text": "Trong giờ rảnh sáng thứ Bảy" } ],
        "held": { "bookingId": "b7…", "holdExpiresAt": "2026-10-09T02:00:00Z" },
        "expiresAt": "2026-10-08T02:05:00Z"
      }
    ],
    "relaxationOffers": [],
    "waitlistAvailable": false,
    "question": null,
    "regions": null,
    "warnings": [],
    "automationDowngrade": null
  }
}
```

`outcome`: `OPTIONS`, `NO_OPTION` (có `relaxationOffers`, `reason`), `CONFLICT` (có `question`), `NEED_LOCATION` (có `regions`), `TIMEOUT_PARTIAL`. Mọi kết quả nghiệp vụ là `201`; chỉ lỗi §9 là mã lỗi.

`relaxationOffers[]`: `{ "code": "RADIUS_X1_5", "label": "Mở rộng lên 8 km", "optionCount": 2 }`.

---

# 5. API-BK01-06 — `POST /scheduling/options/{optionId}/select`

## 5.1 Request

Không body. Idempotent theo `optionId`.

## 5.2 Processing

1. Guards §2 (khoá `scheduling-option`). Đọc lại phương án trong khoá:
   - `selected` / `held` ⇒ `200` với booking đã có (`replayed: true`).
   - `released` / `stale` ⇒ `409 OPTION_INACTIVE`.
   - `expires_at ≤ now` và chưa `held` ⇒ **kiểm tra lại** chỗ (EDGE-BK01-07) thay vì từ chối: còn chỗ thì làm tiếp; hết ⇒ bước 4.
2. Xác định chế độ:
   - **NEW:** xe không có lịch mở.
   - **SWITCH_HOLD:** lịch mở của xe là `proactive pending` của cùng `run` (chủ xe chọn phương án khác phương án đang giữ, SCR-BK01-02).
   - **RESCHEDULE_SAME_WORKSHOP:** lịch mở khác, cùng xưởng ⇒ `BookingService.reschedule` (us-053, giữ luật đổi lịch).
   - **RESCHEDULE_OTHER_WORKSHOP:** lịch mở khác, xưởng khác (BR-BK01-09).
3. **Giữ mới trước, trả cũ sau, một transaction** (SWITCH_HOLD và RESCHEDULE_OTHER_WORKSHOP):
   ```text
   lock vehicle + lock new slot (create_for_slot internals)
   create new booking (proactive = old.proactive for SWITCH_HOLD, false otherwise; replaced_booking_id = old.id)
   transition old → cancelled (reason RESCHEDULED_TO_OTHER_WORKSHOP | PROACTIVE_HOLD_DISMISSED, actor vehicle_owner)
   option.status = selected/held; old option.status = released
   COMMIT
   ```
   Cần thêm vào `booking/service.py`: `replace_booking(user, old_booking_id, new_slot, *, proactive, scheduling_option_id) -> BookingOut` — dùng chung `_create_booking_locked` với cờ bỏ qua BR-013 **chỉ cho** `old_booking_id` (BR-013 vẫn chặn mọi lịch mở khác). Huỷ lịch cũ trong cùng transaction nên không có lúc xe có hai lịch mở.
4. **Hết chỗ** (`SlotFullError`, khung đã qua, xưởng `INACTIVE`): phương án ⇒ `stale`; chạy lại `SchedulerService.run(trigger = <trigger cũ>, excludeSlots = [khung này])` không tự giữ; trả `409 OPTION_SLOT_FULL` với `details = { "run": <RunDto mới> }`. Lịch cũ không đổi (AC-BK01-05).
5. Booking mới đi theo luồng MVP: NEW ở mức `SUGGEST` = giữ ngắn (`hold_expires_at` us-029) và chủ xe vào màn tóm tắt xác nhận như hiện nay; `proactive` chỉ khi chọn từ thẻ giữ sẵn.
6. Sự kiện PL-03 `option_selected` (`mode`, `rank`, `tier`, `latencyFromRunMs`).

## 5.3 Response `200`

```json
{ "data": { "optionId": "o2…", "mode": "RESCHEDULE_OTHER_WORKSHOP", "booking": { "…BookingOut" }, "replacedBookingId": "b1…", "replayed": false } }
```

---

# 6. API-BK01-07 / 08 — Lịch giữ sẵn

## 6.1 `POST /bookings/{bookingId}/proactive/confirm`

1. Booking phải `pending` + `proactive = true` ⇒ không thì `409 NOT_PROACTIVE_HOLD` (`details.status`). `hold_expires_at ≤ now` ⇒ `409 PROACTIVE_HOLD_EXPIRED`.
2. Một transaction: `proactive = false`, `proactive_confirmed_at = now`, `hold_expires_at = NULL`.
   - Xưởng `AUTO` (hoặc WS-01 luật tự nhận khớp) ⇒ `transition(pending → confirmed, actor = system, source = "PROACTIVE_CONFIRM")`.
   - Xưởng `MANUAL` ⇒ giữ `pending`; hạn chót duyệt chạy từ `proactive_confirmed_at` (HOOK-BK01-01).
3. Trả `BookingOut`. Idempotent: gọi lại khi đã `proactive = false` ⇒ `200` booking hiện tại.

**Mức 3** gọi cùng hàm với `by_system = True`: `auto_booked = true`, `free_cancel_until = now + AUTO_BOOK_FREE_CANCEL_HOURS`; thông báo "Đã tự đặt lịch" kèm nút "Huỷ" / "Đổi giờ" (NOTI).

## 6.2 `POST /bookings/{bookingId}/proactive/dismiss`

Booking `pending` + `proactive` ⇒ `cancelled`, `reason = PROACTIVE_HOLD_DISMISSED`, chỗ được trả. Không tính điểm (BK-02). Đã không còn `proactive` ⇒ `409 NOT_PROACTIVE_HOLD`.

## 6.3 HOOK-BK01-01 — `cancel_unconfirmed`

Sửa `BookingService.cancel_unconfirmed`: bỏ qua `proactive = true`; `deadline = coalesce(proactive_confirmed_at, created_at) + BOOKING_WS_CONFIRM_DEADLINE_HOURS`. Bảng việc của xưởng (`GET /workshop-owner/bookings`) trả thêm `proactive`, frontend xưởng hiện nhãn "Hệ thống đang giữ cho khách" và không có nút Duyệt cho tới khi chủ xe xác nhận.

---

# 7. API-BK01-09 — `POST /workshop-owner/bookings/{bookingId}/unable-to-serve`

## 7.1 Request

```json
{ "reason": "STAFF", "note": "2 KTV nghỉ ốm" }
```

`reason ∈ {STAFF, PARTS, INCIDENT, CLOSED}`; `note` ≤ 300 ký tự, bắt buộc khi `INCIDENT`. Gọi nội bộ từ WS-03 (KTV nghỉ đột xuất) thêm `source = TECHNICIAN_ABSENCE`.

## 7.2 Processing

1. Booking `pending` hoặc `confirmed` ⇒ không thì `409 INVALID_BOOKING_STATE`.
2. `SchedulerService.run(trigger = WORKSHOP_UNABLE, user = chủ xe của booking, excludeWorkshopIds = [xưởng này] khi reason ∈ {CLOSED, INCIDENT}, excludeSlots = [khung bị báo])`. Còn < 2 giờ tới giờ hẹn ⇒ ưu tiên khung cùng ngày (thêm yếu tố tạm `SAME_DAY` trọng số 30), không có thì khung sớm nhất (EDGE-BK01-10). Bỏ qua mức tự động: **luôn** giữ phương án đầu (`proactive = true`).
   - **`source = TECHNICIAN_ABSENCE` (WS-03 BR-WS03-05, PO chốt 2026-10-12):** xưởng này không còn đủ người trong ngày đó ⇒ loại cả ngày của xưởng này (`excludeSlots` = mọi khung ngày đó tại xưởng); thêm yếu tố tạm `SIMILAR_WORKSHOP` trọng số 20 = 1 khi xưởng ứng viên làm đủ các hạng mục của lịch cũ và cách xưởng cũ ≤ 5 km (0,5 khi ≤ 10 km), để xưởng phù hợp / tương tự đứng đầu. Xưởng cũ vào ngày khác vẫn là phương án được (chủ xe có thể muốn giữ xưởng quen).
3. Một transaction: lịch cũ `cancelled`, `reason_code = WORKSHOP_UNABLE_<REASON>`, `actor = workshop_owner`, `note`; lịch mới (nếu có) `replaced_booking_id = old.id`.
4. Thông báo chủ xe (NOTI): có phương án ⇒ "Xưởng {tên} không phục vụ được lịch {giờ}. Mình đã giữ {phương án} đến {hạn}." + link SCR-BK01-04 (hiện thêm tối đa 2 phương án khác để chủ xe đổi); với `TECHNICIAN_ABSENCE` câu là "Xưởng {tên} thiếu kỹ thuật viên nên không phục vụ được lịch {giờ}. Mình đã giữ chỗ ở {xưởng / giờ} — xưởng tương tự gần đó."; không có ⇒ lý do + nút "Tìm lại".
5. BK-02: ghi một lần huỷ phía xưởng vào chỉ số tin cậy của xưởng; điểm chủ xe không đổi (AC-BK01-08).

## 7.3 Response `200`

`{ "data": { "bookingId": "…", "status": "CANCELLED", "replacementHeld": true } }` — không trả chi tiết phương án cho xưởng.

---

# 8. Jobs

## 8.1 JOB-BK01-01 — `scheduler.proactive_due_scan`

| | |
|---|---|
| Lịch | Mỗi giờ (Celery beat) |
| Chọn | Xe có `due_status = DUE_SOON`, chủ xe `automation_level ∈ {HOLD, AUTO_BOOK}`, chưa có lịch mở, chưa có `scheduling_run` `DUE_JOB` cho cùng mốc trong 72 giờ |
| Làm | `SchedulerService.run(trigger = DUE_JOB, applyAutomation = true)` từng xe; lỗi một xe không dừng job |
| Kết quả | Có giữ ⇒ thông báo "Lịch giữ sẵn" (link `/bookings/{id}/proactive`); `NO_OPTION` ⇒ thông báo "Chưa tìm được lịch phù hợp" + nút xem gợi ý nới |

## 8.2 JOB-BK01-02 — `scheduler.expire_proactive_holds`

| | |
|---|---|
| Lịch | Mỗi 5 phút |
| Nhắc | `proactive pending`, `hold_expires_at − now ≤ 2h`, chưa nhắc ⇒ thông báo một lần (ghi `booking_reminder` loại `PROACTIVE_HOLD_EXPIRING`) |
| Hết hạn | `hold_expires_at ≤ now` ⇒ `cancelled`, `reason = PROACTIVE_HOLD_EXPIRED`, `actor = system`; thông báo "Lịch giữ sẵn đã hết hạn" + "Tìm lại". Không tính điểm (AC-BK01-07) |

---

# 9. TOOL-BK01-01 — `find_schedule_options`

| | |
|---|---|
| File | `backend/src/agents/tools/scheduler_tools.py` |
| Args (LLM thấy) | `date_from?`, `date_to?`, `part_of_day?` (`MORNING`/`AFTERNOON`/`EVENING`), `workshop_hint?` (tên), `save_as_default?` |
| Danh tính | `user_id`, `user_vehicle_id`, `conversation_id` từ `RunnableConfig["configurable"]` |
| Xử lý | Đổi args thành `overrides` (giờ địa phương), `SchedulerService.run(trigger = CHAT, applyAutomation = true)` |
| Trả về LLM | `{ outcome, headline, options: [{rank, workshop_name, date, time, reasons[]}], held: bool, question?, relaxations? }` — chỉ để LLM diễn đạt |
| Gắn thẻ | `ChatService` gắn `card = { type: "SCHEDULE_OPTIONS", runId }` vào tin trợ lý (như us-061 `propose_booking`). Thẻ đọc phương án từ `scheduling_option`, không từ lời LLM (BR-BK01-15) |
| Prompt | "Không tự thêm, bớt hay sắp xếp lại phương án. Mọi lựa chọn chủ xe bấm trên thẻ." |

`HOOK` làm giàu thẻ khi trả `MessageDto`: gắn trạng thái hiện tại của từng phương án và booking đang giữ (giống us-061 HOOK-QB-01).

---

# 10. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | Body sai | tất cả |
| 404 | `OPTION_NOT_FOUND` / `BOOKING_NOT_FOUND` / `LOCATION_NOT_FOUND` / `CONSTRAINT_NOT_FOUND` | Không thuộc người gọi | |
| 409 | `VEHICLE_NOT_ACTIVE` | Xe không còn hiệu lực | BK01-05, 06 |
| 409 | `SCHEDULER_BUSY` | Lượt chạy khác của cùng xe đang chạy | BK01-05 |
| 409 | `OPTION_IN_PROGRESS` | Chọn cùng phương án song song | BK01-06 |
| 409 | `OPTION_INACTIVE` | Phương án đã `released` / `stale` | BK01-06 |
| 409 | `OPTION_SLOT_FULL` | Hết chỗ lúc chọn; `details.run` có phương án mới | BK01-06 |
| 409 | `NOT_PROACTIVE_HOLD` / `PROACTIVE_HOLD_EXPIRED` | | BK01-07, 08 |
| 409 | `INVALID_BOOKING_STATE` | Xưởng báo bận lịch đã bắt đầu / kết thúc | BK01-09 |
| 409 | `PROFILE_VERSION_CONFLICT` | | BK01-02 |
| 422 | `AUTO_BOOK_CONSENT_REQUIRED` / `WORKSHOP_INACTIVE` | | BK01-02 |
| 503 | `SCHEDULER_TIMEOUT` | Quá ngân sách, chưa có phương án | BK01-05 |
| 503 | `SERVICE_UNAVAILABLE` | Redis / khoá lỗi | BK01-05, 06 |

Lỗi module là `SchedulerError(code, message, details)` (`scheduler/errors.py`), đăng ký qua `_domain_error_response` để giữ `details`.

---

# 11. Performance & Observability

- AC-BK01-09: p90 ≤ 2 s với 20 xưởng, bán kính 10 km, 14 ngày. Ước tính: 3 truy vấn `open_slots` × 20 xưởng = 60 truy vấn; lọc xưởng theo bán kính bằng `geo_index` trước khi quét. Test hiệu năng giữ ngưỡng số câu SQL < 80.
- Log `scheduler.run` (`run_id`, `trigger`, `outcome`, `candidate_count`, `rejected_by`, `duration_ms`, `scorer_version`), `scheduler.hold`, `scheduler.option_selected`, `scheduler.proactive_expired`, `scheduler.workshop_unable`. Không log toạ độ, địa chỉ (NFR-09).
- Metric: `scheduler_run_duration_seconds{trigger}`, `scheduler_outcome_total{outcome}`, `scheduler_hold_conflict_total`.

---

# 12. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit (engine) | Property test ≥ 500 tổ hợp ngẫu nhiên (Hypothesis): 0 phương án vi phạm bán kính / khung rảnh / hạn chót / xưởng bị loại (AC-BK01-03) | +1 |
| Unit | Thứ tự tier 1 > 2 > 3; hoà điểm ⇒ sớm hơn rồi gần hơn (AC-BK01-01, 02) | +3 |
| Unit | Lý do chỉ từ yếu tố > 0, 1–3 lý do | +2 |
| Unit | Nới: chỉ cách cho ≥ 1 phương án, không vượt hạn chót, không tự áp (AC-BK01-04) | +3 |
| Unit | Mâu thuẫn xưởng yêu thích đóng mọi khung rảnh ⇒ `CONFLICT` | +1 |
| Unit | Override "chiều mai" thắng hồ sơ, hồ sơ không đổi (AC-BK01-10) | +1 |
| Service | Mức `HOLD` giữ chủ động `proactive = true`, `hold_expires_at` đúng; `SUGGEST` không giữ | +2 |
| Service | 20 yêu cầu song song giữ chỗ cuối ⇒ 1 thành công, 19 nhận phương án kế (AC-BK01-06, EF-BK01-01) | +1 |
| Service | Đổi xưởng: chỗ mới hết ⇒ lịch cũ nguyên (AC-BK01-05); thành công ⇒ cũ `cancelled` `RESCHEDULED_TO_OTHER_WORKSHOP`, một transaction | +2 |
| Service | Hết hạn giữ ⇒ `PROACTIVE_HOLD_EXPIRED`, BK-02 không tính điểm (AC-BK01-07) | +1 |
| Service | `cancel_unconfirmed` bỏ qua proactive; deadline từ `proactive_confirmed_at` | +2 |
| Service | Xưởng báo bận ⇒ phương án mới được giữ, chủ xe không bị tính điểm (AC-BK01-08) | +1 |
| Service | Bậc `RESTRICTED` hạ mức 3 về 2 (EDGE-BK01-08) | +1 |
| Service | `CONSENT_CALENDAR_SYNC` tắt ⇒ không đọc `calendar_busy_cache` (PL-01 AC-PL01-01) | +1 |
| Perf | 20 xưởng / 14 ngày < 80 câu SQL, < 2 s local | +1 |
| Agent | `find_schedule_options` gắn thẻ `SCHEDULE_OPTIONS`; LLM không có tool nào tạo booking | +2 |

Hạ tầng test: SQLite trong bộ nhớ + fakeredis như `tests/test_modules/test_booking_service.py`; thêm bảng mới vào `tests/_maintenance.TABLES`.

---

# 13. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
| `v0.2` | `2026-10-12` | API-BK01-09: `source = TECHNICIAN_ABSENCE` (WS-03) — loại cả ngày của xưởng, ưu tiên xưởng tương tự (PO chốt) |
