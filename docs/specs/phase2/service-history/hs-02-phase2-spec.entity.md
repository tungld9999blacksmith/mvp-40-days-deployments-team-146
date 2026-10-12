# Entity Specification — Gộp việc vào một lần đến xưởng

> Entity cho Feature `FEAT-P2-HS02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](hs-02-phase2-spec.ff.md). **API:** [API Spec](hs-02-phase2-spec.api.md).
>
> **Nguyên tắc:** gợi ý gộp được **tính khi dựng thẻ** (không lưu bảng gợi ý). Lưu (1) dữ liệu triệu hồi / cập nhật phần mềm đồng bộ từ hãng (cũng dùng cho TA-01 tóm tắt xe), (2) lựa chọn gộp trên đề xuất và trên dòng của lịch, (3) việc chủ xe bỏ chọn triệu hồi để không gợi ý lại trong 30 ngày.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-HS02` — HS-02 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [hs-02-phase2-spec.ff.md](hs-02-phase2-spec.ff.md) |
| Related API | [hs-02-phase2-spec.api.md](hs-02-phase2-spec.api.md) |
| Related FE | [hs-02-phase2-spec.fe.md](hs-02-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-HS02-01` | `RecallCampaign` | `recall_campaign` | **Mới** |
| `ENT-HS02-02` | `VehicleRecall` | `vehicle_recall` | **Mới** |
| `ENT-HS02-03` | `MergeDismissal` | `merge_dismissal` | **Mới** |
| `ENT-475` | `BookingProposal` | `booking_proposal` — **thêm cột** `merged_items` | Có sẵn |
| — | `BookingLine` | `booking_line` — **thêm cột** `merge_source`, `recall_campaign_id` | Có sẵn |

---

# 2. `recall_campaign` (ENT-HS02-01) & `vehicle_recall` (ENT-HS02-02)

`recall_campaign`:

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `id` | `uuid` | No | PK |
| `external_campaign_id` | `varchar(64)` | No | Unique, id của hãng |
| `kind` | `varchar(16)` | No | `RECALL`, `SOFTWARE_UPDATE`, `SERVICE_CAMPAIGN` |
| `title` | `varchar(200)` | No | |
| `description` | `text` | Yes | |
| `item_code` | `varchar(50)` | No | Hạng mục tương ứng (thời lượng WS-02, kỹ năng WS-03) |
| `free_of_charge` | `boolean` | No | Thường `true` |
| `starts_on` / `ends_on` | `date` | Yes | |
| `synced_at` | `timestamptz` | No | |

`vehicle_recall`:

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `user_vehicle_id` | `uuid` | No | PK (1/2), FK `user_vehicle.id` `ON DELETE CASCADE` |
| `campaign_id` | `uuid` | No | PK (2/2), FK `recall_campaign.id` |
| `status` | `varchar(12)` | No | `OPEN`, `COMPLETED` (hãng báo đã làm, EDGE-HS02-01), `NOT_APPLICABLE` |
| `completed_at` | `date` | Yes | |
| `synced_at` | `timestamptz` | No | |

Đồng bộ từ hãng theo VIN (P2Q-06) trong job; VIN không lưu thêm ở bảng này (đã có trên `user_vehicle`). Không có dữ liệu ⇒ không gợi ý triệu hồi (EF-HS02-01).

---

# 3. `merge_dismissal` (ENT-HS02-03)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `user_vehicle_id` | `uuid` | No | PK (1/3) |
| `source` | `varchar(10)` | No | PK (2/3): `RECALL`, `DUE_SOON`, `DEFERRED` |
| `ref_key` | `varchar(80)` | No | PK (3/3): `campaign_id` / `item_code` / `booking_line_id` |
| `until` | `date` | No | Hôm nay + 30 ngày (EDGE-HS02-02) |

Ghi khi chủ xe **bỏ chọn** một mục được chọn sẵn (triệu hồi). Mục tính phí không chọn sẵn ⇒ không ghi (không chọn ≠ từ chối).

---

# 4. Cột mới

| Bảng | Cột | Type | Ghi chú |
|---|---|---|---|
| `booking_proposal` | `merged_items` | `jsonb NOT NULL DEFAULT '[]'` | `[{ source, refKey, itemCode, name, estimate, durationMin, freeOfCharge }]` chủ xe đã chọn; dùng khi xác nhận tạo booking |
| `booking_line` | `merge_source` | `varchar(10) NULL` | `RECALL`, `DUE_SOON`, `DEFERRED`, `COHORT` (PS-04) cho dòng gộp; `NULL` = dòng gốc |
| `booking_line` | `recall_campaign_id` | `uuid NULL` | FK `recall_campaign.id` |

Dòng gộp là `kind = PACKAGE` (chủ xe đã đồng ý trước khi đặt, không cần quyết định lại như `EXTRA`); triệu hồi miễn phí ⇒ `unit_price = 0`, `is_covered_by_warranty = true`. Khuyến nghị chưa làm được gộp ⇒ dòng mới `PACKAGE` với `merge_source = DEFERRED`, dòng `DECLINED` cũ giữ nguyên (lịch sử).

---

# 5. Business Rules (bổ sung)

## BR-ENT-HS02-01 — Không thêm tính phí khi chưa chọn

Chỉ mục có trong `merged_items` (do chủ xe gửi) mới thành dòng; validator từ chối mọi mục tính phí không do chủ xe chọn (AC-HS02-01).

## BR-ENT-HS02-02 — Gộp mốc kế tiếp

Dòng `DUE_SOON` thuộc mốc kế tiếp ⇒ sau khi hoàn tất, bản ghi `EV_CARE` của HS-01 ghi `is_periodic = true` cho mốc đó; F3 vẫn chỉ tính mốc từ lịch sử hãng (BK-03 BR-ENT-BK03-02) — khi hãng đồng bộ lần làm, mốc kế tiếp tính từ ngày / ODO thực tế (BR-HS02-06).

---

# 6. Migration

Một revision: 3 bảng, 3 cột. Mock hãng thêm endpoint chiến dịch (P2Q-06).

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
