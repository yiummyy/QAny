import sys
from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.fixture
def mock_sentence_transformers():
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32
    )
    mock_st = MagicMock(return_value=mock_model)
    sys.modules["sentence_transformers"] = MagicMock()
    sys.modules["sentence_transformers"].SentenceTransformer = mock_st
    return mock_st


@pytest.fixture(autouse=True)
def reset_embedder():
    import app.knowledge.embedder as mod

    mod._embedder = None
    yield
    mod._embedder = None


def test_get_embedder_lazy_load(mock_sentence_transformers):
    from app.knowledge.embedder import get_embedder

    model1 = get_embedder()
    model2 = get_embedder()
    assert model1 is model2


def test_encode_returns_correct_shape(mock_sentence_transformers):
    import asyncio

    from app.knowledge.embedder import encode

    result = asyncio.run(encode(["text1", "text2"]))
    assert result.shape == (2, 3)
    assert result.dtype == np.float32


def test_encode_empty_list(mock_sentence_transformers):
    import asyncio

    from app.knowledge.embedder import encode

    result = asyncio.run(encode([]))
    assert result.shape == (0,)
    assert result.dtype == np.float32


def test_encode_query_returns_1d(mock_sentence_transformers):
    import asyncio

    from app.knowledge.embedder import encode_query

    result = asyncio.run(encode_query("test query"))
    assert result.ndim == 1
