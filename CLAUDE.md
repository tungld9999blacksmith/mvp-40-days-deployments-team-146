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

## Testing

- Backend: `cd backend && APP_ENV=test OPENAI_API_KEY=test-key uv run --frozen pytest tests/` (use `uv`: the root `.venv` python lacks tzdata). Values in the root `.env` leak into Settings-based tests (e.g. `LLM_*_MODEL`); blank them when a routing test fails only locally.
- Frontend: `cd frontend && npm test` (vitest; pure-logic tests next to the code, e.g. `features/booking-lines/logic.test.ts`), plus `npx tsc --noEmit -p .`.
- New behavior gets a test; bug fixes get a regression test that fails before the fix.
