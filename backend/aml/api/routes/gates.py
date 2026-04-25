"""Human-gate resolution endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from ...models.state import HumanGate
from ...orchestrator import Orchestrator
from ..dependencies import current_analyst, get_db, get_orchestrator
from ..schemas import ResolveGateRequest

router = APIRouter(prefix="/gates", tags=["gates"])


@router.post("/{gate_id}/resolve", response_model=HumanGate)
async def resolve_gate(
    gate_id: UUID,
    body: ResolveGateRequest,
    orch: Orchestrator = Depends(get_orchestrator),
    analyst: str = Depends(current_analyst),
) -> HumanGate:
    return await orch.resolve_gate(
        gate_id=gate_id,
        status=body.status,
        analyst_id=analyst,
        notes=body.notes,
    )
