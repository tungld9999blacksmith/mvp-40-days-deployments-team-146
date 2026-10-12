# AI System Evaluation

Thư mục này chỉ chứa dataset, cấu hình, raw result, evidence và report. Các
entrypoint dùng để chạy evaluation nằm trong `backend/tests/test_agents/`.

```text
backend/tests/
├── test_agents/          # Pytest và các evaluation entrypoint
└── evaluation/           # Dataset, cấu hình, raw result, evidence, report
    ├── llm_agent/        # So sánh 10 LLM trong vai trò Agent
    └── rag/              # Retrieval và full RAG evaluation
```

## LLM Agent benchmark đã có

- Hướng dẫn: `llm_agent/README.md`
- Legacy benchmark runner: `llm_agent/benchmark_models.py` (giữ nguyên evidence
  so sánh 10 model theo yêu cầu; evaluation production hiện tại dùng runner bên
  `test_agents`)
- Dataset: `llm_agent/agent_cases.json`
- Báo cáo chính: `llm_agent/results/benchmark_report.md`
- Bảng so sánh: `llm_agent/results/comparison.csv`

Không cần chạy lại 10 paid model để đánh giá model production hiện tại.

## RAG evaluation

- Hướng dẫn: `rag/README.md`
- Entry point: `backend/tests/test_agents/evaluate_rag.py`
- Golden dataset: `rag/datasets/rag_golden_set.jsonl`
- Báo cáo hiện tại: `rag/reports/rag_evaluation_qdrant_3072_current.md`
- Baseline: `rag/reports/rag_evaluation_qdrant_2048_baseline.md`

```bash
.venv/bin/python backend/tests/test_agents/evaluate_rag.py --mode smoke
.venv/bin/python backend/tests/test_agents/evaluate_rag.py --mode retrieval
.venv/bin/python backend/tests/test_agents/evaluate_rag.py --mode full --sample-per-category 1
```

## Agent và toàn hệ thống

```bash
.venv/bin/python backend/tests/test_agents/evaluate_agent.py
.venv/bin/python backend/tests/test_agents/evaluate_ai_system.py
```

Raw JSON là evidence theo từng case và cần được giữ cùng báo cáo tổng hợp.
