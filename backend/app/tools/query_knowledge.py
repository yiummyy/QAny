"""Tool: query_knowledge — atomic RAG pipeline exposed to Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.auth.claims import UserClaims
from app.harness.agent_config import AgentConfig
from app.harness.models import ToolResult
from app.harness.rag_pipeline import RAGPipeline, RAGPipelineConfig
from app.harness.tool_registry import register_shared
from app.providers.router import ProviderRouter


class QueryKnowledgeInput(BaseModel):
    query: str
    index: str | list[str] | None = None
    # Schema description for LLM function-calling:
    # index: 可选。指定目标知识库索引名。
    #   qa_chunks(制度/流程/产品) | ticket_knowledge(工单/SOP/FAQ)
    #   | sales_knowledge(营销/报价) | ops_knowledge(运维/监控)
    #   不传使用默认库。传列表则并行搜索多个库。


@register_shared("query_knowledge", QueryKnowledgeInput)
async def query_knowledge(
    query: str,
    *,
    user_claims: UserClaims,
    agent_config: AgentConfig | None = None,
    provider_router: ProviderRouter | None = None,
    history: str = "",
    index: str | list[str] | None = None,
) -> ToolResult:
    """Fixed RAG pipeline: rewrite → search → rerank → permission → generate.

    *history* is multi-turn conversation context injected by agent_loop.
    *index* optionally overrides the default ES index from AgentConfig.
    The pipeline is deterministic — the Agent only decides WHETHER to call this
    tool and what to do with the result. Internal steps are not Agent-visible.
    """
    if agent_config is None:
        config = RAGPipelineConfig()
    else:
        config = RAGPipelineConfig(
            es_index=agent_config.es_index,
            top_k_search=agent_config.rag_top_k_search,
            top_k_rerank=agent_config.rag_top_k_rerank,
            rerank_enabled=agent_config.rag_rerank_enabled,
            rewrite_enabled=agent_config.rag_rewrite_enabled,
            answer_template=agent_config.answer_template,
        )

    # Dispatch to parallel_run when searching multiple indexes
    indexes = _resolve_indexes(index, agent_config)
    if len(indexes) > 1:
        result, _events = await RAGPipeline.parallel_run(
            indexes=indexes,
            query=query,
            user_claims=user_claims,
            config=config,
            provider_router=provider_router,
            history=history,
        )
    else:
        config.es_index = indexes[0]
        pipeline = RAGPipeline(config)
        result, _events = await pipeline.run(query, user_claims, provider_router, history=history)
    return result


def _resolve_indexes(
    index: str | list[str] | None,
    agent_config: AgentConfig | None,
) -> list[str]:
    """Resolve the effective ES index(es) for this query_knowledge call.

    - None → [agent_config.es_index] (default, backward compatible)
    - str → validate against available_indexes, use if valid, else [fallback]
    - list → filter against available_indexes, dedup, take all valid
    """
    if agent_config is None:
        default = "qa_chunks"
        available = [default]
    else:
        default = agent_config.es_index
        available = getattr(agent_config, "available_indexes", [default])

    if index is None:
        return [default]

    if isinstance(index, str):
        return [index] if index in available else [default]

    if isinstance(index, list) and len(index) > 0:
        valid = [idx for idx in index if idx in available]
        if valid:
            # Dedup preserving order
            return list(dict.fromkeys(valid))
    return [default]
