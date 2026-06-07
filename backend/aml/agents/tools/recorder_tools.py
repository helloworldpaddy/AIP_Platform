"""Write-side tools: `record_evidence`, `record_party`.

Both pull the per-invocation context (`case_id`, `agent_run_id`, `repos`,
`actor_id`) from the contextvar set by the orchestrator — the LLM only
sees pure data parameters.

Returning the freshly-created UUID lets the LLM cite it in the final
output JSON, which is how citations become end-to-end traceable.
"""

from __future__ import annotations

import logging
from typing import Any

from ...models.enums import EvidenceType, PartyType
from ..context import current_tool_context
from .registry import ToolSpec, register_tool

log = logging.getLogger(__name__)


_EVIDENCE_TYPE_VALUES = [e.value for e in EvidenceType]
_PARTY_TYPE_VALUES = [p.value for p in PartyType]


# =============================================================================
# record_evidence
# =============================================================================


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
    """Persist a single piece of evidence to the case ledger.

    Use this BEFORE citing any fact in your final output.  The returned
    `evidence_id` is what you reference in `policy_citations`,
    `evidence_ids`, and narrative footnotes.

    Idempotent: re-recording the same content returns the existing id.

    Returns
    -------
    {"evidence_id": "uuid", "is_new": bool}
    """
    if evidence_type not in _EVIDENCE_TYPE_VALUES:
        return {
            "error": f"unknown evidence_type {evidence_type!r}; "
            f"must be one of {_EVIDENCE_TYPE_VALUES}",
        }
    structured_data: dict[str, Any] = {}
    if structured_data_json:
        try:
            import json

            v = json.loads(structured_data_json)
            structured_data = v if isinstance(v, dict) else {"value": v}
        except Exception as err:  # noqa: BLE001
            return {"error": f"structured_data_json must be valid JSON: {err}"}
    ctx = current_tool_context()
    async with ctx.db_lock:
        evidence = await ctx.repos.evidence.record(
            case_id=ctx.case_id,
            agent_run_id=ctx.agent_run_id,
            evidence_type=EvidenceType(evidence_type),
            source_system=source_system,
            source_uri=source_uri,
            title=title,
            content=content,
            structured_data=structured_data,
            confidence_score=confidence_score,
            contains_pii=bool(contains_pii),
            created_by=ctx.actor_id,
        )
    return {
        "evidence_id": str(evidence.id),
        "evidence_type": evidence.evidence_type.value,
        "title": evidence.title,
    }


RECORD_EVIDENCE_SPEC = register_tool(
    ToolSpec(
        name="record_evidence",
        description=(
            "Persist a fact to the case evidence ledger.  Returns an "
            "evidence_id you MUST cite when referencing this fact in the "
            "output JSON.  Idempotent on (case, content)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "evidence_type": {
                    "type": "string",
                    "enum": _EVIDENCE_TYPE_VALUES,
                },
                "source_system": {
                    "type": "string",
                    "description": "Origin system, e.g. 'core_banking', 'neo4j', 'google_search'.",
                },
                "title": {"type": "string"},
                "content": {
                    "type": "string",
                    "description": "Verbatim text of the evidence (passage, transaction summary, etc.).",
                },
                "source_uri": {"type": "string"},
                "structured_data_json": {
                    "type": "string",
                    "description": "Optional JSON string payload (raw tool result).",
                },
                "confidence_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "contains_pii": {"type": "boolean", "default": False},
            },
            "required": ["evidence_type", "source_system", "title", "content"],
        },
        fn=record_evidence,
    )
)


# =============================================================================
# record_party
# =============================================================================


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

    The returned `party_id` is the row's UUID in `case_parties`.  Reference
    it in your output JSON.  The case will block on Due Diligence until an
    analyst marks every recorded party as verified.

    Idempotent on (case, party_external_id, hop_distance).
    """
    if party_type not in _PARTY_TYPE_VALUES:
        return {
            "error": f"unknown party_type {party_type!r}; "
            f"must be one of {_PARTY_TYPE_VALUES}",
        }
    if hop_distance < 0:
        return {"error": "hop_distance must be >= 0"}

    from uuid import UUID  # local import keeps the module import-light

    ctx = current_tool_context()
    risk_indicators: dict[str, Any] = {}
    if risk_indicators_json:
        try:
            import json

            v = json.loads(risk_indicators_json)
            risk_indicators = v if isinstance(v, dict) else {"value": v}
        except Exception as err:  # noqa: BLE001
            return {"error": f"risk_indicators_json must be valid JSON: {err}"}

    # The model frequently passes non-UUID strings here (party/transaction
    # external ids, or hallucinated values). Coerce tolerantly: keep valid
    # evidence UUIDs, drop the rest with a warning instead of crashing the run.
    evidence_uuids: list[UUID] = []
    skipped: list[str] = []
    for e in source_evidence_ids or []:
        try:
            evidence_uuids.append(UUID(str(e)))
        except (ValueError, AttributeError, TypeError):
            skipped.append(str(e))
    if skipped:
        log.warning(
            "record_party.skipped_invalid_evidence_ids count=%d values=%s",
            len(skipped),
            skipped,
        )

    async with ctx.db_lock:
        party = await ctx.repos.parties.upsert(
            case_id=ctx.case_id,
            party_external_id=party_external_id,
            party_name=party_name,
            party_type=PartyType(party_type),
            relationship=relationship,
            hop_distance=int(hop_distance),
            risk_indicators=risk_indicators,
            source_evidence_ids=evidence_uuids,
        )
    result: dict[str, Any] = {
        "party_id": str(party.id),
        "party_external_id": party.party_external_id,
        "verified": party.verified,
    }
    if skipped:
        result["ignored_source_evidence_ids"] = skipped
        result["note"] = (
            "Some source_evidence_ids were not valid evidence UUIDs and were "
            "ignored. Pass only evidence_id values returned by record_evidence."
        )
    return result


RECORD_PARTY_SPEC = register_tool(
    ToolSpec(
        name="record_party",
        description=(
            "Persist a counter-party on the case (output of graph traversal). "
            "Idempotent on (case, party_external_id, hop_distance).  Returns a "
            "party_id you should reference in the output."
        ),
        parameters={
            "type": "object",
            "properties": {
                "party_external_id": {"type": "string"},
                "party_name": {"type": "string"},
                "party_type": {"type": "string", "enum": _PARTY_TYPE_VALUES},
                "hop_distance": {"type": "integer", "minimum": 0},
                "relationship": {"type": "string"},
                "risk_indicators_json": {
                    "type": "string",
                    "description": "Optional JSON string payload describing risk indicators.",
                },
                "source_evidence_ids": {
                    "type": "array",
                    "items": {"type": "string", "description": "evidence_id from record_evidence"},
                },
            },
            "required": ["party_external_id", "party_name", "party_type", "hop_distance"],
        },
        fn=record_party,
    )
)
