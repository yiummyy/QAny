"""Tool: Query rewriting + intent + entity extraction via LLM."""

from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register
from app.prompts.renderer import render
from app.providers.router import ProviderRouter


class RewriteQueryInput(BaseModel):
    query: str
    history: str = ""


@register("rewrite_query", RewriteQueryInput, max_retries=1)
async def rewrite_query(
    query: str,
    history: str = "",
    *,
    user_claims: UserClaims,
    provider_router: ProviderRouter | None = None,
) -> ToolResult:
    """Rewrite query with coreference resolution, intent identification, entity extraction, and tag prediction."""
    from app.knowledge.tag_registry import ALL_TAGS

    taggable = "\n".join(f"- {t}" for t in ALL_TAGS)
    prompt = render("rewrite_query", query=query, history=history or "无历史对话", taggable=taggable)

    try:
        if not provider_router:
            raise ValueError("ProviderRouter not injected")

        messages = [{"role": "user", "content": prompt}]
        result = await asyncio.wait_for(
            provider_router.chat(messages, stage="intent_recognition"),
            timeout=5.0,
        )

        parsed = json.loads(result)
        rewritten = parsed.get("rewritten", query)
        intent = parsed.get("intent", "其他")
        entities = parsed.get("entities", [])
        raw_tags = parsed.get("tags", [])
        on_tags = [t for t in raw_tags if isinstance(t, str) and t in ALL_TAGS]

        return ToolResult(
            status="ok",
            summary=f"意图={intent}，实体={entities}，标签={on_tags}",
            data={"rewritten": rewritten, "intent": intent, "entities": entities, "tags": on_tags},
        )
    except Exception as exc:
        return ToolResult(
            status="degraded",
            summary=f"查询改写失败，使用原始查询: {exc}",
            data={"rewritten": query, "intent": "其他", "entities": []},
        )
