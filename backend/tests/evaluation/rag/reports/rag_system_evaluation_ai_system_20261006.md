# RAG System Evaluation — ai_system_20261006

Các số liệu dưới đây được đọc trực tiếp từ raw result của run này.

## Smoke

Status: **SYSTEM WORKING**

```json
{
  "qdrant_collection": "ev_care_knowledge_base_3072",
  "qdrant_points": 819,
  "embedding_provider": "GeminiEmbeddingProvider",
  "embedding_model": "models/gemini-embedding-001",
  "embedding_dimension": 3072,
  "collection_dimension": 3072,
  "bm25_indexed_chunks": 819,
  "reranker": "FlashRankReranker",
  "reranker_model": "ms-marco-TinyBERT-L-2-v2",
  "top_k": 3,
  "generator": null,
  "generation_model": null
}
```

## Retrieval

| Metric | Score |
|---|---:|
| Queries | 100 |
| Hit@1 | 82.00% |
| Hit@3 | 97.00% |
| Hit@5 | 99.00% |
| MRR | 0.8957 |
| Avg latency | 1251.7 ms |
| P95 latency | 3068.9 ms |

Failed: P01

## Full RAG

| Metric | Score |
|---|---:|
| evaluated_answers | 6 |
| retrieval_success | 1.0 |
| answer_correctness_heuristic | 0.5045 |
| expected_keyword_coverage | 0.7222 |
| faithfulness_heuristic | 0.8281 |
| citation_validity | 1.0 |
| average_latency_ms | 8192.7 |
| p95_latency_ms | 12923.7 |
| hallucination_rate_negative_cases | 0.0 |
| hallucination_rate_general | NOT MEASURED |
| negative_cases_passed | 4 |
| negative_cases_total | 4 |

## Negative cases

- `NEG-CONTEXT-01`: **PASS**
- `NEG-PRICE-01`: **PASS**
- `NEG-WARRANTY-01`: **PASS**
- `NEG-SOURCE-01`: **PASS**
