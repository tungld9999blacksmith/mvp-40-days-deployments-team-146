"""LangChain model with endpoint retries before any stream output."""

from collections.abc import AsyncIterator, Iterator
from contextlib import aclosing, closing
from typing import Any

from langchain_openai import ChatOpenAI
from openai import RateLimitError

from .openrouter_routing import next_endpoint_kwargs


class OpenRouterChatOpenAI(ChatOpenAI):
    def _routing_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        body = {**(self.extra_body or {}), **(kwargs.get("extra_body") or {})}
        routing = {**((self.extra_body or {}).get("provider") or {}), **(body.get("provider") or {})}
        routing.setdefault("allow_fallbacks", True)
        return {**kwargs, "extra_body": {**body, "provider": routing}}

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        kwargs = self._routing_kwargs(kwargs)
        while True:
            try:
                return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except RateLimitError:
                if self.streaming:
                    raise  # The streaming method already owns pre-output retries.
                retry = next_endpoint_kwargs(kwargs)
                if retry is None:
                    raise
                kwargs = retry

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        kwargs = self._routing_kwargs(kwargs)
        while True:
            try:
                return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except RateLimitError:
                if self.streaming:
                    raise
                retry = next_endpoint_kwargs(kwargs)
                if retry is None:
                    raise
                kwargs = retry

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs) -> AsyncIterator[Any]:
        kwargs = self._routing_kwargs(kwargs)
        emitted = False
        while True:
            try:
                async with aclosing(super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs)) as stream:
                    async for chunk in stream:
                        emitted = True
                        yield chunk
                return
            except RateLimitError:
                retry = None if emitted else next_endpoint_kwargs(kwargs)
                if retry is None:
                    raise
                kwargs = retry

    def _stream(self, messages, stop=None, run_manager=None, **kwargs) -> Iterator[Any]:
        kwargs = self._routing_kwargs(kwargs)
        emitted = False
        while True:
            try:
                with closing(super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)) as stream:
                    for chunk in stream:
                        emitted = True
                        yield chunk
                return
            except RateLimitError:
                retry = None if emitted else next_endpoint_kwargs(kwargs)
                if retry is None:
                    raise
                kwargs = retry
