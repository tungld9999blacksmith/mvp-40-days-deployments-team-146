# RAG Evaluation

Thư mục này chứa dataset, helper metric, báo cáo đọc bởi con người và kết quả
thô của việc đánh giá RAG. Entrypoint thực thi nằm trong
`backend/tests/test_agents/evaluate_rag.py`.

## Cấu trúc

```text
evaluation/
├── datasets/
│   └── rag_golden_set.jsonl
├── scripts/                 # helper/legacy reference, không phải entrypoint
│   ├── run_rag_evaluation.py
│   ├── rag_metrics.py
│   └── audit_retrieval_evidence.py
├── reports/
│   ├── rag_evaluation_qdrant_3072_current.md
│   ├── rag_evaluation_qdrant_2048_baseline.md
│   └── retrieval_error_analysis.md
└── results/
    ├── qdrant_2048_baseline/
    │   ├── audit/
    │   └── full_rag/
    └── qdrant_3072_current/
        ├── retrieval/
        └── full_rag/
```

- `reports/rag_evaluation_qdrant_3072_current.md`: báo cáo tổng hợp mới nhất của RAG và regression test AI Agent.
- `results/qdrant_3072_current/retrieval/`: kết quả retrieval đủ 100 câu.
- `results/qdrant_3072_current/full_rag/`: kết quả retrieval và sinh câu trả lời thật trên mẫu 18 câu.
- `results/qdrant_2048_baseline/`: baseline cũ để đối chiếu; không phải kết quả hiện tại.

## Chạy đánh giá

Chạy từ thư mục gốc repository.

Entrypoint chính nằm trong `backend/tests/test_agents/evaluate_rag.py`.

Retrieval đầy đủ:

```bash
.venv/bin/python backend/tests/test_agents/evaluate_rag.py --mode retrieval \
  --heuristic-rewriter --concurrency 1 --run-name my_retrieval_run
```

Full RAG trên 3 câu cho mỗi category:

```bash
.venv/bin/python backend/tests/test_agents/evaluate_rag.py --mode full \
  --sample-per-category 3 --concurrency 1 \
  --answer-delay-seconds 20 --run-name my_full_rag_run
```

Smoke production RAG:

```bash
.venv/bin/python backend/tests/test_agents/evaluate_rag.py --mode smoke
```

Mỗi lần chạy ghi vào `results/<run_name>/<mode>/`. Nếu không truyền `--run-name`, runner tự tạo tên theo timestamp và không ghi đè baseline/evidence hiện có.
