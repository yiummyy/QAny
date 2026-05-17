import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_cross_encoder():
    mock_model = MagicMock()
    import numpy as np
    mock_model.predict.return_value = np.array([0.9, 0.3, 0.7] + [0.1] * 7)
    mock_ce = MagicMock(return_value=mock_model)
    if "sentence_transformers" not in sys.modules:
        sys.modules["sentence_transformers"] = MagicMock()
    sys.modules["sentence_transformers"].CrossEncoder = mock_ce
    return mock_ce


@pytest.fixture(autouse=True)
def reset_reranker():
    import app.knowledge.reranker as mod

    mod._reranker = None
    yield
    mod._reranker = None


def test_get_reranker_lazy_load(mock_cross_encoder):
    from app.knowledge.reranker import get_reranker

    m1 = get_reranker()
    m2 = get_reranker()
    assert m1 is m2


def test_rerank_sorts_by_score(mock_cross_encoder):
    import asyncio

    from app.knowledge.reranker import rerank

    chunks = [
        {"content": "A", "idx": 0},
        {"content": "B", "idx": 1},
        {"content": "C", "idx": 2},
    ]
    result = asyncio.run(rerank("query", chunks, top_k=2))
    assert len(result) == 2
    assert result[0]["idx"] == 0
    assert result[0]["rerank_score"] == 0.9


def test_rerank_empty_list(mock_cross_encoder):
    import asyncio

    from app.knowledge.reranker import rerank

    result = asyncio.run(rerank("query", []))
    assert result == []


def test_rerank_top_k_truncation(mock_cross_encoder):
    import asyncio

    from app.knowledge.reranker import rerank

    chunks = [{"content": str(i)} for i in range(10)]
    result = asyncio.run(rerank("q", chunks, top_k=3))
    assert len(result) == 3
