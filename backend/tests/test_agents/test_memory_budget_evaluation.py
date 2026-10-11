"""Paid evaluation must stop before calls exceed its cost reservation."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

from scripts.evaluate_memory_budget import BudgetExceeded, BudgetLedger, sandbox_tools
from src.agents.tools import CUSTOMER_AGENT_TOOLS


def result(*, cost=None, input_tokens=1000, output_tokens=100):
    usage = None if input_tokens is None else {
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    return ChatResult(generations=[ChatGeneration(message=AIMessage(
        content="Synthetic result", usage_metadata=usage,
        response_metadata={"token_usage": {"cost": cost}},
    ))])


def test_budget_refuses_request_before_network():
    ledger = BudgetLedger(.0001, .165/1e6, .66/1e6)
    with pytest.raises(BudgetExceeded):
        ledger.reserve([HumanMessage(content="Hello")], [], 384)
    assert ledger.calls == []


def test_cache_discount_does_not_relax_no_cache_budget_guard():
    ledger = BudgetLedger(.10, .165/1e6, .66/1e6)
    call = ledger.reserve([HumanMessage(content="Hello")], [], 384)
    ledger.settle(call, result(cost=.00001))
    assert call["provider_cost_usd"] == .00001
    assert ledger.spent == pytest.approx(.000231)
    assert ledger.spent < call["reserved_usd"]


def test_unknown_billing_keeps_reservation_and_stops():
    ledger = BudgetLedger(.10, .165/1e6, .66/1e6)
    call = ledger.reserve([HumanMessage(content="Hello")], [], 384)
    ledger.settle(call, result(input_tokens=None))
    assert ledger.spent == call["reserved_usd"] and ledger.stop
    with pytest.raises(BudgetExceeded):
        ledger.reserve([], [], 384)


def test_provider_cost_collected_before_message_metadata_is_attached():
    ledger = BudgetLedger(.10, .165/1e6, .66/1e6)
    call = ledger.reserve([HumanMessage(content="Hello")], [], 384)
    response = result()
    response.llm_output = {"token_usage": {"cost": .000012}}
    ledger.settle(call, response)
    assert call["provider_cost_usd"] == .000012


def test_sandbox_preserves_all_schemas_and_blocks_other_services():
    tools = sandbox_tools(lambda: None)
    assert [convert_to_openai_tool(t) for t in tools] == [convert_to_openai_tool(t) for t in CUSTOMER_AGENT_TOOLS]
    assert next(t for t in tools if t.name == "get_due_maintenance").invoke({})["code"] == "EVALUATION_SANDBOX"
