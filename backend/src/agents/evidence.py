"""Carry source metadata through tools, graph and the public response."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage


def rag_artifact(response: Any) -> dict[str, Any]:
    citations = []
    for item in getattr(response, "citations", []) or []:
        value = item.model_dump(mode="json") if hasattr(item, "model_dump") else vars(item)
        if value.get("document_id") and value.get("chunk_id"):
            citations.append(dict(value))
    return {
        "type": "RAG_EVIDENCE",
        "citations": citations,
        "confidence": getattr(response, "confidence", "standard"),
        "fallback_required": bool(getattr(response, "fallback_required", False)),
        "metadata": getattr(response, "metadata", {}) or {},
    }


def collect_rag_evidence(messages: list[Any]) -> dict[str, Any]:
    citations: dict[tuple[str, str], dict] = {}
    latest: dict[str, Any] = {}
    uncertain = False
    for message in messages:
        if isinstance(message, HumanMessage):
            # A previous question's sources must not support this turn's answer.
            citations.clear()
            latest = {}
            uncertain = False
        artifact = getattr(message, "artifact", None)
        if not isinstance(message, ToolMessage) or not isinstance(artifact, dict):
            continue
        if artifact.get("type") != "RAG_EVIDENCE":
            continue
        latest = artifact
        uncertain = uncertain or bool(artifact.get("fallback_required", False))
        for item in artifact.get("citations", []):
            if item.get("document_id") and item.get("chunk_id"):
                citations[(item["document_id"], item["chunk_id"])] = item
    return {
        "citations": list(citations.values()),
        "confidence": "low" if uncertain else latest.get("confidence", "standard"),
        "fallback_required": uncertain,
    }


def preserve_rag_fallback(response: Any, messages: list[Any]) -> Any:
    """Keep a RAG-only answer within the limits returned by its current tools.

    Business tool results require their own answer guards. Never replay a prior
    question's sources or replace a proposal/settings result with RAG text.
    """
    if getattr(response, "tool_calls", None):
        return response
    current = []
    for message in messages:
        if isinstance(message, HumanMessage):
            current.clear()
        elif isinstance(message, ToolMessage):
            current.append(message)
    if not current or any(not isinstance(m.artifact, dict) or m.artifact.get("type") != "RAG_EVIDENCE" for m in current):
        return response
    if not any(m.artifact.get("fallback_required") is True for m in current):
        return response
    contents = list(dict.fromkeys(m.content for m in current if isinstance(m.content, str) and m.content.strip()))
    if not contents:
        return response
    return response.model_copy(update={"content": "\n\n".join(contents), "response_metadata": {
        **response.response_metadata, "rag_fallback_preserved": True,
        "original_rag_answer_before_fallback_guard": response.content,
        "rag_fallback_tool_call_ids": [m.tool_call_id for m in current],
    }})
