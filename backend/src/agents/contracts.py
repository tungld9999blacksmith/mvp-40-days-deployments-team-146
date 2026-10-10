"""Validate the public tool schema before a tool can produce any side effect."""
from __future__ import annotations

import json
import re
from datetime import date, time
from typing import Any
from uuid import UUID

from pydantic import ValidationError


def validate_arguments(tool: Any, arguments: Any) -> list[str]:
    if not isinstance(arguments, dict):
        return ["Arguments must be a JSON object"]
    errors = []
    unknown = set(arguments) - set(tool.args)
    if unknown:
        errors.append("Arguments outside public schema: " + ", ".join(sorted(unknown)))
    try:
        tool.tool_call_schema.model_validate_json(json.dumps(arguments), strict=True)
    except (ValidationError, ValueError, TypeError) as exc:
        if isinstance(exc, ValidationError):
            errors.extend(f"{'.'.join(map(str, e['loc']))}: {e['type']}" for e in exc.errors())
        else:
            errors.append("Arguments cannot be serialized as JSON")
    for name, value in arguments.items():
        try:
            if name in {"workshop_id", "reminder_id"}:
                if value is not None:
                    UUID(str(value))
            elif name in {"target_date", "booking_date"}:
                if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            elif name == "time_slot":
                if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
                    raise ValueError()
                time.fromisoformat(value)
        except (ValueError, TypeError):
            errors.append(f"{name}: invalid business format")
    return errors
