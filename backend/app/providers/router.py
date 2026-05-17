"""Provider Router — primary/fallback selection + degraded failover."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from app.providers.base import BaseLLMProvider, ChatMessage, StreamChunk

logger = logging.getLogger(__name__)


class ProviderRouter:
    """Routes LLM calls to primary provider with automatic fallback on failure."""

    def __init__(
        self,
        primary: BaseLLMProvider,
        fallback: BaseLLMProvider | None = None,
        timeout: float = 30.0,
        model_routing: dict[str, str] | None = None,
        stage_providers: dict[str, BaseLLMProvider] | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.timeout = timeout
        self.model_routing = model_routing or {}
        self.stage_providers = stage_providers or {}

    def get_provider_for_stage(self, stage: str) -> BaseLLMProvider:
        """Get provider configured for a specific stage, fallback to primary if not set."""
        if stage in self.stage_providers:
            return self.stage_providers[stage]

        routing_info = self.model_routing.get(stage)
        if not routing_info or not isinstance(routing_info, str):
            return self.primary

        # Validate that the routed model is compatible with the primary provider's base URL.
        # Silently choosing an incompatible model (e.g. qwen-plus on DeepSeek API) causes
        # 400 "Model Not Exist" errors downstream.
        routed_model: str = routing_info
        if _model_mismatch(self.primary.base_url, routed_model):
            logger.warning(
                "model_routing[%s]=%s incompatible with base_url=%s, using primary model=%s",
                stage, routed_model, getattr(self.primary, 'base_url', ''), self.primary.model,
            )
            return self.primary

        import copy
        provider_copy = copy.copy(self.primary)
        provider_copy.model = routed_model
        return provider_copy

    async def chat(self, messages: list[ChatMessage], stage: str | None = None, **kwargs: Any) -> str:
        provider = self.get_provider_for_stage(stage) if stage else self.primary
        try:
            return await asyncio.wait_for(
                provider.chat(messages, **kwargs), timeout=self.timeout
            )
        except (TimeoutError, Exception) as exc:
            logger.warning("Primary provider failed: %s, trying fallback", exc)
            if self.fallback:
                return await self.fallback.chat(messages, **kwargs)
            raise

    async def stream_chat(self, messages: list[ChatMessage], stage: str | None = None, **kwargs: Any) -> AsyncIterator[StreamChunk | str]:
        provider = self.get_provider_for_stage(stage) if stage else self.primary
        try:
            async for chunk in provider.stream_chat(messages, **kwargs):
                yield chunk
        except (TimeoutError, Exception) as exc:
            logger.warning("Primary stream failed: %s, trying fallback", exc)
            if self.fallback:
                async for chunk in self.fallback.stream_chat(messages, **kwargs):
                    yield chunk
            else:
                raise

    async def plan(self, messages: list[ChatMessage], tools_schema: list[dict[str, Any]], stage: str = "plan") -> dict[str, Any]:
        provider = self.get_provider_for_stage(stage)
        try:
            return await asyncio.wait_for(
                provider.plan(messages, tools_schema), timeout=self.timeout
            )
        except (TimeoutError, Exception) as exc:
            logger.warning("Plan provider failed (stage=%s): %s, trying fallback", stage, exc)
            if self.fallback:
                return await self.fallback.plan(messages, tools_schema)
            raise


# ---------------------------------------------------------------------------
# Provider / model compatibility
# ---------------------------------------------------------------------------

# Map base_url domain keywords to expected model name prefixes.
# When model_routing specifies a model whose prefix doesn't match the
# provider's base URL, we fall back to the primary model to avoid
# "Model Not Exist" 400 errors.
_MODEL_PREFIX_MAP: dict[str, list[str]] = {
    "deepseek": ["deepseek-"],
    "dashscope": ["qwen-", "qwq-", "qwen2-", "deepseek-"],
    "openai": ["gpt-", "o1-", "o3-", "o4-"],
    "bigmodel": ["glm-", "chatglm-"],
}


def _model_mismatch(base_url: str, model: str) -> bool:
    """Return True if *model* looks incompatible with *base_url*.

    Only fires when there's a clear mismatch (e.g. qwen-plus on deepseek API).
    If the provider is unknown, returns False (allow it through).
    """
    if not base_url or not model:
        return False
    base_lower = base_url.lower()
    model_lower = model.lower()
    for keyword, prefixes in _MODEL_PREFIX_MAP.items():
        if keyword in base_lower:
            return not any(model_lower.startswith(p) for p in prefixes)
    # Unknown provider — don't guess
    return False
