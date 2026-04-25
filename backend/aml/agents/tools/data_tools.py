"""Read-side tools: KYC lookup, Neo4j hop traversal, external search.

The actual data sources (core-banking KYC, Neo4j cluster, Google Search /
Bing Web Search) are pluggable.  Each tool depends on a Provider protocol
that can be swapped for a stub during tests.

The default providers raise NotImplementedError unless explicitly
configured via `set_*_provider(...)`; this keeps the import side-effect
free and forces every deployment to make a conscious wiring choice.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Protocol

from .registry import ToolSpec, register_tool

log = logging.getLogger(__name__)

# =============================================================================
# Provider protocols — concrete data layer is injected at startup.
# =============================================================================


class KycProvider(Protocol):
    async def lookup(self, party_id: str) -> dict[str, Any]: ...


class GraphProvider(Protocol):
    async def hop_neighbors(
        self,
        subject_party_id: str,
        hop_distance: int,
        time_window_days: int,
    ) -> list[dict[str, Any]]: ...


class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int) -> list[dict[str, Any]]: ...


# Module-level provider slots (set at startup, never at import).
_kyc_provider: KycProvider | None = None
_graph_provider: GraphProvider | None = None
_search_provider: SearchProvider | None = None


def set_kyc_provider(p: KycProvider) -> None:
    global _kyc_provider
    _kyc_provider = p


def set_graph_provider(p: GraphProvider) -> None:
    global _graph_provider
    _graph_provider = p


def set_search_provider(p: SearchProvider) -> None:
    global _search_provider
    _search_provider = p


def _require(provider: Any, name: str) -> Any:
    if provider is None:
        raise RuntimeError(
            f"{name} provider not configured — call set_{name.lower()}_provider() at startup"
        )
    return provider


# =============================================================================
# Tool: kyc_lookup
# =============================================================================


async def kyc_lookup(party_id: str) -> dict[str, Any]:
    """Fetch the internal KYC record for a party.

    Returns
    -------
    {
      "party_id": str,
      "found": bool,
      "record": {
        "name": str,
        "dob": str|null,
        "nationality": str|null,
        "country_of_residence": str|null,
        "occupation": str|null,
        "pep": bool,
        "sanctions_clear": bool,
        "risk_rating": "LOW|MEDIUM|HIGH",
        "kyc_refreshed_at": iso8601 string|null,
        ...
      } | null
    }
    """
    provider = _require(_kyc_provider, "KYC")
    record = await provider.lookup(party_id)
    return {
        "party_id": party_id,
        "found": record is not None,
        "record": record,
    }


KYC_LOOKUP_SPEC = register_tool(
    ToolSpec(
        name="kyc_lookup",
        description=(
            "Fetch the internal KYC record for a single party (subject or "
            "counter-party).  Returns the full structured KYC profile."
        ),
        parameters={
            "type": "object",
            "properties": {
                "party_id": {
                    "type": "string",
                    "description": "External party identifier (customer number, CIF, etc.).",
                },
            },
            "required": ["party_id"],
        },
        fn=kyc_lookup,
    )
)


# =============================================================================
# Tool: neo4j_hop_traversal
# =============================================================================


async def neo4j_hop_traversal(
    subject_party_id: str,
    hop_distance: int = 1,
    time_window_days: int = 90,
) -> dict[str, Any]:
    """Return counter-parties reachable from the subject within `hop_distance`
    hops, restricted to relationships observed within `time_window_days`.

    Each entry includes the relationship type, total transaction value, and
    any pre-computed risk flags (PEP, shell company, high-risk country).

    Returns
    -------
    {
      "subject_party_id": str,
      "hop_distance": int,
      "time_window_days": int,
      "neighbors": [
        {
          "party_external_id": str,
          "party_name": str,
          "party_type": "INDIVIDUAL|CORPORATE|TRUST|OTHER",
          "relationship": str,           # e.g. "wire_to", "received_from"
          "txn_count": int,
          "total_value": number,
          "currency": str,
          "risk_flags": {"is_pep": bool, "is_shell": bool, "high_risk_country": bool},
        }, ...
      ],
      "count": int
    }
    """
    if hop_distance < 1 or hop_distance > 3:
        return {
            "subject_party_id": subject_party_id,
            "hop_distance": hop_distance,
            "neighbors": [],
            "count": 0,
            "error": "hop_distance must be in [1, 3]",
        }
    provider = _require(_graph_provider, "Graph")
    neighbors = await provider.hop_neighbors(
        subject_party_id=subject_party_id,
        hop_distance=hop_distance,
        time_window_days=time_window_days,
    )
    return {
        "subject_party_id": subject_party_id,
        "hop_distance": hop_distance,
        "time_window_days": time_window_days,
        "neighbors": neighbors,
        "count": len(neighbors),
    }


NEO4J_HOP_SPEC = register_tool(
    ToolSpec(
        name="neo4j_hop_traversal",
        description=(
            "Traverse the investigation graph N hops from the subject party. "
            "Use hop_distance=1 for direct counter-parties, hop_distance=2 for "
            "their counter-parties.  Always restrict by time_window_days."
        ),
        parameters={
            "type": "object",
            "properties": {
                "subject_party_id": {"type": "string"},
                "hop_distance": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
                "time_window_days": {"type": "integer", "minimum": 1, "default": 90},
            },
            "required": ["subject_party_id"],
        },
        fn=neo4j_hop_traversal,
    )
)


# =============================================================================
# Tool: external_search
# =============================================================================


async def external_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search the open web for adverse media, sanctions, and corporate
    registry hits.  Use for due-diligence enrichment — never for primary
    transaction facts.

    Returns
    -------
    {
      "query": str,
      "results": [
        {
          "title": str,
          "url": str,
          "snippet": str,
          "source": str,                 # e.g. "ofac.treasury.gov"
          "category": "SANCTIONS|ADVERSE_MEDIA|REGISTRY|OTHER",
          "severity": "low|medium|high",
          "published_at": iso8601 string|null
        }, ...
      ],
      "count": int
    }
    """
    if not query.strip():
        return {"query": query, "results": [], "count": 0}
    capped = max(1, min(int(max_results), 10))
    provider = _require(_search_provider, "Search")
    results = await provider.search(query=query, max_results=capped)
    return {"query": query, "results": results, "count": len(results)}


EXTERNAL_SEARCH_SPEC = register_tool(
    ToolSpec(
        name="external_search",
        description=(
            "Open-web search for adverse media, sanctions hits, and corporate "
            "registry information about a party.  Subject to API rate limits — "
            "use sparingly."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search query.  Include the party name and qualifiers like 'sanction', 'fraud', 'shell company'.",
                },
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            },
            "required": ["query"],
        },
        fn=external_search,
    )
)
