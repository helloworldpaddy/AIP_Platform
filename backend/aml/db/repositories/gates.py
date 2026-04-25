"""Human-in-the-loop gate repository."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from ...models.enums import AgentName, GateStatus
from ...models.state import HumanGate


def _to_gate(row: asyncpg.Record) -> HumanGate:
    return HumanGate.model_validate(dict(row))


class HumanGatesRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def open(
        self,
        *,
        case_id: UUID,
        gate_name: str,
        blocks_agent: AgentName,
        notes: str | None = None,
    ) -> HumanGate:
        """Idempotent: re-opening an existing gate just returns it."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO human_gates (case_id, gate_name, blocks_agent, status, notes)
            VALUES ($1, $2, $3, 'OPEN_REQUIRED', $4)
            ON CONFLICT (case_id, gate_name) DO UPDATE
              SET notes = COALESCE(EXCLUDED.notes, human_gates.notes)
            RETURNING *
            """,
            case_id,
            gate_name,
            blocks_agent.value,
            notes,
        )
        return _to_gate(row)

    async def resolve(
        self,
        *,
        gate_id: UUID,
        status: GateStatus,
        analyst_id: str,
        notes: str | None = None,
    ) -> HumanGate:
        if status == GateStatus.OPEN_REQUIRED:
            raise ValueError("Cannot resolve a gate to OPEN_REQUIRED")
        row = await self._conn.fetchrow(
            """
            UPDATE human_gates
               SET status      = $2,
                   resolved_at = NOW(),
                   resolved_by = $3,
                   notes       = COALESCE($4, notes)
             WHERE id = $1
               AND status = 'OPEN_REQUIRED'
            RETURNING *
            """,
            gate_id,
            status.value,
            analyst_id,
            notes,
        )
        if row is None:
            raise LookupError(
                f"gate {gate_id} not found or already resolved"
            )
        return _to_gate(row)

    async def list_for_case(self, case_id: UUID) -> list[HumanGate]:
        rows = await self._conn.fetch(
            "SELECT * FROM human_gates WHERE case_id = $1 ORDER BY opened_at",
            case_id,
        )
        return [_to_gate(r) for r in rows]

    async def is_blocked(self, case_id: UUID, agent: AgentName) -> bool:
        return bool(
            await self._conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM human_gates
                     WHERE case_id = $1
                       AND blocks_agent = $2
                       AND status = 'OPEN_REQUIRED'
                )
                """,
                case_id,
                agent.value,
            )
        )
