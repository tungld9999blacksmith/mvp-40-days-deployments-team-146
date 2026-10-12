"""Memory contract: consent, isolation, deletion, retention and durable recovery."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field
from sqlalchemy import func
from sqlmodel import select

from src.agents.graph import build_graph
from src.agents.memory_context import ContextBudgetExceeded, build_memory_context, estimate_tokens
from src.agents.memory_guard import verified_memory_response
from src.agents.orchestrator import AgentOrchestrator
from src.common.core.conversation import ChatMessage, Conversation, MessageRole
from src.common.core.conversation.memory import AgentMemorySource, AgentUserMemory, ConversationSummary, MemoryCleanup
from src.common.core.vehicle import VehicleLinkStatus
from src.config import Settings
from src.modules.agent_memory.lifecycle import ConversationMemoryLifecycleService
from src.modules.agent_memory.preferences import PreferenceService, explicit_consent
from src.modules.agent_memory.summary import SummaryService
from src.modules.conversation.errors import ConversationBusy, ConversationError, ConversationNotFound, InvalidRequest
from tests._maintenance import add_workshop, make_session
from tests._user_vehicle import add_owner, add_vehicle
from tests.test_agents.test_checkpoint_history import FakeChat


@pytest.fixture
def memory_db():
    sessions = make_session()
    db = next(sessions)
    db.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    owner = add_owner(db)
    vehicle = add_vehicle(db, owner)
    other = add_owner(db, uid="other", email="other@example.com")
    other_vehicle = add_vehicle(db, other, vin="OTHER-VIN", external_vehicle_id="OTHER-VEH")
    conversation = Conversation(user_id=owner.user_id, user_vehicle_id=vehicle.id, last_message_at=datetime.now(UTC))
    db.add(conversation)
    db.commit()
    config = Settings(
        _env_file=None,
        app_env="test",
        agent_memory_context_mode="on",
        agent_memory_read_enabled=True,
        agent_memory_write_enabled=True,
    )
    yield db, config, owner, vehicle, other, other_vehicle, conversation
    sessions.close()


def append(db, cid, content, role=MessageRole.USER):
    seq = (db.exec(select(func.max(ChatMessage.seq))).one() or 0) + 1
    row = ChatMessage(conversation_id=cid, seq=seq, role=role, content=content)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remember(fixture, *, scope="account", text="Hãy nhớ tôi thích đặt lịch chiều thứ Bảy"):
    db, config, owner, vehicle, _, _, conversation = fixture
    source = append(db, conversation.id, text)
    row = PreferenceService(db, config).remember(
        owner.user_id,
        vehicle.id,
        conversation.id,
        source.id,
        "preferred_service_window",
        {"day": "saturday", "period": "afternoon"},
        scope,
    )
    return row, source


def test_canary_denies_recall_and_writes_but_preserves_view_and_delete(memory_db):
    db, config, owner, vehicle, other, _, conversation = memory_db
    row, source = remember(memory_db)
    service = PreferenceService(db, config)
    config.agent_memory_canary_user_ids = [other.user_id]
    assert not service.read_enabled_for(owner.user_id)
    assert not service.write_enabled_for(owner.user_id)
    assert service.recall(owner.user_id, vehicle.id) == []
    assert [r.id for r in service.list(owner.user_id, vehicle.id)] == [row.id]
    with pytest.raises(ConversationError, match="disabled"):
        service.remember(owner.user_id, vehicle.id, conversation.id, source.id,
                         "preferred_service_window", {"day": "saturday", "period": "afternoon"})
    with pytest.raises(ConversationError, match="disabled"):
        service.edit(owner.user_id, row.id, {"day": "sunday", "period": "morning"}, row.version)
    service.forget(owner.user_id, row.id)
    assert service.list(owner.user_id, vehicle.id) == []


def test_canary_never_overrides_global_flags_or_account_toggle(memory_db):
    db, config, owner, vehicle, _, _, _ = memory_db
    remember(memory_db)
    config.agent_memory_canary_user_ids = [owner.user_id]
    service = PreferenceService(db, config)
    assert service.recall(owner.user_id, vehicle.id)
    config.agent_memory_read_enabled = False
    config.agent_memory_write_enabled = False
    assert not service.read_enabled_for(owner.user_id)
    assert not service.write_enabled_for(owner.user_id)
    assert service.recall(owner.user_id, vehicle.id) == []
    config.agent_memory_read_enabled = True
    config.agent_memory_write_enabled = True
    service.set_enabled(owner.user_id, False)
    assert service.recall(owner.user_id, vehicle.id) == []
    with pytest.raises(ConversationError, match="disabled"):
        service._write_guard(owner.user_id)


@pytest.mark.parametrize(
    "text",
    [
        "Chiều thứ Bảy tuần này tôi rảnh",
        "Đừng nhớ tôi thích chiều thứ Bảy",
        "Hãy nhớ chiều thứ Bảy được không?",
        'Ví dụ: "hãy nhớ chiều thứ Bảy"',
        "Hãy nhớ tôi không thích chiều thứ Bảy",
    ],
)
def test_one_off_negated_question_and_quoted_requests_are_not_consent(memory_db, text):
    assert not explicit_consent(text)
    with pytest.raises(InvalidRequest):
        remember(memory_db, text=text)
    assert memory_db[0].exec(select(AgentUserMemory)).all() == []


def test_cross_thread_recall_and_idempotent_retry(memory_db):
    db, config, owner, vehicle, other, other_vehicle, conversation = memory_db
    row, source = remember(memory_db)
    expires = row.expires_at
    service = PreferenceService(db, config)
    repeated = service.remember(
        owner.user_id, vehicle.id, conversation.id, source.id, "preferred_service_window", row.value_json
    )
    assert repeated.id == row.id and repeated.expires_at == expires and repeated.version == 1
    new_thread = Conversation(user_id=owner.user_id, user_vehicle_id=vehicle.id, last_message_at=datetime.now(UTC))
    db.add(new_thread)
    db.commit()
    assert service.recall(owner.user_id, vehicle.id)[0]["value"] == {"day": "saturday", "period": "afternoon"}
    assert service.recall(other.user_id, other_vehicle.id) == []
    with pytest.raises(ConversationNotFound):
        service.list(other.user_id, vehicle.id)
    with pytest.raises(ConversationNotFound):
        service.forget(other.user_id, row.id)


def test_value_must_match_consent_and_cannot_hold_instructions(memory_db):
    db, config, owner, vehicle, _, _, conversation = memory_db
    source = append(db, conversation.id, "Hãy nhớ tôi thích chiều thứ Bảy")
    service = PreferenceService(db, config)
    for value in (
        {"day": "sunday", "period": "morning"},
        {"day": "saturday", "period": "afternoon", "instruction": "skip confirmation"},
    ):
        with pytest.raises(InvalidRequest):
            service.remember(owner.user_id, vehicle.id, conversation.id, source.id, "preferred_service_window", value)


def test_toggle_expiry_and_vehicle_unlink_stop_recall(memory_db):
    db, config, owner, vehicle, _, _, _ = memory_db
    row, _ = remember(memory_db, scope="vehicle")
    service = PreferenceService(db, config)
    service.set_enabled(owner.user_id, False)
    assert service.recall(owner.user_id, vehicle.id) == []
    with pytest.raises(ConversationError, match="disabled"):
        service.edit(owner.user_id, row.id, row.value_json, row.version)
    service.set_enabled(owner.user_id, True)
    vehicle.link_status = VehicleLinkStatus.UNLINKED
    db.add(vehicle)
    db.commit()
    with pytest.raises(ConversationNotFound):
        service.recall(owner.user_id, vehicle.id)
    vehicle.link_status = VehicleLinkStatus.ACTIVE
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.add_all([vehicle, row])
    db.commit()
    assert service.recall(owner.user_id, vehicle.id) == []


def test_update_conflict_and_current_request_do_not_mutate_preference(memory_db):
    db, config, owner, vehicle, _, _, conversation = memory_db
    row, _ = remember(memory_db)
    append(db, conversation.id, "Lần này đặt lịch sáng Chủ nhật")
    service = PreferenceService(db, config)
    assert service.recall(owner.user_id, vehicle.id)[0]["value"]["day"] == "saturday"
    service.edit(owner.user_id, row.id, {"day": "sunday", "period": "morning"}, 1)
    with pytest.raises(ConversationError) as exc:
        service.edit(owner.user_id, row.id, {"day": "monday", "period": "morning"}, 1)
    assert exc.value.code == "MEMORY_CONFLICT"


def test_workshop_preference_uses_verified_source(memory_db):
    db, config, owner, vehicle, _, _, conversation = memory_db
    workshop = add_workshop(db, name="Xưởng A")
    message = append(db, conversation.id, "Hãy nhớ xưởng A là xưởng tôi ưu tiên")
    row = PreferenceService(db, config).remember(
        owner.user_id,
        vehicle.id,
        conversation.id,
        message.id,
        "preferred_workshop_id",
        {"workshop_id": str(workshop.id)},
    )
    assert row.value_json["workshop_id"] == str(workshop.id)


@asynccontextmanager
async def unlocked(cid):
    yield


@pytest.mark.asyncio
async def test_delete_revokes_sources_and_retries_cleanup(memory_db):
    db, config, owner, _, _, _, conversation = memory_db
    row, _ = remember(memory_db)
    row_id, cid = row.id, conversation.id
    db.add(ConversationSummary(conversation_id=cid, summary_json={"user_quotes": []}))
    db.commit()
    saver = Mock(adelete_thread=AsyncMock(side_effect=RuntimeError("unavailable")))
    lifecycle = ConversationMemoryLifecycleService(db.bind, config, unlocked, saver, lambda: Mock())
    await lifecycle.delete(owner.user_id, cid)
    db.expire_all()
    assert db.get(Conversation, cid) is None
    assert db.get(AgentUserMemory, row_id) is None
    assert db.get(ConversationSummary, cid) is None
    assert db.exec(select(ChatMessage).where(ChatMessage.conversation_id == cid)).all() == []
    task = db.get(MemoryCleanup, cid)
    assert task.attempts == 1 and task.last_error == "RuntimeError"

    @asynccontextmanager
    async def busy(cid):
        raise ConversationBusy()
        yield

    lifecycle.run_lock = busy
    assert (await lifecycle.cleanup_pending())["busy"] == 1
    assert saver.adelete_thread.call_count == 1
    lifecycle.run_lock = unlocked
    saver.adelete_thread.side_effect = None
    assert (await lifecycle.cleanup_pending())["completed"] == 1
    db.expire_all()
    assert db.get(MemoryCleanup, cid) is None
    assert await lifecycle.cleanup_one(cid)


@pytest.mark.asyncio
async def test_busy_delete_and_retention_dry_run(memory_db):
    db, config, owner, _, _, _, conversation = memory_db
    conversation.last_message_at = datetime.now(UTC) - timedelta(days=181)
    db.add(conversation)
    db.commit()

    @asynccontextmanager
    async def busy(cid):
        raise ConversationBusy()
        yield

    lifecycle = ConversationMemoryLifecycleService(db.bind, config, busy, Mock(adelete_thread=AsyncMock()))
    with pytest.raises(ConversationBusy):
        await lifecycle.delete(owner.user_id, conversation.id)
    preview = await lifecycle.purge()
    assert preview["selected_ids"] == [str(conversation.id)] and preview["deleted"] == 0
    assert (await lifecycle.purge(dry_run=False))["busy"] == 1
    assert db.get(Conversation, conversation.id) is not None
    lifecycle.run_lock = unlocked
    assert (await lifecycle.purge(dry_run=False))["deleted"] == 1


@pytest.mark.asyncio
async def test_cleanup_marks_expired_preferences_without_deleting_source(memory_db):
    db, config, _, _, _, _, conversation = memory_db
    row, _ = remember(memory_db)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.add(row)
    db.commit()
    lifecycle = ConversationMemoryLifecycleService(db.bind, config, unlocked, Mock(adelete_thread=AsyncMock()))
    assert (await lifecycle.cleanup_pending())["expired_preferences"] == 1
    db.expire_all()
    assert db.get(AgentUserMemory, row.id).status == "expired"
    assert db.get(Conversation, conversation.id) is not None


def test_summary_preserves_early_choice_as_quote_and_recovers_after_cursor(memory_db):
    db, config, _, _, _, _, conversation = memory_db
    texts = ["Tôi muốn chọn xưởng A vào chiều thứ Bảy. Pin có hỏng không?"] + [
        f"Trao đổi số {i}, chưa chọn thêm gì." for i in range(69)
    ]
    for text in texts:
        append(db, conversation.id, text)
        append(db, conversation.id, "Thông tin cần kiểm chứng bằng tool.", MessageRole.ASSISTANT)
    service = SummaryService(db.bind, config)
    summary = service.update(conversation.id, force=True)
    assert summary is not None
    assert any(texts[0] == q["text"] for q in summary["summary"]["user_quotes"])
    assert all(q["kind"] == "user_quote" for q in summary["summary"]["user_quotes"])
    history, data = service.history(conversation.id)
    assert len(history) == 12 and data == summary["summary"]
    assert len({m.id for m in history}) == len(history)
    context = build_memory_context(history, "Tra tool và xác nhận trước giao dịch.", config, summary=data)
    assert context.estimated_tokens <= context.budget
    assert "Pin có hỏng không?" in str(context.messages[1].content)


def test_budget_keeps_current_tool_group_and_rejects_oversized_turn():
    config = Settings(_env_file=None, agent_memory_context_mode="on", agent_memory_input_token_budget=1000)
    old = [
        message
        for i in range(70)
        for message in (HumanMessage(content="Old statement " * 30), AIMessage(content="Old answer " * 30))
    ]
    current = [
        HumanMessage(content="Tra slot"),
        AIMessage(content="", tool_calls=[{"name": "read", "args": {}, "id": "call-1", "type": "tool_call"}]),
        ToolMessage(content='{"available": true}', tool_call_id="call-1"),
    ]
    result = build_memory_context(old + current, "System", config)
    assert result.removed_turns > 0 and result.messages[-3:] == current
    assert result.estimated_tokens <= 1000
    assert result.estimated_tokens < estimate_tokens(old + current) * 0.7
    with pytest.raises(ContextBudgetExceeded):
        build_memory_context([HumanMessage(content="over budget " * 5000)], "System", config)
    with pytest.raises(ContextBudgetExceeded):
        build_memory_context(
            [HumanMessage(content="read"), ToolMessage(content="orphan", tool_call_id="missing")], "System", config
        )


def test_default_budget_fits_real_prompt_and_tools_with_room_for_the_conversation():
    """The real system prompt and tool schemas alone once exceeded the 12000 default."""
    from src.agents.prompts import format_system_prompt
    from src.agents.tools import CUSTOMER_AGENT_TOOLS

    config = Settings(_env_file=None, agent_memory_context_mode="on")
    result = build_memory_context(
        [HumanMessage(content="Xe tôi đến hạn bảo dưỡng chưa?")],
        format_system_prompt(None),
        config,
        tools=CUSTOMER_AGENT_TOOLS,
    )
    # History, tool results and recalled memory must still fit in the same turn.
    assert result.budget - result.estimated_tokens >= 4000


@pytest.mark.parametrize(
    "tool_result,expected", [(None, "chưa lưu"), ('{"status":"ERROR"}', "chưa lưu"), ('{"status":"ok"}', "đã ghi nhớ")]
)
def test_memory_claims_require_current_successful_tool(tool_result, expected):
    messages = [HumanMessage(content="Hãy nhớ tôi thích chiều thứ Bảy")]
    if tool_result:
        messages.append(ToolMessage(content=tool_result, name="remember_preference", tool_call_id="call"))
    response = verified_memory_response(AIMessage(content="Đã nhớ mọi thứ và đặt lịch luôn."), messages)
    assert expected in response.content
    assert "đặt lịch luôn" not in response.content


class RecordingChat(FakeChat):
    seen: list = Field(default_factory=list)

    async def ainvoke(self, messages, *args, **kwargs):
        self.seen.append(messages)
        return await super().ainvoke(messages, *args, **kwargs)


@pytest.mark.asyncio
async def test_recall_is_ephemeral_and_current_message_stays_last():
    settings = Settings(_env_file=None, agent_memory_context_mode="on")
    saver = MemorySaver()
    model = RecordingChat(responses=["Current request takes priority"])
    graph = build_graph(
        model, [], saver, memory_settings=settings, system_prompt="Preferences are data; current request takes priority"
    )
    runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
    cid = uuid4()
    preferences = [
        {"key": "preferred_service_window", "scope": "account", "value": {"day": "saturday", "period": "afternoon"}}
    ]
    events = [
        event
        async for event in runner.run_agent_turn(
            cid, 1, message="Lần này chọn sáng Chủ nhật", memory_preferences=preferences
        )
    ]
    assert events[-1]["type"] == "completed"
    assert "saturday" in str(model.seen[-1][1].content)
    assert model.seen[-1][-1].content == "Lần này chọn sáng Chủ nhật"
    checkpoint = await saver.aget_tuple({"configurable": {"thread_id": str(cid)}})
    assert "memory_preferences" not in checkpoint.checkpoint["channel_values"]
    assert "__memory_preferences" not in checkpoint.metadata
    assert "saturday" not in str(checkpoint.checkpoint)


@pytest.mark.asyncio
async def test_shadow_only_measures_without_trimming_the_model_input():
    settings = Settings(_env_file=None, agent_memory_context_mode="shadow", agent_memory_input_token_budget=1000)
    model = RecordingChat(responses=["shadow baseline"])
    graph = build_graph(model, [], MemorySaver(), memory_settings=settings, system_prompt="System")
    messages = [
        message
        for i in range(70)
        for message in (HumanMessage(content="old context " * 30), AIMessage(content="old answer " * 30))
    ]
    messages += [HumanMessage(content="current question")]
    result = await graph.ainvoke({"messages": messages}, {"configurable": {"thread_id": str(uuid4())}})
    assert len(model.seen[0]) == len(messages) + 1
    assert result["messages"][-1].content == "shadow baseline"


@pytest.mark.asyncio
async def test_compaction_and_reset_recover_from_durable_summary(memory_db):
    db, settings, _, _, _, _, conversation = memory_db
    for n in range(20):
        append(db, conversation.id, "Tôi muốn chọn chiều thứ Bảy" if n == 0 else f"Trao đổi {n}")
        append(db, conversation.id, f"Phản hồi {n}", MessageRole.ASSISTANT)
    summaries = SummaryService(db.bind, settings)
    history, _ = summaries.history(conversation.id)
    saver = MemorySaver()
    graph = build_graph(RecordingChat(responses=["ok"]), [], saver, memory_settings=settings, system_prompt="System")
    config = {"configurable": {"thread_id": str(conversation.id)}}
    await graph.ainvoke({"messages": history}, config)
    runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
    summary = summaries.update(conversation.id, force=True)
    await runner.compact_committed_history(conversation.id, summary)
    summaries.mark_compacted(conversation.id, summary["version"])
    assert len((await graph.aget_state(config)).values["messages"]) <= 13
    await saver.adelete_thread(str(conversation.id))
    recovered_history, recovered_summary = summaries.history(conversation.id)
    events = [
        event
        async for event in runner.run_agent_turn(
            conversation.id, 1, message="Tiếp tục", history_messages=recovered_history, memory_summary=recovered_summary
        )
    ]
    assert events[-1]["message_data"]["content"] == "ok"
    restored = (await graph.aget_state(config)).values
    assert any("chiều thứ Bảy" in quote["text"] for quote in restored["memory_summary"]["user_quotes"])
    assert len({message.id for message in restored["messages"]}) == len(restored["messages"])


def test_summary_masks_contact_data_and_shadow_recovery_keeps_baseline(memory_db):
    db, settings, _, _, _, _, conversation = memory_db
    append(db, conversation.id, "Tôi muốn xưởng A, email owner@example.com và số 0912345678")
    append(db, conversation.id, "Đã đọc", MessageRole.ASSISTANT)
    for n in range(20):
        append(db, conversation.id, f"Trao đổi {n}")
        append(db, conversation.id, "Phản hồi", MessageRole.ASSISTANT)
    settings.agent_memory_context_mode = "shadow"
    service = SummaryService(db.bind, settings)
    summary = service.update(conversation.id, force=True)
    assert "owner@example.com" not in str(summary["summary"])
    assert "0912345678" not in str(summary["summary"])
    history, data = service.history(conversation.id)
    assert len(history) == 20 and data == {}


@pytest.mark.parametrize("revocation", ["expire", "disable", "delete"])
@pytest.mark.asyncio
async def test_revoked_cost_preference_cannot_be_claimed_by_graph(memory_db, revocation):
    from langgraph.checkpoint.memory import MemorySaver

    from src.agents.graph import build_graph
    from src.agents.tools import CUSTOMER_AGENT_TOOLS
    from tests.test_agents.test_checkpoint_history import FakeChat

    db, settings, owner, vehicle, _, _, conversation = memory_db
    source = append(db, conversation.id, "Hãy nhớ tôi muốn xem chi phí theo từng hạng mục.")
    service = PreferenceService(db, settings)
    row = service.remember(owner.user_id, vehicle.id, conversation.id, source.id,
                           "cost_display_preference", {"format": "itemized"})
    if revocation == "expire":
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
        db.add(row)
        db.commit()
    elif revocation == "disable":
        service.set_enabled(owner.user_id, False)
    else:
        service.forget(owner.user_id, row.id)
    available = service.recall(owner.user_id, vehicle.id)
    assert not available
    model = FakeChat(responses=["Bạn đã lưu sở thích xem từng hạng mục (itemized)."])
    graph = build_graph(model, CUSTOMER_AGENT_TOOLS, MemorySaver(), memory_settings=settings)
    state = await graph.ainvoke(
        {"messages": [HumanMessage(content="Theo thông tin đang ghi nhớ, tôi thích định dạng chi phí nào? Không tra giá.")]},
        {"configurable": {"thread_id": str(uuid4()), "__memory_preferences": available}},
    )
    assert "Chưa có" in state["messages"][-1].content
    assert "itemized" not in state["messages"][-1].content
