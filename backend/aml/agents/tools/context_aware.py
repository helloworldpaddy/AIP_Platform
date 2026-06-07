"""Context-aware tool wrappers — the single tool set used everywhere.

These callables are what the AML stage agents expose to
:class:`google.adk.agents.LlmAgent`.  They wrap the raw implementations in
``data_tools`` / ``policy_tool`` / ``recorder_tools`` and adapt behaviour to
the runtime:

* **Orchestrator (production)** — :func:`backend.aml.agents.context.bind_tool_context`
  binds an ``AgentToolContext`` and the data providers are configured, so the
  real implementations run (real DB writes + provider calls).
* **``adk web`` (standalone)** — no context is bound and providers may be
  unset, so the wrappers return safe **stub** payloads (flagged with
  ``adk_web_stub`` / ``adk_web_note``) instead of raising, letting a developer
  exercise the prompt + JSON contract without a database.

The wrapper function *names* match the raw tool names (``record_evidence``,
``record_party``, ``policy_rag_search``, ``kyc_lookup``,
``neo4j_hop_traversal``, ``external_search``) because ADK derives each tool's
declared name from ``func.__name__`` and the orchestrator harvests recorded
ids by matching on those names.
"""

from __future__ import annotations

import logging
from typing import Any

from ..context import is_tool_context_bound
from .data_tools import (
    external_search as _external_search_impl,
    kyc_lookup as _kyc_lookup_impl,
    neo4j_hop_traversal as _neo4j_hop_traversal_impl,
)
from .policy_tool import policy_rag_search as _policy_rag_search_impl
from .recorder_tools import (
    record_evidence as _record_evidence_impl,
    record_party as _record_party_impl,
)

log = logging.getLogger(__name__)

_STUB_EVIDENCE_ID = "00000000-0000-4000-8000-000000000001"
_STUB_PARTY_ID = "00000000-0000-4000-8000-000000000002"


def _should_fallback(err: BaseException) -> bool:
    """True when an error indicates we're running standalone (no orchestrator
    context / unconfigured provider) rather than a genuine runtime failure."""
    msg = str(err).lower()
    return "agenttoolcontext" in msg or "provider not configured" in msg


async def policy_rag_search(
    query: str,
    top_k: int = 5,
    tag_filter: str | None = None,
) -> dict[str, Any]:
    """Search the bank's internal AML policy/procedures corpus (pgvector RAG).

    Use to find the governing rule for a scenario.  Quote retrieved passages
    verbatim and cite them via ``record_evidence``.
    """
    try:
        return await _policy_rag_search_impl(query, top_k=top_k, tag_filter=tag_filter)
    except Exception as err:  # noqa: BLE001 — standalone UI: still return a shape
        log.warning("tools.policy_rag_search fallback: %s", err)
        return {
            "query": query,
            "results": [],
            "count": 0,
            "adk_web_note": f"{err.__class__.__name__}: {err}",
        }


async def record_evidence(
    evidence_type: str,
    source_system: str,
    title: str,
    content: str,
    source_uri: str | None = None,
    structured_data_json: str | None = None,
    confidence_score: float | None = None,
    contains_pii: bool = False,
) -> dict[str, Any]:
    """Persist a single fact to the case evidence ledger.

    Call this BEFORE citing any fact in your output.  The returned
    ``evidence_id`` is what you reference in ``policy_citations``,
    ``evidence_ids``, and narrative footnotes.  Idempotent on (case, content).
    """
    if is_tool_context_bound():
        return await _record_evidence_impl(
            evidence_type,
            source_system,
            title,
            content,
            source_uri=source_uri,
            structured_data_json=structured_data_json,
            confidence_score=confidence_score,
            contains_pii=contains_pii,
        )
    log.info("tools.record_evidence stub (no AgentToolContext)")
    return {
        "evidence_id": _STUB_EVIDENCE_ID,
        "evidence_type": evidence_type,
        "title": title,
        "adk_web_stub": True,
    }


async def record_party(
    party_external_id: str,
    party_name: str,
    party_type: str,
    hop_distance: int,
    relationship: str | None = None,
    risk_indicators_json: str | None = None,
    source_evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Persist a counter-party identified during graph traversal.

    The returned ``party_id`` is the row's UUID in ``case_parties``; reference
    it in your output.  The case blocks on Due Diligence until an analyst marks
    every recorded party verified.  Idempotent on
    (case, party_external_id, hop_distance).
    """
    if is_tool_context_bound():
        return await _record_party_impl(
            party_external_id,
            party_name,
            party_type,
            hop_distance,
            relationship=relationship,
            risk_indicators_json=risk_indicators_json,
            source_evidence_ids=source_evidence_ids,
        )
    log.info("tools.record_party stub (no AgentToolContext)")
    return {
        "party_id": _STUB_PARTY_ID,
        "party_external_id": party_external_id,
        "verified": False,
        "adk_web_stub": True,
    }


async def neo4j_hop_traversal(
    subject_party_id: str,
    hop_distance: int = 1,
    time_window_days: int = 90,
) -> dict[str, Any]:
    """Traverse the investigation graph N hops from the subject party.

    Use ``hop_distance=1`` for direct counter-parties and ``hop_distance=2`` for
    their counter-parties.  Always restrict by ``time_window_days``.
    """
    try:
        return await _neo4j_hop_traversal_impl(
            subject_party_id,
            hop_distance=hop_distance,
            time_window_days=time_window_days,
        )
    except RuntimeError as err:
        if _should_fallback(err):
            log.info("tools.neo4j_hop_traversal stub: %s", err)
            return {
                "subject_party_id": subject_party_id,
                "hop_distance": hop_distance,
                "time_window_days": time_window_days,
                "neighbors": [],
                "count": 0,
                "adk_web_stub": True,
            }
        raise


async def kyc_lookup(party_id: str) -> dict[str, Any]:
    """Fetch the internal KYC record for a single party (subject or
    counter-party).  Returns the full structured KYC profile."""
    try:
        return await _kyc_lookup_impl(party_id)
    except RuntimeError as err:
        if _should_fallback(err):
            log.info("tools.kyc_lookup stub: %s", err)
            return {
                "party_id": party_id,
                "found": True,
                "record": {
                    "name": "ADK Web stub",
                    "pep": False,
                    "sanctions_clear": True,
                    "risk_rating": "LOW",
                },
                "adk_web_stub": True,
            }
        raise


async def external_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Open-web search for adverse media, sanctions hits, and corporate
    registry information about a party.  Use sparingly (rate limited)."""
    try:
        return await _external_search_impl(query, max_results=max_results)
    except RuntimeError as err:
        if _should_fallback(err):
            log.info("tools.external_search stub: %s", err)
            return {
                "query": query,
                "results": [
                    {
                        "title": "ADK Web stub result",
                        "url": "https://example.invalid",
                        "snippet": "No live search in ADK Web without a Search provider.",
                        "source": "stub",
                        "category": "OTHER",
                        "severity": "low",
                        "published_at": None,
                    }
                ],
                "count": 1,
                "adk_web_stub": True,
            }
        raise


__all__ = [
    "policy_rag_search",
    "record_evidence",
    "record_party",
    "neo4j_hop_traversal",
    "kyc_lookup",
    "external_search",
]
