"""检索质量评估 — MRR@K / NDCG@K / MAP@K / Recall@K.

支持两种模式:
  direct — 直接导入 backend 模块调用 hybrid_search + rerank（需在项目根运行）
  api    — 调用 backend /api/v1/eval/retrieval 端点（需后端运行）

所有指标公式参考 TREC / MS MARCO 标准.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval.dataset import EvalItemV2


def _add_backend_to_path() -> None:
    """确保 backend/ 在 sys.path 中以便直接导入."""
    backend = str(Path(__file__).resolve().parent.parent / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)


# ── 核心指标计算（纯函数，无外部依赖）───────────────────────────


def dcg_at_k(scores: list[float], k: int) -> float:
    """Discounted Cumulative Gain @ K."""
    return sum(
        rel / math.log2(rank + 2)  # rank 0-indexed → log2(rank+2) = log2(i+1) where i≥1
        for rank, rel in enumerate(scores[:k])
    )


def compute_mrr(
    ranked_ids: list[str],
    relevance: dict[str, int],
    k: int = 10,
    min_rel: int = 2,
) -> float:
    """MRR@K: 第一个相关文档排位的倒数.

    Args:
        ranked_ids: 按分数降序排列的 chunk/doc ID 列表
        relevance: chunk_id → relevance_score (0-3)
        k: 截断位
        min_rel: 视为"相关"的最低分数
    """
    for rank, cid in enumerate(ranked_ids[:k], start=1):
        if relevance.get(cid, 0) >= min_rel:
            return 1.0 / rank
    return 0.0


def compute_ndcg(
    ranked_ids: list[str],
    relevance: dict[str, int],
    k: int = 10,
) -> float:
    """NDCG@K: 归一化折损累积增益.

    IDCG 按 relevance 降序的理想排序计算.
    """
    rels = [relevance.get(cid, 0) for cid in ranked_ids[:k]]
    dcg = dcg_at_k(rels, k)

    ideal_rels = sorted(relevance.values(), reverse=True)[:k]
    idcg = dcg_at_k(ideal_rels, k)

    return dcg / idcg if idcg > 0 else 0.0


def compute_map(
    ranked_ids: list[str],
    relevance: dict[str, int],
    k: int = 5,
    min_rel: int = 2,
) -> float:
    """MAP@K: Mean Average Precision.

    对每个相关文档位置计算 Precision，取平均.
    """
    relevant_count = 0
    precision_sum = 0.0
    for rank, cid in enumerate(ranked_ids[:k], start=1):
        if relevance.get(cid, 0) >= min_rel:
            relevant_count += 1
            precision_sum += relevant_count / rank
    return precision_sum / max(relevant_count, 1)


def compute_recall_at_k(
    ranked_ids: list[str],
    relevance: dict[str, int],
    k: int = 10,
    min_rel: int = 2,
) -> float:
    """Recall@K: Top-K 中命中的相关文档占全部相关文档的比例."""
    total_relevant = sum(1 for v in relevance.values() if v >= min_rel)
    if total_relevant == 0:
        return 0.0
    hit = sum(1 for cid in ranked_ids[:k] if relevance.get(cid, 0) >= min_rel)
    return hit / total_relevant


# ── 评估器 ───────────────────────────────────────────


@dataclass
class RetrievalPerQuery:
    """单条查询的检索评估结果."""

    item_id: str
    raw_top20_ids: list[str] = field(default_factory=list)
    rerank_top5_ids: list[str] = field(default_factory=list)
    mrr_raw_10: float = 0.0
    mrr_rerank_5: float = 0.0
    ndcg_raw_10: float = 0.0
    ndcg_rerank_5: float = 0.0
    map_raw_10: float = 0.0
    map_rerank_5: float = 0.0
    recall_raw_10: float = 0.0
    recall_rerank_5: float = 0.0
    error: str = ""


@dataclass
class RetrievalReport:
    """检索评估汇总报告."""

    per_query: list[RetrievalPerQuery] = field(default_factory=list)
    mrr_raw_10_avg: float = 0.0
    mrr_rerank_5_avg: float = 0.0
    ndcg_raw_10_avg: float = 0.0
    ndcg_rerank_5_avg: float = 0.0
    map_raw_10_avg: float = 0.0
    map_rerank_5_avg: float = 0.0
    recall_raw_10_avg: float = 0.0
    recall_rerank_5_avg: float = 0.0
    total_queries: int = 0
    errors: int = 0


class RetrievalEvaluator:
    """检索评估器 — 封装 direct/api 两种模式的检索调用."""

    def __init__(self, mode: str = "direct", base_url: str = "http://localhost:8000"):
        self.mode = mode
        self.base_url = base_url.rstrip("/")

    async def search(self, item: EvalItemV2) -> tuple[list[str], list[str], str]:
        """执行检索，返回 (raw_top20_ids, rerank_top5_ids, error)."""
        if self.mode == "direct":
            return await self._search_direct(item)
        return await self._search_api(item)

    async def _search_direct(
        self, item: EvalItemV2
    ) -> tuple[list[str], list[str], str]:
        """直接调用 backend 模块（绕过 HTTP，拿到完整的 raw + rerank 结果）."""
        _add_backend_to_path()
        try:
            from app.auth.claims import UserClaims
            from app.knowledge.reranker import rerank
            from app.tools.hybrid_search import hybrid_search
            from app.tools.rewrite_query import rewrite_query
        except ImportError as exc:
            return [], [], f"import_error: {exc}"

        user = UserClaims(
            sub="eval_user",
            username="eval",
            role="admin",
            pl=3,
            department="",
        )

        try:
            # Step 1: Query Rewrite
            rewrite_result = await rewrite_query(
                query=item.question,
                history="",
                user_claims=user,
                provider_router=None,
            )
            rewritten = item.question
            entities: list[str] = []
            if rewrite_result.status == "ok" and isinstance(rewrite_result.data, dict):
                rewritten = rewrite_result.data.get("rewritten", item.question)
                entities = rewrite_result.data.get("entities", [])

            # Step 2: Hybrid Search → raw top-20
            index = item.index or "qa_chunks"
            search_result = await hybrid_search(
                query=rewritten,
                top_k=20,
                user_claims=user,
                index=index,
                entity_filters=entities,
            )
            raw_chunks = search_result.data if search_result.status == "ok" else []

            # Step 3: Rerank → top-5
            reranked = await rerank(query=rewritten, chunks=raw_chunks, top_k=5)

            def _chunk_id(c: dict) -> str:
                return c.get("chunk_id") or c.get("_id", "")

            raw_ids = [_chunk_id(c) for c in (raw_chunks or [])]
            rerank_ids = [_chunk_id(c) for c in reranked]
            return raw_ids, rerank_ids, ""

        except Exception as exc:
            return [], [], str(exc)[:200]

    async def _search_api(
        self, item: EvalItemV2
    ) -> tuple[list[str], list[str], str]:
        """通过 HTTP API 调用后端 eval 端点."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                resp = await client.post(
                    f"{self.base_url}/api/v1/eval/retrieval",
                    json={
                        "question": item.question,
                        "scene": item.scene,
                        "index": item.index or "",
                    },
                )
                if resp.status_code != 200:
                    return [], [], f"HTTP {resp.status_code}"
                data = resp.json()
                raw = data.get("raw_top20", [])
                rerank = data.get("rerank_top5", [])
                raw_ids = [c.get("chunk_id", "") for c in raw]
                rerank_ids = [c.get("chunk_id", "") for c in rerank]
                return raw_ids, rerank_ids, ""
        except Exception as exc:
            return [], [], str(exc)[:200]

    async def evaluate(self, items: list[EvalItemV2]) -> RetrievalReport:
        """批量评估检索质量."""
        report = RetrievalReport(total_queries=len(items))

        for item in items:
            pq = RetrievalPerQuery(item_id=item.id)
            raw_ids, rerank_ids, error = await self.search(item)

            if error:
                pq.error = error
                report.errors += 1
                report.per_query.append(pq)
                continue

            pq.raw_top20_ids = raw_ids
            pq.rerank_top5_ids = rerank_ids

            rel = item.relevance_judgments
            if rel:
                # Raw（rerank 前）metrics @10
                pq.mrr_raw_10 = compute_mrr(raw_ids, rel, k=10)
                pq.ndcg_raw_10 = compute_ndcg(raw_ids, rel, k=10)
                pq.map_raw_10 = compute_map(raw_ids, rel, k=10)
                pq.recall_raw_10 = compute_recall_at_k(raw_ids, rel, k=10)

                # Rerank 后 metrics @5
                pq.mrr_rerank_5 = compute_mrr(rerank_ids, rel, k=5)
                pq.ndcg_rerank_5 = compute_ndcg(rerank_ids, rel, k=5)
                pq.map_rerank_5 = compute_map(rerank_ids, rel, k=5)
                pq.recall_rerank_5 = compute_recall_at_k(rerank_ids, rel, k=5)

            report.per_query.append(pq)

        # 汇总均值
        valid = [pq for pq in report.per_query if not pq.error and pq.mrr_raw_10 >= 0]
        n = len(valid) or 1
        report.mrr_raw_10_avg = sum(pq.mrr_raw_10 for pq in valid) / n
        report.mrr_rerank_5_avg = sum(pq.mrr_rerank_5 for pq in valid) / n
        report.ndcg_raw_10_avg = sum(pq.ndcg_raw_10 for pq in valid) / n
        report.ndcg_rerank_5_avg = sum(pq.ndcg_rerank_5 for pq in valid) / n
        report.map_raw_10_avg = sum(pq.map_raw_10 for pq in valid) / n
        report.map_rerank_5_avg = sum(pq.map_rerank_5 for pq in valid) / n
        report.recall_raw_10_avg = sum(pq.recall_raw_10 for pq in valid) / n
        report.recall_rerank_5_avg = sum(pq.recall_rerank_5 for pq in valid) / n

        return report


# ── 便捷函数 ─────────────────────────────────────────


async def run_retrieval_eval(
    eval_set_path: str,
    mode: str = "direct",
    base_url: str = "http://localhost:8000",
) -> RetrievalReport:
    """一键运行检索评估."""
    from eval.dataset import load_eval_set

    items = load_eval_set(eval_set_path)
    evaluator = RetrievalEvaluator(mode=mode, base_url=base_url)
    return await evaluator.evaluate(items)
