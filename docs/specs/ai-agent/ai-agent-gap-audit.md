# AI-Agent — Báo cáo rà soát Spec ↔ Code (D1)

> **D1** trong [work-scope-clarification.md](work-scope-clarification.md). Đối chiếu 8 spec `.agent.md` với code thực tế trong `backend/src/agents/`, nêu phần đã có / lệch / đã descope, và các vá đã thực hiện.

| Field | Value |
| --- | --- |
| Ngày | 2026-10-05 |
| Phạm vi | AI-001 … AI-008 vs `backend/src/agents/`, `backend/src/modules/` |

---

## 1. Tổng hợp trạng thái

| ID | Agent | Spec | Code | Trạng thái |
| --- | --- | --- | --- | --- |
| AI-001 | Orchestrator | Draft | `orchestrator.py`, `graph.py`, `state.py`, `prompts.py` | ✅ **Đã có & cắm vào chat** (ChatService → `run_agent_turn` → SSE) |
| AI-002 | Knowledge Advisor (RAG) | Draft | `tools/RAG/` + `search_ev_knowledge` | ✅ **Đã có** (hybrid dense+BM25+reranker, citation) |
| AI-003 | Cost Estimation | Draft | `tools/cost_tools.py` (`estimate_service_cost`) | ✅ **Đã có** (tool tất định, LLM không tự cộng số) |
| AI-004 | Booking | Draft | `tools/booking_tools.py` (`find_workshops`, `get_available_slots`, `propose_booking`) + `confirm_booking_turn` | ✅ **Đã có** (CQRS read/propose; confirm-before-side-effect) |
| AI-005 | Quote HITL | Draft | — (migration `drop_quote_support_ticket_discord`) | ⚠️ **ĐÃ DESCOPE** — báo giá đã bỏ khỏi MVP; spec còn "Draft" (stale) |
| AI-006 | Reminder | Draft | `modules/booking/reminders.py`, `celery/tasks/reminder_tasks.py`, `core/maintenance/reminder.py` | ✅ **Đã có dạng job tất định** (không phải LLM-agent trong graph; Discord đã bỏ, dùng Thông báo in-app) |
| AI-007 | Follow-up | Draft | `modules/follow_up/`, `core/crm/follow_up.py` | ✅ **Đã có dạng service** (support_ticket đã bỏ; chỉ ghi `has_issue`) |
| AI-008 | Knowledge Ingestion | Draft | `tools/RAG/ingestion/` | ✅ **Đã có** (chunk → embed → Qdrant) |

**Kết luận:** mọi **agent hội thoại** (AI-001/002/003/004) đã hiện thực và **đã cắm vào API chat**. AI-005 đã bị loại khỏi phạm vi. AI-006/007 tồn tại dưới dạng **worker/dịch vụ tất định** (đúng đề xuất Q-A03: template thay vì LLM). Không có agent hội thoại nào còn thiếu.

---

## 2. Lệch cần lưu ý (không phải lỗi code)

| # | Lệch | Khuyến nghị |
| --- | --- | --- |
| G1 | Spec **AI-005** vẫn "Draft" dù báo giá đã bị bỏ (migration + ghi chú scope 02/10). | Đánh dấu AI-005 **Deprecated/Descoped** ở đầu spec để tránh nhầm khi lập kế hoạch. |
| G2 | AI-006/007 spec mô tả như "agent"; code là **job/service tất định**. | Ghi rõ trong spec: "triển khai dạng worker tất định, không LLM" (khớp Q-A03). |
| G3 | Guardrail hội thoại (PII/no-source/cost-label) trước đây **chưa có** ở tầng output. | ✅ **Đã vá** — xem §3. |
| G4 | Eval **cấp agent** (tool-calling/trajectory) + thống kê (CI/A·B) chưa có. | ✅ **Đã bổ sung** harness `eval/` (D4) + golden datasets (D5). |

---

## 3. Vá đã thực hiện trong đợt này

1. **Guardrail hội thoại (D3)** — `backend/src/agents/conversation_guards/`:
   - `input_guard`: phát hiện prompt-injection + PII người dùng dán nhầm (log cảnh báo).
   - `output_guard`: **redact PII** (VIN/CCCD/SĐT/biển số/email) trong câu trả lời cuối, cờ no-source-no-claim và cost-label.
   - **Đã cắm vào `orchestrator.py`**: `inspect_input` ở đầu lượt; `apply_output_guard` tại event `completed` của cả `run_agent_turn` và `confirm_booking_turn` (không ảnh hưởng streaming; nội dung lưu/emit đã được redact).
   - Test: `backend/tests/test_agents/test_guardrails.py` (12 ca, pass).

2. **Eval harness cấp agent (D4)** — `eval/` (metrics: stats/text/tool_calling/trajectory + runner). Test: `backend/tests/test_eval/test_metrics.py` (20 ca, pass).

3. **Golden datasets (D5)** — `eval/datasets/` (tool-calling, trajectory, task, refusal, red-team, bias).

4. **Tài liệu (D6/D7/D8)** — dev guide, cost spec, testing-strategy spec (đã link vào `DEV_GUIDE.md`).

---

## 4. Việc còn lại (đề xuất, không chặn)

- Cập nhật header AI-005/006/007 theo G1/G2 (tôi có thể làm nếu bạn đồng ý sửa spec).
- Viết script `scripts/gen_predictions.py` chạy golden qua agent thật để sinh predictions cho `eval/run.py` (cần `langchain_google_genai` + khoá API; ngoài CI mặc định).
- Bổ sung LLM-as-Judge (faithfulness) bằng Claude khi có khoá (D8 §3.4) — hiện đã đặc tả, chưa hiện thực do cần khoá & quyết định Q3/Q6.

---

## 5. Lưu ý môi trường

Test dựng **graph thật** (`test_agent_orchestrator.py::test_vf6_demo_walkthrough`) hiện fail vì môi trường thiếu `langchain_google_genai` (dependency của LLM), **không liên quan tới thay đổi đợt này**. Test luồng có mock (`test_conversation_agent_stream.py`) — bao phủ wiring guardrail — vẫn pass.
