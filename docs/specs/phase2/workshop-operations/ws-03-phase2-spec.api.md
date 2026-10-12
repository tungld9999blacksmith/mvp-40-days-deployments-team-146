# API Technical Specification — Tài khoản kỹ thuật viên và tự phân công

> Backend cho Feature `FEAT-P2-WS03`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ws-03-phase2-spec.ff.md). **Entity:** [Entity Spec](ws-03-phase2-spec.entity.md).
>
> **Tái dùng:** Firebase Auth (thêm provider **Email/Password** cho KTV; Admin SDK tạo / đổi mật khẩu / revoke như `workshop_owner_auth/revoker.py`), dependency chủ xưởng `get_current_workshop_owner`, Workshop Board (`workshop_board`), tiến độ 6 bước (us-057, `POST /workshop-owner/bookings/{id}/progress`), `BookingStateMachine` (hook khi `confirmed`), `CapacityService` (WS-02), `SchedulerService` / `API-BK01-09` (xưởng báo không phục vụ được).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-WS03` |
| Version | `v0.2` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/technician/` (mới): `auth.py`, `dependency.py` (`WorkshopActor`), `service.py`, `assignment.py`, `route_owner.py`, `route_technician.py`, `audit.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-WS03-01` | `GET` | `/workshop-owner/technicians` | Danh sách KTV | SCR-WS03-01 |
| `API-WS03-02` | `POST` | `/workshop-owner/technicians` | Tạo tài khoản (tên đăng nhập + mật khẩu tạm) | UC-WS03-01, BR-WS03-01 |
| `API-WS03-03` | `PATCH` | `/workshop-owner/technicians/{technicianId}` | Tên, kỹ năng, lịch tuần, quyền | BR-WS03-02, 03 |
| `API-WS03-04` | `POST` | `/workshop-owner/technicians/{technicianId}/reset-password` | Đặt lại mật khẩu tạm | UC-WS03-07, EF-WS03-01 |
| `API-WS03-05` | `POST` | `/workshop-owner/technicians/{technicianId}/disable` · `/enable` | Vô hiệu / bật lại | UC-WS03-06 |
| `API-WS03-06` | `POST` / `DELETE` | `/workshop-owner/technicians/{technicianId}/absences[/{date}]` | Nghỉ (đột xuất / kế hoạch) | UC-WS03-05 |
| `API-WS03-07` | `PUT` | `/workshop-owner/bookings/{bookingId}/assignment` | Phân công tay | UC-WS03-04 |
| `API-WS03-08` | `POST` | `/technician-auth/session` | KTV lấy phiên sau khi đăng nhập Firebase | UC-WS03-02 |
| `API-WS03-13` | `POST` | `/technician-auth/password` | Đổi mật khẩu (bắt buộc lần đầu) | UC-WS03-02, BR-WS03-08 |
| `API-WS03-09` | `GET` | `/technician/me` | Hồ sơ + quyền | — |
| `API-WS03-10` | `GET` | `/technician/jobs?date` | Việc của tôi | SCR-WS03-02 |
| `API-WS03-11` | `GET` | `/technician/jobs/{bookingId}` | Chi tiết việc | SCR-WS03-02 |
| `API-WS03-12` | `POST` | `/technician/jobs/{bookingId}/progress` | Cập nhật tiến độ | BR-WS03-03 |
| `HOOK-WS03-01` | Internal | `on_booking_confirmed` ⇒ tự phân công | | UC-WS03-03, BR-WS03-04 |
| `HOOK-WS03-02` | Internal | Ghi `technician_audit_log` cho mọi request ghi của KTV | | BR-WS03-06 |

`GET /workshop-owner/bookings` (Board) thêm `assignment` cho mỗi lịch (SCR-WS03-03).

---

# 2. Authorization & Guards

## 2.1 `WorkshopActor`

Dependency mới `get_workshop_actor()` trả `WorkshopActor(kind = OWNER | TECHNICIAN, workshop_id, owner_id?, technician_id?, permissions)`:
- Token Firebase của chủ xưởng ⇒ `OWNER`, mọi quyền của xưởng mình.
- Token của KTV (claim `role = technician`) `active` ⇒ `TECHNICIAN`, quyền theo `technician.permissions`. KTV `disabled` ⇒ `401 TECHNICIAN_INACTIVE` **ngay** ở request kế tiếp (UC-WS03-06): trạng thái đọc mỗi request (đệm Redis 30 s, xoá khi đổi).
- KTV `must_change_password = true` ⇒ mọi route trừ `API-WS03-08/09/13` trả `403 PASSWORD_CHANGE_REQUIRED` (AC-WS03-05).
- Dependency chủ xe (`vehicle_owner_onboarding`) và chủ xưởng từ chối token có claim `role = technician` (`403 FORBIDDEN`), để tài khoản KTV không tự tạo hồ sơ chủ xe.
- Endpoint `/workshop-owner/*` hiện có giữ `get_current_workshop_owner` (chỉ chủ xưởng). Endpoint dùng chung chuyển sang `require(permission)`.

## 2.2 Phạm vi dữ liệu (AC-WS03-01)

Mọi truy vấn của `TECHNICIAN` lọc `workshop_id = actor.workshop_id` **và** (có `VIEW_ALL_BOOKINGS` hoặc `booking_assignment.technician_id = actor.technician_id AND status = 'active'`). Truy cập lịch ngoài phạm vi ⇒ `404 BOOKING_NOT_FOUND` (không lộ tồn tại). Test phân quyền tham số hoá cho mọi route KTV.

---

# 3. Quản lý KTV (chủ xưởng)

## 3.1 API-WS03-02 — tạo tài khoản

```json
{ "username": "xuongminhphat.an", "temporaryPassword": null, "displayName": "An", "skills": ["PERIODIC_MAINTENANCE", "TIRE", "BRAKE"],
  "weeklySchedule": [1,2,3,4,5,6], "permissions": ["VIEW_ASSIGNED","UPDATE_PROGRESS","DRAFT_EXTRA","USE_ASSISTANT"] }
```

1. `username` chữ thường, `^[a-z0-9._]{3,30}$`; trùng ⇒ `409 USERNAME_TAKEN` (`details.suggestions`, EF-WS03-03). Frontend gợi ý tiền tố theo slug xưởng.
2. `temporaryPassword` rỗng ⇒ server sinh 10 ký tự (chữ + số, bỏ ký tự dễ nhầm `0O1lI`); chủ xưởng tự nhập ⇒ ≥ 8 ký tự, có chữ và số.
3. Firebase Admin `create_user(email = "{username}@ktv.evcare.internal", password = temp, email_verified = true)`, custom claim `role = technician`, `workshopId`. Lỗi Firebase ⇒ không tạo dòng DB (`502 AUTH_PROVIDER_ERROR`).
4. Tạo `technician` `pending_activation`, `must_change_password = true`, `temp_password_expires_at = now + 7d`; log `ACCOUNT_CREATED`.
5. Response `201` `{ technician: TechnicianDto, temporaryPassword }` — mật khẩu tạm **chỉ trả lần này**, không lưu, không log, không gửi email. Chủ xưởng đưa trực tiếp cho KTV.

## 3.2 API-WS03-03 / 05 / 06

- **PATCH**: `displayName`, `skills[]`, `weeklySchedule[]` (1–7), `permissions[]` (chỉ trong danh sách cấp được, entity §2.1). Đổi kỹ năng / lịch ⇒ không đổi phân công cũ; lịch mới dùng giá trị mới.
- **Reset password** (`API-WS03-04`, UC-WS03-07): KTV xưởng mình, không `disabled`. Firebase `update_user(password = temp mới)` + revoke refresh token ⇒ KTV bị đăng xuất mọi thiết bị; `pending_activation`, `must_change_password = true`, `temp_password_expires_at = now + 7d`; log `PASSWORD_RESET`. Response `{ temporaryPassword }` (một lần).
- **Disable**: `status = disabled`, Firebase `update_user(disabled = true)` + revoke refresh token; các phân công `active` của lịch **chưa bắt đầu** ⇒ `released (DISABLED)` + tự phân công lại (HOOK-WS03-01); lịch đang `checked_in` / `in_progress` giữ nguyên trạng thái, phân công `released`, Board gắn "Cần chọn KTV" (EDGE-WS03-02).
- **Enable**: `disabled` ⇒ Firebase `disabled = false`; trạng thái về `pending_activation` nếu `must_change_password` còn `true`, ngược lại `active`. Log `ENABLED`.
- **Absence** `POST { "date": "2026-10-12", "kind": "SUDDEN", "note": "…" }` — §5.

## 3.3 API-WS03-07 — phân công tay

`{ "technicianId": "…" }` hoặc `null` (bỏ phân công). KTV phải `active`, làm ngày đó, không trùng khoảng với phân công khác (WS-02 `starts_at/ends_at`) ⇒ không thì `409 TECHNICIAN_UNAVAILABLE` (`details.reason`: `NOT_WORKING`, `OVERLAP`). Thiếu kỹ năng ⇒ vẫn cho (chủ xưởng quyết định) nhưng trả `warnings: ["MISSING_SKILL"]`. Một transaction: `released (REASSIGNED)` cũ + chèn `MANUAL`. Thông báo hai KTV (UC-WS03-04).

## 3.4 `TechnicianDto`

`{ technicianId, username, displayName, status, mustChangePassword, tempPasswordExpiresAt, skills[], weeklySchedule[], permissions[], absences: [{date, kind}], todayLoad: { bookings, minutes } }`.

---

# 4. Đăng nhập và đổi mật khẩu KTV

## 4.1 API-WS03-08 — `POST /technician-auth/session`

Frontend đăng nhập Firebase `signInWithEmailAndPassword("{username}@ktv.evcare.internal", password)` (người dùng chỉ thấy ô "Tên đăng nhập"), rồi gọi endpoint này với `Authorization: Bearer <Firebase ID token>`:

1. Xác minh token; claim `role = technician`; tìm `technician` theo `firebase_uid`. Không có ⇒ `401 UNAUTHORIZED`.
2. `disabled` ⇒ `401 TECHNICIAN_INACTIVE`.
3. `must_change_password` và `temp_password_expires_at < now` ⇒ `401 TEMP_PASSWORD_EXPIRED` "Mật khẩu tạm đã hết hạn, nhờ chủ xưởng đặt lại" (EF-WS03-01).
4. Response `{ technician: TechnicianDto, workshop: { id, name }, mustChangePassword }`. Log `LOGIN`.

Sai mật khẩu do Firebase trả (`auth/invalid-credential`); sai nhiều lần ⇒ Firebase tạm chặn (`auth/too-many-requests`, EF-WS03-04). Backend không nhận mật khẩu ở bước này.

## 4.2 API-WS03-13 — `POST /technician-auth/password`

`{ "newPassword": "…" }`, token KTV có `auth_time` ≤ 5 phút (vừa đăng nhập; quá ⇒ `401 REAUTH_REQUIRED`).

1. Mật khẩu mới ≥ 8 ký tự, có chữ và số, khác tên đăng nhập ⇒ không thì `400 WEAK_PASSWORD`.
2. Firebase `update_user(password)` + revoke refresh token (phiên cũ, kể cả phiên dùng mật khẩu tạm, hết hiệu lực).
3. `must_change_password = false`, `temp_password_expires_at = NULL`, `password_changed_at = now`; `pending_activation` ⇒ `active`, `activated_at` (lần đầu). Log `PASSWORD_CHANGED`.
4. `200`; frontend đăng nhập lại bằng mật khẩu mới.

KTV `active` cũng dùng endpoint này để tự đổi mật khẩu bất kỳ lúc nào.

---

# 5. KTV nghỉ đột xuất (UC-WS03-05, BR-WS03-05)

`POST …/absences` với `date = hôm nay` hoặc ngày tương lai:

1. Chèn `technician_absence` ⇒ `capacity_base` ngày đó giảm 1 **ngay** (xoá đệm sức chứa của xưởng / ngày; AC-WS03-02).
2. Phân công `active` của KTV trong ngày (lịch chưa kết thúc) ⇒ `released (ABSENCE)`; chạy `assign()` (§6) cho từng lịch theo `starts_at`.
3. Sau phân lại, kiểm sức chứa từng đơn vị (WS-02 `occupancy` với `capacity_base` mới). Đơn vị âm ⇒ chọn lịch phải dời: lịch **chưa phân công được** và chồng đơn vị âm, ưu tiên lịch được tạo **muộn nhất** trước. Mỗi lịch ⇒ gọi `API-BK01-09` nội bộ (`reason = STAFF`, `source = TECHNICIAN_ABSENCE`, actor = chủ xưởng đã đánh dấu nghỉ). BK-01 báo chủ xe và đề xuất **xưởng phù hợp hoặc tương tự** (BK-01 API §7.2: loại xưởng này trong ngày nghỉ, ưu tiên xưởng tương tự gần xưởng cũ), giữ chỗ phương án đầu.
4. Response `{ "reassigned": 3, "unassigned": 1, "movedToAlternatives": 1, "bookingIds": […] }`; thông báo chủ xưởng tóm tắt.

> **PO chốt 2026-10-12:** KTV nghỉ đột xuất làm xưởng không đủ người ⇒ báo chủ xe và đề xuất xưởng phù hợp / tương tự (như trên). Thao tác giảm `total_technicians` / khoá chỗ thủ công của WS-02 (EF-WS02-03) vẫn chỉ cảnh báo, vì đó là chủ xưởng tự chỉnh cấu hình; chủ xưởng dùng nút "Không phục vụ được" cho từng lịch.

---

# 6. HOOK-WS03-01 — tự phân công

`assign(booking)` gọi khi booking chuyển `confirmed` (hook trong `BookingStateMachine.transition`, sau commit, Celery task để không chậm luồng xác nhận) và khi phân lại:

1. Xưởng không có KTV `active` hoặc lịch đã có phân công `MANUAL` còn hiệu lực ⇒ bỏ qua.
2. Ứng viên: KTV làm ngày đó (entity §4), đủ kỹ năng (entity §3), không có phân công `active` chồng `[starts_at, ends_at)`.
3. Chọn ít tải nhất: `Σ duration_min` phân công trong ngày; hoà ⇒ ít lịch hơn ⇒ `technician_id` nhỏ hơn (ổn định, test được).
4. Không có ⇒ không phân công, Board nhãn "Chưa phân công", thông báo chủ xưởng (EF-WS03-02).
5. Khoá Redis `assign:{workshopId}:{date}` để hai lịch xác nhận cùng lúc không gán chồng.
6. Thông báo KTV được giao (Workshop Portal + push nếu có).

---

# 7. Việc của tôi (KTV)

## 7.1 API-WS03-10 — `GET /technician/jobs?date=YYYY-MM-DD`

```json
{ "data": { "date": "2026-10-12", "jobs": [
  { "bookingId": "…", "bookingCode": "EVC-…", "startsAt": "…", "endsAt": "…", "status": "CONFIRMED",
    "vehicle": { "modelName": "VF 8", "licensePlateMasked": "30A-***.45" },
    "items": [ { "itemName": "Bảo dưỡng 24.000 km", "category": "PERIODIC_MAINTENANCE" } ],
    "progress": { "stage": null }, "hasPendingExtra": false } ] } }
```

Không có số điện thoại / email chủ xe trong DTO KTV (liên lạc qua MC-01 khi bật). Mục tiêu ≤ 1 s trên 4G: ≤ 3 truy vấn, payload < 30 KB.

## 7.2 API-WS03-11 / 12

- Chi tiết: ghi chú của chủ xe về xe, tóm tắt lịch sử gần nhất (dùng chung với TA-01), danh sách hạng mục (`booking_line`) **không kèm giá** — KTV không xem doanh thu (BR-WS03-03).
- Tiến độ: cùng logic `POST /workshop-owner/bookings/{id}/progress` (us-057), actor `technician`; cần `UPDATE_PROGRESS` + lịch được giao.

---

# 8. HOOK-WS03-02 — log

Middleware cho router `/technician/*` và mọi endpoint dùng chung khi `actor.kind = TECHNICIAN`: sau response 2xx của phương thức ghi, chèn `technician_audit_log` (`action` theo route, `object_type/id` theo path) (AC-WS03-04). Lỗi ghi log ⇒ log lỗi, không làm hỏng request.

---

# 9. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 401 | `TECHNICIAN_INACTIVE` | KTV bị vô hiệu / hết hạn |
| 403 | `PERMISSION_DENIED` | Thiếu quyền (`details.permission`) |
| 400 | `WEAK_PASSWORD` | Mật khẩu mới không đạt quy tắc |
| 401 | `TEMP_PASSWORD_EXPIRED` | Mật khẩu tạm quá 7 ngày (EF-WS03-01) |
| 401 | `REAUTH_REQUIRED` | Đổi mật khẩu với phiên đăng nhập cũ hơn 5 phút |
| 403 | `PASSWORD_CHANGE_REQUIRED` | Chưa đổi mật khẩu lần đầu (AC-WS03-05) |
| 404 | `TECHNICIAN_NOT_FOUND` / `BOOKING_NOT_FOUND` | Ngoài phạm vi |
| 409 | `USERNAME_TAKEN` | Tên đăng nhập đã có (EF-WS03-03) |
| 409 | `TECHNICIAN_UNAVAILABLE` | Phân công tay không hợp lệ |
| 502 | `AUTH_PROVIDER_ERROR` | Firebase lỗi khi tạo / đặt lại |

---

# 10. Observability

Log `technician.created`, `technician.password_reset`, `technician.activated`, `technician.disabled`, `assignment.auto` (`candidates`, `chosen`, `ms`), `assignment.none`, `absence.sudden` (`reassigned`, `moved`). Sự kiện PL-03: `technician_assistant_used` (TA-01), dữ liệu phân công cho M-10.

---

# 11. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Đủ kỹ năng = tập con; `QUICK_CHECK` cần `GENERAL_CHECK` | +3 |
| Unit | Chọn ít tải; hoà ổn định | +2 |
| Service | Tự phân công chỉ KTV đủ kỹ năng (AC-WS03-03); không ai ⇒ "Chưa phân công" | +2 |
| Service | Phân công tay không bị tự đổi (AF-WS03-02) | +1 |
| Service | Nghỉ đột xuất ⇒ sức chứa giảm ngay (AC-WS03-02), phân lại, thiếu ⇒ BK-01 AF-08 đề xuất xưởng khác, chủ xe nhận thông báo | +3 |
| Service | Vô hiệu ⇒ request kế tiếp `401`; lịch đang làm giữ nguyên (EDGE-WS03-02) | +2 |
| Service | Không có KTV `active` ⇒ sức chứa dùng `total_technicians` (EDGE-WS03-01) | +1 |
| Auth | Tạo: tên trùng ⇒ `409`; mật khẩu tạm chỉ có trong response tạo, không có trong log | +2 |
| Auth | `pending_activation` gọi `/technician/jobs` ⇒ `403 PASSWORD_CHANGE_REQUIRED`; đổi xong ⇒ `active` (AC-WS03-05) | +2 |
| Auth | Mật khẩu tạm quá hạn ⇒ `401`; đặt lại ⇒ phiên cũ bị revoke | +2 |
| Auth | Token KTV gọi API chủ xe / chủ xưởng ⇒ `403` | +1 |
| Security | KTV xưởng A gọi mọi route với lịch xưởng B ⇒ `404` (AC-WS03-01) | +1 (tham số hoá) |
| Audit | Mọi request ghi của KTV có log (AC-WS03-04) | +1 |

---

# 12. Open Questions

| ID | Câu hỏi | Đề xuất |
|---|---|---|
| `Q-API-WS03-02` | Thêm luật WS-01 "Không có KTV đủ kỹ năng ⇒ duyệt tay" (EF-WS03-02)? | Đưa vào WS-01 v0.2 nếu PO đồng ý |

---

# 13. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
| `v0.2` | `2026-10-12` | PO chốt: tài khoản tên đăng nhập + mật khẩu do xưởng tạo, đổi mật khẩu lần đầu (§3, §4); nghỉ đột xuất ⇒ báo chủ xe + đề xuất xưởng phù hợp / tương tự (§5) |
