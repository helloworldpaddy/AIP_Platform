"""Party verification endpoint (the typical PARTIES_VERIFIED gate driver)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from ...db.client import AmlDbClient
from ...models.enums import ActorType, AuditEventType
from ...models.state import CaseParty
from ..dependencies import current_analyst, get_db

router = APIRouter(prefix="/parties", tags=["parties"])


@router.post("/{party_id}/verify", response_model=CaseParty)
async def verify_party(
    party_id: UUID,
    db: AmlDbClient = Depends(get_db),
    analyst: str = Depends(current_analyst),
) -> CaseParty:
    async with db.transaction() as repos:
        party = await repos.parties.mark_verified(
            party_id=party_id, analyst_id=analyst
        )
        await repos.audit.append(
            case_id=party.case_id,
            actor_type=ActorType.ANALYST,
            actor_id=analyst,
            event_type=AuditEventType.HUMAN_OVERRIDE,
            event_payload={
                "object": "case_party",
                "party_id": str(party.id),
                "party_external_id": party.party_external_id,
                "verified": True,
            },
        )
        return party
