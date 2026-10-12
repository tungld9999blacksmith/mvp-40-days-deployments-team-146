# Entity Specification — Quyền riêng tư và sự đồng ý

> Entity cho Feature `FEAT-P2-PL01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](pl-01-phase2-spec.ff.md). **API:** [API Spec](pl-01-phase2-spec.api.md).
>
> **Nguyên tắc:** trạng thái đồng ý hiện tại nằm ở một bảng (đọc nhanh, một dòng mỗi chủ xe × mã đồng ý); lịch sử thay đổi nằm ở bảng log chỉ thêm. Mọi tính năng Phase 2 đọc qua `ConsentService`, không đọc bảng trực tiếp.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-PL01` — PL-01 |
| Version | `v0.2` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [pl-01-phase2-spec.ff.md](pl-01-phase2-spec.ff.md) |
| Related API | [pl-01-phase2-spec.api.md](pl-01-phase2-spec.api.md) |
| Related FE | [pl-01-phase2-spec.fe.md](pl-01-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-PL01-01` | `DataConsent` | `data_consent` | **Mới** | Bảng + enum `data_consent_code_enum`, `data_consent_status_enum` |
| `ENT-PL01-02` | `DataConsentLog` | `data_consent_log` | **Mới** | Bảng chỉ thêm |
| `ENT-PL01-03` | `DataDeletionRequest` | `data_deletion_request` | **Mới** | Bảng + enum trạng thái |
| `ENT-006` | `UserConsent` | `user_consent` | Có sẵn — không đổi | Đồng ý điều khoản lúc onboarding (sprint-1); **không** dùng cho PL-01 |
| — | `AgentMemorySetting` | `agent_memory_setting` | Có sẵn — không đổi cột | Ghi đồng bộ khi `CONSENT_LONG_TERM_MEMORY` đổi (§5) |

**Tên bảng:** FF §14 gọi là `user_consent` / `user_consent_log`. Tên `user_consent` đã được ENT-006 dùng (log đồng ý điều khoản khi onboarding, chỉ thêm, không có trạng thái hiện tại), nên Phase 2 dùng `data_consent` / `data_consent_log` để không đụng bảng MVP (**PO chốt 2026-10-12**).

---

# 2. `data_consent` (ENT-PL01-01)

Một dòng cho mỗi (chủ xe, mã đồng ý) đã từng được hỏi. Không có dòng ⇒ `not_asked`.

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `user_id` | `bigint` | No | — | PK (1/2), FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `consent_code` | `data_consent_code_enum` | No | — | PK (2/2). Giá trị §2.1 |
| `status` | `data_consent_status_enum` | No | — | `granted`, `revoked` |
| `policy_version` | `varchar(20)` | No | — | Phiên bản văn bản giải thích lúc chủ xe đổi (config `PRIVACY_POLICY_VERSION`) |
| `granted_at` | `timestamptz` | Yes | `NULL` | Lần bật gần nhất |
| `revoked_at` | `timestamptz` | Yes | `NULL` | Lần tắt gần nhất |
| `version` | `integer` | No | `1` | Khoá lạc quan, tăng mỗi lần đổi |
| `updated_at` | `timestamptz` | No | `now()` | `onupdate` |

## 2.1 Enum

```sql
CREATE TYPE data_consent_code_enum AS ENUM (
  'CONSENT_LONG_TERM_MEMORY',
  'CONSENT_CALENDAR_SYNC',
  'CONSENT_LOCATION',
  'CONSENT_PERSONALIZATION_DATA',
  'CONSENT_AUTO_BOOKING'
);
CREATE TYPE data_consent_status_enum AS ENUM ('granted', 'revoked');
```

`not_asked` không lưu (không có dòng). Mặc định "Bật" của BR-PL01-02 **không** ghi sẵn dòng `granted`: `ConsentService` trả trạng thái hiệu lực theo bảng mặc định §4 và chỉ ghi dòng khi chủ xe thao tác hoặc khi thông báo lần đầu được hiển thị (§4, BR-ENT-PL01-02).

## 2.2 Constraints & Indexes

```sql
ALTER TABLE data_consent ADD PRIMARY KEY (user_id, consent_code);
ALTER TABLE data_consent ADD CONSTRAINT ck_data_consent_times
  CHECK ((status = 'granted' AND granted_at IS NOT NULL)
      OR (status = 'revoked' AND revoked_at IS NOT NULL));
```

---

# 3. `data_consent_log` (ENT-PL01-02)

Chỉ thêm, không sửa, không xoá (trừ khi xoá tài khoản — cascade).

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `consent_code` | `data_consent_code_enum` | No | — | |
| `old_status` | `varchar(16)` | No | — | `not_asked`, `granted`, `revoked` |
| `new_status` | `varchar(16)` | No | — | `granted`, `revoked` |
| `channel` | `varchar(24)` | No | — | `PRIVACY_SCREEN`, `IN_FLOW_PROMPT`, `FIRST_RUN_NOTICE`, `ACCOUNT_DELETION`, `SYSTEM` |
| `source_feature` | `varchar(16)` | Yes | `NULL` | Mã tính năng hỏi trong luồng (`BK-04`, `BK-05`…) khi `channel = IN_FLOW_PROMPT` |
| `policy_version` | `varchar(20)` | No | — | |
| `user_agent` | `varchar(512)` | Yes | `NULL` | Cắt 512 ký tự. Không lưu IP |
| `created_at` | `timestamptz` | No | `now()` | |

```sql
CREATE INDEX ix_data_consent_log_user ON data_consent_log (user_id, created_at DESC);
ALTER TABLE data_consent_log ADD CONSTRAINT ck_data_consent_log_channel
  CHECK (channel IN ('PRIVACY_SCREEN','IN_FLOW_PROMPT','FIRST_RUN_NOTICE','ACCOUNT_DELETION','SYSTEM'));
```

---

# 4. Trạng thái hiệu lực và mặc định

| Mã | Không có dòng (`not_asked`) ⇒ hiệu lực | Ghi chú |
|---|---|---|
| `CONSENT_LONG_TERM_MEMORY` | `granted` **sau khi** đã hiện thông báo lần đầu; trước đó `not_asked` (không dùng) | Thông báo lần đầu ghi dòng `granted`, `channel = FIRST_RUN_NOTICE` |
| `CONSENT_CALENDAR_SYNC` | `revoked` (không dùng) | Hỏi trong luồng ở BK-04 |
| `CONSENT_LOCATION` | `not_asked` (không dùng) | Còn phụ thuộc quyền trình duyệt; xem API §4 |
| `CONSENT_PERSONALIZATION_DATA` | `granted` | Mặc định bật (P2Q-11) |
| `CONSENT_AUTO_BOOKING` | `revoked` (không dùng) | Chỉ bật được bằng thao tác rõ ràng |

Bảng mặc định là config `CONSENT_DEFAULTS` (chờ P2Q-11), không viết cứng trong code nghiệp vụ.

---

# 5. `data_deletion_request` (ENT-PL01-03)

Yêu cầu "Xoá dữ liệu liên quan" theo một mã đồng ý. Job xoá đọc bảng này.

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `user_id` | `bigint` | No | — | FK `vehicle_user.user_id` `ON DELETE CASCADE` |
| `consent_code` | `data_consent_code_enum` | No | — | Loại dữ liệu cần xoá |
| `options` | `jsonb` | No | `'{}'` | Ví dụ `{ "keepCreatedEvents": true }` cho lịch (AF-PL01-01) |
| `status` | `data_deletion_status_enum` | No | `'pending'` | `pending`, `running`, `done`, `failed` |
| `attempts` | `integer` | No | `0` | |
| `last_error` | `varchar(100)` | Yes | `NULL` | Chỉ tên lớp lỗi, không lưu nội dung |
| `due_at` | `timestamptz` | No | — | `created_at + DELETE_SLA_HOURS` |
| `completed_at` | `timestamptz` | Yes | `NULL` | |
| `created_at` | `timestamptz` | No | `now()` | |

```sql
CREATE TYPE data_deletion_status_enum AS ENUM ('pending', 'running', 'done', 'failed');
CREATE INDEX ix_data_deletion_request_due ON data_deletion_request (status, due_at);
-- Một yêu cầu đang mở cho mỗi (chủ xe, loại).
CREATE UNIQUE INDEX ux_data_deletion_open ON data_deletion_request (user_id, consent_code)
  WHERE status IN ('pending', 'running');
```

## 5.1 Dữ liệu bị xoá theo loại

| Mã | Bảng / dữ liệu bị xoá | Spec chủ |
|---|---|---|
| `CONSENT_LONG_TERM_MEMORY` | `agent_user_memory` (+ `agent_memory_source`, `agent_memory_version` cascade, PS-01) (gồm khoá `communication_style` của PS-05), vector của mục nhớ | PS-01, PS-05 |
| `CONSENT_CALENDAR_SYNC` | `calendar_connection` (thu hồi token trước), `calendar_busy_cache`; `booking_calendar_event` + sự kiện đã tạo nếu `keepCreatedEvents = false` | BK-04 |
| `CONSENT_LOCATION` | `owner_scheduling_profile.anchor_type = DEVICE` về `NULL` (giữ khu vực `anchor_province`), `user_location.lat/lng` do thiết bị ghi | BK-01, BK-05 |
| `CONSENT_PERSONALIZATION_DATA` | `owner_workshop_preference_signal` (PS-02), `recommendation_feedback` (PS-03); chủ xe bị loại khỏi nhóm tương đồng ở lần dựng sau (PS-04) | PS-02, PS-03, PS-04 |
| `CONSENT_AUTO_BOOKING` | Không có dữ liệu riêng; chỉ hạ `owner_scheduling_profile.automation_level` từ `AUTO_BOOK` về `HOLD` | BK-01 |

---

# 6. Business Rules (bổ sung)

## BR-ENT-PL01-01 — Ghi trạng thái và log trong một transaction

Mọi thay đổi `data_consent` chèn đúng một dòng `data_consent_log` trong cùng transaction (AC-PL01-03). Ghi `granted` khi đang `granted` là no-op: không đổi `version`, không ghi log.

## BR-ENT-PL01-02 — Thông báo lần đầu là một lần ghi

Khi frontend xác nhận đã hiện thông báo lần đầu của bộ nhớ dài hạn, backend ghi `granted` với `channel = FIRST_RUN_NOTICE` nếu chưa có dòng. Có dòng rồi thì không đổi.

## BR-ENT-PL01-03 — Bật lại sau khi xoá bắt đầu từ rỗng

Xoá không đụng `data_consent`; bật lại chỉ đổi trạng thái. Dữ liệu cũ đã bị xoá nên tính năng bắt đầu từ rỗng (EDGE-PL01-02). Yêu cầu xoá còn `pending` khi chủ xe bật lại vẫn chạy (xoá dữ liệu tạo **trước** `created_at` của yêu cầu).

## BR-ENT-PL01-04 — Đồng bộ với `agent_memory_setting`

`CONSENT_LONG_TERM_MEMORY` là nguồn sự thật. `ConsentService` ghi `agent_memory_setting.enabled` trong cùng transaction để code MVP (`PreferenceService`) đọc đúng. Không ghi ngược lại từ `PATCH /agent-memory/settings`; route này chuyển sang gọi `ConsentService` (API §3.3).

---

# 7. Migration

- Một revision Alembic: 3 enum, 3 bảng, index, CHECK.
- Backfill: với mỗi `agent_memory_setting.enabled = false` ⇒ chèn `data_consent (CONSENT_LONG_TERM_MEMORY, revoked)` + log `channel = SYSTEM`. Các mã khác không backfill.
- `downgrade`: drop bảng, drop enum. Không đụng `user_consent`.
- SQLite trong test: enum thành `VARCHAR`, `jsonb` → `JSON` (helper `_make_sqlite_compatible`); partial index bị bỏ qua nên test kiểm hành vi service.

---

# 8. Retention

| Bảng | Giữ | Xoá |
|---|---|---|
| `data_consent` | Đến khi xoá tài khoản | Cascade |
| `data_consent_log` | Đến khi xoá tài khoản (bằng chứng đồng ý) | Cascade |
| `data_deletion_request` | 180 ngày sau `completed_at` | Job dọn hằng ngày |

---

# 9. Open Questions

| ID | Câu hỏi | Đề xuất |
|---|---|---|
| `Q-ENT-PL01-01` | Có cần giữ log đồng ý sau khi xoá tài khoản để chứng minh tuân thủ? | Hỏi người hiểu quy định (FF §23); tạm cascade |
| `Q-ENT-PL01-02` | Mặc định (P2Q-11) | Theo §4 |

---

# 10. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
| `v0.2` | `2026-10-12` | PO chốt tên bảng `data_consent` / `data_consent_log` |
