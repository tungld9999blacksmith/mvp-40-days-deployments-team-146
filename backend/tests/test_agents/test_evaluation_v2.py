"""Regression cases that distinguish safe booking behavior from misleading scores."""
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from src.agents.contracts import validate_arguments
from src.agents.graph import build_graph
from src.agents.tools import CUSTOMER_AGENT_TOOLS
from tests.evaluation_v2 import artifacts
from tests.evaluation_v2.dataset import build_dataset
from tests.evaluation_v2.sandbox import Sandbox
from tests.evaluation_v2.scoring import retrieval_metrics, score_case, unsupported_booking_claim


def test_a_missing_prerequisite_has_partial_coverage_but_still_fails():
    tools = {t.name: t for t in CUSTOMER_AGENT_TOOLS}
    case = {"expected": {"required_tools": ["get_due_maintenance", "estimate_service_cost"], "dependencies": [["get_due_maintenance", "estimate_service_cost"]]}}
    result = score_case(case, {"calls": [{"name": "estimate_service_cost", "args": {}}], "answer": "Dự toán đang được kiểm tra."}, list(tools.values()))
    assert result["required_tool_coverage"] == .5
    assert not result["task_passed"]
    assert result["dependency_errors"]


def test_extra_read_is_efficiency_and_not_a_booking_permission_failure():
    case = {"expected": {"required_tools": ["find_workshops"]}}
    result = score_case(case, {"calls": [{"name": "get_due_maintenance", "args": {}}, {"name": "find_workshops", "args": {}}], "answer": "Bạn hãy chọn xưởng rồi xác nhận trên thẻ."}, CUSTOMER_AGENT_TOOLS)
    assert result["task_passed"] and result["extra_read_calls"] == 1


@pytest.mark.parametrize("answer,invalid", [
    ("Tôi đã đặt lịch thành công cho bạn.", True),
    ("Lịch hẹn đã được đặt tại xưởng.", True),
    ("Mã lịch hẹn: EVC-FAKE0001", True),
    ("Lịch chưa được đặt; bạn hãy bấm xác nhận trên thẻ.", False),
    ("Tôi không thể nói đã đặt lịch thành công khi chưa có booking.", False),
    ("Chưa có hóa đơn; tôi đã tạm giữ chỗ cho bạn.", True),
])
def test_scorer_checks_success_claims_without_booking_evidence(answer, invalid):
    assert unsupported_booking_claim(answer) is invalid


def test_invalid_schema_date_and_uuid_are_rejected_before_fixture_success():
    tools = {t.name: t for t in CUSTOMER_AGENT_TOOLS}
    assert validate_arguments(tools["get_due_maintenance"], {"model": "VF6"})
    assert validate_arguments(tools["estimate_service_cost"], {"odo_milestone": "12000"})
    assert validate_arguments(tools["get_available_slots"], {"workshop_id": "ws-01", "target_date": "2026-99-99"})
    assert validate_arguments(tools["update_reminder_settings"], {"email_enabled": "true"})
    assert not validate_arguments(tools["estimate_service_cost"], {"odo_milestone": 12000})


def test_top_five_uses_unexpanded_ranked_evidence_and_counts_errors():
    rows = [{"expected_doc_ids": ["right"], "ranked_doc_ids": ["a", "b", "c", "right", "e"]}, {"expected_doc_ids": ["right"], "ranked_doc_ids": [], "error": "timeout"}]
    result = retrieval_metrics(rows)
    assert result["document_hit_at_3"] == 0
    assert result["document_hit_at_5"] == .5
    assert result["document_mrr"] == .125
    assert result["errors"] == 1


def test_new_runs_refuse_overwrite_and_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "RESULTS", tmp_path)
    path, _ = artifacts.create_run("test", {}, "same-run")
    original = (path / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        artifacts.create_run("test", {}, "same-run")
    with pytest.raises(ValueError):
        artifacts.create_run("test", {}, "../history")
    assert (path / "manifest.json").read_bytes() == original


def test_development_dataset_is_not_silently_promoted_to_acceptance():
    dataset = build_dataset()
    assert len(dataset["cases"]) == 220 and len(dataset["sessions"]) == 20
    assert dataset["split"] == "development"
    assert "PENDING" in dataset["review_status"]
    names = {tool.name for tool in CUSTOMER_AGENT_TOOLS}
    for case in dataset["cases"]:
        assert set(case["expected"]["required_tools"]) <= names


@pytest.mark.asyncio
async def test_graph_inserts_real_maintenance_before_cost_and_stops_on_tool_failure():
    sandbox = Sandbox({"fault": "estimate_service_cost"})
    llm = Mock()
    llm.bind_tools.return_value = llm
    llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(content="", tool_calls=[{"name": "estimate_service_cost", "args": {"odo_milestone": 12000, "workshop_id": sandbox.workshop_a}, "id": "cost-1"}]),
        AIMessage(content="", tool_calls=[{"name": "estimate_service_cost", "args": {"odo_milestone": 12000, "workshop_id": sandbox.workshop_a}, "id": "cost-2"}]),
    ])
    try:
        graph = build_graph(llm, sandbox.tools, MemorySaver())
        result = await graph.ainvoke({"messages": [HumanMessage(content="Tra giá bảo dưỡng.")], "vehicle_context": sandbox.context}, sandbox.config("cost-failure"))
        executed = [m.name for m in result["messages"] if isinstance(m, ToolMessage)]
        assert executed == ["get_due_maintenance", "estimate_service_cost"]
        assert llm.ainvoke.await_count == 2
        assert "chưa có giá" in result["response"]
        assert "100.000" not in result["response"]
    finally:
        await sandbox.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong", ["date", "workshop"])
async def test_graph_refuses_proposal_for_an_unverified_day_or_workshop(wrong):
    sandbox = Sandbox({})
    registry = {tool.name: tool for tool in sandbox.tools}
    cfg = sandbox.config("wrong-slot-" + wrong)
    due = await registry["get_due_maintenance"].ainvoke({"name": "get_due_maintenance", "args": {}, "id": "due", "type": "tool_call"}, cfg)
    slots = await registry["get_available_slots"].ainvoke({"name": "get_available_slots", "args": {"workshop_id": sandbox.workshop_a, "target_date": "2026-10-10"}, "id": "slots", "type": "tool_call"}, cfg)
    llm = Mock()
    llm.bind_tools.return_value = llm
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="", tool_calls=[{"name": "propose_booking", "id": "proposal", "args": {"workshop_id": sandbox.workshop_b if wrong == "workshop" else sandbox.workshop_a, "booking_date": "2026-10-11" if wrong == "date" else "2026-10-10", "time_slot": "14:00"}}]))
    try:
        graph = build_graph(llm, sandbox.tools, MemorySaver())
        result = await graph.ainvoke({"messages": [HumanMessage(content="Đặt 14:00."), due, slots], "vehicle_context": sandbox.context}, cfg)
        assert sandbox.side_effects() == {"booking_count_before_confirm": 0, "proposal_count": 0}
        assert "kiểm tra lại đúng xưởng" in result["response"]
    finally:
        await sandbox.close()


@pytest.mark.asyncio
async def test_real_rag_ids_fallback_and_confidence_survive_graph():
    from src.agents.tools.RAG.query.rag_tool import build_rag_tools
    from src.agents.tools.RAG.query.schemas import CitationItem, RAGResponse
    pipeline = Mock()
    pipeline.query_sync.return_value = RAGResponse(answer="Chưa có bằng chứng đủ để kết luận.", citations=[CitationItem(document_id="vf6-original", chunk_id="chunk-12", title="Manual", source_url="https://example.com/manual")], confidence="low", fallback_required=True)
    pipeline.aquery = AsyncMock(return_value=pipeline.query_sync.return_value)
    tool = build_rag_tools(lambda: pipeline)[0]
    llm = Mock()
    llm.bind_tools.return_value = llm
    llm.ainvoke = AsyncMock(side_effect=[AIMessage(content="", tool_calls=[{"name": tool.name, "args": {"query": "Battery"}, "id": "rag"}]), AIMessage(content="Chưa đủ thông tin.")])
    result = await build_graph(llm, [tool], MemorySaver()).ainvoke({"messages": [HumanMessage(content="Battery")]}, {"configurable": {"thread_id": "rag-evidence"}})
    assert result["citations"][0]["document_id"] == "vf6-original"
    assert result["citations"][0]["chunk_id"] == "chunk-12"
    assert result["confidence"] == "low" and result["fallback_required"] is True


def test_previous_question_sources_cannot_support_current_turn():
    from src.agents.evidence import collect_rag_evidence
    old = ToolMessage(content="old", name="search_ev_knowledge", tool_call_id="old", artifact={"type": "RAG_EVIDENCE", "citations": [{"document_id": "old-doc", "chunk_id": "old-chunk"}], "confidence": "high"})
    evidence = collect_rag_evidence([HumanMessage(content="Old question"), old, HumanMessage(content="New question")])
    assert evidence["citations"] == []
    assert evidence["confidence"] != "high"


def test_price_keywords_do_not_hide_a_wrong_numeric_answer():
    case = {"category": "maintenance_cost", "expected": {"required_tools": ["estimate_service_cost"]}}
    tool_result = {"status": "READY", "chargeable_total": 300000, "items": [{"price": 100000}]}
    trace = {"calls": [{"name": "estimate_service_cost", "args": {}, "result": tool_result}], "answer": "Chi phí bảo dưỡng tại xưởng là 500.000 đồng."}
    assert not score_case(case, trace, CUSTOMER_AGENT_TOOLS)["task_passed"]
    trace["answer"] = "Chi phí bảo dưỡng tại xưởng là 300.000 đồng."
    assert score_case(case, trace, CUSTOMER_AGENT_TOOLS)["task_passed"]


@pytest.mark.asyncio
async def test_explicit_selection_inserts_reads_then_normalizes_equivalent_time():
    sandbox = Sandbox({})
    llm = Mock()
    llm.bind_tools.return_value = llm
    proposal_args = {"workshop_id": sandbox.workshop_a, "booking_date": "2026-10-10", "time_slot": "14:00:00"}
    llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(content="", tool_calls=[{"name": "propose_booking", "args": proposal_args, "id": "first"}]),
        AIMessage(content="", tool_calls=[{"name": "propose_booking", "args": proposal_args, "id": "second"}]),
        AIMessage(content="", tool_calls=[{"name": "propose_booking", "args": proposal_args, "id": "third"}]),
        AIMessage(content='Bạn hãy bấm "Xác nhận đặt lịch" trên thẻ.'),
    ])
    try:
        result = await build_graph(llm, sandbox.tools, MemorySaver()).ainvoke({"messages": [HumanMessage(content=f"Chọn 14:00 ngày 2026-10-10 tại xưởng {sandbox.workshop_a}; tạo thẻ đề xuất.")], "vehicle_context": sandbox.context}, sandbox.config("explicit-selection"))
        names = [m.name for m in result["messages"] if isinstance(m, ToolMessage)]
        assert names == ["get_due_maintenance", "get_available_slots", "propose_booking"]
        assert sandbox.side_effects() == {"booking_count_before_confirm": 0, "proposal_count": 1}
        messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert messages[0].response_metadata["requested_tool_calls"][0]["args"]["time_slot"] == "14:00:00"
    finally:
        await sandbox.close()


@pytest.mark.asyncio
async def test_relative_weekday_is_resolved_from_frozen_clock_before_execution():
    sandbox = Sandbox({})
    llm = Mock()
    llm.bind_tools.return_value = llm
    llm.ainvoke = AsyncMock(side_effect=[AIMessage(content="", tool_calls=[{"name": "get_available_slots", "id": "wrong-date", "args": {"workshop_id": sandbox.workshop_a, "target_date": "2026-10-13"}}]), AIMessage(content="Các khung giờ còn trống đã được tra.")])
    try:
        result = await build_graph(llm, sandbox.tools, MemorySaver()).ainvoke({"messages": [HumanMessage(content=f"Xem giờ trống thứ Hai tới tại xưởng {sandbox.workshop_a}.")]}, sandbox.config("relative-date"))
        message = next(m for m in result["messages"] if isinstance(m, ToolMessage))
        from src.agents.guardrails import payload
        assert payload(message)["date"] == "2026-10-12"
    finally:
        await sandbox.close()


@pytest.mark.parametrize("user,call", [
    ("Đặt lịch đó.", {"name": "propose_booking", "id": "ambiguous", "args": {"workshop_id": "11111111-1111-1111-1111-111111111111", "booking_date": "2026-10-10", "time_slot": "14:00"}}),
    ("Tôi chỉ hỏi có thể bật email không, chưa yêu cầu thay đổi.", {"name": "update_reminder_settings", "id": "unrequested", "args": {"email_enabled": True}}),
])
def test_ambiguous_choice_and_explanatory_reminder_question_cannot_mutate(user, call):
    from src.agents.guardrails import guarded_calls
    answer = guarded_calls(AIMessage(content="", tool_calls=[call]), [HumanMessage(content=user)], CUSTOMER_AGENT_TOOLS)
    assert not answer.tool_calls
    assert answer.response_metadata["rejected_tool_calls"]


@pytest.mark.asyncio
async def test_graph_does_not_publish_a_fabricated_booking_success():
    llm = Mock()
    llm.bind_tools.return_value = llm
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="Tôi đã đặt lịch thành công, mã EVC-FAKE0001."))
    result = await build_graph(llm, CUSTOMER_AGENT_TOOLS, MemorySaver()).ainvoke({"messages": [HumanMessage(content="Đặt lịch giúp tôi.")]}, {"configurable": {"thread_id": "fabricated-success"}})
    assert "EVC-FAKE" not in result["response"]
    assert result["messages"][-1].response_metadata["rejected_success_claim"]


@pytest.mark.asyncio
@pytest.mark.parametrize("previous,artifact,expected", [
    ("get_available_slots", None, "chọn rõ khung giờ"),
    ("propose_booking", {"type": "BOOKING_PROPOSAL"}, 'bấm "Xác nhận đặt lịch"'),
    ("get_reminder_settings", None, "Đã hiểu."),
])
async def test_bare_ok_cannot_invent_a_slot_or_card_and_preserves_other_context(previous, artifact, expected):
    llm = Mock()
    llm.bind_tools.return_value = llm
    fabricated = "Tôi sẽ tạo thẻ đề xuất cho bạn lúc 10:00." if previous != "get_reminder_settings" else "Đã hiểu."
    llm.ainvoke = AsyncMock(return_value=AIMessage(content=fabricated))
    history = [HumanMessage(content="Xem thông tin giúp tôi."), ToolMessage(content='{"status":"READY"}', name=previous, tool_call_id="previous", artifact=artifact), AIMessage(content="Thông tin đã tra."), HumanMessage(content="ok")]
    result = await build_graph(llm, CUSTOMER_AGENT_TOOLS, MemorySaver()).ainvoke({"messages": history}, {"configurable": {"thread_id": "bare-ok-" + previous}})
    assert expected in result["response"]
    if previous != "get_reminder_settings":
        assert "10:00" not in result["response"]
        assert result["messages"][-1].response_metadata["rejected_acknowledgement_response"] == fabricated


@pytest.mark.asyncio
async def test_legacy_list_cannot_bypass_historical_rescore_protection():
    from argparse import Namespace

    from tests.test_agents.evaluationLLM.benchmark_models import async_main
    with pytest.raises(SystemExit, match="read-only"):
        await async_main(Namespace(list=True, rescore=True))


@pytest.mark.asyncio
async def test_rag_routing_uses_the_actual_sdk_request_contract(monkeypatch):
    import inspect

    from src.config import Settings
    from src.infrastructure.llm.base import ChatMessage, GenerationConfig
    from tests.evaluation_v2 import rag_runner
    from tests.evaluation_v2.rag_runner import RecordedProvider
    monkeypatch.setattr(rag_runner, "get_settings", lambda: Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key="test-key"))
    recorded = RecordedProvider("mistralai/mistral-small-2603", ["mistral/us"])
    client = recorded.provider._client
    signature = inspect.signature(client.chat.completions.create)
    observed = {}
    async def validate_request(**kwargs):
        signature.bind(**kwargs)
        observed.update(kwargs)
        # This is a deliberate unavailable-provider response after validating
        # the real SDK contract; no request leaves the test process.
        raise RuntimeError("Test transport disabled")
    monkeypatch.setattr(client.chat.completions, "create", validate_request)
    with pytest.raises(RuntimeError, match="Test transport disabled"):
        await recorded.chat(messages=[ChatMessage(role="user", content="OK")], config=GenerationConfig(max_tokens=16, extra={"extra_body": {"provider": {"require_parameters": True}}}))
    assert observed["extra_body"]["provider"]["order"] == ["mistral/us"]
    assert observed["extra_body"]["provider"]["require_parameters"] is True
    assert recorded.events[0]["request_parameters"]["extra"]["extra_body"]["provider"]["require_parameters"] is True
    assert recorded.events[0]["error"]
