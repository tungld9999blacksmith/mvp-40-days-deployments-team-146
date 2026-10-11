# EV Care — Agent Evaluation Harness (D4)

Harness đánh giá **cấp agent** + thống kê, bổ trợ cho RAG retrieval eval
(`backend/tests/test_agents/test_rag/evaluation/`). Thiết kế theo
[ai-eval-testing-strategy.spec.md](../docs/specs/ai-agent/ai-eval-testing-strategy.spec.md) (D8).

## Cấu trúc
```text
eval/
├── metrics/
│   ├── stats.py         # Wilson CI, bootstrap CI, A/B (two-proportion z-test), Holm-Bonferroni
│   ├── text.py          # exact-match, token-F1, ROUGE-L (+ BLEU/BERTScore tuỳ chọn)
│   ├── tool_calling.py  # tool-selection accuracy, arg-F1
│   └── trajectory.py    # exact match, in-order recall, redundancy, efficiency
├── datasets/            # golden sets (D5) — xem datasets/README.md
├── results/             # báo cáo JSON/MD sinh ra
└── run.py               # runner: dataset + predictions → report + CI
```

## Triết lý
- **Lõi tự viết, ít phụ thuộc** (standard library). Metric nặng (BLEU/BERTScore/RAGAS/DeepEval)
  import lười + guard, suite vẫn chạy khi thiếu — đúng quyết định "hybrid" (Q7).
- **Mọi tỉ lệ kèm khoảng tin cậy** (Wilson/bootstrap), không báo điểm trần trụi.

## Chạy
Runner tách **sinh dự đoán** (gọi agent thật, tốn LLM) khỏi **chấm điểm** (offline):

```bash
# 1) Sinh predictions bằng agent thật (xem Adapter bên dưới) → predictions.jsonl
# 2) Chấm điểm offline:
python -m eval.run --suite tool_calling \
    --dataset eval/datasets/tool_calling_golden.jsonl \
    --predictions predictions_tool_calling.jsonl

python -m eval.run --suite trajectory \
    --dataset eval/datasets/trajectory_golden.jsonl \
    --predictions predictions_trajectory.jsonl
```

Predictions JSONL:
- tool_calling: `{"id": "TC01", "actual_calls": [{"tool": "get_due_maintenance", "args": {}}]}`
- trajectory:   `{"id": "TR01", "actual_sequence": ["get_due_maintenance", "estimate_service_cost"]}`

## Adapter sinh predictions (gọi agent thật)
Chạy từng `query` + `vehicle_context` của golden qua orchestrator, thu lại các
`tool_calls` mà LLM phát ra (từ `AIMessage.tool_calls` trong graph), ghi thành
predictions. Khung tối thiểu:

```python
# scripts/gen_predictions.py (ngoài CI mặc định vì gọi LLM)
from src.agents.dependency import get_agent_graph
# duyệt dataset → invoke graph với configurable={user_id, user_vehicle_id, conversation_id}
# gom tool name + args theo thứ tự → {"id", "actual_calls"/"actual_sequence"}
```
Dùng tài khoản test + Firebase Auth Emulator (xem memory `manual-test-auth-emulator`);
danh tính lấy từ `RunnableConfig`, không từ tham số LLM.

## A/B testing
So hai cấu hình (vd reranker on/off, top-k=3 vs 5) trên cùng golden; dùng
`metrics.stats.two_proportion_ztest` cho primary metric nhị phân và
`holm_bonferroni` khi theo dõi nhiều metric. Xem spec #5.3.

## Gate CI (spec #11)
Gate cứng (chặn merge): PII-leak = 0, red-team ASR ≤ 0.02, citation coverage = 1.0.
Gate mềm (cảnh báo): tool-selection ≥ 0.90, trajectory efficiency, latency, cost.
Chạy subset rule-based mỗi PR (gần như miễn phí); chạy full có LLM-judge theo lịch.
