"""Agent triggers + HITL surface."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from ...models.enums import AgentName
from ...models.state import AgentRun
from ...orchestrator import Orchestrator
from ..dependencies import current_analyst, get_db, get_orchestrator
from ..schemas import OverrideRunRequest, RejectRunRequest, TriggerAgentRequest

# Two routers — keeps the path hierarchy clean (one is per-case, one is per-run).
case_agents_router = APIRouter(prefix="/cases/{case_id}/agents", tags=["agents"])
runs_router = APIRouter(prefix="/agents/runs", tags=["agents"])


@case_agents_router.post(
    "/{agent_name}/trigger",
    response_model=AgentRun,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_agent(
    case_id: UUID,
    agent_name: AgentName,
    body: TriggerAgentRequest | None = None,
    orch: Orchestrator = Depends(get_orchestrator),
    analyst: str = Depends(current_analyst),
) -> AgentRun:
    extra = body.extra_input if body else {}
    return await orch.trigger_agent(
        case_id=case_id,
        agent_name=agent_name,
        triggered_by=analyst,
        extra_input=extra,
    )


@runs_router.get("/{run_id}", response_model=AgentRun)
async def get_run(
    run_id: UUID,
    db=Depends(get_db),
) -> AgentRun:
    async with db.connection() as repos:
        run = await repos.agent_runs.get(run_id)
        if run is None:
            raise LookupError(f"agent_run {run_id} not found")
        return run


@runs_router.post("/{run_id}/approve", response_model=AgentRun)
async def approve_run(
    run_id: UUID,
    orch: Orchestrator = Depends(get_orchestrator),
    analyst: str = Depends(current_analyst),
) -> AgentRun:
    return await orch.approve_run(run_id=run_id, analyst_id=analyst)


@runs_router.post("/{run_id}/reject", response_model=AgentRun)
async def reject_run(
    run_id: UUID,
    body: RejectRunRequest,
    orch: Orchestrator = Depends(get_orchestrator),
    analyst: str = Depends(current_analyst),
) -> AgentRun:
    return await orch.reject_run(
        run_id=run_id, analyst_id=analyst, reason=body.reason
    )


@runs_router.post("/{run_id}/override", response_model=AgentRun)
async def override_run(
    run_id: UUID,
    body: OverrideRunRequest,
    orch: Orchestrator = Depends(get_orchestrator),
    analyst: str = Depends(current_analyst),
) -> AgentRun:
    return await orch.apply_override(
        run_id=run_id,
        analyst_id=analyst,
        new_output=body.new_output,
        diff_ops=body.diff_ops,
    )
