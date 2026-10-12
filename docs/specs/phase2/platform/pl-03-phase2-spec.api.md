# API Technical Specification — Chỉ số đo hiệu quả

> Backend cho Feature `FEAT-P2-PL03`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](pl-03-phase2-spec.ff.md). **Entity:** [Entity Spec](pl-03-phase2-spec.entity.md).
>
> **Tái dùng:** Celery (job), Redis (hàng đợi đệm), stack quan sát hiện có (OTel Collector → Grafana Cloud) cho cảnh báo vận hành. Sự kiện sản phẩm (PL-03) **khác** log / trace vận hành: log phục vụ gỡ lỗi, `product_event` phục vụ chỉ số sản phẩm.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-PL03` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/metrics/` (mới): `events.py` (registry + validator), `publisher.py`, `aggregate.py`, `export.py`, `route.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `SVC-PL03-01` | Internal | `EventPublisher.emit(name, *, feature, occurred_at, user_id?, actor?, workshop_id?, session?, props, idem_key)` | Ghi sự kiện, không chặn luồng | UC-PL03-01, BR-PL03-01, 04, 05 |
| `API-PL03-01` | `POST` | `/metrics/client-events` | Sự kiện chỉ frontend biết (ví dụ `option_shown` thực sự hiện trên màn) | UC-PL03-01 |
| `JOB-PL03-01` | Celery | `metrics.flush_events` (liên tục, mỗi 2 s) | Ghi lô từ Redis vào `product_event` | BR-PL03-04 |
| `JOB-PL03-02` | Celery | `metrics.aggregate_daily` (02:00) | Tính M-01…M-12, 3 ngày gần nhất | UC-PL03-02, BR-PL03-03 |
| `JOB-PL03-03` | Celery | `metrics.export_team_data` (04:00) | Xuất Parquet ẩn danh | UC-PL03-03 |
| `JOB-PL03-04` | Celery | `metrics.partition_maintenance` (hằng tháng) | Tạo phân vùng mới, drop phân vùng > 13 tháng | Q-PL03-02 |
| `API-PL03-02` | `GET` | `/internal/metrics?from&to&workshopId?&granularity=WEEK` | Bảng chỉ số nội bộ (SCR-PL03-01) | SCR-PL03-01 |
| `API-PL03-03` | `GET` | `/internal/metrics/definitions` | Định nghĩa + phiên bản | BR-PL03-06 |
| `API-PL03-04` | `GET` | `/workshop-owner/metrics?from&to` | Chỉ số của xưởng mình | FF §16 |

---

# 2. Authorization & Guards

1. `API-PL03-01`: chủ xe / chủ xưởng / KTV đã đăng nhập; backend tự gắn `user_hash` từ token (client không gửi định danh). Giới hạn 120 sự kiện / phút / người dùng; chỉ chấp nhận tên trong danh sách `clientAllowed` của registry.
2. `API-PL03-02/03`: tài khoản có Firebase custom claim `ops = true` (PO, PM, Team Data) ⇒ không thì `403`. Không dùng vai trò chủ xe / chủ xưởng.
3. `API-PL03-04`: chủ xưởng; chỉ chỉ số có chiều `workshop_id` của xưởng mình (M-05, M-06, M-07, M-09, M-10, M-11).

---

# 3. SVC-PL03-01 — `EventPublisher.emit`

1. Lấy schema theo `name` từ registry; không có ⇒ log lỗi lập trình + bỏ (không raise).
2. Validate `props` theo schema + khoá cấm (entity §2.2). Sai ⇒ bỏ sự kiện, tăng `product_event_rejected_total{name,reason}` (AC-PL03-02).
3. Băm định danh (HMAC, muối `PL03_HASH_SALT`).
4. `LPUSH` JSON vào Redis `metrics:events` (O(1), mục tiêu ≤ 5 ms, FF §18). Redis lỗi ⇒ thử ghi vào hàng đợi trong bộ nhớ của tiến trình (tối đa 1.000), quá thì bỏ và tăng `product_event_dropped_total` (EF-PL03-01).
5. **Không bao giờ raise** ra luồng nghiệp vụ; bọc toàn bộ trong `try/except` + log (BR-PL03-04, AC-PL03-03). Gọi **sau commit** của giao dịch nghiệp vụ (`session.after_commit` hook) để không ghi sự kiện cho giao dịch bị rollback.

`JOB-PL03-01` đọc lô ≤ 500, `INSERT … ON CONFLICT (idempotency_key, occurred_at) DO NOTHING`. Lỗi DB ⇒ đẩy lại hàng đợi, backoff.

---

# 4. JOB-PL03-02 — định nghĩa v1 (PRD §12)

| Mã | Công thức (v1) | Nguồn sự kiện | Chiều |
|---|---|---|---|
| M-01 | Median `booking_confirmed.msSinceIntent` (ghép `booking_intent_started` → `booking_confirmed` cùng `session_hash`) | CH-01, BK-01, booking | all |
| M-02 | Median `taps`; median `typedChars`; tỉ lệ `typedChars = 0` | `booking_confirmed` | all |
| M-03 | `scheduler_run` có `outcome ∈ {OPTIONS, TIMEOUT_PARTIAL}` hoặc (`NO_OPTION` có `relaxationOffers > 0` hoặc lý do rõ) / tổng `scheduler_run` chủ xe gọi | BK-01 | all |
| M-04 | `chip_clicked` / `chip_shown` | CH-01 | all, theo `intent` |
| M-05 | `no_show_marked` (trừ `no_show_waived`) / lịch đến hạn trong ngày; `booking_cancelled{late_cancel}` / lịch đến hạn | BK-02 | all, workshop |
| M-06 | `booking_manual_review` / `booking_confirmed` (xưởng) | WS-01 | workshop |
| M-07 | `waitlist_offer_accepted` / `booking_cancelled` có chỗ được mời | BK-07 | workshop |
| M-08 | `advisor_answered` không có `handoff_created` cùng `session_hash` trong 24 giờ / tổng `advisor_answered` | AD, PL-02 | all, theo `topic` |
| M-09 | Median T₄ (`checked_in` → `service_started`), T₅ (`service_finished` → `vehicle_handed_over`) | us-037, us-057 | workshop |
| M-10 | T₃: tổng phút KTV / khoang không có việc trong giờ mở cửa / tổng phút mở cửa (từ phân công WS-03 + tiến độ) | WS-02, WS-03 | workshop |
| M-11 | KTV có ≥ 1 `technician_assistant_used` trong ngày làm việc / KTV có ca ngày đó | TA-01, WS-03 | workshop |
| M-12 | Tỉ lệ chủ xe có `CONSENT_LONG_TERM_MEMORY` hiệu lực (từ `consent_changed` tích luỹ); số `memory_deleted` | PL-01, PS-01 | all |

- Mẫu < 20 ⇒ `value = NULL` (tránh số liệu nhiễu).
- Hoàn tất trước 06:00 (FF §18); log `metrics.aggregate.done` (`ms`, `metrics`), cảnh báo Grafana nếu chưa xong lúc 06:00.

---

# 5. JOB-PL03-03 — xuất cho Team Data

Mỗi ngày: sự kiện của ngày `D−1` (+ tính lại 3 ngày nếu có sự kiện trễ) ⇒ Parquet (cột như `product_event`, `props` dạng JSON string) ⇒ bucket object storage **của Phase 2** `team-data/events/dt=YYYY-MM-DD/` (BR-PL03-07). Ghi `data_export_run`. Không xuất `idempotency_key`. Quyền đọc bucket chỉ cho service account của workspace Team Data.

---

# 6. API-PL03-01 — `POST /metrics/client-events`

```json
{ "events": [ { "name": "option_shown", "occurredAt": "2026-10-12T02:10:00Z", "idempotencyKey": "c-…", "props": { "runId": "…", "rank": 1 } } ] }
```

≤ 20 sự kiện mỗi lần. Backend băm `runId`, gắn `user_hash`, rồi `emit`. Trả `202` kể cả khi có sự kiện bị loại (`{ "accepted": 19, "rejected": 1 }`).

---

# 7. API-PL03-02 — `GET /internal/metrics`

```json
{ "data": { "granularity": "WEEK", "rows": [
  { "metricCode": "M-01", "name": "Thời gian từ ý định đến xác nhận", "unit": "SECONDS", "target": "< 60",
    "definitionVersion": 1, "series": [ { "period": "2026-W46", "value": 48.2, "sampleSize": 132 } ] } ] } }
```

Tuần ISO, giá trị tuần = median / tỉ lệ tính lại từ dữ liệu ngày (median gộp bằng đọc `product_event` của tuần, không trung bình các median ngày). `workshopId` ⇒ chỉ chỉ số có chiều xưởng.

---

# 8. Tích hợp vào các tính năng

Mỗi spec Phase 2 gọi `EventPublisher.emit` với tên ở entity §2.1. Bảng đối chiếu nơi phát:

| Sự kiện | Nơi phát |
|---|---|
| `booking_intent_started` | `chip-actions` intent `book_maintenance` (CH-01), mở wizard `/booking/options` (BK-01), `quick-booking` (us-061), widget / bản đồ |
| `scheduler_run`, `option_selected` | `SchedulerService.run` / `select` (BK-01) |
| `option_shown` | Frontend qua `API-PL03-01` khi thẻ phương án thực sự hiển thị |
| `booking_confirmed` | `BookingService._create_booking_locked` và xác nhận giữ chủ động; `taps`, `typedChars` lấy từ `conversation_flow_state` (CH-01) hoặc frontend gửi kèm request xác nhận |
| `chip_shown`, `chip_clicked` | `ChipSelector.attach`, `chip-actions` (CH-01) |
| `booking_cancelled`, `no_show_*` | `ReliabilityService` (BK-02) |
| `booking_manual_review` | `ConfirmationPolicy.decide` (WS-01) |
| `consent_changed` | `ConsentService` (PL-01) |
| `memory_deleted` | `MemoryService` (PS-01) |

---

# 9. Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Validator chặn khoá / giá trị cấm (SĐT, email, VIN, biển số, toạ độ) (AC-PL03-02) | +6 |
| Unit | HMAC ổn định, khác muối ⇒ khác băm | +2 |
| Service | Redis lỗi + DB lỗi ⇒ luồng đặt lịch vẫn thành công (AC-PL03-03) | +1 |
| Service | Giao dịch rollback ⇒ không có sự kiện | +1 |
| Job | Ghi lô idempotent; sự kiện trễ được tính lại trong 3 ngày (EDGE-PL03-01) | +2 |
| Job | Dữ liệu mẫu ⇒ tính đủ M-01…M-12 (AC-PL03-01) | +12 (tham số hoá) |
| API | `/internal/metrics` cần claim `ops`; chủ xưởng chỉ thấy xưởng mình | +2 |
| Perf | `emit` ≤ 5 ms p99 | +1 |

---

# 10. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
