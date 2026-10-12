# API Technical Specification — Tư vấn phụ tùng và báo giá sửa chữa

> Backend cho Feature `FEAT-P2-AD02`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-02-phase2-spec.ff.md). **Entity:** [Entity Spec](ad-02-phase2-spec.entity.md).
>
> **Tái dùng:** RAG có trích nguồn (`agents/tools/RAG`, AI-002; no-source-no-claim), guard đầu ra, `SchedulerService.rank_workshops` (AD-01) để chọn ≤ 3 xưởng, `PartsAvailabilityService` (BK-09), báo giá HITL us-049 (`POST /quotes`) cho "Xin xưởng báo giá", `SchedulerService.run` (BK-01) với `serviceKind = REPAIR`, thẻ CH-02, chip CH-01. LLM không tính và không viết số giá (thẻ lấy từ tool).

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-AD02` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/repair_pricing/` (mới: bảng giá, tra khoảng giá), `backend/src/agents/tools/repair_tools.py`, `backend/src/agents/safety/` (bộ phát hiện dấu hiệu an toàn) |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-AD02-01` | `GET` | `/workshop-owner/repair-prices?modelId&q` | Bảng giá sửa chữa của xưởng | UC-AD02-05 |
| `API-AD02-02` | `PUT` | `/workshop-owner/repair-prices/{itemCode}` | Nhập / sửa một dòng | UC-AD02-05 |
| `API-AD02-03` | `POST` | `/workshop-owner/repair-prices/import` | Tải CSV | SCR-AD02-03 |
| `API-AD02-04` | `GET` | `/repair-items?q&modelId` | Danh mục hạng mục (tìm, gợi ý) | — |
| `API-AD02-05` | `GET` | `/user-vehicles/{userVehicleId}/repair-estimates?itemCodes` | Khoảng giá ≤ 3 xưởng (cho thẻ và màn ngoài chat) | UC-AD02-01 |
| `SVC-AD02-01` | Internal | `SafetySignalDetector.detect(text)` | Phát hiện dấu hiệu an toàn | BR-AD02-04, 06 |
| `TOOL-AD02-01` | Agent tool | `repair_advice` | Hạng mục có thể liên quan + khoảng giá | UC-AD02-01, 02 |
| `TOOL-AD02-02` | Agent tool | `request_repair_quote` | Xin xưởng báo giá (F5b) | UC-AD02-04 |

---

# 2. Authorization & Guards

`API-AD02-01..03`: chủ xưởng (KTV không sửa bảng giá, WS-03). `API-AD02-04`: mọi người dùng đăng nhập. `API-AD02-05`: chủ xe, xe của mình.

---

# 3. Bảng giá sửa chữa

## 3.1 `PUT /workshop-owner/repair-prices/{itemCode}`

```json
{ "modelId": "VF8", "partPriceMin": "1100000", "partPriceMax": "1300000", "laborPrice": "250000", "durationMin": 60 }
```

Kiểm CHECK entity §3 ⇒ `400 INVALID_REQUEST`; `itemCode` không có trong `repair_item` ⇒ `404 REPAIR_ITEM_NOT_FOUND`. Giá trị không đổi ⇒ không chạm `updated_at`. `{ "delete": true }` ⇒ xoá dòng.

## 3.2 `POST …/import` (CSV)

`multipart/form-data`, ≤ 1 MB, UTF-8, cột `item_code,model_id,part_price_min,part_price_max,labor_price,duration_min`. Kiểm từng dòng; **chạy thử** khi `?dryRun=true` trả lỗi theo dòng; thật ⇒ upsert trong một transaction (lỗi dòng nào ⇒ không ghi dòng nào). Response `{ "inserted": 12, "updated": 6, "errors": [ { "row": 4, "code": "RANGE_INVALID" } ] }`.

---

# 4. SVC-AD02-01 — `SafetySignalDetector`

- Chạy **trước** agent trong mọi lượt chat chủ xe (sau guard đầu vào): khớp mẫu `signals.yaml` trên câu đã chuẩn hoá (bỏ dấu, chữ thường).
- Khớp ⇒ đặt `turn.safety = { group, matched }` trong `RunnableConfig`; graph đi nhánh an toàn: trả lời theo mẫu an toàn của nhóm (không LLM cho phần hướng dẫn, LLM chỉ thêm câu mở đầu đồng cảm, qua guard), thẻ `SAFETY_ADVICE`, **không gọi** `repair_advice` / tool giá trong lượt này (BR-AD02-04, UC-AD02-03).
- Mục tiêu recall 100 % trên bộ eval ≥ 20 câu (AC-AD02-01); chấp nhận dương tính giả.

`SAFETY_ADVICE` card: `{ group, title, steps[] (từ cấu hình), hotline: { workshopName, phone } (xưởng yêu thích hoặc gần nhất), actions: [CHIP "Đặt lịch kiểm tra sớm nhất" (book_now với serviceKind REPAIR, itemCodes theo nhóm, ưu tiên khung sớm nhất)] }`. Hotline hiện dạng chữ chọn được.

---

# 5. TOOL-AD02-01 — `repair_advice`

| | |
|---|---|
| Args (LLM thấy) | `symptom?` (câu chủ xe), `part_query?` (tên phụ tùng), `model?` (mặc định model xe của hội thoại, EDGE-AD02-02) |
| Bước 1 | `part_query` ⇒ khớp `repair_item` theo tên / `synonyms`. `symptom` ⇒ RAG trên tài liệu hãng (bộ lọc model) lấy đoạn nêu hạng mục; ánh xạ đoạn → `item_code` qua `synonyms`. Chỉ giữ hạng mục có ≥ 1 trích nguồn (AC-AD02-03); tối đa 3, xếp theo điểm RAG (EDGE-AD02-01). Không có nguồn ⇒ `{ "items": [], "reason": "NO_SOURCE" }` (EF-AD02-01) |
| Bước 1b | Triệu chứng chưa đủ rõ (RAG không đạt ngưỡng, chưa hỏi đủ 2 lượt) ⇒ `{ "needsClarification": true, "chips": ["Tiếng kêu", "Rung", "Đèn cảnh báo", "Khi nào xảy ra"] }` (AF-AD02-01); sau 2 lượt vẫn mơ hồ ⇒ đề xuất `GENERAL_CHECK` |
| Bước 2 | `rank_workshops(limit = 3)` (AD-01) ⇒ với mỗi xưởng: `repair_price` theo model; `stock` từ BK-09 khi bật |
| Trả về | `{ items: [{ itemCode, name, citations[] }], workshops: [{ workshopId, name, distanceKm, lines: [{ itemCode, partMin, partMax, labor, priceUpdatedAt, stale, stock }], missingPrice: bool }], disclaimer: "Cần KTV kiểm tra để xác nhận" }` |
| Thẻ | `REPAIR_ADVICE` (CH-02): dữ liệu như trên + `actions`: CHIP "Đặt lịch thay {hạng mục}" (`booking.repair` với `itemCodes`), LINK "So sánh xưởng", CHIP "Xin xưởng báo giá" khi `missingPrice` |
| Prompt | "Chỉ nêu hạng mục có trong kết quả tool, luôn kèm 'có thể liên quan' và 'cần KTV kiểm tra để xác nhận'. Không nêu con số giá nào (thẻ hiển thị giá). Không tư vấn phụ tùng ngoài; nếu được hỏi, chỉ nêu điều khoản bảo hành có nguồn (EF-AD02-02)." |
| Guard đầu ra | Chặn câu có một số tiền duy nhất kiểu giá cuối ("hết 1.200.000đ") (AC-AD02-02); chặn khẳng định chẩn đoán ("chắc chắn là") |

Khoảng giá hiển thị: phụ tùng `partMin–partMax`, tiền công riêng (BR-AD02-07). Không cộng thành một số.

---

# 6. Đặt lịch từ tư vấn (AF-AD02-02, AC-AD02-04)

Chip `booking.repair` ⇒ `SchedulerService.run(serviceKind = REPAIR, itemCodes = […], reportedSymptom = <câu chủ xe>)` (BK-01 thêm tham số `reportedSymptom`). Phương án ⇒ `booking_proposal` mang `reported_symptom`, `repair_item_codes` ⇒ khi xác nhận (`API-QB-02`), booking ghi `reported_symptom`, `reported_symptom_items`, `service_kind = REPAIR`, thời lượng = Σ `repair_price.duration_min` (WS-02). Không tạo `booking_line` giá cho hạng mục sửa chữa lúc đặt (giá chốt khi xưởng kiểm tra xe — AD-04 / báo giá hai tầng).

---

# 7. TOOL-AD02-02 — `request_repair_quote`

Gọi luồng us-049 có sẵn để tạo yêu cầu báo giá với `items = itemCodes` (loại `REPAIR`) gửi xưởng được chọn (UC-AD02-04). Chỉ tạo khi chủ xe bấm chip (tác dụng phụ ⇒ thẻ tóm tắt + xác nhận, CH-01 BR-CH01-05). Trả `{ quoteId, status: "SUBMITTED" }`; thẻ `QUOTE` có sẵn.

> Ghi chú: thiết kế "báo giá hai tầng" đã chuyển phần lớn báo giá sang lúc nhận xe. Yêu cầu báo giá trước khi đặt lịch chỉ còn dùng cho sửa chữa thiếu giá (UC-AD02-04); nếu PO quyết định bỏ hẳn us-049, chip này đổi thành "Đặt lịch kiểm tra" (Q-API-AD02-01).

---

# 8. API-AD02-05 — `repair-estimates`

Như output bước 2 của `repair_advice` nhưng gọi trực tiếp (màn ngoài chat, ví dụ từ chi tiết lịch sử HS-01 "Đặt lịch làm tiếp"). Query `itemCodes` (1–3), `workshopIds?`.

---

# 9. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 400 | `INVALID_REQUEST` | Khoảng giá sai, CSV sai định dạng |
| 404 | `REPAIR_ITEM_NOT_FOUND` | |
| 413 | `FILE_TOO_LARGE` | CSV > 1 MB |

---

# 10. Eval & Test Checklist

| Layer | What | Count |
|---|---|---|
| Eval | Bộ ≥ 20 câu dấu hiệu an toàn ⇒ 100 % có lời khuyên an toàn trước, không giá trong lượt (AC-AD02-01) | 1 bộ |
| Eval | Không câu trả lời nào nêu một số giá duy nhất như giá cuối (AC-AD02-02) | 1 bộ |
| Eval | Mọi hạng mục nêu ra có ≥ 1 trích nguồn hợp lệ (AC-AD02-03) | 1 bộ |
| Unit | Khớp `synonyms` có / không dấu | +3 |
| Unit | Khoảng giá: thiếu giá ⇒ `missingPrice`; cũ ⇒ `stale` | +2 |
| Service | Đặt lịch từ tư vấn ⇒ booking có `reported_symptom` (AC-AD02-04) | +1 |
| API | CSV chạy thử không ghi; lỗi một dòng ⇒ không ghi dòng nào | +2 |
| Agent | Không nguồn ⇒ không nêu hạng mục, gợi ý kiểm tra (EF-AD02-01) | +1 |

---

# 11. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
