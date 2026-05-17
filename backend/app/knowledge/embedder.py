from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import numpy as np

from app.config import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)
_embedder: SentenceTransformer | None = None  # type: ignore[type-arg]


def get_embedder() -> SentenceTransformer:  # type: ignore[type-arg]
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        logger.info("Loading embedding model %s", settings.embedding_model)
        _embedder = SentenceTransformer(
            settings.embedding_model,
            device=settings.embedding_device,
        )
    return _embedder


async def encode(
    texts: list[str],
    batch_size: int = 32,
    normalize: bool = True,
) -> np.ndarray:
    """Encode texts to (N, 1024) L2-normalized embeddings."""
    if not texts:
        return np.array([], dtype=np.float32)
    
    def _do_encode():
        model = get_embedder()
        return model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_encode)


async def encode_query(query: str) -> np.ndarray:
    """Encode a single query to (1024,) L2-normalized embedding."""
    result = await encode([query])
    return result[0]
