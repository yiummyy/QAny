"""/api/v1/eval/* — 评估专用端点，暴露内部检索结果供外部评估工具使用."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import UserClaims, require_any_user
from app.knowledge.reranker import rerank
from app.tools.hybrid_search import hybrid_search
from app.tools.rewrite_query import rewrite_query

router = APIRouter(prefix="/api/v1/eval", tags=["eval"])


class RetrievalEvalRequest(BaseModel):
    question: str
    scene: str = "KnowledgeQA"
    index: str = ""


@router.post("/retrieval")
async def eval_retrieval(
    body: RetrievalEvalRequest,
    user_claims: UserClaims = Depends(require_any_user),
) -> dict:
    """返回原始检索结果（含 raw top-20 + rerank top-5），不经过 Agent Loop.

    供外部评估工具计算 MRR / NDCG / MAP 使用.
    """
    index = body.index or "qa_chunks"

    # Step 1: Query Rewrite (不使用 LLM 以保持确定性评估)
    rewrite_result = await rewrite_query(
        query=body.question,
        history="",
        user_claims=user_claims,
        provider_router=None,  # 无 LLM → 回退到原始 query
    )
    rewritten = body.question
    entities: list[str] = []
    if rewrite_result.status == "ok" and isinstance(rewrite_result.data, dict):
        rewritten = rewrite_result.data.get("rewritten", body.question)
        entities = rewrite_result.data.get("entities", [])

    # Step 2: Hybrid Search → raw top-20
    search_result = await hybrid_search(
        query=rewritten,
        top_k=20,
        user_claims=user_claims,
        index=index,
        entity_filters=entities,
    )

    raw_chunks = search_result.data if search_result.status == "ok" else []
    if not isinstance(raw_chunks, list):
        raw_chunks = []

    # Strip internal ES metadata
    raw_clean = [
        {
            "chunk_id": c.get("chunk_id") or c.get("_id", ""),
            "doc_id": c.get("doc_id", ""),
            "doc_name": c.get("doc_name", ""),
            "content": (c.get("content", "") or "")[:300],
            "section": c.get("section", ""),
            "rrf_score": c.get("_rrf_score"),
            "bm25_score": c.get("_score"),
        }
        for c in raw_chunks
    ]

    # Step 3: Rerank → top-5
    reranked = await rerank(query=rewritten, chunks=raw_chunks, top_k=5)
    rerank_clean = [
        {
            "chunk_id": c.get("chunk_id") or c.get("_id", ""),
            "doc_id": c.get("doc_id", ""),
            "doc_name": c.get("doc_name", ""),
            "content": (c.get("content", "") or "")[:300],
            "section": c.get("section", ""),
            "rerank_score": c.get("rerank_score", 0),
        }
        for c in reranked
    ]

    return {
        "query": body.question,
        "rewritten": rewritten,
        "entities": entities,
        "index": index,
        "raw_top20": raw_clean,
        "rerank_top5": rerank_clean,
        "raw_count": len(raw_clean),
    }
