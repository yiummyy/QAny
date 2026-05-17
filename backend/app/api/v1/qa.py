"""/api/v1/qa/* — SSE streaming ask + session lookup + chunk detail — Spec §4.2, §4.3."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserClaims, require_any_user
from app.config import get_settings
from app.harness import agent_loop
from app.harness.agent_config import AGENT_PRESETS, SCENE_TO_AGENT
from app.harness.degrade import get_today_cost_rmb, incr_today_cost_rmb
from app.harness.models import ConfirmationResponse, EventType
from app.harness.session_store import get_history
from app.models.qa_log import QALog
from app.models.settings import QASettings
from app.providers.dashscope_provider import DashScopeProvider
from app.providers.deepseek_provider import DeepSeekProvider
from app.providers.router import ProviderRouter
from app.storage.es_client import get_es
from app.storage.pg import get_db, get_sessionmaker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/qa", tags=["qa"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(..., min_length=1, max_length=64)
    input_type: str = "text"
    scene: str = "general"


# ---------------------------------------------------------------------------
# POST /ask — SSE streaming
# ---------------------------------------------------------------------------


@router.post("/ask")
async def ask_question(
    body: AskRequest,
    request: Request,
    claims: UserClaims = Depends(require_any_user),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream QA agent loop events as Server-Sent Events (SSE)."""
    # ---- Rate limiting (B8) ----
    from app.api.rate_limiter import (
        check_ip_rate_limit,
        check_user_concurrency,
        check_user_daily_quota,
        release_user_concurrency,
    )

    check_ip_rate_limit(request)
    await check_user_daily_quota(claims.sub)
    concurrency_token = await check_user_concurrency(claims.sub)

    trace_id = getattr(request.state, "trace_id", f"tr_{uuid.uuid4().hex[:12]}")
    provider_router = await _build_provider_router(session)

    async def _rate_limited_stream():
        try:
            async for frame in _sse_event_stream(
                query=body.question,
                session_id=body.session_id,
                scene=body.scene,
                user_claims=claims,
                provider_router=provider_router,
                trace_id=trace_id,
            ):
                yield frame
        finally:
            await release_user_concurrency(claims.sub, concurrency_token)

    return StreamingResponse(
        _rate_limited_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _sse_event_stream(
    query: str,
    session_id: str,
    scene: str,
    user_claims: UserClaims,
    provider_router: ProviderRouter,
    trace_id: str,
) -> AsyncIterator[str]:
    """Run agent loop and yield SSE-formatted frames."""
    start_time = time.monotonic()
    full_answer = ""
    sources: list[dict] = []
    confidence: str = "high"
    confidence_score: float = 1.0
    error_code: int | None = None
    status: str = "success"

    # Resolve agent configuration from scene
    agent_name = SCENE_TO_AGENT.get(scene, "KnowledgeQA")
    agent_config = AGENT_PRESETS[agent_name]

    # Check cost circuit breaker before processing
    today_cost = await get_today_cost_rmb()
    daily_limit = await _get_daily_cost_limit()
    if daily_limit > 0 and today_cost >= daily_limit:
        yield _sse_frame("error", {
            "code": 50900,
            "message": f"当日成本已超阈值 (¥{today_cost:.2f}/¥{daily_limit:.2f})，请明日再试",
            "fallback_answer": "系统维护中，请稍后再试或联系管理员。",
        })
        return

    try:
        event_seq = 0
        async for event in agent_loop.run(
            query, session_id, user_claims, agent_config, provider_router,
        ):
            event_seq += 1
            if event.type == EventType.STATUS:
                logger.debug("sse[%d] status phase=%s", event_seq, event.data.get("phase"))
                yield _sse_frame("status", event.data)
            elif event.type == EventType.MESSAGE:
                chunk = event.data.get("chunk", "")
                full_answer += chunk
                logger.debug("sse[%d] message len=%d total=%d", event_seq, len(chunk), len(full_answer))
                yield _sse_frame("message", event.data)
            elif event.type == EventType.DONE:
                full_answer = event.data.get("answer", full_answer)
                sources = event.data.get("sources", [])
                confidence = event.data.get("confidence", "high")
                confidence_score = event.data.get("confidence_score", 1.0)
                event.data["trace_id"] = trace_id
                event.data["response_time_ms"] = int((time.monotonic() - start_time) * 1000)
                logger.info("sse[%d] done answer_len=%d sources=%d", event_seq, len(full_answer), len(sources))
                yield _sse_frame("done", event.data)
            elif event.type == EventType.ERROR:
                error_code = event.data.get("code")
                status = "fallback"
                event.data.setdefault("fallback_answer", "系统繁忙，请稍后重试。")
                logger.warning("sse[%d] error code=%s", event_seq, error_code)
                yield _sse_frame("error", event.data)
    except Exception as exc:
        logger.exception("QA stream error trace_id=%s session_id=%s", trace_id, session_id)
        status = "error"
        error_code = 50000
        fallback = {
            "code": 50000,
            "message": "系统内部错误",
            "fallback_answer": "抱歉，系统暂时无法处理您的问题，请稍后重试或联系管理员。",
        }
        yield _sse_frame("error", fallback)

    # Persist QA log
    response_time_ms = int((time.monotonic() - start_time) * 1000)
    await _persist_qa_log(
        session_id=session_id,
        user_id=user_claims.sub,
        scene=scene,
        question=query,
        answer=full_answer or None,
        sources=sources,
        confidence=confidence,
        confidence_score=confidence_score,
        response_time_ms=response_time_ms,
        status=status,
        error_code=error_code,
        trace_id=trace_id,
    )

    # Track daily cost using model-specific pricing (B7)
    # qwen-plus: input ¥0.002/1K tokens, output ¥0.006/1K tokens
    # Chinese ~1.5 chars/token → estimate tokens from character count
    if full_answer and status == "success":
        output_tokens_est = len(full_answer) / 1.5
        input_tokens_est = len(query) / 1.5 + sum(len(s.get("content", "")) for s in sources) / 1.5
        estimated_cost = (input_tokens_est / 1000) * 0.002 + (output_tokens_est / 1000) * 0.006
        await incr_today_cost_rmb(estimated_cost)


def _sse_frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _get_daily_cost_limit() -> float:
    """Read daily cost limit from qa_settings (best-effort, default 1000 RMB)."""
    try:
        from app.models.settings import QASettings
        from app.storage.pg import get_sessionmaker

        async with get_sessionmaker()() as session:
            row = await session.get(QASettings, 1)
            if row and "cost_daily_limit_rmb" in row.config:
                return float(row.config["cost_daily_limit_rmb"])
    except Exception:
        pass
    return 1000.0


async def _build_provider_router(session: AsyncSession | None = None) -> ProviderRouter:
    """Build ProviderRouter.
    
    API keys and custom providers are resolved in order:
    1. qa_settings.config in the database (set by admin via UI)
    2. .env file (DASHSCOPE_API_KEY / DEEPSEEK_API_KEY)
    """
    primary = None
    fallback = None

    # Try DB settings first
    db_config: dict[str, Any] = {}
    if session is not None:
        try:
            row = await session.get(QASettings, 1)
            if row:
                db_config = row.config or {}
        except Exception:
            pass

    # Generic LLM configuration
    llm_provider = db_config.get("llm_provider")
    llm_base_url = db_config.get("llm_base_url")
    llm_api_key = db_config.get("llm_api_key")
    llm_model = db_config.get("llm_model", "qwen-plus")
    model_routing = db_config.get("model_routing", {})

    # Support legacy config fields if the generic ones aren't set
    if not llm_api_key:
        llm_api_key = db_config.get("dashscope_api_key")
    if not llm_api_key:
        settings = get_settings()
        llm_api_key = settings.dashscope_api_key.get_secret_value() if settings.dashscope_api_key else ""

    # Setup the primary provider dynamically
    if llm_api_key and "****" not in llm_api_key:
        if llm_provider == "deepseek":
            base_url = llm_base_url or "https://api.deepseek.com/v1"
            primary = DashScopeProvider(model=llm_model, api_key=llm_api_key)
            primary.base_url = base_url
        elif llm_provider == "openai" or llm_provider == "zhipu":
            base_url = llm_base_url
            if llm_provider == "zhipu" and not base_url:
                base_url = "https://open.bigmodel.cn/api/paas/v4"
            primary = DashScopeProvider(model=llm_model, api_key=llm_api_key)
            if base_url:
                primary.base_url = base_url
        else:
            # Default is DashScope
            base_url = llm_base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            primary = DashScopeProvider(model=llm_model, api_key=llm_api_key)
            primary.base_url = base_url

    # Fallback to DeepSeek if explicitly defined (legacy behavior)
    dk_key = db_config.get("deepseek_api_key") or (
        get_settings().deepseek_api_key.get_secret_value() if get_settings().deepseek_api_key else ""
    )
    if dk_key and "****" not in dk_key:
        if primary is None:
            primary = DeepSeekProvider(api_key=dk_key)
        else:
            fallback = DeepSeekProvider(api_key=dk_key)

    if primary is None:
        # Return a no-op router — agent_loop will use _default_plan for everything
        primary = DashScopeProvider(model="qwen-plus")

    stage_providers: dict[str, BaseLLMProvider] = {}
    if isinstance(model_routing, dict):
        for stage, routing_info in model_routing.items():
            if not routing_info or not isinstance(routing_info, dict):
                continue
            
            st_provider = routing_info.get("provider") or llm_provider
            st_base_url = routing_info.get("base_url") or llm_base_url
            st_api_key = routing_info.get("api_key")
            if not st_api_key or "****" in st_api_key:
                st_api_key = llm_api_key
            st_model = routing_info.get("model") or llm_model
            
            if st_api_key and "****" not in st_api_key:
                if st_provider == "deepseek":
                    b_url = st_base_url or "https://api.deepseek.com/v1"
                    p = DashScopeProvider(model=st_model, api_key=st_api_key)
                    p.base_url = b_url
                    stage_providers[stage] = p
                elif st_provider == "openai" or st_provider == "zhipu":
                    b_url = st_base_url
                    if st_provider == "zhipu" and not b_url:
                        b_url = "https://open.bigmodel.cn/api/paas/v4"
                    p = DashScopeProvider(model=st_model, api_key=st_api_key)
                    if b_url:
                        p.base_url = b_url
                    stage_providers[stage] = p
                else:
                    b_url = st_base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
                    p = DashScopeProvider(model=st_model, api_key=st_api_key)
                    p.base_url = b_url
                    stage_providers[stage] = p

    return ProviderRouter(primary=primary, fallback=fallback, model_routing=model_routing, stage_providers=stage_providers)


# ---------------------------------------------------------------------------
# QA log persistence
# ---------------------------------------------------------------------------


async def _persist_qa_log(
    session_id: str,
    user_id: str,
    scene: str,
    question: str,
    answer: str | None,
    sources: list[dict],
    confidence: str,
    confidence_score: float,
    response_time_ms: int,
    status: str,
    error_code: int | None,
    trace_id: str,
) -> None:
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            log = QALog(
                log_id=f"qalog_{uuid.uuid4().hex[:12]}",
                session_id=session_id,
                user_id=user_id,
                scene=scene,
                question=question,
                answer=answer,
                sources=sources or None,
                confidence=confidence,
                confidence_score=round(confidence_score, 3),
                response_time_ms=response_time_ms,
                status=status,
                error_code=error_code,
                trace_id=trace_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(log)
            await session.commit()
            logger.info(
                "qa_log_persisted log_id=%s session_id=%s status=%s trace_id=%s",
                log.log_id, session_id, status, trace_id,
            )
    except Exception:
        logger.exception("Failed to persist QA log")


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    claims: UserClaims = Depends(require_any_user),
) -> dict:
    """Return session history from JSONL / Redis store."""
    records = await get_history(session_id)
    return {"session_id": session_id, "records": records, "count": len(records)}


# ---------------------------------------------------------------------------
# GET /chunks/{chunk_id}
# ---------------------------------------------------------------------------


@router.get("/chunks/{chunk_id}")
async def get_chunk(
    chunk_id: str,
    claims: UserClaims = Depends(require_any_user),
) -> dict:
    """Fetch a single chunk by chunk_id from Elasticsearch (source drawer)."""
    es = get_es()
    try:
        result = await es.search(
            index="qa_chunks",
            body={"query": {"term": {"chunk_id": chunk_id}}, "size": 1},
        )
        hits = result["hits"]["hits"]
        if not hits:
            raise HTTPException(status_code=404, detail={"code": 40001, "message": "Chunk 不存在"})
        source = hits[0]["_source"]
        return {
            "chunk_id": source.get("chunk_id"),
            "doc_id": source.get("doc_id"),
            "doc_name": source.get("doc_name"),
            "content": source.get("content"),
            "section": source.get("section"),
            "permission_level": source.get("permission_level"),
            "chunk_index": source.get("chunk_index"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch chunk %s: %s", chunk_id, exc)
        raise HTTPException(status_code=500, detail={"code": 50101, "message": "ES 查询异常"})


# ---------------------------------------------------------------------------
# POST /confirm — human-in-the-loop confirmation for side-effect tools
# ---------------------------------------------------------------------------


@router.post("/confirm")
async def confirm_action(
    body: ConfirmationResponse,
    claims: UserClaims = Depends(require_any_user),
) -> dict:
    """Handle user confirmation/rejection for a pending side-effect action.

    Called by the frontend when the user clicks [确认] or [取消] on a
    confirmation card rendered in the chat stream.
    """
    from app.harness.agent_loop import get_pending_confirmation
    from app.storage.redis_client import get_redis

    redis = get_redis()
    key = f"cfm:{body.action_token}"
    raw = await redis.get(key)

    if raw is None:
        raise HTTPException(
            status_code=400,
            detail={"code": 50201, "message": "确认令牌无效或已过期"},
        )

    data = json.loads(raw)
    if data.get("status") != "pending":
        raise HTTPException(
            status_code=400,
            detail={"code": 50202, "message": "该操作已被处理，无需重复确认"},
        )

    # Write user choice to Redis
    data["status"] = body.choice
    data["user_id"] = claims.sub
    await redis.setex(key, 60, json.dumps(data))  # keep for 60s after decision

    # Signal the waiting agent loop
    event = get_pending_confirmation(body.action_token)
    if event is not None:
        event.set()

    logger.info(
        "confirmation action_token=%s choice=%s user=%s",
        body.action_token, body.choice, claims.sub,
    )
    return {"status": "ok", "message": "确认已收到"}
