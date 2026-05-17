from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)
_reranker: CrossEncoder | None = None  # type: ignore[type-arg]


def get_reranker() -> CrossEncoder:  # type: ignore[type-arg]
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        settings = get_settings()
        logger.info("Loading reranker model %s", settings.reranker_model)
        _reranker = CrossEncoder(
            settings.reranker_model,
            max_length=512,
            device=settings.embedding_device,
        )
    return _reranker


async def rerank(
    query: str,
    chunks: list[dict],
    top_k: int | None = None,
) -> list[dict]:
    if not chunks:
        return []

    settings = get_settings()
    top_k = top_k or settings.reranker_top_k
    model = get_reranker()
    pairs = [(query, c["content"]) for c in chunks]
    loop = asyncio.get_event_loop()
    scores = await loop.run_in_executor(None, lambda: model.predict(pairs).tolist())

    ranked = list(zip(chunks, scores, strict=False))
    ranked.sort(key=lambda x: x[1], reverse=True)
    result = []
    for c, s in ranked[:top_k]:
        result.append({**c, "rerank_score": float(s)})
    return result
