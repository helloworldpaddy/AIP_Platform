"""
Ingestion pipeline.

Pipeline stages:
    1. Enumerate files (from a local path or pluggable StorageAdapter)
    2. Extract text (PDF / DOCX / TXT / MD)
    3. Chunk with overlap
    4. Embed chunks (batched)
    5. Upsert into Postgres with metadata

Supports incremental indexing: re-ingesting the same file replaces its
chunks (keyed on `document_id`).
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agents.rag_agent.config.settings import get_settings
from agents.rag_agent.db.postgres_client import get_postgres_client
from agents.rag_agent.services.embedding_service import get_embedding_service
from agents.rag_agent.utils.chunking import TextChunker
from agents.rag_agent.utils.telemetry import traced
from agents.rag_agent.utils.text_extraction import LocalFileStorage, StorageAdapter, extract_text

log = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    document_id: str
    source: str
    chunks_written: int
    bytes_read: int
    duration_ms: float


class IngestionService:
    def __init__(self, storage: StorageAdapter | None = None) -> None:
        self._settings = get_settings()
        self._embed = get_embedding_service()
        self._db = get_postgres_client()
        self._storage = storage or LocalFileStorage()
        self._chunker = TextChunker(
            chunk_size=self._settings.ingestion.chunk_size,
            chunk_overlap=self._settings.ingestion.chunk_overlap,
        )

    async def ingest_path(
        self,
        path: str,
        *,
        tags: list[str] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> list[IngestionResult]:
        """
        Ingest a file or every supported file under a directory.
        Returns one result per document processed.
        """
        supported = set(self._settings.ingestion.supported_extensions)
        max_bytes = self._settings.ingestion.max_file_mb * 1024 * 1024
        results: list[IngestionResult] = []

        for file_path in self._storage.list_files(path):
            if file_path.suffix.lower() not in supported:
                continue
            if file_path.stat().st_size > max_bytes:
                log.warning(
                    "ingest.skip.too_large",
                    extra={"path": str(file_path), "max_mb": self._settings.ingestion.max_file_mb},
                )
                continue
            try:
                result = await self.ingest_file(
                    file_path, tags=tags, extra_metadata=extra_metadata
                )
                results.append(result)
            except Exception:
                log.exception("ingest.file.failed", extra={"path": str(file_path)})
        return results

    async def ingest_file(
        self,
        path: Path,
        *,
        tags: list[str] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        with traced("rag.ingest", path=str(path)):
            t0 = time.perf_counter()
            text = extract_text(path)
            if not text.strip():
                raise ValueError(f"Extracted empty text from {path}")

            document_id = _document_id_for(path, text)

            # Incremental re-ingest: purge stale chunks for this document_id.
            deleted = await self._db.delete_by_document_id(document_id)
            if deleted:
                log.info(
                    "ingest.replacing",
                    extra={"document_id": document_id, "deleted": deleted},
                )

            chunks = self._chunker.chunk(text)
            texts = [c.content for c in chunks]
            embeddings = await self._embed.embed_documents(texts)

            base_meta = {
                "filename": path.name,
                "extension": path.suffix.lower(),
                "tags": tags or [],
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                **(extra_metadata or {}),
            }

            rows: list[dict[str, Any]] = []
            for chunk, emb in zip(chunks, embeddings, strict=True):
                rows.append(
                    {
                        "document_id": document_id,
                        "chunk_index": chunk.index,
                        "source": str(path),
                        "content": chunk.content,
                        "embedding": emb,
                        "metadata": {
                            **base_meta,
                            "token_count": chunk.token_count,
                            "char_start": chunk.char_start,
                            "char_end": chunk.char_end,
                        },
                    }
                )

            written = await self._db.upsert_chunks(rows)
            duration_ms = (time.perf_counter() - t0) * 1000

        log.info(
            "ingest.file.done",
            extra={
                "document_id": document_id,
                "chunks": written,
                "duration_ms": duration_ms,
            },
        )
        return IngestionResult(
            document_id=document_id,
            source=str(path),
            chunks_written=written,
            bytes_read=len(text.encode("utf-8")),
            duration_ms=duration_ms,
        )

    async def delete_document(self, document_id: str) -> int:
        return await self._db.delete_by_document_id(document_id)


def _document_id_for(path: Path, text: str) -> str:
    """
    Stable document id derived from absolute path + content hash.

    Path gives human-recognizable identity; content hash makes the id
    change automatically when the file is updated.
    """
    h = hashlib.sha256()
    h.update(str(path.resolve()).encode("utf-8"))
    h.update(b"\0")
    h.update(text.encode("utf-8"))
    return h.hexdigest()[:32]


_svc: IngestionService | None = None


def get_ingestion_service() -> IngestionService:
    global _svc
    if _svc is None:
        _svc = IngestionService()
    return _svc
