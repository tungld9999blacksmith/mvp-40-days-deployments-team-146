# Step 4 — structured Rewrite revision, 08/10/2026

Production Rewrite prompt/request updated; current application model/env unchanged and no app restart. Same 30 original queries (24 golden +6 v2.1), unchanged rubric. Five-query pilots rerun for all three models; full 30 only for eligible pilots. Original runs and verdicts preserved.

| Phase | Model | Complete queries | Raw JSON passes | Input anchor matches | Errors | Rewrite receipt USD |
| --- | --- | --- | --- | --- | --- | ---: |
| pilot | mistralai/mistral-small-2603 | 5/5 | 5 | 5 | 0 | 0.000859254 |
| full | mistralai/mistral-small-2603 | 30/30 | 30 | 30 | 0 | 0.003173065 |
| pilot | google/gemma-4-26b-a4b-it | 5/5 | 5 | 5 | 0 | 0.000429908 |
| full | google/gemma-4-26b-a4b-it | 30/30 | 30 | 30 | 0 | 0.003073576 |
| pilot | google/gemini-3.5-flash-lite | 5/5 | 5 | 5 | 0 | 0.002711400 |
| full | google/gemini-3.5-flash-lite | 30/30 | 30 | 30 | 0 | 0.016533600 |

Known new Rewrite spend: **0.026780803 USD**. Embedding costs unknown, so no certified total pipeline cost. Local FlashRank; no generation or Write calls. No GPT-4o or fourth model.

New request: seven-field JSON schema with `require_parameters=true`; metadata extraction prompt distinguishes maintenance milestone from current ODO/warranty/range. Observation wrapper forwards provider capability. Raw model output remains scored without Markdown stripping or milestone correction. Source before/after and original file copies are preserved.

Same embedding model/dimensions, hybrid retrieval, local reranker and corpus payload as previous revision. Query-specific evidence retrieved separately; no category oracle. Golden document IDs/category/anchors are draft and unreviewed. Document hits do not certify answer correctness. No independent labels, no production acceptance. Single development repeat; no holdout, robustness or TTFT claim.

Prior revision is a different prompt/request configuration, so before/after failure counts do not isolate model quality. Paired current request conditions verified in `comparison_conditions.json`; provider routing/load differ. Preservation checks in `final_preservation.json` verify history, corpus, frozen source and env.

Next: address remaining full-run failures if present; otherwise compare stage candidates and proceed to generation Mistral/Gemma under a frozen shared revision. Review remains deferred; don't change production model on this evidence alone.
