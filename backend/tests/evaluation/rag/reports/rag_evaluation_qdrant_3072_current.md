# Báo cáo đánh giá RAG và AI Agent — Qdrant 3072 (Hiện tại)

Ngày chạy: 06/10/2026

## 1. Cấu hình được kiểm chứng

- Qdrant collection: `ev_care_knowledge_base_3072`
- Số point: 819
- Embedding: `models/gemini-embedding-001`, 3072 chiều
- Query rewrite: `mistralai/mistral-small-2603`
- Reranker: FlashRank
- RAG answer generation: `google/gemma-4-26b-a4b-it`
- Booking/write reviewer: `openai/gpt-4o`

## 2. Retrieval evaluation — 100 câu

Command:

```bash
.venv/bin/python backend/tests/evaluation/rag/scripts/run_rag_evaluation.py \
  --heuristic-rewriter --concurrency 1 \
  --output-dir backend/tests/evaluation/rag/results/qdrant_3072_current/retrieval
```

| Chỉ số | Kết quả |
|---|---:|
| Pass rate | 82.0% |
| Hit@1 | 79.0% |
| Hit@3 | 97.0% |
| Hit@5 | 97.0% |
| MRR | 0.8717 |
| Average top score | 0.8531 |
| Context precision | 61.17% |
| Context recall | 81.42% |
| Average latency | 759.8 ms |
| P95 latency | 1,013.4 ms |

18 case không đạt tiêu chí tổng hợp: `M10`, `M16`, `M23`, `M25`, `W06`, `W17`, `B01`, `B07`, `B11`, `B17`, `P01`, `PR02`, `PR04`, `PR05`, `G01`, `G05`, `G07`, `G08`.

## 3. Full RAG evaluation — 18 câu

Mỗi category được lấy 3 câu. Cả 18 câu đều sinh output thật bằng Gemma; không có lỗi và không có offline fallback.

| Chỉ số | Kết quả |
|---|---:|
| Answer coverage | 100% (18/18) |
| Correctness | 0.6134 |
| Completeness | 0.7870 |
| Answer relevancy | 0.9019 |
| Coherence | 1.0000 |
| Citation correctness | 0.6759 |
| Citation support | 0.8889 |
| Grounded pass rate | 88.89% |

Hai case không đạt tiêu chí tổng hợp là `B01` và `P01`. Không ghi nhận rate limit trong lần chạy có delay 20 giây.

## 4. So sánh với baseline 2048 trước đó

| Chỉ số | Baseline 2048 | Collection 3072 | Thay đổi |
|---|---:|---:|---:|
| Hit@1 | 85.0% | 79.0% | -6.0 điểm % |
| Hit@3 | 96.0% | 97.0% | +1.0 điểm % |
| MRR | 0.9017 | 0.8717 | -0.0300 |
| Average top score | 0.8291 | 0.8531 | +0.0240 |
| Context precision | 63.0% | 61.17% | -1.83 điểm % |
| Context recall | 82.83% | 81.42% | -1.41 điểm % |
| Average latency | 2,811.6 ms | 759.8 ms | giảm 72.98% |
| Answer correctness | 0.6833 | 0.6134 | -0.0699 |
| Answer completeness | 0.8333 | 0.7870 | -0.0463 |
| Answer relevancy | 0.8514 | 0.9019 | +0.0505 |
| Citation correctness | 0.6944 | 0.6759 | -0.0185 |
| Citation support | 0.7222 | 0.8889 | +0.1667 |

Baseline và lần chạy mới không chỉ khác dimension: baseline dùng Gemini 3.5 Flash Lite và HeuristicReranker, còn lần mới dùng Gemma 4 26B và FlashRank. Vì vậy bảng trên phản ánh thay đổi của toàn pipeline, không cô lập riêng tác động của embedding 3072.

## 5. AI Agent regression

Command:

```bash
.venv/bin/pytest -p no:cacheprovider backend/tests/test_agents -q
```

Kết quả: **38 passed trong 34.44 giây**.

Các test xác nhận Agent graph, RAG pipeline, tool contracts, maintenance/cost/workshop tools, guardrail, backend integration và kịch bản orchestrator đều hoạt động với collection mới.

## 6. Kết luận

Collection 3072 đã giải quyết hoàn toàn lỗi không tương thích vector và toàn bộ test Agent hiện tại đều pass. Pipeline mới cải thiện Hit@3, tốc độ retrieval, answer relevancy và citation support. Hit@1, MRR, correctness, completeness và citation correctness giảm; vì vậy chưa thể kết luận chất lượng tổng thể tốt hơn baseline chỉ từ final score. Hai hướng ưu tiên tiếp theo là phân tích 18 retrieval failures và rà prompt/context selection cho `B01`, `P01`.
