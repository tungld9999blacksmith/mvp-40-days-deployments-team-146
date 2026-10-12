# Entity Specification — Tư vấn phụ tùng và báo giá sửa chữa

> Entity cho Feature `FEAT-P2-AD02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-02-phase2-spec.ff.md). **API:** [API Spec](ad-02-phase2-spec.api.md).
>
> **Nguyên tắc:** bảng giá sửa chữa tách khỏi `service_price` (giá hạng mục bảo dưỡng theo mốc, giá một con số) vì sửa chữa cần **khoảng giá phụ tùng + tiền công riêng + thời lượng** (BR-AD02-03, BR-AD02-07). Hạng mục sửa chữa dùng một danh mục chuẩn để xưởng, RAG và BK-09 nói cùng một mã.

---

# 0. Document Information

| Field | Value |
|---|---|
| Feature | `FEAT-P2-AD02` — AD-02 |
| Version | `v0.1` |
| Status | `Draft` |
| Owner | Backend Team |
| Created Date | `2026-10-12` |
| Related FF | [ad-02-phase2-spec.ff.md](ad-02-phase2-spec.ff.md) |
| Related API | [ad-02-phase2-spec.api.md](ad-02-phase2-spec.api.md) |
| Related FE | [ad-02-phase2-spec.fe.md](ad-02-phase2-spec.fe.md) |

---

# 1. Entity Catalog

| Entity ID | Entity | Table | Trạng thái |
|---|---|---|---|
| `ENT-AD02-01` | `RepairItem` | `repair_item` | **Mới** — danh mục hạng mục sửa chữa chuẩn |
| `ENT-AD02-02` | `RepairPrice` | `repair_price` | **Mới** — bảng giá sửa chữa theo xưởng |
| `ENT-402` | `Booking` | `booking` — **thêm cột** `reported_symptom`, `reported_symptom_items` | Có sẵn |
| `ENT-475` | `BookingProposal` | `booking_proposal` — **thêm cột** `reported_symptom`, `repair_item_codes` | Có sẵn (us-061) |
| — | `official_document` / `document_chunk` | Không đổi | Nguồn RAG |

---

# 2. `repair_item` (ENT-AD02-01)

| Column | Type | Null | Ghi chú |
|---|---|---|---|
| `item_code` | `varchar(50)` | No | PK, ví dụ `BRAKE_PAD_FRONT`, `TIRE_235_55R19` |
| `name_vi` | `varchar(200)` | No | "Má phanh trước" |
| `category` | `varchar(16)` | No | Nhóm HS-01 (`BRAKE`, `TIRE`, …) — dùng cho kỹ năng KTV (WS-03) |
| `model_ids` | `jsonb` | No | Model áp dụng (`[]` = mọi model) |
| `oem_part_numbers` | `jsonb` | No | Mã phụ tùng hãng tương thích (BK-09 khớp tồn kho) |
| `synonyms` | `jsonb` | No | Cách gọi khác ("bố thắng", "má thắng") để khớp câu hỏi |
| `is_safety_related` | `boolean` | No | Hạng mục an toàn (gắn cờ khi thành dòng `booking_line`) |
| `active` | `boolean` | No | |

Seed bởi nhóm dữ liệu từ tài liệu hãng + 20 hạng mục phổ biến (Q-AD02-02). Không có API ghi cho người dùng.

---

# 3. `repair_price` (ENT-AD02-02)

| Column | Type | Null | Default | Ghi chú |
|---|---|---|---|---|
| `id` | `uuid` | No | `gen` | PK |
| `workshop_id` | `uuid` | No | — | FK `workshop.id` `ON DELETE CASCADE` |
| `model_id` | `varchar(64)` | No | — | `*` = mọi model |
| `item_code` | `varchar(50)` | No | — | FK `repair_item.item_code` |
| `part_price_min` | `numeric(12,2)` | No | — | `≥ 0` |
| `part_price_max` | `numeric(12,2)` | No | — | `≥ part_price_min` |
| `labor_price` | `numeric(12,2)` | No | — | Tiền công, hiển thị riêng (BR-AD02-07) |
| `duration_min` | `smallint` | No | — | Thời lượng (WS-02 dùng khi đặt lịch sửa chữa) |
| `updated_at` | `timestamptz` | No | `now()` | Chỉ đổi khi giá trị đổi |
| `updated_by_owner_id` | `uuid` | Yes | `NULL` | |

```sql
CREATE UNIQUE INDEX ux_repair_price ON repair_price (workshop_id, model_id, item_code);
ALTER TABLE repair_price ADD CONSTRAINT ck_repair_price_range
  CHECK (part_price_min >= 0 AND part_price_max >= part_price_min AND labor_price >= 0 AND duration_min BETWEEN 5 AND 600);
CREATE INDEX ix_repair_price_item ON repair_price (item_code, model_id);
```

Tra giá cho xe: dòng `model_id = <model xe>` trước, không có thì `*`. Cũ hơn `PRICE_STALE_DAYS` ⇒ cảnh báo (EF-AD02-03).

---

# 4. Cột mới

| Bảng | Cột | Type | Ghi chú |
|---|---|---|---|
| `booking` | `reported_symptom` | `varchar(500) NULL` | Nguyên văn chủ xe kể (BR-AD02-05, AC-AD02-04); TA-01 hiển thị "Khách mô tả" |
| `booking` | `reported_symptom_items` | `jsonb NOT NULL DEFAULT '[]'` | `item_code` hạng mục có thể liên quan agent đã nêu (kèm nguồn) |
| `booking_proposal` | `reported_symptom`, `repair_item_codes` | `varchar(500) NULL`, `jsonb NOT NULL DEFAULT '[]'` | Mang triệu chứng từ thẻ đề xuất sang booking khi xác nhận |

`reported_symptom` là dữ liệu chủ xe tự kể: không lọc nội dung y tế / cá nhân khác ngoài guard đầu vào hiện có; giới hạn 500 ký tự. Xoá theo booking.

---

# 5. Dấu hiệu an toàn (BR-AD02-06)

Không phải bảng: cấu hình trong code `agents/safety/signals.yaml` (mẫu từ khoá + regex tiếng Việt có / không dấu, nhóm `BRAKE_FAILURE`, `HV_BATTERY_WARNING`, `SMOKE`, `BURNING_SMELL`, `LEAK`), phiên bản hoá theo git, có bộ eval riêng (`eval/datasets/safety_signals`). Dùng chung với F9 (follow-up) nếu F9 đã có danh sách — gộp thành một nguồn.

---

# 6. Migration

Một revision: 2 bảng, 4 cột, index, CHECK; seed `repair_item`.

---

# 7. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
