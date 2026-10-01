"""Minimal LLM client (plain HTTP, no SDK) returning a JSON object.

Provider, API key, model and base URL come from the tool's own settings
(``tools/api_sync/.env``, see ``settings.py``); CLI flags may override the
provider and model.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from settings import Settings

# provider: (default model, default base url)
PROVIDERS: dict[str, tuple[str, str]] = {
    "openai": ("gpt-4o-mini", "https://api.openai.com/v1"),
    "anthropic": ("claude-haiku-4-5-20251001", "https://api.anthropic.com/v1"),
    "gemini": ("gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta/openai"),
    "grok": ("grok-4", "https://api.x.ai/v1"),
    "deepseek": ("deepseek-chat", "https://api.deepseek.com"),
}


class LLMError(RuntimeError):
    pass


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: str
    base_url: str

    @classmethod
    def resolve(cls, settings: Settings, provider: str | None = None, model: str | None = None) -> LLMConfig:
        provider = (provider or settings.llm_provider or "openai").lower()
        if provider not in PROVIDERS:
            raise LLMError(f"Unknown LLM provider '{provider}'. Choose one of: {', '.join(PROVIDERS)}")
        if not settings.llm_api_key:
            raise LLMError(f"LLM_API_KEY is not set in {settings.env_file} (or the environment).")
        default_model, default_base = PROVIDERS[provider]
        # A model/base URL configured for another provider would not work; only
        # reuse them when the provider was not overridden on the command line.
        same_provider = provider == settings.llm_provider
        return cls(
            provider=provider,
            model=model or (settings.llm_model if same_provider else "") or default_model,
            api_key=settings.llm_api_key,
            base_url=((settings.llm_base_url if same_provider else "") or default_base).rstrip("/"),
        )


def _post(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise LLMError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"Cannot reach {url}: {exc.reason}") from exc


def _parse_json_object(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("LLM reply contains no JSON object.")
    return json.loads(text[start : end + 1])


def complete_json(config: LLMConfig, system: str, prompt: str, timeout: float = 180) -> dict[str, Any]:
    if config.provider == "anthropic":
        data = _post(
            f"{config.base_url}/messages",
            {"x-api-key": config.api_key, "anthropic-version": "2023-06-01"},
            {
                "model": config.model,
                "max_tokens": 8192,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout,
        )
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    else:  # every other provider speaks the OpenAI chat-completions protocol
        data = _post(
            f"{config.base_url}/chat/completions",
            {"authorization": f"Bearer {config.api_key}"},
            {
                "model": config.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
            timeout,
        )
        text = data["choices"][0]["message"]["content"] or ""
    return _parse_json_object(text)
