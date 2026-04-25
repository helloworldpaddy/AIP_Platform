"""Narrative editing + submission."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from ...db.client import AmlDbClient
from ...models.state import Citation, Narrative
from ...orchestrator import Orchestrator
from ..dependencies import current_analyst, get_db, get_orchestrator
from ..schemas import UpdateNarrativeRequest

router = APIRouter(prefix="/narratives", tags=["narratives"])


@router.patch("/{narrative_id}", response_model=Narrative)
async def update_narrative(
    narrative_id: UUID,
    body: UpdateNarrativeRequest,
    db: AmlDbClient = Depends(get_db),
    analyst: str = Depends(current_analyst),
) -> Narrative:
    citations = (
        [Citation.model_validate(c) for c in body.citations]
        if body.citations is not None
        else None
    )
    async with db.transaction() as repos:
        return await repos.narratives.update_draft(
            narrative_id=narrative_id,
            rationale=body.rationale,
            markdown_body=body.markdown_body,
            citations=citations,
            human_modified=True,
        )


@router.post("/{narrative_id}/submit", response_model=Narrative)
async def submit_narrative(
    narrative_id: UUID,
    orch: Orchestrator = Depends(get_orchestrator),
    analyst: str = Depends(current_analyst),
) -> Narrative:
    return await orch.submit_narrative(
        narrative_id=narrative_id, analyst_id=analyst
    )
