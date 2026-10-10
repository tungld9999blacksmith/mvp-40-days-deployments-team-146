"""Live BOOK-03 comparison regression, preserving independent workshop facts."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from langchain_core.messages import ToolMessage

from src.agents.booking_grounding import booking_answer

ROOT = Path(__file__).resolve().parents[3]
ROWS = [json.loads(line) for line in (ROOT / "eval/results/agent_v2_1_booking_followup_preflight_mistral_20261008_06/case_results.jsonl").read_text(encoding="utf-8").splitlines()]


def tools(calls):
    return [ToolMessage(content=json.dumps(c["result"]), name=c["name"], tool_call_id=f"read-{i}", artifact=c.get("artifact")) for i, c in enumerate(calls)]


@pytest.mark.parametrize("repeat", [2, 3])
def test_observed_multishop_afternoon_answer_uses_each_actual_result(repeat):
    row = next(r for r in ROWS if r["repeat"] == repeat)
    answer = booking_answer(tools(row["trace"]["calls"]), session="afternoon")
    reads = [c["result"] for c in row["trace"]["calls"] if c["name"] == "get_available_slots"]
    assert len(reads) >= 2
    assert "11/10/2026" not in answer and "18:00: còn" not in answer
    for result in reads:
        assert f"Ngày 10/10/2026, xưởng {result['workshop_id']} có 6 khung giờ khả dụng" in answer
    assert "Lịch chưa được đặt hoặc giữ chỗ" in answer


def comparison():
    row = next(r for r in ROWS if r["repeat"] == 2)
    return deepcopy([c for c in row["trace"]["calls"] if c["name"] == "get_available_slots"])


def test_capacity_not_copied_across_workshops_and_latest_read_wins():
    calls = comparison()
    calls[0]["result"]["slots"] = [{"time_slot": "14:00", "available": True, "remaining": 1}]
    calls[1]["result"]["slots"] = [{"time_slot": "14:00", "available": False, "remaining": 0}]
    newer = deepcopy(calls[0])
    newer["result"]["slots"][0]["remaining"] = 2
    answer = booking_answer(tools([*calls, newer]), session="afternoon")
    assert "14:00: còn 2 chỗ" in answer and "14:00: còn 1 chỗ" not in answer
    assert f"xưởng {calls[1]['result']['workshop_id']} có 0 khung giờ khả dụng" in answer


def test_new_failed_comparison_read_cannot_reuse_old_success():
    calls = comparison()
    calls.append({"name": "get_available_slots", "result": {"status": "ERROR"}})
    assert "Chưa có dữ liệu" in booking_answer(tools(calls), session="afternoon")


def test_different_days_are_not_rendered_as_single_selected_day():
    calls = comparison()
    calls[1]["result"]["date"] = "2026-10-11"
    assert booking_answer(tools(calls), session="afternoon") is None
