"""Try alternative endpoints of the configured model with bounded synthetic text."""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from src.agents.checkpoint import selector_loop_factory
from src.config import get_settings
from src.infrastructure.llm.routing import settings_for_stage


async def probe():
    settings = settings_for_stage(get_settings(), "orchestrator")
    if settings.llm_provider != "openrouter":
        raise ValueError("This probe requires the configured OpenRouter provider")
    model = settings.openrouter_model
    base = settings.openrouter_base_url.rstrip("/")
    results = []
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(f"{base}/models/{model}/endpoints")
        response.raise_for_status()
        endpoints = response.json()["data"]["endpoints"]
        # Prefer regional endpoints over the already failing default pool.
        candidates = sorted(
            (endpoint for endpoint in endpoints if "/" in endpoint.get("tag", "")),
            key=lambda endpoint: {"mistral/us": 0, "mistral/eu": 1, "mistral/zdr": 2}.get(endpoint["tag"], 3),
        )
        for endpoint in candidates[:3]:
            prices = endpoint["pricing"]
            # $/token; retain the cost envelope already estimated for this run.
            if float(prices["prompt"]) > 0.000000165 or float(prices["completion"]) > 0.00000066:
                continue
            tag = endpoint["tag"]
            response = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": "Bearer " + settings.openrouter_api_key},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply only OK"}],
                    "max_tokens": 64,
                    "provider": {"only": [tag], "allow_fallbacks": False},
                },
            )
            payload = response.json()
            error = payload.get("error") or {}
            metadata = error.get("metadata") or {}
            usage = payload.get("usage") or {}
            content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
            result = {
                "endpoint": tag,
                "http_status": response.status_code,
                "has_reply": bool(content),
                "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason"),
                "provider": payload.get("provider") or metadata.get("provider_name"),
                "limit_source": metadata.get("limit_source"),
                "input_usd_per_million": float(prices["prompt"]) * 1_000_000,
                "output_usd_per_million": float(prices["completion"]) * 1_000_000,
                "usage": {key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "cost")},
            }
            results.append(result)
            print(json.dumps(result), flush=True)
            if response.is_success and content:
                break
    return {
        "run_at_utc": datetime.now(UTC).isoformat(),
        "model": model,
        "probes": results,
        "working_endpoint": next(
            (row["endpoint"] for row in results if row["http_status"] == 200 and row["has_reply"]), None
        ),
    }


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=selector_loop_factory) as runner:
        result = runner.run(probe())
    output = Path(__file__).resolve().parents[2] / "docs/plans/AGENT_MEMORY_ENDPOINT_PROBES_20261010.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
