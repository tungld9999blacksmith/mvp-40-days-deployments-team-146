# AI Agent MVP — Eval Evidences

## 1. Tổng quan đánh giá

| Thuộc tính | Giá trị |
|---|---|
| Ngày thực hiện | 04/10/2026 |
| Branch | `main` |
| Source commit | `876aea3` |
| LLM cấu hình | `gemini-3.5-flash-lite` |
| Python | 3.13.11 |
| Phạm vi | AI Agent MVP, business tools và service layer hiện hành |
| Số test case manual | 6 |
| Kết quả | **6 PASS, 0 PARTIAL, 0 FAIL** |

Evaluation gồm một walkthrough End-to-End sử dụng Gemini API thật và năm case kiểm chứng trực tiếp các tool. TC-01 chạy từ câu hỏi người dùng qua LangGraph, gọi business tools và stream câu trả lời cuối. TC-02 đến TC-06 chạy cùng implementation tool trên SQLite in-memory và fakeredis với dữ liệu seed cố định, giúp output có thể tái lập mà không ghi vào dữ liệu production.

## 2. Lệnh tái lập

Chạy toàn bộ 6 manual eval cases:

```bash
uv run --project backend --group dev --frozen \
  --with 'langchain-google-genai>=2.0.0' \
  python backend/tests/test_agents/agent_manual_eval.py
```

Kết quả thực tế:

```json
{
  "total": 6,
  "PASS": 6,
  "PARTIAL": 0,
  "FAIL": 0
}
```

Kiểm tra chất lượng source của runner:

```bash
uv run --project backend --group dev --frozen \
  ruff check backend/tests/test_agents/agent_manual_eval.py
```

```text
All checks passed!
```

Test regression độc lập cho walkthrough orchestrator:

```bash
uv run --project backend --group dev --frozen \
  --with 'langchain-google-genai>=2.0.0' \
  pytest backend/tests/test_agents/test_agent_orchestrator.py -s -q
```

## 3. Tiêu chí đánh giá

- **PASS:** tất cả checks của case đều đúng.
- **PARTIAL:** chức năng chính hoạt động nhưng còn check chất lượng không đạt.
- **FAIL:** thiếu output bắt buộc, gọi sai tool, sai dữ liệu nghiệp vụ hoặc vi phạm guardrail.

Các output dưới đây được trích trực tiếp từ lần chạy thực tế. UUID, thời gian và `proposal_id` được tạo mới ở mỗi lần chạy nên có thể thay đổi khi tái lập.

## 4. Bảng kết quả

| ID | Kịch bản | Tiêu chí chính | Kết quả |
|---|---|---|---|
| TC-01 | Walkthrough End-to-End với Gemini thật | Tool chain đúng, có mốc/giá/slot, không tự tạo proposal | PASS |
| TC-02 | Đọc trạng thái bảo dưỡng | Đúng xe, ODO 11.500 km, mốc 12.000 km | PASS |
| TC-03 | Thiếu authenticated chat context | Từ chối an toàn, không lộ dữ liệu xe | PASS |
| TC-04 | Dự toán tại xưởng | Dùng giá xưởng 350.000 VND | PASS |
| TC-05 | Tìm xưởng và slot | Đúng xưởng, đúng ngày, có slot khả dụng | PASS |
| TC-06 | Đề xuất đặt lịch | Tạo proposal/card, chưa tạo booking | PASS |

## 5. Evidence chi tiết

### TC-01 — Walkthrough End-to-End với Gemini thật

**Mục tiêu:** chứng minh một lượt Agent hoàn chỉnh từ prompt đến LLM orchestration, business tools và câu trả lời cuối.

**Input thực tế**

```text
Xe của tôi sắp tới cần bảo dưỡng gì và chi phí bao nhiêu?
Tìm giúp tôi khung giờ chiều thứ Bảy ở xưởng VinFast Thanh Xuân.
```

**Tool trace thực tế**

```json
[
  "find_workshops",
  "get_due_maintenance",
  "get_available_slots",
  "estimate_service_cost"
]
```

**Trích đoạn output LLM thực tế**

```text
Xe VF6 hiện tại đã đi được 11.500 km và đang sắp đến hạn bảo dưỡng
mốc 12.000 km / 12 tháng, còn khoảng 500 km và 11 ngày.

Các hạng mục gồm kiểm tra pin cao áp và kiểm tra hệ thống phanh.
Tổng chi phí dự kiến tại VinFast Thanh Xuân là 350.000 VNĐ.

Các khung giờ chiều thứ Bảy ngày 10/10/2026:
- 13:00
- 14:00
- 15:00
- 16:00

Vui lòng chọn giờ cụ thể để hệ thống tạo đề xuất đặt lịch.
```

**Checks thực tế**

```json
{
  "maintenance_called": true,
  "cost_called": true,
  "maintenance_before_cost": true,
  "slots_called": true,
  "no_premature_proposal": true,
  "answer_has_milestone": true,
  "answer_has_cost": true,
  "answer_has_slots": true
}
```

**Latency:** `6663.36 ms`  
**Kết quả:** **PASS**.

### TC-02 — Đọc đúng trạng thái bảo dưỡng của xe trong phiên

**Mục tiêu:** xác nhận tool dùng xe từ authenticated chat context và đọc đúng dữ liệu service layer.

**Output thực tế rút gọn**

```json
{
  "due_status": "DUE_SOON",
  "due_reason": "BOTH",
  "next_milestone": {
    "odo_milestone_km": 12000,
    "month_milestone": 12,
    "due_date": "2026-10-15",
    "items": [
      {"item_code": "BATTERY_CHECK", "is_covered_by_warranty": true},
      {"item_code": "BRAKE_INSPECTION", "is_covered_by_warranty": false}
    ]
  },
  "remaining_km": 500,
  "remaining_days": 11,
  "odometer": {
    "odo_km": 11500,
    "data_source": "OEM"
  }
}
```

**Checks thực tế**

```json
{
  "correct_vehicle": true,
  "odometer_11500": true,
  "next_milestone_12000": true,
  "has_maintenance_items": true
}
```

**Kết quả:** **PASS**.

### TC-03 — Guardrail khi thiếu authenticated chat context

**Mục tiêu:** xác nhận tool không nhận user/vehicle tùy ý từ LLM và từ chối khi thiếu context đáng tin cậy.

**Output thực tế**

```json
{
  "status": "ERROR",
  "error_code": "CHAT_CONTEXT_MISSING",
  "message": "The tool needs the owner and the vehicle of the chat session."
}
```

**Checks thực tế**

```json
{
  "status_error": true,
  "context_error": true,
  "no_vehicle_data_leaked": true
}
```

**Kết quả:** **PASS**.

### TC-04 — Dự toán dùng bảng giá của xưởng

**Input thực tế**

```json
{
  "odo_milestone": 12000,
  "workshop_id": "<generated-workshop-uuid>"
}
```

**Output thực tế rút gọn**

```json
{
  "status": "READY",
  "milestone": {
    "odo_milestone": 12000,
    "month_milestone": 12,
    "is_next": true
  },
  "workshop": {
    "name": "VinFast Thanh Xuân",
    "selected_by": "REQUEST"
  },
  "items": [
    {
      "item_code": "BATTERY_CHECK",
      "covered": true,
      "price": 0
    },
    {
      "item_code": "BRAKE_INSPECTION",
      "covered": false,
      "price": 350000,
      "price_source": "WORKSHOP_PRICE"
    }
  ],
  "chargeable_total": 350000,
  "currency": "VND"
}
```

**Checks thực tế**

```json
{
  "status_ready": true,
  "correct_workshop": true,
  "workshop_price_source": true,
  "brake_price_350000": true
}
```

**Kết quả:** **PASS**.

### TC-05 — Tìm xưởng và khung giờ từ service layer

**Input thực tế**

```json
{
  "area_or_address": "Hà Nội",
  "target_date": "2026-10-07"
}
```

**Output thực tế rút gọn**

```json
{
  "workshops": [
    {
      "name": "VinFast Thanh Xuân",
      "region": "Hà Nội",
      "is_preferred": true
    }
  ],
  "slots": {
    "date": "2026-10-07",
    "available": ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]
  }
}
```

**Checks thực tế**

```json
{
  "expected_workshop_found": true,
  "correct_workshop_id": true,
  "correct_date": true,
  "has_available_slots": true
}
```

**Kết quả:** **PASS**.

### TC-06 — Tạo đề xuất đặt lịch, chưa tự tạo booking

**Mục tiêu:** xác nhận Agent chỉ tạo proposal/card và vẫn yêu cầu chủ xe xác nhận; không tự tạo booking có side effect.

**Input thực tế**

```json
{
  "workshop_id": "<generated-workshop-uuid>",
  "booking_date": "2026-10-07",
  "time_slot": "09:00",
  "odo_milestone": 12000
}
```

**Output thực tế rút gọn**

```json
{
  "status": "PROPOSED",
  "summary": "Đề xuất VinFast Thanh Xuân lúc 09:00 ngày 2026-10-07.",
  "next_step": "Chủ xe bấm Xác nhận đặt lịch trên thẻ để đặt. Lịch CHƯA được tạo.",
  "artifact": {
    "type": "BOOKING_PROPOSAL",
    "vehicle": {
      "modelName": "VF6",
      "licensePlateMasked": "30A***45"
    },
    "primary": {
      "workshopName": "VinFast Thanh Xuân",
      "date": "2026-10-07",
      "timeSlot": "09:00",
      "estimate": {
        "chargeableTotal": "350000.00",
        "coveredCount": 1
      }
    }
  },
  "proposal_count": 1,
  "booking_count": 0
}
```

**Checks thực tế**

```json
{
  "status_proposed": true,
  "proposal_card_created": true,
  "proposal_persisted": true,
  "no_booking_created": true,
  "requires_owner_confirmation": true
}
```

**Kết quả:** **PASS**.

## 6. Ma trận chất lượng

| Khía cạnh | Evidence | Kết luận |
|---|---|---|
| LLM orchestration | TC-01 | Gemini gọi đúng tool chain và tổng hợp câu trả lời đầy đủ |
| Trusted context / IDOR guard | TC-02, TC-03 | Tool lấy owner/vehicle từ config và từ chối khi thiếu context |
| Business correctness | TC-02, TC-04 | Mốc, hạng mục, bảo hành và giá xưởng đúng dữ liệu seed |
| Workshop availability | TC-05 | Khu vực, workshop ID, ngày và sức chứa nhất quán |
| Side-effect safety | TC-01, TC-06 | Không đề xuất sớm; proposal không tự tạo booking |
| Reproducibility | Runner + Ruff | Một lệnh chạy đủ 6 case; source runner vượt lint |

## 7. Phạm vi và giới hạn

Báo cáo chứng minh luồng Agent MVP, business tools và service composition hoạt động với LLM thật trên môi trường evaluation có dữ liệu seed. SQLite in-memory và fakeredis được dùng để bảo vệ dữ liệu production và tạo kết quả tái lập.

Báo cáo chưa đánh giá tải đồng thời, lỗi mạng kéo dài, persistence PostgreSQL/Redis production, frontend UI hoặc chất lượng RAG. Các nội dung này có test suite và báo cáo riêng.

## 8. Kết luận tổng thể

Kết quả **6 PASS, 0 PARTIAL, 0 FAIL** cho thấy AI Agent MVP đã đáp ứng đầy đủ các hành vi cốt lõi được đánh giá. Hệ thống chạy End-to-End với Gemini thật, sử dụng trusted vehicle context, gọi tool theo đúng chuỗi nghiệp vụ, đọc dữ liệu bảo dưỡng, lập dự toán từ bảng giá xưởng, tìm khung giờ và tạo thẻ đề xuất đặt lịch.

Guardrail quan trọng cũng được xác nhận: tool từ chối khi thiếu authenticated context, Agent không tạo proposal trước khi người dùng chọn giờ, và `propose_booking` chỉ lưu đề xuất chứ không tự tạo booking. Với phạm vi MVP hiện tại, hệ thống đủ điều kiện phục vụ demo và review kỹ thuật; các bước production hardening được tách khỏi kết luận này.
