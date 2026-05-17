"""Admin endpoints — settings CRUD + logs + metrics — Spec §4.2."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserClaims, require_admin, require_any_user
from app.config import get_settings
from app.models.feedback import Feedback
from app.models.qa_log import QALog
from app.models.settings import QASettings
from app.storage.pg import get_db

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# API key keys in the config JSONB that should be masked on read
_API_KEY_KEYS = {"dashscope_api_key", "deepseek_api_key", "llm_api_key"}


def _mask_config_for_read(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of config with API key values masked for display."""
    masked = dict(config)
    for key in _API_KEY_KEYS:
        val = masked.get(key)
        if isinstance(val, str) and val:
            masked[key] = _mask_value(val)
    return masked


def _mask_value(value: str) -> str:
    """Mask a secret value, showing only last 4 characters."""
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


def _resolve_incoming_keys(incoming: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """If the incoming value for an API key is masked, preserve the existing stored key."""
    resolved = dict(incoming)
    for key in _API_KEY_KEYS:
        new_val = resolved.get(key)
        if isinstance(new_val, str) and "****" in new_val:
            # User didn't change the key — keep the stored value
            resolved[key] = existing.get(key, "")
    return resolved


# ---------------------------------------------------------------------------
# Existing Phase 2 endpoints
# ---------------------------------------------------------------------------


@router.get("/ping")
async def admin_ping(claims: UserClaims = Depends(require_admin)) -> dict[str, object]:
    return {"pong": True, "caller": claims.username}


@router.get("/whoami")
async def whoami(claims: UserClaims = Depends(require_any_user)) -> dict[str, object]:
    return {"role": claims.role.value, "pl": claims.pl}


# ---------------------------------------------------------------------------
# Settings CRUD (optimistic locking)
# ---------------------------------------------------------------------------


class SettingsOut(BaseModel):
    config: dict[str, Any]
    updated_by: str | None = None
    updated_at: str


class UpdateSettingsRequest(BaseModel):
    config: dict[str, Any]
    updated_at: str = Field(..., description="ISO-format timestamp for optimistic locking")


@router.get("/settings", response_model=SettingsOut)
async def get_admin_settings(
    claims: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> SettingsOut:
    row = await session.get(QASettings, 1)
    if row is None:
        raise HTTPException(status_code=500, detail={"code": 50000, "message": "qa_settings 未初始化"})
    return SettingsOut(
        config=_mask_config_for_read(row.config),
        updated_by=row.updated_by,
        updated_at=row.updated_at.isoformat(),
    )


@router.put("/settings", response_model=SettingsOut)
async def update_admin_settings(
    body: UpdateSettingsRequest,
    claims: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> SettingsOut:
    row = await session.get(QASettings, 1)
    if row is None:
        raise HTTPException(status_code=500, detail={"code": 50000, "message": "qa_settings 未初始化"})

    # Optimistic lock: compare updated_at
    expected = body.updated_at
    actual = row.updated_at.isoformat()
    if expected != actual:
        raise HTTPException(
            status_code=409,
            detail={
                "code": 40001,
                "message": "配置已被其他管理员修改，请刷新后重试",
                "current_updated_at": actual,
            },
        )

    row.config = _resolve_incoming_keys(body.config, row.config)
    row.updated_by = claims.sub
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()

    return SettingsOut(
        config=_mask_config_for_read(row.config),
        updated_by=row.updated_by,
        updated_at=row.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# QA Logs — paginated + filters
# ---------------------------------------------------------------------------


class LogItem(BaseModel):
    log_id: str
    session_id: str
    user_id: str
    scene: str
    question: str
    answer: str | None = None
    confidence: str | None = None
    confidence_score: float | None = None
    status: str
    error_code: int | None = None
    trace_id: str | None = None
    response_time_ms: int | None = None
    created_at: str


class LogListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[LogItem]


@router.get("/logs", response_model=LogListResponse)
async def list_logs(
    offset: int = 0,
    limit: int = 20,
    user_id: str | None = None,
    status_filter: str | None = None,
    scene: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    claims: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> LogListResponse:
    base = select(QALog)
    if user_id:
        base = base.where(QALog.user_id == user_id)
    if status_filter:
        base = base.where(QALog.status == status_filter)
    if scene:
        base = base.where(QALog.scene == scene)
    if date_from:
        base = base.where(QALog.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        base = base.where(QALog.created_at <= datetime.fromisoformat(date_to))

    # Count total
    count_q = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_q)).scalar_one()

    # Fetch page
    rows = (
        await session.execute(
            base.order_by(QALog.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()

    items = [
        LogItem(
            log_id=r.log_id,
            session_id=r.session_id,
            user_id=r.user_id,
            scene=r.scene,
            question=r.question,
            answer=r.answer,
            confidence=r.confidence,
            confidence_score=float(r.confidence_score) if r.confidence_score is not None else None,
            status=r.status,
            error_code=r.error_code,
            trace_id=r.trace_id,
            response_time_ms=r.response_time_ms,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]

    return LogListResponse(total=total, offset=offset, limit=limit, items=items)


# ---------------------------------------------------------------------------
# Aggregated metrics
# ---------------------------------------------------------------------------


class MetricsOut(BaseModel):
    today_questions: int = 0
    success_rate: float = 0.0
    avg_response_ms: float = 0.0
    today_cost_rmb: float = 0.0
    today_tokens: int = 0
    feedback_thumbs_up: int = 0
    feedback_thumbs_down: int = 0


@router.get("/metrics", response_model=MetricsOut)
async def get_metrics(
    claims: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> MetricsOut:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Today's questions
    total_today = (
        await session.scalar(
            select(func.count()).where(QALog.created_at >= today_start)
        )
    ) or 0

    # Success rate (non-error, non-fallback)
    success_today = (
        await session.scalar(
            select(func.count()).where(
                QALog.created_at >= today_start,
                QALog.status == "success",
            )
        )
    ) or 0

    # Average response time
    avg_ms = (
        await session.scalar(
            select(func.avg(QALog.response_time_ms)).where(
                QALog.created_at >= today_start,
                QALog.response_time_ms.isnot(None),
            )
        )
    ) or 0.0

    # Today's cost
    cost_today = (
        await session.scalar(
            select(func.sum(QALog.cost_rmb)).where(
                QALog.created_at >= today_start,
                QALog.cost_rmb.isnot(None),
            )
        )
    ) or Decimal("0")

    # Tokens
    tokens_today = (
        await session.scalar(
            select(func.sum(QALog.input_tokens + QALog.output_tokens)).where(
                QALog.created_at >= today_start,
            )
        )
    ) or 0

    # Feedback counts
    thumbs_up = (
        await session.scalar(
            select(func.count()).where(
                Feedback.created_at >= today_start,
                Feedback.feedback_type == "thumbs_up",
            )
        )
    ) or 0
    thumbs_down = (
        await session.scalar(
            select(func.count()).where(
                Feedback.created_at >= today_start,
                Feedback.feedback_type == "thumbs_down",
            )
        )
    ) or 0

    return MetricsOut(
        today_questions=total_today,
        success_rate=round(success_today / total_today, 4) if total_today > 0 else 0.0,
        avg_response_ms=round(float(avg_ms), 1),
        today_cost_rmb=round(float(cost_today), 4),
        today_tokens=int(tokens_today) if tokens_today else 0,
        feedback_thumbs_up=thumbs_up,
        feedback_thumbs_down=thumbs_down,
    )
