"""Tool-calling accuracy metrics (testing-strategy spec #4.1).

A tool call is represented as ``{"tool": str, "args": dict}``. A golden case
carries ``expected_tool`` and ``expected_args``. ``actual_calls`` is the ordered
list of calls the agent made in the turn.
"""

from __future__ import annotations

from dataclasses import dataclass

from .text import normalize


@dataclass
class ToolCallScore:
    selected_correct: bool      # expected tool was called at all
    first_call_correct: bool    # the FIRST tool call was the expected one
    arg_f1: float               # argument overlap F1 for the matched call
    invalid_call: bool          # a call referenced an unknown tool
    over_called: bool           # tools were called when none were expected


def _match_value(expected, actual) -> bool:
    """Enum/id values compare exactly; free-text compares after normalization."""
    if isinstance(expected, str) and isinstance(actual, str):
        return normalize(expected) == normalize(actual)
    return expected == actual


def arg_f1(expected_args: dict, actual_args: dict) -> float:
    """F1 over correctly matched (key, value) argument pairs."""
    if not expected_args and not actual_args:
        return 1.0
    if not expected_args or not actual_args:
        return 0.0
    correct = sum(
        1
        for key, exp in expected_args.items()
        if key in actual_args and _match_value(exp, actual_args[key])
    )
    if correct == 0:
        return 0.0
    precision = correct / len(actual_args)
    recall = correct / len(expected_args)
    return 2 * precision * recall / (precision + recall)


def score_tool_call(
    *,
    expected_tool: str | None,
    expected_args: dict | None,
    actual_calls: list[dict],
    known_tools: set[str] | None = None,
) -> ToolCallScore:
    expected_args = expected_args or {}
    actual_tools = [c.get("tool") for c in actual_calls]

    invalid = bool(known_tools) and any(t not in known_tools for t in actual_tools if t)

    # Case where the correct behaviour is to call no tool (e.g. small talk).
    if expected_tool is None:
        return ToolCallScore(
            selected_correct=not actual_calls,
            first_call_correct=not actual_calls,
            arg_f1=1.0 if not actual_calls else 0.0,
            invalid_call=invalid,
            over_called=bool(actual_calls),
        )

    selected = expected_tool in actual_tools
    first_correct = bool(actual_tools) and actual_tools[0] == expected_tool

    # Score args against the first matching call of the expected tool.
    matched_args: dict = {}
    for call in actual_calls:
        if call.get("tool") == expected_tool:
            matched_args = call.get("args", {}) or {}
            break

    return ToolCallScore(
        selected_correct=selected,
        first_call_correct=first_correct,
        arg_f1=arg_f1(expected_args, matched_args) if selected else 0.0,
        invalid_call=invalid,
        over_called=False,
    )
