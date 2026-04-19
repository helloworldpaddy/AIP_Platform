"""
Unit tests for EmbeddingService.

We stub the underlying google-genai client so tests do not require a
network connection or API key.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agents.rag_agent.services import embedding_service as emb_mod
from agents.rag_agent.services.embedding_service import EmbeddingService


class _FakeEmbedding:
    def __init__(self, values):
        self.values = values


def _fake_response(n, dim):
    return SimpleNamespace(embeddings=[_FakeEmbedding([0.01 * i] * dim) for i in range(n)])


@pytest.fixture
def service(monkeypatch):
    svc = EmbeddingService.__new__(EmbeddingService)
    from agents.rag_agent.config.settings import get_settings
    svc._settings = get_settings().gemini
    from agents.rag_agent.utils.cache import Cache
    # Disable cache regardless of env config.
    noop_cache = Cache.__new__(Cache)
    noop_cache._settings = SimpleNamespace(enabled=False, redis_url="", ttl_seconds=0)
    noop_cache._redis = None
    svc._cache = noop_cache
    svc._client = MagicMock()
    return svc


@pytest.mark.asyncio
async def test_embed_query_returns_single_vector(service):
    dim = service.dim
    service._client.models.embed_content.return_value = _fake_response(1, dim)
    vec = await service.embed_query("hello")
    assert len(vec) == dim
    service._client.models.embed_content.assert_called_once()


@pytest.mark.asyncio
async def test_embed_documents_batches(service, monkeypatch):
    dim = service.dim
    # Force small batch size to check batching.
    service._settings = service._settings.model_copy(update={"embedding_batch_size": 2})

    call_count = {"n": 0}

    def _embed(*, model, contents, config):
        call_count["n"] += 1
        return _fake_response(len(contents), dim)

    service._client.models.embed_content.side_effect = _embed

    vectors = await service.embed_documents(["a", "b", "c", "d", "e"])
    assert len(vectors) == 5
    # 5 items with batch size 2 → 3 API calls
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_dim_mismatch_raises(service):
    # Return a 10-dim vector when we expect `service.dim`.
    service._client.models.embed_content.return_value = _fake_response(1, 10)
    with pytest.raises(ValueError):
        await service.embed_query("bad")
