"""
ADK function tool that ingests documents into the Postgres/pgvector store.

Mirrors the shape of `postgres_vector_search_tool`:
    - async FunctionTool wrapper
    - JSON-string params for anything Gemini's schema validator can't express
      as a closed object (tags, metadata)
    - returns a structured summary the model can quote

Security note: exposing ingestion as an agent tool means the model can write
to the index. Keep the tool's exposure limited to trusted users; in shared
environments gate it behind an auth-aware wrapper and/or constrain `path`
to an allowlist.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from agents.rag_agent.config.settings import get_settings
from agents.rag_agent.services.ingestion_service import get_ingestion_service

log = logging.getLogger(__name__)


async def postgres_document_ingest(
    path: str,
    tags_csv: str = "",
    extra_metadata_json: str = "",
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Ingest a file or directory of files into the knowledge base.

    Use this tool when the user asks to *load*, *ingest*, *index*, or *add*
    documents so they become searchable by the retrieval tool. Supported
    file types: PDF, DOCX, TXT, MD. Text is chunked with overlap, embedded
    with Gemini, and upserted into PostgreSQL/pgvector. Re-ingesting the
    same file replaces its prior chunks (incremental indexing).

    Args:
        path: Absolute or working-directory-relative path to a file or
            directory. Directories are walked recursively; only files with
            supported extensions are ingested, others are skipped.
        tags_csv: Optional comma-separated tags attached to every chunk's
            metadata, e.g. ``"aml,policy,q2-2026"``.
        extra_metadata_json: Optional JSON object merged into each chunk's
            metadata, e.g. ``'{"owner": "compliance-team", "version": 3}'``.
            Pass an empty string for none.

    Returns:
        A dict with:
            - ``files_ingested``: number of files successfully processed.
            - ``chunks_written``: total chunks inserted or updated.
            - ``total_duration_ms``: wall-clock time for the whole batch.
            - ``results``: per-file summary (source, document_id, chunks,
              duration_ms).
            - ``error``: only present when the input is invalid.
    """
    settings = get_settings()

    target = Path(path).expanduser()
    if not target.exists():
        return {
            "files_ingested": 0,
            "chunks_written": 0,
            "results": [],
            "error": f"path not found: {target}",
        }

    tags = [t.strip() for t in tags_csv.split(",") if t.strip()] if tags_csv else []

    extra_metadata: dict[str, Any] = {}
    if extra_metadata_json and extra_metadata_json.strip():
        try:
            parsed = json.loads(extra_metadata_json)
        except json.JSONDecodeError as exc:
            return {
                "files_ingested": 0,
                "chunks_written": 0,
                "results": [],
                "error": f"invalid extra_metadata_json: {exc}",
            }
        if not isinstance(parsed, dict):
            return {
                "files_ingested": 0,
                "chunks_written": 0,
                "results": [],
                "error": "extra_metadata_json must be a JSON object",
            }
        extra_metadata = parsed

    service = get_ingestion_service()
    results = await service.ingest_path(
        str(target), tags=tags, extra_metadata=extra_metadata
    )

    total_chunks = sum(r.chunks_written for r in results)
    total_ms = sum(r.duration_ms for r in results)

    # Expose document_ids via tool context so the agent / downstream tools
    # can reference them (e.g. follow-up delete or re-index).
    if tool_context is not None:
        tool_context.state["last_ingested_document_ids"] = [
            r.document_id for r in results
        ]

    log.info(
        "tool.postgres_document_ingest.done",
        extra={
            "path": str(target),
            "files": len(results),
            "chunks": total_chunks,
            "duration_ms": total_ms,
        },
    )

    return {
        "files_ingested": len(results),
        "chunks_written": total_chunks,
        "total_duration_ms": round(total_ms, 2),
        "results": [
            {
                "source": r.source,
                "document_id": r.document_id,
                "chunks_written": r.chunks_written,
                "bytes_read": r.bytes_read,
                "duration_ms": round(r.duration_ms, 2),
            }
            for r in results
        ],
        "config": {
            "chunk_size": settings.ingestion.chunk_size,
            "chunk_overlap": settings.ingestion.chunk_overlap,
            "embedding_model": settings.gemini.embedding_model,
        },
    }


postgres_document_ingest_tool = FunctionTool(func=postgres_document_ingest)
