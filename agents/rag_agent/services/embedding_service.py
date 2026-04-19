"""
Gemini embedding service.

Uses `google.genai` (the unified SDK that works with both AI Studio and
Vertex-hosted Gemini). The service:
    - Batches texts up to `embedding_batch_size` per API call
    - Retries with exponential backoff on transient errors
    - Validates that returned vectors match `embedding_dim`
    - Supports separate task types for documents vs queries
"""
from __future__ import annotations

import asyncio
import logging
from typing import Iterable, Sequence

from google import genai
from google.genai import types as genai_types
from tenacity import retry, stop_after_attempt, wait_exponential

from agents.rag_agent.config.settings import get_settings
from agents.rag_agent.utils.cache import get_cache
from agents.rag_agent.utils.chunking import batched
from agents.rag_agent.utils.telemetry import EMBED_LATENCY, timed

log = logging.getLogger(__name__)

TASK_DOCUMENT = "RETRIEVAL_DOCUMENT"
TASK_QUERY = "RETRIEVAL_QUERY"


class EmbeddingService:
    def __init__(self) -> None:
        self._settings = get_settings().gemini
        self._cache = get_cache()
        self._client = self._build_client()

    def _build_client(self) -> genai.Client:
        if self._settings.use_vertex:
            return genai.Client(
                vertexai=True,
                project=self._settings.project,
                location=self._settings.location,
            )
        api_key = (
            self._settings.api_key.get_secret_value()
            if self._settings.api_key else None
        )
        return genai.Client(api_key=api_key)

    @property
    def dim(self) -> int:
        return self._settings.embedding_dim

    @timed(EMBED_LATENCY, label="embed_query")
    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        cached = await self._cache.get(
            "emb:q", {"model": self._settings.embedding_model, "text": text}
        )
        if cached is not None:
            return cached
        vectors = await self._embed([text], task_type=TASK_QUERY)
        vec = vectors[0]
        await self._cache.set(
            "emb:q", {"model": self._settings.embedding_model, "text": text}, vec
        )
        return vec

    @timed(EMBED_LATENCY, label="embed_documents")
    async def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        """Embed many document chunks, batching requests."""
        if not texts:
            return []
        all_vectors: list[list[float]] = []
        for batch in batched(texts, self._settings.embedding_batch_size):
            vectors = await self._embed(batch, task_type=TASK_DOCUMENT)
            all_vectors.extend(vectors)
        return all_vectors

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=16),
    )
    async def _embed(
        self,
        texts: Sequence[str],
        *,
        task_type: str,
    ) -> list[list[float]]:
        # google-genai exposes a sync embed_content; run it in a thread so
        # we don't block the event loop during bulk ingests.
        def _call():
            return self._client.models.embed_content(
                model=self._settings.embedding_model,
                contents=list(texts),
                config=genai_types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.dim,
                ),
            )

        resp = await asyncio.to_thread(_call)
        vectors = [list(e.values) for e in resp.embeddings]
        self._validate_dims(vectors)
        return vectors

    def _validate_dims(self, vectors: Iterable[list[float]]) -> None:
        for v in vectors:
            if len(v) != self.dim:
                raise ValueError(
                    f"Embedding dim mismatch: got {len(v)}, expected {self.dim}. "
                    f"Check EMBEDDING_DIM against the chosen model."
                )


_svc: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _svc
    if _svc is None:
        _svc = EmbeddingService()
    return _svc
