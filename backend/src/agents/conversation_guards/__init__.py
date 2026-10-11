"""Conversation-level guardrails for the EV Care agent.

Three layers (see docs/specs/ai-agent/ai-eval-testing-strategy.spec.md #5):

- input_guard  : inspect the user turn (prompt-injection, user PII, scope).
- output_guard : inspect the model answer before it reaches the client
                 (PII redaction, no-source-no-claim, cost-label enforcement).
- tool guard   : timeout + exception shielding, already in tools/guard.py.

These functions are pure and side-effect free so they can be unit-tested
without the LLM or the database. Enforcement policy (block / warn / rewrite)
is decided by the caller; the guards only report and, for output, return a
sanitized text.
"""

from __future__ import annotations

from .input_guard import InputGuardReport, inspect_input
from .output_guard import OutputGuardReport, apply_output_guard, inspect_output

__all__ = [
    "InputGuardReport",
    "inspect_input",
    "OutputGuardReport",
    "inspect_output",
    "apply_output_guard",
]
