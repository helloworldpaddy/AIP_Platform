"""
ADK function tool that wraps the retrieval service.

The tool is intentionally simple at the interface level — ADK inspects
the signature and docstring to expose the tool to Gemini. Keep the
parameters JSON-friendly (str, dict, int) and the docstring precise —
it is the contract the model sees.
"""
from __future__ import annotations

import logging
from typing import Any

from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

from agents.rag_agent.config.settings import get_settings
from agents.rag_agent.services.retrieval_service import get_retrieval_service

log = logging.getLogger(__name__)


async def postgres_vector_search(
    query: str,
    top_k: int = 5,
    filters_json: str = "",
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Search the internal knowledge base for passages relevant to a query.

    Use this tool whenever you need factual grounding from the ingested
    corpus. The tool performs hybrid (vector + lexical) search over
    PostgreSQL/pgvector and applies AML-aware re-scoring. Return values
    must be quoted verbatim in the final answer.

    Args:
        query: Natural-language question or topic to search for.
        top_k: Maximum number of passages to return (default 5).
        filters_json: Optional JSON string for metadata filtering via JSONB
            containment. Examples: '{"tags": ["policy"]}' or
            '{"extension": ".pdf"}'. Pass an empty string for no filter.

    Returns:
        A dict with:
            - ``results``: list of passages, each with ``content``,
              ``source``, ``score``, and ``metadata``.
            - ``count``: number of passages returned.
    """
    import json

    settings = get_settings()
    effective_k = min(max(top_k, 1), 20)

    filters: dict[str, Any] | None = None
    if filters_json and filters_json.strip():
        try:
            filters = json.loads(filters_json)
        except json.JSONDecodeError as exc:
            return {"count": 0, "results": [], "error": f"invalid filters_json: {exc}"}

    service = get_retrieval_service()
    chunks = await service.retrieve(
        query=query,
        top_k=effective_k,
        filters=filters,
    )

    # ADK tools carry context in `tool_context.state` — useful for
    # sharing retrieved sources with the calling agent (e.g. for citations).
    if tool_context is not None:
        tool_context.state["last_retrieved_sources"] = [
            {"source": c.source, "document_id": c.document_id, "chunk_index": c.chunk_index}
            for c in chunks
        ]

    log.info(
        "tool.postgres_vector_search.done",
        extra={"query_len": len(query), "returned": len(chunks)},
    )

    return {
        "count": len(chunks),
        "results": [c.to_dict() for c in chunks],
        "config": {
            "embedding_model": settings.gemini.embedding_model,
            "hybrid": settings.retrieval.hybrid_search,
            "aml_enabled": settings.aml.enabled,
        },
    }


# ADK FunctionTool wrapper — this is what the agent binds.
postgres_vector_search_tool = FunctionTool(func=postgres_vector_search)
