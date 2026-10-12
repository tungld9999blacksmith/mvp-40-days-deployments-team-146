"""Unit tests for the agent evaluation metric core (D4).

These are pure-function tests: no LLM, no database. They verify the maths of the
statistical utilities and the metric scorers.
"""

from __future__ import annotations

import math

import pytest
from eval.metrics import stats, text, tool_calling, trajectory

# --- stats -----------------------------------------------------------------

def test_wilson_interval_bounds_and_center():
    ci = stats.wilson_interval(8, 10)
    assert ci.n == 10
    assert ci.point == pytest.approx(0.8)
    assert 0.0 <= ci.low < ci.point < ci.high <= 1.0


def test_wilson_interval_handles_extremes():
    perfect = stats.wilson_interval(10, 10)
    assert perfect.point == 1.0
    assert perfect.high <= 1.0
    assert perfect.low < 1.0  # interval still has width
    zero = stats.wilson_interval(0, 10)
    assert zero.point == 0.0
    assert zero.low == 0.0
    assert zero.high > 0.0


def test_wilson_interval_empty():
    ci = stats.wilson_interval(0, 0)
    assert (ci.point, ci.low, ci.high, ci.n) == (0.0, 0.0, 0.0, 0)


def test_bootstrap_ci_brackets_mean():
    sample = [1.0, 1.0, 1.0, 0.0, 0.0]  # mean 0.6
    ci = stats.bootstrap_ci(sample, resamples=2000, seed=1)
    assert ci.point == pytest.approx(0.6)
    assert ci.low <= ci.point <= ci.high


def test_two_proportion_ztest_detects_difference():
    res = stats.two_proportion_ztest(50, 100, 80, 100)
    assert res.diff == pytest.approx(0.3)
    assert res.significant
    assert res.p_value < 0.05


def test_two_proportion_ztest_no_difference():
    res = stats.two_proportion_ztest(50, 100, 51, 100)
    assert not res.significant
    assert res.p_value > 0.05


def test_holm_bonferroni_step_down():
    rejects = stats.holm_bonferroni({"a": 0.001, "b": 0.04, "c": 0.9}, alpha=0.05)
    assert rejects["a"] is True
    assert rejects["c"] is False


# --- text metrics ----------------------------------------------------------

def test_exact_match_normalizes():
    assert text.exact_match("Mốc 15.000 km.", "mốc 15000 km") == 0.0  # digits differ
    assert text.exact_match("Bảo dưỡng!", "bảo dưỡng") == 1.0


def test_token_f1_partial_overlap():
    f1 = text.token_f1("kiểm tra phanh và lốp", "kiểm tra phanh")
    assert 0.0 < f1 < 1.0


def test_token_f1_identical():
    assert text.token_f1("kiểm tra phanh", "kiểm tra phanh") == pytest.approx(1.0)


def test_rouge_l_in_unit_range():
    score = text.rouge_l("kiểm tra phanh và áp suất lốp", "kiểm tra áp suất lốp")
    assert 0.0 < score <= 1.0


# --- tool calling ----------------------------------------------------------

def test_tool_selection_correct_with_args():
    score = tool_calling.score_tool_call(
        expected_tool="estimate_service_cost",
        expected_args={"odo_milestone": 15000},
        actual_calls=[{"tool": "estimate_service_cost", "args": {"odo_milestone": 15000}}],
    )
    assert score.selected_correct and score.first_call_correct
    assert score.arg_f1 == pytest.approx(1.0)


def test_tool_no_call_expected():
    score = tool_calling.score_tool_call(
        expected_tool=None, expected_args={}, actual_calls=[]
    )
    assert score.selected_correct and not score.over_called


def test_tool_over_calling_flagged():
    score = tool_calling.score_tool_call(
        expected_tool=None,
        expected_args={},
        actual_calls=[{"tool": "get_due_maintenance", "args": {}}],
    )
    assert score.over_called and not score.selected_correct


def test_tool_invalid_call_flagged():
    score = tool_calling.score_tool_call(
        expected_tool="get_due_maintenance",
        expected_args={},
        actual_calls=[{"tool": "delete_everything", "args": {}}],
        known_tools={"get_due_maintenance"},
    )
    assert score.invalid_call


def test_arg_f1_free_text_normalized():
    assert tool_calling.arg_f1({"area_or_address": "Cầu Giấy"}, {"area_or_address": "cầu giấy"}) == pytest.approx(1.0)


# --- trajectory ------------------------------------------------------------

def test_trajectory_exact_match():
    score = trajectory.score_trajectory(
        expected_sequence=["a", "b"], actual_sequence=["a", "b"], optimal_steps=2, max_steps=5
    )
    assert score.exact_match
    assert score.in_order_recall == pytest.approx(1.0)
    assert score.step_efficiency == pytest.approx(1.0)


def test_trajectory_in_order_recall_partial():
    assert trajectory.in_order_recall(["a", "b", "c"], ["a", "c"]) == pytest.approx(2 / 3)


def test_trajectory_redundancy_and_efficiency():
    score = trajectory.score_trajectory(
        expected_sequence=["a", "b"],
        actual_sequence=["a", "a", "b", "b"],
        optimal_steps=2,
        max_steps=3,
    )
    assert score.redundant_step_rate == pytest.approx(0.5)
    assert score.step_efficiency == pytest.approx(0.5)
    assert score.overran  # 4 > 3


def test_trajectory_empty_is_efficient():
    score = trajectory.score_trajectory(expected_sequence=[], actual_sequence=[])
    assert score.exact_match
    assert score.redundant_step_rate == 0.0
    assert math.isclose(score.step_efficiency, 1.0)
