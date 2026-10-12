"""Conversion between a locked prompt text and a LangSmith Prompt Hub commit.

A prompt is pushed as a ``ChatPromptTemplate`` holding one ``SystemMessage``. The
message is a ``BaseMessage`` instance, not a template string, so braces in the text
are kept as they are. ``text_from_manifest`` reads the same shape back.
"""

from __future__ import annotations

from typing import Any

from langchain_core.load import dumpd
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate


def hub_repo_name(name: str, prefix: str) -> str:
    """Hub repositories accept lowercase words joined by hyphens."""
    return prefix + name.replace("_", "-")


def build_template(text: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([SystemMessage(content=text)])


def manifest_of(text: str) -> dict[str, Any]:
    """Manifest as the Hub stores it (what ``push_prompt`` sends)."""
    return dumpd(build_template(text))


def text_from_manifest(manifest: dict[str, Any]) -> str:
    messages = manifest.get("kwargs", {}).get("messages", [])
    if len(messages) != 1 or messages[0].get("kwargs", {}).get("type", "system") != "system":
        raise ValueError("Prompt Hub commit must hold exactly one system message")
    content = messages[0]["kwargs"].get("content")
    if not isinstance(content, str):
        raise ValueError("Prompt Hub commit has no text content")
    return content
