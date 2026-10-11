# Hướng dẫn Dev — AI-Agent EV Care

> **D6** trong [work-scope-clarification.md](../../docs/specs/ai-agent/work-scope-clarification.md). Hướng dẫn **thực hành** cho dev: hiểu cấu trúc code agent, vòng đời một lượt chat từ client, cách thêm tool/guardrail, cách test & chạy eval.
>
> Tài liệu **kiến trúc chi tiết** nằm ở [backend/src/agents/README.md](../src/agents/README.md); quy ước đặt tên ở [backend/guide/agent.md](agent.md). File này tập trung "làm thế nào".

---

## 1. Bản đồ nhanh (mental model)

```
Client (web/app)
   │  POST /conversations/{id}/messages   (SSE stream)
   ▼
ChatService            ── modules/conversation/service.py
   │  gọi orchestrator, chuyển event → SSE, lưu chat_message
   ▼
AgentOrchestrator      ── agents/orchestrator.py  (run_agent_turn)
   │  nạp context xe, chạy graph, phát token/tool_start/completed
   ▼
LangGraph StateGraph   ── agents/graph.py   (ReAct loop: agent ⇄ tools → respond)
   │
   ├─ node "agent"  : LLM (Gemini) đọc context + lịch sử, quyết định tool_calls
   ├─ node "tools"  : ToolNode chạy tool đã bind
   └─ (điều kiện)   : còn tool_calls → quay lại agent; hết → kết thúc, stream
        │
        ▼
Tools (agents/tools/*.py) ──► Services backend (modules/*) ──► DB / Qdrant / Redis
```

**3 nguyên tắc bất biến** (đừng phá khi sửa code):
1. **Danh tính từ session, không từ LLM.** `user_id`, `user_vehicle_id` lấy từ `RunnableConfig["configurable"]` do `run_agent_turn` truyền, không bao giờ từ tham số LLM sinh. → LLM không thao tác được trên xe người khác.
2. **Deterministic tách Generative.** Tính mốc/giá/slot nằm ở service backend; LLM chỉ gọi tool và diễn giải, **không tự cộng số**.
3. **Confirm trước side-effect.** `propose_booking` chỉ tạo *thẻ đề xuất*; booking thật tạo khi chủ xe bấm "Xác nhận" (API-QB-02). Không tool nào tự ghi đơn.

---

## 2. Cấu trúc thư mục

```text
backend/src/agents/
├── orchestrator.py     # Entrypoint: run_agent_turn (stream SSE), confirm_booking_turn
├── graph.py            # StateGraph: node agent/tools, bind LLM + tools, checkpointer
├── state.py            # AgentState (messages, vehicle_context, draft...)
├── prompts.py          # System prompt nghiệp vụ EV
├── dependency.py       # Composition root (cache graph + orchestrator theo process)
└── tools/
    ├── __init__.py         # build_customer_agent_tools() — registry tools
    ├── dependency.py       # AgentToolServices (factory session + services)
    ├── _services.py        # dựng service thật từ config phiên chat
    ├── guard.py            # tool_guard decorator (timeout + che exception)
    ├── result.py           # ToolResult chuẩn hoá {status, data, code, hint}
    ├── maintenance_tools.py, cost_tools.py, booking_tools.py
    └── RAG/                # ingestion/ + query/ (hybrid, reranker, citation)
```

---

## 3. Vòng đời một lượt chat (chi tiết)

1. **Client** gửi message tới endpoint conversation; nhận lại **SSE stream**.
2. **ChatService** lấy context xe (model, ODO, trạng thái bảo hành/đến hạn) + lịch sử, gọi:
   ```python
   async for event in self._orchestrator.run_agent_turn(
       conversation_id=..., user_id=..., vehicle_id=vehicle.id,
       message=content, vehicle_context=vehicle_context,
       history_messages=history_messages, source_message_id=...,
       operation_key=str(client_message_id),
   ):
       if event["type"] == "token":      yield SseFrame("token", {"delta": event["delta"]})
       elif event["type"] == "tool_start": yield SseFrame("status", {"stage": f"Đang tra cứu {event['tool']}..."})
       elif event["type"] == "completed":  citations = event["message_data"]["citations"]
   ```
3. **Orchestrator** chạy graph ReAct: node `agent` (LLM) → nếu có `tool_calls` → node `tools` → quay lại `agent`; khi LLM trả lời hoàn chỉnh → stream token + citation.
4. **ChatService** lưu câu trả lời qua `MessageService` rồi phát `message.completed`.

**Event agent phát ra:** `token` (delta text), `tool_start` (bắt đầu gọi tool), `completed` (xong, kèm `message_data` có citations/artifact). UI dựa vào đây để stream + hiện trạng thái "đang tra cứu".

---

## 4. Thêm một tool mới (công thức)

1. **Viết factory tool** trong `tools/<verb>_tools.py` theo đúng mẫu hiện có: hàm `build_<area>_tools(services)` trả về list các hàm `@tool`. Danh tính lấy từ `config: RunnableConfig` qua `_services.caller`, **không** để LLM truyền:
   ```python
   def build_maintenance_tools(services: AgentToolServices | None = None) -> list[BaseTool]:
       provider = services if services is not None else _services

       @tool
       def get_due_maintenance(config: RunnableConfig) -> dict[str, Any]:
           """Tình trạng bảo dưỡng của xe đang chọn trong phiên chat (TOOL-VEH-001).
           Không cần truyền tham số: xe lấy từ phiên chat. Returns: due_status, next_milestone, ...
           """
           with provider.open_session() as session:
               try:
                   who = _services.caller(session, config)          # danh tính từ session
                   service = provider.user_vehicle_service(session)
                   vehicle = service.get_owned_active_vehicle(who.user, who.user_vehicle_id)
                   return service.get_maintenance_status(vehicle).model_dump(mode="json")
               except (_services.MissingCallerError, vehicle_errors.UserVehicleError) as exc:
                   return _services.tool_error(exc)   # dict lỗi an toàn, không raw exception

       return [get_due_maintenance]
   ```
   - **Đầu vào nghiệp vụ** (odo_milestone, workshop_id…) do LLM sinh; **danh tính** (user/vehicle) lấy từ `config`, **không** để LLM truyền.
   - Lỗi nghiệp vụ → trả dict lỗi an toàn (`_services.tool_error`), **không raise raw exception** ra LLM. Dùng `@tool_guard` ([guard.py](../src/agents/tools/guard.py)) khi cần timeout/che exception tập trung.
   - Docstring tool chính là **schema LLM đọc** để quyết định gọi — mô tả rõ *khi nào dùng* + *trả về gì*.
2. **Đăng ký** trong `tools/__init__.py` (`CUSTOMER_AGENT_TOOLS` / `build_customer_agent_tools`) — bind với `AgentToolServices` qua closure để dependency không lọt vào schema gửi LLM.
3. **Định nghĩa schema LangChain** (docstring + type hints rõ) — đây là thứ LLM đọc để quyết định gọi. Viết docstring **mô tả khi nào dùng**, không chỉ cái gì.
4. **Guardrail** nếu tool có side-effect: theo mẫu `propose_booking` (chỉ đề xuất, chờ confirm).
5. **Test**: thêm case vào `tests/test_agents/test_ev_care_tools.py` (mock service) + `tool_calling_golden.jsonl` (LLM có chọn đúng tool không).

> **Không** tạo tool `get_vehicle_context` — context xe đã nạp sẵn vào state (tránh tốn 1 vòng LLM + rủi ro LLM đoán sai xe).

---

## 5. Guardrail (xem D3 / eval-testing-strategy §5)

3 lớp:
- **Input guard** (`conversation_guards/input_guard.py` — D3): off-scope, prompt-injection, PII người dùng dán nhầm.
- **Output guard**: no-source-no-claim (chặn khẳng định kỹ thuật thiếu citation), che PII (VIN/CCCD/SĐT/biển số), chặn số liệu chi phí bịa.
- **Tool/action guard** (`guard.py` — đã có): timeout, che exception, confirm-before-side-effect.

Khi review PR agent, luôn hỏi: *câu trả lời kỹ thuật có citation chưa? có lộ PII không? số chi phí có nhãn "ước tính" chưa? side-effect có confirm chưa?*

---

## 6. Chạy & test local

```bash
# Unit/integration test agent (mock LLM & service, không tốn API)
cd backend && uv run pytest tests/test_agents -q

# Chỉ RAG retrieval eval (không gọi LLM)
uv run python tests/test_agents/test_rag/evaluation/run_eval.py

# RAG full (sinh + chấm answer — GỌI LLM, tốn phí)
uv run python tests/test_agents/test_rag/evaluation/run_eval.py --full-rag

# Eval cấp agent (tool-calling / trajectory / task) — xem eval/README.md (D4)
uv run python -m eval.run --suite tool_calling
```

- Mặc định test **không gọi API trả phí**; các eval có LLM nằm sau cờ (`--full-rag`, `--suite ... --judge`).
- Cần biến môi trường model/Qdrant trong `.env` (xem [free-accounts](../../docs/guide/free-accounts.md)).

---

## 7. Đọc trace & debug

- Mỗi lượt có `conversation_id`, `agent_run_id`, `intent`, `status` (xem README §4).
- Lỗi tool: tìm log `Ngoại lệ khi thực thi tool <name>` (guard.py ghi structured, không lộ DB/Redis ra LLM).
- Agent lặp vòng / không hội tụ: kiểm `max_steps` và trajectory (eval §4.2) — thường do prompt/tool docstring chưa rõ.

---

## 8. Liên kết
- Kiến trúc chi tiết: [agents/README.md](../src/agents/README.md)
- Quy ước đặt tên: [agent.md](agent.md)
- RAG engine: [agents/tools/RAG/README.md](../src/agents/tools/RAG/README.md)
- Chiến lược kiểm thử & metric: [ai-eval-testing-strategy.spec.md](../../docs/specs/ai-agent/ai-eval-testing-strategy.spec.md)
- Chi phí vận hành: [ai-operational-cost.spec.md](../../docs/specs/ai-agent/ai-operational-cost.spec.md)
- Spec từng agent: [docs/specs/ai-agent/](../../docs/specs/ai-agent/)
