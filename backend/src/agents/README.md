# EV Care — AI Agent Orchestrator

Tài liệu thiết kế kiến trúc, cấu trúc thư mục, danh mục Tools nghiệp vụ và luồng hoạt động chi tiết của **Trợ lý AI EV Care (Agent Core)**.

---

## 1. Triết lý Thiết kế & Phạm vi (Design Philosophy & Scope)

Hệ thống AI Agent của EV Care được xây dựng dựa trên triết lý:
* **Single Orchestrator + Tools rõ ràng + Deterministic State Machine**: Không sử dụng kiến trúc Multi-Agent phức tạp ở giai đoạn này để tránh rủi ro vòng lặp vô tận (infinite loop), chi phí token cao, độ trễ lớn và khó kiểm soát dữ liệu giao dịch.
* **Deterministic kết hợp Generative**: Các tác vụ tính toán hạn bảo dưỡng, tra cứu xưởng, dự toán chi phí và giữ chỗ được giao cho các **Service & Rule Engine nghiệp vụ** của backend. LLM chịu trách nhiệm phân tích ý định, điều phối gọi tool theo thứ tự hợp lý và sinh câu trả lời tự nhiên, có trích dẫn.
* **Phạm vi giai đoạn hiện tại (Agent Core)**: 
  * Tập trung vào vòng lặp thực thi **ReAct (Reasoning + Acting)** hoàn chỉnh thông qua LangGraph.
  * Tạm hoãn cơ chế Human-In-The-Loop (HITL) phức tạp và xử lý lỗi đa tầng sang phiên bản tiếp theo để ưu tiên hoàn thành luồng nghiệp vụ chạy được ngay (runnable & testable).

---

## 2. Cấu trúc Thư mục (Directory Structure)

Toàn bộ mã nguồn của Agent được tổ chức tinh gọn trong thư mục `backend/src/agents/`:

```text
backend/src/agents/
├── README.md                      # Tài liệu kiến trúc và luồng hoạt động (file này)
├── state.py                       # Schema AgentState (messages, context xe, draft booking...)
├── prompts.py                     # System Prompts định hướng nghiệp vụ xe điện EV Care
├── graph.py                       # LangGraph StateGraph (vòng lặp: agent ⇆ tools ➔ respond)
├── orchestrator.py                # Entrypoint điều phối (run_agent_turn stream SSE)
└── tools/                         # Bộ công cụ nghiệp vụ kết nối với Service Layer backend
    ├── __init__.py                # Registry tập hợp và xuất danh sách tools cho Agent
    ├── maintenance_tools.py       # [Mới] Xác định hạng mục đến hạn theo ODO & tháng (MaintenanceRule)
    ├── cost_tools.py              # [Mới] Dự toán chi phí bảo dưỡng (ràng buộc nhận item_codes)
    ├── booking_tools.py           # [Mới] Tách riêng: find_workshops, get_available_slots (Đọc) & create_booking_draft (Ghi)
    └── RAG/                       # [Có sẵn] Engine RAG chuyên sâu trên Qdrant Cloud
        ├── ingestion/             # Luồng nạp sổ bảo dưỡng, chunking, embedding lên Qdrant
        └── query/                 # Luồng Hybrid Search (Dense+BM25), Reranker, và rag_tool.py
```

---

## 3. Danh mục Tools Nghiệp vụ (Agent Tools)

> **💡 Nguyên tắc Kiến trúc quan trọng:**
> 1. **Nạp ngữ cảnh trước Agent (Pre-loaded Context):** Thông tin xe (`model`, `current_odo`, `last_service_date`, `months_since_last`) được backend nạp trực tiếp vào `AgentState` từ phiên đăng nhập/session trước khi gọi node `agent`. Không tạo tool `get_vehicle_context` để tránh lãng phí 1 vòng lặp LLM và loại bỏ nguy cơ LLM quên gọi hoặc đoán sai thông tin xe.
> 2. **Ràng buộc phụ thuộc (Tool Chaining & Self-Correction):** `estimate_service_cost` bắt buộc phải nhận danh sách `item_codes` từ kết quả của `get_due_maintenance`. Nếu LLM gọi sai thứ tự, tool sẽ kích hoạt cơ chế Self-Correction để yêu cầu LLM chạy lại đúng quy trình.
> 3. **Phân tách Đọc / Ghi (CQRS):** Tách bạch rõ các tool tra cứu (`find_workshops`, `get_available_slots`) với tool ghi nhận dữ liệu (`create_booking_draft`). Khi bổ sung HITL ở phiên bản sau, chỉ cần gắn cổng kiểm duyệt vào tool ghi mà không ảnh hưởng tool đọc.

| Tên Tool | Loại | Đầu vào chính (Inputs) | Đầu ra chính (Outputs) | Module Backend liên kết | Trách nhiệm |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `get_due_maintenance` | **Đọc** | `model_id`, `current_odo`, `months_since_last` | Danh sách hạng mục cần làm, mốc km/tháng kích hoạt, `item_codes` | `common/core/maintenance` | Kiểm tra quy tắc bảo dưỡng theo ODO và thời gian. |
| `estimate_service_cost` | **Đọc** | `model_id`, `item_codes`, `workshop_id` | Chi phí ước tính min/max, chi tiết từng hạng mục | `modules/cost_estimate` | Tính toán giá dịch vụ tạm tính (yêu cầu `item_codes` từ bước trước). |
| `search_ev_knowledge` | **Đọc** | `query`, `model`, `category` | Đoạn trích cẩm nang kỹ thuật + Citation nguồn | `agents/tools/RAG` (Qdrant Cloud) | Tra cứu sổ tay bảo hành, hướng dẫn kỹ thuật chính hãng VinFast. |
| `find_workshops` | **Đọc** | `latitude`, `longitude` (hoặc tên khu vực) | Danh sách xưởng gần nhất, khoảng cách (km), địa chỉ | `modules/booking` (Redis GEO) | Định vị và gợi ý xưởng dịch vụ thuận tiện. |
| `get_available_slots` | **Đọc** | `workshop_id`, `target_date` | Danh sách các khung giờ trống (còn capacity) | `modules/booking/service.py` | Kiểm tra lịch trống của xưởng, trừ slot đã đầy hoặc block. |
| `create_booking_draft` | **Ghi** | `vehicle_id`, `workshop_id`, `slot_time`, `service_items` | `draft_id`, thông tin lịch giữ chỗ tạm thời (HOLD) | `modules/booking/service.py` | Tạo bản nháp lịch hẹn (giữ chỗ tạm 10 phút chống overbooking). |

---

## 4. Luồng Hoạt động Tổng thể (StateGraph Architecture)

Agent hoạt động theo mô hình **ReAct (Reasoning + Action)** trên nền tảng LangGraph StateGraph:

### 📊 Sơ đồ trực quan (ASCII Diagram — Căn chỉnh chuẩn)

```text
+------------------------------------------------------+
|            LUỒNG ĐIỀU PHỐI AGENT EV CARE             |
+------------------------------------------------------+

              [ 1. CHỦ XE GỬI YÊU CẦU ]
                          │
                          ▼
         [ Nạp ngữ cảnh xe & ODO từ Session ]
                          │
                          ▼
+──────────────────────────────────────────────────────+
| 2. LANGGRAPH RE-ACT LOOP                             |
|                                                      |
|  [Node: agent] LLM đọc Context xe & phân tích query  |
|       │                                              |
|       ├─► Cần tra cứu? ──► [Node: tools] Điều phối   |
|       │                               │              |
|       │    ┌──────────────────────────┘              |
|       │    ▼                                         |
|       │  [Tầng Công cụ: Đọc & Ghi độc lập]           |
|       │    • get_due_maintenance (quy tắc mốc)      |
|       │    • estimate_service_cost (chi phí)        |
|       │    • search_ev_knowledge (Qdrant RAG)       |
|       │    • find_workshops (tìm xưởng - Đọc)       |
|       │    • get_available_slots (giờ trống - Đọc)  |
|       │    • create_booking_draft (giữ chỗ - Ghi)   |
|       │                               │              |
|       │    ┌──────────────────────────┘              |
|       │    ▼                                         |
|       │  [Tầng Dịch vụ & DB Backend]                 |
|       │    • MaintenanceRule DB / cost_estimate     |
|       │    • Qdrant Hybrid RAG / Redis GEO & Lock   |
|       │                               │              |
|       │    └─► Trả kết quả ➔ Cập nhật State          |
|       │                               │              |
|       └◄────── (Lặp lại ReAct) ◄──────┘              |
|                                                      |
|  [Đã đủ dữ liệu]                                     |
|       │                                              |
|       ▼                                              |
|  [Node: respond] Tạo câu trả lời có trích dẫn        |
+──────────────────────────────────────────────────────+
                          │
                          ▼
            [ 3. PHẢN HỒI CHO CHỦ XE (SSE) ]
              • Giải thích nguyên nhân quá hạn
              • Báo giá chi tiết theo mốc
              • Đề xuất 2-3 khung giờ chiều thứ Bảy
```

---

<details>
<summary><b>📈 Bấm để mở Sơ đồ Mermaid đồ họa (Dành cho GitHub / Trình duyệt hỗ trợ Mermaid)</b></summary>

```mermaid
flowchart TD
    %% Subgraph Lõi điều phối LangGraph
    subgraph Orchestrator ["1. VÒNG LẶP LANGGRAPH (Lõi điều phối)"]
        direction TB
        StartNode([👤 Chủ xe gửi yêu cầu]):::term --> Preload["📋 Nạp Context Xe & ODO (Từ Session)"]:::preload
        Preload --> AgentNode["🤖 Agent Node (LLM Suy luận ý định)"]:::agent
        AgentNode --> Check{"Cần gọi Tool?"}:::decision
        Check -- "Có" --> ToolsNode["⚙️ Tools Node (Dispatcher)"]:::tools
        ToolsNode -- "Cập nhật AgentState" --> AgentNode
        Check -- "Đã đủ thông tin" --> EndNode([💬 SSE Stream phản hồi]):::term
    end

    %% Subgraph Tầng thực thi nghiệp vụ
    subgraph Execution ["2. TẦNG THỰC THI (Tools ➔ Backend Services)"]
        direction TB
        M["🛠️ Mốc & Hạng mục"]:::item <--> MS[("MaintenanceRule Database")]:::db
        C["💰 Dự toán chi phí"]:::item <--> CS[("cost_estimate Service")]:::db
        R["📚 Căn cứ chính hãng"]:::item <--> RS[("Qdrant Cloud Hybrid RAG")]:::db
        W["📍 Tìm xưởng (Đọc)"]:::item <--> WS[("booking (Redis GEO)")]:::db
        S["📅 Giờ trống (Đọc)"]:::item <--> SS[("booking Slot Capacity")]:::db
        B["📝 Giữ chỗ tạm (Ghi)"]:::item <--> BS[("booking HOLD Lock")]:::db
    end

    %% Kết nối 2 tầng
    ToolsNode ==> M
    ToolsNode ==> C
    ToolsNode ==> R
    ToolsNode ==> W
    ToolsNode ==> S
    ToolsNode ==> B

    %% Styling
    classDef term fill:#0f172a,stroke:#334155,stroke-width:2px,color:#ffffff,font-weight:bold;
    classDef preload fill:#f1f5f9,stroke:#64748b,stroke-width:1.5px,color:#0f172a;
    classDef agent fill:#eff6ff,stroke:#2563eb,stroke-width:2px,color:#1e3a8a,font-weight:bold;
    classDef decision fill:#fffbeb,stroke:#f59e0b,stroke-width:2px,color:#92400e,font-weight:bold;
    classDef tools fill:#f0fdf4,stroke:#16a34a,stroke-width:2px,color:#14532d,font-weight:bold;
    classDef item fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#0f172a;
    classDef db fill:#fdf4ff,stroke:#a855f7,stroke-width:1.5px,color:#581c87;
```
</details>

### Giải thích 3 phân vùng chính:
1. **Lõi điều phối (`LangGraph State Machine`)**:
   * `Preload`: Tự động nạp thông tin xe đang kích hoạt vào state trước khi LLM bắt đầu suy luận.
   * `agent`: Node gọi LLM. LLM nhận lịch sử chat, context xe và danh sách tools được bind.
   * `Router`: Bộ định tuyến điều kiện (`tools_condition`). Nếu LLM trả về yêu cầu `tool_calls` thì chuyển sang `tools`; nếu là câu trả lời hoàn chỉnh thì kết thúc vòng lặp để stream về UI.
   * `tools`: Node thực thi tool (`ToolNode`) và ghi nhận kết quả (ToolMessage) vào `AgentState`.
2. **Tầng Công cụ (`src/agents/tools/`)**:
   * Đóng vai trò là các Adapter chuẩn hóa dữ liệu: chuyển đổi tham số từ LLM thành các lệnh gọi hàm Python nội bộ của backend.
3. **Tầng Dịch vụ Backend (`src/modules/` & Database)**:
   * Chứa toàn bộ business logic cốt lõi (tính ODO, kiểm tra Redis GEO, trừ slot booking, tìm kiếm vector). Đảm bảo tính toán chính xác tuyệt đối (Deterministic).

---

## 5. Kịch bản Demo Chi tiết (Walkthrough Flow)

### 📌 Tình huống kiểm thử:
> **Chủ xe hỏi**: *“Xe Evo200 của tôi đi 5.760 km, lần bảo dưỡng trước là 5.100 km cách đây 7 tháng. Tôi cần làm gì và chi phí bao nhiêu? Đặt giúp lịch chiều thứ Bảy ở gần Thanh Xuân.”*

### 📊 Trình tự xử lý trực quan (ASCII Flow — Căn chỉnh chuẩn)

```text
+------------------------------------------------------+
|          KỊCH BẢN XỬ LÝ: XE EVO200 (DEMO FLOW)       |
+------------------------------------------------------+

 [CHỦ XE]: "Xe Evo200 đi 5.760km (cách lần trước 7th).  
            Cần làm gì, giá bao nhiêu? Đặt lịch chiều  
            thứ Bảy ở gần khu vực Thanh Xuân."         
     │                                                  
     ▼                                                  
 [Nạp sẵn Context]: Evo200 | ODO 5.760km | Lần cuối: 7th
     │                                                  
     ▼                                                  
+──────────────────────────────────────────────────────+
| GIAI ĐOẠN 1: TÍNH TOÁN QUY TẮC BẢO DƯỠNG ĐẾN HẠN     |
|                                                      |
|  [Agent] ──► get_due_maintenance(Evo200, 5760km, 7th)|
|               └─► Kết luận: Quá hạn mốc 6 THÁNG      |
|                   Hạng mục: Phanh, siết ốc, pin...   |
+──────────────────────────┬───────────────────────────+
                           │                            
                           ▼                            
+──────────────────────────────────────────────────────+
| GIAI ĐOẠN 2: DỰ TOÁN CHI PHÍ (RÀNG BUỘC HẠNG MỤC)    |
|                                                      |
|  [Agent] ──► estimate_service_cost(Evo200, items)    |
|               (Bắt buộc lấy item_codes từ Bước 1)    |
|               └─► Ước tính: 150.000đ - 250.000đ      |
|                   (Miễn phí tiền công mốc 6 tháng)   |
+──────────────────────────┬───────────────────────────+
                           │                            
                           ▼                            
+──────────────────────────────────────────────────────+
| GIAI ĐOẠN 3: TÌM XƯỞNG & LỌC SLOT (TÁCH BIỆT READ)   |
|                                                      |
|  [Agent] ──► find_workshops("Thanh Xuân")            |
|               └─► Xưởng VinFast Thanh Xuân (1.2 km)  |
|                                                      |
|  [Agent] ──► get_available_slots(xưởng, "Thứ Bảy")   |
|               └─► Slot trống: 14:00, 15:30, 16:30    |
+──────────────────────────┬───────────────────────────+
                           │                            
                           ▼                            
+──────────────────────────────────────────────────────+
| GIAI ĐOẠN 4: ĐỀ XUẤT LỊCH (AN TOÀN - CHƯA GHI ĐƠN)   |
|                                                      |
|  [Agent] ──► Gửi phản hồi SSE cho Chủ xe:            |
|               1. Giải thích lý do quá hạn 7 tháng    |
|               2. Báo giá dự kiến 150.000đ - 250.000đ |
|               3. Gợi ý 3 slot chiều thứ Bảy          |
|               👉 Chỉ gọi create_booking khi đã chọn! |
+──────────────────────────────────────────────────────+
```

<details>
<summary><b>📈 Bấm để mở Sơ đồ Sequence Mermaid đồ họa (Dành cho GitHub / Trình duyệt hỗ trợ Mermaid)</b></summary>

```mermaid
sequenceDiagram
    autonumber
    
    box rgb(240, 249, 255) Giao diện Người dùng
        actor User as 👤 Chủ xe (Evo200)
    end
    
    box rgb(245, 243, 255) AI Orchestrator
        participant Agent as 🤖 Agent Core
    end
    
    box rgb(240, 253, 244) Dịch vụ & Dữ liệu Backend
        participant MaintDB as 🛠️ Maintenance DB
        participant CostSvc as 💰 cost_estimate
        participant BookSvc as 📍 booking (GEO & Lock)
    end

    Note over User,Agent: Context xe đã nạp sẵn: Evo200 | 5.760 km | Lần cuối: 7 tháng trước
    User->>Agent: "Xe Evo200 đi 5.760km (lần trước 5.100km cách 7 tháng).<br/>Cần làm gì, chi phí bao nhiêu? Đặt lịch chiều thứ Bảy gần Thanh Xuân."
    activate Agent

    rect rgb(238, 242, 255)
        Note over Agent,MaintDB: GIAI ĐOẠN 1: Tính toán quy tắc bảo dưỡng
        Agent->>MaintDB: 1. get_due_maintenance(Evo200, 5.760 km, 7 tháng)
        MaintDB-->>Agent: Quá hạn mốc 6 tháng (kiểm tra phanh, siết ốc, tra dầu cổ phốt...)
    end

    rect rgb(254, 249, 195)
        Note over Agent,CostSvc: GIAI ĐOẠN 2: Tính toán dự toán chi phí (phụ thuộc Bước 1)
        Agent->>CostSvc: 2. estimate_service_cost(Evo200, items=[...])
        CostSvc-->>Agent: Ước tính: 150.000đ - 250.000đ
    end

    rect rgb(236, 253, 245)
        Note over Agent,BookSvc: GIAI ĐOẠN 3: Tìm xưởng & Khung giờ trống (Tool Đọc độc lập)
        Agent->>BookSvc: 3. find_workshops(area="Thanh Xuân")
        BookSvc-->>Agent: Xưởng VinFast Thanh Xuân (cách 1.2 km)
        Agent->>BookSvc: 4. get_available_slots(workshop_id, date="Thứ Bảy")
        BookSvc-->>Agent: Slot trống chiều T7: 14:00, 15:30, 16:30
    end

    rect rgb(255, 241, 242)
        Note over User,Agent: GIAI ĐOẠN 4: Đề xuất phương án (Chưa gọi create_booking_draft)
        Agent-->>User: Giải thích quá hạn 7 tháng, báo giá 150-250k,<br/>đề xuất 3 khung giờ chiều thứ Bảy. Chờ chủ xe xác nhận!
    end
    deactivate Agent
```
</details>

---

## 6. Giao tiếp với Module Hội thoại (`conversation`) — [Đã hoàn thành ✅]

Agent đã được cắm trực tiếp vào luồng xử lý chat của ứng dụng trong [conversation/service.py](file:///d:/lab_vinuni/AI_logs/P-146/backend/src/modules/conversation/service.py) (thay thế lệnh gọi `LLMProvider.chat_stream` đơn thuần):

```python
# Seam tích hợp LangGraph Agent Orchestrator
from src.agents.orchestrator import run_agent_turn

async for event in run_agent_turn(
    conversation_id=conversation_id,
    user_id=user_id,
    vehicle_id=vehicle.id,
    message=content,
):
    if event["type"] == "token":
        yield SseFrame(event="token", data={"delta": event["delta"]})
    elif event["type"] == "tool_start":
        yield SseFrame(event="status", data={"stage": f"Đang tra cứu {event['tool']}..."})
    elif event["type"] == "completed":
        yield SseFrame(event="message.completed", data=event["message_data"])
```

---

## 7. Lộ trình Nâng cấp Phiên bản tiếp theo (Roadmap to Post-Core)

Sau khi hoàn thiện Core Agent chạy được kịch bản trên, các tính năng tiếp theo sẽ được bổ sung:
1. **Trigger Nhắc bảo dưỡng Chủ động (Outbound Trigger từ Celery Beat)**:
   * Ở phiên bản hiện tại, Agent tập trung xử lý luồng **Inbound Chat (Chủ xe nhắn tin trước)**.
   * Ở phiên bản sau, Celery Beat hằng ngày sẽ kích hoạt Agent chạy ngầm để quét mốc ODO/thời gian của các xe ➔ tự động soạn nội dung nhắc nhở cá nhân hóa gửi qua Discord/Zalo/Notification Service.
2. **Human-In-The-Loop (HITL) Gate**: Tích hợp cơ chế ngắt nhịp (interrupt/breakpoint) của LangGraph để gắn cổng duyệt vào tool ghi `create_booking_draft` trước khi xác nhận lịch chính thức.
3. **Technician Toolset & RBAC**: Tách riêng bộ công cụ duyệt/chỉnh sửa báo giá cho Kỹ thuật viên xưởng.
4. **Structured Audit Log**: Ghi log chi tiết từng lệnh gọi tool vào bảng `agent_audit_log` của PostgreSQL để phục vụ phân tích chất lượng phản hồi và kiểm toán giao dịch.

