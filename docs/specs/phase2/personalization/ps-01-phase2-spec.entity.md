# Entity Specification — Bộ nhớ ngắn hạn và dài hạn của agent

> Entity cho Feature `FEAT-P2-PS01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-01-phase2-spec.ff.md). **API:** [API Spec](ps-01-phase2-spec.api.md).
>
> **Nguyên tắc (PO chốt 2026-10-12):** **mở rộng** bảng bộ nhớ MVP `agent_user_memory` ([AI-001 §13](../../ai-agent/ai-001-sprint-2-spec.agent.md), module `agent_memory`) thay vì tạo bảng `agent_memory` mới như FF §14 gợi ý — tránh hai nguồn sự thật cho cùng một khái niệm. Bộ nhớ ngắn hạn giữ nguyên checkpoint LangGraph (`agents/checkpoint.py`) và `conversation_summary`. Đồng ý: PL-01 `CONSENT_LONG_TERM_MEMORY` thay cho `agent_memory_setting.enabled` (đồng bộ một chiều, PL-01 BR-ENT-PL01-04).

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-PS01` — PS-01 |
| Version | `v0.2` |
| Status | `Draft` |
| Owner | Backend + AI Team |
| Created Date | `2026-10-12` |
| Related FF | [ps-01-phase2-spec.ff.md](ps-01-phase2-spec.ff.md) |
| Related API | [ps-01-phase2-spec.api.md](ps-01-phase2-spec.api.md) |
| Related FE | [ps-01-phase2-spec.fe.md](ps-01-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| — | `AgentUserMemory` | `agent_user_memory` | Có sẵn — **mở rộng** | Danh mục khoá mới, `source`, `confirm_count`, `last_used_at`, `superseded_by_id`, `value_hash`; `consent_message_id` cho phép `NULL` |
| `ENT-PS01-01` | `AgentMemoryVersion` | `agent_memory_version` | **Mới** | Lịch sử phiên bản (BR-PS01-03) |
| `ENT-PS01-02` | `AgentMemoryUse` | `agent_memory_use` | **Mới** | Mục nào được dùng ở tin nhắn nào (AC-PS01-04, làm mới hạn) |
| — | `AgentMemorySource` | `agent_memory_source` | Có sẵn — không đổi | Tin nhắn nguồn của mục chủ xe nói |
| — | `AgentMemorySetting` | `agent_memory_setting` | Có sẵn — chỉ còn là bản sao | PL-01 là nguồn sự thật |
| — | `ConversationSummary`, checkpoint | có sẵn | Không đổi | Bộ nhớ ngắn hạn |

---

# 2. `agent_user_memory` — thay đổi

## 2.1 Danh mục khoá (BR-PS01-01)

| `memory_key` | Thay khoá MVP | `scope_type` | Nhiều giá trị? | Nguồn cho phép | `value_json` |
|---|---|---|---|---|---|
| `preferred_workshop` | `preferred_workshop_id` | `account` | Không | `OWNER_STATED`, `INFERRED` | `{ "workshopId": "…" }` |
| `preferred_time` | `preferred_service_window` | `account` | Không | `OWNER_STATED`, `INFERRED` | `{ "weekdays": [6], "start": "08:00", "end": "10:00" }` |
| `location_anchor` | — | `account` | Không | `OWNER_STATED` | `{ "province": "Hà Nội", "district": "Cầu Giấy", "label": "Nhà" }` — **chỉ khu vực**, không số nhà |
| `addressing` | — | `account` | Không | `OWNER_STATED` | `{ "text": "anh Tùng" }` (≤ 30 ký tự) |
| `vehicle_issue` | — | `vehicle` | Có | `OWNER_STATED`, `FEEDBACK` | `{ "category": "BRAKE", "text": "Phanh trước kêu", "observedAt": "2025-10" }` |
| `service_feedback` | — | `account` | Có | `FEEDBACK` | `{ "workshopId": "…", "aspect": "WAIT_TIME", "sentiment": "NEGATIVE", "followUpId": "…" }` |
| `cancel_habit` | — | `account` | Không | `INFERRED` | `{ "pattern": "RESCHEDULE_LAST_MINUTE", "count": 3 }` |
| `communication_style` | — | `account` | Không | `OWNER_STATED`, `INFERRED` | Theo PS-05 (`{ "length": "SHORT", "tone": "CASUAL" }`) |
| `cost_display_preference` | giữ MVP | `account` | Không | `OWNER_STATED` | Như MVP |

```sql
ALTER TABLE agent_user_memory DROP CONSTRAINT ck_agent_memory_key;
ALTER TABLE agent_user_memory ADD CONSTRAINT ck_agent_memory_key CHECK (memory_key IN (
  'preferred_workshop','preferred_time','location_anchor','addressing','vehicle_issue',
  'service_feedback','cancel_habit','communication_style','cost_display_preference'));
```

Danh mục cấm (EF-PS01-01, AC-PS01-02): số CCCD, VIN đầy đủ (17 ký tự), biển số đầy đủ, số điện thoại, email, địa chỉ có số nhà, sức khoẻ, tài chính cá nhân, suy đoán tính cách. Không có khoá cho các loại này; `validate_value` (có sẵn trong `preferences.py`) thêm bộ lọc regex chặn các mẫu trên **bên trong** giá trị văn bản (`addressing.text`, `vehicle_issue.text`).

## 2.2 Cột mới / đổi

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `source` | `varchar(16)` | No | `'OWNER_STATED'` | `OWNER_STATED`, `INFERRED`, `FEEDBACK` (BR-PS01-02) |
| `confirm_count` | `smallint` | No | `1` | Số lần quan sát / xác nhận. Mục `INFERRED` chỉ được **dùng** khi `≥ MEMORY_INFER_MIN_REPEAT` |
| `last_used_at` | `timestamptz` | Yes | `NULL` | Lần agent dùng gần nhất (SCR-PS01-01) |
| `superseded_by_id` | `uuid` | Yes | `NULL` | FK tự tham chiếu khi bị thay (EF-PS01-02) |
| `value_hash` | `char(16)` | No | — | Băm ngắn `value_json` chuẩn hoá; unique cho khoá nhiều giá trị |
| `consent_message_id` | `uuid` | **Yes** (đổi) | `NULL` | Bắt buộc khi `source = OWNER_STATED` |

`status`: `active`, `superseded`, `expired`, `revoked` (MVP — dùng cho "đã xoá", sau đó xoá cứng trong `DELETE_SLA_HOURS`).

```sql
ALTER TABLE agent_user_memory ALTER COLUMN consent_message_id DROP NOT NULL;
ALTER TABLE agent_user_memory ADD CONSTRAINT ck_agent_memory_status
  CHECK (status IN ('active', 'superseded', 'expired', 'revoked'));  -- thay CHECK cũ
ALTER TABLE agent_user_memory ADD CONSTRAINT ck_agent_memory_source CHECK (source IN ('OWNER_STATED','INFERRED','FEEDBACK'));
ALTER TABLE agent_user_memory ADD CONSTRAINT ck_agent_memory_stated
  CHECK (source <> 'OWNER_STATED' OR consent_message_id IS NOT NULL);
-- Khoá một giá trị: giữ ux_agent_memory_active nhưng chỉ cho khoá một giá trị.
DROP INDEX ux_agent_memory_active;
CREATE UNIQUE INDEX ux_agent_memory_active_single ON agent_user_memory (user_id, scope_type, scope_id, memory_key)
  WHERE status = 'active' AND memory_key NOT IN ('vehicle_issue', 'service_feedback');
CREATE UNIQUE INDEX ux_agent_memory_active_multi ON agent_user_memory (user_id, scope_type, scope_id, memory_key, value_hash)
  WHERE status = 'active' AND memory_key IN ('vehicle_issue', 'service_feedback');
CREATE INDEX ix_agent_memory_expiry ON agent_user_memory (expires_at) WHERE status = 'active';
```

## 2.3 Hạn (BR-PS01-07)

`expires_at = max(expires_at, now + MEMORY_TTL_DAYS)` mỗi lần dùng (ghi `agent_memory_use`). Job hết hạn đổi `active → expired`.

---

# 3. `agent_memory_version` (ENT-PS01-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `memory_id` | `uuid` | No | — | FK `agent_user_memory.id` `ON DELETE CASCADE` |
| `version` | `integer` | No | — | Bằng `agent_user_memory.version` trước khi đổi |
| `value_json` | `jsonb` | No | — | Giá trị cũ |
| `changed_by` | `varchar(12)` | No | — | `OWNER_EDIT`, `AGENT`, `INFERENCE`, `FEEDBACK` |
| `created_at` | `timestamptz` | No | `now()` | |

Xoá mục ⇒ xoá cả phiên bản (cascade khi xoá cứng, BR-PS01-08).

---

# 4. `agent_memory_use` (ENT-PS01-02)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `memory_id` | `uuid` | No | — | PK (1/2), FK `agent_user_memory.id` `ON DELETE CASCADE` |
| `message_id` | `uuid` | No | — | PK (2/2), FK `chat_message.id` `ON DELETE CASCADE` — tin trợ lý đã dùng mục |
| `created_at` | `timestamptz` | No | `now()` | |

Phục vụ AC-PS01-04 (mỗi câu trả lời dùng mục nhớ có câu dẫn: kiểm tra trên `chat_message.refs.memoryRefs`) và eval AC-PS01-01 (mục đã xoá không còn xuất hiện).

---

# 5. Business Rules (bổ sung)

## BR-ENT-PS01-01 — LLM đề xuất, service quyết định

Agent không ghi bảng. Mọi ghi đi qua `MemoryService.propose(...)` (API §4), kiểm danh mục, nguồn cho phép, regex cấm, đồng ý (BR-PS01-09).

## BR-ENT-PS01-02 — Mâu thuẫn

Ghi giá trị mới cho khoá một giá trị: một transaction — dòng cũ `superseded` + `superseded_by_id`, chèn `agent_memory_version`, chèn dòng mới `active` (EF-PS01-02).

## BR-ENT-PS01-03 — Xe đổi chủ

`vehicle_issue` gắn `scope_id = user_vehicle_id`; khi `user_vehicle` của chủ cũ chuyển `INACTIVE` vì đổi chủ, job xoá (`revoked`) các mục `scope_type = 'vehicle'` của xe đó (EDGE-PS01-02).

---

# 6. Migration

- Một revision: đổi CHECK, index, thêm cột (`source` mặc định `OWNER_STATED`, `confirm_count = 1`, `value_hash` backfill), cho phép `NULL` ở `consent_message_id`, 2 bảng mới.
- Đổi tên khoá dữ liệu cũ: `preferred_workshop_id` → `preferred_workshop` (`{ workshop_id }` → `{ workshopId }`), `preferred_service_window` → `preferred_time` (`{ day, period }` → `{ weekdays, start, end }` theo buổi `SCHEDULER_DAY_PARTS`). Code MVP đọc khoá cũ được cập nhật cùng PR.
- Không đổi `agent_memory_source`, `conversation_summary`.

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
| `v0.2` | `2026-10-12` | PO chốt mở rộng `agent_user_memory` |
