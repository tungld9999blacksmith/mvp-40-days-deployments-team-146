# API Technical Specification — Tiến độ dịch vụ chi tiết 6 bước

> Backend cho Feature `FEAT-PROG-001` — PRD F8b (US-057 → US-059).
>
> **Nguồn nghiệp vụ:** [Functional Spec](../feature-functional/us-057-sprint-4-spec.ff.md). **Entity:** [Entity Spec](../entity/us-057-sprint-4-spec.entity.md) — `service_progress` (ENT-403, mở rộng cột người ghi).
>
> **Tích hợp F8:** hook trong `API-WB-04` (`CHECK_IN`, `START`) của [us-037 API](../../sprint-3/api/us-037-sprint-3-spec.api.md).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-PROG-001` |
| Version | `v1.0` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Created Date | `2026-09-30` |

---

# 1. API Group

| API ID | Method | Endpoint / Trigger | Actor | Mục đích | FF |
|---|---|---|---|---|---|
| `API-PG-01` | `GET` | `/api/v1/workshop-owner/bookings/{bookingId}/progress` | Chủ xưởng | Dòng thời gian + mốc kế tiếp hợp lệ | SCR-1301 |
| `API-PG-02` | `POST` | `/api/v1/workshop-owner/bookings/{bookingId}/progress` | Chủ xưởng | Thêm mốc | UC-1302, BR-1302, BR-1303 |
| `API-PG-03` | `GET` | `/api/v1/bookings/{bookingId}/progress` | Chủ xe | Dòng thời gian | UC-1303 |
| `HOOK-PG-01` | Internal | `ServiceProgressService.on_booking_transition(booking, action)` | Hệ thống | Ghi `checked_in` / `inspecting` trong transaction của `API-WB-04` | UC-1301 |

> `API-WB-02` (chi tiết booking của Board) và `API-BR-01` (ticket) **có thể nhúng** `progress` để giảm một request; các endpoint riêng ở trên dùng cho làm mới định kỳ.

---

# 2. Authorization

| API | Rule |
|---|---|
| `API-PG-01/02` | `require_active_workshop_owner`; `booking.workshop_id` = xưởng của chủ xưởng, sai ⇒ `404 BOOKING_NOT_FOUND` (BR-1306) |
| `API-PG-03` | `require_active_user`; `booking.user_id = uid`, sai ⇒ `404 BOOKING_NOT_FOUND` (AC-1304) |

---

# 3. Response chung — `Progress`

```json
{
  "data": {
    "bookingId": "8d2e…",
    "bookingStatus": "IN_PROGRESS",
    "currentStage": "WAITING_PARTS",
    "isFrozen": false,
    "nextStages": ["SERVICING"],
    "entries": [
      { "stage": "CHECKED_IN", "note": null, "actorType": "SYSTEM", "createdAt": "2026-10-04T02:05:00Z" },
      { "stage": "INSPECTING", "note": null, "actorType": "SYSTEM", "createdAt": "2026-10-04T02:10:00Z" },
      { "stage": "SERVICING", "note": null, "actorType": "WORKSHOP_OWNER", "createdAt": "2026-10-04T02:40:00Z" },
      { "stage": "WAITING_PARTS", "note": "Chờ má phanh trước, dự kiến 14:00", "actorType": "WORKSHOP_OWNER", "createdAt": "2026-10-04T03:30:00Z" }
    ]
  }
}
```

| Field | Description |
|---|---|
| `currentStage` | Dòng mới nhất; nếu chưa có dòng nào: suy ra theo EDGE-1304 (`CHECKED_IN` / `INSPECTING`) hoặc `null` khi `CONFIRMED` |
| `isFrozen` | `bookingStatus ∈ {COMPLETED, CANCELLED}` |
| `nextStages` | Theo bảng BR-1302, chỉ các mốc chủ xưởng được ghi; `[]` khi frozen hoặc chưa `IN_PROGRESS`. **Chỉ trả ở API-PG-01** |
| `entries[]` | Tăng dần theo thời gian. Ở `API-PG-03` bỏ trường người ghi cụ thể, chỉ giữ `actorType` |

---

# 4. API-PG-02 — `POST …/progress`

## 4.1 Request

```json
{ "stage": "WAITING_PARTS", "note": "Chờ má phanh trước, dự kiến 14:00", "expectedCurrentStage": "SERVICING" }
```

| Field | Type | Required | Constraints |
|---|---|---:|---|
| `stage` | `string` | Yes | `SERVICING` / `WAITING_PARTS` / `QUALITY_CHECK` / `READY_FOR_PICKUP` (không nhận `CHECKED_IN`, `INSPECTING` — do hook) |
| `note` | `string` | Cond. | Bắt buộc 10–500 khi `WAITING_PARTS`; ≤ 500 khác |
| `expectedCurrentStage` | `string` | Yes | Chống ghi đè khi hai tab (EF-1302) |

## 4.2 Processing

```text
BEGIN
  SELECT booking FOR UPDATE  (quyền xưởng)
  booking.status ≠ in_progress → 409 BOOKING_NOT_IN_PROGRESS (EDGE-1301/1303)
  current = latest service_progress(booking) or derived (EDGE-1304)
  current ≠ expectedCurrentStage → 409 PROGRESS_CHANGED + details.currentStage
  stage ∉ allowed_next(current) → 422 INVALID_STAGE_TRANSITION + details.nextStages
  WAITING_PARTS ∧ note invalid → 422 NOTE_REQUIRED
  INSERT service_progress(booking_id, stage, note, actor_type='workshop_owner',
                          actor_workshop_owner_id=:owner, source='BOARD')
COMMIT
after-commit: stage ∈ {WAITING_PARTS, READY_FOR_PICKUP} → NotificationService.send(PROGRESS_UPDATE) (BR-1305; giới hạn EDGE-1306)
201 + Progress
```

---

# 5. HOOK-PG-01

| `API-WB-04` action | Ghi thêm (cùng transaction) |
|---|---|
| `CHECK_IN` | `service_progress(stage='checked_in', actor_type='system', source='CHECK_IN')` |
| `START` | `service_progress(stage='inspecting', actor_type='system', source='START')` |
| `COMPLETE`, `CANCEL` | Không ghi; tiến độ đóng băng |

Bật/tắt bằng cờ `FEATURE_SERVICE_PROGRESS_ENABLED` (Could — có thể tắt mà không ảnh hưởng F8).

---

# 6. Error Cases

| Case | Code | HTTP |
|---|---|---:|
| Không thấy / không thuộc | `BOOKING_NOT_FOUND` | `404` |
| Booking không `in_progress` | `BOOKING_NOT_IN_PROGRESS` | `409` |
| Mốc hiện tại đã đổi | `PROGRESS_CHANGED` | `409` |
| Sai thứ tự | `INVALID_STAGE_TRANSITION` | `422` |
| Thiếu ghi chú chờ phụ tùng | `NOTE_REQUIRED` | `422` |
| Tính năng tắt | `FEATURE_DISABLED` | `404` |

---

# 7. Notification content (Discord)

```text
[EV Care] Cập nhật xe tại {workshop_name}: {stage_label_vi}.
{note_truncated_200}
Xem chi tiết: {APP_BASE_URL}/bookings/{booking_id}
```

Không chứa VIN, SĐT, biển số đầy đủ (PRD F7). Kết quả gửi ghi theo cơ chế delivery của us-021 `[Đề xuất: dùng chung bảng delivery hiện có hoặc chỉ log — Q-ENT-1302]`.

---

# 8. Performance & Observability

- p90 ≤ 500 ms. Index `service_progress(booking_id, created_at)` đã có.
- Log `progress.appended` (`booking_id`, `stage`, `actor_type`); metric `progress_stage_duration_minutes{stage}` (đo thời gian giữa các mốc — tham khảo, chưa đặt mục tiêu).

---

# 9. Test Checklist

- [ ] CHECK_IN/START ghi đúng mốc tự động trong cùng transaction (AC-1301); rollback F8 ⇒ không có mốc.
- [ ] Sai thứ tự ⇒ `422` + `nextStages` (AC-1302).
- [ ] `WAITING_PARTS` thiếu ghi chú ⇒ `422`; có ghi chú ⇒ gửi thông báo (AC-1303).
- [ ] Chủ xe B đọc booking của A ⇒ `404` (AC-1304).
- [ ] Sau `COMPLETED` ⇒ `409` (AC-1305).
- [ ] `expectedCurrentStage` lệch ⇒ `409 PROGRESS_CHANGED`.

---

# 10. Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0` | `2026-09-30` | Team 4 Người | Bản đầu |
