# API Technical Specification — Quyền riêng tư và sự đồng ý

> Backend cho Feature `FEAT-P2-PL01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](pl-01-phase2-spec.ff.md). **Entity:** [Entity Spec](pl-01-phase2-spec.entity.md) — `data_consent`, `data_consent_log`, `data_deletion_request`.
>
> **Tái dùng:** xác thực chủ xe `get_current_user_id` (Firebase), envelope lỗi chung ([platform/error-handling.md](../../platform/error-handling.md)), Redis (`infrastructure/redis`), Celery (`celery_tasks.py`), `PreferenceService` của `agent_memory` (chuyển sang đọc đồng ý qua `ConsentService`).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-PL01` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/privacy/` (mới) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-PL01-01` | `GET` | `/privacy/consents` | Trạng thái 5 công tắc + yêu cầu xoá đang chạy | UC-PL01-01 |
| `API-PL01-02` | `PUT` | `/privacy/consents/{consentCode}` | Bật / tắt một đồng ý (màn Quyền riêng tư hoặc hỏi trong luồng) | UC-PL01-02, UC-PL01-03, UC-PL01-05 |
| `API-PL01-03` | `POST` | `/privacy/consents/{consentCode}/deletion-requests` | Xoá dữ liệu liên quan | UC-PL01-04 |
| `API-PL01-04` | `GET` | `/privacy/consents/{consentCode}/deletion-requests/latest` | Theo dõi tiến độ xoá | UC-PL01-04 |
| `SVC-PL01-01` | Internal | `ConsentService.is_granted(user_id, code)` | Cổng duy nhất cho mọi tính năng | BR-PL01-03, BR-PL01-06 |
| `JOB-PL01-01` | Celery | `privacy.run_deletion_requests` | Xoá theo loại trong `DELETE_SLA_HOURS` | BR-PL01-03, EF-PL01-02 |
| `HOOK-PL01-01` | Internal | `on_consent_revoked(user_id, code)` | Dừng dùng ngay + dọn dữ liệu đệm | AF-PL01-01, AF-PL01-02 |

Log thay đổi chỉ vận hành đọc (FF §16), không có endpoint cho chủ xe; vận hành truy vấn DB qua công cụ nội bộ.

---

# 2. Authorization & Guards

1. Mọi `API-PL01-*`: chủ xe đăng nhập (`get_current_user_id`), tài khoản `ACTIVE`. Chỉ thao tác trên đồng ý của chính mình; không có tham số `userId`.
2. `consentCode` không thuộc enum ⇒ `404 CONSENT_NOT_FOUND`.
3. Chủ xưởng và KTV (WS-03) không gọi được (`403 FORBIDDEN`).

---

# 3. API-PL01-01 — `GET /privacy/consents`

## 3.1 Response `200`

```json
{
  "data": {
    "policyVersion": "2026-10",
    "items": [
      {
        "code": "CONSENT_LONG_TERM_MEMORY",
        "status": "GRANTED",
        "effective": true,
        "source": "USER",
        "updatedAt": "2026-10-12T02:10:00Z",
        "hasViewData": true,
        "deletion": { "requestId": "5b1e…", "status": "PENDING", "dueAt": "2026-10-13T02:11:00Z" }
      },
      { "code": "CONSENT_CALENDAR_SYNC", "status": "NOT_ASKED", "effective": false, "source": "DEFAULT", "updatedAt": null, "hasViewData": false, "deletion": null }
    ]
  }
}
```

| Field | Ý nghĩa |
|---|---|
| `status` | `NOT_ASKED` / `GRANTED` / `REVOKED` — giá trị đã lưu (không dòng ⇒ `NOT_ASKED`) |
| `effective` | Tính năng có được dùng dữ liệu không, sau khi áp mặc định (entity §4) |
| `source` | `USER` (chủ xe đã chọn) / `DEFAULT` (đang theo mặc định) |
| `hasViewData` | Có link "Xem dữ liệu" không: bộ nhớ → `/settings/memory` (PS-01), lịch → kết nối lịch (BK-04) |
| `deletion` | Yêu cầu xoá gần nhất còn `PENDING` / `RUNNING`, hoặc `null` |

Thứ tự `items` cố định như FF §3.1.

---

# 4. API-PL01-02 — `PUT /privacy/consents/{consentCode}`

## 4.1 Request

```json
{ "granted": false, "channel": "PRIVACY_SCREEN", "sourceFeature": null, "expectedVersion": 3 }
```

| Field | Type | Required | Validation |
|---|---|---|---|
| `granted` | `bool` | Yes | |
| `channel` | `enum` | Yes | `PRIVACY_SCREEN`, `IN_FLOW_PROMPT`, `FIRST_RUN_NOTICE` (chủ xe không gửi được `SYSTEM`, `ACCOUNT_DELETION`) |
| `sourceFeature` | `string` | No | Bắt buộc khi `channel = IN_FLOW_PROMPT`; một trong `BK-01`, `BK-04`, `BK-05`, `PS-01`, `PS-02`, `PS-04` |
| `expectedVersion` | `int` | No | Khi có và khác `data_consent.version` ⇒ `409 CONSENT_VERSION_CONFLICT` |

## 4.2 Processing

1. Guards §2. `FIRST_RUN_NOTICE` chỉ hợp lệ với `CONSENT_LONG_TERM_MEMORY` và `granted = true`; đã có dòng ⇒ trả trạng thái hiện tại, không ghi (BR-ENT-PL01-02).
2. `CONSENT_LOCATION` với `granted = true` chỉ ghi nhận ý định của chủ xe; frontend vẫn phải xin quyền trình duyệt. Bị trình duyệt từ chối thì frontend gọi lại với `granted = false`.
3. Một transaction: upsert `data_consent` (`version + 1`, `granted_at` / `revoked_at`), chèn `data_consent_log` (`old_status`, `new_status`, `channel`, `source_feature`, `policy_version`, `user_agent`). Không đổi giá trị ⇒ no-op, trả `200` với `changed: false` (BR-ENT-PL01-01).
4. `CONSENT_LONG_TERM_MEMORY`: ghi `agent_memory_setting.enabled` cùng transaction (BR-ENT-PL01-04).
5. Sau commit: xoá đệm Redis `consent:{userId}` (§8), gọi `HOOK-PL01-01` khi chuyển sang `revoked`.

## 4.3 `HOOK-PL01-01` — khi thu hồi

| Mã | Việc làm ngay (đồng bộ, sau commit) |
|---|---|
| `CONSENT_LONG_TERM_MEMORY` | Không gì thêm: agent đọc `ConsentService` mỗi lượt nên lượt sau đã dừng đọc/ghi (Main Flow bước 2). Dữ liệu chỉ xoá khi chủ xe yêu cầu xoá |
| `CONSENT_CALENDAR_SYNC` | Xoá `calendar_busy_cache` của chủ xe; thu hồi token (`CalendarProvider.revoke`); đánh dấu `calendar_connection.status = revoked`. Sự kiện đã tạo giữ nguyên tới khi chủ xe chọn trong yêu cầu xoá (AF-PL01-01) |
| `CONSENT_AUTO_BOOKING` | `owner_scheduling_profile.automation_level` đang `AUTO_BOOK` ⇒ hạ về `HOLD`. Lịch đã tự đặt giữ nguyên (AF-PL01-02) |
| `CONSENT_LOCATION` | Bộ lập lịch dùng khu vực thay toạ độ ở lần gọi sau (BR-PL01-05) |
| `CONSENT_PERSONALIZATION_DATA` | Dừng ghi tín hiệu PS-02 / PS-03; gợi ý không dùng cá nhân hoá ở lần gọi sau |

Lỗi trong hook (ví dụ thu hồi token thất bại) không làm hỏng `PUT`: đồng ý đã `revoked` nên không tính năng nào dùng dữ liệu; hook ghi job thử lại `privacy.retry_revoke_hook`.

## 4.4 Response `200`

```json
{ "data": { "code": "CONSENT_CALENDAR_SYNC", "status": "REVOKED", "effective": false, "version": 4, "changed": true } }
```

---

# 5. API-PL01-03 — `POST /privacy/consents/{consentCode}/deletion-requests`

## 5.1 Request

```json
{ "options": { "keepCreatedEvents": true } }
```

`options.keepCreatedEvents` chỉ hợp lệ với `CONSENT_CALENDAR_SYNC` (mặc định `true`); mã khác gửi `options` không rỗng ⇒ `400 INVALID_REQUEST`.

## 5.2 Processing

1. Guards §2.
2. Đồng ý đang `granted` ⇒ tự chuyển `revoked` trước (log `channel = PRIVACY_SCREEN`), vì không thể vừa dùng vừa xoá. Màn xác nhận đã nói rõ điều này (SCR-PL01-03).
3. Đã có yêu cầu `pending` / `running` cùng mã ⇒ trả yêu cầu đó (`200`, idempotent theo index `ux_data_deletion_open`).
4. Chèn `data_deletion_request` (`due_at = now + DELETE_SLA_HOURS`), đẩy `JOB-PL01-01` ngay (không đợi lịch quét).

## 5.3 Response `202`

```json
{ "data": { "requestId": "5b1e…", "code": "CONSENT_LONG_TERM_MEMORY", "status": "PENDING", "dueAt": "2026-10-13T02:11:00Z" } }
```

---

# 6. API-PL01-04 — `GET …/deletion-requests/latest`

Trả yêu cầu gần nhất của mã đó (`200`, cùng shape §5.3 thêm `completedAt`), hoặc `404 DELETION_REQUEST_NOT_FOUND`.

---

# 7. JOB-PL01-01 — `privacy.run_deletion_requests`

| | |
|---|---|
| Lịch | Celery beat mỗi 15 phút + chạy ngay khi có yêu cầu mới |
| Chọn | `status = pending` hoặc (`failed` và `attempts < 5`), `FOR UPDATE SKIP LOCKED` |
| Xử lý | `status = running` → gọi `DataEraser` theo mã (bảng ở entity §5.1). Mỗi tính năng đăng ký eraser của mình qua `register_eraser(code, fn)`; PL-01 không biết bảng của tính năng khác |
| Thành công | `done`, `completed_at`. Log `privacy.deletion.done` (`request_id`, `code`, `rows_deleted`) |
| Lỗi | `failed`, `attempts + 1`, `last_error` = tên lớp lỗi; backoff 5 → 15 → 45 phút |
| Quá hạn | `now > due_at` và chưa `done` ⇒ log `privacy.deletion.overdue` mức `ERROR` + cảnh báo Grafana (EF-PL01-02) |
| Vector | Mục nhớ có vector: xoá vector trước rồi xoá dòng, theo cách `MemoryCleanup` hiện có |

**Xoá tài khoản (EDGE-PL01-01):** luồng xoá tài khoản tạo một yêu cầu cho **mỗi** mã (`channel = ACCOUNT_DELETION`) trước khi xoá `vehicle_user`; các bảng còn lại xoá theo cascade.

---

# 8. SVC-PL01-01 — `ConsentService`

```python
class ConsentService:
    def is_granted(self, user_id: int, code: ConsentCode) -> bool: ...
    def snapshot(self, user_id: int) -> dict[ConsentCode, bool]: ...
```

- Đọc theo thứ tự: đệm Redis `consent:{userId}` (hash, TTL 10 phút) → DB → áp mặc định `CONSENT_DEFAULTS`.
- **Lỗi bất kỳ** (Redis + DB đều lỗi, timeout 50 ms) ⇒ trả `False` cho mọi mã và log `privacy.consent.fail_closed` (BR-PL01-06, AC-PL01-04). Redis lỗi nhưng DB tốt ⇒ đọc DB.
- Mọi tính năng Phase 2 gọi `is_granted` ở **mỗi lần dùng** dữ liệu (không giữ kết quả quá một request / một lượt agent). Agent: `snapshot()` một lần đầu lượt, truyền vào `RunnableConfig["configurable"]["consents"]`.
- Mục tiêu p95 ≤ 20 ms (FF §18) khi đệm trúng.

---

# 9. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 400 | `INVALID_REQUEST` | Body sai, `channel` không hợp lệ, thiếu `sourceFeature`, `options` sai mã | PL01-02, PL01-03 |
| 401 | `UNAUTHORIZED` | Chưa đăng nhập | tất cả |
| 403 | `FORBIDDEN` | Không phải chủ xe | tất cả |
| 404 | `CONSENT_NOT_FOUND` | Mã không tồn tại | tất cả |
| 404 | `DELETION_REQUEST_NOT_FOUND` | Chưa từng yêu cầu xoá | PL01-04 |
| 409 | `CONSENT_VERSION_CONFLICT` | `expectedVersion` lệch (hai tab cùng đổi) | PL01-02 |
| 422 | `FIRST_RUN_NOTICE_NOT_ALLOWED` | `FIRST_RUN_NOTICE` với mã khác hoặc `granted = false` | PL01-02 |
| 503 | `SERVICE_UNAVAILABLE` | DB không ghi được | PL01-02, PL01-03 |

---

# 10. Observability

- Log: `privacy.consent.changed` (`code`, `old`, `new`, `channel`, `source_feature`), `privacy.deletion.requested`, `privacy.deletion.done`, `privacy.deletion.overdue`, `privacy.consent.fail_closed`. Không log nội dung dữ liệu bị xoá.
- Metric (Grafana qua OTel Collector, như stack hiện có): `consent_change_total{code,new_status,channel}`, `deletion_duration_seconds{code}`, `deletion_overdue_total`.
- Chỉ số M-12 của PRD (tỉ lệ tắt đồng ý) lấy từ `data_consent_log` (PL-03).

---

# 11. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `ConsentService`: mặc định theo entity §4 khi không có dòng; `granted`/`revoked` đã lưu thắng mặc định | +5 |
| Unit | `ConsentService` fail-closed: DB lỗi ⇒ `False` mọi mã (AC-PL01-04) | +1 |
| Service | `PUT` ghi đúng một dòng log; ghi lặp cùng giá trị không thêm log (AC-PL01-03) | +2 |
| Service | `PUT` xoá đệm; lần `is_granted` kế tiếp thấy giá trị mới | +1 |
| Service | Thu hồi `CONSENT_CALENDAR_SYNC` ⇒ `calendar_busy_cache` trống, bộ lập lịch kế tiếp không đọc bận/rảnh (AC-PL01-01) | +1 |
| Service | Thu hồi `CONSENT_AUTO_BOOKING` ⇒ mức tự động hạ về `HOLD`, lịch đã tự đặt giữ nguyên | +1 |
| Service | `FIRST_RUN_NOTICE` lần hai không đổi trạng thái đã tắt | +1 |
| Job | Yêu cầu xoá bộ nhớ ⇒ không còn `agent_user_memory` của chủ xe (AC-PL01-02) | +1 |
| Job | Eraser lỗi ⇒ `failed`, thử lại, quá `due_at` ⇒ log `overdue` | +2 |
| API | Yêu cầu xoá lặp trả cùng `requestId` | +1 |
| API | Đồng bộ `agent_memory_setting.enabled` khi đổi bộ nhớ (BR-ENT-PL01-04) | +1 |

---

# 12. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
