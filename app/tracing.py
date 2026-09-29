from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

try:
    from langfuse import get_client, observe, propagate_attributes

    LANGFUSE_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - chỉ dùng khi chưa cài requirements
    LANGFUSE_SDK_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        return decorator

    class _DummyClient:
        def update_current_span(self, **kwargs: Any) -> None:
            return None

        def update_current_generation(self, **kwargs: Any) -> None:
            return None

    def get_client():
        return _DummyClient()

    @contextmanager
    def propagate_attributes(**kwargs: Any):
        yield


def get_langfuse_client():
    return get_client()


def tracing_enabled() -> bool:
    return LANGFUSE_SDK_AVAILABLE and bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )


class NoopObservation:
    """Đứng thay observation khi SDK thiếu hoặc client không hỗ trợ child observation."""

    def update(self, **_: Any) -> None:
        return None


@contextmanager
def child_observation(client: Any, **kwargs: Any):
    """Mở child observation bằng API v4, hoặc yield no-op nếu không khả dụng.

    Nhờ vậy agent luôn chạy được khi tracing tắt (không có key), khi chưa cài
    Langfuse SDK, hoặc khi test dùng client giả tối giản.
    """
    starter = getattr(client, "start_as_current_observation", None)
    if not callable(starter):
        yield NoopObservation()
        return

    with starter(**kwargs) as observation:
        yield observation
