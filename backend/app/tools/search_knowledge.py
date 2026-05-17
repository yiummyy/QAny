"""Tool: search_knowledge — RAG pipeline steps 1-4 with entity-aware index routing."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from pydantic import BaseModel

from app.auth.claims import UserClaims
from app.harness.agent_config import AgentConfig
from app.harness.models import ToolResult
from app.harness.tool_registry import register_shared
from app.providers.router import ProviderRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entity-aware index routing
# ---------------------------------------------------------------------------

ENTITY_INDEX_HINTS: list[tuple[str, list[str]]] = [
    (r"逆变器|逆变|光伏组件|风机|变流器|升压|SVG|汇流箱|箱变|电站|并网|直流|交流侧|直流侧|过压|过载|绝缘",
     ["ops_knowledge"]),
    (r"OA|报销|请假|考勤|审批|入职|离职|打印机|网络故障|VPN|账号|密码重置|IT支持|工位|门禁|会议室",
     ["ticket_knowledge"]),
    (r"报价|价格|方案|定价|竞品|客户案例|营销|小红书|抖音|流量|转化率|话术|成功案例|获客|投放|ROI",
     ["sales_knowledge"]),
    (r"故障代码|报错|E\d{3,4}|告警|异常停机|跳闸|短路|过流",
     ["ops_knowledge", "ticket_knowledge"]),
]

INTENT_INDEX_BOOST: dict[str, list[str]] = {
    "故障排查": ["ticket_knowledge"],
}


def _route_indexes(
    intent: str,
    entities: list[str],
    default_index: str,
    available_indexes: list[str],
) -> list[str]:
    """Determine which ES indexes to search based on intent + entities.

    Returns a list of 1-2 indexes. Always includes the default index as fallback.
    """
    indexes: set[str] = set()

    search_text = " ".join(entities) if entities else ""
    for pattern, idxs in ENTITY_INDEX_HINTS:
        if re.search(pattern, search_text, re.IGNORECASE):
            indexes.update(idxs)

    if intent in INTENT_INDEX_BOOST:
        indexes.update(INTENT_INDEX_BOOST[intent])

    indexes.add(default_index)

    valid = [i for i in indexes if i in available_indexes]
    return list(dict.fromkeys(valid)) or [default_index]


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------


class SearchKnowledgeInput(BaseModel):
    query: str
    index: str | list[str] | None = None
    top_k_search: int = 20
    top_k_rerank: int = 5


@register_shared("search_knowledge", SearchKnowledgeInput, timeout=30.0, max_retries=1)
async def search_knowledge(
    query: str,
    *,
    user_claims: UserClaims,
    agent_config: AgentConfig | None = None,
    provider_router: ProviderRouter | None = None,
    history: str = "",
    index: str | list[str] | None = None,
    top_k_search: int = 20,
    top_k_rerank: int = 5,
) -> ToolResult:
    """Execute RAG steps 1-4: rewrite → search → rerank → permission.

    Index selection is automatic based on intent + entities extracted during
    rewrite, unless the caller passes an explicit *index* override.
    """
    default_index = agent_config.es_index if agent_config else "qa_chunks"
    available_indexes = (
        getattr(agent_config, "available_indexes", [default_index])
        if agent_config
        else [default_index]
    )

    rewritten_query = query
    intent = "其他"
    entities: list[str] = []
    predicted_tags: list[str] = []
    rewrite_failed = False

    # ---- Step 1: Rewrite ----
    if provider_router:
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
                predicted_tags = rewrite_result.data.get("tags", [])
                if not isinstance(entities, list):
                    entities = []
                if not isinstance(predicted_tags, list):
                    predicted_tags = []
            elif rewrite_result.status == "degraded":
                rewrite_failed = True
                logger.warning("rewrite_query degraded: %s", rewrite_result.summary)
        except Exception as exc:
            rewrite_failed = True
            logger.warning("rewrite_query failed: %s", exc)

    # ---- Gate check: short-circuit chitchat / out-of-scope before expensive RAG steps ----
    from app.tools.intent_gate import check as gate_check

    gate_result = gate_check(
        query, intent, entities, predicted_tags,
        rewrite_failed=rewrite_failed,
        rewritten_query=rewritten_query,
    )
    if gate_result and gate_result.blocked:
        return ToolResult(
            status="chitchat",
            summary=f"意图门控: {gate_result.category}",
            data={
                "chunks": [],
                "intent": intent,
                "rewritten_query": rewritten_query,
                "entities": entities,
                "gate_category": gate_result.category,
                "gate_response": gate_result.response,
            },
        )

    # ---- Step 2: Resolve indexes (explicit override or automatic routing) ----
    if index is not None:
        if isinstance(index, str):
            target_indexes = [index] if index in available_indexes else [default_index]
        elif isinstance(index, list) and len(index) > 0:
            target_indexes = [i for i in index if i in available_indexes] or [default_index]
        else:
            target_indexes = [default_index]
    else:
        target_indexes = _route_indexes(intent, entities, default_index, available_indexes)

    # ---- Step 3: Search (single or parallel multi-index) ----
    raw_hit_count = 0
    from app.tools.hybrid_search import hybrid_search

    if len(target_indexes) == 1:
        search_result = await hybrid_search(
            query=rewritten_query,
            top_k=top_k_search,
            user_claims=user_claims,
            index=target_indexes[0],
            entity_filters=entities if entities else None,
            predicted_tags=predicted_tags if predicted_tags else None,
        )
        if search_result.status == "ok" and search_result.data:
            chunks = search_result.data.get("chunks", [])
        else:
            chunks = []
        raw_hit_count = len(chunks)
    else:
        # Parallel search across multiple indexes
        async def _search_one(idx: str) -> list[dict]:
            r = await hybrid_search(
                query=rewritten_query,
                top_k=top_k_search,
                user_claims=user_claims,
                index=idx,
                entity_filters=entities if entities else None,
                predicted_tags=predicted_tags if predicted_tags else None,
            )
            if r.status == "ok" and r.data:
                for c in r.data.get("chunks", []):
                    c["_source_index"] = idx
                return r.data.get("chunks", [])
            return []

        all_lists = await asyncio.gather(*[_search_one(idx) for idx in target_indexes])

        # Merge: dedup by chunk_id (keep highest score) + sort
        seen: dict[str, dict] = {}
        merged: list[dict] = []
        for chunk_list in all_lists:
            for c in chunk_list:
                cid = c.get("chunk_id", "") or c.get("_id", "")
                if not cid:
                    merged.append(c)
                    continue
                existing = seen.get(cid)
                if existing is None:
                    seen[cid] = c
                    merged.append(c)
                else:
                    new_score = float(c.get("rerank_score", c.get("_rrf_score", c.get("_score", 0))))
                    old_score = float(existing.get("rerank_score", existing.get("_rrf_score", existing.get("_score", 0))))
                    if new_score > old_score:
                        idx_pos = next((i for i, m in enumerate(merged) if m.get("chunk_id") == cid or m.get("_id") == cid), None)
                        if idx_pos is not None:
                            merged[idx_pos] = c
                        seen[cid] = c

        raw_hit_count = len(merged)
        merged.sort(
            key=lambda c: float(c.get("_rrf_score", c.get("_score", 0))),
            reverse=True,
        )
        chunks = merged[:top_k_search]

    if not chunks:
        return ToolResult(
            status="degraded",
            summary="未检索到相关文档",
            data={
                "chunks": [],
                "intent": intent,
                "rewritten_query": rewritten_query,
                "entities": entities,
                "diagnostics": {
                    "raw_hit_count": 0,
                    "rerank_top_score": 0.0,
                    "permission_filtered": 0,
                    "indexes_used": target_indexes,
                },
            },
        )

    # ---- Step 4: Rerank ----
    rerank_top_score = 0.0
    reranker_degraded = False
    if len(chunks) > top_k_rerank:
        try:
            from app.tools.rerank import rerank_chunks

            rr_result = await rerank_chunks(
                query=rewritten_query,
                chunks=chunks,
                top_k=top_k_rerank,
                user_claims=user_claims,
            )
            if rr_result.status in ("ok", "degraded") and rr_result.data:
                chunks = rr_result.data.get("chunks", chunks[:top_k_rerank])
            if rr_result.status == "degraded":
                reranker_degraded = True
        except Exception:
            chunks = chunks[:top_k_rerank]
            reranker_degraded = True

    # G2: When reranker degrades, assign a synthetic low score so the
    # generate_answer threshold gate still functions. Without this, chunks
    # missing rerank_score bypass the MIN_SCORE_THRESHOLD check entirely.
    if reranker_degraded and chunks:
        for c in chunks:
            if "rerank_score" not in c:
                c["rerank_score"] = 0.35  # below MIN_SCORE_THRESHOLD (0.4)

    if chunks:
        scores = [float(c.get("rerank_score", 0)) for c in chunks if "rerank_score" in c]
        rerank_top_score = max(scores) if scores else 0.0

    # ---- Step 5: Permission Check ----
    before_pc = len(chunks)
    try:
        from app.tools.permission_check import permission_check

        pc_result = await permission_check(chunks=chunks, user_claims=user_claims)
        if pc_result.status in ("ok", "degraded") and pc_result.data:
            chunks = pc_result.data.get("chunks", chunks)
    except Exception:
        pass
    permission_filtered = before_pc - len(chunks)

    if not chunks:
        return ToolResult(
            status="degraded",
            summary="权限过滤后无可用文档",
            data={
                "chunks": [],
                "intent": intent,
                "rewritten_query": rewritten_query,
                "entities": entities,
                "diagnostics": {
                    "raw_hit_count": raw_hit_count,
                    "rerank_top_score": rerank_top_score,
                    "permission_filtered": permission_filtered,
                    "indexes_used": target_indexes,
                },
            },
        )

    # ---- Build result ----
    indexes_label = ",".join(target_indexes)
    summary = (
        f"意图={intent}，路由至{indexes_label} → 召回{raw_hit_count}条"
        f" → 重排{len(chunks)}条(最高分{rerank_top_score:.2f})"
    )
    if permission_filtered:
        summary += f" → 权限过滤{permission_filtered}条"

    return ToolResult(
        status="ok",
        summary=summary,
        data={
            "chunks": chunks,
            "intent": intent,
            "rewritten_query": rewritten_query,
            "entities": entities,
            "diagnostics": {
                "raw_hit_count": raw_hit_count,
                "rerank_top_score": rerank_top_score,
                "permission_filtered": permission_filtered,
                "indexes_used": target_indexes,
            },
        },
    )
