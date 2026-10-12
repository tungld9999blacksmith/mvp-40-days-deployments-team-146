"""An additional LLM check; domain authorization and owner confirmation still apply."""

import asyncio
import json
import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictBool

from src.config import get_settings
from src.infrastructure.llm.base import ChatMessage, GenerationConfig
from src.infrastructure.llm.dependency import get_llm_provider_for_stage
from src.infrastructure.prompts import load_prompt

logger = logging.getLogger(__name__)
SENSITIVE_TOOL_NAMES = frozenset({"propose_booking", "update_reminder_settings"})

REVIEW_PROMPT = load_prompt("tool_review")


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed: StrictBool


def parse_review_decision(text: str) -> ReviewDecision:
    """Accept a complete JSON code block while preserving strict decision validation."""
    text = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    return ReviewDecision.model_validate_json(text)


async def review_tool_call(messages: list[Any], call: dict[str, Any]) -> bool:
    # Exclude the pending assistant call: it is the subject being checked, not evidence.
    history = [
        {
            "role": m.type,
            "name": getattr(m, "name", None),
            "content": m.content,
            "tool_calls": getattr(m, "tool_calls", []),
        }
        for m in messages[:-1]
        if m.type != "system"
    ]
    try:
        provider = get_llm_provider_for_stage("booking")
        response = await asyncio.wait_for(
            provider.chat(
                [
                    ChatMessage(role="system", content=REVIEW_PROMPT),
                    ChatMessage(
                        role="user",
                        content=json.dumps(
                            {"history": history, "proposed_tool_call": call}, ensure_ascii=False, default=str
                        ),
                    ),
                ],
                GenerationConfig(temperature=0, max_tokens=128),
            ),
            timeout=get_settings().llm_call_timeout_seconds,
        )
        return parse_review_decision(response.text).allowed
    except Exception as exc:
        # Fail closed without exposing provider errors, credentials or conversation text.
        logger.warning("Tool review unavailable (%s); tool withheld", type(exc).__name__)
        return False
