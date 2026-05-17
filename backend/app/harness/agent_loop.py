"""Main Agent Loop — Plan high-level actions only, RAG runs deterministically."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from app.auth.claims import UserClaims
from app.harness.agent_config import AgentConfig
from app.harness.context import COMPACT_THRESHOLD, build, build_rewrite_history, compact, should_compact
from app.harness.degrade import DegradeState
from app.harness.models import (
    ConfirmationRequest,
    ConfirmationResponse,
    Event,
    EventType,
    PlanDecision,
    ToolCall,
    ToolResult,
)
from app.harness.cost_tracker import CostTracker
from app.harness.perf_tracker import PerfTracker
from app.harness.session_store import append, make_task_id, save_task
from app.harness.tool_registry import build_agent_handlers
from app.providers.base import StreamChunk
from app.providers.router import ProviderRouter

logger = logging.getLogger(__name__)

FALLBACK_ANSWER = "抱歉，我无法确定答案，建议您咨询相关部门或查阅原始文档。"

# Side-effect tools that require user confirmation — label for UI display
TOOL_LABEL_MAP: dict[str, str] = {
    "create_ticket": "创建工单",
    "escalate": "升级工单",
    "run_diagnostic": "执行诊断",
}

# In-process pending confirmations: action_token → asyncio.Event
# Shared between agent_loop (waiter) and /confirm endpoint (setter).
_pending_confirmations: dict[str, asyncio.Event] = {}


def get_pending_confirmation(action_token: str) -> asyncio.Event | None:
    """Look up a pending confirmation event by action_token (used by /confirm endpoint)."""
    return _pending_confirmations.get(action_token)


async def _execute_tool_with_retry(
    handler, kwargs: dict[str, Any],
) -> ToolResult:
    """Execute a tool with timeout and retry support.

    Uses ``handler.timeout`` for ``asyncio.wait_for`` and retries up to
    ``handler.max_retries`` times with exponential backoff (1s, 2s, 4s…).
    Only exceptions listed in ``handler.retryable_exceptions`` trigger a retry;
    non-retryable exceptions and ``TimeoutError`` exhaustion return an error.
    """
    max_attempts = 1 + handler.max_retries
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return await asyncio.wait_for(
                handler.fn(**kwargs),
                timeout=handler.timeout,
            )
        except TimeoutError:
            last_error = TimeoutError(f"工具 {handler.name} 超时 ({handler.timeout}s)")
            if attempt < max_attempts - 1:
                delay = 2 ** attempt
                logger.warning(
                    "tool_timeout name=%s attempt=%d/%d retry_in=%ds",
                    handler.name, attempt + 1, max_attempts, delay,
                )
                await asyncio.sleep(delay)
        except Exception as exc:
            retryable = handler.retryable_exceptions or ()
            if type(exc) in retryable:
                last_error = exc
                if attempt < max_attempts - 1:
                    delay = 2 ** attempt
                    logger.warning(
                        "tool_retryable_error name=%s attempt=%d/%d exc=%s retry_in=%ds",
                        handler.name, attempt + 1, max_attempts, exc, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                # Exhausted retries → fall through to end-of-loop error
            else:
                return ToolResult(status="error", summary=f"工具执行异常: {exc}")

    return ToolResult(
        status="error",
        summary=f"工具 {handler.name} 重试耗尽 ({max_attempts}次): {last_error}",
        data={"retries_exhausted": True},
    )


async def _execute_tools(
    decision: PlanDecision,
    tool_handlers: dict,
    user_claims: UserClaims,
    provider_router: ProviderRouter | None,
    agent_config: AgentConfig,
    ctx,
) -> list[tuple[str, ToolResult]]:
    """Execute tools from a PlanDecision — single or parallel via asyncio.gather.

    Supports both the legacy ``decision.tool`` (single) and new
    ``decision.tools`` (parallel) fields. Tools are executed concurrently
    with independent timeout/retry per tool.
    """
    # Resolve tool calls from decision
    tool_calls: list[ToolCall] = []
    if decision.tools:
        tool_calls = decision.tools
    elif decision.tool:
        tool_calls = [ToolCall(tool=decision.tool, args=decision.args or {})]

    if not tool_calls:
        return []

    async def _run_one(tc: ToolCall) -> tuple[str, ToolResult]:
        handler = tool_handlers.get(tc.tool)
        if not handler:
            return (tc.tool, ToolResult(status="error", summary=f"未知工具: {tc.tool}"))

        try:
            args: dict[str, Any] = dict(tc.args)
            _inject_tool_args_from_context(args, ctx)

            sig = inspect.signature(handler.fn)
            kwargs: dict[str, Any] = dict(args, user_claims=user_claims)
            if "provider_router" in sig.parameters:
                kwargs["provider_router"] = provider_router
            if "agent_config" in sig.parameters:
                kwargs["agent_config"] = agent_config
            if "history" in sig.parameters:
                kwargs["history"] = build_rewrite_history(ctx)
            result = await _execute_tool_with_retry(handler, kwargs)
            return (tc.tool, result)
        except Exception as exc:
            return (tc.tool, ToolResult(status="error", summary=f"工具执行异常: {exc}"))

    # Parallel execution — each tool has its own timeout via _execute_tool_with_retry
    results = await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
    return list(results)


# Map tool names to user-facing phase names and status messages.
# RAG sub-steps (hybrid_search, rerank, permission_check, generate_answer) are
# no longer exposed — they run inside query_knowledge.
TOOL_PHASE_MAP: dict[str, tuple[str, str]] = {
    "search_knowledge": ("searching", "正在检索知识库..."),
    "query_knowledge": ("retrieving", "正在检索知识库..."),  # legacy compat
    "generate_answer": ("generating", "正在生成答案..."),
    "hallucination_check": ("verifying", "正在验证答案可信度..."),
}


# ---------------------------------------------------------------------------
# Confirmation helpers (human-in-the-loop for side-effect tools)
# ---------------------------------------------------------------------------


def _build_confirmation_summary(tool_name: str, args: dict[str, Any]) -> str:
    """Generate a user-friendly summary of the pending side-effect action."""
    if tool_name == "create_ticket":
        title = args.get("title", "未知工单")
        priority = args.get("priority", "medium")
        category = args.get("category", "其他")
        return f"AI 将为您创建一个工单：「{title}」，优先级: {priority}，分类: {category}"
    elif tool_name == "escalate":
        ticket_id = args.get("ticket_id", "未知")
        reason = args.get("reason", "未提供原因")
        return f"AI 将把工单 {ticket_id} 升级为 urgent，原因: {reason}"
    elif tool_name == "run_diagnostic":
        device = args.get("device_name", "未知设备")
        check_type = args.get("check_type", "all")
        return f"AI 将在设备 {device} 上执行诊断：{check_type}"
    return f"AI 将执行操作：{tool_name}"


async def _build_confirmation_request(
    tc: ToolCall,
    handler,
    session_id: str,
) -> tuple[ConfirmationRequest, asyncio.Event]:
    """Build a ConfirmationRequest, store in Redis, register event. Returns (req, event)."""
    from app.storage.redis_client import get_redis

    action_token = f"cfm_{uuid.uuid4().hex[:16]}"
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=handler.confirmation_timeout
    )

    summary = _build_confirmation_summary(tc.tool, tc.args)
    label = TOOL_LABEL_MAP.get(tc.tool, tc.tool)

    req = ConfirmationRequest(
        action_token=action_token,
        tool_name=tc.tool,
        tool_label=label,
        summary=summary,
        details=tc.args,
        expires_at=expires_at.isoformat(),
    )

    redis = get_redis()
    await redis.setex(
        f"cfm:{action_token}",
        int(handler.confirmation_timeout) + 30,
        json.dumps({"session_id": session_id, "status": "pending"}),
    )

    event = asyncio.Event()
    _pending_confirmations[action_token] = event
    return req, event


async def _wait_for_confirmation(
    action_token: str,
    event: asyncio.Event,
    timeout: float,
) -> ConfirmationResponse:
    """Wait for user confirmation or timeout. Returns ConfirmationResponse."""
    from app.storage.redis_client import get_redis

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        redis = get_redis()
        raw = await redis.get(f"cfm:{action_token}")
        data = json.loads(raw) if raw else {}
        choice = data.get("choice", "rejected")
        return ConfirmationResponse(action_token=action_token, choice=choice)
    except asyncio.TimeoutError:
        return ConfirmationResponse(action_token=action_token, choice="rejected")
    finally:
        _pending_confirmations.pop(action_token, None)
        try:
            redis = get_redis()
            await redis.delete(f"cfm:{action_token}")
        except Exception:
            pass


async def run(
    query: str,
    session_id: str,
    user_claims: UserClaims,
    agent_config: AgentConfig,
    provider_router: ProviderRouter | None = None,
) -> AsyncIterator[Event]:
    """Execute the agent main loop, yielding Events.

    The Agent plans high-level actions only (query_knowledge, final_answer).
    The RAG pipeline runs deterministically inside query_knowledge — the
    Agent does NOT plan individual RAG steps.
    """
    # Use raw session_id for storage (frontend sends it directly)
    store_session_id = session_id

    ctx = await build(
        store_session_id, query, user_claims,
        system_prompt_override=agent_config.plan_system_prompt,
    )

    # Extract user-declared constraints from query (rule-based, fast)
    for ctype, matched in extract_constraints(query):
        ctx.pin_constraint(matched, ctype, source_step=0)

    await append(store_session_id, {"type": "user", "content": query})

    yield Event(type=EventType.STATUS, data={"phase": "planning", "message": "正在分析问题..."})

    degrade = DegradeState()

    tool_handlers = build_agent_handlers(agent_config)

    perf = PerfTracker()  # per-request performance tracker
    cost = CostTracker(model=getattr(provider_router, "model", "qwen-plus") if provider_router else "qwen-plus")
    perf.track_start("total")

    last_compact_step: int = -999  # cooldown tracker for compaction

    for step in range(agent_config.max_steps):
        degraded = await degrade.check("_any_")
        if degraded:
            yield Event(type=EventType.ERROR, data={"code": 50000, "message": degraded.summary})
            await append(store_session_id, {"type": "error", "message": degraded.summary})
            return

        if provider_router is None:
            decision = _default_plan(ctx, step, agent_config)
            perf.record_decision(step, {"type": decision.type, "tool": decision.tool})
        else:
            try:
                yield Event(type=EventType.STATUS, data={
                    "phase": "planning",
                    "message": f"正在分析问题... (步骤 {step + 1})",
                })
                # Programmatic guard: remove tools that have already succeeded,
                # forcing the Plan LLM forward through search → generate → final
                active_handlers = dict(tool_handlers)
                for name in list(active_handlers.keys()):
                    if name in ("search_knowledge", "generate_answer") and _find_tool_result(ctx, name):
                        del active_handlers[name]
                        logger.info("removed %s from available tools (already succeeded)", name)
                tools_schema = _build_tools_schema(active_handlers)
                plan_messages = _build_plan_messages(ctx)
                async with perf.track("plan"):
                    plan_result = await provider_router.plan(plan_messages, tools_schema)
                decision = PlanDecision(**plan_result)
                degrade.record_success("plan")
                perf.record_decision(step, {"type": decision.type, "tool": decision.tool, "tools": [
                    {"tool": t.tool, "args": t.args} for t in (decision.tools or [])
                ]} if decision.tools else {"type": decision.type, "tool": decision.tool})
                logger.info("plan step=%d decision=%s tool=%s", step, decision.type, decision.tool)
            except Exception as exc:
                logger.warning("Plan step %d failed: %s", step, exc)
                degrade.record_failure("plan")
                decision = _default_plan(ctx, step, agent_config)
                perf.record_decision(step, {"type": "fallback", "tool": decision.tool})

        if decision.type == "final_answer" or step >= agent_config.max_steps - 1:
            # Guard: if generate_answer hasn't been called, inject it now
            if not _find_tool_result(ctx, "generate_answer") and not _find_tool_result(ctx, "query_knowledge"):
                logger.info("final_answer triggered before generate_answer — injecting generate_answer")
                gen_decision = PlanDecision(
                    type="tool_call",
                    tool="generate_answer",
                    tools=[ToolCall(tool="generate_answer", args={"query": query})],
                )
                gen_results = await _execute_tools(
                    decision=gen_decision,
                    tool_handlers=tool_handlers,
                    user_claims=user_claims,
                    provider_router=provider_router,
                    agent_config=agent_config,
                    ctx=ctx,
                )
                if gen_results:
                    for name, result in gen_results:
                        ctx.append_tool_result(name, result)
                        await append(store_session_id, {
                            "type": "tool_result", "name": name,
                            "summary": result.summary,
                        })

            yield Event(type=EventType.STATUS, data={"phase": "thinking", "message": "AI 正在思考..."})

            full_answer = ""
            full_reasoning = ""
            ttft_ms: float | None = None
            t_stream_start = time.monotonic()
            async for chunk in _stream_final_answer(ctx, query, user_claims, provider_router):
                if ttft_ms is None:
                    ttft_ms = round((time.monotonic() - t_stream_start) * 1000, 1)
                if isinstance(chunk, dict):
                    content = chunk.get("content", "")
                    reasoning = chunk.get("reasoning_content", "")
                    if reasoning:
                        full_reasoning += reasoning
                        yield Event(type=EventType.MESSAGE, data={"chunk": "", "reasoning_chunk": reasoning})
                    if content:
                        full_answer += content
                        yield Event(type=EventType.MESSAGE, data={"chunk": content, "reasoning_chunk": ""})
                else:
                    full_answer += chunk
                    yield Event(type=EventType.MESSAGE, data={"chunk": chunk})

            perf.ttft_ms = ttft_ms

            # --- Citation verification (post-stream, programmatic) ---
            citation_report = None
            chunks = _extract_chunks(ctx)
            if full_answer and full_answer != FALLBACK_ANSWER and chunks:
                yield Event(type=EventType.STATUS, data={
                    "phase": "verifying",
                    "message": "正在验证引用可信度...",
                })
                try:
                    from app.tools.citation_verifier import verify_citations
                    citation_report = await verify_citations(full_answer, chunks)
                except Exception as exc:
                    logger.warning("Citation verification failed: %s", exc)
                    citation_report = None

            # Explicitly run hallucination check AFTER streaming the answer
            hal_handler = tool_handlers.get("hallucination_check")
            chunks = _extract_chunks(ctx)
            if hal_handler and full_answer and full_answer != FALLBACK_ANSWER:
                yield Event(type=EventType.STATUS, data={"phase": "verifying", "message": "正在验证答案可信度..."})
                try:
                    sig = inspect.signature(hal_handler.fn)
                    hal_kwargs: dict[str, Any] = dict(
                        answer=full_answer, chunks=chunks, user_claims=user_claims,
                    )
                    if "provider_router" in sig.parameters:
                        hal_kwargs["provider_router"] = provider_router
                    if "citation_report" in sig.parameters and citation_report:
                        hal_kwargs["citation_report"] = citation_report
                    hal_result: ToolResult = await hal_handler.fn(**hal_kwargs)
                except Exception as exc:
                    hal_result = ToolResult(status="error", summary=f"幻觉检测异常: {exc}")

                ctx.append_tool_result("hallucination_check", hal_result)
                await append(store_session_id, {
                    "type": "tool_result",
                    "name": "hallucination_check",
                    "summary": hal_result.summary,
                })

                # G1: Replace answer if hallucination score is too low
                hal_data = hal_result.data or {}
                if hal_data.get("needs_fallback"):
                    logger.warning(
                        "hallucination: needs_fallback=True score=%.2f session=%s",
                        hal_data.get("score", 0), store_session_id,
                    )
                    full_answer = FALLBACK_ANSWER
                    # G3: Notify frontend that answer was downgraded
                    yield Event(type=EventType.STATUS, data={
                        "phase": "corrected",
                        "message": "检测到答案可信度不足，已替换为兜底回答",
                    })

            metadata = _extract_metadata(ctx)

            # Content safety audit (post-stream, non-blocking for first token)
            from app.harness.safety_check import SAFETY_FALLBACK, audit_answer
            safety = await audit_answer(
                answer=full_answer,
                sources=metadata.get("sources", []),
                user_permission_level=user_claims.pl,
            )
            if safety.is_blocked():
                logger.warning("safety: answer blocked for session=%s", store_session_id)
                full_answer = SAFETY_FALLBACK
                # G3: Notify frontend that content was blocked
                yield Event(type=EventType.STATUS, data={
                    "phase": "blocked",
                    "message": "检测到回答内容存在安全风险，已自动拦截",
                })
            task_id = make_task_id()
            tasks_data: dict[str, Any] = {
                "task_id": task_id,
                "session_id": store_session_id,
                "query": query,
                "answer": full_answer,
                "steps": step + 1,
                **metadata,
            }
            await save_task(task_id, tasks_data)
            await append(store_session_id, {
                "type": "assistant_done",
                "content": full_answer,
                "steps": step + 1,
            })

            perf.track_end("total")
            # Estimate cost: rough token count based on answer length
            cost.record("answer_generation", output_tokens=len(full_answer))
            yield Event(type=EventType.DONE, data={
                "answer": full_answer,
                "sources": metadata.get("sources", []),
                "confidence": metadata.get("confidence", "high"),
                "confidence_score": metadata.get("confidence_score", 1.0),
                "ttft_ms": ttft_ms,
                "citations": citation_report.model_dump() if citation_report else None,
                "steps": step + 1,
                "perf": perf.summary(),
                "cost": cost.summary(),
            })
            return

        # Resolve tools from decision (supports both single and parallel)
        tool_calls: list[ToolCall] = []
        if decision.tools:
            tool_calls = decision.tools
        elif decision.tool:
            tool_calls = [ToolCall(tool=decision.tool, args=decision.args or {})]

        # Deduplicate: remove identical parallel calls to the same tool
        seen: set[tuple[str, str]] = set()
        deduped: list[ToolCall] = []
        for tc in tool_calls:
            key = (tc.tool, json.dumps(tc.args or {}, sort_keys=True))
            if key not in seen:
                seen.add(key)
                deduped.append(tc)
        if len(deduped) < len(tool_calls):
            logger.info("deduplicated parallel tool calls: %d → %d", len(tool_calls), len(deduped))
        tool_calls = deduped

        # Validate all tools exist before executing any
        missing = [tc.tool for tc in tool_calls if tc.tool not in tool_handlers]
        if missing:
            yield Event(type=EventType.ERROR, data={"code": 50000, "message": f"未知工具: {', '.join(missing)}"})
            await append(store_session_id, {"type": "error", "message": f"unknown tools: {missing}"})
            return

        if len(tool_calls) == 1:
            logger.info("Step %d: calling tool %s", step, tool_calls[0].tool)
        else:
            logger.info("Step %d: parallel calling %d tools: %s", step, len(tool_calls),
                        [tc.tool for tc in tool_calls])

        # Yield progress status for frontend progress stepper
        tool_names = [tc.tool for tc in tool_calls]
        for tname in tool_names:
            tool_phase = TOOL_PHASE_MAP.get(tname)
            if tool_phase:
                phase_name, phase_msg = tool_phase
                yield Event(type=EventType.STATUS, data={"phase": phase_name, "message": phase_msg})

        # --- Confirmation checkpoint: side-effect tools need human approval ---
        tools_needing_confirmation = [
            tc for tc in tool_calls
            if (handler := tool_handlers.get(tc.tool))
            and handler.requires_confirmation
        ]

        if tools_needing_confirmation:
            for tc in tools_needing_confirmation:
                handler = tool_handlers[tc.tool]

                req, event = await _build_confirmation_request(
                    tc, handler, store_session_id,
                )

                yield Event(type=EventType.STATUS, data={
                    "phase": "confirming",
                    "message": f"等待确认: {req.tool_label}",
                    "confirmation": req.model_dump(),
                })

                result = await _wait_for_confirmation(
                    req.action_token, event, handler.confirmation_timeout,
                )

                is_timeout = not event.is_set()
                if result.choice == "rejected":
                    reject_phase = (
                        "confirmation_timeout" if is_timeout
                        else "confirmation_rejected"
                    )
                    reject_msg = (
                        f"确认超时，已自动取消: {req.tool_label}"
                        if is_timeout
                        else f"用户取消了操作: {req.tool_label}"
                    )
                    yield Event(type=EventType.STATUS, data={
                        "phase": reject_phase, "message": reject_msg,
                    })
                    ctx.append_tool_result(tc.tool, ToolResult(
                        status="degraded",
                        summary=reject_msg,
                        data={"confirmation": "timeout" if is_timeout else "rejected"},
                    ))
                    # Remove this tool from the execution list
                    tool_calls = [t for t in tool_calls if t.tool != tc.tool]

            if not tool_calls:
                # All side-effect tools were rejected — loop back to Plan step
                continue

        # Execute tools (serial or parallel depending on count)
        async with perf.track("tool_execution"):
            tool_results = await _execute_tools(
                decision, tool_handlers, user_claims, provider_router, agent_config, ctx,
            )

        for tool_name, result in tool_results:
            ctx.append_tool_result(tool_name, result)
            await append(store_session_id, {
                "type": "tool_call",
                "name": tool_name,
                "args": decision.args if tool_name == decision.tool else None,
            })
            await append(store_session_id, {
                "type": "tool_result",
                "name": tool_name,
                "summary": result.summary,
            })

            # ---- Observe phase: structured quality assessment (P0) ----
            from app.harness.observe import observe as _observe
            observation = _observe(tool_name, result, step)
            ctx.observation_log.append(observation)

            # ---- P1: Quality-gated retry for insufficient search ----
            if tool_name == "search_knowledge" and observation.coverage_verdict == "不足":
                if ctx.retry_count < 1:
                    logger.info(
                        "observe: coverage=%s hit=%d top=%.2f → retry #%d",
                        observation.coverage_verdict,
                        observation.hit_count,
                        observation.top_score,
                        ctx.retry_count + 1,
                    )
                    ctx.retry_count += 1
                    # Relax search: use original query + fallback index
                    search_handler = tool_handlers.get("search_knowledge")
                    if search_handler:
                        retry_result = await _execute_tool_with_retry(
                            search_handler,
                            dict(
                                query=query,  # original query (not rewritten)
                                index=None,   # let the router decide (includes default)
                                user_claims=user_claims,
                                provider_router=provider_router,
                                agent_config=agent_config,
                                history=build_rewrite_history(ctx),
                            ),
                        )
                        retry_obs = _observe("search_knowledge", retry_result, step)
                        ctx.observation_log.append(retry_obs)
                        # Replace the last tool_result with the retry result
                        ctx.tool_results[-1] = {
                            "tool": "search_knowledge",
                            "summary": retry_result.summary,
                            "status": retry_result.status,
                            "data": retry_result.data,
                        }
                        # If retry still insufficient → set stop signal
                        if retry_obs.coverage_verdict == "不足":
                            logger.warning(
                                "observe: retry still insufficient hit=%d top=%.2f → stop",
                                retry_obs.hit_count, retry_obs.top_score,
                            )
                            retry_obs.should_stop = True
                            retry_obs.stop_reason = "检索质量不足且重试已耗尽"
                            ctx.observation_log[-1] = retry_obs
                            observation = retry_obs

            # ---- Stop check: terminate loop early if signal is set ----
            if observation.should_stop:
                logger.info("observe: should_stop step=%d tool=%s reason=%s",
                            step, tool_name, observation.stop_reason)
                yield Event(type=EventType.STATUS, data={
                    "phase": "degraded",
                    "message": observation.stop_reason or "当前无法获取有效答案",
                })
                async for chunk in _stream_final_answer(
                    ctx, query, user_claims, provider_router,
                ):
                    yield chunk
                return

        # Check compaction threshold (adaptive cooldown based on token urgency)
        if should_compact(ctx, last_compact_step, step):
            ctx = await compact(ctx, provider_router)
            last_compact_step = step

    # MAX_STEPS exceeded
    yield Event(type=EventType.ERROR, data={"code": 50000, "message": "max steps exceeded"})
    await append(store_session_id, {"type": "error", "message": "max steps exceeded"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _stream_final_answer(
    ctx,
    query: str,
    user_claims: UserClaims,
    provider_router: ProviderRouter | None,
) -> AsyncIterator[StreamChunk | str]:
    """Stream the final answer from LLM, or use the fallback template.

    Looks for query_knowledge result first (new path), then falls back to
    generate_answer result (legacy path).
    """
    # Check generate_answer first (new decomposed path), then query_knowledge (legacy)
    gen_result = _find_tool_result(ctx, "generate_answer")
    qk_result = _find_tool_result(ctx, "query_knowledge")

    primary_result = gen_result or qk_result

    logger.info(
        "_stream_final_answer primary=%s status=%s provider=%s",
        "generate_answer" if gen_result else ("query_knowledge" if qk_result else "none"),
        primary_result.get("status") if primary_result else "none",
        provider_router is not None,
    )

    # Check if the primary result was short-circuited by the intent gate (chitchat / out-of-scope).
    if primary_result and primary_result.get("status") == "chitchat":
        gate_response = primary_result.get("gate_response", "")
        if gate_response:
            logger.info("_stream_final_answer → chitchat (%s)", primary_result.get("gate_category", "unknown"))
            yield gate_response
            return

    # Check if the primary result signaled degradation (low scores).
    if primary_result and primary_result.get("status") == "degraded":
        logger.info("_stream_final_answer → fallback (degraded)")
        yield FALLBACK_ANSWER
        return

    # Try LLM streaming
    if provider_router and primary_result:
        primary_data = primary_result.get("data", {}) or {}
        prompt = primary_data.get("prompt", "")
        if prompt:
            try:
                chunk_count = 0
                messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
                async for chunk in provider_router.stream_chat(
                    messages, stage="answer_generation", temperature=0.3, max_tokens=2000
                ):
                    chunk_count += 1
                    yield chunk
                logger.info("_stream_final_answer → LLM stream done, chunks=%d", chunk_count)
                return
            except Exception as exc:
                logger.warning("LLM streaming failed, using fallback: %s", exc)
        else:
            logger.info("_stream_final_answer primary result present but prompt is empty, falling to direct path")
    elif provider_router:
        # No generate_answer result — build prompt from search_knowledge chunks directly
        sk_result = _find_tool_result(ctx, "search_knowledge")
        if sk_result:
            sk_data = sk_result.get("data", {}) or {}
            chunks = sk_data.get("chunks", [])
            if chunks:
                # Build a simple answer prompt from search results
                from app.prompts.renderer import render
                chunks_text = "\n\n".join(
                    f"[S{i+1}] ({c.get('doc_name', '未知')}) {c.get('content', '')[:800]}"
                    for i, c in enumerate(chunks[:5])
                )
                prompt = render("generate_answer", query=query, chunks=chunks_text, permission_note=f"权限级别: {user_claims.pl}")
                messages = [{"role": "user", "content": prompt}]
                try:
                    chunk_count = 0
                    async for chunk in provider_router.stream_chat(
                        messages, stage="answer_generation", temperature=0.3, max_tokens=2000
                    ):
                        chunk_count += 1
                        yield chunk
                    logger.info("_stream_final_answer → fallback from search chunks done, chunks=%d", chunk_count)
                    if chunk_count > 0:
                        return
                except Exception as exc:
                    logger.warning("Fallback from search chunks failed: %s", exc)
            else:
                logger.info("_stream_final_answer → search found but empty chunks")
        else:
            logger.info("_stream_final_answer → direct LLM stream (no primary result, no search result)")

    # Last resort: direct LLM with context messages (no RAG)
    if provider_router:
        try:
            chunk_count = 0
            messages = [{"role": "system", "content": ctx.system_prompt}] + ctx.messages
            async for chunk in provider_router.stream_chat(
                messages, stage="answer_generation", temperature=0.3, max_tokens=2000
            ):
                chunk_count += 1
                yield chunk
            logger.info("_stream_final_answer → direct LLM stream done, chunks=%d", chunk_count)
            if chunk_count > 0:
                return
        except Exception as exc:
            logger.warning("LLM direct streaming failed: %s", exc)

    logger.info("_stream_final_answer → static fallback")
    yield "抱歉，当前知识库中没有找到相关信息，无法为您生成可靠答案。请尝试上传相关文档后再提问。"


def _find_tool_result(ctx, tool_name: str) -> dict | None:
    """Find the most recent result for a given tool in context."""
    for tr in reversed(ctx.tool_results):
        if tr.get("tool") == tool_name:
            return tr
    return None


def _extract_metadata(ctx) -> dict[str, Any]:
    """Extract sources, confidence, and confidence_score from tool results."""
    sources: list[dict] = []
    confidence = "high"
    confidence_score = 1.0

    # Extract sources: check search_knowledge first (new), then query_knowledge / generate_answer / hybrid_search (legacy)
    sk_result = _find_tool_result(ctx, "search_knowledge")
    qk_result = _find_tool_result(ctx, "query_knowledge")
    gen_result = _find_tool_result(ctx, "generate_answer")
    search_result = _find_tool_result(ctx, "hybrid_search")

    source_result = sk_result or qk_result or gen_result or search_result
    if source_result:
        src_data = source_result.get("data", {}) or {}
        chunks = src_data.get("chunks", [])
        for c in chunks[:5]:
            sources.append({
                "doc_id": c.get("doc_id", ""),
                "doc_name": c.get("doc_name", c.get("title", "未知文档")),
                "chunk_id": c.get("chunk_id", "") or c.get("_id", ""),
                "section": c.get("section", ""),
                "score": round(float(c.get("rerank_score", c.get("_rrf_score", c.get("_score", 0)))), 4),
            })

    # Extract confidence from hallucination_check
    hal_result = _find_tool_result(ctx, "hallucination_check")
    if hal_result:
        hal_data = hal_result.get("data", {}) or {}
        score = hal_data.get("score")
        verdict = hal_data.get("verdict")
        if score is not None:
            confidence_score = float(score)
        if verdict:
            confidence = verdict

    # No sources and no hallucination check override → low confidence
    if not sources and not hal_result:
        confidence = "low"
        confidence_score = 0.0

    return {
        "sources": sources,
        "confidence": confidence,
        "confidence_score": confidence_score,
    }


def _build_tools_schema(tool_handlers: dict) -> list[dict]:
    """Build OpenAI function-calling schema from tool handlers."""
    schema = []
    for name, handler in tool_handlers.items():
        # Exclude hallucination_check from LLM planner — it runs automatically post-stream
        if name == "hallucination_check":
            continue
        schema.append({
            "name": name,
            "description": f"Tool: {name}",
            "parameters": handler.input_schema.model_json_schema(),
        })
    return schema


def _build_plan_messages(ctx) -> list[dict]:
    """Build messages for the planner LLM, with structured observation reports (P0+P2)."""
    messages: list[dict] = []
    for msg in ctx.messages:
        messages.append({"role": msg["role"], "content": msg.get("content", "")})

    # ---- P0/P2: Structured observation report (replaces raw tool-call history) ----
    if ctx.observation_log:
        parts = ["## 执行观察报告\n"]
        prev_hit = 0
        prev_score = 0.0
        for obs in ctx.observation_log:
            # Step label
            step_label = f"Step {obs.step}" if not getattr(obs, "is_retry", False) else f"Step {obs.step}r"
            if obs.tool_name in ("search_knowledge", "query_knowledge"):
                verdict_icon = {"充足": "[OK]", "一般": "[~]", "不足": "[!!]"}.get(obs.coverage_verdict, "")
                idx_label = ", ".join(obs.indexes_searched) if obs.indexes_searched else "默认索引"
                parts.append(
                    f"{step_label}: {obs.tool_name} → {idx_label} → "
                    f"召回 {obs.hit_count} 条, 最高分 {obs.top_score:.2f}"
                )
                if obs.coverage_verdict:
                    parts.append(f"  覆盖率判定: {verdict_icon} {obs.coverage_verdict}")
                if obs.gap_description:
                    parts.append(f"  差距: {obs.gap_description}")
                if obs.suggested_action:
                    parts.append(f"  建议: {obs.suggested_action}")
                prev_hit = obs.hit_count
                prev_score = obs.top_score
            elif obs.tool_name == "generate_answer":
                status_label = "就绪" if obs.answer_ready else "未就绪(已降级)"
                parts.append(f"{step_label}: {obs.tool_name} → {status_label}")
                if obs.gap_description:
                    parts.append(f"  {obs.gap_description}")
            else:
                parts.append(f"{step_label}: {obs.tool_name} → {obs.status}")
            parts.append("")

        # ---- Trend analysis (P2) ----
        search_obs = [o for o in ctx.observation_log
                      if o.tool_name in ("search_knowledge", "query_knowledge")]
        if len(search_obs) >= 2:
            prev = search_obs[-2]
            last = search_obs[-1]
            if last.hit_count > prev.hit_count or last.top_score > prev.top_score:
                parts.append(
                    f"趋势: 检索质量提升 "
                    f"(召回 {prev.hit_count}→{last.hit_count}, "
                    f"最高分 {prev.top_score:.2f}→{last.top_score:.2f})。"
                )
            elif last.hit_count < prev.hit_count or last.top_score < prev.top_score:
                parts.append(
                    f"趋势: 检索质量下降 "
                    f"(召回 {prev.hit_count}→{last.hit_count}, "
                    f"最高分 {prev.top_score:.2f}→{last.top_score:.2f})。"
                )

        parts.append("\n请基于以上观察决定下一步工具调用（不要重复已成功的工具）。")
        messages.append({"role": "system", "content": "\n".join(parts)})

    # Inject pinned constraints so the planner never forgets user-declared limits
    if ctx.pinned_constraints:
        active = [c for c in ctx.pinned_constraints if c.expires_after_steps == 0]
        if active:
            constraint_text = "\n".join(
                f"- [{c.constraint_type}] {c.constraint}"
                for c in active
            )
            messages.append({"role": "system", "content": (
                "## 用户已声明的约束（以下约束在本次对话中持续有效，不可忽略）：\n"
                f"{constraint_text}"
            )})

    return messages


# ---------------------------------------------------------------------------
# Rule-based constraint extraction (Spec: context-compaction-optimization B3)
# ---------------------------------------------------------------------------

import re as _re

_CONSTRAINT_PATTERNS: list[tuple[str, str]] = [
    (_re.compile(r"只看|只关心|只看一下|只关注"), "scope"),
    (_re.compile(r"仅限于|仅限|仅|只能|只要"), "scope"),
    (_re.compile(r"近\d+[个]?月|最近\d+[个]?月|过去\d+[个]?月"), "time_range"),
    (_re.compile(r"今年|本季度|本月|本周|今天|今日"), "time_range"),
    (_re.compile(r"华东|华南|华北|华中|西南|西北|东北"), "region"),
    (_re.compile(r"北京|上海|广州|深圳|杭州|成都|武汉"), "region"),
    (_re.compile(r"产品线|业务线|事业部|部门"), "department"),
    (_re.compile(r"[A-Z]+产品|[A-Z]+项目"), "product_line"),
]


def extract_constraints(text: str) -> list[tuple[str, str]]:
    """Extract user-declared constraints from query text via regex patterns.

    Returns list of (constraint_type, matched_text).
    """
    results: list[tuple[str, str]] = []
    for pattern, ctype in _CONSTRAINT_PATTERNS:
        for match in pattern.finditer(text):
            matched = match.group()
            # Avoid duplicates
            if not any(r[1] == matched for r in results):
                results.append((ctype, matched))
    return results


def _extract_query(ctx) -> str:
    """Extract the latest user query from context messages."""
    for msg in reversed(ctx.messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def _extract_chunks(ctx) -> list[dict]:
    """Extract chunks from search_knowledge, query_knowledge, rerank, or hybrid_search results."""
    for tool_name in ("search_knowledge", "query_knowledge", "rerank", "hybrid_search"):
        for tr in reversed(ctx.tool_results):
            if tr.get("tool") != tool_name:
                continue
            data = tr.get("data") or {}
            chunks = data.get("chunks")
            if chunks:
                for c in chunks:
                    if "doc_name" not in c and "title" in c:
                        c["doc_name"] = c["title"]
                return chunks
    return []


def _extract_answer(ctx) -> str:
    """Extract the answer text from generate_answer or query_knowledge result."""
    for tool_name in ("query_knowledge", "generate_answer"):
        result = _find_tool_result(ctx, tool_name)
        if result:
            data = result.get("data") or {}
            return data.get("answer") or ""
    return ""


# Tools whose input schema includes a "chunks" parameter.
_CHUNK_TOOLS = {"search_knowledge", "rerank", "permission_check", "generate_answer", "hallucination_check"}


def _inject_tool_args_from_context(args: dict, ctx) -> None:
    """Fill missing 'chunks' arg from prior tool results in ctx.

    The LLM planner only sees tool summaries, not raw data, so it often
    passes empty args for data-carrying parameters.
    """
    if ctx is None:
        return
    existing_chunks = args.get("chunks")
    if not existing_chunks:
        ctx_chunks = _extract_chunks(ctx)
        if ctx_chunks:
            args["chunks"] = ctx_chunks


class FallbackPlanner:
    """Agent-aware fallback planner — replaces hardcoded _default_plan (B10).

    Each agent defines a ``fallback_plan_sequence`` in its ``AgentConfig``.
    The planner steps through the sequence, filling ``{query}`` and
    ``{chunks}`` placeholders from context.
    """

    def __init__(self, agent_config: AgentConfig):
        self._sequence = agent_config.fallback_plan_sequence or [
            {"type": "tool_call", "tool": "search_knowledge", "args": {"query": "{query}"}},
            {"type": "tool_call", "tool": "generate_answer", "args": {"query": "{query}"}},
            {"type": "final_answer"},
        ]

    def plan(self, ctx, step: int) -> PlanDecision:
        if step < len(self._sequence):
            tmpl = self._sequence[step]
        else:
            return PlanDecision(type="final_answer")

        if tmpl.get("type") == "final_answer":
            return PlanDecision(type="final_answer")

        args = dict(tmpl.get("args", {}))
        query = _extract_query(ctx)
        for k, v in args.items():
            if isinstance(v, str):
                args[k] = v.replace("{query}", query)
            if isinstance(v, str) and "{chunks}" in v:
                chunks_count = len(_extract_chunks(ctx))
                args[k] = v.replace("{chunks}", str(chunks_count))

        return PlanDecision(type="tool_call", tool=tmpl.get("tool", ""), args=args)


def _default_plan(ctx, step: int, agent_config: AgentConfig) -> PlanDecision:
    """Backward-compatible wrapper — delegates to FallbackPlanner."""
    return FallbackPlanner(agent_config).plan(ctx, step)
