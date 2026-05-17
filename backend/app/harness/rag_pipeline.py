"""Fixed RAG pipeline — rewrite → search → rerank → permission → generate."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.auth.claims import UserClaims
from app.harness.models import Event, EventType, ToolResult
from app.providers.router import ProviderRouter


@dataclass
class RAGPipelineConfig:
    """Per-agent RAG pipeline configuration."""

    es_index: str = "qa_chunks"
    top_k_search: int = 20
    top_k_rerank: int = 5
    rerank_enabled: bool = True
    rewrite_enabled: bool = True
    answer_template: str = "generate_answer"


class RAGPipeline:
    """Fixed RAG pipeline: rewrite → search → rerank → permission → generate.

    This is NOT agent-orchestrated. The pipeline is deterministic — if any step
    fails, it degrades gracefully and continues with what it has.
    """

    def __init__(self, config: RAGPipelineConfig) -> None:
        self.config = config

    async def run(
        self,
        query: str,
        user_claims: UserClaims,
        provider_router: ProviderRouter | None = None,
        history: str = "",
    ) -> tuple[ToolResult, list[Event]]:
        """Execute the full RAG pipeline.

        *history* is multi-turn conversation context for rewrite query
        coreference resolution (built from ctx.messages by agent_loop).

        Returns (final_result, progress_events) where progress_events can be
        yielded as SSE status frames.
        """
        events: list[Event] = []
        chunks: list[dict] = []
        rewritten_query = query
        intent = "其他"
        entities: list[str] = []

        # --- Step 1: Rewrite ---
        if self.config.rewrite_enabled and provider_router:
            events.append(
                Event(
                    type=EventType.STATUS,
                    data={"phase": "rewriting", "message": "正在分析问题..."},
                )
            )
            try:
                from app.tools.rewrite_query import rewrite_query

                result = await rewrite_query(
                    query=query,
                    history=history or "无历史对话",
                    user_claims=user_claims,
                    provider_router=provider_router,
                )
                if result.status == "ok" and result.data:
                    rewritten_query = result.data.get("rewritten", query)
                    intent = result.data.get("intent", "其他")
                    entities = result.data.get("entities", [])
                    if not isinstance(entities, list):
                        entities = []
            except Exception:
                pass

        # --- Step 2: Hybrid Search ---
        events.append(
            Event(
                type=EventType.STATUS,
                data={"phase": "searching", "message": "正在搜索知识库..."},
            )
        )
        try:
            from app.tools.hybrid_search import hybrid_search

            result = await hybrid_search(
                query=rewritten_query,
                top_k=self.config.top_k_search,
                user_claims=user_claims,
                index=self.config.es_index,
                entity_filters=entities if entities else None,
            )
            if result.status == "ok" and result.data:
                chunks = result.data.get("chunks", [])
        except Exception:
            chunks = []

        if not chunks:
            return (
                ToolResult(
                    status="degraded",
                    summary="未检索到相关文档",
                    data={"prompt": "", "chunks": [], "intent": intent},
                ),
                events,
            )

        # --- Step 3: Rerank ---
        if self.config.rerank_enabled and len(chunks) > self.config.top_k_rerank:
            events.append(
                Event(
                    type=EventType.STATUS,
                    data={"phase": "reranking", "message": "正在重排搜索结果..."},
                )
            )
            try:
                from app.tools.rerank import rerank_chunks

                result = await rerank_chunks(
                    query=rewritten_query,
                    chunks=chunks,
                    top_k=self.config.top_k_rerank,
                    user_claims=user_claims,
                )
                if result.status in ("ok", "degraded") and result.data:
                    chunks = result.data.get("chunks", chunks[: self.config.top_k_rerank])
            except Exception:
                chunks = chunks[: self.config.top_k_rerank]

        # --- Step 4: Permission Check ---
        events.append(
            Event(
                type=EventType.STATUS,
                data={"phase": "checking_permissions", "message": "正在检查访问权限..."},
            )
        )
        try:
            from app.tools.permission_check import permission_check

            result = await permission_check(chunks=chunks, user_claims=user_claims)
            if result.status in ("ok", "degraded") and result.data:
                chunks = result.data.get("chunks", chunks)
        except Exception:
            pass

        if not chunks:
            return (
                ToolResult(
                    status="degraded",
                    summary="权限过滤后无可用文档",
                    data={"prompt": "", "chunks": [], "intent": intent},
                ),
                events,
            )

        # --- Step 5: Generate Answer Prompt ---
        events.append(
            Event(
                type=EventType.STATUS,
                data={"phase": "generating", "message": "正在生成答案..."},
            )
        )
        try:
            from app.tools.generate_answer import generate_answer

            result = await generate_answer(
                query=rewritten_query,
                chunks=chunks,
                user_claims=user_claims,
                template_name=self.config.answer_template,
            )
        except Exception:
            result = ToolResult(
                status="error",
                summary="生成答案失败",
                data={"prompt": "", "chunks": chunks},
            )

        if result.data:
            result.data["intent"] = intent
            result.data["rewritten_query"] = rewritten_query
            result.data["entities"] = entities

        # Include intent in the summary so Agent plan() can see it
        if result.summary and intent != "其他":
            result.summary = f"{result.summary}，intent={intent}"

        return result, events

    @classmethod
    async def parallel_run(
        cls,
        indexes: list[str],
        query: str,
        user_claims: UserClaims,
        config: RAGPipelineConfig,
        provider_router: ProviderRouter | None = None,
        history: str = "",
    ) -> tuple[ToolResult, list[Event]]:
        """Run the RAG pipeline against multiple ES indexes in parallel.

        Rewrite is shared (called once). Search + rerank + permission_check run
        per-index concurrently.  Results are merged, deduped by chunk_id, and
        globally re-ranked by rerank_score before generate_answer.
        """
        events: list[Event] = []
        rewritten_query = query
        intent = "其他"
        entities: list[str] = []

        # --- Shared Step 1: Rewrite (once) ---
        if config.rewrite_enabled and provider_router:
            events.append(
                Event(
                    type=EventType.STATUS,
                    data={"phase": "rewriting", "message": "正在分析问题..."},
                )
            )
            try:
                from app.tools.rewrite_query import rewrite_query

                rewrite_result = await rewrite_query(
                    query=query,
                    history=history or "无历史对话",
                    user_claims=user_claims,
                    provider_router=provider_router,
                )
                if rewrite_result.status == "ok" and rewrite_result.data:
                    rewritten_query = rewrite_result.data.get("rewritten", query)
                    intent = rewrite_result.data.get("intent", "其他")
                    entities = rewrite_result.data.get("entities", [])
                    if not isinstance(entities, list):
                        entities = []
            except Exception:
                pass

        # --- Per-index Steps 2-4 (parallel) ---
        events.append(
            Event(
                type=EventType.STATUS,
                data={
                    "phase": "searching",
                    "message": f"正在并行搜索 {len(indexes)} 个知识库...",
                },
            )
        )

        async def _per_index_pipeline(index_name: str) -> list[dict]:
            """Run search → rerank → permission_check for a single index."""
            chunks: list[dict] = []

            # Search
            from app.tools.hybrid_search import hybrid_search

            result = await hybrid_search(
                query=rewritten_query,
                top_k=config.top_k_search,
                user_claims=user_claims,
                index=index_name,
                entity_filters=entities if entities else None,
            )
            if result.status != "ok" or not result.data:
                return []
            chunks = result.data.get("chunks", [])
            if not chunks:
                return []

            # Tag each chunk with its source index
            for c in chunks:
                c["_source_index"] = index_name

            # Rerank
            if config.rerank_enabled and len(chunks) > config.top_k_rerank:
                try:
                    from app.tools.rerank import rerank_chunks

                    rr_result = await rerank_chunks(
                        query=rewritten_query,
                        chunks=chunks,
                        top_k=config.top_k_rerank,
                        user_claims=user_claims,
                    )
                    if rr_result.status in ("ok", "degraded") and rr_result.data:
                        chunks = rr_result.data.get("chunks", chunks[: config.top_k_rerank])
                except Exception:
                    chunks = chunks[: config.top_k_rerank]

            # Permission Check
            try:
                from app.tools.permission_check import permission_check

                pc_result = await permission_check(chunks=chunks, user_claims=user_claims)
                if pc_result.status in ("ok", "degraded") and pc_result.data:
                    chunks = pc_result.data.get("chunks", chunks)
            except Exception:
                pass

            return chunks

        # Run all indexes in parallel
        all_chunk_lists = await asyncio.gather(
            *[_per_index_pipeline(idx) for idx in indexes]
        )

        # --- Merge: dedup (keep highest score) + global sort ---
        seen: dict[str, dict] = {}
        merged: list[dict] = []
        for chunk_list in all_chunk_lists:
            for c in chunk_list:
                chunk_id = c.get("chunk_id", "")
                if not chunk_id:
                    merged.append(c)
                    continue
                existing = seen.get(chunk_id)
                if existing is None:
                    seen[chunk_id] = c
                    merged.append(c)
                else:
                    new_score = float(c.get("rerank_score", c.get("_rrf_score", c.get("_score", 0))))
                    old_score = float(existing.get("rerank_score", existing.get("_rrf_score", existing.get("_score", 0))))
                    if new_score > old_score:
                        idx = next((i for i, m in enumerate(merged) if m.get("chunk_id") == chunk_id), None)
                        if idx is not None:
                            merged[idx] = c
                        seen[chunk_id] = c

        if not merged:
            return (
                ToolResult(
                    status="degraded",
                    summary="多库并行搜索未检索到相关文档",
                    data={"prompt": "", "chunks": [], "intent": intent},
                ),
                events,
            )

        # Sort by rerank_score descending (fallback to _rrf_score, _score)
        merged.sort(
            key=lambda c: float(c.get("rerank_score", c.get("_rrf_score", c.get("_score", 0)))),
            reverse=True,
        )

        # Take top-N (per-index top_k × number of indexes, capped)
        top_n = config.top_k_rerank * len(indexes)
        merged = merged[:top_n]

        events.append(
            Event(
                type=EventType.STATUS,
                data={
                    "phase": "reranking",
                    "message": f"合并 {len(indexes)} 个知识库结果，去重后共 {len(merged)} 条",
                },
            )
        )

        # --- Shared Step 5: Generate Answer ---
        events.append(
            Event(
                type=EventType.STATUS,
                data={"phase": "generating", "message": "正在生成答案..."},
            )
        )
        try:
            from app.tools.generate_answer import generate_answer

            gen_result = await generate_answer(
                query=rewritten_query,
                chunks=merged,
                user_claims=user_claims,
                template_name=config.answer_template,
            )
        except Exception:
            gen_result = ToolResult(
                status="error",
                summary="生成答案失败",
                data={"prompt": "", "chunks": merged},
            )

        if gen_result.data:
            gen_result.data["intent"] = intent
            gen_result.data["rewritten_query"] = rewritten_query
            gen_result.data["entities"] = entities

        if gen_result.summary and intent != "其他":
            gen_result.summary = f"{gen_result.summary}，intent={intent}"

        source_indexes = [c.get("_source_index") for c in merged if c.get("_source_index")]
        unique_sources = list(dict.fromkeys(source_indexes))
        if unique_sources:
            gen_result.summary = f"{gen_result.summary}，来源库={','.join(unique_sources)}"

        return gen_result, events
