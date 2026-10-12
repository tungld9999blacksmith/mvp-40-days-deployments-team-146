# API Technical Specification — Bộ nhớ ngắn hạn và dài hạn của agent

> Backend cho Feature `FEAT-P2-PS01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ps-01-phase2-spec.ff.md). **Entity:** [Entity Spec](ps-01-phase2-spec.entity.md).
>
> **Tái dùng, không viết lại:** router `/agent-memory` và `PreferenceService` (`modules/agent_memory/preferences.py`: `remember`, `list`, `recall`, `forget`, `edit`, `validate_value`), `MemoryCleanup` (xoá vector), `agents/memory_context.py` + `memory_guard.py` (nạp bộ nhớ vào prompt, chặn rò rỉ), tool `remember_preference` (`agents/tools/memory_tools.py`), checkpoint LangGraph. Đồng ý: `ConsentService` (PL-01).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-PS01` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/agent_memory/` (mở rộng): `preferences.py` → `MemoryService`, `inference.py` (mới), `jobs.py` (mới) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-PS01-01` | `GET` | `/agent-memory` (sửa) | Danh sách theo nhóm, nguồn, lần dùng gần nhất, hạn | UC-PS01-04 |
| `API-PS01-02` | `PATCH` | `/agent-memory/{memoryId}` (có sẵn) | Sửa giá trị | UC-PS01-04 |
| `API-PS01-03` | `DELETE` | `/agent-memory/{memoryId}` (có sẵn) | Xoá một mục | UC-PS01-04, BR-PS01-08 |
| `API-PS01-04` | `DELETE` | `/agent-memory` (có sẵn) | Xoá tất cả | UC-PS01-04 |
| `API-PS01-05` | `PATCH` | `/agent-memory/settings` (sửa) | Bật / tắt — chuyển tiếp sang PL-01 | UC-PS01-05 |
| `SVC-PS01-01` | Internal | `MemoryService.recall_for_intent(user, vehicle, intent)` | Nạp mục liên quan ý định | UC-PS01-03, FF §21 |
| `SVC-PS01-02` | Internal | `MemoryService.propose(user, key, value, source, evidence)` | Cổng ghi duy nhất | UC-PS01-01, BR-PS01-09 |
| `TOOL-PS01-01` | Agent tool | `remember_preference` (sửa) / `forget_memory` (mới) | LLM đề xuất ghi / xoá | UC-PS01-01, AF-PS01-02 |
| `JOB-PS01-01` | Celery | `memory.infer` (hằng ngày) | Suy ra từ hành vi | UC-PS01-02 |
| `JOB-PS01-02` | Celery | `memory.expire_and_purge` (mỗi giờ) | Hết hạn, xoá cứng mục `revoked` | BR-PS01-07, 08 |

---

# 2. Authorization & Guards

1. Chủ xe (`memory_owner` có sẵn). Chủ xưởng, KTV không có quyền (FF §16).
2. Mọi đọc / ghi bộ nhớ dài hạn kiểm `ConsentService.is_granted(CONSENT_LONG_TERM_MEMORY)` **mỗi lần** (thay `PreferenceService.enabled` / `read_enabled_for` / `write_enabled_for`). Lỗi ⇒ coi như tắt (PL-01 BR-PL01-06).
3. Màn quản lý vẫn **xem và xoá** được khi đã tắt (chủ xe phải xoá được dữ liệu cũ); không sửa, không thêm.

---

# 3. API-PS01-01 — `GET /agent-memory` (sửa)

```json
{
  "data": {
    "enabled": true,
    "groups": [
      { "key": "preferred_workshop", "title": "Xưởng hay đến",
        "items": [ { "id": "…", "value": { "workshopId": "…" }, "label": "VinFast Cầu Giấy", "source": "INFERRED",
                     "confirmCount": 3, "usable": true, "lastUsedAt": "…", "expiresAt": "…", "version": 2, "editable": true } ] },
      { "key": "vehicle_issue", "title": "Vấn đề xe từng gặp", "items": [ … ] }
    ]
  }
}
```

- `usable = false` cho mục `INFERRED` có `confirmCount < MEMORY_INFER_MIN_REPEAT` (hiện mờ, nhãn "Đang quan sát").
- `editable`: `service_feedback`, `cancel_habit` không sửa được (chỉ xoá) vì đến từ hệ thống.
- Giữ trường MVP (`enabled`, `items` phẳng) một phiên bản để `MemoryDrawer` cũ không vỡ; frontend mới đọc `groups`.

---

# 4. SVC-PS01-02 — `MemoryService.propose`

```python
def propose(self, user_id, key, value, *, source, vehicle_id=None, evidence_message_id=None) -> ProposeResult
```

1. Đồng ý tắt ⇒ `SKIPPED_NO_CONSENT`.
2. `key` không trong danh mục, `source` không được phép cho khoá (entity §2.1), giá trị chứa mẫu cấm ⇒ `REJECTED` — log `memory.rejected` chỉ với `key` và lý do, **không** log giá trị (EF-PS01-01).
3. `OWNER_STATED`: bắt buộc `evidence_message_id` là tin của chủ xe trong hội thoại hiện tại và nội dung tin khớp giá trị (`_matches_consent` có sẵn).
4. Có mục `active` cùng khoá:
   - Giá trị giống ⇒ `confirm_count + 1`, làm mới hạn.
   - Khác ⇒ BR-ENT-PS01-02 (thay, lưu phiên bản). Riêng `preferred_time` từ AF-PS01-01 ("lần này buổi chiều"): BK-01 ghi nhận một lần dùng override; chỉ khi override cùng giá trị lặp `≥ MEMORY_INFER_MIN_REPEAT` lần mới gọi `propose(source = INFERRED)` để thay.
5. Mục mới: `expires_at = now + MEMORY_TTL_DAYS`.
6. `preferred_workshop` / `preferred_time` / `location_anchor` thay đổi ⇒ đồng bộ ràng buộc suy ra / khai của BK-01 (`owner_scheduling_constraint` `source = INFERRED`, `memory_item_id`) — mục `INFERRED` vào BK-01 ở trạng thái `pending_review` cho tới khi chủ xe xác nhận (BK-01 BR-BK01-10), mục `OWNER_STATED` vào `active`.

---

# 5. SVC-PS01-01 — `recall_for_intent`

| Ý định (router hiện có) | Khoá được nạp |
|---|---|
| `BOOKING` | `preferred_workshop`, `preferred_time`, `location_anchor`, `cancel_habit`, `addressing` |
| `MAINTENANCE_QA` / `RAG` | `vehicle_issue`, `addressing`, `communication_style` |
| `COST` | `cost_display_preference`, `addressing` |
| `SMALL_TALK` / khác | `addressing`, `communication_style` |

- Chỉ mục `active` và `usable`; tối đa 8 mục; định dạng ngắn trong khối `MEMORY` của prompt (`memory_context.py`) với id mục (`m1`, `m2`…).
- Nạp song song với RAG / grounding; ngân sách ≤ 200 ms tăng thêm cho token đầu (FF §18): một truy vấn có index, đệm theo lượt.
- Service lỗi ⇒ trả rỗng, log, agent chạy như MVP (EF-PS01-03).

## 5.1 Nêu rõ khi dùng (BR-PS01-04, AC-PS01-04)

- Prompt: "Khi dùng một mục trong khối MEMORY, nói rõ bằng câu dẫn như 'Lần trước bạn…', 'Bạn từng nói…' và trả `memory_refs` (id mục)."
- Agent trả `memory_refs` qua output có cấu trúc (`agents/contracts.py`); `ChatService` lưu `chat_message.refs.memoryRefs = [memoryId…]`, ghi `agent_memory_use`, làm mới hạn.
- `output_guard` thêm kiểm: có `memory_refs` mà câu trả lời không chứa câu dẫn (danh sách cụm từ) ⇒ log `memory.unattributed` (đo eval, không chặn).

---

# 6. Tools

| Tool | Thay đổi |
|---|---|
| `remember_preference` (sửa) | Args (LLM thấy): `key` (enum danh mục, trừ `service_feedback` / `cancel_habit`), `value` (theo schema khoá), `evidence_message_id` ngầm = tin chủ xe gần nhất. Gọi `propose(source = OWNER_STATED)`. Trả `{ status: SAVED | UPDATED | REJECTED | SKIPPED_NO_CONSENT }` — không trả lý do chi tiết khi `REJECTED` |
| `forget_memory` (mới) | Args: `key`, `hint?`. Xoá mục `active` khớp khoá (và `hint` cho khoá nhiều giá trị) của chủ xe (AF-PS01-02). Trả `{ status: FORGOTTEN, count }` |

---

# 7. API-PS01-02..05

- **Sửa** (`PATCH /{memoryId}`): body `{ value, version }` như MVP; kiểm schema khoá + regex cấm; lưu phiên bản; `source` giữ nguyên trừ khi chủ xe sửa mục `INFERRED` ⇒ thành `OWNER_STATED` (chủ xe đã xác nhận). `version` lệch ⇒ `409 MEMORY_VERSION_CONFLICT`.
- **Xoá một / tất cả**: `status = revoked` ngay (agent không đọc từ lượt sau, AC-PS01-01); `JOB-PS01-02` xoá cứng dòng + phiên bản + lượt dùng + vector trong `DELETE_SLA_HOURS` (BR-PS01-08). Xoá tất cả = PL-01 `deletion-request` cho `CONSENT_LONG_TERM_MEMORY` nhưng **không** tắt đồng ý.
- **Bật / tắt** (`PATCH /settings`): chuyển tiếp `PUT /privacy/consents/CONSENT_LONG_TERM_MEMORY` (`channel = PRIVACY_SCREEN`). Tắt ⇒ lượt chat kế tiếp không nạp bộ nhớ dài hạn (AC-PS01-03); dữ liệu giữ nguyên cho tới khi chủ xe xoá.

---

# 8. JOB-PS01-01 — `memory.infer`

Hằng ngày 03:00, chủ xe có đồng ý. Nguồn: 180 ngày `booking` `completed` / `confirmed` và sự kiện BK-02.

| Khoá | Quy tắc |
|---|---|
| `preferred_workshop` | Cùng xưởng ở ≥ `MEMORY_INFER_MIN_REPEAT` lịch gần nhất |
| `preferred_time` | ≥ N lịch cùng buổi + cùng nhóm ngày (ngày thường / cuối tuần) |
| `cancel_habit` | ≥ N lần đổi giờ trong `LATE_CANCEL_HOURS` hoặc huỷ muộn trong cửa sổ BK-02 |
| `communication_style` | Theo PS-05 (job PS-05 gọi `propose`) |

`propose(source = INFERRED, confirm_count = số lần quan sát)`. Mục chủ xe đã xoá trong 90 ngày với cùng giá trị ⇒ không suy ra lại (đọc log xoá trong Redis `memory:forgotten:{userId}:{key}:{valueHash}`, TTL 90 ngày). Chủ xe nói lại ngay sau khi xoá vẫn ghi như mục mới (EDGE-PS01-01) vì đó là `OWNER_STATED`.

---

# 9. Error Cases

| HTTP | Code | Khi | API |
|---|---|---|---|
| 400 | `INVALID_MEMORY_VALUE` | Sai schema / chứa mẫu cấm | PS01-02 |
| 403 | `MEMORY_DISABLED` | Sửa khi đã tắt | PS01-02 |
| 404 | `MEMORY_NOT_FOUND` | | PS01-02, 03 |
| 409 | `MEMORY_VERSION_CONFLICT` | | PS01-02 |
| 409 | `MEMORY_NOT_EDITABLE` | Sửa `service_feedback` / `cancel_habit` | PS01-02 |

---

# 10. Observability & Eval

- Log `memory.proposed` (`key`, `source`, `result`), `memory.recalled` (`intent`, `count`, `ms`), `memory.used` (`count`), `memory.unattributed`, `memory.purged`. Không log `value_json`.
- LangSmith: span `memory.recall` gắn số mục, không gắn giá trị (stack quan sát hiện có).
- Eval (`eval/datasets`, AI-agent eval harness): (1) mục đã xoá không xuất hiện trong câu trả lời sau đó (AC-PS01-01); (2) mỗi câu dùng mục có câu dẫn (AC-PS01-04); (3) bộ câu chứa CCCD / SĐT / VIN không tạo mục (AC-PS01-02).

---

# 11. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | `validate_value` chặn CCCD / SĐT / email / VIN 17 ký tự / địa chỉ có số nhà | +5 |
| Unit | Nguồn không được phép cho khoá ⇒ `REJECTED` | +2 |
| Service | Mâu thuẫn ⇒ `superseded` + phiên bản (EF-PS01-02) | +1 |
| Service | `INFERRED` chưa đủ lần không vào `recall` | +1 |
| Service | Tắt đồng ý ⇒ `recall` rỗng, `propose` `SKIPPED` (AC-PS01-03) | +2 |
| Service | Xoá ⇒ không còn trong `recall` ngay; xoá cứng sau job (BR-PS01-08) | +2 |
| Service | Dùng mục ⇒ `agent_memory_use` + `expires_at` làm mới | +1 |
| Service | Service lỗi ⇒ lượt chat vẫn trả lời (EF-PS01-03) | +1 |
| Job | Suy ra `preferred_workshop` sau 2 lịch cùng xưởng; không suy ra lại giá trị vừa bị xoá | +2 |
| Migration | Khoá MVP đổi tên giữ dữ liệu | +1 |
| Eval | AC-PS01-01, 02, 04 | 3 bộ |

---

# 12. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
