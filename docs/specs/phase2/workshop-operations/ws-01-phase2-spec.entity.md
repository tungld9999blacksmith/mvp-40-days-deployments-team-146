# Entity Specification — Tự nhận lịch hẹn có điều kiện

> Entity cho Feature `FEAT-P2-WS01`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ws-01-phase2-spec.ff.md). **API:** [API Spec](ws-01-phase2-spec.api.md).
>
> **Nguyên tắc:** luật là cấu hình có kiểu (mã luật cố định + tham số JSON đã kiểm), không phải biểu thức tự viết (FF §3.2). Quyết định tự nhận / duyệt tay và lý do được **chụp lại trên booking** lúc chủ xe xác nhận, để đổi luật sau đó không đổi lịch đang chờ (BR-WS01-04) và để đo M-06.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-WS01` — WS-01 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [ws-01-phase2-spec.ff.md](ws-01-phase2-spec.ff.md) |
| Related API | [ws-01-phase2-spec.api.md](ws-01-phase2-spec.api.md) |
| Related FE | [ws-01-phase2-spec.fe.md](ws-01-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-WS01-01` | `WorkshopBookingRule` | `workshop_booking_rule` | **Mới** | Một dòng mỗi (xưởng, mã luật) |
| `ENT-402` | `Booking` | `booking` | Có sẵn — **thêm cột** | `confirmation_decision`, `manual_review_reasons` |
| `ENT-008` | `Workshop` | `workshop` | Có sẵn — không đổi cột | `booking_confirmation_mode` vẫn dùng khi không bật luật nào (BR-WS01-03) |

---

# 2. `workshop_booking_rule` (ENT-WS01-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `workshop_id` | `uuid` | No | — | PK (1/2), FK `workshop.id` `ON DELETE CASCADE` |
| `rule_code` | `varchar(16)` | No | — | PK (2/2): `R-CAPACITY`, `R-RELIABILITY`, `R-PARTS`, `R-SLOT`, `R-EXTRA` |
| `enabled` | `boolean` | No | — | |
| `params` | `jsonb` | No | `'{}'` | Theo §2.1 |
| `updated_by_owner_id` | `uuid` | Yes | `NULL` | FK `workshop_owner.id` `ON DELETE SET NULL` |
| `updated_at` | `timestamptz` | No | `now()` | |

```sql
ALTER TABLE workshop_booking_rule ADD CONSTRAINT ck_wbr_code
  CHECK (rule_code IN ('R-CAPACITY', 'R-RELIABILITY', 'R-PARTS', 'R-SLOT', 'R-EXTRA'));
```

## 2.1 `params` theo luật

| Luật | Schema | Ràng buộc | Mặc định khi tạo |
|---|---|---|---|
| `R-CAPACITY` | `{ "minRemaining": 1 }` | `1..20` | bật, `1` |
| `R-RELIABILITY` | `{ "tiers": ["RESTRICTED"] }` | Tập con của bậc BK-02 | bật |
| `R-PARTS` | `{ "statuses": ["UNKNOWN", "ARRIVING"], "arrivingWithinDays": 3 }` | `arrivingWithinDays 1..30` | bật khi BK-09 bật, ngược lại tắt |
| `R-SLOT` | `{ "slots": [ { "weekday": 6, "startTime": "08:00", "endTime": "10:00" } ] }` | ≤ 28 khoảng, `start < end`, nằm trong giờ mở cửa | tắt, `slots: []` |
| `R-EXTRA` | `{ "quoteAboveVnd": 5000000 }` | `> 0` | tắt |

Kiểm schema bằng Pydantic (`workshop_board/rules.py`), không lưu khi sai.

**Không có dòng nào** cho xưởng ⇒ "không bật luật nào" (BR-WS01-03). Dòng mặc định chỉ được chèn khi chủ xưởng lưu màn Luật nhận lịch lần đầu.

---

# 3. `booking` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `confirmation_decision` | `varchar(16)` | Yes | `NULL` | `AUTO_RULES` (thoả mọi luật), `MANUAL_RULES` (chạm ≥ 1 luật), `MVP_AUTO`, `MVP_MANUAL` (không bật luật), `EVAL_ERROR` (EF-WS01-01). `NULL` khi lịch chưa qua bước xác nhận của chủ xe (giữ chủ động BK-01) |
| `manual_review_reasons` | `jsonb` | No | `'[]'` | Mảng lý do khi `MANUAL_RULES` / `EVAL_ERROR` |
| `confirmation_evaluated_at` | `timestamptz` | Yes | `NULL` | |

```sql
ALTER TABLE booking ADD CONSTRAINT ck_booking_conf_decision CHECK (confirmation_decision IS NULL
  OR confirmation_decision IN ('AUTO_RULES', 'MANUAL_RULES', 'MVP_AUTO', 'MVP_MANUAL', 'EVAL_ERROR'));
ALTER TABLE booking ADD CONSTRAINT ck_booking_review_reasons CHECK (
  confirmation_decision NOT IN ('MANUAL_RULES', 'EVAL_ERROR') OR jsonb_array_length(manual_review_reasons) >= 1);
CREATE INDEX ix_booking_conf_decision ON booking (workshop_id, confirmation_evaluated_at) WHERE confirmation_decision IS NOT NULL;
```

## 3.1 `manual_review_reasons[]`

```json
[ { "ruleCode": "R-RELIABILITY", "code": "CUSTOMER_TIER_RESTRICTED", "text": "Khách lỡ hẹn nhiều lần (90 ngày)" },
  { "ruleCode": "R-CAPACITY", "code": "LOW_REMAINING", "text": "Sau lịch này còn 0 chỗ trong ngày (luật: còn ≥ 1)" } ]
```

`code` cố định: `LOW_REMAINING`, `CUSTOMER_TIER_RESTRICTED`, `PARTS_UNKNOWN`, `PARTS_ARRIVING`, `MANUAL_SLOT`, `LARGE_QUOTE`, `EVALUATION_ERROR`. `text` sinh từ `code` + tham số, bằng tiếng Việt, để Board hiện ngay.

---

# 4. Business Rules (bổ sung)

## BR-ENT-WS01-01 — Chụp lại một lần

`confirmation_decision`, `manual_review_reasons` ghi một lần ở bước xác nhận của chủ xe, trong cùng transaction tạo / xác nhận lịch (FF §18). Đổi luật sau đó không sửa các cột này (AF-WS01-01). Đổi lịch (us-053) **không** đánh giá lại (lịch đã `confirmed` giữ `confirmed`).

## BR-ENT-WS01-02 — Đo M-06

`manual_rate(workshop, period) = count(MANUAL_RULES + EVAL_ERROR + MVP_MANUAL) / count(confirmation_decision IS NOT NULL)` (AC-WS01-03). PL-03 đọc từ đây.

---

# 5. Migration

- Một revision: bảng mới, 3 cột `booking`, CHECK, index.
- Không tạo dòng luật cho xưởng hiện có (giữ hành vi MVP, AC-WS01-02).
- Backfill `confirmation_decision` cho lịch cũ: `MVP_AUTO` / `MVP_MANUAL` theo sự kiện tạo trong `booking_status_event` (tạo thẳng `confirmed` ⇒ `MVP_AUTO`), để chỉ số M-06 có mốc so sánh.

---

# 6. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
