"""
End-to-end integration test.

Requires:
    - A running PostgreSQL with pgvector on the configured DSN
    - Valid GOOGLE_API_KEY (or Vertex credentials)

Run with:
    pytest tests/test_integration.py -v -m integration
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"


@pytest.mark.asyncio
async def test_full_pipeline_ingest_then_retrieve():
    """Ingest the sample AML policy and ensure relevant chunks come back."""
    from agents.rag_agent.db.postgres_client import get_postgres_client
    from agents.rag_agent.services.ingestion_service import get_ingestion_service
    from agents.rag_agent.services.retrieval_service import get_retrieval_service

    ingestion = get_ingestion_service()
    retrieval = get_retrieval_service()
    db = get_postgres_client()

    try:
        results = await ingestion.ingest_path(str(SAMPLE_DIR), tags=["test", "aml"])
        assert results, "no files ingested"
        assert all(r.chunks_written > 0 for r in results)

        chunks = await retrieval.retrieve(
            "What is a beneficial owner and when is EDD required?",
            top_k=3,
        )
        assert len(chunks) > 0
        # Expect at least one chunk to mention UBO / beneficial ownership.
        joined = " ".join(c.content.lower() for c in chunks)
        assert "beneficial" in joined or "ubo" in joined

        # Sanctions query should surface the sanctions-heavy chunk.
        chunks = await retrieval.retrieve("OFAC sanctions and high-risk jurisdictions", top_k=3)
        joined = " ".join(c.content.lower() for c in chunks)
        assert "ofac" in joined or "sanction" in joined
    finally:
        # Clean up chunks created by this test.
        for r in results:
            await ingestion.delete_document(r.document_id)
        await db.close()
