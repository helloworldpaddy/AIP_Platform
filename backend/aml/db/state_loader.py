"""Build an `InvestigationState` aggregate from the per-table repositories.

Used by both the FastAPI read endpoint (`GET /cases/{id}`) and by the
orchestrator at the start of each agent stage.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from ..models.enums import AgentName, AgentRunStatus, CaseStage, GateStatus
from ..models.state import (
    AgentRun,
    HumanGate,
    InvestigationState,
    StageProgress,
)
from .client import AmlRepositories

# Mapping from a case stage to the agent that owns it.
_STAGE_AGENT: dict[CaseStage, AgentName | None] = {
    CaseStage.INTAKE: None,
    CaseStage.INITIAL_ASSESSMENT: AgentName.INITIAL_ASSESSMENT,
    CaseStage.TRANSACTION_ENRICHMENT: AgentName.TRANSACTION_ENRICHMENT,
    CaseStage.DUE_DILIGENCE: AgentName.DUE_DILIGENCE,
    CaseStage.CASE_ANALYSIS: AgentName.CASE_ANALYSIS,
    CaseStage.COMPLETED: None,
}


def _progress_for(
    stage: CaseStage,
    agent: AgentName,
    runs: list[AgentRun],
    gates: list[HumanGate],
) -> StageProgress:
    latest = max(
        (r for r in runs if r.agent == agent),
        key=lambda r: r.attempt,
        default=None,
    )
    blocking = next(
        (
            g
            for g in gates
            if g.blocks_agent == agent and g.status == GateStatus.OPEN_REQUIRED
        ),
        None,
    )

    status = latest.status if latest else AgentRunStatus.PENDING
    requires_review = status in {
        AgentRunStatus.AWAITING_REVIEW,
        AgentRunStatus.MODIFIED,
    }
    return StageProgress(
        stage=stage,
        agent=agent,
        status=status,
        latest_run_id=latest.id if latest else None,
        requires_review=requires_review,
        blocking_gate=blocking,
        started_at=latest.started_at if latest else None,
        completed_at=latest.completed_at if latest else None,
    )


async def load_investigation_state(
    repos: AmlRepositories, case_id: UUID
) -> InvestigationState:
    case = await repos.cases.get(case_id)
    if case is None:
        raise LookupError(f"case {case_id} not found")

    agent_runs = await repos.agent_runs.list_for_case(case_id)
    evidence = await repos.evidence.list_for_case(case_id)
    parties = await repos.parties.list_for_case(case_id)
    gates = await repos.gates.list_for_case(case_id)
    narratives = await repos.narratives.list_for_case(case_id)

    try:
        case_transactions = await repos.case_monitoring.list_transactions_for_case(
            case_id
        )
    except asyncpg.exceptions.UndefinedTableError:
        case_transactions = []

    try:
        swift_messages = await repos.services_swift.list_messages_for_case(case_id)
    except asyncpg.exceptions.UndefinedTableError:
        swift_messages = []

    progress = [
        _progress_for(stage, agent, agent_runs, gates)
        for stage, agent in _STAGE_AGENT.items()
        if agent is not None
    ]

    return InvestigationState(
        case=case,
        agent_runs=agent_runs,
        evidence=evidence,
        parties=parties,
        gates=gates,
        narratives=narratives,
        progress=progress,
        case_transactions=case_transactions,
        swift_messages=swift_messages,
    )
