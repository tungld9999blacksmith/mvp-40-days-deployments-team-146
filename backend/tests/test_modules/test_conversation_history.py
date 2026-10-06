"""Loading chat history must not initialize AI or issue one query per preview."""

from unittest.mock import Mock

from sqlalchemy import event

from src.agents import dependency as agent_dependency
from src.common.core.conversation import ChatMessage, Conversation, MessageRole
from src.infrastructure.vectorstore import dependency as vector_dependency
from src.modules.conversation import dependency
from tests._user_vehicle import NOW, add_owner, add_vehicle, make_session


def test_history_loads_without_ai_services_and_batches_previews(monkeypatch):
    unavailable = Mock(side_effect=RuntimeError("AI service unavailable"))
    monkeypatch.setattr(agent_dependency, "get_agent_orchestrator", unavailable)
    monkeypatch.setattr(vector_dependency, "get_knowledge_vector_store", unavailable)
    monkeypatch.setattr(vector_dependency, "get_vector_store", unavailable)
    monkeypatch.setattr(dependency, "get_message_service", lambda: Mock())
    monkeypatch.setattr(dependency, "get_redis_toolkit", lambda: Mock())

    for session in make_session():
        owner = add_owner(session)
        vehicle = add_vehicle(session, owner)
        conversations = [
            Conversation(user_id=owner.user_id, user_vehicle_id=vehicle.id, last_message_at=NOW) for _ in range(3)
        ]
        session.add_all(conversations)
        session.flush()
        ids = [c.id for c in conversations]
        messages = [
            ChatMessage(conversation_id=ids[0], seq=1, role=MessageRole.USER, content="Old message"),
            ChatMessage(conversation_id=ids[0], seq=2, role=MessageRole.ASSISTANT, content="Latest answer"),
            ChatMessage(
                conversation_id=ids[0],
                seq=3,
                role=MessageRole.TOOL,
                content="Internal tool output",
                tool_call_id="call-1",
                tool_name="maintenance",
            ),
            ChatMessage(conversation_id=ids[1], seq=4, role=MessageRole.USER, content="x" * 150),
        ]
        session.add_all(messages)
        session.commit()
        monkeypatch.setattr(dependency, "engine", session.bind)
        service = dependency.get_chat_service.__wrapped__()
        items, _, _ = service.list_conversations(owner.user_id, vehicle.id, 20, None)
        assert {c.id for c in items} == set(ids)

        statements = []

        def record_statement(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(session.bind, "before_cursor_execute", record_statement)
        try:
            previews = service.last_message_previews(ids)
            assert service.last_message_previews([]) == {}
        finally:
            event.remove(session.bind, "before_cursor_execute", record_statement)
        assert previews == {ids[0]: "Latest answer", ids[1]: "x" * 100}
        assert len(statements) == 1
        unavailable.assert_not_called()
