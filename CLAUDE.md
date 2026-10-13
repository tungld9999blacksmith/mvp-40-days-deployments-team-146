## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec

## Design System
Read DESIGN.md before visual or UI work: it defines the fonts, colors, spacing, and
aesthetic direction. Ask the user before departing from it. When reviewing or QA-ing
UI, flag code that doesn't match DESIGN.md.

## Background work (outbox)

When a request does work whose result the response does not need (notifications,
emails, external API calls, LLM enrichment, cleanup, sync), or that would slow a
response that must be fast, move it to a background job via the transactional
outbox (`backend/src/infrastructure/outbox`, guide: `backend/guide/outbox.md`):

- Define an `OutboxEvent` (ids + minimal data, no PII) and an idempotent `OutboxHandler`;
  register it and list its module in `OUTBOX_HANDLER_MODULES` (`celery/tasks/outbox_tasks.py`).
- Call `publish(session, event, ...)` in the same transaction as the business change;
  never commit it in a separate session.
- Use `PermanentError` for unrecoverable failures, `RetryableError` for transient ones.
- Keep inline: work that must finish inside the transaction (capacity/lock checks,
  validation) or whose result the response returns.
- Live UI updates use Redis pub/sub (non-durable), not the outbox.

## Testing

- Backend: `cd backend && APP_ENV=test OPENAI_API_KEY=test-key uv run --frozen pytest tests/` (use `uv`: the root `.venv` python lacks tzdata). Values in the root `.env` leak into Settings-based tests (e.g. `LLM_*_MODEL`); blank them when a routing test fails only locally.
- Frontend: `cd frontend && npm test` (vitest; pure-logic tests next to the code, e.g. `features/booking-lines/logic.test.ts`), plus `npx tsc --noEmit -p .`.
- New behavior gets a test; bug fixes get a regression test that fails before the fix.
