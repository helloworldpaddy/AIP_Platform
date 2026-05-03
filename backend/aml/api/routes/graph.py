"""Case-graph projection for the analyst console.

Returns a force-directed-friendly `{nodes, links}` payload describing the
investigation graph for one case.  The MVP source is the `case_parties`
table (i.e. exactly what the agents persisted), so the endpoint works
even when Neo4j isn't wired.

When Neo4j is available the response can be augmented with
counter-parties reachable from the subject — gated on the
`?include_neo4j=true` query parameter so callers opt in.  Neo4j-side
nodes are tagged with `kind="party"` and a synthetic `id="party:<extid>"`
so the UI can deduplicate against rows already produced by the
Transaction Enrichment agent.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...agents.tools import data_tools
from ...db.client import AmlDbClient
from ...models.state import InvestigationState
from ..dependencies import current_analyst, get_db, get_state
from ..schemas import CaseGraphResponse, GraphLink, GraphNode

router = APIRouter(prefix="/cases", tags=["graph"])

log = logging.getLogger(__name__)


@router.get("/{case_id}/graph", response_model=CaseGraphResponse)
async def get_case_graph(
    case_id: UUID,
    include_neo4j: bool = Query(
        default=False,
        description=(
            "If true, augment the case_parties projection with one extra hop "
            "from Neo4j around the subject.  Requires `NEO4J_URI` configured."
        ),
    ),
    neo4j_hop: int = Query(default=1, ge=1, le=2),
    neo4j_window_days: int = Query(default=90, ge=1, le=730),
    db: AmlDbClient = Depends(get_db),
) -> CaseGraphResponse:
    state = await get_state(case_id=case_id, db=db)  # 404 if missing
    case = state.case

    subject_id = f"party:{case.subject_party_id}"
    nodes: dict[str, GraphNode] = {
        subject_id: GraphNode(
            id=subject_id,
            label=case.subject_party_name,
            kind="subject",
            party_type=None,
            hop_distance=0,
            verified=None,
            risk_indicators={},
        )
    }
    links: list[GraphLink] = []

    # ---- 1. case_parties projection ---------------------------------------
    for party in state.parties:
        node_id = f"party:{party.party_external_id}"
        nodes[node_id] = GraphNode(
            id=node_id,
            label=party.party_name,
            kind="party",
            party_type=party.party_type.value,
            hop_distance=party.hop_distance,
            verified=party.verified,
            risk_indicators=party.risk_indicators or {},
        )
        # Edge from the subject (or its closer hop) to this party.  We don't
        # have full path information in case_parties, so for hop > 1 we
        # still attach to the subject to keep the projection a tree; the
        # `hop_distance` field on the node carries the real distance for
        # the renderer to apply spacing or color.
        links.append(
            GraphLink(
                source=subject_id,
                target=node_id,
                relationship=party.relationship or "RELATED",
                weight=1.0,
                metadata={"source": "case_parties"},
            )
        )

    source = "case_parties"

    # ---- 2. optional Neo4j augmentation -----------------------------------
    if include_neo4j:
        provider = data_tools._graph_provider  # module-level singleton
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Neo4j graph provider not configured",
            )
        try:
            neighbors = await provider.hop_neighbors(
                subject_party_id=case.subject_party_id,
                hop_distance=neo4j_hop,
                time_window_days=neo4j_window_days,
            )
        except Exception as err:  # noqa: BLE001 — surface as 502
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Neo4j hop failed: {err}",
            ) from err

        for n in neighbors:
            node_id = f"party:{n['party_external_id']}"
            if node_id not in nodes:
                nodes[node_id] = GraphNode(
                    id=node_id,
                    label=n.get("party_name") or n["party_external_id"],
                    kind="party",
                    party_type=n.get("party_type"),
                    hop_distance=int(n.get("hop_distance") or neo4j_hop),
                    verified=None,
                    risk_indicators=n.get("risk_flags") or {},
                )
            links.append(
                GraphLink(
                    source=subject_id,
                    target=node_id,
                    relationship=n.get("relationship") or "RELATED",
                    weight=float(n.get("txn_count") or 1),
                    metadata={
                        "source": "neo4j",
                        "total_value": n.get("total_value"),
                        "currency": n.get("currency"),
                    },
                )
            )
        source = "hybrid" if state.parties else "neo4j"

    return CaseGraphResponse(
        case_id=str(case.id),
        subject_party_id=case.subject_party_id,
        nodes=list(nodes.values()),
        links=links,
        source=source,
    )


@router.post("/{case_id}/graph/sync-transactions")
async def sync_case_transactions_to_neo4j(
    case_id: UUID,
    state: InvestigationState = Depends(get_state),
    analyst: str = Depends(current_analyst),
) -> dict[str, int]:
    """Materialize `case_transactions` from Postgres into Neo4j (idempotent).

    Requires Neo4j wired at API startup. Uses the same Party/Relationship shape
    as `hop_neighbors` (`last_seen` on :TRANSFERRED_TO from ledger `booked_at`).
    """
    provider = data_tools._graph_provider
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j graph provider not configured",
        )

    txns = state.case_transactions
    if not txns:
        return {"synced": 0}

    log.info(
        "graph.sync_transactions case_id=%s analyst=%s rows=%s",
        case_id,
        analyst,
        len(txns),
    )
    n = await provider.sync_case_transactions(
        subject_party_id=state.case.subject_party_id,
        subject_party_name=state.case.subject_party_name,
        case_id=case_id,
        transactions=txns,
    )
    return {"synced": n}
