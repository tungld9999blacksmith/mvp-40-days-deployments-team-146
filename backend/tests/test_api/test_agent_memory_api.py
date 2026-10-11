"""The memory API requires a token and scopes every action to its owner."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.modules.agent_memory import route
from src.modules.conversation import errors


@pytest.fixture
def memory_api():
    app = FastAPI()
    app.include_router(route.router)
    service = Mock()
    service.list.return_value = []
    service.enabled.return_value = True
    service.settings.agent_memory_read_enabled = True
    service.settings.agent_memory_write_enabled = True
    service.read_enabled_for.return_value = True
    service.write_enabled_for.return_value = True
    app.dependency_overrides[route.memory_service] = lambda: service
    app.dependency_overrides[route.get_current_user_id] = lambda: 17

    @app.exception_handler(errors.ConversationError)
    async def handle(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=errors.status_for(exc.code), content={"error": {"code": exc.code}})

    return TestClient(app), service


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/agent-memory", None),
        ("PATCH", "/agent-memory/settings", {"enabled": False}),
        ("DELETE", "/agent-memory", None),
    ],
)
def test_header_owner_without_token_is_rejected(memory_api, method, path, body):
    client, service = memory_api
    response = client.request(method, path, headers={"X-User-Id": "17"}, json=body)
    assert response.status_code == 401
    service.list.assert_not_called()
    service.forget.assert_not_called()
    service.set_enabled.assert_not_called()


def test_authenticated_owner_and_version_are_server_scoped(memory_api):
    client, service = memory_api
    headers = {"Authorization": "Bearer verified-by-overridden-guard", "X-User-Id": "999"}
    assert client.get("/agent-memory", headers=headers).status_code == 200
    service.list.assert_called_once_with(17, None)
    assert (
        client.patch("/agent-memory/settings", json={"enabled": False, "user_id": 999}, headers=headers).status_code
        == 422
    )
    assert client.patch("/agent-memory/settings", json={"enabled": False}, headers=headers).status_code == 200
    service.set_enabled.assert_called_once_with(17, False)
    mid = uuid4()
    assert client.delete(f"/agent-memory/{mid}", headers=headers).status_code == 204
    service.forget.assert_called_once_with(17, mid)


def test_edit_conflict_does_not_report_success(memory_api):
    client, service = memory_api
    service.edit.side_effect = errors.ConversationError("conflict", code="MEMORY_CONFLICT")
    response = client.patch(
        f"/agent-memory/{uuid4()}",
        headers={"Authorization": "Bearer test"},
        json={"value": {"format": "total"}, "version": 1},
    )
    assert response.status_code == 409


def test_list_flags_reflect_server_scoped_canary_access(memory_api):
    client, service = memory_api
    service.read_enabled_for.return_value = False
    service.write_enabled_for.return_value = False
    response = client.get("/agent-memory", headers={"Authorization": "Bearer test", "X-User-Id": "999"})
    assert response.status_code == 200
    assert response.json()["data"]["read_enabled"] is False
    assert response.json()["data"]["write_enabled"] is False
    service.read_enabled_for.assert_called_once_with(17)
    service.write_enabled_for.assert_called_once_with(17)
