"""Agent trajectory metrics for ReAct/CoT quality (testing-strategy spec #4.2).

A trajectory is the ordered list of tool names the agent invoked. Two agents can
reach the same answer with very different trajectories; these metrics expose
redundancy and inefficiency that drive latency and cost.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TrajectoryScore:
    exact_match: bool          # actual sequence equals expected sequence
    in_order_recall: float     # fraction of required steps present, in order
    redundant_step_rate: float # repeated consecutive identical calls / total
    step_efficiency: float     # optimal_steps / actual_steps (capped at 1.0)
    overran: bool              # exceeded the allowed step budget


def _lcs_length(a: list[str], b: list[str]) -> int:
    """Length of the longest common subsequence of two sequences."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for item_a in a:
        curr = [0]
        for j, item_b in enumerate(b, 1):
            if item_a == item_b:
                curr.append(prev[j - 1] + 1)
            else:
                curr.append(max(prev[j], curr[j - 1]))
        prev = curr
    return prev[-1]


def in_order_recall(required: list[str], actual: list[str]) -> float:
    """Fraction of ``required`` steps that appear in ``actual`` keeping order.

    Uses the longest common subsequence so that an out-of-place step in
    ``actual`` does not consume a later required step. For required=[a,b,c] and
    actual=[a,c] the recall is 2/3.
    """
    if not required:
        return 1.0
    return _lcs_length(required, actual) / len(required)


def redundant_step_rate(actual: list[str]) -> float:
    """Share of steps that repeat the immediately preceding identical call."""
    if len(actual) <= 1:
        return 0.0
    repeats = sum(1 for i in range(1, len(actual)) if actual[i] == actual[i - 1])
    return repeats / len(actual)


def score_trajectory(
    *,
    expected_sequence: list[str],
    actual_sequence: list[str],
    optimal_steps: int | None = None,
    max_steps: int | None = None,
) -> TrajectoryScore:
    optimal = optimal_steps if optimal_steps is not None else len(expected_sequence)
    actual_len = len(actual_sequence)
    efficiency = 1.0 if actual_len == 0 else min(1.0, optimal / actual_len) if optimal else 1.0
    return TrajectoryScore(
        exact_match=actual_sequence == expected_sequence,
        in_order_recall=in_order_recall(expected_sequence, actual_sequence),
        redundant_step_rate=redundant_step_rate(actual_sequence),
        step_efficiency=efficiency,
        overran=bool(max_steps) and actual_len > max_steps,
    )
