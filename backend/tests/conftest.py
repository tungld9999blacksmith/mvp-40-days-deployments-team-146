from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def pytest_addoption(parser):
    parser.addoption("--run-live", action="store_true", help="Opt in to tests calling external LLM/Qdrant APIs")
    parser.addoption("--run-staging", action="store_true", help="Opt in to isolated EVAL_DATABASE_URL/EVAL_REDIS_URL tests")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: calls external providers; explicit --run-live required")
    config.addinivalue_line("markers", "staging: writes exclusively to an isolated evaluation database/schema")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "live" in item.keywords and not config.getoption("--run-live"):
            item.add_marker(pytest.mark.skip(reason="Live APIs require --run-live"))
        if "staging" in item.keywords and not config.getoption("--run-staging"):
            item.add_marker(pytest.mark.skip(reason="Staging writes require --run-staging and isolated EVAL URLs"))


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing API endpoints."""
    # Demo tests inject their own app and must not initialize SQL/Firebase
    # production configuration just to collect the test suite.
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock
