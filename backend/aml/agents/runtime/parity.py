"""Parity contracts between orchestrator surfaces (Sprint 5).

The production FastAPI trigger, ADK ``orchestrator`` mode, and optional
``trigger_*_via_orchestrator`` tools must agree on run shape after a stub/LLM
turn completes.
"""

from __future__ import annotations

from typing import Any

from ...models.enums import AgentName, AgentRunStatus
from ...models.state import AgentRun

# Minimum keys each stage stub/contract expects in ``output_payload``.
STAGE_OUTPUT_KEYS: dict[AgentName, tuple[str, ...]] = {
    AgentName.INITIAL_ASSESSMENT: ("risk_score",),
    AgentName.TRANSACTION_ENRICHMENT: ("party_count",),
    AgentName.DUE_DILIGENCE: ("sanctions_hits",),
    AgentName.CASE_ANALYSIS: ("classification",),
}

TERMINAL_TRIGGER_STATUSES = frozenset(
    {
        AgentRunStatus.AWAITING_REVIEW,
        AgentRunStatus.COMPLETED,
        AgentRunStatus.MODIFIED,
    }
)


def assert_trigger_parity(run: AgentRun, *, agent: AgentName) -> None:
    """Validate a completed orchestrator trigger matches platform contracts."""
    if run.agent != agent:
        raise AssertionError(f"expected agent {agent.value}, got {run.agent.value}")
    if run.status not in TERMINAL_TRIGGER_STATUSES:
        raise AssertionError(
            f"expected terminal trigger status, got {run.status.value}"
        )
    if run.output_payload is None:
        raise AssertionError("output_payload must be set after trigger")

    required = STAGE_OUTPUT_KEYS.get(agent, ())
    missing = [k for k in required if k not in run.output_payload]
    if missing:
        raise AssertionError(
            f"output_payload missing keys {missing} for {agent.value}: "
            f"{list(run.output_payload.keys())}"
        )


def runs_equivalent(a: AgentRun, b: AgentRun) -> bool:
    """True when two runs represent the same logical trigger outcome."""
    return (
        a.agent == b.agent
        and a.status == b.status
        and (a.output_payload or {}) == (b.output_payload or {})
    )


def parity_report(run: AgentRun) -> dict[str, Any]:
    """JSON-serialisable summary for eval/parity logs."""
    return {
        "run_id": str(run.id),
        "case_id": str(run.case_id),
        "agent": run.agent.value,
        "status": run.status.value,
        "output_keys": sorted((run.output_payload or {}).keys()),
        "requires_review": run.status == AgentRunStatus.AWAITING_REVIEW,
    }
