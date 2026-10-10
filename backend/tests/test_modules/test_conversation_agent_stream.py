"""Unit test verifying ChatService streaming integration with LangGraph Agent Orchestrator (Mục 6 README)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.common.core.conversation import MessageRole
from src.common.core.vehicle import UserVehicle, VehicleLinkStatus
from src.modules.conversation.schemas import SseFrame
from src.modules.conversation.service import ChatService


@pytest.mark.asyncio
@pytest.mark.parametrize("completed_content,stream_tokens,metadata", [
    ("Xe của bạn đến hạn bảo dưỡng 6 tháng.", True, {}),
    ("Chưa có lịch hẹn được tạo. Hãy bấm xác nhận trên thẻ.", True, {"confidence": "low", "fallback_required": True}),
    ("Hệ thống chưa tra được dự toán chi phí.", False, {"confidence": "low", "fallback_required": True}),
])
async def test_chat_service_run_turn_with_agent_orchestrator(completed_content, stream_tokens, metadata):
    """Kiểm tra ChatService._run_turn tích hợp với run_agent_turn và phát đầy đủ SSE frames."""
    conversation_id = uuid4()
    user_id = 123
    client_message_id = uuid4()
    content = "Xe Evo200 đi 5760 km bảo dưỡng gì?"
    trace_id = "test-trace-id"

    # Mock UserVehicle
    vehicle = MagicMock(spec=UserVehicle)
    vehicle.id = uuid4()
    vehicle.external_model_id = "Evo200"
    vehicle.declared_model_id = None
    vehicle.license_plate = "29-AA 123.45"
    vehicle.odometer_km = 5760
    vehicle.last_service_odometer_km = 5100
    vehicle.months_since_last_service = 7
    vehicle.link_status = VehicleLinkStatus.ACTIVE

    from datetime import UTC, datetime

    # Mock MessageService
    mock_messages = MagicMock()
    user_msg_mock = MagicMock()
    user_msg_mock.id = uuid4()
    user_msg_mock.seq = 1
    user_msg_mock.role = MessageRole.USER
    user_msg_mock.content = content
    user_msg_mock.created_at = datetime.now(UTC)
    user_msg_mock.citations = []
    user_msg_mock.refs = {}
    user_msg_mock.card = None

    user_result_mock = MagicMock()
    user_result_mock.created = True
    user_result_mock.message = user_msg_mock
    mock_messages.append = AsyncMock()
    mock_messages.publish = AsyncMock()

    # User message append result
    assistant_msg_mock = MagicMock()
    assistant_msg_mock.id = uuid4()
    assistant_msg_mock.seq = 2
    assistant_msg_mock.role = MessageRole.ASSISTANT
    assistant_msg_mock.content = completed_content
    assistant_msg_mock.created_at = datetime.now(UTC)
    assistant_msg_mock.citations = [{"documentId": "DOC-EVO200"}]
    assistant_msg_mock.refs = {}
    assistant_msg_mock.card = None

    assistant_result_mock = MagicMock()
    assistant_result_mock.message = assistant_msg_mock

    mock_messages.append.side_effect = [user_result_mock, assistant_result_mock]

    # Inject the agent runner; no global function patch or production DB lookup.
    orchestrator = MagicMock()
    orchestrator.fetch_vehicle_context = AsyncMock(return_value={})
    orchestrator.record_committed_answer = AsyncMock()

    # Mock dependencies for ChatService
    service = ChatService(
        engine=MagicMock(),
        message_service=mock_messages,
        toolkit=MagicMock(),
        llm=MagicMock(),
        knowledge_store=MagicMock(),
        vector_store=MagicMock(),
        settings=MagicMock(chat_run_timeout_seconds=30),
        orchestrator=orchestrator,
    )

    # Mock _build_history_messages to return empty list
    service._build_history_messages = MagicMock(return_value=[])

    # Mock run_agent_turn to yield tool_start, token, completed
    async def fake_agent_turn(**kwargs):
        yield {"type": "tool_start", "tool": "get_due_maintenance", "input": {"model": "Evo200"}}
        yield {"type": "tool_end", "tool": "get_due_maintenance", "output": {"due": True}}
        if stream_tokens:
            yield {"type": "token", "delta": "Xe của bạn "}
            yield {"type": "token", "delta": "đến hạn bảo dưỡng 6 tháng."}
        yield {
            "type": "completed",
            "message_data": {
                "citations": [{"documentId": "DOC-EVO200"}],
                "content": completed_content,
                **metadata,
            },
        }

    orchestrator.run_agent_turn.side_effect = fake_agent_turn
    frames: list[SseFrame] = []
    async for frame in service._run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        vehicle=vehicle,
        client_message_id=client_message_id,
        content=content,
        trace_id=trace_id,
        is_disconnected=None,
    ):
        frames.append(frame)

    orchestrator.fetch_vehicle_context.assert_awaited_once_with(vehicle.id)
    run_args = orchestrator.run_agent_turn.call_args.kwargs
    assert run_args["vehicle_id"] == vehicle.id
    assert run_args["user_id"] == user_id
    assert run_args["source_message_id"] == user_msg_mock.id
    assert run_args["operation_key"] == str(client_message_id)
    orchestrator.record_committed_answer.assert_awaited_once_with(
        conversation_id, assistant_msg_mock.id, assistant_msg_mock.content,
    )

    # Kiểm tra các sự kiện SSE phát ra
    events = [f.event for f in frames]
    assert events[0] == "message.accepted"
    assert events[1] == "status"
    assert frames[1].data["stage"] == "analyzing"
    assert events[2] == "status"
    assert "get_due_maintenance" in frames[2].data["stage"]
    if stream_tokens:
        assert events[3] == "token"
        assert frames[3].data["delta"] == "Xe của bạn "
        assert events[4] == "token"
        assert frames[4].data["delta"] == "đến hạn bảo dưỡng 6 tháng."
    else:
        assert "token" not in events
    assert events[-1] == "message.completed"

    # Kiểm tra lưu trữ assistant message vào database
    assert mock_messages.append.call_count == 2
    assistant_call = mock_messages.append.call_args_list[1]
    assert assistant_call[0][0] == conversation_id
    assert assistant_call[0][1] == MessageRole.ASSISTANT
    assert assistant_call[0][2] == completed_content
    assert assistant_call[1]["citations"] == [{"documentId": "DOC-EVO200"}]
    assert assistant_call[1]["refs"] == ({"rag": metadata} if metadata else {})


@pytest.mark.asyncio
async def test_chat_turn_saves_the_quote_card_of_create_draft_quote():
    """AI-005 TOOL-501: the QUOTE card artifact goes on the answer; the LLM never sees it."""
    from datetime import UTC, datetime

    from langchain_core.messages import ToolMessage

    conversation_id = uuid4()
    vehicle = MagicMock(spec=UserVehicle)
    vehicle.id = uuid4()
    vehicle.link_status = VehicleLinkStatus.ACTIVE

    def _message(role, seq):
        msg = MagicMock()
        msg.id, msg.seq, msg.role, msg.content = uuid4(), seq, role, "x"
        msg.created_at, msg.citations, msg.refs, msg.card = datetime.now(UTC), [], {}, None
        result = MagicMock()
        result.created, result.message = True, msg
        return result

    messages = MagicMock()
    messages.append = AsyncMock(side_effect=[_message(MessageRole.USER, 1), _message(MessageRole.ASSISTANT, 2)])
    messages.publish = AsyncMock()
    orchestrator = MagicMock()
    orchestrator.fetch_vehicle_context = AsyncMock(return_value={"vehicle_id": str(vehicle.id)})
    orchestrator.record_committed_answer = AsyncMock()
    card = {"type": "QUOTE", "quote": {"quoteId": str(uuid4()), "displayStatus": "DRAFT"}}

    async def fake_agent_turn(**kwargs):
        output = ToolMessage(content='{"status": "DRAFT"}', tool_call_id="call-1", artifact=card)
        yield {"type": "tool_end", "tool": "create_draft_quote", "output": output}
        yield {"type": "completed", "message_data": {"citations": []}}

    orchestrator.run_agent_turn.side_effect = fake_agent_turn
    service = ChatService(
        engine=MagicMock(),
        message_service=messages,
        toolkit=MagicMock(),
        llm=MagicMock(),
        knowledge_store=MagicMock(),
        vector_store=MagicMock(),
        settings=MagicMock(chat_run_timeout_seconds=30),
        orchestrator=orchestrator,
    )
    service._build_history_messages = MagicMock(return_value=[])
    service._attach_proposal_message = MagicMock()

    async for _frame in service._run_turn(
        conversation_id=conversation_id,
        user_id=123,
        vehicle=vehicle,
        client_message_id=uuid4(),
        content="Gửi xưởng báo giá giúp tôi",
        trace_id="t",
        is_disconnected=None,
    ):
        pass

    answer_call = messages.append.call_args_list[1]
    assert answer_call.kwargs["card"] == card
    assert "Gửi xưởng duyệt" in answer_call.args[2]  # the model said nothing: fallback text
    service._attach_proposal_message.assert_not_called()  # only proposals link back to the message
