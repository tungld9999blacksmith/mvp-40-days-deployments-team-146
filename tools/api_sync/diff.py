"""Compare two OpenAPI documents: which models and endpoints changed.

Changes are structural only (types, required flags, enum values, fields,
parameters); description-only edits are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from openapi import Endpoint, Model, closure, index_spec
from typescript import property_signatures, render_type


@dataclass
class DiffReport:
    models_added: list[str] = field(default_factory=list)
    models_removed: list[str] = field(default_factory=list)
    models_changed: dict[str, list[str]] = field(default_factory=dict)
    endpoints_added: list[str] = field(default_factory=list)
    endpoints_removed: list[str] = field(default_factory=list)
    endpoints_changed: dict[str, list[str]] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return any(
            (
                self.models_added,
                self.models_removed,
                self.models_changed,
                self.endpoints_added,
                self.endpoints_removed,
                self.endpoints_changed,
            )
        )

    def summary(self) -> dict[str, int]:
        return {
            "modelsAdded": len(self.models_added),
            "modelsRemoved": len(self.models_removed),
            "modelsChanged": len(self.models_changed),
            "endpointsAdded": len(self.endpoints_added),
            "endpointsRemoved": len(self.endpoints_removed),
            "endpointsChanged": len(self.endpoints_changed),
        }


def _ts_names(models: dict[str, Model]) -> dict[str, str]:
    return {n: m.ts_name for n, m in models.items()}


def _model_changes(old: Model, new: Model, old_names: dict[str, str], new_names: dict[str, str]) -> list[str]:
    old_props = property_signatures(old.schema, old_names)
    new_props = property_signatures(new.schema, new_names)
    if not old_props and not new_props:
        before = " ".join(render_type(old.schema, old_names).split())
        after = " ".join(render_type(new.schema, new_names).split())
        return [f"type: {before}  ->  {after}"] if before != after else []

    changes: list[str] = []
    for name in new_props.keys() - old_props.keys():
        ts, req = new_props[name]
        changes.append(f"+ {name}{'' if req else '?'}: {ts}")
    for name in old_props.keys() - new_props.keys():
        ts, req = old_props[name]
        changes.append(f"- {name}{'' if req else '?'}: {ts}")
    for name in old_props.keys() & new_props.keys():
        (old_ts, old_req), (new_ts, new_req) = old_props[name], new_props[name]
        if old_ts != new_ts:
            changes.append(f"~ {name}: {old_ts}  ->  {new_ts}")
        if old_req != new_req:
            changes.append(f"~ {name}: {'required' if new_req else 'optional'} (was {'required' if old_req else 'optional'})")
    return sorted(changes, key=lambda c: c[2:])


def _param_signatures(ep: Endpoint, names: dict[str, str]) -> set[str]:
    return {
        f"{p.get('in')}:{p.get('name')}{'' if p.get('required') else '?'}: "
        + " ".join(render_type(p.get("schema", {}), names).split())
        for p in ep.parameters
        if "name" in p
    }


def compare_specs(old_spec: dict[str, Any], new_spec: dict[str, Any]) -> DiffReport:
    old_models, old_eps = index_spec(old_spec)
    new_models, new_eps = index_spec(new_spec)
    old_names, new_names = _ts_names(old_models), _ts_names(new_models)
    report = DiffReport()

    report.models_added = sorted(new_models.keys() - old_models.keys())
    report.models_removed = sorted(old_models.keys() - new_models.keys())
    for name in sorted(old_models.keys() & new_models.keys()):
        changes = _model_changes(old_models[name], new_models[name], old_names, new_names)
        if changes:
            report.models_changed[name] = changes

    old_by_key = {e.key: e for e in old_eps}
    new_by_key = {e.key: e for e in new_eps}
    report.endpoints_added = sorted(new_by_key.keys() - old_by_key.keys())
    report.endpoints_removed = sorted(old_by_key.keys() - new_by_key.keys())

    touched = set(report.models_changed) | set(report.models_added) | set(report.models_removed)
    new_schemas = {n: m.schema for n, m in new_models.items()}
    for key in sorted(old_by_key.keys() & new_by_key.keys()):
        old_ep, new_ep = old_by_key[key], new_by_key[key]
        reasons: list[str] = []
        for side, before, after in (
            ("input", old_ep.inputs, new_ep.inputs),
            ("output", old_ep.outputs, new_ep.outputs),
        ):
            if before != after:
                reasons.append(f"{side} model: {', '.join(sorted(before)) or '-'} -> {', '.join(sorted(after)) or '-'}")
            else:
                hit = sorted(closure(after, new_schemas) & touched)
                if hit:
                    reasons.append(f"{side} schema changed via {', '.join(hit)}")
        old_params, new_params = _param_signatures(old_ep, old_names), _param_signatures(new_ep, new_names)
        for p in sorted(new_params - old_params):
            reasons.append(f"+ param {p}")
        for p in sorted(old_params - new_params):
            reasons.append(f"- param {p}")
        if reasons:
            report.endpoints_changed[key] = reasons
    return report


def format_report(report: DiffReport, synced: set[str] | None = None) -> list[str]:
    """Human-readable lines. Models in ``synced`` are marked with ``*``."""
    synced = synced or set()
    mark = lambda n: f"{n} *" if n in synced else n  # noqa: E731
    lines: list[str] = []
    if not report.has_changes:
        return ["No schema changes."]
    if report.models_added or report.models_removed or report.models_changed:
        lines.append("Models:")
        lines += [f"  [added]   {n}" for n in report.models_added]
        lines += [f"  [removed] {mark(n)}" for n in report.models_removed]
        for name, changes in report.models_changed.items():
            lines.append(f"  [changed] {mark(name)}")
            lines += [f"      {c}" for c in changes]
    if report.endpoints_added or report.endpoints_removed or report.endpoints_changed:
        lines.append("Endpoints:")
        lines += [f"  [added]   {k}" for k in report.endpoints_added]
        lines += [f"  [removed] {k}" for k in report.endpoints_removed]
        for key, reasons in report.endpoints_changed.items():
            lines.append(f"  [changed] {key}")
            lines += [f"      {r}" for r in reasons]
    if synced:
        lines.append("(* = model included in the last synced TypeScript file)")
    return lines
