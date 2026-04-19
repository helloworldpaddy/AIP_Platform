"""
Retrieval service: vector / hybrid / entity-boosted search with optional
AML query expansion and risk-based re-scoring.

This layer is decoupled from the ADK tool so it can be reused in batch
evaluation, CLI scripts, and other agents.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from agents.rag_agent.aml.entity_extractor import EntityExtractor
from agents.rag_agent.aml.query_expansion import QueryExpander
from agents.rag_agent.aml.risk_scoring import RiskScorer
from agents.rag_agent.config.settings import get_settings
from agents.rag_agent.db.postgres_client import get_postgres_client
from agents.rag_agent.services.embedding_service import get_embedding_service
from agents.rag_agent.utils.cache import get_cache
from agents.rag_agent.utils.telemetry import RETRIEVAL_LATENCY, traced

log = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    id: str
    document_id: str
    chunk_index: int
    source: str
    content: str
    metadata: dict[str, Any]
    score: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["id"] = str(self.id)
        return d


class RetrievalService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._embed = get_embedding_service()
        self._db = get_postgres_client()
        self._cache = get_cache()
        self._expander = QueryExpander()
        self._entity_extractor = EntityExtractor()
        self._risk_scorer = RiskScorer()

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        *,
        use_aml_expansion: bool | None = None,
    ) -> list[RetrievedChunk]:
        """
        Main entry point. Steps:
            1. (Optional) AML query expansion
            2. (Optional) entity extraction for trigram boosting
            3. Embed the query
            4. Hybrid or pure vector search in Postgres
            5. Risk re-scoring (AML-aware)
            6. Truncate to top_k
        """
        cfg = self._settings.retrieval
        aml_cfg = self._settings.aml
        top_k = top_k or cfg.top_k
        use_aml = use_aml_expansion if use_aml_expansion is not None else aml_cfg.enabled

        t0 = time.perf_counter()
        with traced("rag.retrieve", query_length=len(query), top_k=top_k):
            expanded_query = (
                self._expander.expand(query) if use_aml else query
            )
            entities = self._entity_extractor.extract(query) if use_aml else []

            cache_key = {
                "q": expanded_query,
                "k": top_k,
                "f": filters or {},
                "e": entities,
                "hybrid": cfg.hybrid_search,
            }
            cached = await self._cache.get("retrieve", cache_key)
            if cached is not None:
                RETRIEVAL_LATENCY.record(
                    (time.perf_counter() - t0) * 1000, {"path": "cache"}
                )
                return [RetrievedChunk(**c) for c in cached]

            embedding = await self._embed.embed_query(expanded_query)

            # Candidate pool is larger than top_k to allow re-scoring headroom.
            candidate_pool = max(top_k * 4, cfg.rerank_top_n)

            if entities:
                rows = await self._db.entity_boosted_search(
                    query_embedding=embedding,
                    entities=entities,
                    top_k=candidate_pool,
                    metadata_filter=filters,
                )
            elif cfg.hybrid_search:
                rows = await self._db.hybrid_search(
                    query_text=expanded_query,
                    query_embedding=embedding,
                    top_k=candidate_pool,
                    vector_weight=cfg.hybrid_vector_weight,
                    bm25_weight=cfg.hybrid_bm25_weight,
                    metadata_filter=filters,
                    candidate_pool=candidate_pool,
                )
            else:
                rows = await self._db.similarity_search(
                    query_embedding=embedding,
                    top_k=candidate_pool,
                    metadata_filter=filters,
                )

            chunks = [_row_to_chunk(r) for r in rows]

            if use_aml:
                chunks = self._risk_scorer.rescore(query, chunks)

            chunks = chunks[:top_k]

            await self._cache.set(
                "retrieve", cache_key, [c.to_dict() for c in chunks]
            )

        RETRIEVAL_LATENCY.record(
            (time.perf_counter() - t0) * 1000, {"path": "db"}
        )
        log.info(
            "retrieve.done",
            extra={
                "returned": len(chunks),
                "top_score": chunks[0].score if chunks else None,
                "entities": entities,
                "expanded": expanded_query != query,
            },
        )
        return chunks


def _row_to_chunk(r: dict[str, Any]) -> RetrievedChunk:
    md = r.get("metadata") or {}
    if isinstance(md, str):  # some drivers return JSONB as str
        import json
        md = json.loads(md)
    return RetrievedChunk(
        id=str(r["id"]),
        document_id=r["document_id"],
        chunk_index=r["chunk_index"],
        source=r["source"],
        content=r["content"],
        metadata=md,
        score=float(r["score"]),
    )


_svc: RetrievalService | None = None


def get_retrieval_service() -> RetrievalService:
    global _svc
    if _svc is None:
        _svc = RetrievalService()
    return _svc
