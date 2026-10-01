"""Render OpenAPI (3.0 / 3.1) schemas as TypeScript interfaces and types."""

from __future__ import annotations

import json
import re
from typing import Any

from openapi import Model, ref_name

_IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_PRIMITIVES = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "null": "null"}


def _key(name: str) -> str:
    return name if _IDENT_RE.match(name) else json.dumps(name)


def _union(parts: list[str]) -> str:
    seen: list[str] = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    # Keep `null` last: `string | null` reads better than `null | string`.
    seen.sort(key=lambda p: p == "null")
    return " | ".join(seen) if seen else "unknown"


def _wrap(t: str) -> str:
    return f"({t})" if (" | " in t or " & " in t) else t


def render_type(schema: Any, ts_names: dict[str, str], indent: int = 0) -> str:
    """TypeScript type expression for ``schema``."""
    if not isinstance(schema, dict) or not schema:
        return "unknown"
    if "$ref" in schema:
        return ts_names.get(ref_name(schema["$ref"]), "unknown")
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    if "enum" in schema:
        return _union([json.dumps(v, ensure_ascii=False) for v in schema["enum"]])
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return _union([render_type(s, ts_names, indent) for s in schema[key]])
    if "allOf" in schema:
        parts = [render_type(s, ts_names, indent) for s in schema["allOf"]]
        return parts[0] if len(parts) == 1 else " & ".join(_wrap(p) for p in parts)

    typ = schema.get("type")
    if isinstance(typ, list):  # OpenAPI 3.1: ["string", "null"]
        return _union([render_type({**schema, "type": t}, ts_names, indent) for t in typ])
    if schema.get("nullable") is True:  # OpenAPI 3.0
        inner = {k: v for k, v in schema.items() if k != "nullable"}
        return _union([render_type(inner, ts_names, indent), "null"])

    if typ == "array":
        if "prefixItems" in schema:
            return "[" + ", ".join(render_type(s, ts_names, indent) for s in schema["prefixItems"]) + "]"
        return f"{_wrap(render_type(schema.get('items', {}), ts_names, indent))}[]"
    if typ == "object" or "properties" in schema:
        return _render_object(schema, ts_names, indent)
    return _PRIMITIVES.get(typ, "unknown")


def _render_object(schema: dict[str, Any], ts_names: dict[str, str], indent: int) -> str:
    props: dict[str, Any] = schema.get("properties", {})
    extra = schema.get("additionalProperties")
    if not props:
        if isinstance(extra, dict) and extra:
            return f"Record<string, {render_type(extra, ts_names, indent)}>"
        return "Record<string, unknown>"
    lines = ["{"]
    lines += _property_lines(schema, ts_names, indent + 1)
    lines.append(f"{'  ' * indent}}}")
    return "\n".join(lines)


def _jsdoc(schema: dict[str, Any], pad: str, extra_lines: list[str] | None = None) -> list[str]:
    notes = []
    text = (schema.get("description") or "").strip()
    if text:
        notes += text.splitlines()
    if fmt := schema.get("format"):
        notes.append(f"@format {fmt}")
    if "default" in schema and schema["default"] is not None:
        notes.append(f"@default {json.dumps(schema['default'], ensure_ascii=False)}")
    notes += extra_lines or []
    if not notes:
        return []
    if len(notes) == 1:
        return [f"{pad}/** {notes[0]} */"]
    return [f"{pad}/**"] + [f"{pad} * {n}".rstrip() for n in notes] + [f"{pad} */"]


def _property_lines(schema: dict[str, Any], ts_names: dict[str, str], indent: int) -> list[str]:
    pad = "  " * indent
    required = set(schema.get("required", []))
    lines: list[str] = []
    for name, prop in schema.get("properties", {}).items():
        lines += _jsdoc(prop if isinstance(prop, dict) else {}, pad)
        optional = "" if name in required else "?"
        lines.append(f"{pad}{_key(name)}{optional}: {render_type(prop, ts_names, indent)};")
    return lines


def property_signatures(schema: dict[str, Any], ts_names: dict[str, str]) -> dict[str, tuple[str, bool]]:
    """``{property: (ts type, required)}`` — used for diffs and listings."""
    required = set(schema.get("required", []))
    return {
        name: (" ".join(render_type(prop, ts_names).split()), name in required)
        for name, prop in schema.get("properties", {}).items()
    }


def render_model(model: Model, ts_names: dict[str, str], style: str = "interface") -> str:
    schema = model.schema
    used_by = sorted({f"{key} ({role})" for key, role in model.used_by})
    doc_schema = {"description": model.description}
    lines = _jsdoc(doc_schema, "", [f"Used by: {u}" for u in used_by])

    is_plain_object = schema.get("type") == "object" and "properties" in schema and not any(
        k in schema for k in ("anyOf", "oneOf", "allOf")
    )
    if style == "interface" and is_plain_object:
        lines.append(f"export interface {model.ts_name} {{")
        lines += _property_lines(schema, ts_names, 1)
        lines.append("}")
    else:
        lines.append(f"export type {model.ts_name} = {render_type(schema, ts_names)};")
    return "\n".join(lines)


def render_file(models: list[Model], ts_names: dict[str, str], header: list[str], style: str) -> str:
    out = ["/* eslint-disable */", *[f"// {h}" for h in header], ""]
    for model in sorted(models, key=lambda m: m.ts_name):
        out.append(render_model(model, ts_names, style))
        out.append("")
    return "\n".join(out)
