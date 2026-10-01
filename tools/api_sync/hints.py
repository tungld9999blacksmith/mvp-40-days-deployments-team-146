"""Build the hints file (``api_hints.json``) used by ``mock --llm``.

A hints file tells the LLM what each long-text field means. Keys are
``Model`` (purpose of the model) and ``Model.field`` (meaning of one field),
e.g. ``"WarrantyOut.termsDescription"`` or ``"MessageResponse.message"``.

Initial values come from, in order: an existing hints file (never overwritten
unless forced), the schema ``description``, an LLM draft (``--llm``), then a
template based on the field name, the model and the endpoints using it.
"""

from __future__ import annotations

import json
import re
from typing import Any

from llm import LLMConfig, complete_json
from mockdata import MockGenerator
from openapi import Model

# (field-name pattern, template). {field}, {model}, {context} are filled in.
_FIELD_TEMPLATES: list[tuple[str, str]] = [
    (r"terms", "Plain-language {model} terms: what is covered, conditions, exclusions and how to claim"),
    (r"message", "Short message shown to the user{context}; one or two sentences explaining the result and the next step"),
    (r"summary", "Short summary of the {model}{context}, a few sentences"),
    (r"description", "Plain-language {field} of the {model}: what it is and the key details a user needs"),
    (r"(note|comment|remark)", "Free-form {field} about the {model}, written by staff or the user"),
    (r"(feedback|review)", "User {field} about the {model}: experience, what went well and what did not"),
    (r"instruction", "Step-by-step {field} the user should follow for the {model}"),
    (r"detail", "Extra {field} about the {model}{context}, e.g. the reason or what was checked"),
    (r"(content|body)", "Main text {field} of the {model}"),
    (r"bio", "Short self-introduction ({field}) for the {model}"),
]


def humanize(name: str) -> str:
    """``termsDescription`` / ``WarrantyOut`` -> ``terms description`` / ``warranty``."""
    name = re.sub(r"(Out|In|Request|Response|Envelope|Data)$", "", name) or name
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name).replace("_", " ")
    return words.lower().strip()


def _endpoint_context(model: Model, summaries: dict[str, str]) -> str:
    texts = sorted({summaries.get(key) or key for key, _ in model.used_by})
    if not texts:
        return ""
    return f" after '{texts[0]}'" if len(texts) == 1 else f" after an action (e.g. '{texts[0]}')"


def template_field_hint(model: Model, field: str, summaries: dict[str, str]) -> str:
    values = {"field": humanize(field), "model": humanize(model.ts_name), "context": _endpoint_context(model, summaries)}
    for pattern, template in _FIELD_TEMPLATES:
        if re.search(pattern, field, re.IGNORECASE):
            return template.format(**values)
    return "Free text for the {field} of the {model}{context}".format(**values)


def template_model_hint(model: Model, summaries: dict[str, str]) -> str:
    if model.description:
        return model.description.splitlines()[0]
    uses = sorted({f"{key} ({summaries[key]})" if summaries.get(key) else key for key, _ in model.used_by})
    role = {"input": "Request body", "output": "Response data", "both": "Data"}.get(model.kind, "Data")
    about = f"{role}: {humanize(model.ts_name)}"
    return f"{about}, used by {', '.join(uses[:3])}" if uses else about


def collect_fields(gen: MockGenerator, models: dict[str, Model], selected: list[Model]) -> list[tuple[Model, str, dict]]:
    """Long-text fields (same rule as ``mock``) of the selected models, in order."""
    found = []
    for model in sorted(selected, key=lambda m: m.ts_name):
        for key, prop in model.schema.get("properties", {}).items():
            if gen._is_long_text(prop, key, model.name):
                found.append((model, key, prop))
    return found


def build_hints(
    gen: MockGenerator,
    models: dict[str, Model],
    selected: list[Model],
    summaries: dict[str, str],
    existing: dict[str, str],
    *,
    force: bool = False,
    llm: LLMConfig | None = None,
    language: str = "en",
) -> tuple[dict[str, str], list[str]]:
    """Return (hints, keys added or replaced). Existing values win unless ``force``."""
    fields = collect_fields(gen, models, selected)
    owners = sorted({m.name: m for m, _, _ in fields}.values(), key=lambda m: m.ts_name)

    drafts: dict[str, str] = {}
    for model in owners:
        drafts[model.ts_name] = template_model_hint(model, summaries)
        for m, key, prop in fields:
            if m is model:
                desc = (prop.get("description") or "").strip()
                drafts[f"{model.ts_name}.{key}"] = desc or template_field_hint(model, key, summaries)

    missing = [k for k in drafts if force or k not in existing]
    if llm and missing:
        drafts.update(_llm_drafts(llm, missing, drafts, owners, fields, summaries, language))

    hints = dict(existing)
    changed = []
    for key, value in drafts.items():
        if key in missing:
            hints[key] = value
            changed.append(key)
    return hints, changed


def _llm_drafts(
    config: LLMConfig,
    keys: list[str],
    drafts: dict[str, str],
    owners: list[Model],
    fields: list[tuple[Model, str, dict]],
    summaries: dict[str, str],
    language: str,
) -> dict[str, str]:
    context: list[dict[str, Any]] = []
    for model in owners:
        context.append(
            {
                "model": model.ts_name,
                "usedBy": sorted({f"{k} ({r}) {summaries.get(k, '')}".strip() for k, r in model.used_by}),
                "fields": {
                    name: _short_type(prop) for name, prop in model.schema.get("properties", {}).items()
                },
            }
        )
    prompt = _PROMPT.format(
        language=language,
        models=json.dumps(context, ensure_ascii=False, indent=2),
        keys=json.dumps({k: drafts[k] for k in keys}, ensure_ascii=False, indent=2),
    )
    result = complete_json(config, _SYSTEM, prompt)
    return {k: v.strip() for k, v in result.items() if k in keys and isinstance(v, str) and v.strip()}


def _short_type(prop: dict[str, Any]) -> str:
    options = prop.get("anyOf") or [prop]
    types = [o.get("type") or o.get("$ref", "").rsplit("/", 1)[-1] or "object" for o in options]
    return " | ".join(t for t in types if t)


_SYSTEM = "You document API data models for a test-data generator. Reply with one JSON object only."

_PROMPT = """Write a hint for every key below. A hint tells another LLM what to write in sample data.
Language of the hints: {language}.

- "Model" keys: one sentence on what the model represents and when the API returns/accepts it.
- "Model.field" keys: what the text field should contain, its tone and typical length, like
  "Plain-language warranty terms: what is covered, exclusions, how to claim".
- Use the model's endpoints and its other fields to be specific to this domain (EV owners,
  workshops, warranties, vehicle verification). Improve the draft value; do not repeat it verbatim.

Return a JSON object with exactly these keys: {{"Key": "hint", ...}}

Models:
{models}

Keys with their current draft:
{keys}
"""
