"""Orchestrator parity tools — full trigger path from ADK web chat."""

from __future__ import annotations

import logging
from typing import Any

from ...db.client import get_aml_db_client
from ...models.enums import AgentName
from ...orchestrator.service import Orchestrator
from .bootstrap import ensure_runtime_ready
from .case_resolver import load_case_by_number, parse_case_number

log = logging.getLogger(__name__)

_orchestrator: Orchestrator | None = None


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        from ..registry import build_default_agents

        _orchestrator = Orchestrator(get_aml_db_client(), build_default_agents())
    return _orchestrator


def _normalize_case_number(case_number: str) -> str | None:
    case_number = case_number.strip().upper()
    if parse_case_number(case_number):
        return case_number
    if case_number.startswith("AML-"):
        return case_number
    return None


async def trigger_stage_via_orchestrator(
    case_number: str,
    agent_name: AgentName,
) -> dict[str, Any]:
    """Run an AML stage through the production Orchestrator (parity smoke test)."""
    await ensure_runtime_ready()
    normalized = _normalize_case_number(case_number)
    if normalized is None:
        return {"error": f"invalid case_number: {case_number!r}"}

    case = await load_case_by_number(normalized)
    orch = _get_orchestrator()
    run = await orch.trigger_agent(
        case_id=case.id,
        agent_name=agent_name,
        triggered_by="adk_web",
        extra_input={"source": "orchestrator_tool"},
    )
    log.info(
        "runtime.orchestrator_tool.done agent=%s case=%s run_id=%s status=%s",
        agent_name.value,
        normalized,
        run.id,
        run.status.value,
    )
    return {
        "case_number": case.case_number,
        "agent": agent_name.value,
        "run_id": str(run.id),
        "status": run.status.value,
        "output_payload": run.output_payload,
        "requires_review": run.status.value == "AWAITING_REVIEW",
    }


async def trigger_initial_assessment_via_orchestrator(
    case_number: str,
) -> dict[str, Any]:
    """Run Initial Assessment via Orchestrator (``POST .../INITIAL_ASSESSMENT/trigger``)."""
    return await trigger_stage_via_orchestrator(
        case_number, AgentName.INITIAL_ASSESSMENT
    )


async def trigger_transaction_enrichment_via_orchestrator(
    case_number: str,
) -> dict[str, Any]:
    """Run Transaction Enrichment via Orchestrator."""
    return await trigger_stage_via_orchestrator(
        case_number, AgentName.TRANSACTION_ENRICHMENT
    )


async def trigger_due_diligence_via_orchestrator(
    case_number: str,
) -> dict[str, Any]:
    """Run Due Diligence via Orchestrator."""
    return await trigger_stage_via_orchestrator(case_number, AgentName.DUE_DILIGENCE)


async def trigger_case_analysis_via_orchestrator(
    case_number: str,
) -> dict[str, Any]:
    """Run Case Analysis via Orchestrator."""
    return await trigger_stage_via_orchestrator(case_number, AgentName.CASE_ANALYSIS)
