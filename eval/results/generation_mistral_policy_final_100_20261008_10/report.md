# Fixed-evidence generation comparison

DEVELOPMENT ONLY. No new retrieval; generation latency is not full pipeline/UI latency. Semantic and claim support review pending. The historical copied baseline used prompt-only JSON; today's candidate uses JSON schema. A changed prompt requires explicit --allow-prompt-change and is not a model-only comparison against that baseline. Pair two new runs with identical prompt, schema and fixed-input hashes for a model comparison.

```json
{
  "attempted": 100,
  "errors": 0,
  "provider_errors": 0,
  "nonempty_answers": 100,
  "raw_schema_valid": 93,
  "provider_calls": 93,
  "answers_with_citations": 89,
  "fallback_required": 30,
  "average_generation_seconds": 1.730312117204292,
  "p50_generation_seconds": 1.5496452999996109,
  "p90_generation_seconds": 2.702639700000873,
  "p95_generation_seconds": 3.046729100000448,
  "cost_receipts": 93,
  "provider_cost_usd": 0.03440612999999998,
  "known_cost_usd_partial": 0.03440612999999998,
  "semantic_correctness": "NEEDS_INDEPENDENT_REVIEW",
  "production_acceptance": false,
  "selected": 100,
  "complete": true,
  "paired_generation_comparison": {
    "baseline_model": "google/gemma-4-26b-a4b-it",
    "baseline": {
      "attempted": 100,
      "errors": 100,
      "provider_errors": 0,
      "nonempty_answers": 100,
      "raw_schema_valid": 0,
      "provider_calls": 100,
      "answers_with_citations": 99,
      "fallback_required": 8,
      "average_generation_seconds": 6.783251375999899,
      "p50_generation_seconds": 4.604873699998279,
      "p90_generation_seconds": 13.483207199999015,
      "p95_generation_seconds": 23.818167999997968,
      "cost_receipts": 0,
      "provider_cost_usd": null,
      "known_cost_usd_partial": 0,
      "semantic_correctness": "NEEDS_INDEPENDENT_REVIEW",
      "production_acceptance": false
    },
    "candidate_model": "mistralai/mistral-small-2603",
    "candidate": {
      "attempted": 100,
      "errors": 0,
      "provider_errors": 0,
      "nonempty_answers": 100,
      "raw_schema_valid": 93,
      "provider_calls": 93,
      "answers_with_citations": 89,
      "fallback_required": 30,
      "average_generation_seconds": 1.730312117204292,
      "p50_generation_seconds": 1.5496452999996109,
      "p90_generation_seconds": 2.702639700000873,
      "p95_generation_seconds": 3.046729100000448,
      "cost_receipts": 93,
      "provider_cost_usd": 0.03440612999999998,
      "known_cost_usd_partial": 0.03440612999999998,
      "semantic_correctness": "NEEDS_INDEPENDENT_REVIEW",
      "production_acceptance": false
    }
  },
  "probes": []
}
```
