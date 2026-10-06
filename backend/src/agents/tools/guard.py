from __future__ import annotations

import asyncio
import functools
import logging
import os
from collections.abc import Callable
from typing import Any

from .result import ToolResult

logger = logging.getLogger(__name__)


def is_mock_enabled() -> bool:
    """Kiểm tra cờ USE_MOCK_SERVICES.

    - Mặc định là False.
    - Trong môi trường production, LUÔN LUÔN là False (từ chối bật mock ở production).
    """
    env_name = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "development").lower()
    if env_name in ("production", "prod"):
        return False
    return os.getenv("USE_MOCK_SERVICES", "false").lower() in ("true", "1", "yes")


def tool_guard(
    *,
    tool_name: str,
    timeout_seconds: float = 5.0,
    default_hint: str = "Hệ thống tra cứu đang bận hoặc gặp sự cố kết nối. Quý khách vui lòng thử lại sau ít phút hoặc liên hệ hotline VinFast 1900 23 23 89.",
) -> Callable:
    """Decorator bảo vệ tool nghiệp vụ của Agent:

    1. Quản lý timeout thực thi.
    2. Bắt mọi ngoại lệ ngoài dự kiến và chuyển thành ToolResult(status='error').
    3. Ghi log có cấu trúc phục vụ audit và tracing.
    4. Không trả raw exception hoặc thông tin kết nối DB/Redis cho LLM.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> ToolResult:
            try:
                res = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
                if isinstance(res, ToolResult):
                    return res
                if isinstance(res, dict):
                    return ToolResult(status="ok", data=res)
                return ToolResult(status="ok", data={"result": res})
            except TimeoutError:
                logger.error("Tool %s bị timeout sau %.1fs", tool_name, timeout_seconds)
                return ToolResult(
                    status="error",
                    code="TIMEOUT",
                    hint=f"Thời gian tra cứu của công cụ {tool_name} vượt quá giới hạn cho phép. Quý khách vui lòng thử lại sau.",
                )
            except Exception as e:
                logger.exception("Ngoại lệ khi thực thi tool %s: %s", tool_name, e)
                return ToolResult(
                    status="error",
                    code="INTERNAL_ERROR",
                    hint=default_hint,
                )

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> ToolResult:
            try:
                res = func(*args, **kwargs)
                if isinstance(res, ToolResult):
                    return res
                if isinstance(res, dict):
                    return ToolResult(status="ok", data=res)
                return ToolResult(status="ok", data={"result": res})
            except Exception as e:
                logger.exception("Ngoại lệ khi thực thi đồng bộ tool %s: %s", tool_name, e)
                return ToolResult(
                    status="error",
                    code="INTERNAL_ERROR",
                    hint=default_hint,
                )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
