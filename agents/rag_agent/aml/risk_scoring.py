"""
Risk-aware re-scoring.

Given a list of already-retrieved chunks, boost those that show AML
signals (sanctions keywords, high-risk jurisdictions, entity matches).
The final score is a weighted blend so vector similarity remains the
dominant signal — domain boosts only break ties and pull buried true
positives to the top.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from agents.rag_agent.aml.entity_extractor import EntityExtractor
from agents.rag_agent.config.settings import get_settings

if TYPE_CHECKING:
    from agents.rag_agent.services.retrieval_service import RetrievedChunk


class RiskScorer:
    def __init__(self) -> None:
        self._settings = get_settings().aml
        self._entity_extractor = EntityExtractor()
        # Lowercase once for cheap substring checks.
        self._keywords = [k.lower() for k in self._settings.boost_keywords]
        self._jurisdictions = [
            j.lower() for j in self._settings.high_risk_jurisdictions
        ]

    def rescore(
        self,
        query: str,
        chunks: list["RetrievedChunk"],
    ) -> list["RetrievedChunk"]:
        if not chunks or not self._settings.enabled:
            return chunks

        weights = self._settings.risk_weights
        w_vec = weights.get("vector", 0.7)
        w_kw = weights.get("keyword", 0.15)
        w_ent = weights.get("entity", 0.15)

        query_entities = [e.lower() for e in self._entity_extractor.extract(query)]

        # Normalize the original vector scores to [0, 1] so weighted sums
        # behave sensibly regardless of the underlying similarity metric.
        max_score = max((c.score for c in chunks), default=1.0) or 1.0
        min_score = min((c.score for c in chunks), default=0.0)
        span = max(max_score - min_score, 1e-6)

        for chunk in chunks:
            norm_vec = (chunk.score - min_score) / span
            content_lc = chunk.content.lower()

            kw_hits = sum(1 for k in self._keywords if k in content_lc)
            juris_hits = sum(1 for j in self._jurisdictions if j in content_lc)
            kw_signal = min((kw_hits + juris_hits) / 3.0, 1.0)

            ent_signal = 0.0
            if query_entities:
                matches = sum(1 for e in query_entities if e in content_lc)
                ent_signal = min(matches / max(len(query_entities), 1), 1.0)

            boosted = (
                w_vec * norm_vec
                + w_kw * kw_signal
                + w_ent * ent_signal
            )
            chunk.metadata["risk_signals"] = {
                "keyword_hits": kw_hits,
                "jurisdiction_hits": juris_hits,
                "entity_matches": ent_signal,
            }
            chunk.score = boosted

        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks
