"""Tests for step5_frozen_transport_retry_v2 transport-fix additions.

Covers:
- _is_transport_error detection
- TimeoutReadOnlyStore accepts external client (Option A interface)
- TimeoutReadOnlyStore closes client on init failure (same as v1 contract)
- TimeoutReadOnlyStore exposes .client attribute
- budget accounting unchanged from v1
"""
import errno
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import step5_frozen_transport_retry_v2 as execution


# ---------------------------------------------------------------------------
# _is_transport_error
# ---------------------------------------------------------------------------

def test_is_transport_error_connection_reset_error():
    assert execution._is_transport_error(ConnectionResetError("reset"))


def test_is_transport_error_oserror_10054():
    exc = OSError()
    exc.errno = 10054
    assert execution._is_transport_error(exc)


def test_is_transport_error_string_match_10054():
    exc = Exception("WinError 10054 connection reset")
    assert execution._is_transport_error(exc)


def test_is_transport_error_string_match_connection_reset():
    exc = RuntimeError("ConnectionResetError underlying transport")
    assert execution._is_transport_error(exc)


def test_is_transport_error_false_for_unrelated():
    assert not execution._is_transport_error(ValueError("not a transport error"))


def test_is_transport_error_cause_chain():
    inner = ConnectionResetError("inner")
    outer = RuntimeError("outer")
    outer.__cause__ = inner
    assert execution._is_transport_error(outer)


# ---------------------------------------------------------------------------
# TimeoutReadOnlyStore — same core contract as v1
# ---------------------------------------------------------------------------

def test_timeout_is_applied_to_read_only_client_without_changing_settings():
    settings = SimpleNamespace(qdrant_url="https://example.invalid", qdrant_api_key="fixture",
                               qdrant_prefer_grpc=False)
    client = MagicMock()
    with patch.object(execution.common, "get_settings", return_value=settings), \
         patch("qdrant_client.QdrantClient", return_value=client) as factory, \
         patch.object(execution.common.ReadOnlyStore, "__init__", return_value=None) as parent:
        store = execution.TimeoutReadOnlyStore(embedding_provider="fixture_embedding")
    factory.assert_called_once_with(url=settings.qdrant_url, api_key=settings.qdrant_api_key,
                                    prefer_grpc=False, timeout=60)
    parent.assert_called_once_with(embedding_provider="fixture_embedding")
    client.close.assert_not_called()
    assert vars(settings) == {"qdrant_url": "https://example.invalid", "qdrant_api_key": "fixture",
                              "qdrant_prefer_grpc": False}


def test_failed_read_only_initialization_closes_client():
    settings = SimpleNamespace(qdrant_url="https://example.invalid", qdrant_api_key="fixture",
                               qdrant_prefer_grpc=False)
    client = MagicMock()
    with patch.object(execution.common, "get_settings", return_value=settings), \
         patch("qdrant_client.QdrantClient", return_value=client), \
         patch.object(execution.common.ReadOnlyStore, "__init__", side_effect=RuntimeError("read failed")), \
         pytest.raises(RuntimeError, match="read failed"):
        execution.TimeoutReadOnlyStore()
    client.close.assert_called_once_with()


def test_store_exposes_client_attribute():
    """v2: store._eval_client must be set after successful init (used by Option A loop)."""
    settings = SimpleNamespace(qdrant_url="https://example.invalid", qdrant_api_key="fixture",
                               qdrant_prefer_grpc=False)
    client = MagicMock()
    with patch.object(execution.common, "get_settings", return_value=settings), \
         patch("qdrant_client.QdrantClient", return_value=client), \
         patch.object(execution.common.ReadOnlyStore, "__init__", return_value=None):
        store = execution.TimeoutReadOnlyStore(embedding_provider="x")
    assert store._eval_client is client


def test_external_client_not_closed_on_failure():
    """When caller passes client=, init failure must NOT close the external client."""
    settings = SimpleNamespace(qdrant_url="https://example.invalid", qdrant_api_key="fixture",
                               qdrant_prefer_grpc=False)
    external_client = MagicMock()
    with patch.object(execution.common, "get_settings", return_value=settings), \
         patch.object(execution.common.ReadOnlyStore, "__init__", side_effect=RuntimeError("boom")), \
         pytest.raises(RuntimeError, match="boom"):
        execution.TimeoutReadOnlyStore(client=external_client)
    external_client.close.assert_not_called()


# ---------------------------------------------------------------------------
# Budget accounting — unchanged from v1
# ---------------------------------------------------------------------------

def test_budget_includes_aborted_run_and_new_pilots_once(tmp_path, monkeypatch):
    aborted = tmp_path / "aborted"
    master = tmp_path / "new"
    aborted.mkdir()
    for name in ("pilot_base", "repeat1_base", "judge_pilot"):
        (master / name).mkdir(parents=True)
    write = execution.common.write
    write(aborted / "all_attempts_cost.json", {"pipeline": .012})
    write(master / "pilot_base/metrics.json", {"known_total_llm_cost_usd": .003})
    write(master / "repeat1_base/metrics.json", {"known_total_llm_cost_usd": .03})
    write(master / "judge_pilot/metrics.json", {"known_cost_usd": .02})
    monkeypatch.setattr(execution, "ABORTED", aborted)
    monkeypatch.setattr(execution, "MASTER", master)
    assert execution.spent() == pytest.approx({"pipeline": .045, "judge": .02, "all": .065})
