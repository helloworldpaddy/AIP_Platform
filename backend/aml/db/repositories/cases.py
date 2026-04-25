"""Case aggregate repository."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from ...models.enums import CasePriority, CaseStage, CaseStatus
from ...models.state import Case, CaseCreate
from ._base import row_to_dict, rows_to_dicts


class CasesRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------ writes
    async def create(self, dto: CaseCreate) -> Case:
        row = await self._conn.fetchrow(
            """
            INSERT INTO cases (
                case_number, alert_type, alert_payload,
                subject_party_id, subject_party_name,
                priority, assigned_analyst_id, created_by, updated_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)
            RETURNING *
            """,
            dto.case_number,
            dto.alert_type,
            dto.alert_payload,
            dto.subject_party_id,
            dto.subject_party_name,
            dto.priority.value,
            dto.assigned_analyst_id,
            dto.created_by,
        )
        return Case.model_validate(dict(row))

    async def update_status(
        self,
        case_id: UUID,
        status: CaseStatus,
        updated_by: str,
    ) -> Case:
        row = await self._conn.fetchrow(
            """
            UPDATE cases
               SET status = $2, updated_by = $3
             WHERE id = $1
            RETURNING *
            """,
            case_id,
            status.value,
            updated_by,
        )
        if row is None:
            raise LookupError(f"case {case_id} not found")
        return Case.model_validate(dict(row))

    async def advance_stage(
        self,
        case_id: UUID,
        stage: CaseStage,
        updated_by: str,
    ) -> Case:
        row = await self._conn.fetchrow(
            """
            UPDATE cases
               SET current_stage = $2, updated_by = $3
             WHERE id = $1
            RETURNING *
            """,
            case_id,
            stage.value,
            updated_by,
        )
        if row is None:
            raise LookupError(f"case {case_id} not found")
        return Case.model_validate(dict(row))

    async def assign(
        self,
        case_id: UUID,
        analyst_id: str | None,
        updated_by: str,
    ) -> Case:
        row = await self._conn.fetchrow(
            """
            UPDATE cases
               SET assigned_analyst_id = $2, updated_by = $3
             WHERE id = $1
            RETURNING *
            """,
            case_id,
            analyst_id,
            updated_by,
        )
        if row is None:
            raise LookupError(f"case {case_id} not found")
        return Case.model_validate(dict(row))

    async def set_priority(
        self,
        case_id: UUID,
        priority: CasePriority,
        updated_by: str,
    ) -> Case:
        row = await self._conn.fetchrow(
            """
            UPDATE cases
               SET priority = $2, updated_by = $3
             WHERE id = $1
            RETURNING *
            """,
            case_id,
            priority.value,
            updated_by,
        )
        if row is None:
            raise LookupError(f"case {case_id} not found")
        return Case.model_validate(dict(row))

    async def lock(self, case_id: UUID, locked_by: str) -> Case:
        """Mark a case immutable.  After this call, the lock-guard trigger
        rejects every subsequent UPDATE/DELETE on the row."""
        row = await self._conn.fetchrow(
            """
            UPDATE cases
               SET status = 'SUBMITTED',
                   current_stage = 'COMPLETED',
                   locked = TRUE,
                   locked_at = NOW(),
                   locked_by = $2,
                   updated_by = $2
             WHERE id = $1
               AND locked = FALSE
            RETURNING *
            """,
            case_id,
            locked_by,
        )
        if row is None:
            raise LookupError(f"case {case_id} not found or already locked")
        return Case.model_validate(dict(row))

    # ------------------------------------------------------------------ reads
    async def get(self, case_id: UUID) -> Case | None:
        row = await self._conn.fetchrow("SELECT * FROM cases WHERE id = $1", case_id)
        d = row_to_dict(row)
        return Case.model_validate(d) if d else None

    async def get_by_number(self, case_number: str) -> Case | None:
        row = await self._conn.fetchrow(
            "SELECT * FROM cases WHERE case_number = $1", case_number
        )
        d = row_to_dict(row)
        return Case.model_validate(d) if d else None

    async def list_summary(
        self,
        *,
        status: CaseStatus | None = None,
        assigned_analyst_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []

        if status is not None:
            params.append(status.value)
            clauses.append(f"status = ${len(params)}")
        if assigned_analyst_id is not None:
            params.append(assigned_analyst_id)
            clauses.append(f"assigned_analyst_id = ${len(params)}")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        sql = f"""
            SELECT *
              FROM v_case_summary
              {where}
             ORDER BY created_at DESC
             LIMIT ${len(params) - 1}
             OFFSET ${len(params)}
        """
        rows = await self._conn.fetch(sql, *params)
        return rows_to_dicts(rows)
