"""Evidence ledger repository."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from ...models.enums import EvidenceType
from ...models.state import Evidence
from ...utils.hashing import content_hash
from ._base import row_to_dict


def _to_evidence(row: asyncpg.Record) -> Evidence:
    return Evidence.model_validate(dict(row))


class EvidenceRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def record(
        self,
        *,
        case_id: UUID,
        agent_run_id: UUID | None,
        evidence_type: EvidenceType,
        source_system: str,
        source_uri: str | None,
        title: str,
        content: str,
        structured_data: dict[str, Any] | None,
        confidence_score: float | None,
        contains_pii: bool,
        created_by: str,
    ) -> Evidence:
        """Idempotent insert keyed by (case_id, content_hash).

        If the same evidence is recorded twice the existing row is returned;
        callers can therefore safely re-run a tool without polluting the
        ledger.
        """
        chash = content_hash(
            source_system=source_system,
            source_uri=source_uri,
            title=title,
            content=content,
            structured_data=structured_data,
        )
        row = await self._conn.fetchrow(
            """
            INSERT INTO evidence_ledger (
                case_id, agent_run_id, evidence_type, source_system, source_uri,
                title, content, structured_data, content_hash,
                confidence_score, contains_pii, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (case_id, content_hash) DO UPDATE
              SET agent_run_id = COALESCE(evidence_ledger.agent_run_id, EXCLUDED.agent_run_id)
            RETURNING *
            """,
            case_id,
            agent_run_id,
            evidence_type.value,
            source_system,
            source_uri,
            title,
            content,
            structured_data or {},
            chash,
            confidence_score,
            contains_pii,
            created_by,
        )
        return _to_evidence(row)

    async def get(self, evidence_id: UUID) -> Evidence | None:
        row = await self._conn.fetchrow(
            "SELECT * FROM evidence_ledger WHERE id = $1", evidence_id
        )
        return _to_evidence(row) if row else None

    async def list_for_case(
        self,
        case_id: UUID,
        *,
        evidence_type: EvidenceType | None = None,
    ) -> list[Evidence]:
        if evidence_type is None:
            rows = await self._conn.fetch(
                "SELECT * FROM evidence_ledger WHERE case_id = $1 ORDER BY retrieved_at",
                case_id,
            )
        else:
            rows = await self._conn.fetch(
                """
                SELECT * FROM evidence_ledger
                 WHERE case_id = $1 AND evidence_type = $2
                 ORDER BY retrieved_at
                """,
                case_id,
                evidence_type.value,
            )
        return [_to_evidence(r) for r in rows]

    async def get_many(self, ids: list[UUID]) -> list[Evidence]:
        if not ids:
            return []
        rows = await self._conn.fetch(
            "SELECT * FROM evidence_ledger WHERE id = ANY($1::uuid[])",
            ids,
        )
        return [_to_evidence(r) for r in rows]
