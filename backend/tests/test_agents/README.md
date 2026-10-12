# AI Agent Test Assets

Thư mục này chứa pytest và các Python entrypoint chạy evaluation. Dataset,
raw result, evidence và report được ghi sang thư mục cùng cấp
`backend/tests/evaluation`.

## Evaluation entrypoint

- `evaluate_rag.py`: smoke, retrieval và full RAG.
- `evaluate_agent.py`: model production, tool calling, guardrail, known issues và
  hội thoại nhiều lượt trên production LangGraph.
- `evaluate_ai_system.py`: master runner, tiếp tục các bước độc lập khi một bước
  thất bại.

## File quan trọng cần giữ

### Test tự động

- `test_agent_graph.py`: routing và thực thi LangGraph.
- `test_agent_orchestrator.py`: luồng Agent nhiều bước và policy xác nhận booking.
- `test_backend_integration.py`: contract, dependency injection, timeout và tích hợp backend.
- `test_ev_care_tools.py`: maintenance, cost, workshop, slot và booking tools.
- `test_rag_pipeline.py`: ingestion và RAG pipeline ở mức unit/integration.
- `test_rag/test_rag_quality_guards.py`: context selection, citation và RAG metrics.
- `__init__.py` và `test_rag/__init__.py`: giữ package test ổn định.

Phần đánh giá cần giữ được khai báo tại `backend/tests/evaluation/README.md`.

## File không quan trọng hoặc có thể tái sinh

Các mục dưới đây không nên commit và có thể xóa:

- `__pycache__/` và `*.pyc`: bytecode do Python tạo lại.
- `test_qdrant_rag.py`: script manual cũ, đã được thay bằng RAG evaluation runner.
- `test_rag/test_rag_retrieval_flow.py`: script chạy logic ở import time, trùng với test và runner hiện tại.
- Output benchmark/evaluation tạm chưa được review hoặc chưa đưa vào báo cáo chính thức.

Không xóa raw result chính thức chỉ vì đã có báo cáo Markdown. Raw JSON lưu output theo từng case để reviewer kiểm chứng lại số liệu.
