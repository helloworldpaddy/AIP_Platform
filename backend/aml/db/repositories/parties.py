"""Case-parties repository (output of the Transaction Enrichment agent)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from ...models.enums import PartyType
from ...models.state import CaseParty
from ._base import row_to_dict


def _to_party(row: asyncpg.Record) -> CaseParty:
    return CaseParty.model_validate(dict(row))


class CasePartiesRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def upsert(
        self,
        *,
        case_id: UUID,
        party_external_id: str,
        party_name: str,
        party_type: PartyType,
        relationship: str | None,
        hop_distance: int,
        risk_indicators: dict[str, Any] | None,
        source_evidence_ids: list[UUID],
    ) -> CaseParty:
        row = await self._conn.fetchrow(
            """
            INSERT INTO case_parties (
                case_id, party_external_id, party_name, party_type, relationship,
                hop_distance, risk_indicators, source_evidence_ids
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (case_id, party_external_id, hop_distance) DO UPDATE
              SET party_name          = EXCLUDED.party_name,
                  party_type          = EXCLUDED.party_type,
                  relationship        = EXCLUDED.relationship,
                  risk_indicators     = EXCLUDED.risk_indicators,
                  source_evidence_ids = EXCLUDED.source_evidence_ids
            RETURNING *
            """,
            case_id,
            party_external_id,
            party_name,
            party_type.value,
            relationship,
            hop_distance,
            risk_indicators or {},
            source_evidence_ids,
        )
        return _to_party(row)

    async def list_for_case(self, case_id: UUID) -> list[CaseParty]:
        rows = await self._conn.fetch(
            """
            SELECT * FROM case_parties
             WHERE case_id = $1
             ORDER BY hop_distance, party_name
            """,
            case_id,
        )
        return [_to_party(r) for r in rows]

    async def mark_verified(
        self,
        *,
        party_id: UUID,
        analyst_id: str,
    ) -> CaseParty:
        row = await self._conn.fetchrow(
            """
            UPDATE case_parties
               SET verified = TRUE,
                   verified_at = NOW(),
                   verified_by = $2
             WHERE id = $1
            RETURNING *
            """,
            party_id,
            analyst_id,
        )
        if row is None:
            raise LookupError(f"case_party {party_id} not found")
        return _to_party(row)

    async def all_verified(self, case_id: UUID) -> bool:
        unverified = await self._conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM case_parties
                 WHERE case_id = $1 AND verified = FALSE
            )
            """,
            case_id,
        )
        return not bool(unverified)
