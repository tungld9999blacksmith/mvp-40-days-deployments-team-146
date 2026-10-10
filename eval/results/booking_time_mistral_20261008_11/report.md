# Booking: raw time format followup — 08/10/2026

Development evaluation, step 3; not production acceptance. Mistral Small 2603 retained.

The read tool returns seconds (14:00:00), while proposal arguments require HH:MM. The prompt now explicitly explains conversion of a verified zero-second slot without changing its hour/minute, workshop or date. Nonzero seconds must not be rounded. Public schema, normalization, dataset and scorer remain unchanged.

Offline regression: 496 passed, 5 skipped; Ruff exit code 0. [JUnit evidence](offline_regression_01.xml).

| Run | Runtime PASS | API errors | Raw argument error cases | Safety violations |
|---|---:|---:|---:|---:|
| Historical matched 54 baseline | 54/54 | 0 | 9 | 0 |
| agent_v2_1_time_preflight_mistral_20261008_11 | 9/9 | 0 | 0 | 0 |
| agent_v2_1_time_booking_54_mistral_20261008_11 | 0/1 | 1 | 0 | 0 |
| agent_v2_1_time_keycheck_mistral_20261008_12 | 1/1 | 0 | 0 | 0 |
| agent_v2_1_time_booking_54_mistral_20261008_12 | 54/54 | 0 | 0 | 0 |

| Run | Raw proposal requests | Requests before verified slots | Mean case latency (s) |
|---|---:|---:|---:|
| Historical matched 54 baseline | 17 | 8 | 3.357 |
| agent_v2_1_time_preflight_mistral_20261008_11 | 19 | 9 | 7.247 |
| agent_v2_1_time_booking_54_mistral_20261008_11 | 0 | 0 | 2.837 |
| agent_v2_1_time_keycheck_mistral_20261008_12 | 0 | 0 | 8.580 |
| agent_v2_1_time_booking_54_mistral_20261008_12 | 19 | 10 | 3.480 |

The first full run was interrupted by HTTP403 `Key limit exceeded (total limit)`: 1/54 attempted, 53 not attempted. The rejected request is not evidence of a wrong BOOK-03 answer. The user then updated .env; BOOK-03 was checked in a new keycheck run and the full regression restarted in a new directory. The failed run is preserved and is not combined with the new run's PASS denominator.

Raw proposal requests can precede verified slot reads. Existing runtime guards insert prerequisites rather than executing those proposals. Format correctness does not prove that the model independently follows the complete tool chain. The counters above retain this limitation; task PASS is the delivered runtime behavior.

Current iteration known receipt subtotal: 0.07189462500000002 USD; 1 case(s) lack cost metadata. Missing cost is not interpreted as zero; total cost is not certified.

[Dataset audit](dataset_audit.json): all 100 RAG golden objects match the historical golden file in order; v2/v2.1 user queries are identical. The golden, datasets and historical results were not changed or rescored.

[Preservation](preservation.json) verifies historical artifacts, corpus and frozen source revision. The user updated .env after the 403; its new revision is recorded without exposing credentials. The agent did not write .env. Raw proposal requests and normalization remain visible in producer traces; runtime PASS is not raw model accuracy.

Independent semantic labels: 0. Source-owner adjudication, holdout, shortlist, full HTTP/Firebase/UI confirmation, TTFT/concurrency and pilot remain pending. No production writes, real email, corpus/Qdrant mutation or app restart was performed.
