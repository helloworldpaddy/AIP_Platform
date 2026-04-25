"""Audit-trail listing + chain integrity check."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ...db.client import AmlDbClient
from ...models.state import AuditEvent
from ..dependencies import get_db
from ..schemas import AuditChainStatus

router = APIRouter(prefix="/cases/{case_id}/audit", tags=["audit"])


@router.get("", response_model=list[AuditEvent])
async def list_audit(
    case_id: UUID,
    db: AmlDbClient = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> list[AuditEvent]:
    async with db.connection() as repos:
        return await repos.audit.list_for_case(case_id, limit=limit)


@router.get("/verify", response_model=AuditChainStatus)
async def verify_audit_chain(
    case_id: UUID,
    db: AmlDbClient = Depends(get_db),
) -> AuditChainStatus:
    async with db.connection() as repos:
        ok, first_bad = await repos.audit.verify_chain(case_id)
        return AuditChainStatus(ok=ok, first_bad_id=first_bad)
