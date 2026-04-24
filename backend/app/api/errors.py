"""Standard error envelope + FastAPI exception handlers — Spec §4.6."""

from __future__ import annotations

import secrets
from enum import IntEnum
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.logging_conf import get_logger

log = get_logger(__name__)


class ErrorCode(IntEnum):
    # 400xx parameters
    BAD_REQUEST = 40001
    # 401xx auth
    TOKEN_EXPIRED = 40101
    ACCOUNT_DISABLED = 40102
    # 403xx permission
    PERMISSION_DENIED = 40301
    # 429xx rate limit
    RATE_LIMITED = 42900
    # 500xx system/llm/es (placeholder; Phase 4/5 扩充)
    LLM_TIMEOUT = 50001
    ES_UNAVAILABLE = 50101
    INTERNAL_ERROR = 50000


def _new_trace_id() -> str:
    return f"tr_{secrets.token_hex(6)}"


def _envelope(code: int, message: str, trace_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": int(code), "message": message, "trace_id": trace_id}
    if extra:
        body.update(extra)
    return body


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", None) or _new_trace_id()
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        code = int(detail["code"])
        message = str(detail.get("message", ""))
        extra = {k: v for k, v in detail.items() if k not in {"code", "message"}}
    else:
        code = ErrorCode.BAD_REQUEST if exc.status_code < 500 else ErrorCode.INTERNAL_ERROR
        message = str(detail) if detail else ""
        extra = None
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code, message, trace_id, extra),
        headers=exc.headers,
    )


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", None) or _new_trace_id()
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=_envelope(
            ErrorCode.BAD_REQUEST,
            "请求参数格式非法",
            trace_id,
            extra={"errors": exc.errors()},
        ),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", None) or _new_trace_id()
    log.error("unhandled_exception", trace_id=trace_id, error=repr(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(ErrorCode.INTERNAL_ERROR, "系统内部错误", trace_id),
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_exception_handler)
