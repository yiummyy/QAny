"""Trace ID middleware — injects trace_id into every request/response cycle.

Pure ASGI middleware (not BaseHTTPMiddleware) to avoid issues with
StreamingResponse used by SSE endpoints.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def _new_trace_id() -> str:
    return f"tr_{secrets.token_hex(6)}"


class TraceIDMiddleware:
    """ASGI middleware that generates a trace_id per request.

    - Sets ``request.state.trace_id``
    - Binds trace_id to structlog context
    - Adds ``X-Trace-Id`` response header
    - Cleans up structlog context after response
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = _new_trace_id()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        async def _send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"x-trace-id"] = trace_id.encode()
                message["headers"] = list(headers.items())
            await send(message)

        try:
            await self.app(scope, receive, _send_with_header)
        finally:
            structlog.contextvars.clear_contextvars()
