# Entity Specification — Báo giá phát sinh khi thay phụ tùng

> Entity cho Feature `FEAT-P2-AD04`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-04-phase2-spec.ff.md). **API:** [API Spec](ad-04-phase2-spec.api.md).
>
> **Quyết định mô hình dữ liệu (PO chốt 2026-10-12, Q-ENT-AD04-01):** FF BR-AD04-01 ghi "`quote` loại `extra`, dùng luồng duyệt F5b". Sau FF, repo đã có thiết kế đã duyệt [Báo giá hai tầng](../../../designs/bao-gia-hai-tang.md) và code `booking_line` (`kind = EXTRA`: xưởng đề xuất, chủ xe duyệt / từ chối từng dòng, ảnh `booking_line_photo`, quyết định qua app hoặc điện thoại có người ghi, cờ hạng mục an toàn). Đó chính là "phát sinh khi xe đang ở xưởng". Spec này **xây AD-04 trên `booking_line`** và chỉ thêm một bảng gom nhóm `extra_quote` cho phần FF mới (nháp của KTV, chủ xưởng duyệt trước khi gửi, giải thích của agent, ngưỡng bắt buộc đồng ý, hết thời gian). Không mở rộng `quote` (us-049) để tránh hai luồng phát sinh song song. Nghiệp vụ (ai tạo, ai duyệt, ai đồng ý, ngưỡng) giữ đúng FF.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-AD04` — AD-04 |
| Version | `v0.2` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [ad-04-phase2-spec.ff.md](ad-04-phase2-spec.ff.md) |
| Related API | [ad-04-phase2-spec.api.md](ad-04-phase2-spec.api.md) |
| Related FE | [ad-04-phase2-spec.fe.md](ad-04-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái | Thay đổi |
|---|---|---|---|---|
| `ENT-AD04-01` | `ExtraQuote` | `extra_quote` | **Mới** | Một lần báo phát sinh = một nhóm dòng |
| — | `BookingLine` | `booking_line` | Có sẵn — **thêm cột + giá trị** | `extra_quote_id`; `line_status` thêm `DRAFT`; `decided_via` thêm `NO_OBJECTION` |
| — | `BookingLinePhoto` | `booking_line_photo` | Có sẵn — không đổi | Ảnh bằng chứng (EF-AD04-01) |
| `ENT-008` | `Workshop` | `workshop` — **thêm cột** | Có sẵn | `auto_approve_extra_vnd` |

Khuyến nghị chưa làm (FF §14 `deferred_recommendation`): **không thêm bảng** — dòng `EXTRA` có `line_status = DECLINED` chính là khuyến nghị chưa làm; HS-01 đọc từ đó (AC-AD04-03).

---

# 2. `extra_quote` (ENT-AD04-01)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `booking_id` | `uuid` | No | — | FK `booking.id` `ON DELETE CASCADE`; lịch `in_progress` (hoặc `checked_in`) lúc tạo |
| `status` | `varchar(16)` | No | `'draft'` | FF §13: `draft`, `pending_approval`, `rejected`, `sent_to_owner`, `awaiting_owner`, `accepted`, `declined`, `partially_accepted` |
| `urgency` | `varchar(12)` | No | — | `SAFETY` (an toàn), `RECOMMENDED` (nên làm), `DEFERRABLE` (có thể để sau) |
| `reason` | `varchar(300)` | No | — | Lý do ngắn của KTV |
| `explanation` | `text` | Yes | `NULL` | Lời giải thích dễ hiểu (agent soạn, chủ xưởng sửa được) |
| `explanation_source` | `varchar(12)` | Yes | `NULL` | `AGENT`, `AGENT_EDITED`, `MANUAL` |
| `explanation_citations` | `jsonb` | No | `'[]'` | Trích dẫn tài liệu hãng khi agent dùng RAG |
| `created_by_actor_type` | `varchar(16)` | No | — | `technician`, `workshop_owner` |
| `created_by_technician_id` / `created_by_owner_id` | `uuid` | Yes | | Đúng một cái có giá trị |
| `approved_by_owner_id` | `uuid` | Yes | `NULL` | Người duyệt (AC-AD04-02) |
| `auto_approved` | `boolean` | No | `false` | Tự duyệt dưới `auto_approve_extra_vnd` |
| `baseline_total` | `numeric(12,2)` | No | — | Tổng ban đầu của lịch lúc gửi (§3) |
| `extras_before` | `numeric(12,2)` | No | `0` | Tổng phát sinh đã được chấp nhận trước đó của lịch (EDGE-AD04-01) |
| `this_total` | `numeric(12,2)` | No | — | Tổng dòng của lần này (giá xưởng đã duyệt) |
| `consent_required` | `boolean` | No | — | `(extras_before + this_total) / baseline_total > EXTRA_CONSENT_PCT` |
| `sent_at` | `timestamptz` | Yes | `NULL` | |
| `respond_by` | `timestamptz` | Yes | `NULL` | `sent_at + EXTRA_TIMEOUT_MIN` |
| `owner_wants_call_at` | `timestamptz` | Yes | `NULL` | Chủ xe bấm "Gọi cho xưởng" (AF-AD04-03) |
| `decided_at` | `timestamptz` | Yes | `NULL` | |
| `decided_via` | `varchar(14)` | Yes | `NULL` | `APP`, `PHONE`, `NO_OBJECTION` |
| `version` | `integer` | No | `1` | Chủ xe chỉ quyết định trên đúng phiên bản đã thấy |
| `created_at` / `updated_at` | `timestamptz` | No | `now()` | |

```sql
CREATE INDEX ix_extra_quote_booking ON extra_quote (booking_id, created_at);
CREATE INDEX ix_extra_quote_pending ON extra_quote (status, respond_by) WHERE status IN ('pending_approval', 'sent_to_owner');
ALTER TABLE extra_quote ADD CONSTRAINT ck_extra_quote_status CHECK (status IN
  ('draft','pending_approval','rejected','sent_to_owner','awaiting_owner','accepted','declined','partially_accepted'));
ALTER TABLE extra_quote ADD CONSTRAINT ck_extra_quote_creator CHECK (
  (created_by_actor_type = 'technician') = (created_by_technician_id IS NOT NULL)
  AND (created_by_actor_type = 'workshop_owner') = (created_by_owner_id IS NOT NULL));
ALTER TABLE extra_quote ADD CONSTRAINT ck_extra_quote_approval CHECK (
  status IN ('draft','pending_approval','rejected') OR auto_approved OR approved_by_owner_id IS NOT NULL);
-- AC-AD04-01: vượt ngưỡng không thể "accepted" qua NO_OBJECTION.
ALTER TABLE extra_quote ADD CONSTRAINT ck_extra_quote_consent CHECK (
  NOT (consent_required AND status IN ('accepted','partially_accepted') AND decided_via = 'NO_OBJECTION'));
```

`partially_accepted`: chủ xe đồng ý một số dòng, từ chối dòng khác (giữ khả năng duyệt từng dòng của báo giá hai tầng).

---

# 3. `baseline_total`

Tổng ban đầu của lịch để so ngưỡng (BR-AD04-04), chụp lúc gửi:
1. `pricing_flow = two_tier`: Σ giá tính phí các dòng `PACKAGE` (`confirmed_price` hoặc `unit_price`) — không gồm phần bảo hành chi trả.
2. `legacy` có báo giá us-049 đã duyệt: tổng báo giá.
3. Không có ⇒ `booking.estimated_cost`.
4. Vẫn không có (0 / `NULL`) ⇒ `consent_required = true` (không có mốc so sánh thì luôn hỏi).

---

# 4. `booking_line` — thay đổi

| Thay đổi | Chi tiết |
|---|---|
| Cột `extra_quote_id uuid NULL` | FK `extra_quote.id` `ON DELETE CASCADE`; bắt buộc với dòng `EXTRA` tạo từ Phase 2 (dòng `EXTRA` MVP cũ để `NULL`) |
| `line_status` thêm `DRAFT` | Dòng của `extra_quote` chưa gửi; **chủ xe không thấy** dòng `DRAFT` |
| `decided_via` thêm `NO_OBJECTION` | Dòng dưới ngưỡng được chấp nhận vì chủ xe không phản đối trong `EXTRA_TIMEOUT_MIN` |
| Cột `urgency` | Không thêm: `is_safety_critical = (extra_quote.urgency = SAFETY)` ghi xuống từng dòng để code MVP (cảnh báo hạng mục an toàn) dùng tiếp |

```sql
ALTER TABLE booking_line DROP CONSTRAINT ck_booking_line_status;
ALTER TABLE booking_line ADD CONSTRAINT ck_booking_line_status CHECK (line_status IN
  ('DRAFT','PENDING_CONFIRM','CONFIRMED','PROPOSED','APPROVED','DECLINED','WITHDRAWN'));
ALTER TABLE booking_line DROP CONSTRAINT ck_booking_line_extra_status;
ALTER TABLE booking_line ADD CONSTRAINT ck_booking_line_extra_status CHECK (
  kind = 'PACKAGE' OR line_status IN ('DRAFT','PROPOSED','APPROVED','DECLINED','WITHDRAWN'));
ALTER TABLE booking_line DROP CONSTRAINT ck_booking_line_decided_via;
ALTER TABLE booking_line ADD CONSTRAINT ck_booking_line_decided_via
  CHECK (decided_via IS NULL OR decided_via IN ('APP','PHONE','NO_OBJECTION'));
CREATE INDEX ix_booking_line_extra_quote ON booking_line (extra_quote_id) WHERE extra_quote_id IS NOT NULL;
```

Ánh xạ trạng thái nhóm ↔ dòng:

| `extra_quote.status` | `booking_line.line_status` |
|---|---|
| `draft`, `pending_approval` | `DRAFT` |
| `rejected` | `WITHDRAWN` |
| `sent_to_owner`, `awaiting_owner` | `PROPOSED` |
| `accepted` / `declined` / `partially_accepted` | `APPROVED` / `DECLINED` theo từng dòng |

---

# 5. `workshop` — cột mới

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `auto_approve_extra_vnd` | `numeric(12,2)` | Yes | `NULL` | `NULL` = tắt tự duyệt (mặc định, P2Q-13). Có giá trị ⇒ phát sinh có `this_total` < giá trị này được tự duyệt |

---

# 6. Lưu vết (BR-AD04-08)

Không dùng `booking_status_event` (bảng đó chỉ cho trạng thái booking). Lưu vết bằng các cột thời điểm + người trên `extra_quote` và `booking_line` (`proposed_by`, `confirmed_by`, `decided_by`, `decided_via`, `phone_confirmed_by`, `recorded_by` — có sẵn) cộng `technician_audit_log` (WS-03) cho thao tác của KTV. Đủ để trả lời "ai tạo, ai duyệt, lúc nào, chủ xe phản hồi gì".

---

# 7. Migration

Một revision: bảng `extra_quote`, cột `booking_line.extra_quote_id`, thay 3 CHECK, cột `workshop.auto_approve_extra_vnd`. Không backfill (dòng `EXTRA` cũ giữ nguyên, không có nhóm).

---

# 8. Open Questions

| ID | Câu hỏi | Đề xuất |
|---|---|---|
| `Q-ENT-AD04-01` | Xây AD-04 trên `booking_line` (báo giá hai tầng) thay vì `quote` loại `extra` như FF BR-AD04-01? | **Đã chốt 2026-10-12:** có; FF v0.3 đã sửa |
| `Q-ENT-AD04-02` | Lịch `legacy` (không phải `two_tier`) có dùng AD-04 không? | Có: tạo dòng `EXTRA` như nhau; chỉ `baseline_total` khác (§3) |

---

# 9. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
| `v0.2` | `2026-10-12` | PO chốt xây trên `booking_line` (Q-ENT-AD04-01) |
