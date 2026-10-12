# API Technical Specification — Tư vấn bảo hành và gói bảo hành

> Backend cho Feature `FEAT-P2-AD03`.
>
> **Nguồn nghiệp vụ:** [Functional Spec](ad-03-phase2-spec.ff.md). **Entity:** [Entity Spec](ad-03-phase2-spec.entity.md).
>
> **Tái dùng:** `vehicle_warranty` + đồng bộ hãng (`oem_integration`, `infrastructure/oem`), RAG `warranty_policy` (AI-002, no-source-no-claim, PQ-07), `CostEstimationService` (F5) cho phép so sánh gói, PL-02 chuyển người thật (tranh chấp), thẻ CH-02, guard đầu ra.

---

# 0. Document Information

| Field | Value |
|---|---|
| Document ID | `API-SPEC-P2-AD03` |
| Version | `v0.1` |
| Status | `Draft` |
| Base URL | `/api/v1` |
| Module | `backend/src/modules/warranty/` (mới: `coverage.py`, `plans.py`, `route.py`, `jobs.py`), `agents/tools/warranty_tools.py` |
| Created Date | `2026-10-12` |

---

# 1. API Group

| API ID | Method | Endpoint | Mục đích | FF |
|---|---|---|---|---|
| `API-AD03-01` | `GET` | `/user-vehicles/{userVehicleId}/warranty` | Bảo hành theo thành phần của xe (SCR-AD03-01) | UC-AD03-01, BR-AD03-01 |
| `API-AD03-02` | `GET` | `/user-vehicles/{userVehicleId}/warranty-plans/compare?planId` | So sánh gói với trả từng lần (SCR-AD03-02) | UC-AD03-03, BR-AD03-03 |
| `TOOL-AD03-01` | Agent tool | `get_vehicle_warranty` | Trả thời hạn từ dữ liệu hãng | UC-AD03-01 |
| `TOOL-AD03-02` | Agent tool | `warranty_policy_qa` | RAG điều kiện / quy trình có nguồn | UC-AD03-02 |
| `TOOL-AD03-03` | Agent tool | `compare_warranty_plan` | Phép tính gói minh bạch | UC-AD03-03 |
| `HOOK-AD03-01` | Internal | Ý định tranh chấp ⇒ PL-02 `create_handoff(reason = WARRANTY_DISPUTE)` | | UC-AD03-04, BR-AD03-04 |
| `JOB-AD03-01` | Celery | `warranty.refresh` (hằng tuần + khi hỏi nếu > 7 ngày) | Làm mới từ hãng | BR-AD03-01 |
| `JOB-AD03-02` | Celery | `warranty.sync_plans` (hằng ngày) | Đồng bộ danh mục gói | Q-AD03-01 |

---

# 2. Authorization & Guards

Chủ xe; xe của mình (`get_owned_vehicle_readonly`). Tool chỉ nhận `user_vehicle_id` nội bộ từ `RunnableConfig` — VIN không bao giờ vào prompt hay output của tool (BR-AD03-05).

---

# 3. API-AD03-01 — bảo hành của xe

```json
{ "data": {
    "source": "OEM", "lastRefreshedAt": "2026-10-10T03:00:00Z", "odoKm": 23400, "odoAsOf": "2026-10-10",
    "components": [
      { "component": "battery", "label": "Pin cao áp", "status": "ACTIVE", "endDate": "2032-04-01", "kmLimit": 200000,
        "remainingDays": 1997, "remainingKm": 176600, "termsCitation": { "documentId": "…", "title": "Chính sách bảo hành", "version": "2025" } }
    ],
    "unavailableReason": null } }
```

- `components` từ `vehicle_warranty` (entity §2: hiệu lực tính khi đọc). Không có dòng nào ⇒ `components = []`, `unavailableReason = "NO_VEHICLE_WARRANTY_DATA"`; tool / UI nói rõ "chưa có dữ liệu riêng của xe" rồi mới trả lời theo tài liệu chung (UC-AD03-01 nhánh C-Không).
- `lastRefreshedAt` > 7 ngày ⇒ trả dữ liệu đang có **và** đẩy `JOB-AD03-01` cho xe đó.
- EDGE-AD03-01: dữ liệu xe và tài liệu chung mâu thuẫn ⇒ dùng dữ liệu xe; `notes: ["OEM_DATA_DIFFERS_FROM_POLICY"]`.

---

# 4. API-AD03-02 — so sánh gói (BR-AD03-03)

Query `planId` (bắt buộc). Xử lý:

1. Gói `active`, áp dụng model xe, xe thoả `eligibility` ⇒ không thì `eligible = false` + lý do (không so sánh).
2. **Giả định** (trả về rõ ràng): km/tháng = trung bình 6 tháng ODO đồng bộ (`vehicle_usage` có sẵn; < 2 điểm ODO ⇒ 1.500 km/tháng mặc định, ghi rõ là mặc định); thời hạn = `duration_months` hoặc tới `km_limit`, cái nào đến trước.
3. Liệt kê các mốc bảo dưỡng rơi vào thời hạn theo giả định (F3 lịch mốc) ∩ hạng mục của gói (`warranty_plan_item`).
4. **Trả từng lần** = Σ `CostEstimationService.estimate` (giá xưởng yêu thích / gần nhất, nhãn "ước tính") cho các mốc đó, chỉ phần hạng mục gói bao gồm. Gói bảo hành mở rộng: không quy ra tiền rủi ro (không đoán xác suất hỏng) — chỉ liệt kê thành phần + thời hạn tăng thêm.
5. Trả `{ planPrice, payAsYouGoEstimate, difference, milestonesCovered[], assumptions[], citations[] }`. Không có trường "khuyến nghị mua" (không bán hàng).

Không có danh mục gói ⇒ `404 NO_PLAN_CATALOG` (EF-AD03-02).

---

# 5. Tools

| Tool | Hành vi |
|---|---|
| `get_vehicle_warranty(component?)` | Như API-AD03-01, lọc thành phần; trả `status`, `endDate`, `kmLimit`, `remaining*`; xe hết bảo hành thành phần ⇒ `EXPIRED` và prompt không thêm cảnh báo mất bảo hành (AF-AD03-01, quy tắc F7) |
| `warranty_policy_qa(question)` | RAG chỉ trên `documentType = warranty_policy` (bộ lọc metadata có sẵn), ngưỡng điểm như AI-002; không đạt ⇒ `{ "found": false }` ⇒ trả lời "Tài liệu hãng chưa nêu điều này, bạn nên hỏi xưởng" (EF-AD03-01, PQ-07) |
| `compare_warranty_plan(plan_name?)` | Khớp tên gói ⇒ API-AD03-02; thẻ `WARRANTY_PLAN_COMPARE` |

Thẻ:
- `WARRANTY_STATUS` (CH-02): dữ liệu API-AD03-01; `actions`: CHIP "Đặt lịch mốc {km}" khi xe có mốc sắp đến (giữ bảo hành bằng bảo dưỡng đúng mốc — câu này chỉ nói khi có trích nguồn chính sách).
- `WARRANTY_PLAN_COMPARE`: dữ liệu API-AD03-02.

Prompt: "Mọi khẳng định về điều kiện / quy trình bảo hành phải kèm trích dẫn từ `warranty_policy_qa`. Không tự nêu ân hạn, ngưỡng mất bảo hành. Không phán xử tranh chấp." Guard đầu ra: câu có cụm điều kiện bảo hành ("mất bảo hành", "không được bảo hành", "được bảo hành nếu") mà lượt không có citation ⇒ thay bằng câu từ chối khẳng định (AC-AD03-02).

---

# 6. HOOK-AD03-01 — tranh chấp

Router ý định (AI-001) thêm ý định `WARRANTY_DISPUTE` (mẫu: "xưởng từ chối bảo hành", "không chịu bảo hành", "khiếu nại bảo hành"). Khớp ⇒ không gọi tool tư vấn; gọi PL-02 `create_handoff(reason = WARRANTY_DISPUTE, summary = …)` và trả lời theo mẫu chuyển người (AC-AD03-03).

---

# 7. Jobs

- `warranty.refresh`: gọi hãng (mock) `GET /vehicles/{vin}/warranties` theo VIN lưu ở `user_vehicle` (chỉ trong job, không log VIN); payload đổi (`source_payload_hash`) ⇒ upsert `vehicle_warranty`, `last_refreshed_at`. Lỗi hãng ⇒ giữ dữ liệu cũ, log.
- `warranty.sync_plans`: `GET /plans` ⇒ upsert `warranty_plan` / `warranty_plan_item`; gói biến mất ⇒ `active = false`.
- Mock hệ thống hãng (`backend/mock-ev-system`) thêm hai endpoint trên + seed (P2Q-05).

---

# 8. Error Cases

| HTTP | Code | Khi |
|---|---|---|
| 404 | `VEHICLE_NOT_FOUND` | |
| 404 | `NO_PLAN_CATALOG` / `PLAN_NOT_FOUND` | Chưa có danh mục / gói không tồn tại |

---

# 9. Eval & Test Checklist

| Layer | What | Count |
|---|---|---|
| Unit | Hiệu lực thành phần theo ngày + km; `km_limit NULL` | +4 |
| Service | Thời hạn trả về khớp dữ liệu mock hãng (AC-AD03-01) | +2 |
| Service | So sánh gói: giả định được trả về; mặc định km/tháng khi thiếu ODO; xe không đủ điều kiện | +3 |
| Eval | 100 % câu khẳng định điều kiện có trích nguồn (AC-AD03-02) | 1 bộ |
| Eval | 100 % câu tranh chấp được chuyển người (AC-AD03-03) | 1 bộ |
| Security | VIN không xuất hiện trong prompt / output tool (quét LangSmith trace trong test) | +1 |

---

# 10. Change Log

| Version | Date | Change |
|---|---|---|
| `v0.1` | `2026-10-12` | Bản nháp đầu |
