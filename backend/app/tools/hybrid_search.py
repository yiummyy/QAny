"""Tool: Hybrid search — BM25 + KNN → RRF fusion + RBAC filter."""

from __future__ import annotations

import asyncio
import math
from typing import Any

from pydantic import BaseModel

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register
from app.knowledge.embedder import encode_query
from app.rbac.filter_builder import build_es_filter
from app.storage.es_client import get_es

INDEX_NAME = "qa_chunks"
RRF_K = 60


class HybridSearchInput(BaseModel):
    query: str
    top_k: int = 20


def _build_entity_clauses(entities: list[str] | None) -> list[dict]:
    """Build multi_match clauses for entity-driven search boosting.

    Each entity is matched against content, section (weighted higher),
    and doc_name.  Uses *must* (scoring boost) rather than *filter* so
    that results are not eliminated when an entity doesn't match.
    """
    if not entities:
        return []
    return [
        {
            "multi_match": {
                "query": entity,
                "fields": ["content^1", "section^3", "doc_name^2"],
            }
        }
        for entity in entities
    ]


def _build_tag_clauses(tags: list[str] | None) -> list[dict]:
    """Build should clauses for predicted tag boosting.

    Each predicted tag is matched against the document tags field with a boost.
    Using *should* (not *must*) so results without matching tags are not eliminated.
    """
    if not tags:
        return []
    return [
        {"match": {"tags": {"query": tag, "boost": 3.0}}}
        for tag in tags
    ]


@register("hybrid_search", HybridSearchInput)
async def hybrid_search(
    query: str,
    top_k: int = 20,
    *,
    user_claims: UserClaims,
    index: str = "qa_chunks",
    entity_filters: list[str] | None = None,
    predicted_tags: list[str] | None = None,
) -> ToolResult:
    """BM25 + KNN parallel search → RRF fusion with RBAC filter.

    When *entity_filters* are provided (from rewrite_query entities), each
    entity is injected as a multi_match clause to boost documents mentioning
    those entities in section/doc_name/content.

    When *predicted_tags* are provided, they are added as should clauses
    to boost chunks with matching document tags.
    """
    es_filter = build_es_filter(user_claims)
    query_vec = await encode_query(query)
    entity_clauses = _build_entity_clauses(entity_filters)
    tag_clauses = _build_tag_clauses(predicted_tags)

    es = get_es()

    bm25_must: list[dict] = [{"match": {"content": query}}]
    bm25_must.extend(entity_clauses)
    bm25_body: dict[str, Any] = {
        "query": {
            "bool": {
                "must": bm25_must,
                "should": tag_clauses,
                "filter": es_filter,
            }
        },
        "size": top_k * 2,
        "_source": ["chunk_id", "doc_id", "doc_name", "content", "chunk_index", "permission_level", "department", "source_type", "section", "content_type", "page", "tags"],
    }

    knn_body: dict[str, Any] = {
        "knn": {
            "field": "embedding",
            "query_vector": query_vec.tolist(),
            "k": top_k * 2,
            "num_candidates": top_k * 4,
            "filter": es_filter,
        },
        "size": top_k * 2,
        "_source": ["chunk_id", "doc_id", "doc_name", "content", "chunk_index", "permission_level", "department", "source_type", "section", "content_type", "page", "tags"],
    }

    try:
        bm25_task = es.search(index=index, body=bm25_body)
        knn_task = es.search(index=index, body=knn_body)
        bm25_resp, knn_resp = await asyncio.gather(bm25_task, knn_task)

        bm25_hits = _extract_hits(bm25_resp)
        knn_hits = _extract_hits(knn_resp)

        fused = _rrf_fuse(bm25_hits, knn_hits, k=RRF_K)
        fused = fused[:top_k]

        return ToolResult(
            status="ok",
            summary=f"召回 {len(fused)} 条",
            data={"chunks": fused},
        )
    except Exception as exc:
        return ToolResult(
            status="error",
            summary=f"检索失败: {exc}",
            data={"chunks": []},
        )


def _extract_hits(response: dict) -> list[dict[str, Any]]:
    hits = []
    for hit in response.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        source["_score"] = hit.get("_score", 0)
        source["_id"] = hit.get("_id", "")
        hits.append(source)
    return hits


def _rrf_fuse(
    list_a: list[dict],
    list_b: list[dict],
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion: merge two ranked lists into one."""
    scores: dict[str, tuple[float, dict]] = {}

    for rank, item in enumerate(list_a):
        chunk_id = item.get("_id", str(rank))
        rrf_score = 1.0 / (k + rank + 1)
        scores[chunk_id] = (rrf_score, item)

    for rank, item in enumerate(list_b):
        chunk_id = item.get("_id", str(rank))
        rrf_score = 1.0 / (k + rank + 1)
        if chunk_id in scores:
            scores[chunk_id] = (scores[chunk_id][0] + rrf_score, scores[chunk_id][1])
        else:
            scores[chunk_id] = (rrf_score, item)

    fused = sorted(scores.values(), key=lambda x: x[0], reverse=True)
    result = []
    for score, item in fused:
        result.append({**item, "_rrf_score": score})
    return result
