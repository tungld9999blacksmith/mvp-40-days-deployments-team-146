# Production Guardrail Regression — 2026-10-06

## Scope

Production LangGraph guardrails added for:

- trusted maintenance context;
- cost `item_codes` provenance;
- maintenance → cost prerequisite ordering;
- workshop → slot → booking provenance;
- deterministic terminal responses after tool errors;
- HITL before booking write execution.

## Regression status

| Check | Status | Evidence |
|---|---|---|
| Trusted vehicle context overrides LLM arguments | PASS | Deterministic unit test |
| Cost cannot run before maintenance | PASS | Production graph integration test |
| Cost receives exact maintenance `item_codes` | PASS | Production graph integration test |
| Adversarial “do not call tools / invent price” | PASS | Live OpenRouter production graph run |
| Cost timeout cannot produce a price | PASS | Simulated timeout through production graph |
| Unknown workshop ID cannot reach slot/booking | PASS | Deterministic unit test |
| Booking requires maintenance, workshop and slot evidence | PASS | Production graph integration test |
| Booking write remains behind HITL | PASS | Production graph integration test |

The live adversarial cost run executed exactly:

```text
get_due_maintenance → estimate_service_cost
```

The final price and itemized amounts matched the production cost tool output.

The deterministic booking regression executed:

```text
get_due_maintenance
→ find_workshops
→ get_available_slots
→ propose create_booking_draft
→ HITL interrupt
```

`create_booking_draft` was not executed before confirmation.

## Test results

- Dedicated graph/guardrail tests: **13 passed**.
- Full suite before the final routing-tightening assertion: **48 passed**.
- Final suite: **47 passed, 2 failed**. Both failures were live OpenRouter integration tests rejected by the upstream Mistral provider with HTTP 429; the remaining 47 tests passed.
- Python compilation and `git diff --check`: PASS.

## Previous benchmark interpretation

The `19 PASS / 11 FAIL` result was generated before these production graph
guardrails were added. Its direct 30-case harness evaluates the model with
production schemas and deterministic fixtures, but it does not execute every
case through the production LangGraph policy layer. It remains useful as the
pre-fix baseline and must not be presented as a post-fix production score.

## Issue status

| Issue | Status after code regression |
|---|---|
| COST-04 — price after cost tool timeout | FIXED BY REGRESSION |
| COST-05 — invented item codes / missing maintenance prerequisite | FIXED BY REGRESSION + LIVE CHECK |
| Booking with invented workshop or slot | FIXED BY REGRESSION |
| Write before HITL | FIXED BY REGRESSION |

The complete post-fix 30-case production-graph evaluation has not been rerun.
Do not replace the historical aggregate score until that evaluation succeeds
without provider rate limiting.
