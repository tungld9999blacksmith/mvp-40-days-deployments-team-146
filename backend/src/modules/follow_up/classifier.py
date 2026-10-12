"""Follow-up — LLM feedback classifier (AI-007 TOOL-702 ``classify_feedback``).

Implements ``ports.FeedbackClassifier`` on top of the shared ``LLMProvider``.
The owner's comment goes into a delimited block and is treated as data, never
as an instruction (FF EF-906, AI-EDGE-703). Any bad or missing output returns
``None`` so the service falls back to the keyword/rating rules (AF-904).
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation

from src.infrastructure.llm.base import ChatMessage, GenerationConfig, LLMProvider, LLMProviderError
from src.infrastructure.prompts import load_prompt

from .domain import Classification, ClassifiedBy, FeedbackIntent, classify_by_rules

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("follow_up_classifier")

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _user_prompt(rating: int, comment: str) -> str:
    # Keep the owner from closing the data block early.
    safe = comment.replace("<feedback>", "").replace("</feedback>", "")
    return f"Điểm hài lòng: {rating}/5\n<feedback>\n{safe}\n</feedback>"


def parse_classification(text: str, rating: int, comment: str) -> Classification | None:
    """Validate the model's JSON; ``None`` when anything is off."""
    match = _JSON_OBJECT.search(text or "")
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
        intent = FeedbackIntent(str(data["intent"]).upper())
        confidence = Decimal(str(data["confidence"])).quantize(Decimal("0.01"))
    except (ValueError, KeyError, TypeError, InvalidOperation):
        return None
    has_issue = data.get("has_issue")
    safety = data.get("safety_flag", False)
    if not isinstance(has_issue, bool) or not isinstance(safety, bool) or not 0 <= confidence <= 1:
        return None
    # Only SATISFIED may clear the issue flag (AI-007 §7.2, AI-EDGE-701).
    has_issue = has_issue or intent != FeedbackIntent.SATISFIED
    # Safety keywords are a floor the model cannot lower (BR-908).
    safety = safety or classify_by_rules(rating, comment, by=ClassifiedBy.RULES).safety
    return Classification(intent, has_issue or safety, safety, ClassifiedBy.LLM, confidence)


class LLMFeedbackClassifier:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def classify(self, rating: int, comment: str) -> Classification | None:
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=_user_prompt(rating, comment)),
        ]
        try:
            response = await self._llm.chat(messages, GenerationConfig(temperature=0.0, max_tokens=200))
        except LLMProviderError:
            logger.warning("follow_up.llm_classify_error", exc_info=True)
            return None
        result = parse_classification(response.text, rating, comment)
        if result is None:
            logger.warning("follow_up.llm_classify_bad_output", extra={"provider": self._llm.provider_name})
        return result
