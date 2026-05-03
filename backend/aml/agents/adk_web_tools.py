"""Tool wrappers for ADK Web / ``adk web`` local debugging.

Production agents use :mod:`backend.aml.agents.tools` directly inside the
orchestrator, where :func:`backend.aml.agents.context.bind_tool_context`
provides ``case_id``, ``repos``, and provider wiring.

The ADK Web UI loads ``root_agent`` from ``agents/*/agent.py`` **without**
that context.  These wrappers delegate to the real tools when the orchestrator
context is bound *and* providers exist; otherwise they return **stub**
payloads so the model can still exercise prompts and JSON output (see
``adk_web_stub`` / ``adk_web_note`` flags in results).
"""

from __future__ import annotations

import logging
from typing import Any

from .context import is_tool_context_bound
from .tools.data_tools import (
    external_search,
    kyc_lookup,
    neo4j_hop_traversal,
)
from .tools.policy_tool import policy_rag_search
from .tools.recorder_tools import record_evidence, record_party

log = logging.getLogger(__name__)

_STUB_EVIDENCE_ID = "00000000-0000-4000-8000-000000000001"
_STUB_PARTY_ID = "00000000-0000-4000-8000-000000000002"


def _should_fallback(err: BaseException) -> bool:
    msg = str(err).lower()
    return "agenttoolcontext" in msg or "provider not configured" in msg


async def policy_rag_search_adk_web(
    query: str,
    top_k: int = 5,
    tag_filter: str | None = None,
) -> dict[str, Any]:
    try:
        return await policy_rag_search(query, top_k=top_k, tag_filter=tag_filter)
    except Exception as err:  # noqa: BLE001 — dev UI: still return a shape
        log.warning("adk_web_tools.policy_rag_search fallback: %s", err)
        return {
            "query": query,
            "results": [],
            "count": 0,
            "adk_web_note": f"{err.__class__.__name__}: {err}",
        }


async def record_evidence_adk_web(
    evidence_type: str,
    source_system: str,
    title: str,
    content: str,
    source_uri: str | None = None,
    structured_data_json: str | None = None,
    confidence_score: float | None = None,
    contains_pii: bool = False,
) -> dict[str, Any]:
    if is_tool_context_bound():
        return await record_evidence(
            evidence_type,
            source_system,
            title,
            content,
            source_uri=source_uri,
            structured_data_json=structured_data_json,
            confidence_score=confidence_score,
            contains_pii=contains_pii,
        )
    log.info("adk_web_tools.record_evidence stub (no AgentToolContext)")
    return {
        "evidence_id": _STUB_EVIDENCE_ID,
        "evidence_type": evidence_type,
        "title": title,
        "adk_web_stub": True,
    }


async def record_party_adk_web(
    party_external_id: str,
    party_name: str,
    party_type: str,
    hop_distance: int,
    relationship: str | None = None,
    risk_indicators_json: str | None = None,
    source_evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    if is_tool_context_bound():
        return await record_party(
            party_external_id,
            party_name,
            party_type,
            hop_distance,
            relationship=relationship,
            risk_indicators_json=risk_indicators_json,
            source_evidence_ids=source_evidence_ids,
        )
    log.info("adk_web_tools.record_party stub (no AgentToolContext)")
    return {
        "party_id": _STUB_PARTY_ID,
        "party_external_id": party_external_id,
        "verified": False,
        "adk_web_stub": True,
    }


async def neo4j_hop_traversal_adk_web(
    subject_party_id: str,
    hop_distance: int = 1,
    time_window_days: int = 90,
) -> dict[str, Any]:
    try:
        return await neo4j_hop_traversal(
            subject_party_id,
            hop_distance=hop_distance,
            time_window_days=time_window_days,
        )
    except RuntimeError as err:
        if _should_fallback(err):
            log.info("adk_web_tools.neo4j_hop_traversal stub: %s", err)
            return {
                "subject_party_id": subject_party_id,
                "hop_distance": hop_distance,
                "time_window_days": time_window_days,
                "neighbors": [],
                "count": 0,
                "adk_web_stub": True,
            }
        raise


async def kyc_lookup_adk_web(party_id: str) -> dict[str, Any]:
    try:
        return await kyc_lookup(party_id)
    except RuntimeError as err:
        if _should_fallback(err):
            log.info("adk_web_tools.kyc_lookup stub: %s", err)
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


async def external_search_adk_web(
    query: str, max_results: int = 5
) -> dict[str, Any]:
    try:
        return await external_search(query, max_results=max_results)
    except RuntimeError as err:
        if _should_fallback(err):
            log.info("adk_web_tools.external_search stub: %s", err)
            return {
                "query": query,
                "results": [
                    {
                        "title": "ADK Web stub result",
                        "url": "https://example.invalid",
                        "snippet": "No live search in ADK Web without Search provider.",
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
