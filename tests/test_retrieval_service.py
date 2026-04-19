"""
Unit tests for RetrievalService with a stubbed DB and embedding service.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.rag_agent.services import retrieval_service as retr_mod
from agents.rag_agent.services.retrieval_service import RetrievalService, RetrievedChunk


def _row(i: int, score: float = 0.8, content: str = "chunk"):
    return {
        "id": f"row-{i}",
        "document_id": f"doc-{i}",
        "chunk_index": 0,
        "source": f"/tmp/file-{i}.txt",
        "content": content,
        "metadata": {},
        "score": score,
    }


@pytest.fixture
def svc():
    service = RetrievalService.__new__(RetrievalService)
    from agents.rag_agent.config.settings import get_settings
    service._settings = get_settings()
    service._embed = MagicMock()
    service._embed.embed_query = AsyncMock(return_value=[0.01] * service._settings.gemini.embedding_dim)
    service._db = MagicMock()
    service._db.similarity_search = AsyncMock(return_value=[_row(0), _row(1)])
    service._db.hybrid_search = AsyncMock(return_value=[_row(0), _row(1)])
    service._db.entity_boosted_search = AsyncMock(return_value=[_row(0), _row(1)])
    # Fresh no-op cache.
    from types import SimpleNamespace
    from agents.rag_agent.utils.cache import Cache
    cache = Cache.__new__(Cache)
    cache._settings = SimpleNamespace(enabled=False, redis_url="", ttl_seconds=0)
    cache._redis = None
    service._cache = cache
    from agents.rag_agent.aml.query_expansion import QueryExpander
    from agents.rag_agent.aml.entity_extractor import EntityExtractor
    from agents.rag_agent.aml.risk_scoring import RiskScorer
    service._expander = QueryExpander()
    service._entity_extractor = EntityExtractor()
    service._risk_scorer = RiskScorer()
    return service


@pytest.mark.asyncio
async def test_retrieve_with_no_entities_uses_hybrid_path(svc):
    svc._settings.retrieval.hybrid_search = True
    result = await svc.retrieve("what is layering in AML?", top_k=2, use_aml_expansion=False)
    assert len(result) == 2
    svc._db.hybrid_search.assert_awaited()
    svc._db.similarity_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieve_with_entities_uses_entity_path(svc):
    svc._settings.retrieval.hybrid_search = True
    result = await svc.retrieve('Who owns "ACME Holdings"?', top_k=2, use_aml_expansion=True)
    assert len(result) == 2
    svc._db.entity_boosted_search.assert_awaited()


@pytest.mark.asyncio
async def test_retrieve_returns_typed_chunks(svc):
    result = await svc.retrieve("anything", top_k=2, use_aml_expansion=False)
    for r in result:
        assert isinstance(r, RetrievedChunk)
        assert r.score is not None
