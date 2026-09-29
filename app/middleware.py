from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

CORRELATION_HEADER = "x-request-id"
RESPONSE_TIME_HEADER = "x-response-time-ms"
SAFE_CORRELATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def new_correlation_id() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"


def resolve_correlation_id(request: Request) -> str:
    incoming = request.headers.get(CORRELATION_HEADER, "").strip()
    if incoming and SAFE_CORRELATION_RE.match(incoming):
        return incoming
    return new_correlation_id()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        clear_contextvars()
        correlation_id = resolve_correlation_id(request)
        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id
        request.state.request_started_at = time.perf_counter()

        try:
            response = await call_next(request)
        finally:
            clear_contextvars()

        elapsed_ms = (time.perf_counter() - request.state.request_started_at) * 1000
        response.headers[CORRELATION_HEADER] = correlation_id
        response.headers[RESPONSE_TIME_HEADER] = f"{elapsed_ms:.2f}"
        return response
