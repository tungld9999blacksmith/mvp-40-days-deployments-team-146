# BÁO CÁO NGHIỆM THU KIẾN TRÚC
## TÍCH HỢP TẦNG DỊCH VỤ BACKEND & BẢO VỆ GIAO DỊCH (BACKEND SERVICE INTEGRATION)
### Hệ thống Trợ lý AI Thông minh EV Care

> **Bộ kiểm thử tự động:** 15/15 tests PASSED (100% Green)

---

### 1. Tổng quan mục tiêu kiến trúc

Phân hệ **Tích hợp Tầng Dịch vụ Backend & Bảo vệ Giao dịch (Backend Service Integration)** giải quyết bài toán cốt lõi: **Chuyển đổi AI Agent EV Care từ mô hình demo/mock cục bộ sang kiến trúc tích hợp thực tế với Backend Service Layer, PostgreSQL và Redis**, tuân thủ nghiêm ngặt các nguyên lý kỹ thuật:
- **"Tool mỏng – Service sở hữu nghiệp vụ" (Hexagonal Architecture / Ports & Adapters)**: LLM chỉ đóng vai trò phân tích ý định, điều phối công cụ và diễn đạt ngôn ngữ tự nhiên. Toàn bộ logic nghiệp vụ, tính toán chi phí, phân bổ năng lực xưởng và ràng buộc dữ liệu thuộc về Backend Service Layer.
- **Tách biệt CQRS (Command Query Responsibility Segregation)**: Các thao tác Đọc (truy vấn xưởng, kiểm tra slot trống, dự toán nhẩm chi phí) không được phép làm phát sinh dữ liệu Ghi (không tự ý lưu bản ghi `Quote` hoặc tạo `Booking` khi chưa đủ điều kiện).
- **An toàn giao dịch & Bảo vệ IDOR**: Ngữ cảnh định danh (`user_id`, `vehicle_id`) được nạp tự động từ backend đã xác thực qua `RunnableConfig`, LLM tuyệt đối không được tự ý can thiệp hoặc nhận tham số ID người dùng.
- **Triệt tiêu ảo giác (Zero Hallucination)**: Chuẩn hóa kết quả trả về `ToolResult`, phân giải ngày giờ tự nhiên tiếng Việt, và loại bỏ hoàn toàn các citation/dữ liệu giả định.

---

### 2. Các thành quả kỹ thuật đã triển khai (Deliverables)

#### 2.1. Chuẩn hóa giao thức kết quả công cụ — `ToolResult`
- **Tệp nguồn:** [backend/src/agents/tools/result.py](./tools/result.py)
- **Đặc tả:** Mọi công cụ hệ thống đều trả về cấu trúc thống nhất:
  ```json
  {
    "status": "ok | empty | error",
    "code": "Mã định danh nghiệp vụ hoặc lỗi (ví dụ: TIMEOUT, NOT_FOUND, PREREQUISITE_MISSING)",
    "data": { ... },
    "hint": "Chỉ dẫn an toàn, trung thực để LLM diễn đạt cho người dùng khi status != 'ok'"
  }
  ```
- **Khả năng tương thích ngược 100%:** Hỗ trợ đầy đủ các phương thức `__getitem__`, `__len__`, `__iter__`, `__contains__`, `get()`. Các mã nguồn và unit test cũ gọi dạng dict (`result["item_codes"]`, `workshops[0]`, `len(workshops)`) tiếp tục hoạt động trơn tru không lỗi.

#### 2.2. Ngữ cảnh bảo mật chống truy cập chéo (IDOR) — `AgentCtx`
- **Tệp nguồn:** [backend/src/agents/context.py](./context.py)
- **Đặc tả:** Đóng gói định danh đáng tin cậy (`user_id`, `vehicle_id`, `conversation_id`, `source_message_id`, `operation_key`, `tz`).
- **Cơ chế truyền:** Nạp qua `RunnableConfig` (`config={"configurable": {"ctx": agent_ctx, "thread_id": ...}}`). LLM không nhìn thấy các trường ID này trong tool arguments, loại bỏ triệt để tấn công Prompt Injection và truy cập chéo dữ liệu xe.

#### 2.3. Lớp bọc an toàn thực thi — `@tool_guard`
- **Tệp nguồn:** [backend/src/agents/tools/guard.py](./tools/guard.py)
- **Tính năng:**
  - Thiết lập timeout nghiêm ngặt cho từng tool (mặc định 5.0s, chặn kẹt luồng).
  - Bắt toàn bộ ngoại lệ hạ tầng (DB ngắt kết nối, lỗi mạng) và chuyển hóa thành `ToolResult(status='error', code='INTERNAL_ERROR')` kèm câu gợi ý an toàn `hint`. Tuyệt đối không để lộ chuỗi kết nối DB/Redis ra giao diện chat.
  - Hàm `is_mock_enabled()`: Bắt buộc trả về `False` trên môi trường production, chỉ cho phép mock khi dev chạy offline có cờ tường minh.

#### 2.4. Kiến trúc Ports & Adapters (Hexagonal Architecture)
- **Tệp nguồn:** [backend/src/agents/tools/ports.py](./tools/ports.py) và [backend/src/agents/tools/adapters.py](./tools/adapters.py)
- **Tính năng:**
  - Định nghĩa 3 Protocol chuẩn mực: `BookingPort`, `CostPort`, `MaintenancePort`.
  - Cung cấp Fake Ports (`FakeBookingPort`, `FakeCostPort`, `FakeMaintenancePort`) và Dependency Injection Registry (`set_booking_port`, `get_booking_port`,...) giúp chạy test cô lập cực nhanh mà không cần khởi động PostgreSQL/Redis.
  - Các Default Adapters (`DefaultBookingAdapter`, `DefaultCostAdapter`, `DefaultMaintenanceAdapter`) kết nối trực tiếp với backend data access layer.

#### 2.5. Module phân giải ngày giờ tự nhiên tiếng Việt — `resolve_date`
- **Tệp nguồn:** [backend/src/agents/tools/resolve_date.py](./tools/resolve_date.py)
- **Tính năng:**
  - Xử lý ngày ISO (`YYYY-MM-DD`), ngày Việt Nam (`DD/MM/YYYY`, `DD/MM`).
  - Xử lý từ khóa tương đối ("hôm nay", "ngày mai", "ngày kia").
  - Xử lý thứ trong tuần: "chiều thứ Bảy" -> phân giải chính xác ngày thứ Bảy gần nhất. Nếu hôm nay đã quá giờ làm việc (>= 17:00), tự động đề xuất thứ Bảy tuần kế tiếp.
  - Tách bạch buổi và giờ hẹn: "chiều" -> `session='afternoon'`, `target_time=None`, **không tự tiện gán một giờ cố định** khi khách chưa chỉ định.

#### 2.6. Tách bạch CQRS (Dự toán chi phí vs Báo giá duyệt)
- **Tệp nguồn:** [backend/src/agents/tools/cost_tools.py](./tools/cost_tools.py) và [backend/src/agents/tools/booking_tools.py](./tools/booking_tools.py)
- **Tính năng:**
  - `estimate_service_cost`: Chỉ tính toán dự toán tham khảo dựa trên chính sách bảo hành VinFast (tiền công 0đ) và vật tư tiêu hao. Không tạo thực thể `Quote` vào database, không tự gán `approved_by="system"`.
  - `create_booking_draft`: Nhận tham số `quote_id` tùy chọn, chỉ tạo phiếu hẹn giữ chỗ tạm thời trong 10 phút (`status='HOLD'`, mã `EVC-...`). Giữ nguyên các trạng thái chuẩn của DB (`pending`, `confirmed`), không tạo enum lạ ngoài schema.

#### 2.7. Triệt tiêu nguy cơ Double Booking & Trung thực hóa Citations
- **Tệp nguồn:** [backend/src/agents/orchestrator.py](./orchestrator.py), [backend/src/agents/graph.py](./graph.py) và [backend/src/modules/conversation/service.py](../modules/conversation/service.py)
- **Tính năng:**
  - **Chống Double Booking:** Loại bỏ hoàn toàn khối `except` tự ý chạy lại `agent.ainvoke(initial_state)` khi SSE stream bị ngắt kết nối giữa chừng.
  - **Truy vấn ODO và lịch sử thật:** `fetch_vehicle_context` đọc trực tiếp số km lớn nhất từ `VehicleOdometerReading` và lịch sử định kỳ gần nhất từ `VehicleServiceRecord`. Nếu xe chưa có dữ liệu, trả `None` để Agent lịch sự hỏi khách hàng, không tự fake về `0`.
  - **Citations trung thực:** Bỏ đoạn code tự tạo cẩm nang giả định `DOC-VINFAST-OFFICIAL`. Chỉ đính kèm trích dẫn khi có tài liệu RAG thực tế hoặc sổ tay bảo dưỡng theo mốc km được xác nhận.

---

### 3. Bảng đối chiếu nâng cấp hệ thống

| Tiêu chuẩn kỹ thuật | Phiên bản Mock/Thử nghiệm ban đầu | Phiên bản Tích hợp Backend hoàn thiện |
| :--- | :--- | :--- |
| **Nguồn dữ liệu xe** | Dùng số km giả định hoặc fallback `0 km`. | Truy vấn trực tiếp từ `VehicleOdometerReading` & `VehicleServiceRecord`. |
| **Dự toán chi phí** | Có nguy cơ tạo Quote giả danh duyệt tự động. | CQRS Read thuần túy, tính nhẩm minh bạch, Quote là tùy chọn. |
| **Định dạng kết quả Tool** | Dict tự do, khó kiểm soát lỗi. | [ToolResult](./tools/result.py) chuẩn hóa `{status, code, data, hint, for_llm()}`. |
| **Xử lý ngày hẹn** | Chuỗi text thô, dễ gán giờ sai lệch. | Module [resolve_date](./tools/resolve_date.py) hiểu ngữ cảnh tiếng Việt và timezone Việt Nam. |
| **Bảo vệ đứt kết nối stream** | Tự chạy lại `ainvoke` (nguy cơ đặt lịch 2 lần). | Trả thông báo lỗi an toàn, bảo vệ trạng thái giao dịch một chiều. |
| **Bảo vệ quyền truy cập (IDOR)** | LLM có thể truyền sai hoặc giả mạo vehicle_id. | Ngữ cảnh nạp tự động vào `AgentCtx`, LLM không can thiệp ID. |
| **Kiểm thử tự động** | 5 tests cơ bản. | **15 tests** toàn diện từ Tool, Date Resolver, Ports đến SSE Stream. |

---

### 4. Báo cáo kết quả kiểm thử (Test Execution Report)

Toàn bộ 15 test cases trong 3 test suites đã được thực thi và vượt qua 100%:

```bash
pytest backend/tests/test_agents/test_ev_care_tools.py \
       backend/tests/test_agents/test_backend_integration.py \
       backend/tests/test_modules/test_conversation_agent_stream.py -v
```

```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: D:\lab_vinuni\AI_logs\P-146
configfile: pytest.ini
collected 15 items

backend/tests/test_agents/test_ev_care_tools.py::test_get_due_maintenance_evo200_overdue PASSED        [  6%]
backend/tests/test_agents/test_ev_care_tools.py::test_estimate_service_cost_guardrail_dependency_error PASSED [ 13%]
backend/tests/test_agents/test_ev_care_tools.py::test_estimate_service_cost_with_valid_items PASSED   [ 20%]
backend/tests/test_agents/test_ev_care_tools.py::test_find_workshops_and_slots PASSED                 [ 26%]
backend/tests/test_agents/test_ev_care_tools.py::test_create_booking_draft_hold PASSED                [ 33%]
backend/tests/test_agents/test_backend_integration.py::test_tool_result_contract_and_for_llm PASSED  [ 40%]
backend/tests/test_agents/test_backend_integration.py::test_tool_result_backwards_compatibility PASSED [ 46%]
backend/tests/test_agents/test_backend_integration.py::test_tool_guard_sync_success_and_exception PASSED [ 53%]
backend/tests/test_agents/test_backend_integration.py::test_tool_guard_async_timeout PASSED          [ 60%]
backend/tests/test_agents/test_backend_integration.py::test_resolve_date_iso_and_vietnamese_format PASSED [ 66%]
backend/tests/test_agents/test_backend_integration.py::test_resolve_date_relative_keywords PASSED    [ 73%]
backend/tests/test_agents/test_backend_integration.py::test_resolve_date_weekday_and_afternoon PASSED [ 80%]
backend/tests/test_agents/test_backend_integration.py::test_resolve_date_specific_time PASSED        [ 86%]
backend/tests/test_agents/test_backend_integration.py::test_agent_ctx_and_port_di PASSED             [ 93%]
backend/tests/test_modules/test_conversation_agent_stream.py::test_chat_service_run_turn_with_agent_orchestrator PASSED [100%]

============================= 15 passed in 21.88s =============================
```

---

### 5. Lộ trình phát triển tiếp theo (Next Architectural Milestones)

Hệ thống đã sẵn sàng các điểm cắm (*integration seams*) chuẩn xác để chuyển sang các giai đoạn tính năng nâng cao:

1. **Quy trình Phê duyệt Đa bên & Human-in-the-Loop (Multi-Party Approval & HITL Workflow):** Tích hợp LangGraph `interrupt()` và checkpointer (PostgresSaver) để tạm dừng đợi duyệt và resume phiên hội thoại khi có tương tác từ Chủ xe hoặc Xưởng dịch vụ.
2. **Nhắc lịch Bảo dưỡng Thông minh Chủ động (Automated Outbound Reminder):** Tự động phát hiện xe đến hạn và kích hoạt AI tạo thông điệp nhắc bảo dưỡng cá nhân hóa.
3. **Quan sát Toàn diện, Giám sát & Kiểm toán (Observability, Audit Trail & Evaluation):** Bảng kiểm toán `agent_audit_log`, dashboard theo dõi latency, token usage, và đánh giá chất lượng hội thoại theo thời gian.
4. **Bộ Công cụ Chẩn đoán Kỹ thuật viên (Technician Diagnostics Toolset):** Hỗ trợ xưởng tra cứu mã lỗi DTC chuyên sâu và tối ưu hóa quy trình bảo dưỡng.
