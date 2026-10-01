"""Helpers shared by the cache / lock decorators to turn call arguments into keys."""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable
from typing import Any

from .errors import CacheError


def require_async(func: Callable[..., Any]) -> None:
    if not inspect.iscoroutinefunction(func):
        raise TypeError(
            f"{func.__qualname__} must be an async function to use the Redis toolkit decorators "
            "(wrap sync DB calls with starlette's run_in_threadpool)"
        )


def bind_arguments(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Map a call's positional + keyword args onto parameter names, defaults applied."""
    bound = inspect.signature(func).bind(*args, **kwargs)
    bound.apply_defaults()
    return dict(bound.arguments)


def render_template(template: str, arguments: dict[str, Any]) -> str:
    """
    `str.format` over the bound arguments, so attribute / index access works:
    "vehicle:{vehicle.id}", "user:{user_id}:page:{filters[page]}".
    """
    try:
        return template.format(**arguments)
    except (KeyError, AttributeError, IndexError) as exc:
        raise CacheError(f"Cannot render key template {template!r} with args {list(arguments)}: {exc}") from exc


def default_call_key(func: Callable[..., Any], arguments: dict[str, Any]) -> str:
    """
    Stable key for a call when no template is given: "<module>.<qualname>:<sha1 of args>".
    `self` / `cls` / sessions are skipped so methods and injected DB sessions don't break the key.
    """
    skip = {"self", "cls", "session", "db"}
    payload = {k: v for k, v in arguments.items() if k not in skip}
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, default=repr).encode()).hexdigest()[:16]
    return f"{func.__module__}.{func.__qualname__}:{digest}"


def build_key(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    key: str | Callable[..., str] | None,
) -> str:
    """Resolve a decorator's `key=` option: template string, callable(*args, **kwargs), or auto."""
    if callable(key):
        return str(key(*args, **kwargs))
    arguments = bind_arguments(func, args, kwargs)
    if key is None:
        return default_call_key(func, arguments)
    return render_template(key, arguments)
