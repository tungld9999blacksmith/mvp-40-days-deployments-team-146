# API Technical Specification — Widget lịch

> Backend cho Feature `FEAT-P2-BK04`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](bk-04-phase2-spec.ff.md). **Entity:** [Entity Spec](bk-04-phase2-spec.entity.md).
>
> **Tái dùng:** `get_maintenance_status` (cửa sổ đến hạn, F3), `GET /bookings` (Lịch của tôi), `BookingService.open_slots` / `CapacityService.occupancy` (WS-02), `SchedulerService.run` (BK-01, `trigger = WIDGET`), `GET /workshop-owner/capacity` (Board), `ConsentService` (PL-01), Celery. Google Calendar qua adapter mới `infrastructure/calendar/google.py` (port `CalendarProvider`).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-BK04` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/calendar/` (mới): `service.py`, `route.py`, `ics.py`, `jobs.py`; adapter `infrastructure/calendar/` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-BK04-01` | `GET` | `/calendar/overview?userVehicleId&from&to` | Dữ liệu widget: cửa sổ đến hạn, lịch hẹn, trạng thái kết nối | UC-BK04-01 |
| `API-BK04-02` | `GET` | `/calendar/busy?from&to` | Lớp ngày bận (tải nền) | UC-BK04-03, AC-BK04-04 |
| `API-BK04-03` | `GET` | `/calendar/days/{date}/slots?userVehicleId&workshopId?` | Khung còn chỗ của ngày (SCR-BK04-02) | UC-BK04-02 |
| `API-BK04-04` | `POST` | `/calendar/google/connect` | Bắt đầu OAuth (trả URL) | UC-BK04-03 |
| `API-BK04-05` | `GET` | `/calendar/google/callback` | Nhận mã OAuth, lưu token | UC-BK04-03 |
| `API-BK04-06` | `PUT` | `/calendar/connection` | Chọn lịch đọc bận/rảnh, bật/tắt quyền ghi | EDGE-BK04-02 |
| `API-BK04-07` | `DELETE` | `/calendar/connection` | Ngắt kết nối | — |
| `API-BK04-08` | `POST` | `/bookings/{bookingId}/calendar-event` | "Thêm vào lịch": Google hoặc `.ics` | UC-BK04-04 |
| `API-BK04-09` | `GET` | `/bookings/{bookingId}/calendar.ics` | Tải tệp `.ics` | AF-BK04-02 |
| `API-BK04-10` | `GET` | `/workshop-owner/calendar/week?start` | Lịch tuần của xưởng | UC-BK04-06 |
| `HOOK-BK04-01` | Internal | Booking đổi giờ / huỷ ⇒ đẩy cập nhật sự kiện | | UC-BK04-05, AC-BK04-03 |
| `JOB-BK04-01` | Celery | `calendar.purge_busy_cache` (mỗi giờ) | Xoá đệm quá 24 giờ | BR-BK04-07 |

---

# 2. Authorization & Guards

1. Chủ xe cho `API-BK04-01..09`; xe / booking thuộc chủ xe.
2. `API-BK04-02`, `04`, `05`, `06`: cần `CONSENT_CALENDAR_SYNC` hiệu lực ⇒ không thì `403 CONSENT_REQUIRED` (`details.code`). Frontend hỏi đồng ý trước (PL-01 `useConsentGate`).
3. `API-BK04-05`: xác thực bằng `state` (JWT ký, gắn `user_id`, `nonce`, hạn 10 phút, lưu `nonce` ở Redis một lần dùng) — callback từ Google không có bearer token.
4. `API-BK04-10`: chủ xưởng / KTV có quyền xem Board của xưởng.

---

# 3. API-BK04-01 — `GET /calendar/overview`

Query `from`, `to` (≤ 62 ngày; mặc định tháng hiện tại ± 7 ngày để nối liền, EDGE-BK04-03).

```json
{
  "data": {
    "today": "2026-10-12",
    "dueWindow": { "start": "2026-10-19", "end": "2026-10-31", "dueStatus": "DUE_SOON", "milestoneLabel": "24.000 km / 24 tháng" },
    "dueWindowUnavailableReason": null,
    "bookings": [ { "bookingId": "…", "bookingCode": "EVC-…", "date": "2026-10-24", "timeSlot": "08:00", "status": "CONFIRMED", "workshopName": "…", "proactive": false } ],
    "connection": { "status": "CONNECTED", "canWrite": false, "lastSyncedAt": "…" }
  }
}
```

- `dueWindow` (BR-BK04-01): `start` = ngày xe vào `DUE_SOON` (tính ngược bằng `due_soon_days` / `due_soon_km` + dự báo km của `maintenance_forecast` có sẵn); `end` = `next_milestone.due_date`. `OVERDUE` ⇒ `start` = ngày vào `DUE_SOON`, `end` = hôm nay, `dueStatus = OVERDUE`. `UNKNOWN` ⇒ `dueWindow = null`, `dueWindowUnavailableReason = unknown_reason` (EDGE-BK04-04).
- `bookings`: lịch không `cancelled` của chủ xe trong khoảng (gồm giữ chủ động BK-01).
- Không gọi Google trong API này (p90 ≤ 1 s, FF §18).

---

# 4. API-BK04-02 — `GET /calendar/busy`

1. Không kết nối / `revoked` ⇒ `200 { "status": "NOT_CONNECTED", "busy": [] }`.
2. Đệm còn hạn cho toàn khoảng ⇒ trả đệm.
3. Hết ⇒ gọi Google `freebusy.query` (`timeMin`, `timeMax`, `items = calendar_ids`, timeout 3 s). Ghi đè đệm khoảng đó (`expires_at = now + 24h`). Sự kiện cả ngày ⇒ `all_day = true`.
4. Google lỗi / token hết hạn: thử refresh một lần; `invalid_grant` ⇒ `status = revoked`, gọi `ConsentService` ghi `CONSENT_CALENDAR_SYNC = revoked` (`channel = SYSTEM`), xoá đệm (EF-BK04-02); lỗi khác ⇒ `status = error`. Trả `200 { "status": "ERROR", "busy": [] }` — không bao giờ làm hỏng widget (AC-BK04-04, EF-BK04-01).

```json
{ "data": { "status": "OK", "busy": [ { "start": "2026-10-24T01:00:00Z", "end": "2026-10-24T03:00:00Z", "allDay": false } ], "fetchedAt": "…" } }
```

---

# 5. API-BK04-03 — `GET /calendar/days/{date}/slots`

Gọi `SchedulerService.run(trigger = WIDGET, overrides = { availability: [cả ngày `date` trong giờ mở cửa], workshopId? }, applyAutomation = false)` (BR-BK04-03). Kết quả là `RunDto` của BK-01 (cùng shape, chọn bằng `API-BK01-06`).

- Không truyền `workshopId` ⇒ ưu tiên xưởng yêu thích (BK-01 tier 1/2).
- Ngày kín ⇒ BK-01 tự đưa phương án xưởng khác cùng ngày (AF-BK04-03).
- Thêm `busyWarning: true` khi ngày có khoảng bận (AF-BK04-01) — chỉ đọc đệm, không gọi Google.
- Ngày quá khứ ⇒ `422 DATE_IN_PAST`.

Số chỗ trên các phương án đến từ `open_slots` / WS-02 tại thời điểm gọi (AC-BK04-01).

---

# 6. Kết nối Google

## 6.1 API-BK04-04 — `POST /calendar/google/connect`

Body `{ "write": false }`. Trả `{ "authUrl": "https://accounts.google.com/o/oauth2/v2/auth?..." }` với:
- `scope`: `https://www.googleapis.com/auth/calendar.freebusy` (+ `https://www.googleapis.com/auth/calendar.events.owned` khi `write = true`) — phạm vi tối thiểu (FF §21).
- `access_type=offline`, `prompt=consent`, `state` §2.3, PKCE (`code_challenge` S256; `code_verifier` lưu Redis theo `nonce`).

## 6.2 API-BK04-05 — `GET /calendar/google/callback?code&state`

Kiểm `state` + `nonce` (một lần), đổi `code` lấy token, mã hoá lưu `calendar_connection` (`status = connected`, `scopes` theo Google trả về thực tế). Redirect `302` về `{APP_BASE_URL}/settings/calendar?connected=1` (lỗi ⇒ `?error=<code>`).

## 6.3 API-BK04-06 / 07

- `PUT /calendar/connection` `{ "calendarIds": ["primary", "work@…"], "write": true }`: `calendarIds` phải nằm trong `calendarList` của tài khoản (gọi Google một lần); `write = true` khi chưa có scope ⇒ trả `{ "reauthUrl": … }` (cần cấp thêm quyền).
- `DELETE /calendar/connection`: thu hồi token ở Google, xoá đệm, `status = revoked`. Không đổi đồng ý PL-01 (chủ xe có thể kết nối lại); sự kiện đã tạo giữ nguyên.

---

# 7. "Thêm vào lịch"

## 7.1 API-BK04-08 — `POST /bookings/{bookingId}/calendar-event`

Body `{ "target": "AUTO" | "GOOGLE" | "ICS" }`.

1. Booking phải `pending` / `confirmed` ⇒ không thì `409 INVALID_BOOKING_STATE`.
2. `AUTO`: có kết nối với `scopes ∋ events` ⇒ `GOOGLE`; ngược lại `ICS` (Q-BK04-01: mặc định `.ics`).
3. `GOOGLE`: đã có dòng `GOOGLE` ⇒ trả lại (idempotent). Chưa ⇒ `events.insert` nội dung entity §5, `iCalUID = ics_uid`; lưu `booking_calendar_event`.
4. `ICS`: upsert dòng `ICS`; trả `downloadUrl` (`API-BK04-09`).

Response `201`: `{ "data": { "kind": "GOOGLE", "status": "CREATED", "downloadUrl": null } }`.

## 7.2 API-BK04-09 — `GET /bookings/{bookingId}/calendar.ics`

`Content-Type: text/calendar; charset=utf-8`, `Content-Disposition: attachment; filename="evcare-{bookingCode}.ics"`. `METHOD:PUBLISH`, `UID = ics_uid`, `SEQUENCE = ics_sequence`, `STATUS:CANCELLED` khi lịch đã huỷ. Tạo bằng `ics.py` (chuỗi thuần, không thêm thư viện). Yêu cầu bearer token như các API chủ xe; frontend tải bằng `fetch` + blob.

## 7.3 HOOK-BK04-01 — đồng bộ thay đổi (UC-BK04-05)

Đăng ký sau commit của: đổi lịch (us-053, BK-01 đổi xưởng), huỷ (mọi lý do), `starts_at` đổi (HS-02 gộp việc). Đẩy job `calendar.push_event(booking_id)` (Celery, ngay):

| Dòng | Đổi giờ | Huỷ / bị thay |
|---|---|---|
| `GOOGLE` | `events.patch` (start, end, location); `status = updated` | `events.delete`; `status = deleted` |
| `ICS` | `ics_sequence + 1`; thông báo trong app "Lịch hẹn đã đổi, cập nhật lịch của bạn" + link tải tệp mới (AF-BK04-02) | `ics_sequence + 1`, tệp `STATUS:CANCELLED` + thông báo |

- Google trả `404 / 410` ⇒ `status = orphaned`, **không tạo lại** (EF-BK04-03).
- Booking mới thay booking cũ (BK-01 `replaced_booking_id`) ⇒ xoá sự kiện cũ; **không** tự tạo sự kiện cho booking mới (chủ xe bấm lại "Thêm vào lịch"), trừ khi chủ xe bật "Tự thêm lịch hẹn mới" (câu hỏi mở, chưa làm ở v0.1).
- Thử lại 3 lần (backoff 10 s, 30 s, 90 s); mục tiêu ≤ 1 phút (AC-BK04-03).

---

# 8. API-BK04-10 — `GET /workshop-owner/calendar/week?start=YYYY-MM-DD`

Dựng từ **cùng** nguồn với `GET /workshop-owner/capacity` (BR-BK04-05): 7 ngày từ `start`; mỗi ô `{ date, slot, remaining, total, full }` (`full` ⇒ "Hết chỗ"). Xưởng bật WS-02 ⇒ ô theo `SLOT_UNIT_MIN`. Không có dữ liệu bận/rảnh của khách (FF §16).

---

# 9. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 400 | `INVALID_RANGE` | `from > to` hoặc > 62 ngày | BK04-01, 02 |
| 403 | `CONSENT_REQUIRED` | Chưa đồng ý đồng bộ lịch | BK04-02, 04, 05, 06 |
| 409 | `INVALID_BOOKING_STATE` | Thêm lịch cho booking đã huỷ / xong | BK04-08 |
| 409 | `CALENDAR_NOT_CONNECTED` | `target = GOOGLE` khi chưa có quyền ghi | BK04-08 |
| 422 | `DATE_IN_PAST` | | BK04-03 |
| 502 | `CALENDAR_PROVIDER_ERROR` | Google lỗi khi tạo sự kiện | BK04-08 |

Lỗi Google ở API-BK04-02 **không** là mã lỗi (§4).

---

# 10. Observability & Security

- Log `calendar.busy_fetched` (`days`, `blocks`, `ms`), `calendar.provider_error` (`code`), `calendar.event_pushed` (`kind`, `op`, `lag_ms`). Không log token, không log khoảng bận cụ thể.
- Metric `calendar_push_lag_seconds` (p95 ≤ 60 s), `calendar_provider_errors_total{code}`.
- Kiểm thử dữ liệu (AC-BK04-02): test schema khẳng định `calendar_busy_cache` không có cột ngoài entity §3; adapter chỉ gọi `freebusy.query` để đọc.

---

# 11. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Cửa sổ đến hạn: `DUE_SOON`, `OVERDUE`, `UNKNOWN`, trải hai tháng | +4 |
| Unit | `ics.py`: UID ổn định, `SEQUENCE` tăng, `STATUS:CANCELLED`, không có VIN / biển số / giá | +3 |
| Service | Busy: đệm còn hạn không gọi Google; hết hạn gọi lại; `invalid_grant` ⇒ revoked + PL-01 revoked + đệm xoá | +3 |
| Service | Google lỗi ⇒ overview + slots vẫn hoạt động (AC-BK04-04) | +1 |
| Service | Đổi giờ ⇒ `events.patch` ≤ 1 phút (fake provider, AC-BK04-03); huỷ ⇒ delete; 410 ⇒ `orphaned`, không tạo lại | +3 |
| Service | Slots ngày D gọi BK-01 với ràng buộc ngày D; số chỗ khớp sức chứa (AC-BK04-01) | +1 |
| API | OAuth `state` dùng lại ⇒ từ chối | +1 |
| Job | Purge xoá mọi dòng quá 24 giờ | +1 |
| Data | Không cột nội dung sự kiện (AC-BK04-02) | +1 |

---

# 12. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
