"""/api/v1/feedback — thumbs up/down with optional comment — Spec §4.2."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserClaims, require_any_user
from app.models.feedback import Feedback
from app.models.qa_log import QALog
from app.storage.pg import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    log_id: str = Field(..., min_length=1, max_length=64)
    feedback_type: str = Field(..., pattern="^(thumbs_up|thumbs_down)$")
    reason: str | None = Field(None, max_length=32)
    comment: str | None = Field(None, max_length=500)


class FeedbackResponse(BaseModel):
    feedback_id: str
    log_id: str
    feedback_type: str
    message: str


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    claims: UserClaims = Depends(require_any_user),
    session: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    # Validate log_id exists
    log = await session.get(QALog, body.log_id)
    if log is None:
        raise HTTPException(
            status_code=404,
            detail={"code": 40001, "message": "问答记录不存在"},
        )

    # Prevent duplicate feedback
    existing = (
        await session.execute(
            select(Feedback).where(
                Feedback.log_id == body.log_id,
                Feedback.user_id == claims.sub,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": 40001, "message": "您已对该回答提交过反馈"},
        )

    feedback = Feedback(
        feedback_id=f"fb_{uuid.uuid4().hex[:12]}",
        log_id=body.log_id,
        user_id=claims.sub,
        feedback_type=body.feedback_type,
        reason=body.reason,
        comment=body.comment,
        created_at=datetime.now(timezone.utc),
    )
    session.add(feedback)
    await session.commit()

    return FeedbackResponse(
        feedback_id=feedback.feedback_id,
        log_id=feedback.log_id,
        feedback_type=feedback.feedback_type,
        message="反馈已提交，感谢您的参与",
    )
