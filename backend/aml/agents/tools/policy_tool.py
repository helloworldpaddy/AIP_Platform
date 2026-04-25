"""Policy / Grounded-Rules RAG tool.

Reuses the existing pgvector retrieval service from `agents.rag_agent`
(the same one ingested by `scripts/ingest.py`).  Keeps a single source
of truth for policy documents and avoids duplicating embedding logic.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.rag_agent.services.retrieval_service import get_retrieval_service

from .registry import ToolSpec, register_tool

log = logging.getLogger(__name__)


async def policy_rag_search(
    query: str,
    top_k: int = 5,
    tag_filter: str | None = None,
) -> dict[str, Any]:
    """Retrieve the most relevant internal policy paragraphs for a query.

    Returns
    -------
    {
      "query": str,
      "results": [
        {
          "content": str,            # the paragraph text
          "source": str,             # filename or doc URI
          "document_id": str,
          "chunk_index": int,
          "score": float,            # 0..1 relevance
          "metadata": {...}
        }, ...
      ],
      "count": int
    }
    """
    if not query.strip():
        return {"query": query, "results": [], "count": 0}

    capped = max(1, min(int(top_k), 10))
    filters = {"tags": [tag_filter]} if tag_filter else None

    service = get_retrieval_service()
    chunks = await service.retrieve(query=query, top_k=capped, filters=filters)

    return {
        "query": query,
        "results": [c.to_dict() for c in chunks],
        "count": len(chunks),
    }


POLICY_RAG_SPEC = register_tool(
    ToolSpec(
        name="policy_rag_search",
        description=(
            "Search the bank's internal AML policy and procedures corpus "
            "(pgvector-backed RAG).  Use to find the governing rule for a "
            "scenario.  Quote retrieved passages verbatim and cite them."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
                "tag_filter": {
                    "type": "string",
                    "description": "Optional tag (e.g. 'sanctions', 'kyc') to narrow the search.",
                },
            },
            "required": ["query"],
        },
        fn=policy_rag_search,
    )
)
