"""Case CRUD + dashboard list."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from ...db.client import AmlDbClient
from ...models.enums import ActorType, AuditEventType, CaseStatus
from ...models.state import Case, CaseCreate, InvestigationState
from ..dependencies import current_analyst, get_db, get_state
from ..schemas import AssignAnalystRequest, UpdatePriorityRequest

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=Case, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CaseCreate,
    db: AmlDbClient = Depends(get_db),
    analyst: str = Depends(current_analyst),
) -> Case:
    # `created_by` in the body wins; fall back to the header if the client
    # left it blank (common for service-to-service intake jobs).
    if not body.created_by:
        body = body.model_copy(update={"created_by": analyst})
    async with db.transaction() as repos:
        case = await repos.cases.create(body)
        await repos.audit.append(
            case_id=case.id,
            actor_type=ActorType.SYSTEM,
            actor_id=body.created_by,
            event_type=AuditEventType.CASE_CREATED,
            event_payload={
                "case_number": case.case_number,
                "alert_type": case.alert_type,
                "priority": case.priority.value,
            },
        )
        return case


@router.get("", response_model=list[dict[str, Any]])
async def list_cases(
    db: AmlDbClient = Depends(get_db),
    status_filter: CaseStatus | None = Query(default=None, alias="status"),
    assigned_analyst_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    async with db.connection() as repos:
        return await repos.cases.list_summary(
            status=status_filter,
            assigned_analyst_id=assigned_analyst_id,
            limit=limit,
            offset=offset,
        )


@router.get("/{case_id}", response_model=InvestigationState)
async def get_case(state: InvestigationState = Depends(get_state)) -> InvestigationState:
    return state


@router.post("/{case_id}/assign", response_model=Case)
async def assign_case(
    case_id: UUID,
    body: AssignAnalystRequest,
    db: AmlDbClient = Depends(get_db),
    analyst: str = Depends(current_analyst),
) -> Case:
    async with db.transaction() as repos:
        return await repos.cases.assign(
            case_id=case_id,
            analyst_id=body.analyst_id,
            updated_by=analyst,
        )


@router.patch("/{case_id}/priority", response_model=Case)
async def set_priority(
    case_id: UUID,
    body: UpdatePriorityRequest,
    db: AmlDbClient = Depends(get_db),
    analyst: str = Depends(current_analyst),
) -> Case:
    async with db.transaction() as repos:
        return await repos.cases.set_priority(
            case_id=case_id,
            priority=body.priority,
            updated_by=analyst,
        )
