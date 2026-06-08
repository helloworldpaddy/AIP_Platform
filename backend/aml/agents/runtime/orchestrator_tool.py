"""Orchestrator parity tools — full trigger path from ADK web chat."""

from __future__ import annotations

import logging
from typing import Any

from ...models.enums import AgentName
from .orchestrator_invoke import invoke_orchestrator_stage

log = logging.getLogger(__name__)


async def trigger_stage_via_orchestrator(
    case_number: str,
    agent_name: AgentName,
) -> dict[str, Any]:
    """Run an AML stage through the production Orchestrator (parity smoke test)."""
    run = await invoke_orchestrator_stage(
        case_number=case_number,
        agent_name=agent_name,
        triggered_by="adk_web",
        extra_input={"source": "orchestrator_tool"},
    )
    return {
        "case_number": case_number.strip().upper(),
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
